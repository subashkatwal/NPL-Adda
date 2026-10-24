"""
Google Identity Services ID-token verification (google-auth library).

The frontend obtains a signed ID token ("credential") from Google's button; we verify
its signature, audience (our client ID), issuer and expiry here. No client secret is
involved in this flow, so none is stored anywhere.
"""
from django.conf import settings

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleAuthError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def verify_google_token(credential):
    """Return the verified token claims (sub, email, email_verified, name, picture) or raise GoogleAuthError."""
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleAuthError("google_not_configured", "Google sign-in is not configured on this server.", 503)
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(
            credential, google_requests.Request(), settings.GOOGLE_CLIENT_ID, clock_skew_in_seconds=10
        )
    except ValueError as exc:  # bad signature, wrong audience, expired, malformed
        raise GoogleAuthError("invalid_google_token", "Google sign-in could not be verified.") from exc
    if claims.get("iss") not in GOOGLE_ISSUERS or not claims.get("sub") or not claims.get("email"):
        raise GoogleAuthError("invalid_google_token", "Google sign-in could not be verified.")
    if not claims.get("email_verified"):
        raise GoogleAuthError("google_email_unverified", "Your Google email address is not verified.")
    return claims
