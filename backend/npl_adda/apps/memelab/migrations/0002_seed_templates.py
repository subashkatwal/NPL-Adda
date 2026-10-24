"""Seed original MEME Zone templates. Layouts are drawn by the frontend; no third-party meme images."""
from django.db import migrations

TEMPLATES = [
    ("Scoreboard Shout", "scoreboard-shout", "top_bottom",
     {"background": "scoreboard", "text": "bottom", "accent": "team", "aspect": 1}),
    ("Then vs Now", "then-vs-now", "comparison",
     {"background": "split", "text": "split", "labels": ["Before the toss", "After the toss"], "aspect": 1}),
    ("Floodlight Roar", "floodlight-roar", "celebration",
     {"background": "floodlights", "text": "center", "accent": "lime", "aspect": 1}),
    ("Rain Delay Mood", "rain-delay-mood", "heartbreak",
     {"background": "rain", "text": "bottom", "accent": "muted", "aspect": 1}),
    ("Third Umpire", "third-umpire", "reaction",
     {"background": "review", "text": "top", "stamp": "DECISION PENDING", "aspect": 1}),
]


def seed(apps, schema_editor):
    MemeTemplate = apps.get_model("memelab", "MemeTemplate")
    for name, slug, category, layout in TEMPLATES:
        MemeTemplate.objects.get_or_create(slug=slug, defaults={"name": name, "category": category,
                                                                "layout_config": layout})


def unseed(apps, schema_editor):
    apps.get_model("memelab", "MemeTemplate").objects.filter(slug__in=[t[1] for t in TEMPLATES]).delete()


class Migration(migrations.Migration):
    dependencies = [("memelab", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
