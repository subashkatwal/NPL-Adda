from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel, alive
from apps.content.models import CommunityPost
from apps.fanengagement.models import FanProfile


class ModerationReport(BaseModel):
    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        HARASSMENT = "harassment", "Harassment or hate"
        MISINFORMATION = "misinformation", "Misinformation"
        COPYRIGHT = "copyright", "Copyright"
        INAPPROPRIATE = "inappropriate", "Inappropriate content"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        UNDER_REVIEW = "under_review", "Under review"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    reporter = models.ForeignKey(
        FanProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports_filed", help_text="Reporting fan."
    )
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name="reports", help_text="Reported post.")
    comment = models.ForeignKey(
        "content.PostComment", null=True, blank=True, on_delete=models.CASCADE, related_name="reports",
        help_text="Reported comment on the post; empty when the post itself is reported.",
    )
    reason =models.CharField(max_length=20, choices=Reason.choices, help_text="Report category.")
    description = models.TextField(max_length=1000, blank=True, help_text="Optional details from the reporter.")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True, help_text="Review state."
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_reports",
        help_text="Moderator reviewing the report.",
    )
    resolution_note = models.TextField(blank=True, help_text="How the report was resolved.")
    resolved_at = models.DateTimeField(null=True, blank=True, help_text="When the report was resolved or dismissed.")

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["status", "created_at"], name="report_queue_idx")]  # moderator queue
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "post", "comment"],
                condition=alive(reporter__isnull=False, status__in=["open", "under_review"]),
                nulls_distinct=False,  # a post-level report (comment empty) is still one per reporter
                name="report_one_open_per_reporter_target",
            )
        ]

    def __str__(self):
        target = f"comment {self.comment_id}" if self.comment_id else self.post_id
        return f"{self.reason} on {target} ({self.status})"


class ModerationAction(BaseModel):
    """Immutable audit record of a moderation decision; protected from deletion."""

    class ActionType(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        HIDDEN = "hidden", "Hidden"
        REMOVED = "removed", "Removed"
        RESTORED = "restored", "Restored"

    post = models.ForeignKey(
        CommunityPost, on_delete=models.PROTECT, related_name="moderation_actions", help_text="Post acted on."
    )
    moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="moderation_actions",
        help_text="Authorised moderator who made the decision.",
    )
    action_type = models.CharField(max_length=20, choices=ActionType.choices, help_text="Decision taken.")
    reason = models.TextField(help_text="Required explanation of the decision.")
    previous_status = models.CharField(
        max_length=20, choices=CommunityPost.Status.choices, help_text="Post status before the action."
    )
    new_status = models.CharField(
        max_length=20, choices=CommunityPost.Status.choices, help_text="Post status after the action."
    )
    metadata = models.JSONField(default=dict, blank=True, help_text="Audit details, e.g. linked report or soft deletion.")

    class Meta(BaseModel.Meta):
        permissions = [("moderate_content", "Can moderate community content")]
        constraints = [models.CheckConstraint(condition=Q(reason__regex=r"\S"), name="action_reason_required")]

    def __str__(self):
        return f"{self.action_type} {self.post_id}"
