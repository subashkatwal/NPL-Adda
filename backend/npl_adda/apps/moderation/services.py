from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.common.permissions import is_moderator
from apps.content.models import CommunityPost
from apps.fanengagement.rewards import Activity, record_activity
from apps.memelab.models import MemeDraft

from .models import ModerationAction, ModerationReport

Status = CommunityPost.Status
Action = ModerationAction.ActionType

# action -> statuses it may be applied from
ALLOWED_FROM = {
    Action.APPROVED: {Status.PENDING_REVIEW, Status.APPROVED, Status.REJECTED, Status.HIDDEN},
    Action.REJECTED: {Status.PENDING_REVIEW, Status.APPROVED},
    Action.HIDDEN: {Status.PUBLISHED, Status.APPROVED},
    Action.REMOVED: set(Status.values),
    Action.RESTORED: {Status.HIDDEN, Status.REJECTED, Status.REMOVED},
}

DRAFT_STATUS_FOR_POST = {
    Status.PUBLISHED: MemeDraft.Status.PUBLISHED,
    Status.REJECTED: MemeDraft.Status.REJECTED,
    Status.HIDDEN: MemeDraft.Status.REJECTED,
    Status.REMOVED: MemeDraft.Status.REJECTED,
    Status.PENDING_REVIEW: MemeDraft.Status.PENDING_REVIEW,
}


@transaction.atomic
def apply_action(post, moderator, action_type, reason, report=None):
    """Apply a moderation decision and write its audit record. The only path to privileged post states."""
    if not is_moderator(moderator):
        raise PermissionDenied("Moderator permission required.")
    post = CommunityPost.all_objects.select_for_update().select_related("author").get(pk=post.pk)
    if post.author.user_id == moderator.pk:
        raise PermissionDenied("Moderators cannot act on their own content.")
    if not (reason or "").strip():
        raise ValidationError({"reason": "A reason is required."})

    previous = post.status
    removed_already = post.deleted_at is not None
    if action_type == Action.RESTORED:
        if not (removed_already or previous in ALLOWED_FROM[action_type]):
            raise ValidationError({"action_type": f"Cannot restore a post that is '{previous}'."})
    elif removed_already:
        raise ValidationError({"action_type": "Post has been removed; restore it first."})
    elif previous not in ALLOWED_FROM[action_type]:
        raise ValidationError({"action_type": f"Cannot apply '{action_type}' to a post that is '{previous}'."})

    metadata = {}
    if action_type == Action.APPROVED:
        post.publish()
    elif action_type == Action.REJECTED:
        post.status = Status.REJECTED
    elif action_type == Action.HIDDEN:
        post.status = Status.HIDDEN
    elif action_type == Action.REMOVED:
        post.status = Status.REMOVED
        post.deleted_at = timezone.now()
        metadata["soft_deleted"] = True
    elif action_type == Action.RESTORED:
        post.deleted_at = None
        if post.published_at:
            post.publish()
        else:
            post.status = Status.PENDING_REVIEW
        metadata["restored_from_removal"] = removed_already
    post.save(update_fields=["status", "published_at", "deleted_at", "updated_at"])

    if report is not None:
        metadata["report_id"] = str(report.pk)
        report.status = ModerationReport.Status.RESOLVED
        report.resolution_note = reason
        report.resolved_at = timezone.now()
        report.assigned_to = report.assigned_to or moderator
        report.save(update_fields=["status", "resolution_note", "resolved_at", "assigned_to", "updated_at"])

    action = ModerationAction.objects.create(
        post=post, moderator=moderator, action_type=action_type, reason=reason,
        previous_status=previous, new_status=post.status, metadata=metadata,
    )
    if post.status == Status.PUBLISHED:
        record_activity(post.author, Activity.POST_PUBLISHED, reference=post, idempotency_key=f"post_published:{post.pk}")
    if draft_status := DRAFT_STATUS_FOR_POST.get(post.status):
        MemeDraft.objects.filter(published_post=post).update(status=draft_status, updated_at=timezone.now())
    return action
