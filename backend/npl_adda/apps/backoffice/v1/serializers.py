from django.apps import apps
from django.contrib.auth import password_validation
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.common.permissions import MODERATE_PERMISSION
from apps.content.models import CommunityPost
from apps.fanengagement.models import Badge, FanActivity, FanProfile, Poll, PollOption
from apps.moderation.models import ModerationAction, ModerationReport
from apps.teams.models import Team

from .base import BASE_READ_ONLY, AdminSerializer, admin_serializer, resource_for_model

PRIVILEGE_FIELDS = ("is_staff", "is_superuser", "is_moderator")


def moderate_permission():
    app_label, codename = MODERATE_PERMISSION.split(".")
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


class AdminUserSerializer(AdminSerializer):
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, style={"input_type": "password"},
        help_text="Set a new password. Leave blank to keep the current one (or none, for Google-only accounts).",
    )
    is_moderator = serializers.BooleanField(
        required=False, help_text="Can review and act on community posts and reports. Superusers always can.",
    )
    has_password = serializers.SerializerMethodField(help_text="False for Google-only accounts.")
    providers = serializers.SerializerMethodField(help_text="Linked external sign-in providers.")

    class Meta:
        model = User
        fields = ("id", "email", "username", "display_name", "avatar_url", "password", "is_active", "is_staff",
                  "is_superuser", "is_moderator", "email_verified_at", "has_password", "providers", "date_joined",
                  "last_login", "last_seen_at", "created_at", "updated_at", "deleted_at")
        read_only_fields = BASE_READ_ONLY + ("date_joined", "last_login", "last_seen_at")
        validators = []
        extra_kwargs = {"email": {"validators": []}}

    def get_has_password(self, obj):
        return obj.has_usable_password()

    def get_providers(self, obj):
        return sorted({s.provider for s in obj.social_accounts.all() if s.deleted_at is None})

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["is_moderator"] = instance.is_superuser or any(
            p.codename == "moderate_content" for p in instance.user_permissions.all()
        ) or any(p.codename == "moderate_content" for g in instance.groups.all() for p in g.permissions.all())
        return data

    def validate_email(self, value):
        value = value.strip().lower()
        others = User.all_objects.filter(email__iexact=value)
        if self.instance:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError("Another account already uses this email.")
        return value

    def validate_username(self, value):
        if not value:
            return None
        others = User.all_objects.filter(username__iexact=value)
        if self.instance:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError("This handle is taken.")
        return value

    def validate(self, attrs):
        actor = self.context["request"].user
        target = self.instance
        current = self.to_representation(target) if target else {}
        changing = [f for f in PRIVILEGE_FIELDS if f in attrs and attrs[f] != current.get(f, False)]
        if changing and not actor.is_superuser:
            raise serializers.ValidationError({changing[0]: "Only superusers can change staff, superuser or moderator access."})
        if target is not None and target.is_superuser and not actor.is_superuser:
            raise serializers.ValidationError({"detail": "Only superusers can edit a superuser account."})
        if target is not None and target.pk == actor.pk:
            for flag in ("is_active", "is_staff", "is_superuser"):
                if flag in attrs and not attrs[flag] and getattr(target, flag):
                    raise serializers.ValidationError({flag: "You cannot remove your own access."})
        if attrs.get("password"):
            email = attrs.get("email") or (target.email if target else "")
            password_validation.validate_password(attrs["password"], User(email=email))
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", "") or None
        moderator = validated_data.pop("is_moderator", False)
        email = validated_data.pop("email")
        user = User.objects.create_user(email, password, **validated_data)
        self._set_moderator(user, moderator)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", "")
        moderator = validated_data.pop("is_moderator", None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save(update_fields=["password"])
        if moderator is not None:
            self._set_moderator(instance, moderator)
        return instance

    @staticmethod
    def _set_moderator(user, on):
        (user.user_permissions.add if on else user.user_permissions.remove)(moderate_permission())


class AdminFanProfileSerializer(admin_serializer(FanProfile, read_only=("user", "guest_session"))):
    points = serializers.IntegerField(read_only=True, help_text="Total points in the activity ledger.")
    current_team = serializers.UUIDField(read_only=True, label="Current team", help_text="Team the fan supports now.")
    current_team_label = serializers.CharField(read_only=True, allow_null=True, label="Current team",
                                               help_text="Name of the current team.")
    post_count = serializers.IntegerField(read_only=True, help_text="Community posts written.")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["current_team_resource"] = "teams"
        return data


def _load_references(rows):
    """{(reference_type, uuid): obj} for a page of ledger rows, one query per referenced model."""
    wanted = {}
    for row in rows:
        if row.reference_type and row.reference_uuid:
            wanted.setdefault(row.reference_type, set()).add(row.reference_uuid)
    found = {}
    for label, ids in wanted.items():
        try:
            model = apps.get_model(label)
        except LookupError:
            continue
        # select_related(): str() of e.g. a membership names its team
        found.update(((label, obj.pk), obj) for obj in model._base_manager.select_related().filter(pk__in=ids))
    return found


class AdminActivityListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        rows = list(data.all() if hasattr(data, "all") else data)
        self.child.references = _load_references(rows)
        return super().to_representation(rows)


class AdminActivitySerializer(admin_serializer(FanActivity)):
    """Names the record a ledger row points at (``reference_type`` + ``reference_uuid``) instead of a bare id."""

    references = None  # filled per page by AdminActivityListSerializer

    class Meta(admin_serializer(FanActivity).Meta):
        list_serializer_class = AdminActivityListSerializer

    def to_representation(self, instance):
        data = super().to_representation(instance)
        label, resource = None, None
        if instance.reference_type and instance.reference_uuid:
            try:
                model = apps.get_model(instance.reference_type)
                refs = self.references if self.references is not None else _load_references([instance])
                obj = refs.get((instance.reference_type, instance.reference_uuid))
                label = str(obj) if obj is not None else "Deleted record"
                resource = resource_for_model(model)
            except LookupError:
                label = instance.reference_type
        data["reference_uuid_label"] = label
        data["reference_uuid_resource"] = resource
        return data


class AdminPollSerializer(admin_serializer(Poll, read_only=("created_by",), clean=True)):
    option_texts = serializers.ListField(
        child=serializers.CharField(max_length=120), write_only=True, required=False,
        help_text="Options to add, one per line. A new poll needs at least two. Existing options are kept.",
    )
    options_summary = serializers.SerializerMethodField(help_text="Options with their vote counts.")

    def get_options_summary(self, obj):
        return [
            {"id": str(o.pk), "text": o.text, "votes": getattr(o, "vote_count", 0), "deleted": o.deleted_at is not None}
            for o in obj.options.all()
        ]

    def validate(self, attrs):
        texts = attrs.pop("option_texts", None)
        attrs = super().validate(attrs)
        texts = [t.strip() for t in texts or [] if t.strip()]
        if len(set(texts)) != len(texts):
            raise serializers.ValidationError({"option_texts": "Options must be different."})
        if self.instance is None and len(texts) < 2:
            raise serializers.ValidationError({"option_texts": "Provide at least two options."})
        attrs["option_texts"] = texts
        return attrs

    def create(self, validated_data):
        texts = validated_data.pop("option_texts")
        poll = Poll.objects.create(created_by=self.context["request"].user, **validated_data)
        PollOption.objects.bulk_create(PollOption(poll=poll, text=t, display_order=i) for i, t in enumerate(texts))
        return poll

    def update(self, instance, validated_data):
        texts = validated_data.pop("option_texts", [])
        instance = super().update(instance, validated_data)
        existing = set(instance.options.values_list("text", flat=True))
        start = instance.options.count()
        new = [t for t in texts if t not in existing]
        PollOption.objects.bulk_create(
            PollOption(poll=instance, text=t, display_order=start + i) for i, t in enumerate(new)
        )
        return instance


class AdminPostSerializer(admin_serializer(CommunityPost, read_only=("author", "status", "published_at"))):
    open_reports = serializers.IntegerField(read_only=True, help_text="Reports still open or under review.")
    score = serializers.IntegerField(read_only=True, help_text="Upvotes minus downvotes.")


class AdminReportSerializer(admin_serializer(ModerationReport, read_only=("reporter", "post", "reason",
                                                                           "description", "resolved_at"))):
    def update(self, instance, validated_data):
        new_status = validated_data.get("status", instance.status)
        closing = new_status in (ModerationReport.Status.RESOLVED, ModerationReport.Status.DISMISSED)
        validated_data["resolved_at"] = (instance.resolved_at or timezone.now()) if closing else None
        return super().update(instance, validated_data)


# ----- custom action inputs -----

class SwitchTeamInput(serializers.Serializer):
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.filter(is_active=True), help_text="New team.")


class AdjustPointsInput(serializers.Serializer):
    points = serializers.IntegerField(min_value=-10000, max_value=10000,
                                      help_text="Points to add (negative to deduct).")
    reason = serializers.CharField(max_length=200, help_text="Why the points changed; stored in the ledger.")

    def validate_points(self, value):
        if value == 0:
            raise serializers.ValidationError("Use a non-zero amount.")
        return value


class AwardBadgeInput(serializers.Serializer):
    badge = serializers.PrimaryKeyRelatedField(queryset=Badge.objects.filter(is_active=True), help_text="Badge to award.")
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, help_text="Optional note.")


class ModerateInput(serializers.Serializer):
    action_type = serializers.ChoiceField(choices=ModerationAction.ActionType.choices, help_text="Decision.")
    reason = serializers.CharField(max_length=1000, help_text="Required explanation; kept in the audit log.")
    report = serializers.PrimaryKeyRelatedField(
        queryset=ModerationReport.objects.all(), required=False, allow_null=True,
        help_text="Optional report this decision resolves.",
    )


class ReasonInput(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, help_text="Required explanation; kept in the audit log.")
