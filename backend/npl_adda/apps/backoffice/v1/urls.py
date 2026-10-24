"""
Mounted at /api/v1/admin (staff only): ``/resources``, ``/dashboard`` and, per resource,
``/<key>``, ``/<key>/<uuid>``, ``/<key>/<uuid>/restore`` and ``/<key>/<uuid>/run/<action>``.
"""
from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views
from .base import REGISTRY

app_name = "backoffice"

router = SimpleRouter(trailing_slash="")
for viewset in REGISTRY:
    router.register(f"/{viewset.resource}", viewset, basename=f"admin-{viewset.resource}")

urlpatterns = [
    path("/resources", views.ResourceIndexView.as_view(), name="resources"),
    path("/dashboard", views.DashboardView.as_view(), name="dashboard"),
    path("/attention", views.AttentionView.as_view(), name="attention"),
    *router.urls,
]
