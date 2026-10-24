import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.common.models import AllObjectsManager, BaseModel, SoftDeleteQuerySet, alive


class UserManager(BaseUserManager.from_queryset(SoftDeleteQuerySet)):
    """Email-based user manager that hides soft-deleted accounts (they cannot log in)."""

    use_in_migrations = True

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not (extra_fields["is_staff"] and extra_fields["is_superuser"]):
            raise ValueError("Superusers must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """Registered NPL Adda account. Email is the login identifier."""

    email = models.EmailField(
        unique=True,
        help_text="Unique, lower-cased email address used to log in. Stays reserved after soft deletion.",
    )
    username = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        validators=[RegexValidator(r"^[A-Za-z0-9_]{3,30}$", "3-30 letters, digits or underscores.")],
        help_text="Optional unique public handle (3-30 letters, digits or underscores).",
    )
    display_name = models.CharField(
        max_length=60,
        blank=True,
        help_text="Name shown to other fans.",
    )
    password = models.CharField(
        max_length=128,
        help_text="Django-managed salted password hash; the raw password is never stored.",
    )
    last_login = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user last authenticated through Django's login flow.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the account may log in. Cleared when the account is soft-deleted.",
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Whether the user can access the Django admin and manage reference data.",
    )
    email_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the email address was verified; empty if unverified.",
    )
    date_joined = models.DateTimeField(
        default=timezone.now,
        help_text="When the account was registered.",
    )
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time the user was active in the API.",
    )
    avatar_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Profile picture link, e.g. copied from Google on first sign-in.",
    )

    objects = UserManager()
    all_objects = AllObjectsManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta(BaseModel.Meta):
        verbose_name = "user"

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        if self.username == "":
            self.username = None
        super().save(*args, **kwargs)

    def soft_delete(self):
        self.is_active = False
        self.save(update_fields=["is_active"])
        super().soft_delete()


class SocialAccount(BaseModel):
    """
    External sign-in identity linked to a User. Google accounts are keyed by the stable
    Google ``sub`` id, never by email, so a changed or recycled email cannot take over an account.
    """

    class Provider(models.TextChoices):
        GOOGLE = "google", "Google"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="social_accounts",
        help_text="Account this identity signs in to.",
    )
    provider = models.CharField(max_length=20, choices=Provider.choices, help_text="Identity provider.")
    uid = models.CharField(max_length=255, help_text="Provider's stable user id (Google 'sub').")
    email = models.EmailField(help_text="Email the provider reported at the last sign-in.")
    email_verified = models.BooleanField(default=False, help_text="Whether the provider verified that email.")
    extra_data = models.JSONField(
        default=dict, blank=True, help_text="Non-sensitive profile fields from the provider (name, picture)."
    )
    last_used_at = models.DateTimeField(null=True, blank=True, help_text="Last sign-in with this identity.")

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["provider", "uid"], condition=alive(), name="social_unique_provider_uid"),
            models.UniqueConstraint(fields=["user", "provider"], condition=alive(), name="social_one_per_provider"),
        ]

    def __str__(self):
        return f"{self.provider}:{self.email}"


class GuestSession(BaseModel):
    """
    Anonymous fan session. Only a SHA-256 hash of the random token is stored; the raw
    token is returned once at creation. A session is valid while not revoked, not
    soft-deleted and before ``expires_at`` (fixed lifetime of GUEST_SESSION_TTL_DAYS).
    Claiming it into an account revokes it.
    """

    token_hash = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="SHA-256 hex digest of the guest token; the raw token is never stored.",
    )
    linked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guest_sessions",
        help_text="Account this guest session was migrated into, if any.",
    )
    expires_at = models.DateTimeField(
        db_index=True,
        help_text="When the session stops being accepted.",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the session was revoked; empty while it is usable.",
    )
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this session authenticated a request.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Non-sensitive client details such as locale or app version.",
    )

    class Meta(BaseModel.Meta):
        pass

    def __str__(self):
        return f"Guest {self.pk}"

    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @classmethod
    def issue(cls, metadata=None):
        """Create a session; returns (session, raw_token). The raw token is not recoverable later."""
        raw = secrets.token_urlsafe(32)
        session = cls.objects.create(
            token_hash=cls.hash_token(raw),
            expires_at=timezone.now() + timedelta(days=settings.GUEST_SESSION_TTL_DAYS),
            metadata=metadata or {},
        )
        return session, raw

    @classmethod
    def authenticate(cls, raw_token):
        return cls.objects.filter(
            token_hash=cls.hash_token(raw_token), revoked_at__isnull=True, expires_at__gt=timezone.now()
        ).first()

    @property
    def is_valid(self):
        return self.revoked_at is None and self.deleted_at is None and self.expires_at > timezone.now()

    def revoke(self):
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at", "updated_at"])

    def touch(self):
        now = timezone.now()
        if self.last_seen_at is None or now - self.last_seen_at > timedelta(minutes=5):
            self.last_seen_at = now
            self.save(update_fields=["last_seen_at"])
