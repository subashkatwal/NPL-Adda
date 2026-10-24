"""
Create a "Meme of the Match" contest for every stored match of a season (default: the latest real
season). Development-sample matches are skipped. Contests are created as drafts unless --publish
is given, so staff can review them first. Idempotent: matches that already have a contest are skipped.

Window per match: entries from the scheduled start until 30h later, votes from the start until 48h later.
Contests only reference the fixture; results are never assumed.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.matches.models import Match, Season
from apps.memelab.models import MemeContest
from apps.memelab.services import contest_window_for

DEV_SOURCE = "development-sample"


class Command(BaseCommand):
    help = "Create Meme of the Match contests for a season's matches (drafts unless --publish)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, help="Season year (default: latest non-sample season).")
        parser.add_argument("--publish", action="store_true", help="Publish the contests immediately.")

    @transaction.atomic
    def handle(self, *args, season=None, publish=False, **options):
        seasons = Season.objects.exclude(source_metadata__source=DEV_SOURCE).order_by("-year")
        target = seasons.filter(year=season).first() if season else seasons.first()
        if target is None:
            raise CommandError("No matching season with real fixtures.")
        created = 0
        matches = Match.objects.filter(season=target).exclude(data_source=DEV_SOURCE).select_related(
            "home_team", "away_team").order_by("starts_at")
        for match in matches:
            if MemeContest.objects.filter(match=match, team__isnull=True).exists():
                continue
            number = f" (Match {match.match_number})" if match.match_number else ""
            MemeContest.objects.create(
                title=f"Meme of the Match: {match.home_team.short_name} vs {match.away_team.short_name}{number}",
                description=(f"Best meme about {match.home_team.name} vs {match.away_team.name}. Enter a published "
                             "meme about the match or either team; one entry per fan, one vote per fan."),
                match=match, status=MemeContest.Status.PUBLISHED if publish else MemeContest.Status.DRAFT,
                **contest_window_for(match),
            )
            created += 1
        state = "published" if publish else "draft"
        self.stdout.write(self.style.SUCCESS(f"{target.name}: {created} {state} contest(s) created."))
