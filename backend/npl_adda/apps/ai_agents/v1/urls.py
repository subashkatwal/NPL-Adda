"""Mounted at /api/v1/ai-agents. Read-only audit of runs; execution lives in the external AI service."""
from django.urls import path

from apps.common.routing import resource_routes

from . import views

app_name = "ai_agents"

urlpatterns = [
    *resource_routes(views.AgentRunViewSet, "/runs", "run"),
    path("/runs/<uuid:pk>/tool-calls", views.AgentToolCallListView.as_view(), name="run-tool-calls"),
]
