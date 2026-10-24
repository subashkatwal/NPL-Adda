"""Staff admin console API (/api/v1/admin)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.content.models import CommunityPost
from apps.fanengagement.models import Badge, FanActivity, Poll, TeamMembership
from apps.matches.models import Match
from apps.moderation.models import ModerationAction, ModerationReport
from apps.teams.models import Team
from tests.conftest import auth_client

A = "/api/v1/admin"


@pytest.fixture
def staff(make_user):
    return make_user(is_staff=True)


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("root@example.com", "Str0ng-pass-123")


def rows(response):
    return response.json()["results"]


def test_admin_api_is_staff_only(api, make_user, staff):
    assert api.get(f"{A}/resources").status_code == 401
    assert auth_client(make_user()).get(f"{A}/teams").status_code == 403
    response = auth_client(staff).get(f"{A}/resources")
    assert response.status_code == 200
    keys = {r["key"] for r in response.json()["resources"]}
    assert {"users", "teams", "matches", "fan-profiles", "posts", "meme-templates", "reports", "polls"} <= keys


def test_every_resource_lists_and_describes_itself(staff):
    client = auth_client(staff)
    for resource in client.get(f"{A}/resources").json()["resources"]:
        url = f"{A}/{resource['key']}"
        assert client.get(url).status_code == 200, url
        meta = client.options(url).json()
        assert meta["resource"]["key"] == resource["key"]
        assert "id" in meta["fields"]


def test_metadata_links_relations_and_choices(staff):
    meta = auth_client(staff).options(f"{A}/matches").json()
    assert meta["fields"]["home_team"]["type"] == "related"
    assert meta["fields"]["home_team"]["related"] == "teams"
    assert {c["value"] for c in meta["fields"]["status"]["choices"]} >= {"scheduled", "completed"}


def test_team_crud_soft_delete_and_restore(staff):
    client = auth_client(staff)
    created = client.post(f"{A}/teams", {"name": "Pokhara Avengers", "slug": "pokhara", "short_name": "PA",
                                         "city": "Pokhara", "primary_color": "#112233",
                                         "secondary_color": "#ffeeaa"}, format="json")
    assert created.status_code == 201, created.json()
    pk = created.json()["id"]
    assert client.patch(f"{A}/teams/{pk}", {"is_active": False}, format="json").json()["is_active"] is False
    assert client.delete(f"{A}/teams/{pk}").status_code == 204
    assert Team.all_objects.get(pk=pk).deleted_at is not None
    assert pk not in {r["id"] for r in rows(client.get(f"{A}/teams"))}
    assert pk in {r["id"] for r in rows(client.get(f"{A}/teams?deleted=only"))}
    assert client.post(f"{A}/teams/{pk}/restore").status_code == 200
    assert Team.objects.filter(pk=pk).exists()


def test_match_rules_are_enforced(staff, season, make_team):
    home, away, other = make_team(), make_team(), make_team()
    body = {"season": str(season.pk), "home_team": str(home.pk), "away_team": str(away.pk), "venue": "TU",
            "starts_at": timezone.now().isoformat(), "status": "scheduled", "winner": str(other.pk)}
    response = auth_client(staff).post(f"{A}/matches", body, format="json")
    assert response.status_code == 400
    assert "winner" in response.json()


def test_score_predictions_action(staff, make_match):
    match = make_match()
    match.status, match.winner = Match.Status.COMPLETED, match.home_team
    match.save()
    response = auth_client(staff).post(f"{A}/matches/{match.pk}/run/score-predictions")
    assert response.status_code == 200
    assert response.json()["_message"] == "Scored 0 prediction(s)."


def test_app_written_history_can_be_corrected_but_not_created(staff, make_profile, make_team):
    profile = make_profile()
    client = auth_client(staff)
    client.post(f"{A}/fan-profiles/{profile.pk}/run/switch-team", {"team": str(make_team().pk)}, format="json")
    activity = FanActivity.objects.filter(fan_profile=profile).first()
    assert client.post(f"{A}/activities", {"points_delta": 5}, format="json").status_code == 405
    assert client.patch(f"{A}/activities/{activity.pk}", {"points_delta": 7}, format="json").json()["points_delta"] == 7
    assert client.delete(f"{A}/activities/{activity.pk}").status_code == 204
    assert client.post(f"{A}/activities/{activity.pk}/restore").status_code == 200


def test_every_resource_allows_edit_and_delete(staff):
    resources = auth_client(staff).get(f"{A}/resources").json()["resources"]
    assert all(r["can_update"] and r["can_delete"] for r in resources)


def test_fan_profile_actions(staff, make_profile, make_team):
    profile = make_profile()
    team = make_team()
    client = auth_client(staff)
    url = f"{A}/fan-profiles/{profile.pk}"
    data = client.post(f"{url}/run/switch-team", {"team": str(team.pk)}, format="json").json()
    assert data["current_team"] == str(team.pk)
    assert TeamMembership.objects.get(fan_profile=profile).join_source == "admin"
    before = data["points"]
    data = client.post(f"{url}/run/adjust-points", {"points": -3, "reason": "spam"}, format="json").json()
    assert data["points"] == before - 3
    badge = Badge.objects.filter(is_active=True).first()
    if badge and not profile.badges.filter(badge=badge).exists():
        assert client.post(f"{url}/run/award-badge", {"badge": str(badge.pk)}, format="json").status_code == 200
        assert client.post(f"{url}/run/award-badge", {"badge": str(badge.pk)}, format="json").status_code == 409
    assert client.post(f"{url}/run/nope").status_code == 404


def test_only_superusers_grant_privileges(staff, superuser, make_user):
    target = make_user()
    response = auth_client(staff).patch(f"{A}/users/{target.pk}", {"is_staff": True}, format="json")
    assert response.status_code == 400
    response = auth_client(superuser).patch(f"{A}/users/{target.pk}", {"is_staff": True, "is_moderator": True},
                                            format="json")
    assert response.status_code == 200, response.json()
    assert response.json()["is_moderator"] is True
    target = User.objects.get(pk=target.pk)
    assert target.is_staff and target.has_perm("moderation.moderate_content")


def test_staff_cannot_lock_themselves_out(staff):
    client = auth_client(staff)
    assert client.patch(f"{A}/users/{staff.pk}", {"is_active": False}, format="json").status_code == 400
    assert client.delete(f"{A}/users/{staff.pk}").status_code == 400


def test_user_create_password_and_soft_delete(superuser):
    client = auth_client(superuser)
    created = client.post(f"{A}/users", {"email": "New@Example.com", "password": "An0ther-strong-pass"},
                          format="json")
    assert created.status_code == 201, created.json()
    user = User.objects.get(email="new@example.com")
    assert user.check_password("An0ther-strong-pass")
    assert client.post(f"{A}/users", {"email": "new@example.com"}, format="json").status_code == 400
    assert client.delete(f"{A}/users/{user.pk}").status_code == 204
    assert not User.all_objects.get(pk=user.pk).is_active
    client.post(f"{A}/users/{user.pk}/restore")
    assert User.objects.get(pk=user.pk).is_active


def test_poll_create_with_options(staff, make_team):
    client = auth_client(staff)
    now = timezone.now()
    body = {"question": "Who wins?", "opens_at": now.isoformat(), "closes_at": now.isoformat(),
            "status": "open", "option_texts": ["A", "B"]}
    assert client.post(f"{A}/polls", body, format="json").status_code == 400  # closes == opens
    body["closes_at"] = (now + timedelta(days=1)).isoformat()
    created = client.post(f"{A}/polls", body, format="json")
    assert created.status_code == 201, created.json()
    poll = Poll.objects.get(pk=created.json()["id"])
    assert poll.created_by == staff
    assert [o["text"] for o in created.json()["options_summary"]] == ["A", "B"]
    client.patch(f"{A}/polls/{poll.pk}", {"option_texts": ["B", "C"]}, format="json")
    assert list(poll.options.values_list("text", flat=True)) == ["A", "B", "C"]


def test_post_moderation_goes_through_audit(staff, superuser, make_profile):
    post = CommunityPost.objects.create(author=make_profile(), body="hello", status="pending_review")
    report = ModerationReport.objects.create(post=post, reason="spam")
    url = f"{A}/posts/{post.pk}"
    assert auth_client(staff).patch(url, {"status": "published"}, format="json").json()["status"] == "pending_review"
    body = {"action_type": "approved", "reason": "fine", "report": str(report.pk)}
    assert auth_client(staff).post(f"{url}/run/moderate", body, format="json").status_code == 403
    response = auth_client(superuser).post(f"{url}/run/moderate", body, format="json")
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "published"
    assert ModerationAction.objects.filter(post=post).count() == 1
    report.refresh_from_db()
    assert report.status == "resolved"


def test_report_resolution_timestamp(staff, make_profile):
    post = CommunityPost.objects.create(author=make_profile(), body="x")
    report = ModerationReport.objects.create(post=post, reason="spam")
    client = auth_client(staff)
    assert client.patch(f"{A}/reports/{report.pk}", {"status": "dismissed"}, format="json").json()["resolved_at"]
    assert client.patch(f"{A}/reports/{report.pk}", {"status": "open"}, format="json").json()["resolved_at"] is None


def test_dashboard(staff, make_profile):
    CommunityPost.objects.create(author=make_profile(), body="pending", status="pending_review")
    data = auth_client(staff).get(f"{A}/dashboard").json()
    assert data["totals"]["posts_pending"] == 1
    assert data["pending_posts"][0]["title"] == "pending"


def test_bulk_delete_and_restore(staff, make_team):
    teams = [make_team(city="Dharan") for _ in range(3)]
    other = make_team(city="Butwal")
    client = auth_client(staff)
    ids = [str(t.pk) for t in teams[:2]]
    assert client.post(f"{A}/teams/bulk", {"action": "delete", "ids": ids}, format="json").json() == {"done": 2, "skipped": []}
    assert Team.objects.filter(city="Dharan").count() == 1
    # "all" applies to every row matching the list filters, not just one page
    response = client.post(f"{A}/teams/bulk?city=Dharan&deleted=include", {"action": "delete", "all": True}, format="json")
    assert response.json()["done"] == 1
    assert Team.objects.filter(pk=other.pk).exists()
    response = client.post(f"{A}/teams/bulk?deleted=only", {"action": "restore", "all": True}, format="json")
    assert response.json()["done"] == 3
    assert client.post(f"{A}/teams/bulk", {"action": "delete"}, format="json").status_code == 400


def test_bulk_delete_skips_rows_a_rule_refuses(staff, make_user):
    victim = make_user()
    body = {"action": "delete", "ids": [str(staff.pk), str(victim.pk)]}
    data = auth_client(staff).post(f"{A}/users/bulk", body, format="json").json()
    assert data["done"] == 1
    assert data["skipped"][0]["id"] == str(staff.pk)
    assert "own account" in data["skipped"][0]["reason"]


def test_ledger_rows_name_what_they_reference(staff, make_profile, make_team):
    profile, team = make_profile(), make_team(name="Far West Stars")
    client = auth_client(staff)
    client.post(f"{A}/fan-profiles/{profile.pk}/run/switch-team", {"team": str(team.pk)}, format="json")
    row = next(r for r in client.get(f"{A}/activities?activity_type=team_joined").json()["results"])
    assert row["reference_uuid_label"] == "Far West Stars"
    assert row["reference_uuid_resource"] == "teams"
    data = client.get(f"{A}/fan-profiles/{profile.pk}").json()
    assert data["current_team_label"] == "Far West Stars" and data["current_team_resource"] == "teams"
