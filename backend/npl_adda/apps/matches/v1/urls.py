"""Mounted at /api/v1/matches: matches, /seasons, /innings and /performances."""
from django.urls import path

from apps.common.routing import resource_routes

from . import views

app_name = "matches"

urlpatterns = [
    *resource_routes(views.MatchViewSet, "", "match"),
    path("/<uuid:pk>/performances", views.MatchPerformanceListView.as_view(), name="match-performances"),
    *resource_routes(views.SeasonViewSet, "/seasons", "season"),
    *resource_routes(views.MatchInningsViewSet, "/innings", "innings"),
    *resource_routes(views.PerformanceViewSet, "/performances", "performance"),
]
