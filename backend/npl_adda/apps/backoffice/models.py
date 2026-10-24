from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class SeenMarker(BaseModel):
    """When a staff member last opened an admin section; drives the console's "new since" badges."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="admin_seen",
                             help_text="Staff member.")
    resource = models.CharField(max_length=50, help_text="Admin resource key, e.g. 'users'.")
    seen_at = models.DateTimeField(default=timezone.now, help_text="When the section was last opened.")

    class Meta(BaseModel.Meta):
        constraints = [models.UniqueConstraint(fields=["user", "resource"], name="seenmarker_unique_user_resource")]

    def __str__(self):
        return f"{self.user} saw {self.resource} at {self.seen_at:%Y-%m-%d %H:%M}"
