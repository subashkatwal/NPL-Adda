from django.db import migrations

BADGES = [
    ("team-member", "Team Member", "Joined a team for the first time.", "shield", "team_member"),
    ("first-vote", "Voice of the Crowd", "Voted in a fan poll.", "ballot", "first_vote"),
    ("first-prediction", "Fortune Teller", "Made a first match prediction.", "crystal-ball", "first_prediction"),
    ("prediction-ace", "Prediction Ace", "Got five match predictions right.", "target", "prediction_ace"),
    ("first-post", "Storyteller", "Had a first post published.", "quill", "first_post"),
]


def seed(apps, schema_editor):
    Badge = apps.get_model("fanengagement", "Badge")
    for code, name, description, icon, rule in BADGES:
        Badge.objects.get_or_create(
            code=code, defaults={"name": name, "description": description, "icon_name": icon, "rule_key": rule}
        )


def unseed(apps, schema_editor):
    apps.get_model("fanengagement", "Badge").objects.filter(code__in=[b[0] for b in BADGES]).delete()


class Migration(migrations.Migration):
    dependencies = [("fanengagement", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
