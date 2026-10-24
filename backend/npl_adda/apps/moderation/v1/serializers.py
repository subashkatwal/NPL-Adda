from rest_framework import serializers

from apps.common.permissions import is_moderator
from apps.content.models import CommunityPost

from ..models import ModerationAction, ModerationReport


class ReportCreateSerializer(serializers.ModelSerializer):
    post = serializers.PrimaryKeyRelatedField(queryset=CommunityPost.objects.filter(status="published"))

    class Meta:
        model = ModerationReport
        fields = ("id", "post", "reason", "description", "status", "created_at")
        read_only_fields = ("id", "status", "created_at")
        validators = []


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModerationReport
        exclude = ("deleted_at",)
        read_only_fields = ("id", "reporter", "post", "comment", "reason", "description", "resolved_at", "created_at",
                            "updated_at")
        validators = []

    def validate_assigned_to(self, value):
        if value is not None and not is_moderator(value):
            raise serializers.ValidationError("Reports can only be assigned to moderators.")
        return value

    def validate(self, attrs):
        if attrs.get("status") in (ModerationReport.Status.RESOLVED, ModerationReport.Status.DISMISSED):
            if not (attrs.get("resolution_note") or getattr(self.instance, "resolution_note", "")).strip():
                raise serializers.ValidationError({"resolution_note": "Explain the resolution."})
        return attrs


class ActionCreateSerializer(serializers.Serializer):
    post = serializers.UUIDField()
    action_type = serializers.ChoiceField(choices=ModerationAction.ActionType.choices)
    reason = serializers.CharField()
    report = serializers.UUIDField(required=False, allow_null=True, help_text="Report this action resolves.")


class ActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModerationAction
        exclude = ("deleted_at",)
        read_only_fields = [f.name for f in ModerationAction._meta.fields]
