from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.common.models import BaseModel, alive
from apps.fanengagement.models import FanProfile
from apps.matches.models import Match
from apps.teams.models import Team


class Language(models.TextChoices):
    ENGLISH = "en", "English"
    NEPALI = "ne", "Nepali"
    ROMANIZED = "ne_rom", "Romanized Nepali"
    MIXED = "mixed", "Mixed"


class CommunityPost(BaseModel):
    """
    Fan content. Only PUBLISHED, non-deleted posts are public. Authors may create
    drafts and submit for review; status changes beyond that go through moderation.
    """

    class ContentType(models.TextChoices):
        FAN_POST = "fan_post", "Fan post"
        MEME = "meme", "Meme"
        REACTION = "reaction", "Reaction"
        ANALYSIS = "analysis", "Analysis"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_REVIEW = "pending_review", "Pending review"
        APPROVED = "approved", "Approved"
        PUBLISHED = "published", "Published"
        REJECTED = "rejected", "Rejected"
        HIDDEN = "hidden", "Hidden"
        REMOVED = "removed", "Removed"

    author = models.ForeignKey(FanProfile, on_delete=models.CASCADE, related_name="posts", help_text="Fan who wrote it.")
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.PROTECT, related_name="posts", help_text="Related team, if any."
    )
    match = models.ForeignKey(
        Match, null=True, blank=True, on_delete=models.PROTECT, related_name="posts", help_text="Related match, if any."
    )
    content_type = models.CharField(
        max_length=20, choices=ContentType.choices, default=ContentType.FAN_POST, help_text="Kind of post."
    )
    title = models.CharField(max_length=150, blank=True, help_text="Optional title.")
    body = models.TextField(max_length=5000, help_text="Post text (up to 5000 characters).")
    language = models.CharField(
        max_length=10, choices=Language.choices, default=Language.ENGLISH, help_text="Language of the post."
    )
    media_url = models.URLField(blank=True, help_text="Optional media link, e.g. a rendered meme.")
    is_ai_generated = models.BooleanField(default=False, help_text="Whether an AI model produced the content.")
    source_references = models.JSONField(
        default=list, blank=True, help_text="References to stored records supporting factual claims."
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True, help_text="Publication state."
    )
    published_at = models.DateTimeField(null=True, blank=True, help_text="When the post was first published.")
    featured_at = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text="When staff featured the post; empty if not featured."
    )

    class Meta(BaseModel.Meta):
        ordering = ("-published_at", "-created_at")
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["team", "status"]),
            models.Index(fields=["match", "status"]),
            models.Index(fields=["author", "status"]),
            # public feeds read only published, non-deleted rows, newest first (partial indexes stay small)
            models.Index(F("published_at").desc(nulls_last=True), name="post_public_feed_idx",
                         condition=Q(status="published", deleted_at__isnull=True)),
            models.Index("team", F("published_at").desc(nulls_last=True), name="post_team_feed_idx",
                         condition=Q(status="published", deleted_at__isnull=True)),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="published") | Q(published_at__isnull=False), name="post_published_has_timestamp"
            )
        ]

    def __str__(self):
        return self.title or self.body[:40]

    def publish(self):
        self.status = self.Status.PUBLISHED
        self.published_at = self.published_at or timezone.now()


class ContentVote(BaseModel):
    """One up/down vote per profile per post; re-voting changes the existing vote."""

    class VoteType(models.TextChoices):
        UP = "up", "Upvote"
        DOWN = "down", "Downvote"

    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name="votes", help_text="Voted post.")
    fan_profile = models.ForeignKey(
        FanProfile, on_delete=models.CASCADE, related_name="content_votes", help_text="Voting fan."
    )
    vote_type = models.CharField(max_length=10, choices=VoteType.choices, help_text="Upvote or downvote.")
    voted_at = models.DateTimeField(default=timezone.now, help_text="When the vote was last cast.")

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["post", "vote_type"], name="contentvote_post_type_idx")]  # post scores
        constraints = [
            models.UniqueConstraint(
                fields=["post", "fan_profile"], condition=alive(), name="contentvote_one_per_profile_post"
            )
        ]


class PostReaction(BaseModel):
    """One emoji reaction per fan per post; reacting again with another emoji changes it, the same one removes it."""

    class Kind(models.TextChoices):
        FIRE = "fire", "Fire"
        LAUGH = "laugh", "Laugh"
        CLAP = "clap", "Clap"
        HEARTBREAK = "heartbreak", "Heartbreak"

    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name="reactions",
                             help_text="Post reacted to.")
    fan_profile = models.ForeignKey(FanProfile, on_delete=models.CASCADE, related_name="post_reactions",
                                    help_text="Reacting fan.")
    kind = models.CharField(max_length=20, choices=Kind.choices, help_text="Which reaction.")

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["post", "kind"], name="reaction_post_kind_idx")]
        constraints = [
            models.UniqueConstraint(fields=["post", "fan_profile"], condition=alive(), name="reaction_one_per_fan_post")
        ]

    def __str__(self):
        return f"{self.kind} on {self.post_id}"


class PostComment(BaseModel):
    """A comment on a published post, or a reply to one (one level deep). Moderators can hide comments."""

    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name="comments",
                             help_text="Post commented on.")
    author = models.ForeignKey(FanProfile, on_delete=models.CASCADE, related_name="comments",
                               help_text="Fan who wrote the comment.")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies",
                               help_text="Comment this replies to; empty for a top-level comment.")
    body = models.TextField(max_length=1000, help_text="Comment text (up to 1000 characters).")
    is_hidden = models.BooleanField(default=False, db_index=True, help_text="Hidden by a moderator.")
    hidden_reason = models.CharField(max_length=255, blank=True, help_text="Why a moderator hid the comment.")

    class Meta(BaseModel.Meta):
        ordering = ("created_at",)
        indexes = [models.Index(fields=["post", "created_at"], name="comment_post_time_idx")]
        constraints = [models.CheckConstraint(condition=Q(body__regex=r"\S"), name="comment_body_required")]

    def __str__(self):
        return self.body[:40]
