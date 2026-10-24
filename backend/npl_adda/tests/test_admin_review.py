"""One-click verify/approve actions and the nav badge counts in the admin console."""
import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.backoffice.models import SeenMarker
from apps.content.models import CommunityPost
from apps.moderation.models import ModerationAction, ModerationReport
from tests.conftest import auth_client

pytestmark = pytest.mark.django_db
A = "/api/v1/admin"


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("root@example.com", "Str0ng-pass-123")


def pending(make_profile, body="hi"):
    return CommunityPost.objects.create(author=make_profile(), body=body, status="pending_review")


def test_quick_actions_are_described_with_their_conditions(superuser):
    posts = next(r for r in auth_client(superuser).get(f"{A}/resources").json()["resources"] if r["key"] == "posts")
    verify = next(a for a in posts["actions"] if a["name"] == "verify")
    assert verify["quick"] and verify["when"] == {"status": ["pending_review"]} and posts["has_queue"]


def test_verify_publishes_and_is_audited(superuser, make_profile):
    post = pending(make_profile)
    res = auth_client(superuser).post(f"{A}/posts/{post.pk}/run/verify", {}, format="json")
    assert res.status_code == 200 and res.json()["status"] == "published"
    assert ModerationAction.objects.get(post=post).action_type == "approved"
    again = auth_client(superuser).post(f"{A}/posts/{post.pk}/run/verify", {}, format="json")
    assert again.status_code == 400  # no longer pending: the button doesn't apply


def test_verify_needs_moderator_and_reject_needs_reason(make_user, superuser, make_profile):
    post = pending(make_profile)
    staff = make_user(is_staff=True)
    assert auth_client(staff).post(f"{A}/posts/{post.pk}/run/verify", {}, format="json").status_code == 403
    client = auth_client(superuser)
    assert client.post(f"{A}/posts/{post.pk}/run/reject", {}, format="json").status_code == 400
    assert client.post(f"{A}/posts/{post.pk}/run/reject", {"reason": "spam"}, format="json").json()["status"] == "rejected"


def test_bulk_verify_skips_rows_already_handled(superuser, make_profile):
    a, b = pending(make_profile, "a"), pending(make_profile, "b")
    done = CommunityPost.objects.create(author=make_profile(), body="c", status="published", published_at=timezone.now())
    res = auth_client(superuser).post(f"{A}/posts/bulk-run/verify",
                                      {"ids": [str(a.pk), str(b.pk), str(done.pk)]}, format="json").json()
    assert res["done"] == 2 and len(res["skipped"]) == 1
    assert set(CommunityPost.objects.values_list("status", flat=True)) == {"published"}
    assert auth_client(superuser).post(f"{A}/posts/bulk-run/moderate", {"ids": []}, format="json").status_code == 404


def test_report_quick_resolve_and_user_email_verify(superuser, make_profile, make_user):
    report = ModerationReport.objects.create(post=pending(make_profile), reason="spam")
    res = auth_client(superuser).post(f"{A}/reports/{report.pk}/run/dismiss", {"reason": "fine"}, format="json").json()
    assert res["status"] == "dismissed" and res["resolved_at"] and res["resolution_note"] == "fine"
    user = make_user(email_verified_at=None)
    out = auth_client(superuser).post(f"{A}/users/{user.pk}/run/verify-email", {}, format="json").json()
    assert out["email_verified_at"]


def test_attention_counts_pending_and_new_since_seen(superuser, make_profile, make_user):
    client = auth_client(superuser)
    pending(make_profile)
    counts = client.get(f"{A}/attention").json()
    assert counts["posts"]["pending"] == 1 and counts["users"]["new"] >= 1
    assert client.post(f"{A}/attention", {"resource": "users"}, format="json").status_code == 204
    assert SeenMarker.objects.filter(user=superuser, resource="users").exists()
    assert client.get(f"{A}/attention").json()["users"]["new"] == 0
    make_user()  # a new sign-up after the visit
    assert client.get(f"{A}/attention").json()["users"]["new"] == 1
    assert client.post(f"{A}/attention", {"resource": "nope"}, format="json").status_code == 400


def test_attention_is_staff_only(make_user):
    assert auth_client(make_user()).get(f"{A}/attention").status_code == 403
