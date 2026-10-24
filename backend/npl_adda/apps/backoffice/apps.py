from django.apps import AppConfig


class BackofficeConfig(AppConfig):
    """Staff admin console API (/api/v1/admin). Manages every other app's data; owns only SeenMarker."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backoffice"
    label = "backoffice"
