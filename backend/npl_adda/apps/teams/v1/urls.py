"""Mounted at /api/v1/teams: teams, /players and /rosters."""
from django.urls import path

from apps.common.routing import resource_routes

from . import views

app_name = "teams"

urlpatterns = [
    *resource_routes(views.TeamViewSet, "", "team"),
    path("/<uuid:pk>/roster", views.TeamRosterListView.as_view(), name="team-roster"),
    *resource_routes(views.PlayerViewSet, "/players", "player"),
    *resource_routes(views.TeamRosterViewSet, "/rosters", "roster"),
]
