import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.fanengagement import card
from apps.fanengagement.models import FanActivity, FanProfile
from apps.fanengagement.rewards import Activity, record_activity

from .conftest import auth_client

pytestmark = pytest.mark.django_db


def image_file(fmt="PNG", size=(900, 600), name="me.png"):
    buf = io.BytesIO()
    Image.new("RGB", size, "#c8ff4d").save(buf, fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


@pytest.mark.parametrize("points, key, next_key", [
    (0, "rookie", "super_fan"), (49, "rookie", "super_fan"), (50, "super_fan", "die_hard"),
    (200, "die_hard", "legend"), (500, "legend", None), (-10, "rookie", "super_fan"),
])
def test_fan_levels_follow_points(points, key, next_key):
    level = card.fan_level(points)
    assert level["key"] == key
    assert (level["next"] or {}).get("key") == next_key
    assert 0 <= level["progress"] <= 1


def test_fan_code_is_stable_and_hides_the_id(make_profile):
    profile = make_profile()
    code = card.fan_code(profile)
    assert code == card.fan_code(profile) and code.startswith("NPL-") and len(code) == 13
    assert str(profile.pk)[:8].upper() not in code.replace("-", "")


def test_my_card_uses_ledger_points_and_never_leaks_private_data(make_profile, make_team):
    profile = make_profile()
    record_activity(profile, Activity.POLL_VOTE, idempotency_key="v1")
    record_activity(profile, Activity.ADJUSTMENT, points=60, idempotency_key="adj")
    data = auth_client(profile.user).get("/api/v1/fanpage/me/card").data
    assert data["level"]["key"] == "super_fan"
    assert data["stats"]["points"] == card.card_stats(profile)["points"] and data["stats"]["votes"] == 1
    assert data["is_owner"] and data["privacy"] == {"avatar": True, "stats": True, "badges": True, "since": True}
    flat = repr(data)
    assert profile.user.email not in flat and str(profile.user.pk) not in flat


def test_public_card_respects_privacy_switches(make_profile, make_user):
    owner = make_profile(card_show_stats=False, card_show_badges=False, card_show_since=False)
    data = auth_client(make_user()).get(f"/api/v1/fanpage/{owner.pk}/card").data
    assert data["stats"] is None and data["badges"] is None and data["member_since"] is None
    assert "privacy" not in data and "profile_id" not in data and not data["is_owner"]
    assert data["level"]["name"]  # level always shows


def test_private_card_is_hidden_except_from_owner(make_profile, api):
    owner = make_profile(is_public=False)
    assert api.get(f"/api/v1/fanpage/{owner.pk}/card").status_code == 404
    assert auth_client(owner.user).get(f"/api/v1/fanpage/{owner.pk}/card").status_code == 200


def test_customisation_is_validated_and_owner_only(make_profile):
    owner, other = make_profile(), make_profile()
    client = auth_client(owner.user)
    ok = client.patch(f"/api/v1/fanpage/{owner.pk}", {
        "tagline": "  Cricket   is life ", "card_theme": "stadium", "card_show_stats": False}, format="json")
    assert ok.status_code == 200 and ok.data["tagline"] == "Cricket is life" and ok.data["card_theme"] == "stadium"
    assert client.patch(f"/api/v1/fanpage/{owner.pk}", {"card_theme": "neon"}, format="json").status_code == 400
    assert client.patch(f"/api/v1/fanpage/{owner.pk}", {"tagline": "x" * 81}, format="json").status_code == 400
    assert client.patch(f"/api/v1/fanpage/{owner.pk}", {"tagline": "see www.spam.example"}, format="json").status_code == 400
    assert client.patch(f"/api/v1/fanpage/{owner.pk}", {"nickname": "muji"}, format="json").status_code == 400
    assert client.patch(f"/api/v1/fanpage/{other.pk}", {"tagline": "hijack"}, format="json").status_code == 403
    # avatar_url is no longer writable: external links can't be injected onto cards
    client.patch(f"/api/v1/fanpage/{owner.pk}", {"avatar_url": "https://evil.example/x.png"}, format="json")
    owner.refresh_from_db()
    assert owner.avatar_url == "" and client.get("/api/v1/fanpage/me").data["avatar_url"] == ""


def test_points_cannot_be_set_through_the_profile(make_profile):
    owner = make_profile()
    auth_client(owner.user).patch(f"/api/v1/fanpage/{owner.pk}", {"points": 9999, "level": "legend"}, format="json")
    assert card.card_stats(owner)["points"] == 0 and not FanActivity.objects.filter(fan_profile=owner).exists()


def test_avatar_upload_is_cropped_square_and_replaceable(make_profile):
    owner = make_profile()
    client = auth_client(owner.user)
    res = client.post("/api/v1/fanpage/me/avatar", {"image": image_file()}, format="multipart")
    assert res.status_code == 200 and res.data["avatar_url"].startswith("/media/avatars/")
    owner.refresh_from_db()
    first = owner.avatar.name
    with Image.open(owner.avatar.path) as img:
        assert img.size == (card.AVATAR_SIDE, card.AVATAR_SIDE) and img.format == "JPEG"
    client.post("/api/v1/fanpage/me/avatar", {"image": image_file("JPEG", name="b.jpg")}, format="multipart")
    owner.refresh_from_db()
    assert owner.avatar.name != first and not owner.avatar.storage.exists(first)  # old file removed
    assert client.delete("/api/v1/fanpage/me/avatar").data["avatar_url"] == ""


def test_avatar_rejects_non_images_and_hides_when_private(make_profile, make_user):
    owner = make_profile()
    client = auth_client(owner.user)
    bad = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
    assert client.post("/api/v1/fanpage/me/avatar", {"image": bad}, format="multipart").status_code == 400
    gif = image_file("GIF", name="a.gif")
    assert client.post("/api/v1/fanpage/me/avatar", {"image": gif}, format="multipart").status_code == 400
    client.post("/api/v1/fanpage/me/avatar", {"image": image_file()}, format="multipart")
    FanProfile.objects.filter(pk=owner.pk).update(card_show_avatar=False)
    assert auth_client(make_user()).get(f"/api/v1/fanpage/{owner.pk}/card").data["avatar_url"] == ""


def test_avatar_upload_requires_a_profile(make_user, api):
    assert api.post("/api/v1/fanpage/me/avatar", {"image": image_file()}, format="multipart").status_code in (401, 403)


def test_leaderboard_entries_carry_levels(make_profile, api):
    fan = make_profile()
    record_activity(fan, Activity.ADJUSTMENT, points=210, idempotency_key="big")
    row = next(r for r in api.get("/api/v1/fanpage/leaderboard").data["results"] if r["id"] == str(fan.pk))
    assert row["level"] == {"key": "die_hard", "name": "Die-hard"}
