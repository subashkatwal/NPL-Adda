from datetime import timedelta
from itertools import count

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import GuestSession, User
from apps.fanengagement.models import FanProfile
from apps.matches.models import Match, Season
from apps.teams.models import Player, Team

_seq = count(1)


@pytest.fixture(autouse=True)
def isolated_cache(settings):
    """Per-test in-memory cache so throttle counters never leak between tests or into Redis."""
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                                   "LOCATION": f"test-{next(_seq)}"}}


@pytest.fixture(autouse=True)
def offline_captions(settings):
    """Tests never call a real AI service, whatever the developer's .env says."""
    settings.MEME_CAPTION_PROVIDER = "mock"
    settings.GEMINI_API_KEY = ""


@pytest.fixture(autouse=True)
def isolated_media(settings, tmp_path):
    """Uploaded and rendered images go to a temporary folder, not the real media directory."""
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def api():
    return APIClient()


def auth_client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def guest_client():
    session, raw = GuestSession.issue()
    client = APIClient()
    client.credentials(HTTP_X_GUEST_TOKEN=raw)
    return client, session, raw


@pytest.fixture
def make_user(db):
    def make(**kwargs):
        n = next(_seq)
        kwargs.setdefault("email", f"fan{n}@example.com")
        return User.objects.create_user(password="Str0ng-pass-123", **kwargs)

    return make


@pytest.fixture
def moderator(make_user):
    user = make_user(is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="moderate_content"))
    return User.objects.get(pk=user.pk)  # reload to clear the permission cache


@pytest.fixture
def make_team(db):
    def make(**kwargs):
        n = next(_seq)
        defaults = dict(name=f"Team {n}", slug=f"team-{n}", short_name=f"T{n}", city="Kathmandu",
                        primary_color="#112233", secondary_color="#AABBCC")
        return Team.objects.create(**{**defaults, **kwargs})

    return make


@pytest.fixture
def make_player(db):
    def make(**kwargs):
        n = next(_seq)
        defaults = dict(full_name=f"Player {n}", slug=f"player-{n}", nationality="Nepal", role=Player.Role.BATTER)
        return Player.objects.create(**{**defaults, **kwargs})

    return make


@pytest.fixture
def season(db):
    return Season.objects.create(name="NPL 2025", year=2025, status=Season.Status.ACTIVE)


@pytest.fixture
def make_match(season, make_team):
    def make(home=None, away=None, **kwargs):
        defaults = dict(season=season, home_team=home or make_team(), away_team=away or make_team(),
                        venue="TU Ground", starts_at=timezone.now() + timedelta(days=1))
        return Match.objects.create(**{**defaults, **kwargs})

    return make


@pytest.fixture
def make_profile(make_user):
    def make(user=None, guest=None, **kwargs):
        if user is None and guest is None:
            user = make_user()
        return FanProfile.objects.create(user=user, guest_session=guest, nickname=kwargs.pop("nickname", "Fan"), **kwargs)

    return make
