from rest_framework.permissions import BasePermission

from apps.accounts.models import GuestSession

from .models import FanProfile

_UNSET = object()


def get_guest_session(request):
    auth = getattr(request, "auth", None)
    return auth if isinstance(auth, GuestSession) else None


def get_fan_profile(request):
    """
    The logged-in user's active FanProfile, cached per request.

    Guests (anonymous or guest-token) can browse but never act as a fan: voting,
    predicting, posting and joining a team all require a registered account.
    """
    cached = getattr(request, "_fan_profile", _UNSET)
    if cached is not _UNSET:
        return cached
    profile = None
    if request.user and request.user.is_authenticated:
        profile = FanProfile.objects.filter(user=request.user).first()
    request._fan_profile = profile
    return profile


class HasFanIdentity(BasePermission):
    """A logged-in account (needed to create a fan profile)."""

    message = "Log in to take part."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class HasFanProfile(BasePermission):
    """A logged-in account with a fan profile. Anonymous callers get 401 from DRF."""

    message = "Log in and create a fan profile first."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated) and get_fan_profile(request) is not None
