from django.contrib.auth.models import AnonymousUser
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import GuestSession

GUEST_HEADER = "X-Guest-Token"


class GuestSessionAuthentication(BaseAuthentication):
    """
    Authenticates anonymous fans by the ``X-Guest-Token`` header.

    ``request.user`` stays anonymous; ``request.auth`` is the GuestSession.
    """

    def authenticate(self, request):
        raw = request.headers.get(GUEST_HEADER)
        if not raw:
            return None
        session = GuestSession.authenticate(raw)
        if session is None:
            raise AuthenticationFailed("Invalid, expired or revoked guest session.")
        session.touch()
        return AnonymousUser(), session

    def authenticate_header(self, request):
        return "GuestToken"


class GuestSessionScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.GuestSessionAuthentication"
    name = "guestToken"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": GUEST_HEADER}
