"""
Central registry of v1 feature routes.

Prefixes carry no trailing slash. Each feature's ``v1/urls.py`` routes its
collection as ``""`` and every sub-path with a leading slash, e.g. ``"/<uuid:pk>"``,
so the final URLs are ``/api/v1/teams`` and ``/api/v1/teams/<uuid>``.
"""
from django.urls import include, path

urlpatterns = [
    path("", include("apps.common.v1.urls")),
    path("accounts", include("apps.accounts.v1.urls")),
    path("teams", include("apps.teams.v1.urls")),
    path("matches", include("apps.matches.v1.urls")),
    path("fanpage", include("apps.fanengagement.v1.urls")),
    path("content", include("apps.content.v1.urls")),
    path("memelab", include("apps.memelab.v1.urls")),
    path("ai-agents", include("apps.ai_agents.v1.urls")),
    path("moderation", include("apps.moderation.v1.urls")),
    path("admin", include("apps.backoffice.v1.urls")),
]
