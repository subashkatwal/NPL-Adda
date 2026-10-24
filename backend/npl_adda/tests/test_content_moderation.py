import pytest

from apps.content.models import CommunityPost
from apps.memelab.models import MemeDraft
from apps.moderation.models import ModerationAction

from .conftest import auth_client

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def review_on(settings):
    """These tests cover the optional review queue (off by default: fans publish freely)."""
    settings.POST_REQUIRE_REVIEW = True
    settings.MEME_REQUIRE_REVIEW = True


@pytest.fixture
def author(make_profile):
    return make_profile(nickname="Author")


def create_post(client, **extra):
    return client.post("/api/v1/content", {"body": "What a chase at TU!", **extra}, format="json")


def test_author_cannot_self_publish_and_unpublished_hidden(api, author):
    client = auth_client(author.user)
    res = create_post(client, status="published")
    assert res.status_code == 201 and res.data["status"] == "draft"
    assert api.get("/api/v1/content").data["count"] == 0
    assert api.get(f"/api/v1/content/{res.data['id']}").status_code == 404
    assert client.get(f"/api/v1/content/{res.data['id']}").status_code == 200
    assert client.get("/api/v1/content/mine").data["count"] == 1


def test_only_owner_edits(author, make_profile):
    post_id = create_post(auth_client(author.user)).data["id"]
    other = auth_client(make_profile().user)
    assert other.patch(f"/api/v1/content/{post_id}", {"body": "x"}, format="json").status_code == 404
    edited = auth_client(author.user).patch(f"/api/v1/content/{post_id}", {"body": "Edited", "submit_for_review": True},
                                            format="json")
    assert edited.status_code == 200 and edited.data["status"] == "pending_review"


def test_moderation_flow_is_audited(api, author, moderator, make_profile):
    post_id = create_post(auth_client(author.user), submit_for_review=True).data["id"]
    payload = {"post": post_id, "action_type": "approved", "reason": "Fine"}
    assert auth_client(author.user).post("/api/v1/moderation/actions", payload, format="json").status_code == 403

    mod = auth_client(moderator)
    assert mod.post("/api/v1/moderation/actions", {**payload, "reason": "  "}, format="json").status_code == 400
    res = mod.post("/api/v1/moderation/actions", payload, format="json")
    assert res.status_code == 201 and res.data["previous_status"] == "pending_review"
    assert api.get("/api/v1/content").data["count"] == 1
    assert author.activities.filter(activity_type="post_published").count() == 1

    reporter = auth_client(make_profile().user)
    report = reporter.post("/api/v1/moderation/reports", {"post": post_id, "reason": "spam"}, format="json")
    assert report.status_code == 201
    assert reporter.post("/api/v1/moderation/reports", {"post": post_id, "reason": "spam"}, format="json").status_code == 409
    assert reporter.get("/api/v1/moderation/reports").status_code == 403

    removed = mod.post("/api/v1/moderation/actions", {"post": post_id, "action_type": "removed", "reason": "Spam",
                                                      "report": report.data["id"]}, format="json")
    assert removed.status_code == 201
    assert api.get("/api/v1/content").data["count"] == 0
    assert CommunityPost.all_objects.get(pk=post_id).deleted_at is not None
    assert mod.get(f"/api/v1/moderation/reports/{report.data['id']}").data["status"] == "resolved"
    assert ModerationAction.objects.filter(post_id=post_id).count() == 2


def test_moderator_cannot_approve_own_post(moderator, make_profile):
    own = make_profile(user=moderator)
    post_id = create_post(auth_client(moderator), submit_for_review=True).data["id"]
    assert own.posts.count() == 1
    res = auth_client(moderator).post("/api/v1/moderation/actions",
                                      {"post": post_id, "action_type": "approved", "reason": "mine"}, format="json")
    assert res.status_code == 403


def test_content_vote_one_per_fan(author, moderator, make_profile):
    post_id = create_post(auth_client(author.user), submit_for_review=True).data["id"]
    auth_client(moderator).post("/api/v1/moderation/actions",
                                {"post": post_id, "action_type": "approved", "reason": "ok"}, format="json")
    voter = auth_client(make_profile().user)
    assert voter.post(f"/api/v1/content/{post_id}/vote", {"vote_type": "up"}, format="json").status_code == 201
    assert voter.post(f"/api/v1/content/{post_id}/vote", {"vote_type": "down"}, format="json").status_code == 200
    detail = voter.get(f"/api/v1/content/{post_id}").data
    assert detail["score"] == -1


def test_meme_draft_submit_and_moderation_sync(author, moderator):
    client = auth_client(author.user)
    draft = client.post("/api/v1/memelab/drafts", {"caption": "Rhinos charging"}, format="json")
    assert draft.status_code == 201
    submitted = client.post(f"/api/v1/memelab/drafts/{draft.data['id']}/submit")
    assert submitted.status_code == 201 and submitted.data["status"] == "pending_review"
    assert client.patch(f"/api/v1/memelab/drafts/{draft.data['id']}", {"caption": "x"}, format="json").status_code == 400
    auth_client(moderator).post("/api/v1/moderation/actions",
                                {"post": submitted.data["id"], "action_type": "rejected", "reason": "Off-topic"},
                                format="json")
    assert MemeDraft.objects.get(pk=draft.data["id"]).status == "rejected"


def test_agent_runs_are_staff_only(api, make_user):
    assert api.get("/api/v1/ai-agents/runs").status_code == 401
    assert auth_client(make_user(is_staff=True)).get("/api/v1/ai-agents/runs").status_code == 200
