import pytest
from django.db import IntegrityError

from apps.matches.models import Match, MatchInnings, PlayerMatchPerformance
from apps.teams.models import TeamRoster

from .conftest import auth_client

pytestmark = pytest.mark.django_db


def test_team_list_detail_and_roster(api, make_team, make_player):
    team = make_team(name="Kathmandu Gurkhas")
    make_team(is_active=False)
    captain, other = make_player(full_name="A Captain"), make_player(full_name="B Player")
    TeamRoster.objects.create(team=team, player=captain, season_year=2025, is_captain=True)
    TeamRoster.objects.create(team=team, player=other, season_year=2025)
    TeamRoster.objects.create(team=team, player=other, season_year=2024)

    listing = api.get("/api/v1/teams")
    assert listing.status_code == 200 and listing.data["count"] == 1
    assert api.get(f"/api/v1/teams/{team.pk}").data["name"] == "Kathmandu Gurkhas"
    roster = api.get(f"/api/v1/teams/{team.pk}/roster").data
    assert [r["player_detail"]["full_name"] for r in roster] == ["A Captain", "B Player"]


def test_roster_unique_team_player_season(make_team, make_player):
    team, player = make_team(), make_player()
    TeamRoster.objects.create(team=team, player=player, season_year=2025)
    with pytest.raises(IntegrityError):
        TeamRoster.objects.create(team=team, player=player, season_year=2025)


def test_team_write_requires_staff(api, make_user, make_team):
    payload = {"name": "New", "slug": "new", "short_name": "NEW", "city": "Biratnagar",
               "primary_color": "#000000", "secondary_color": "#FFFFFF"}
    assert api.post("/api/v1/teams", payload, format="json").status_code == 401
    assert auth_client(make_user()).post("/api/v1/teams", payload, format="json").status_code == 403
    staff = auth_client(make_user(is_staff=True))
    assert staff.post("/api/v1/teams", {**payload, "primary_color": "red"}, format="json").status_code == 400
    created = staff.post("/api/v1/teams", payload, format="json")
    assert created.status_code == 201
    assert staff.delete(f"/api/v1/teams/{created.data['id']}").status_code == 204
    assert api.get(f"/api/v1/teams/{created.data['id']}").status_code == 404


def test_match_constraints(make_match, make_team):
    team = make_team()
    with pytest.raises(IntegrityError):
        make_match(home=team, away=team)


def test_toss_and_winner_must_belong_to_match(make_match, make_team):
    match = make_match()
    outsider = make_team()
    match.toss_winner, match.toss_decision = outsider, "bat"
    with pytest.raises(IntegrityError):
        match.save()


def test_winner_rejected_via_api_when_not_in_match(make_user, make_match, make_team):
    match = make_match()
    staff = auth_client(make_user(is_staff=True))
    res = staff.patch(f"/api/v1/matches/{match.pk}", {"winner": str(make_team().pk), "status": "completed"},
                      format="json")
    assert res.status_code == 400 and "winner" in res.data


def test_match_detail_with_innings_and_stats(api, make_match, make_player):
    match = make_match(status=Match.Status.COMPLETED)
    MatchInnings.objects.create(match=match, innings_number=1, batting_team=match.home_team,
                                bowling_team=match.away_team, runs=145, wickets=6, legal_balls=120, extras=8,
                                is_complete=True)
    player = make_player()
    PlayerMatchPerformance.objects.create(match=match, player=player, team=match.home_team, runs_scored=52,
                                          balls_faced=31, fours=4, sixes=3)
    detail = api.get(f"/api/v1/matches/{match.pk}").data
    assert detail["innings"][0]["overs"] == "20.0" and detail["innings"][0]["run_rate"] == "7.25"
    stats = api.get(f"/api/v1/matches/{match.pk}/performances").data
    assert stats[0]["strike_rate"] == "167.74"
    team_filter = api.get(f"/api/v1/matches?team={match.home_team.pk}").data
    assert team_filter["count"] == 1


def test_performance_rejects_impossible_stats(make_match, make_player):
    match = make_match()
    with pytest.raises(IntegrityError):
        PlayerMatchPerformance.objects.create(match=match, player=make_player(), team=match.home_team,
                                              runs_scored=10, balls_faced=5, sixes=3)
