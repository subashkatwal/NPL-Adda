"""Meme editor upgrades: mixed-script captions, fonts, sizes, collages, the funny style and instant publishing."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.content.models import CommunityPost
from apps.memelab import imaging
from apps.memelab.captioning import CaptionContext, MockCaptionProvider

from .conftest import auth_client

pytestmark = pytest.mark.django_db
M = "/api/v1/memelab"


def photo(color="#c8102e"):
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), color).save(buf, "PNG")
    return SimpleUploadedFile("p.png", buf.getvalue(), content_type="image/png")


def upload(client, color="#c8102e"):
    res = client.post(f"{M}/uploads", {"image": photo(color)}, format="multipart")
    assert res.status_code == 201, res.content
    return res.json()["id"]


def test_mixed_nepali_english_uses_a_latin_font_for_latin_runs():
    font = imaging._font_for("जब toss delay हुन्छ", 60)
    assert isinstance(font, imaging.MixedFont)
    runs = list(font.runs("जब toss हुन्छ?"))
    assert [k for k, _ in runs] == ["dev", "lat", "dev", "lat"]
    # Latin letters measured in the Latin font (the Devanagari font only has an empty box for them)
    assert font.getlength("toss") == font.fonts["lat"].getlength("toss")


def test_text_style_validates_new_options():
    style = imaging.clean_text_style({"font": "serif", "caps": False, "band": True, "top_size": 1.8, "collage": "grid"})
    assert style["font"] == "serif" and style["collage"] == "grid" and style["top_size"] == 1.8
    for bad in ({"font": "comic"}, {"collage": "nine"}, {"caps": "yes"}, {"bottom_size": 3}):
        with pytest.raises(ValueError):
            imaging.clean_text_style(bad)


@pytest.mark.parametrize("collage", ["side", "stack", "grid"])
def test_collage_preview_renders_with_own_photos(make_profile, collage):
    client = auth_client(make_profile().user)
    first, second = upload(client), upload(client, "#003893")
    res = client.post(f"{M}/render", {"upload": first, "extra_uploads": [second], "top_text": "When", "bottom_text": "Then",
                                      "text_style": {"collage": collage, "font": "display"}}, format="json")
    assert res.status_code == 200 and res["Content-Type"] == "image/jpeg"


def test_collage_rejects_someone_elses_photo(make_profile):
    mine, theirs = auth_client(make_profile().user), auth_client(make_profile().user)
    other = upload(theirs)
    res = mine.post(f"{M}/render", {"upload": upload(mine), "extra_uploads": [other], "top_text": "x",
                                    "text_style": {"collage": "side"}}, format="json")
    assert res.status_code == 400


def test_funny_style_is_accepted_and_tagged():
    result = MockCaptionProvider().generate(CaptionContext(topic="rain delay", language="en", style="funny"))
    assert len(result.options) == 3 and all("laughing" in o["bottom"] for o in result.options)


def test_memes_publish_without_review_by_default(make_profile, settings):
    assert settings.MEME_REQUIRE_REVIEW is False
    client = auth_client(make_profile().user)
    draft = client.post(f"{M}/drafts", {"template": None, "upload": upload(client), "top_text": "Toss delayed",
                                        "bottom_text": "Chai finished"}, format="json")
    assert draft.status_code == 201, draft.content
    post = client.post(f"{M}/drafts/{draft.json()['id']}/submit", {}, format="json")
    assert post.status_code in (200, 201), post.content
    assert CommunityPost.objects.get(pk=post.json()["id"]).status == "published"


def test_posts_publish_without_review_by_default(make_profile):
    client = auth_client(make_profile().user)
    res = client.post("/api/v1/content", {"title": "Hi", "body": "What a game", "submit_for_review": True}, format="json")
    assert res.status_code == 201 and res.json()["status"] == "published"


def test_review_can_still_be_switched_on(make_profile, settings):
    settings.POST_REQUIRE_REVIEW = True
    client = auth_client(make_profile().user)
    res = client.post("/api/v1/content", {"title": "Hi", "body": "Hold this one", "submit_for_review": True}, format="json")
    assert res.json()["status"] == "pending_review"
