from datetime import timedelta

import pytest
from django.utils import timezone

from apps.content.models import CommunityPost
from apps.fanengagement.models import FanActivity, Poll
from apps.fanengagement.rewards import record_activity
from apps.memelab.models import MemeDraft, MemeGenerationRequest, MemeTemplate
from apps.matches.models import Match, Season

from .conftest import auth_client

pytestmark = pytest.mark.django_db


# --- Fan engagement -------------------------------------------------------------------


def test_team_leaderboard_is_server_computed(make_profile, make_team):
    a, b = make_team(), make_team()
    for team, fans in ((a, 2), (b, 1)):
        for _ in range(fans):
            p = make_profile()
            auth_client(p.user).post("/api/v1/fanpage/me/membership", {"team": str(team.pk)}, format="json")
    rows = auth_client(make_profile().user).get("/api/v1/fanpage/leaderboard/teams").data
    top = rows[0]
    assert top["team"]["id"] == str(a.pk) and top["points"] == 20 and top["members"] == 2 and top["rank"] == 1
    assert rows[1]["team"]["id"] == str(b.pk) and rows[1]["rank"] == 2


def test_switching_keeps_points_with_original_team(make_profile, make_team):
    a, b = make_team(), make_team()
    profile = make_profile()
    client = auth_client(profile.user)
    client.post("/api/v1/fanpage/me/membership", {"team": str(a.pk)}, format="json")
    client.post("/api/v1/fanpage/me/membership", {"team": str(b.pk)}, format="json")
    rows = {r["team"]["id"]: r for r in client.get("/api/v1/fanpage/leaderboard/teams").data}
    assert rows[str(a.pk)]["points"] == 10 and rows[str(a.pk)]["members"] == 0
    assert rows[str(b.pk)]["points"] == 10 and rows[str(b.pk)]["members"] == 1


def test_individual_leaderboard_rank_and_season_filter(make_profile, make_team):
    season = Season.objects.create(name="NPL 2030", year=2030, status=Season.Status.ACTIVE)
    old, new = make_profile(nickname="Old"), make_profile(nickname="New")
    record_activity(old, FanActivity.ActivityType.ADJUSTMENT, points=50, evaluate=False)
    FanActivity.objects.filter(fan_profile=old).update(occurred_at=timezone.now().replace(year=2029))
    record_activity(new, FanActivity.ActivityType.ADJUSTMENT, points=5, evaluate=False)
    FanActivity.objects.filter(fan_profile=new).update(occurred_at=timezone.now().replace(year=2030))

    all_time = auth_client(new.user).get("/api/v1/fanpage/leaderboard").data["results"]
    assert [r["nickname"] for r in all_time[:2]] == ["Old", "New"] and all_time[0]["rank"] == 1
    seasonal = auth_client(new.user).get(f"/api/v1/fanpage/leaderboard?season={season.pk}").data["results"]
    assert seasonal[0]["nickname"] == "New" and seasonal[0]["points"] == 5


def test_season_summary(make_profile, make_match, season):
    profile = make_profile()
    client = auth_client(profile.user)
    match = make_match()
    client.post("/api/v1/fanpage/predictions", {"match": str(match.pk), "predicted_winner": str(match.home_team.pk)},
                format="json")
    data = client.get(f"/api/v1/fanpage/me/season-summary?season={season.pk}").data
    assert data["season"]["year"] == 2025 or data["season"]["id"] == str(season.pk)
    assert data["predictions_made"] == 1 and data["predictions_pending"] == 1


def test_challenges_show_progress_and_completion(make_profile, make_team):
    profile = make_profile()
    client = auth_client(profile.user)
    client.post("/api/v1/fanpage/me/membership", {"team": str(make_team().pk)}, format="json")
    rows = {r["badge"]["rule_key"]: r for r in client.get("/api/v1/fanpage/me/challenges").data}
    assert rows["team_member"]["completed"] and rows["team_member"]["current"] == 1
    assert rows["prediction_ace"] == {**rows["prediction_ace"], "current": 0, "target": 5, "completed": False}


def test_poll_card_fields_hide_results_until_allowed(make_profile, make_user):
    now = timezone.now()
    poll = Poll.objects.create(question="Best finisher?", created_by=make_user(is_staff=True), status=Poll.Status.OPEN,
                               opens_at=now - timedelta(hours=1), closes_at=now + timedelta(hours=1),
                               results_visibility=Poll.ResultsVisibility.AFTER_VOTE)
    option = poll.options.create(text="A")
    poll.options.create(text="B")
    client = auth_client(make_profile().user)
    before = client.get(f"/api/v1/fanpage/polls/{poll.pk}").data
    assert before["my_vote"] is None and before["results"] is None
    client.post(f"/api/v1/fanpage/polls/{poll.pk}/vote", {"option": str(option.pk)}, format="json")
    after = client.get(f"/api/v1/fanpage/polls/{poll.pk}").data
    assert after["my_vote"] == option.pk and after["results"]["total_votes"] == 1


def test_prediction_split_hidden_until_deadline(api, make_profile, make_match):
    match = make_match()
    client = auth_client(make_profile().user)
    client.post("/api/v1/fanpage/predictions", {"match": str(match.pk), "predicted_winner": str(match.home_team.pk)},
                format="json")
    assert api.get(f"/api/v1/fanpage/matches/{match.pk}/prediction-summary").status_code == 403
    Match.objects.filter(pk=match.pk).update(starts_at=timezone.now() - timedelta(minutes=5))
    data = api.get(f"/api/v1/fanpage/matches/{match.pk}/prediction-summary").data
    assert data["total"] == 1 and data["split"][0]["count"] == 1


def test_reward_idempotent_under_repeat(make_profile):
    profile = make_profile()
    for _ in range(3):
        record_activity(profile, FanActivity.ActivityType.POLL_VOTE, idempotency_key="vote:same")
    assert profile.activities.filter(idempotency_key="vote:same").count() == 1


# --- Content states --------------------------------------------------------------------


def test_removed_state_and_team_feed(api, make_profile, moderator, make_team):
    team = make_team()
    author = make_profile()
    client = auth_client(author.user)
    post_id = client.post("/api/v1/content", {"body": "Team feed post", "team": str(team.pk), "submit_for_review": True},
                          format="json").data["id"]
    mod = auth_client(moderator)
    mod.post("/api/v1/moderation/actions", {"post": post_id, "action_type": "approved", "reason": "ok"}, format="json")
    assert api.get(f"/api/v1/content?team={team.pk}").data["count"] == 1
    assert api.get(f"/api/v1/content?team={make_team().pk}").data["count"] == 0
    mod.post("/api/v1/moderation/actions", {"post": post_id, "action_type": "removed", "reason": "spam"}, format="json")
    assert CommunityPost.all_objects.get(pk=post_id).status == "removed"
    assert api.get(f"/api/v1/content?team={team.pk}").data["count"] == 0
    restored = mod.post("/api/v1/moderation/actions", {"post": post_id, "action_type": "restored", "reason": "appeal"},
                        format="json")
    assert restored.data["new_status"] == "published"


def test_author_cannot_set_ai_flag(make_profile):
    res = auth_client(make_profile().user).post("/api/v1/content", {"body": "x" * 5, "is_ai_generated": True},
                                                format="json")
    assert res.status_code == 201 and res.data["is_ai_generated"] is False


# --- MEME Zone ----------------------------------------------------------------------------


def generate(client, key="k1", **body):
    payload = {"topic": "a last-ball six", "language": "en", "style": "hype", **body}
    return client.post("/api/v1/memelab/generations", payload, format="json", HTTP_IDEMPOTENCY_KEY=key)


def test_templates_are_seeded(api):
    slugs = {t["slug"] for t in api.get("/api/v1/memelab/templates").data["results"]}
    assert {"scoreboard-shout", "then-vs-now", "floodlight-roar"} <= slugs


@pytest.mark.parametrize("language,marker", [("en", "fans"), ("ne", "फ्यान"), ("mixed", "jaba")])
def test_generation_languages_alternatives_and_mock_label(make_profile, make_team, language, marker):
    team = make_team(name="Chitwan Rhinos")
    client = auth_client(make_profile().user)
    res = generate(client, language=language, team=str(team.pk), topic="the powerplay collapse")
    assert res.status_code == 201
    assert res.data["is_mock"] is True and "not an AI model" in res.data["notice"]
    assert res.data["request"]["provider"] == "mock" and res.data["request"]["status"] == "completed"
    assert len(res.data["captions"]) == 3 and len(set(res.data["captions"])) == 3
    assert res.data["draft"]["alternate_captions"] == res.data["options"][1:]  # top/bottom pairs
    assert res.data["draft"]["source_references"] == [{"type": "teams.team", "id": str(team.pk)}]
    if language != "ne":
        assert any("Chitwan Rhinos" in c for c in res.data["captions"])


def test_generation_is_deterministic_and_idempotent(make_profile):
    client = auth_client(make_profile().user)
    first = generate(client, key="same")
    replay = generate(client, key="same")
    assert first.status_code == 201 and replay.status_code == 200
    assert replay.data["request"]["id"] == first.data["request"]["id"]
    assert MemeGenerationRequest.objects.count() == 1 and MemeDraft.objects.count() == 1
    again = generate(client, key="other")
    assert again.data["captions"] == first.data["captions"]


def test_generation_uses_match_context(make_profile, make_match):
    match = make_match(venue="Mulpani")
    res = generate(auth_client(make_profile().user), team=str(match.home_team.pk), match=str(match.pk))
    assert "Mulpani" in res.data["captions"][0]
    assert res.data["draft"]["source_references"][1]["type"] == "matches.match"


def test_generation_validation_and_errors(make_profile, make_match, make_team, settings):
    client = auth_client(make_profile().user)
    assert generate(client, topic="x").status_code == 400
    assert client.post("/api/v1/memelab/generations", {"topic": "valid topic"}, format="json").status_code == 400
    match = make_match()
    assert generate(client, key="m", team=str(make_team().pk), match=str(match.pk)).status_code == 400
    settings.MEME_CAPTION_PROVIDER = "external"
    res = generate(client, key="ext")
    assert res.status_code == 503 and res.data["code"] == "provider_not_configured"
    assert MemeGenerationRequest.objects.get(idempotency_key="ext").status == "failed"


def test_generation_rate_limited(make_profile, settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"meme_generation": "2/hour"}}
    from rest_framework.throttling import SimpleRateThrottle

    SimpleRateThrottle.THROTTLE_RATES = {"meme_generation": "2/hour"}
    try:
        client = auth_client(make_profile().user)
        assert generate(client, key="r1").status_code == 201
        assert generate(client, key="r2", topic="another topic").status_code == 201
        limited = generate(client, key="r3", topic="third topic")
        assert limited.status_code == 429 and "Retry-After" in limited.headers
    finally:
        from rest_framework.settings import api_settings

        SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES


def test_fan_can_generate_edit_and_submit_with_duplicate_check(make_team, make_user, moderator, settings):
    settings.MEME_REQUIRE_REVIEW = True  # covers the optional review queue
    client = auth_client(make_user())
    client.post("/api/v1/fanpage", {"nickname": "Maker"}, format="json")
    template = MemeTemplate.objects.get(slug="scoreboard-shout")
    draft_id = generate(client, team=str(make_team().pk)).data["draft"]["id"]
    edited = client.patch(f"/api/v1/memelab/drafts/{draft_id}", {"caption": "Edited caption for review",
                                                                  "template": str(template.pk)}, format="json")
    assert edited.status_code == 200
    post = client.post(f"/api/v1/memelab/drafts/{draft_id}/submit")
    assert post.status_code == 201 and post.data["status"] == "pending_review"
    assert post.data["is_ai_generated"] is False  # mock output is not AI content
    assert post.data["meme"]["template"]["slug"] == "scoreboard-shout"

    other = auth_client(make_user())
    other.post("/api/v1/fanpage", {"nickname": "Copycat"}, format="json")
    copy = other.post("/api/v1/memelab/drafts", {"caption": "Edited caption for review!"}, format="json")
    dup = other.post(f"/api/v1/memelab/drafts/{copy.data['id']}/submit")
    assert dup.status_code == 409 and dup.data["code"] == "duplicate_content"
