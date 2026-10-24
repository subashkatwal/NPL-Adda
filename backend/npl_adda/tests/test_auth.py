from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.google import GoogleAuthError, verify_google_token
from apps.accounts.models import SocialAccount, User
from apps.matches.models import Match

from .conftest import auth_client, guest_client

pytestmark = pytest.mark.django_db

PASSWORD = "Str0ng-pass-123"
VERIFY = "apps.accounts.google.verify_google_token"


def claims(sub="g-123", email="fan@gmail.com", **extra):
    return {"iss": "https://accounts.google.com", "sub": sub, "email": email, "email_verified": True,
            "name": "Google Fan", "picture": "https://lh3.googleusercontent.com/a/pic", **extra}


def google_post(client, url="/api/v1/accounts/google", data=None):
    return client.post(url, {"credential": "header.payload.sig"}, format="json") if data is None else \
        client.post(url, data, format="json")


# --- Email/password + session ------------------------------------------------------------


def test_login_session_and_logout_invalidates(api, make_user):
    make_user(email="sess@example.com")
    res = api.post("/api/v1/accounts/login", {"email": "SESS@example.com", "password": PASSWORD}, format="json")
    assert res.status_code == 200 and res.data["email"] == "sess@example.com" and res.data["has_password"]
    assert "sessionid" in res.cookies and res.cookies["sessionid"]["httponly"]
    assert api.get("/api/v1/accounts/session").data["authenticated"] is True
    assert api.post("/api/v1/accounts/logout").status_code == 204
    assert api.get("/api/v1/accounts/me").status_code in (401, 403)
    assert api.get("/api/v1/accounts/session").data == {"authenticated": False, "user": None}


@pytest.mark.parametrize("email,password", [("nobody@example.com", PASSWORD), ("known@example.com", "wrong-pass")])
def test_invalid_credentials_same_error(api, make_user, email, password):
    make_user(email="known@example.com")
    res = api.post("/api/v1/accounts/login", {"email": email, "password": password}, format="json")
    assert res.status_code == 401 and res.data == {"code": "invalid_credentials", "detail": "Invalid email or password."}


def test_inactive_and_deleted_users_cannot_log_in(api, make_user):
    inactive = make_user(email="off@example.com", is_active=False)
    assert api.post("/api/v1/accounts/login", {"email": inactive.email, "password": PASSWORD}, format="json").status_code == 401
    gone = make_user(email="gone@example.com")
    gone.soft_delete()
    assert api.post("/api/v1/accounts/login", {"email": gone.email, "password": PASSWORD}, format="json").status_code == 401


def test_register_validation_and_duplicates(api, make_user):
    make_user(email="taken@example.com")
    dup = api.post("/api/v1/accounts/register", {"email": "Taken@Example.com", "password": PASSWORD}, format="json")
    assert dup.status_code == 400 and "email" in dup.data
    weak = api.post("/api/v1/accounts/register", {"email": "new@example.com", "password": "123"}, format="json")
    assert weak.status_code == 400
    bad = api.post("/api/v1/accounts/register", {"email": "not-an-email", "password": PASSWORD}, format="json")
    assert bad.status_code == 400


def test_csrf_enforced_for_browser_login():
    client = APIClient(enforce_csrf_checks=True)
    assert client.post("/api/v1/accounts/login", {"email": "a@b.co", "password": "x"}, format="json").status_code == 403
    client.get("/api/v1/accounts/session")  # sets csrftoken
    token = client.cookies["csrftoken"].value
    res = client.post("/api/v1/accounts/login", {"email": "a@b.co", "password": "x"}, format="json",
                      HTTP_X_CSRFTOKEN=token)
    assert res.status_code == 401  # past CSRF, rejected on credentials


def test_login_rate_limited(api, settings):
    from rest_framework.throttling import SimpleRateThrottle

    original = SimpleRateThrottle.THROTTLE_RATES
    SimpleRateThrottle.THROTTLE_RATES = {**original, "auth": "3/min"}
    try:
        codes = [api.post("/api/v1/accounts/login", {"email": "x@y.co", "password": "nope"}, format="json").status_code
                 for _ in range(4)]
        assert codes == [401, 401, 401, 429]
    finally:
        SimpleRateThrottle.THROTTLE_RATES = original


def test_expired_and_blacklisted_jwt(api, make_user):
    user = make_user()
    expired = AccessToken.for_user(user)
    expired.set_exp(lifetime=-timedelta(minutes=1))
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {expired}")
    assert api.get("/api/v1/accounts/me").status_code == 401

    refresh = RefreshToken.for_user(user)
    client = APIClient()
    assert client.post("/api/v1/accounts/token/blacklist", {"refresh": str(refresh)}, format="json").status_code == 200
    assert client.post("/api/v1/accounts/token/refresh", {"refresh": str(refresh)}, format="json").status_code == 401


# --- Google -----------------------------------------------------------------------------------


def test_google_not_configured(api, settings):
    settings.GOOGLE_CLIENT_ID = ""
    res = google_post(api)
    assert res.status_code == 503 and res.data["code"] == "google_not_configured"


def test_google_rejects_invalid_token(api, settings):
    settings.GOOGLE_CLIENT_ID = "test-client.apps.googleusercontent.com"
    with mock.patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("bad signature")):
        res = google_post(api)
    assert res.status_code == 400 and res.data["code"] == "invalid_google_token"


def test_google_verifier_checks_audience_issuer_and_email(settings):
    settings.GOOGLE_CLIENT_ID = "test-client.apps.googleusercontent.com"
    with mock.patch("google.oauth2.id_token.verify_oauth2_token", return_value=claims()) as verify:
        assert verify_google_token("tok")["sub"] == "g-123"
        assert verify.call_args.args[2] == "test-client.apps.googleusercontent.com"  # audience pinned
    with mock.patch("google.oauth2.id_token.verify_oauth2_token", return_value=claims(iss="https://evil.example")):
        with pytest.raises(GoogleAuthError):
            verify_google_token("tok")
    with mock.patch("google.oauth2.id_token.verify_oauth2_token", return_value=claims(email_verified=False)):
        with pytest.raises(GoogleAuthError) as exc:
            verify_google_token("tok")
        assert exc.value.code == "google_email_unverified"


def test_google_creates_then_reuses_account(api):
    with mock.patch(VERIFY, return_value=claims()):
        first = google_post(api)
        assert first.status_code == 201 and first.data["created"] is True
        assert first.data["has_password"] is False and first.data["providers"] == ["google"]
        assert api.get("/api/v1/accounts/me").status_code == 200
        api.post("/api/v1/accounts/logout")
        again = google_post(api)
    assert again.status_code == 200 and again.data["created"] is False
    assert User.objects.count() == 1 and SocialAccount.objects.count() == 1
    user = User.objects.get()
    assert user.email_verified_at and user.avatar_url.startswith("https://")


def test_google_matches_by_sub_not_email(api):
    with mock.patch(VERIFY, return_value=claims(sub="s1", email="old@gmail.com")):
        google_post(api)
    with mock.patch(VERIFY, return_value=claims(sub="s1", email="renamed@gmail.com")):
        res = google_post(api)
    assert res.status_code == 200 and User.objects.count() == 1


def test_google_refuses_to_take_over_unverified_password_account(api, make_user):
    make_user(email="fan@gmail.com")  # registered with a password, email never verified
    with mock.patch(VERIFY, return_value=claims()):
        res = google_post(api)
    assert res.status_code == 409 and res.data["code"] == "account_exists_unverified"
    assert SocialAccount.objects.count() == 0


def test_google_links_verified_account_automatically(api, make_user):
    user = make_user(email="fan@gmail.com", email_verified_at=timezone.now())
    with mock.patch(VERIFY, return_value=claims()):
        res = google_post(api)
    assert res.status_code == 200 and res.data["id"] == str(user.pk)


def test_google_cannot_sign_into_disabled_account(api, make_user):
    make_user(email="fan@gmail.com", email_verified_at=timezone.now(), is_active=False)
    with mock.patch(VERIFY, return_value=claims()):
        assert google_post(api).status_code == 403


def test_link_and_unlink_google_from_settings(make_user):
    user = make_user(email="me@example.com")
    client = auth_client(user)
    with mock.patch(VERIFY, return_value=claims(email="me@example.com")):
        linked = google_post(client, "/api/v1/accounts/google/link")
    assert linked.status_code == 200 and linked.data["providers"] == ["google"]
    user.refresh_from_db()
    assert user.email_verified_at is not None  # same email proven via Google
    other = auth_client(make_user())
    with mock.patch(VERIFY, return_value=claims(email="me@example.com")):
        assert google_post(other, "/api/v1/accounts/google/link").data["code"] == "google_already_linked"
    assert client.delete("/api/v1/accounts/google/link").data["providers"] == []


def test_google_only_user_cannot_unlink_or_use_password(api):
    with mock.patch(VERIFY, return_value=claims()):
        google_post(api)
    assert api.delete("/api/v1/accounts/google/link").data["code"] == "last_sign_in_method"
    res = APIClient().post("/api/v1/accounts/login", {"email": "fan@gmail.com", "password": "anything"}, format="json")
    assert res.status_code == 401 and res.data["code"] == "use_google"


# --- Guest browsing vs protected actions ------------------------------------------------------------


@pytest.mark.parametrize("url", ["/api/v1/teams", "/api/v1/matches", "/api/v1/content", "/api/v1/fanpage/leaderboard",
                                 "/api/v1/fanpage/leaderboard/teams", "/api/v1/fanpage/polls", "/api/v1/memelab/templates"])
def test_guests_can_browse_public_data(api, url):
    assert api.get(url).status_code == 200


def test_protected_actions_require_login(api, make_match, make_team):
    match = make_match()
    attempts = [
        ("post", "/api/v1/fanpage", {"nickname": "Anon"}),
        ("post", "/api/v1/fanpage/me/membership", {"team": str(make_team().pk)}),
        ("post", "/api/v1/fanpage/predictions", {"match": str(match.pk), "predicted_winner": str(match.home_team.pk)}),
        ("post", "/api/v1/content", {"body": "hello"}),
        ("post", "/api/v1/memelab/generations", {"topic": "a six"}),
        ("get", "/api/v1/fanpage/me", None),
    ]
    for method, url, body in attempts:
        res = getattr(api, method)(url, body, format="json") if body else getattr(api, method)(url)
        assert res.status_code == 401, (url, res.status_code)


def test_guest_token_cannot_act_as_fan(make_team):
    client, _, _ = guest_client()
    assert client.post("/api/v1/fanpage", {"nickname": "Guesty"}, format="json").status_code == 403
    assert client.get("/api/v1/teams").status_code == 200


def test_logged_in_user_without_profile_gets_403_for_fan_actions(make_user):
    client = auth_client(make_user())
    assert client.get("/api/v1/fanpage/me").status_code == 403
    assert client.post("/api/v1/fanpage", {"nickname": "New Fan"}, format="json").status_code == 201
    assert client.get("/api/v1/fanpage/me").status_code == 200


def test_staff_only_endpoints(make_user, make_match):
    match = make_match(status=Match.Status.COMPLETED)
    regular = auth_client(make_user())
    assert regular.post(f"/api/v1/fanpage/matches/{match.pk}/score-predictions").status_code == 403
    assert regular.post("/api/v1/teams", {}, format="json").status_code == 403
