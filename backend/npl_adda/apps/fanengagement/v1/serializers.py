from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.permissions import is_moderator
from apps.matches.models import Match
from apps.teams.models import Team
from apps.teams.v1.serializers import TeamSerializer

from apps.memelab import moderation

from .. import card
from ..identity import get_fan_profile
from ..models import Badge, FanActivity, FanBadge, FanProfile, Poll, PollOption, Prediction, TeamMembership

BASE_READ_ONLY = ("id", "created_at", "updated_at")


class TeamMembershipSerializer(serializers.ModelSerializer):
    team_detail = TeamSerializer(source="team", read_only=True)

    class Meta:
        model = TeamMembership
        fields = ("id", "team", "team_detail", "joined_at", "left_at", "join_source")
        read_only_fields = fields


class JoinTeamSerializer(serializers.Serializer):
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.filter(is_active=True))


CARD_PRIVACY_FIELDS = ("card_show_avatar", "card_show_stats", "card_show_badges", "card_show_since")


class FanProfileSerializer(serializers.ModelSerializer):
    current_team = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    # Only server-processed uploads (POST /fanpage/me/avatar) are shown; external links are not accepted.
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = FanProfile
        fields = ("id", "nickname", "fan_personality", "bio", "tagline", "avatar_url", "card_theme", "is_public",
                  *CARD_PRIVACY_FIELDS, "current_team", "is_owner", "created_at", "updated_at")
        read_only_fields = BASE_READ_ONLY

    def get_avatar_url(self, obj):
        return card.avatar_src(obj)

    def _clean_text(self, value):
        value = " ".join((value or "").split())  # collapse whitespace and newlines
        if problem := moderation.check_text(value):
            raise serializers.ValidationError(problem)
        return value

    def validate_nickname(self, value):
        value = self._clean_text(value)
        if len(value) < 2:
            raise serializers.ValidationError("Use at least 2 characters.")
        return value

    def validate_tagline(self, value):
        return self._clean_text(value)

    def validate_bio(self, value):
        return self._clean_text(value)

    @extend_schema_field(TeamSerializer(allow_null=True))
    def get_current_team(self, obj):
        prefetched = getattr(obj, "active_memberships", None)  # set by the list view's prefetch
        membership = prefetched[0] if prefetched else (None if prefetched is not None else obj.current_membership)
        return TeamSerializer(membership.team).data if membership else None

    @extend_schema_field(serializers.BooleanField())
    def get_is_owner(self, obj):
        request = self.context.get("request")
        profile = get_fan_profile(request) if request else None
        return bool(profile and profile.pk == obj.pk)


class FanProfileCreateSerializer(FanProfileSerializer):
    team = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.filter(is_active=True), write_only=True, required=False,
        help_text="Optional team to join immediately.",
    )

    class Meta(FanProfileSerializer.Meta):
        fields = FanProfileSerializer.Meta.fields + ("team",)


class FanActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = FanActivity
        fields = ("id", "activity_type", "team", "reference_type", "reference_uuid", "points_delta",
                  "metadata", "occurred_at")
        read_only_fields = fields


class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = ("id", "code", "name", "description", "icon_name", "rule_key", "is_active")
        read_only_fields = ("id",)


class FanBadgeSerializer(serializers.ModelSerializer):
    badge = BadgeSerializer(read_only=True)

    class Meta:
        model = FanBadge
        fields = ("id", "badge", "awarded_at", "reason")
        read_only_fields = fields


class LeaderboardEntrySerializer(serializers.ModelSerializer):
    points = serializers.IntegerField(read_only=True)
    rank = serializers.IntegerField(read_only=True)
    level = serializers.SerializerMethodField(help_text="Fan level from all-time verified points.")

    class Meta:
        model = FanProfile
        fields = ("id", "rank", "nickname", "fan_personality", "card_theme", "points", "level")
        read_only_fields = fields

    @extend_schema_field(serializers.DictField())
    def get_level(self, obj):
        lvl = card.fan_level(getattr(obj, "total_points", obj.points))
        return {"key": lvl["key"], "name": lvl["name"]}


class FanCardSerializer(serializers.Serializer):
    """Shape of GET /fanpage/me/card and /fanpage/<id>/card (documentation only)."""

    fan_code = serializers.CharField()
    nickname = serializers.CharField()
    tagline = serializers.CharField()
    theme = serializers.CharField()
    team = TeamSerializer(allow_null=True)
    level = serializers.DictField()
    avatar_url = serializers.CharField()
    stats = serializers.DictField(allow_null=True)
    badges = serializers.ListField(child=serializers.DictField(), allow_null=True)
    badges_total = serializers.IntegerField()
    member_since = serializers.IntegerField(allow_null=True)
    is_owner = serializers.BooleanField()


class AvatarUploadSerializer(serializers.Serializer):
    image = serializers.ImageField(help_text="JPEG, PNG or WebP up to 5 MB. Cropped to a square and stripped of metadata.")


class TeamLeaderboardEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    team = TeamSerializer()
    points = serializers.IntegerField(help_text="Points fans earned while supporting this team.")
    members = serializers.IntegerField(help_text="Fans currently supporting this team.")
    activity_count = serializers.IntegerField(help_text="Ledger activities attributed to this team.")


class SeasonRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    year = serializers.IntegerField()


class SeasonSummarySerializer(serializers.Serializer):
    season = SeasonRefSerializer(allow_null=True)
    points = serializers.IntegerField()
    rank = serializers.IntegerField(allow_null=True, help_text="Rank among public fans this season; null with no points.")
    activities_by_type = serializers.DictField(child=serializers.IntegerField())
    votes = serializers.IntegerField()
    predictions_made = serializers.IntegerField()
    predictions_correct = serializers.IntegerField()
    predictions_pending = serializers.IntegerField()
    badges_earned = serializers.IntegerField()
    posts_published = serializers.IntegerField()
    teams_supported = serializers.IntegerField()


class ChallengeSerializer(serializers.Serializer):
    badge = BadgeSerializer()
    current = serializers.IntegerField()
    target = serializers.IntegerField()
    completed = serializers.BooleanField()
    awarded_at = serializers.DateTimeField(allow_null=True)


class PredictionSplitSerializer(serializers.Serializer):
    team = serializers.UUIDField()
    name = serializers.CharField()
    count = serializers.IntegerField()


class PredictionSummarySerializer(serializers.Serializer):
    match = serializers.UUIDField()
    total = serializers.IntegerField()
    split = PredictionSplitSerializer(many=True)


class PollOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PollOption
        fields = ("id", "text", "display_order")
        read_only_fields = ("id",)


class PollSerializer(serializers.ModelSerializer):
    options = PollOptionSerializer(many=True)
    is_accepting_votes = serializers.SerializerMethodField()
    my_vote = serializers.SerializerMethodField(help_text="Option the caller voted for, if any.")
    results = serializers.SerializerMethodField(help_text="Vote counts, only when the visibility rule allows.")

    class Meta:
        model = Poll
        fields = ("id", "question", "description", "team", "match", "opens_at", "closes_at", "status",
                  "results_visibility", "options", "is_accepting_votes", "my_vote", "results", "created_at")
        read_only_fields = ("id", "created_at")

    def _profile(self):
        request = self.context.get("request")
        return get_fan_profile(request) if request else None

    @extend_schema_field(serializers.BooleanField())
    def get_is_accepting_votes(self, obj):
        return obj.is_accepting_votes()

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_my_vote(self, obj):
        if hasattr(obj, "my_vote_id"):  # annotated by the list view
            return obj.my_vote_id
        profile = self._profile()
        if not profile:
            return None
        return obj.votes.filter(fan_profile=profile).values_list("option_id", flat=True).first()

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_results(self, obj):
        request = self.context.get("request")
        if request and PollResultsSerializer.can_view(obj, request, self._profile()):
            return PollResultsSerializer(PollResultsSerializer.build(obj)).data
        return None

    def validate(self, attrs):
        opens = attrs.get("opens_at", getattr(self.instance, "opens_at", None))
        closes = attrs.get("closes_at", getattr(self.instance, "closes_at", None))
        if opens and closes and closes <= opens:
            raise serializers.ValidationError({"closes_at": "Voting must close after it opens."})
        if self.instance is None and len(attrs.get("options", [])) < 2:
            raise serializers.ValidationError({"options": "Provide at least two options."})
        return attrs

    def create(self, validated_data):
        options = validated_data.pop("options")
        poll = Poll.objects.create(created_by=self.context["request"].user, **validated_data)
        PollOption.objects.bulk_create(PollOption(poll=poll, **o) for o in options)
        return poll

    def update(self, instance, validated_data):
        validated_data.pop("options", None)  # options are fixed once created so votes stay valid
        return super().update(instance, validated_data)


class VoteSerializer(serializers.Serializer):
    option = serializers.UUIDField()


class PollResultOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    text = serializers.CharField()
    votes = serializers.IntegerField()


class PollResultsSerializer(serializers.Serializer):
    poll = serializers.UUIDField()
    total_votes = serializers.IntegerField()
    options = PollResultOptionSerializer(many=True)

    @staticmethod
    def build(poll):
        rows = list(poll.options.all())  # reuses the annotated prefetch when the view supplied one
        if rows and not hasattr(rows[0], "vote_count"):
            rows = poll.options.annotate(vote_count=Count("votes", filter=Q(votes__deleted_at__isnull=True)))
        options = [{"id": o.pk, "text": o.text, "votes": o.vote_count} for o in rows]
        return {"poll": poll.pk, "total_votes": sum(o["votes"] for o in options), "options": options}

    @staticmethod
    def can_view(poll, request, profile):
        if is_moderator(request.user) or request.user.is_staff:
            return True
        if poll.results_visibility == Poll.ResultsVisibility.ALWAYS:
            return True
        if poll.results_visibility == Poll.ResultsVisibility.AFTER_VOTE:
            if hasattr(poll, "my_vote_id"):
                return poll.my_vote_id is not None
            return bool(profile and poll.votes.filter(fan_profile=profile).exists())
        return poll.status == Poll.Status.CLOSED or timezone.now() >= poll.closes_at


class PredictionSerializer(serializers.ModelSerializer):
    match = serializers.PrimaryKeyRelatedField(queryset=Match.objects.all())
    predicted_winner = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all())

    class Meta:
        model = Prediction
        fields = ("id", "match", "predicted_winner", "submitted_at", "points_awarded", "scored_at")
        read_only_fields = ("id", "submitted_at", "points_awarded", "scored_at")
        validators = []


class ScoreResultSerializer(serializers.Serializer):
    scored = serializers.IntegerField()
