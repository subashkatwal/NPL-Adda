"""Mounted at /api/v1/moderation."""
from django.urls import path

from apps.common.routing import resource_routes

from . import views

app_name = "moderation"

urlpatterns = [
    *resource_routes(views.ReportViewSet, "/reports", "report"),
    path("/actions", views.ActionListCreateView.as_view(), name="actions"),
]
