import pytest
from django.core.management import call_command

from apps.matches.models import Match
from apps.teams.models import Team

pytestmark = pytest.mark.django_db


def test_seed_commands_are_idempotent_and_labelled():
    call_command("seed_npl_teams")
    call_command("seed_npl_teams")
    assert Team.objects.count() == 8
    call_command("seed_dev_matches")
    call_command("seed_dev_matches")
    assert Match.objects.count() == 4
    assert set(Match.objects.values_list("data_source", flat=True)) == {"development-sample"}


def test_npl_2026_fixtures_load_once_with_nepal_times():
    call_command("seed_npl_teams")
    call_command("seed_npl_2026_fixtures")
    call_command("seed_npl_2026_fixtures")
    matches = Match.objects.filter(season__year=2026).order_by("match_number")
    assert matches.count() == 28
    first = matches.first()
    assert (first.home_team.slug, first.away_team.slug) == ("lumbini-lions", "sudurpaschim-royals")
    assert first.starts_at.isoformat() == "2026-10-26T11:15:00+00:00"  # 17:00 NPT (UTC+05:45)
    playoffs = first.season.source_metadata["playoffs"]
    assert [p["stage"] for p in playoffs] == ["Qualifier 1", "Eliminator", "Qualifier 2", "Final"]
    for team in Team.objects.all():  # each team plays seven league games
        assert matches.filter(home_team=team).count() + matches.filter(away_team=team).count() == 7
