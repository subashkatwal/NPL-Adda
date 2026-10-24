from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..models import CommunityPost, ContentVote


class PostMemeSerializer(serializers.Serializer):
    caption = serializers.CharField()
    template = serializers.DictField(allow_null=True, help_text="slug, category and layout_config for rendering.")
    team = serializers.UUIDField(allow_null=True)


class CommunityPostSerializer(serializers.ModelSerializer):
    author_nickname = serializers.CharField(source="author.nickname", read_only=True)
    score = serializers.SerializerMethodField()
    meme = serializers.SerializerMethodField(help_text="Template and caption when the post came from MEME Zone.")
    submit_for_review = serializers.BooleanField(
        write_only=True, required=False, default=False, help_text="Send straight to moderation instead of saving a draft."
    )

    class Meta:
        model = CommunityPost
        fields = ("id", "author", "author_nickname", "team", "match", "content_type", "title", "body", "language",
                  "media_url", "is_ai_generated", "source_references", "status", "published_at", "score", "meme",
                  "submit_for_review", "created_at", "updated_at")
        read_only_fields = ("id", "author", "status", "published_at", "is_ai_generated", "created_at", "updated_at")

    @extend_schema_field(serializers.IntegerField())
    def get_score(self, obj):
        return getattr(obj, "score", 0) or 0

    @extend_schema_field(PostMemeSerializer(allow_null=True))
    def get_meme(self, obj):
        draft = next(iter(obj.meme_drafts.all()), None)  # uses the prefetch when present
        if draft is None:
            return None
        template = draft.template
        return {
            "caption": draft.caption,
            "team": draft.team_id,
            "template": {"slug": template.slug, "category": template.category, "layout_config": template.layout_config}
            if template else None,
        }

    def validate_source_references(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a list.")
        return value


class ContentVoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentVote
        fields = ("id", "vote_type", "voted_at")
        read_only_fields = ("id", "voted_at")
