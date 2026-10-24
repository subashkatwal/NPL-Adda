"""Mounted at /api/v1/accounts."""
from django.urls import path
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from . import views

app_name = "accounts"

TokenObtain = extend_schema_view(post=extend_schema(tags=["accounts"]))(TokenObtainPairView)
TokenRefresh = extend_schema_view(post=extend_schema(tags=["accounts"]))(TokenRefreshView)
TokenBlacklist = extend_schema_view(post=extend_schema(tags=["accounts"]))(TokenBlacklistView)

urlpatterns = [
    # Browser (session cookie + CSRF)
    path("/session", views.SessionView.as_view(), name="session"),
    path("/register", views.RegisterView.as_view(), name="register"),
    path("/login", views.LoginView.as_view(), name="login"),
    path("/logout", views.LogoutView.as_view(), name="logout"),
    path("/google", views.GoogleLoginView.as_view(), name="google"),
    path("/google/link", views.GoogleLinkView.as_view(), name="google-link"),
    path("/me", views.MeView.as_view(), name="me"),
    # API clients (JWT); /token/blacklist invalidates a refresh token on logout
    path("/token", TokenObtain.as_view(), name="token"),
    path("/token/refresh", TokenRefresh.as_view(), name="token-refresh"),
    path("/token/blacklist", TokenBlacklist.as_view(), name="token-blacklist"),
    # Legacy guest sessions: browse-only; kept so earlier guest data can be claimed into an account
    path("/guest-sessions", views.GuestSessionCreateView.as_view(), name="guest-session-create"),
    path("/guest-sessions/current", views.CurrentGuestSessionView.as_view(), name="guest-session-current"),
    path("/guest-sessions/revoke", views.RevokeGuestSessionView.as_view(), name="guest-session-revoke"),
    path("/guest-sessions/claim", views.ClaimGuestSessionView.as_view(), name="guest-session-claim"),
]
