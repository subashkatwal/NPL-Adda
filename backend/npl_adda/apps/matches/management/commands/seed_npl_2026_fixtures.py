"""
Load the published NPL 2026 (third edition) fixture list: 28 league matches plus the four
playoff dates. Schedule announced 19 Sep 2026 and revised for evening matches on 20 Oct 2026
(DRS); times below are the revised ones, in Nepal time.

Playoff opponents are decided by the league table, so they are stored on the season's
``source_metadata["playoffs"]`` until the teams are known; add them as matches then.
Idempotent: re-running updates the same rows (matched by season + match number).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.matches.models import Match, Season
from apps.teams.models import Team

NPT = ZoneInfo("Asia/Kathmandu")
VENUE = "TU International Cricket Ground, Kirtipur"
SOURCE = "published-schedule"
SOURCE_URL = "https://en.wikipedia.org/wiki/2026_Nepal_Premier_League"

T = {
    "BRK": "biratnagar-kings", "CHR": "chitwan-rhinos", "JKB": "janakpur-bolts", "KAY": "karnali-yaks",
    "KTG": "kathmandu-gurkhas", "LUL": "lumbini-lions", "POA": "pokhara-avengers", "SPR": "sudurpaschim-royals",
}

# match number, date, time (NPT), team listed first, team listed second
LEAGUE = [
    (1, "2026-10-26", "17:00", "LUL", "SPR"),
    (2, "2026-10-27", "12:30", "BRK", "CHR"),
    (3, "2026-10-27", "17:00", "KAY", "JKB"),
    (4, "2026-10-28", "17:00", "POA", "SPR"),
    (5, "2026-10-29", "12:30", "JKB", "KTG"),
    (6, "2026-10-29", "17:00", "KAY", "BRK"),
    (7, "2026-10-31", "12:30", "LUL", "CHR"),
    (8, "2026-10-31", "17:00", "SPR", "BRK"),
    (9, "2026-11-01", "17:00", "JKB", "POA"),
    (10, "2026-11-02", "12:30", "KTG", "KAY"),
    (11, "2026-11-02", "17:00", "SPR", "CHR"),
    (12, "2026-11-03", "12:30", "BRK", "JKB"),
    (13, "2026-11-03", "17:00", "LUL", "POA"),
    (14, "2026-11-05", "12:30", "LUL", "JKB"),
    (15, "2026-11-05", "17:00", "KTG", "BRK"),
    (16, "2026-11-06", "12:30", "SPR", "KAY"),
    (17, "2026-11-06", "17:00", "CHR", "POA"),
    (18, "2026-11-07", "17:00", "KTG", "LUL"),
    (19, "2026-11-09", "12:30", "POA", "KAY"),
    (20, "2026-11-09", "17:00", "CHR", "KTG"),
    (21, "2026-11-10", "17:00", "SPR", "JKB"),
    (22, "2026-11-12", "12:30", "BRK", "POA"),
    (23, "2026-11-12", "17:00", "KAY", "LUL"),
    (24, "2026-11-13", "12:30", "KTG", "SPR"),
    (25, "2026-11-13", "17:00", "JKB", "CHR"),
    (26, "2026-11-14", "17:00", "BRK", "LUL"),
    (27, "2026-11-15", "12:30", "CHR", "KAY"),
    (28, "2026-11-15", "17:00", "POA", "KTG"),
]

PLAYOFFS = [
    ("Qualifier 1", "2026-11-17", "16:30", "1st v 2nd in the league table"),
    ("Eliminator", "2026-11-18", "16:30", "3rd v 4th in the league table"),
    ("Qualifier 2", "2026-11-19", "16:30", "Loser of Qualifier 1 v winner of the Eliminator"),
    ("Final", "2026-11-21", "16:30", "Winner of Qualifier 1 v winner of Qualifier 2"),
]


def npt(day, time):
    return datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=NPT)


class Command(BaseCommand):
    help = "Create or update the published NPL 2026 fixtures (28 league matches; playoffs on the season)."

    @transaction.atomic
    def handle(self, *args, **options):
        teams = {code: Team.objects.filter(slug=slug).first() for code, slug in T.items()}
        if missing := [T[c] for c, team in teams.items() if team is None]:
            raise CommandError(f"Missing teams {missing}. Run seed_npl_teams first.")
        now = timezone.now()
        season, _ = Season.objects.update_or_create(
            year=2026,
            defaults=dict(
                name="NPL 2026", starts_at="2026-10-26", ends_at="2026-11-21",
                source_metadata={
                    "source": SOURCE, "source_url": SOURCE_URL,
                    "published": "2026-09-19", "revised": "2026-10-20",
                    "note": "Evening start times revised on 20 Oct 2026 after DRS was added.",
                    "venue": VENUE,
                    "playoffs": [
                        {"stage": stage, "starts_at": npt(day, time).isoformat(), "description": desc, "venue": VENUE}
                        for stage, day, time, desc in PLAYOFFS
                    ],
                },
            ),
        )
        if season.status == Season.Status.COMPLETED:
            raise CommandError("NPL 2026 is marked completed; refusing to overwrite fixtures.")
        created = 0
        for number, day, time, home, away in LEAGUE:
            match = Match.objects.filter(season=season, match_number=number).first()
            fields = dict(home_team=teams[home], away_team=teams[away], starts_at=npt(day, time), venue=VENUE,
                          data_source=SOURCE, source_url=SOURCE_URL, last_synced_at=now)
            if match is None:
                Match.objects.create(season=season, match_number=number, **fields)
                created += 1
            elif match.status == Match.Status.SCHEDULED:  # never touch a match that has started
                for key, value in fields.items():
                    setattr(match, key, value)
                match.save()
        self.stdout.write(self.style.SUCCESS(
            f"NPL 2026: {len(LEAGUE)} league fixtures ready ({created} created), {len(PLAYOFFS)} playoff dates."
        ))
