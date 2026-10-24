"""
DEVELOPMENT ONLY: create clearly labelled sample fixtures so the UI can be built
without a live-data feed. Every row has data_source="development-sample" and the
season's source_metadata says so; nothing here is a real result.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.matches.models import Match, MatchInnings, Season
from apps.teams.models import Team

DEV_SOURCE = "development-sample"


class Command(BaseCommand):
    help = "Create labelled development fixtures (one sample result, three upcoming). Idempotent."

    @transaction.atomic
    def handle(self, *args, **options):
        teams = list(Team.objects.filter(is_active=True).order_by("display_order")[:8])
        if len(teams) < 4:
            raise CommandError("Run seed_npl_teams first.")
        season, _ = Season.objects.get_or_create(
            year=2099,
            defaults=dict(name="Development sample season", status=Season.Status.ACTIVE,
                          source_metadata={"source": DEV_SOURCE, "note": "Sample data for development, not real."}),
        )
        if Match.objects.filter(season=season).exists():
            self.stdout.write("Development fixtures already exist.")
            return
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        common = dict(season=season, venue="TU International Cricket Ground", data_source=DEV_SOURCE,
                      last_synced_at=timezone.now())

        done = Match.objects.create(
            match_number=1, home_team=teams[0], away_team=teams[1], starts_at=now - timedelta(days=1),
            status=Match.Status.COMPLETED, toss_winner=teams[1], toss_decision=Match.TossDecision.FIELD,
            winner=teams[1], result_text="Sample result: won by 4 wickets", **common,
        )
        MatchInnings.objects.create(match=done, innings_number=1, batting_team=teams[0], bowling_team=teams[1],
                                    runs=152, wickets=7, legal_balls=120, extras=9, is_complete=True)
        MatchInnings.objects.create(match=done, innings_number=2, batting_team=teams[1], bowling_team=teams[0],
                                    runs=153, wickets=6, legal_balls=115, extras=6, target_runs=153, is_complete=True)

        for i, (home, away) in enumerate([(teams[2], teams[3]), (teams[0], teams[2]), (teams[1], teams[3])], start=2):
            Match.objects.create(match_number=i, home_team=home, away_team=away,
                                 starts_at=now + timedelta(days=i - 1, hours=15 - now.hour), **common)
        self.stdout.write(self.style.SUCCESS("Created 4 development-sample matches."))
