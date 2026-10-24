from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.fanengagement.models import FanActivity, FanBadge, FanProfile, Poll, TeamMembership
from apps.fanengagement.rewards import total_points
from apps.fanengagement.services import score_match_predictions
from apps.matches.models import Match

from .conftest import auth_client

pytestmark = pytest.mark.django_db


def test_profile_requires_exactly_one_owner(make_user):
    with pytest.raises(IntegrityError):
        FanProfile.objects.create(nickname="Nobody")


def test_onboarding_membership_persists_and_switch_keeps_history(make_team, make_user):
    client = auth_client(make_user())
    first, second = make_team(), make_team()
    created = client.post("/api/v1/fanpage", {"nickname": "Rhino", "team": str(first.pk)}, format="json")
    assert created.status_code == 201 and created.data["current_team"]["id"] == str(first.pk)
    assert client.get("/api/v1/fanpage/me/membership").data["team"] == first.pk

    switched = client.post("/api/v1/fanpage/me/membership", {"team": str(second.pk)}, format="json")
    assert switched.status_code == 201
    history = client.get("/api/v1/fanpage/me/memberships").data["results"]
    assert len(history) == 2 and sum(1 for m in history if m["left_at"] is None) == 1
    assert client.post("/api/v1/fanpage/me/membership", {"team": str(second.pk)}, format="json").status_code == 200


def test_one_active_membership_constraint(make_profile, make_team):
    profile = make_profile()
    TeamMembership.objects.create(fan_profile=profile, team=make_team())
    with pytest.raises(IntegrityError):
        TeamMembership.objects.create(fan_profile=profile, team=make_team())


def test_duplicate_profile_rejected(make_profile):
    profile = make_profile()
    res = auth_client(profile.user).post("/api/v1/fanpage", {"nickname": "Again"}, format="json")
    assert res.status_code == 409


def test_team_join_points_not_farmed_by_switching_back(make_profile, make_team):
    profile = make_profile()
    client = auth_client(profile.user)
    a, b = make_team(), make_team()
    for team in (a, b, a, b):
        client.post("/api/v1/fanpage/me/membership", {"team": str(team.pk)}, format="json")
    assert profile.activities.filter(activity_type="team_joined").count() == 2
    assert FanBadge.objects.filter(fan_profile=profile, badge__code="team-member").count() == 1


@pytest.fixture
def open_poll(make_user):
    now = timezone.now()
    poll = Poll.objects.create(question="Best opener?", created_by=make_user(is_staff=True), status=Poll.Status.OPEN,
                               opens_at=now - timedelta(hours=1), closes_at=now + timedelta(hours=1),
                               results_visibility=Poll.ResultsVisibility.AFTER_VOTE)
    poll.options.create(text="A", display_order=1)
    poll.options.create(text="B", display_order=2)
    return poll


def test_vote_once_and_points_once(make_profile, open_poll):
    profile = make_profile()
    client = auth_client(profile.user)
    option = open_poll.options.first()
    assert client.get(f"/api/v1/fanpage/polls/{open_poll.pk}/results").status_code == 403
    first = client.post(f"/api/v1/fanpage/polls/{open_poll.pk}/vote", {"option": str(option.pk)}, format="json")
    assert first.status_code == 201 and first.data["total_votes"] == 1
    again = client.post(f"/api/v1/fanpage/polls/{open_poll.pk}/vote", {"option": str(option.pk)}, format="json")
    assert again.status_code == 409
    assert profile.activities.filter(activity_type="poll_vote").count() == 1
    assert client.get(f"/api/v1/fanpage/polls/{open_poll.pk}/results").status_code == 200


def test_vote_rejects_foreign_option_and_closed_window(make_profile, open_poll, make_user):
    client = auth_client(make_profile().user)
    other = Poll.objects.create(question="Other", created_by=make_user(is_staff=True), status=Poll.Status.OPEN,
                                opens_at=open_poll.opens_at, closes_at=open_poll.closes_at)
    foreign = other.options.create(text="X")
    res = client.post(f"/api/v1/fanpage/polls/{open_poll.pk}/vote", {"option": str(foreign.pk)}, format="json")
    assert res.status_code == 400
    open_poll.closes_at = timezone.now() - timedelta(minutes=1)
    open_poll.opens_at = open_poll.closes_at - timedelta(hours=1)
    open_poll.save()
    res = client.post(f"/api/v1/fanpage/polls/{open_poll.pk}/vote",
                      {"option": str(open_poll.options.first().pk)}, format="json")
    assert res.status_code == 400


def test_prediction_deadline_upsert_and_scoring(make_profile, make_match, make_user):
    profile = make_profile()
    client = auth_client(profile.user)
    match = make_match()
    payload = {"match": str(match.pk), "predicted_winner": str(match.home_team.pk)}
    assert client.post("/api/v1/fanpage/predictions", payload, format="json").status_code == 201
    payload["predicted_winner"] = str(match.away_team.pk)
    assert client.post("/api/v1/fanpage/predictions", payload, format="json").status_code == 201
    assert profile.predictions.count() == 1

    match.starts_at = timezone.now() - timedelta(minutes=1)
    match.save()
    assert client.post("/api/v1/fanpage/predictions", payload, format="json").status_code == 400

    match.status, match.winner = Match.Status.COMPLETED, match.away_team
    match.save()
    staff = auth_client(make_user(is_staff=True))
    assert client.post(f"/api/v1/fanpage/matches/{match.pk}/score-predictions").status_code == 403
    assert staff.post(f"/api/v1/fanpage/matches/{match.pk}/score-predictions").data == {"scored": 1}
    assert score_match_predictions(match) == 0  # idempotent
    assert profile.predictions.get().points_awarded == 10
    assert FanActivity.objects.filter(fan_profile=profile, activity_type="prediction_correct").count() == 1


def test_points_are_server_side_and_private(make_profile, make_team):
    profile, other = make_profile(), make_profile()
    client = auth_client(profile.user)
    client.post("/api/v1/fanpage/me/membership", {"team": str(make_team().pk)}, format="json")
    assert total_points(profile) == 10
    activities = auth_client(other.user).get("/api/v1/fanpage/me/activities").data
    assert activities["count"] == 0
    board = client.get("/api/v1/fanpage/leaderboard").data["results"]
    assert board[0]["id"] == str(profile.pk) and board[0]["points"] == 10
