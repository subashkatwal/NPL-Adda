import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import GuestSession, User
from apps.fanengagement.models import FanProfile, Vote

from .conftest import auth_client, guest_client

pytestmark = pytest.mark.django_db


def test_register_and_login_with_email(api):
    res = api.post("/api/v1/accounts/register", {"email": "New@Example.com", "password": "Str0ng-pass-123"},
                   format="json")
    assert res.status_code == 201 and res.data["email"] == "new@example.com"
    assert "access" not in res.data  # browser auth uses the HttpOnly session cookie, not tokens in JS
    assert api.get("/api/v1/accounts/me").status_code == 200  # session started by registration
    login = api.post("/api/v1/accounts/token", {"email": "new@example.com", "password": "Str0ng-pass-123"},
                     format="json")
    assert login.status_code == 200 and "access" in login.data  # JWT still available for API clients
    assert isinstance(User.objects.get(email="new@example.com").pk, uuid.UUID)


def test_soft_deleted_user_cannot_log_in(api, make_user):
    user = make_user(email="gone@example.com")
    user.soft_delete()
    res = api.post("/api/v1/accounts/token", {"email": "gone@example.com", "password": "Str0ng-pass-123"},
                   format="json")
    assert res.status_code == 401


def test_guest_session_stores_only_hash_and_returns(api):
    res = api.post("/api/v1/accounts/guest-sessions", {"metadata": {"locale": "ne"}}, format="json")
    assert res.status_code == 201
    raw = res.data["token"]
    session = GuestSession.objects.get(pk=res.data["id"])
    assert session.token_hash != raw and len(session.token_hash) == 64
    api.credentials(HTTP_X_GUEST_TOKEN=raw)
    assert api.get("/api/v1/accounts/guest-sessions/current").status_code == 200


def test_guest_metadata_rejects_unknown_keys(api):
    res = api.post("/api/v1/accounts/guest-sessions", {"metadata": {"password": "x"}}, format="json")
    assert res.status_code == 400


@pytest.mark.parametrize("state", ["expired", "revoked"])
def test_expired_or_revoked_guest_is_rejected(state):
    client, session, _ = guest_client()
    if state == "expired":
        session.expires_at = timezone.now() - timedelta(seconds=1)
        session.save()
    else:
        session.revoke()
    assert client.get("/api/v1/accounts/guest-sessions/current").status_code == 401


def test_guest_revoke_endpoint():
    client, session, _ = guest_client()
    assert client.post("/api/v1/accounts/guest-sessions/revoke").status_code == 204
    session.refresh_from_db()
    assert session.revoked_at is not None


def test_claim_transfers_guest_profile_to_new_account(make_user, make_team, make_profile):
    from apps.fanengagement.services import switch_team

    _, session, raw = guest_client()
    team = make_team()
    switch_team(make_profile(user=None, guest=session, nickname="Guesty"), team)  # legacy guest data
    user = make_user()
    res = auth_client(user).post("/api/v1/accounts/guest-sessions/claim", {"guest_token": raw}, format="json")
    assert res.status_code == 200 and res.data["nickname"] == "Guesty"
    profile = FanProfile.objects.get(user=user)
    assert profile.guest_session is None and profile.current_membership.team == team
    session.refresh_from_db()
    assert session.revoked_at and session.linked_user == user


def test_claim_merges_without_duplicating_votes(make_user, make_profile, make_team):
    from apps.fanengagement.models import Poll
    from apps.fanengagement.services import cast_vote

    staff = make_user(is_staff=True)
    now = timezone.now()
    poll = Poll.objects.create(question="Q?", created_by=staff, opens_at=now - timedelta(hours=1),
                               closes_at=now + timedelta(hours=1), status=Poll.Status.OPEN)
    opt = poll.options.create(text="A")
    user = make_user()
    user_profile = make_profile(user=user)
    _, session, raw = guest_client()
    guest_profile = make_profile(user=None, guest=session, nickname="G")
    cast_vote(user_profile, poll, opt)
    cast_vote(guest_profile, poll, opt)

    res = auth_client(user).post("/api/v1/accounts/guest-sessions/claim", {"guest_token": raw}, format="json")
    assert res.status_code == 200
    assert Vote.objects.filter(poll=poll, fan_profile=user_profile).count() == 1
    assert not FanProfile.objects.filter(pk=guest_profile.pk).exists()


def test_profile_owner_checks(make_profile):
    owner = make_profile(nickname="Owner")
    other = make_profile(nickname="Other")
    res = auth_client(other.user).patch(f"/api/v1/fanpage/{owner.pk}", {"nickname": "Hacked"}, format="json")
    assert res.status_code == 403
    res = auth_client(owner.user).patch(f"/api/v1/fanpage/{owner.pk}", {"nickname": "Renamed"}, format="json")
    assert res.status_code == 200 and res.data["nickname"] == "Renamed"
