import uuid

from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)


class ActiveManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Default manager: hides soft-deleted rows."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Includes soft-deleted rows; use for audits, admin and restores."""


class BaseModel(models.Model):
    """
    Abstract base for project-owned models: UUID primary key, timestamps and soft deletion.

    ``soft_delete()`` only stamps ``deleted_at``; it never cascades, so related rows stay
    intact and database integrity is untouched. ``delete()`` keeps Django's physical
    deletion (with its on_delete rules) and is reserved for explicitly authorised
    operations such as superuser admin actions. Foreign-key traversal uses Django's
    plain base manager, so history pointing at a soft-deleted row still resolves.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this record, generated automatically.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Date and time when this record was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Date and time when this record was last updated.",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        editable=False,
        help_text="When this record was soft-deleted; empty while the record is active.",
    )

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True
        ordering = ("-created_at",)

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        if self.deleted_at is None:
            self.deleted_at = timezone.now()
            self.save(update_fields=["deleted_at", "updated_at"])

    def restore(self):
        """Reactivate the row. May raise IntegrityError if an active duplicate now exists."""
        if self.deleted_at is not None:
            self.deleted_at = None
            self.save(update_fields=["deleted_at", "updated_at"])


def alive(**filters):
    """Condition for unique constraints that should ignore soft-deleted rows."""
    return models.Q(deleted_at__isnull=True, **filters)
