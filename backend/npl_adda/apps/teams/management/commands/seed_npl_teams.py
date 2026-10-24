"""
Seed the eight NPL franchises (names and home regions only).

Brand colours are neutral placeholders chosen for this app, not official team colours,
and no logos are referenced. Verify the list against the target season before production
use and replace colours/artwork with authorised values through the admin.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.teams.models import Team

PLACEHOLDER_NOTE = "Colours are app placeholders, not official branding. No official logo is used."

TEAMS = [
    # name, slug, short name, region, primary, secondary
    ("Biratnagar Kings", "biratnagar-kings", "BRK", "Biratnagar", "#3A4A7A", "#E3C565"),
    ("Chitwan Rhinos", "chitwan-rhinos", "CHR", "Chitwan", "#2F5D50", "#F2A541"),
    ("Janakpur Bolts", "janakpur-bolts", "JKB", "Janakpur", "#6B3FA0", "#F5D547"),
    ("Karnali Yaks", "karnali-yaks", "KAY", "Karnali", "#7A3B2E", "#9FD8CB"),
    ("Kathmandu Gurkhas", "kathmandu-gurkhas", "KTG", "Kathmandu", "#8C1C2B", "#F0E6D2"),
    ("Lumbini Lions", "lumbini-lions", "LUL", "Lumbini", "#B5651D", "#1F2A44"),
    ("Pokhara Avengers", "pokhara-avengers", "POA", "Pokhara", "#1D5C8C", "#E8EEF2"),
    ("Sudurpaschim Royals", "sudurpaschim-royals", "SPR", "Sudurpaschim", "#4B2E5C", "#D9B44A"),
]


class Command(BaseCommand):
    help = "Create or update the eight NPL team records (idempotent; colours are placeholders)."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for order, (name, slug, short, city, primary, secondary) in enumerate(TEAMS, start=1):
            _, was_created = Team.objects.update_or_create(
                slug=slug,
                defaults=dict(name=name, short_name=short, city=city, primary_color=primary,
                              secondary_color=secondary, display_order=order, description=PLACEHOLDER_NOTE),
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"Teams ready: {len(TEAMS)} ({created} created)."))
