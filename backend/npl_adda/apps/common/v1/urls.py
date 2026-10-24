"""
Shared v1 routes, mounted at the v1 root in api/v1/urls.py.

Unlike feature modules this one is mounted at "", so its routes have no leading slash.
"""
from django.urls import path

from .views import HealthView

app_name = "common"

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
]
