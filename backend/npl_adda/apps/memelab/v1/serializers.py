from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.content.models import CommunityPost, Language, PostComment, PostReaction
from apps.fanengagement.card import fan_identity
from apps.matches.models import Match
from apps.teams.models import Team

from .. import imaging
from ..captioning import join_caption
from ..models import ContestEntry, MemeContest, MemeDraft, MemeGenerationRequest, MemeTemplate, MemeUpload
from ..moderation import check_text
from ..stats import reaction_counts

FAN_STYLES = ("funny", "roast", "rivalry", "reaction", "fan_pain")


def _moderated(value, *, allow_links=False):
    if problem := check_text(value, allow_links=allow_links):
        raise serializers.ValidationError(problem)
    return value


def _media(file_field):
    return file_field.url if file_field else None


class GenerationCreateSerializer(serializers.Serializer):
    topic = serializers.CharField(min_length=3, max_length=200, trim_whitespace=True)
    language = serializers.ChoiceField(choices=Language.choices, default=Language.ENGLISH)
    style = serializers.ChoiceField(choices=MemeGenerationRequest.Style.choices,
                                    default=MemeGenerationRequest.Style.REACTION)
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.filter(is_active=True), required=False,
                                              allow_null=True)
    match = serializers.PrimaryKeyRelatedField(queryset=Match.objects.all(), required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=100, required=False,
                                            help_text="Or send the Idempotency-Key header.")

    def validate_topic(self, value):
        return _moderated(value)

    def validate(self, attrs):
        team, match = attrs.get("team"), attrs.get("match")
        if team and match and team.pk not in match.team_ids:
            raise serializers.ValidationError({"match": "Pick a match involving the selected team."})
        return attrs


class MemeTemplateSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField(help_text="Background image, if the template has one.")

    class Meta:
        model = MemeTemplate
        exclude = ("deleted_at",)
        read_only_fields = ("id", "created_at", "updated_at", "image")

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_image_url(self, obj):
        return _media(obj.image)

    def validate_layout_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be a JSON object.")
        return value


class MemeUploadSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MemeUpload
        fields = ("id", "image_url", "width", "height", "size_bytes", "created_at")
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_image_url(self, obj):
        return _media(obj.image)


class UploadCreateSerializer(serializers.Serializer):
    image = serializers.FileField(help_text="JPEG, PNG or WebP, up to MEME_UPLOAD_MAX_BYTES (5 MB by default).")


class MemeGenerationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemeGenerationRequest
        exclude = ("deleted_at", "fan_profile")
        read_only_fields = [f.name for f in MemeGenerationRequest._meta.fields]


class TextStyleField(serializers.JSONField):
    def to_internal_value(self, data):
        try:
            return imaging.clean_text_style(super().to_internal_value(data))
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))


class ExtraUploadsField(serializers.ListField):
    """Up to 3 more of the caller's own uploads (for collages), stored as id strings."""

    def __init__(self, **kwargs):
        super().__init__(child=serializers.UUIDField(), max_length=3, required=False, **kwargs)

    def to_internal_value(self, data):
        ids = list(dict.fromkeys(super().to_internal_value(data)))  # de-duplicate, keep order
        profile = self.context.get("profile")
        owned = set(MemeUpload.objects.filter(pk__in=ids, fan_profile=profile).values_list("pk", flat=True)) if profile else set()
        if any(i not in owned for i in ids):
            raise serializers.ValidationError("Use your own uploads.")
        return [str(i) for i in ids]


class MemeDraftSerializer(serializers.ModelSerializer):
    text_style = TextStyleField(required=False, help_text="Caption placement (see the model help).")
    extra_uploads = ExtraUploadsField(help_text="Up to 3 more of your upload ids for a collage.")
    caption = serializers.CharField(max_length=280, required=False, allow_blank=True)
    rendered_image_url = serializers.SerializerMethodField()
    upload_url = serializers.SerializerMethodField()

    class Meta:
        model = MemeDraft
        fields = ("id", "generation_request", "team", "match", "template", "upload", "upload_url", "extra_uploads", "caption",
                  "top_text", "bottom_text", "text_style", "language", "alternate_captions", "source_references",
                  "rendered_image_url", "status", "published_post", "created_at", "updated_at")
        read_only_fields = ("id", "generation_request", "source_references", "status", "published_post",
                            "created_at", "updated_at")

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_rendered_image_url(self, obj):
        return _media(obj.rendered_image)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_upload_url(self, obj):
        return _media(obj.upload.image) if obj.upload_id else None

    def validate_alternate_captions(self, value):
        def ok(item):
            if isinstance(item, str):
                return len(item) <= 280
            return isinstance(item, dict) and all(isinstance(item.get(k, ""), str) and len(item.get(k, "")) <= 140
                                                  for k in ("top", "bottom"))
        if not isinstance(value, list) or not all(ok(c) for c in value):
            raise serializers.ValidationError("Must be a list of captions.")
        return value

    def validate_template(self, value):
        if value is not None and not value.is_active:
            raise serializers.ValidationError("Template is not available.")
        return value

    def validate_upload(self, value):
        profile = self.context.get("profile")
        if value is not None and (profile is None or value.fan_profile_id != profile.pk):
            raise serializers.ValidationError("Use one of your own uploads.")
        return value

    def validate_top_text(self, value):
        return _moderated(value.strip())

    def validate_bottom_text(self, value):
        return _moderated(value.strip())

    def validate_caption(self, value):
        return _moderated(value.strip())

    def validate(self, attrs):
        top = attrs.get("top_text", getattr(self.instance, "top_text", ""))
        bottom = attrs.get("bottom_text", getattr(self.instance, "bottom_text", ""))
        if "top_text" in attrs or "bottom_text" in attrs:
            attrs["caption"] = join_caption(top, bottom)
        elif "caption" in attrs:  # single-caption edit (older clients): it becomes the meme's bottom line
            attrs["top_text"], attrs["bottom_text"] = "", attrs["caption"][:140]
        caption = attrs.get("caption", getattr(self.instance, "caption", ""))
        if len((caption or "").strip()) < 2:
            raise serializers.ValidationError({"caption": "Write a caption (top or bottom text)."})
        return attrs


class RenderPreviewSerializer(serializers.Serializer):
    template = serializers.PrimaryKeyRelatedField(queryset=MemeTemplate.objects.filter(is_active=True), required=False,
                                                  allow_null=True)
    upload = serializers.PrimaryKeyRelatedField(queryset=MemeUpload.objects.all(), required=False, allow_null=True)
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.filter(is_active=True), required=False,
                                              allow_null=True)
    top_text = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    bottom_text = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    text_style = TextStyleField(required=False, default=dict)
    extra_uploads = ExtraUploadsField(default=list)

    def validate_upload(self, value):
        profile = self.context.get("profile")
        if value is not None and (profile is None or value.fan_profile_id != profile.pk):
            raise serializers.ValidationError("Use one of your own uploads.")
        return value


class CaptionOptionSerializer(serializers.Serializer):
    top = serializers.CharField(allow_blank=True)
    bottom = serializers.CharField(allow_blank=True)


class GenerationResultSerializer(serializers.Serializer):
    request = MemeGenerationRequestSerializer()
    draft = MemeDraftSerializer(allow_null=True)
    captions = serializers.ListField(child=serializers.CharField())
    options = CaptionOptionSerializer(many=True)
    is_mock = serializers.BooleanField(help_text="True when captions came from the offline templates, not an AI model.")
    provider = serializers.CharField()
    verified_facts = serializers.BooleanField(help_text="True when captions could use stored match facts.")
    notice = serializers.CharField(allow_null=True)


class GenerationErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()
    request = MemeGenerationRequestSerializer()


# ---------------------------------------------------------------- feed

class TeamBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ("id", "name", "short_name", "primary_color", "secondary_color")


class MemeSerializer(serializers.ModelSerializer):
    """A published meme with its engagement, as shown on cards and the detail page."""

    image_url = serializers.CharField(source="media_url", allow_null=True)
    author = serializers.SerializerMethodField()
    team = TeamBriefSerializer(allow_null=True)
    match = serializers.SerializerMethodField()
    legacy = serializers.SerializerMethodField(help_text="Template and caption for memes made before server rendering.")
    counts = serializers.SerializerMethodField()
    engagement = serializers.IntegerField()
    my_vote = serializers.CharField(allow_null=True, default=None)
    my_reaction = serializers.CharField(allow_null=True, default=None)
    is_mine = serializers.SerializerMethodField()
    is_featured = serializers.SerializerMethodField()

    class Meta:
        model = CommunityPost
        fields = ("id", "image_url", "body", "language", "author", "team", "match", "legacy", "counts", "engagement",
                  "my_vote", "my_reaction", "is_mine", "is_featured", "is_ai_generated", "published_at")

    def get_author(self, obj):
        return fan_identity(obj.author, getattr(obj, "author_points", None))

    def get_match(self, obj):
        m = obj.match
        if not m:
            return None
        return {"id": str(m.pk), "label": f"{m.home_team.short_name} vs {m.away_team.short_name}",
                "starts_at": m.starts_at, "status": m.status}

    def get_legacy(self, obj):
        if obj.media_url:
            return None
        draft = next(iter(obj.meme_drafts.all()), None)
        if draft is None:
            return None
        tpl = draft.template
        return {"caption": draft.caption, "template": {"layout_config": tpl.layout_config} if tpl else None}

    def get_counts(self, obj):
        return {"upvotes": obj.upvotes, "downvotes": obj.downvotes, "reactions": obj.reaction_count,
                "comments": obj.comment_count, "by_reaction": reaction_counts(obj)}

    def get_is_mine(self, obj):
        profile = self.context.get("profile")
        return bool(profile and obj.author_id == profile.pk)

    def get_is_featured(self, obj):
        return obj.featured_at is not None


class ReactionInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=PostReaction.Kind.choices)


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = PostComment
        fields = ("id", "author", "body", "is_hidden", "parent", "replies", "is_mine", "created_at")

    def get_author(self, obj):
        return fan_identity(obj.author, getattr(obj, "author_points", None))

    def get_body(self, obj):
        return None if obj.is_hidden else obj.body

    def get_replies(self, obj):
        if obj.parent_id:
            return []
        replies = [r for r in obj.replies.all() if r.deleted_at is None]
        return CommentSerializer(replies, many=True, context=self.context).data

    def get_is_mine(self, obj):
        profile = self.context.get("profile")
        return bool(profile and obj.author_id == profile.pk)


class CommentCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=1000, trim_whitespace=True)
    parent = serializers.UUIDField(required=False, allow_null=True)

    def validate_body(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("Write something first.")
        return _moderated(value)


class CommentReportInput(serializers.Serializer):
    reason = serializers.ChoiceField(choices=[("spam", "Spam"), ("harassment", "Harassment or hate"),
                                              ("misinformation", "Misinformation"), ("inappropriate", "Inappropriate"),
                                              ("other", "Other")])
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class HideCommentInput(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


# ---------------------------------------------------------------- contests

class ContestEntrySerializer(serializers.ModelSerializer):
    meme = serializers.SerializerMethodField()
    votes = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = ContestEntry
        fields = ("id", "meme", "status", "votes", "final_votes", "final_rank", "is_mine", "created_at")

    def get_meme(self, obj):
        post = obj.post
        return {"id": str(post.pk), "image_url": post.media_url or None, "body": post.body,
                "author": post.author.nickname, "team": post.team.short_name if post.team_id else None,
                "available": post.status == CommunityPost.Status.PUBLISHED and post.deleted_at is None}

    def get_votes(self, obj):
        if obj.final_votes is not None:
            return obj.final_votes
        return (self.context.get("tally") or {}).get(obj.pk, 0)

    def get_is_mine(self, obj):
        profile = self.context.get("profile")
        return bool(profile and obj.fan_profile_id == profile.pk)


class ContestSerializer(serializers.ModelSerializer):
    phase = serializers.SerializerMethodField(
        help_text="draft | upcoming | submissions | open | voting | submissions_closed | closed | finalized | cancelled")
    match = serializers.SerializerMethodField()
    team = TeamBriefSerializer(allow_null=True)
    entry_count = serializers.IntegerField(read_only=True, default=0)
    winner = serializers.SerializerMethodField()

    class Meta:
        model = MemeContest
        fields = ("id", "title", "description", "phase", "status", "match", "team", "submissions_open_at",
                  "submissions_close_at", "voting_open_at", "voting_close_at", "max_entries_per_fan",
                  "requires_entry_review", "entry_count", "winner", "finalized_at")

    def get_phase(self, obj):
        return obj.phase(timezone.now())

    def get_match(self, obj):
        m = obj.match
        if not m:
            return None
        return {"id": str(m.pk), "label": f"{m.home_team.name} vs {m.away_team.name}", "match_number": m.match_number,
                "starts_at": m.starts_at, "status": m.status, "result_text": m.result_text,
                "home": TeamBriefSerializer(m.home_team).data, "away": TeamBriefSerializer(m.away_team).data}

    def get_winner(self, obj):
        if not obj.winner_id:
            return None
        post = obj.winner.post
        return {"entry_id": str(obj.winner_id), "meme_id": str(post.pk), "image_url": post.media_url or None,
                "author": post.author.nickname, "votes": obj.winner.final_votes}


class EnterContestInput(serializers.Serializer):
    post = serializers.PrimaryKeyRelatedField(queryset=CommunityPost.objects.all(), help_text="Your published meme.")


class ContestVoteInput(serializers.Serializer):
    entry = serializers.PrimaryKeyRelatedField(queryset=ContestEntry.objects.select_related("post"))
