"""Meme Zone: uploads, Pillow rendering, feed, reactions, comments, contests, rankings and the caption pipeline."""
import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from PIL import Image

from apps.accounts.models import User
from apps.content.models import CommunityPost, ContentVote, PostComment
from apps.fanengagement.models import FanActivity, FanProfile
from apps.matches.models import Match
from apps.memelab import imaging, pipeline
from apps.memelab.captioning import CaptionContext, GeminiCaptionProvider
from apps.memelab.models import ContestEntry, ContestVote, MemeContest, MemeDraft, MemeTemplate
from apps.moderation.models import ModerationReport
from tests.conftest import auth_client

M = "/api/v1/memelab"
pytestmark = pytest.mark.django_db


def png_bytes(size=(64, 48), color="#C8FF4D", fmt="PNG"):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, fmt)
    return out.getvalue()


@pytest.fixture
def fan(make_user):
    """(client, profile) for a logged-in fan with a profile; accounts are a week old (not flagged as new)."""
    def make(nickname="Fan"):
        user = make_user()
        User.objects.filter(pk=user.pk).update(date_joined=timezone.now() - timedelta(days=7))
        profile = FanProfile.objects.create(user=user, nickname=nickname)
        return auth_client(User.objects.get(pk=user.pk)), profile
    return make


def meme(author, team=None, match=None, published_at=None, body=None):
    return CommunityPost.objects.create(
        author=author, team=team, match=match, content_type=CommunityPost.ContentType.MEME,
        body=body or f"meme {timezone.now().timestamp()}", status=CommunityPost.Status.PUBLISHED,
        published_at=published_at or timezone.now(), media_url="/media/memes/x.jpg",
    )


# ---------------------------------------------------------------- uploads & rendering

def test_upload_is_validated_and_reencoded(fan, api, settings):
    client, profile = fan()
    assert api.post(f"{M}/uploads", {"image": SimpleUploadedFile("a.png", png_bytes())}).status_code == 401
    res = client.post(f"{M}/uploads", {"image": SimpleUploadedFile("a.png", png_bytes(), "image/png")})
    assert res.status_code == 201, res.data
    assert res.data["image_url"].endswith(".jpg") and (res.data["width"], res.data["height"]) == (64, 48)
    fake = SimpleUploadedFile("evil.png", b"<?php echo 1; ?>", "image/png")
    assert "isn't a readable image" in str(client.post(f"{M}/uploads", {"image": fake}).data["image"])
    gif = SimpleUploadedFile("a.gif", png_bytes(fmt="GIF"), "image/gif")
    assert "JPEG, PNG or WebP" in str(client.post(f"{M}/uploads", {"image": gif}).data["image"])
    settings.MEME_UPLOAD_MAX_BYTES = 100
    big = SimpleUploadedFile("big.png", png_bytes((400, 400)), "image/png")
    assert client.post(f"{M}/uploads", {"image": big}).status_code == 400


def test_render_preview_and_upload_ownership(fan):
    client, _ = fan()
    other, _ = fan("Other")
    upload_id = client.post(f"{M}/uploads", {"image": SimpleUploadedFile("a.png", png_bytes())}).data["id"]
    res = client.post(f"{M}/render", {"top_text": "When the rain stops", "bottom_text": "and starts again",
                                      "upload": upload_id}, format="json")
    assert res.status_code == 200 and res["Content-Type"] == "image/jpeg"
    assert Image.open(io.BytesIO(res.content)).size == (720, 720)
    assert other.post(f"{M}/render", {"upload": upload_id}, format="json").status_code == 400


@pytest.mark.parametrize("accept", ["image/jpeg, application/json;q=0.9", "image/*", "*/*"])
def test_image_endpoints_honour_browser_accept_headers(fan, accept):
    client, _ = fan()
    res = client.post(f"{M}/render", {"bottom_text": "Accept me"}, format="json", HTTP_ACCEPT=accept)
    assert res.status_code == 200 and res["Content-Type"] == "image/jpeg"
    bad = client.post(f"{M}/render", {"text_style": {"color": "red"}}, format="json", HTTP_ACCEPT=accept)
    assert bad.status_code == 400 and bad["Content-Type"].startswith("application/json")
    assert b"color" in bad.content
    draft = client.post(f"{M}/drafts", {"bottom_text": "Download me"}, format="json")
    image = client.get(f"{M}/drafts/{draft.data['id']}/image", HTTP_ACCEPT=accept)
    assert image.status_code == 200 and image["Content-Type"] == "image/jpeg"


def test_nepali_text_renders_with_shaping():
    status = imaging.rendering_status()
    assert status["devanagari_font"] and status["complex_script_shaping"]
    img = imaging.render_meme(imaging.MemeSpec(top_text="बिरालोले बाटो काट्यो", bottom_text="अब के हुन्छ?"))
    assert img.size == (imaging.SIZE, imaging.SIZE)


def test_text_style_validation():
    assert imaging.clean_text_style({"color": "#ff7043", "size": 1.2})["color"] == "#FF7043"
    for bad in ({"color": "red"}, {"size": 3}, {"top_y": "x"}, {"oops": 1}, []):
        with pytest.raises(ValueError):
            imaging.clean_text_style(bad)


def test_editor_draft_submit_renders_image(fan, settings):
    settings.MEME_REQUIRE_REVIEW = True  # covers the optional review queue
    client, profile = fan()
    template = MemeTemplate.objects.get(slug="floodlight-roar")
    body = {"template": str(template.pk), "top_text": "Me at 4:59 pm", "bottom_text": "Floodlights on, worries off",
            "text_style": {"color": "#C8FF4D"}, "language": "en"}
    draft = client.post(f"{M}/drafts", body, format="json")
    assert draft.status_code == 201, draft.data
    assert draft.data["caption"] == "Me at 4:59 pm / Floodlights on, worries off"
    assert client.post(f"{M}/drafts", {**body, "text_style": {"color": "lime"}}, format="json").status_code == 400
    assert client.post(f"{M}/drafts", {**body, "top_text": "you muji"}, format="json").status_code == 400
    image = client.get(f"{M}/drafts/{draft.data['id']}/image")
    assert image.status_code == 200 and image["Content-Disposition"].startswith("attachment")
    post = client.post(f"{M}/drafts/{draft.data['id']}/submit")
    assert post.status_code == 201 and post.data["status"] == "pending_review"
    assert post.data["media_url"].startswith("/media/memes/rendered/")
    assert MemeDraft.objects.get(pk=draft.data["id"]).rendered_image
    # with review switched off the meme is live at once (still reportable)
    settings.MEME_REQUIRE_REVIEW = False
    second = client.post(f"{M}/drafts", {**body, "top_text": "Second meme", "bottom_text": "Different words"},
                         format="json")
    assert client.post(f"{M}/drafts/{second.data['id']}/submit").data["status"] == "published"


# ---------------------------------------------------------------- feed, reactions, comments

def test_feed_lists_only_published_memes_with_counts(fan, api, django_assert_max_num_queries):
    client, me = fan("Me")
    _, author = fan("Author")
    live = meme(author)
    CommunityPost.objects.create(author=author, content_type="meme", body="pending", status="pending_review")
    CommunityPost.objects.create(author=author, content_type="fan_post", body="text", status="published",
                                 published_at=timezone.now())
    for _ in range(5):
        meme(author)
    ContentVote.objects.create(post=live, fan_profile=me, vote_type="up")
    with django_assert_max_num_queries(6):
        res = client.get(f"{M}/memes?sort=top")
    assert res.data["count"] == 6
    top = res.data["results"][0]
    assert top["id"] == str(live.pk) and top["engagement"] == 2 and top["my_vote"] == "up"
    assert api.get(f"{M}/memes?sort=new").status_code == 200
    assert api.get(f"{M}/memes?team=not-a-uuid").status_code == 400


def test_reactions_toggle_and_cannot_self_react(fan):
    client, me = fan()
    _, author = fan("Author")
    post = meme(author)
    url = f"{M}/memes/{post.pk}/react"
    assert client.post(url, {"kind": "fire"}, format="json").data["my_reaction"] == "fire"
    data = client.post(url, {"kind": "laugh"}, format="json").data
    assert data["my_reaction"] == "laugh" and data["counts"]["reactions"] == 1 and data["counts"]["by_reaction"]["laugh"] == 1
    data = client.post(url, {"kind": "laugh"}, format="json").data
    assert data["my_reaction"] is None and data["counts"]["reactions"] == 0
    own = meme(me)
    assert client.post(f"{M}/memes/{own.pk}/react", {"kind": "fire"}, format="json").status_code == 400


def test_comments_replies_hiding_and_reports(fan, api, moderator):
    client, me = fan()
    other, _ = fan("Other")
    post = meme(me)
    url = f"{M}/memes/{post.pk}/comments"
    assert api.post(url, {"body": "hi"}, format="json").status_code == 401
    top = client.post(url, {"body": "Kya meme!"}, format="json").data
    reply = other.post(url, {"body": "Haha", "parent": top["id"]}, format="json").data
    nested = client.post(url, {"body": "Reply to reply", "parent": reply["id"]}, format="json").data
    assert str(nested["parent"]) == str(top["id"])  # one level of threads
    assert client.post(url, {"body": "Kya meme!"}, format="json").status_code == 409  # duplicate burst
    assert client.post(url, {"body": "see https://spam.example"}, format="json").status_code == 400
    listing = api.get(url).data
    assert listing["count"] == 1 and len(listing["results"][0]["replies"]) == 2
    assert other.post(f"{M}/comments/{top['id']}/report", {"reason": "spam"}, format="json").status_code == 201
    assert other.post(f"{M}/comments/{top['id']}/report", {"reason": "spam"}, format="json").status_code == 409
    assert ModerationReport.objects.filter(comment_id=top["id"]).count() == 1
    assert other.post(f"{M}/comments/{top['id']}/hide", {"reason": "x"}, format="json").status_code == 403
    mod = auth_client(moderator)
    assert mod.post(f"{M}/comments/{top['id']}/hide", {"reason": "Spam"}, format="json").data["body"] is None
    assert other.delete(f"{M}/comments/{top['id']}").status_code == 403
    assert client.delete(f"{M}/comments/{top['id']}").status_code == 204
    assert not PostComment.objects.filter(pk=top["id"]).exists()


# ---------------------------------------------------------------- contests

@pytest.fixture
def contest(make_match):
    match = make_match()
    now = timezone.now()
    return MemeContest.objects.create(
        title="Meme of the Match", match=match, status=MemeContest.Status.PUBLISHED,
        submissions_open_at=now - timedelta(hours=1), submissions_close_at=now + timedelta(hours=5),
        voting_open_at=now - timedelta(hours=1), voting_close_at=now + timedelta(hours=10),
    )


def test_contest_entry_rules(fan, contest, make_team):
    client, me = fan()
    other_team = make_team()
    eligible = meme(me, team=contest.match.home_team)
    off_topic = meme(me, team=other_team)
    url = f"{M}/contests/{contest.pk}/enter"
    assert client.post(url, {"post": str(off_topic.pk)}, format="json").status_code == 400
    assert client.post(url, {"post": str(eligible.pk)}, format="json").status_code == 201
    second = meme(me, match=contest.match)
    assert client.post(url, {"post": str(second.pk)}, format="json").status_code == 409  # max 1 per fan
    stranger, _ = fan("Stranger")
    assert stranger.post(url, {"post": str(second.pk)}, format="json").status_code == 403
    contest.submissions_close_at = timezone.now() - timedelta(minutes=1)
    contest.save()
    assert stranger.post(url, {"post": str(meme(_, team=contest.match.home_team).pk)}, format="json").status_code == 400


def test_contest_voting_flags_and_finalize(fan, contest, make_user):
    a_client, a = fan("A")
    b_client, b = fan("B")
    c_client, c = fan("C")
    entry_a = ContestEntry.objects.create(contest=contest, post=meme(a, team=contest.match.home_team), fan_profile=a)
    entry_b = ContestEntry.objects.create(contest=contest, post=meme(b, team=contest.match.away_team), fan_profile=b)
    vote_url = f"{M}/contests/{contest.pk}/vote"
    assert a_client.post(vote_url, {"entry": str(entry_a.pk)}, format="json").status_code == 400  # own entry
    assert a_client.post(vote_url, {"entry": str(entry_b.pk)}, format="json").status_code == 201
    assert c_client.post(vote_url, {"entry": str(entry_a.pk)}, format="json").status_code == 201
    assert c_client.post(vote_url, {"entry": str(entry_b.pk)}, format="json").data["changed"] is True
    assert ContestVote.objects.filter(contest=contest).count() == 2  # one per fan, moved not duplicated
    newbie = make_user()
    FanProfile.objects.create(user=newbie, nickname="New")
    auth_client(newbie).post(vote_url, {"entry": str(entry_a.pk)}, format="json")
    assert "account under 24h old" in ContestVote.objects.get(fan_profile__user=newbie).flag_reason
    detail = c_client.get(f"{M}/contests/{contest.pk}").data
    assert detail["phase"] == "open" and detail["entries"][0]["id"] == str(entry_b.pk)
    assert detail["entries"][0]["votes"] == 2 and detail["my_vote"] == str(entry_b.pk)
    from apps.memelab import services
    with pytest.raises(Exception):
        services.finalize_contest(contest)  # voting still open
    contest.voting_close_at = timezone.now() - timedelta(seconds=1)
    contest.voting_open_at = contest.submissions_open_at
    contest.save()
    assert c_client.post(vote_url, {"entry": str(entry_a.pk)}, format="json").status_code == 400  # closed
    services.finalize_contest(contest)
    contest.refresh_from_db()
    assert contest.winner == entry_b and contest.phase(timezone.now()) == "finalized"
    assert FanActivity.objects.filter(fan_profile=b, activity_type="meme_contest_win", points_delta=25).count() == 1


def test_contest_ties_go_to_earlier_entry(fan, contest):
    from apps.memelab import services
    _, a = fan("A")
    _, b = fan("B")
    voter_1, _ = fan("V1")
    voter_2, _ = fan("V2")
    first = ContestEntry.objects.create(contest=contest, post=meme(a, team=contest.match.home_team), fan_profile=a)
    second = ContestEntry.objects.create(contest=contest, post=meme(b, team=contest.match.home_team), fan_profile=b)
    voter_1.post(f"{M}/contests/{contest.pk}/vote", {"entry": str(second.pk)}, format="json")
    voter_2.post(f"{M}/contests/{contest.pk}/vote", {"entry": str(first.pk)}, format="json")
    MemeContest.objects.filter(pk=contest.pk).update(voting_close_at=timezone.now() - timedelta(seconds=1),
                                                     voting_open_at=contest.submissions_open_at)
    services.finalize_contest(contest)
    assert MemeContest.objects.get(pk=contest.pk).winner == first


def test_match_contest_command_skips_samples_and_is_idempotent(make_match, season):
    call_command("seed_npl_teams")
    call_command("seed_npl_2026_fixtures")
    call_command("create_match_meme_contests")
    call_command("create_match_meme_contests")
    contests = MemeContest.objects.all()
    assert contests.count() == 28 and set(contests.values_list("status", flat=True)) == {"draft"}
    first = contests.order_by("submissions_open_at").first()
    assert first.voting_close_at - first.match.starts_at == timedelta(hours=48)


# ---------------------------------------------------------------- rankings

def test_hall_of_fame_scoring_and_periods(fan, api, make_team):
    _, a = fan("A")
    _, b = fan("B")
    voters = [fan(f"V{i}")[1] for i in range(3)]
    team = make_team()
    best = meme(a, team=team)
    for voter in voters:
        ContentVote.objects.create(post=best, fan_profile=voter, vote_type="up")
    old = meme(b, team=team, published_at=timezone.now() - timedelta(days=40))
    for voter in voters:
        ContentVote.objects.create(post=old, fan_profile=voter, vote_type="up")
    week = api.get(f"{M}/hall-of-fame?period=week").data
    assert [m["id"] for m in week["top_memes"]] == [str(best.pk)]
    assert week["top_creators"][0]["nickname"] == "A" and week["top_creators"][0]["score"] == 6
    assert "2 x upvotes" in week["scoring"]
    everything = api.get(f"{M}/hall-of-fame?period=all").data
    assert len(everything["top_memes"]) == 2
    wars = api.get(f"{M}/team-wars?period=all").data
    row = next(t for t in wars["teams"] if t["team_id"] == str(team.pk))
    assert row["memes"] == 2 and row["score"] == 12 and row["rank"] == 1
    assert api.get(f"{M}/hall-of-fame?period=decade").status_code == 400


# ---------------------------------------------------------------- caption pipeline

class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def gemini_reply(captions):
    import json
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": json.dumps({"captions": captions})}]}}],
                              "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20}})


def test_gemini_provider_parses_and_falls_back_between_models(settings):
    session = FakeSession(FakeResponse(404, {}), gemini_reply([{"top": "Rain", "bottom": "Again"}]))
    provider = GeminiCaptionProvider(api_key="k", model="retired-model", fallback_model="backup", session=session)
    result = provider.generate(CaptionContext(topic="rain", language="ne_rom", style="fan_pain"))
    assert result.options == [{"top": "Rain", "bottom": "Again"}] and result.model_name == "backup"
    url, kwargs = session.calls[0]
    assert "retired-model" in url and kwargs["headers"]["x-goog-api-key"] == "k"
    assert "Romanized Nepali" in kwargs["json"]["contents"][0]["parts"][0]["text"]


def test_pipeline_falls_back_to_templates_when_ai_is_down(make_team):
    provider = GeminiCaptionProvider(api_key="k", fallback_model="backup-a,backup-b",
                                     session=FakeSession(*[FakeResponse(503, {}) for _ in range(3)]))
    result, _ = pipeline.run(topic="rain delay", language="en", style="reaction", team=make_team(), provider=provider)
    assert result.is_mock and result.options and "AI captions unavailable" in result.notices[0]


def test_pipeline_drops_unverified_facts_and_offensive_captions(make_match, make_team):
    match = make_match(status=Match.Status.SCHEDULED)
    other = make_team(name="Far Away XI")
    captions = [
        {"top": f"{other.name} fans", "bottom": "crying"},  # names a team outside this match
        {"top": "Ref was a", "bottom": "bastard"},  # blocked word
        {"top": "Toss time", "bottom": "Heart rate: also T20"},
    ]
    provider = GeminiCaptionProvider(api_key="k", session=FakeSession(gemini_reply(captions)))
    result, refs = pipeline.run(topic="toss", language="en", style="rivalry", match=match, provider=provider)
    assert result.verified and refs[-1]["type"] == "matches.match"
    assert result.options == [{"top": "Toss time", "bottom": "Heart rate: also T20"}]
    assert result.dropped == {"unsupported_facts": 1, "moderation": 1}
    kept, dropped = pipeline.validate_facts([{"top": "Won by 45 runs", "bottom": ""}], {"date": "2026-10-26"}, "", set())
    assert kept == [] and dropped == 1  # numbers must come from verified facts or the fan's own topic


def test_sample_matches_are_never_treated_as_verified(make_match):
    match = make_match(data_source="development-sample")
    _, match_ctx, facts, verified, _ = pipeline.retrieve_facts(None, match)
    assert not verified and match_ctx is None and "fixture" not in facts


def test_caption_status_reports_provider(api, settings):
    assert api.get(f"{M}/caption-status").data["provider"] == "mock"
    settings.MEME_CAPTION_PROVIDER, settings.GEMINI_API_KEY = "auto", "key"
    data = api.get(f"{M}/caption-status").data
    assert data["provider"] == "gemini" and data["ai"] is True
