from django.core.validators import MinLengthValidator
from django.db import models
from django.db.models import F, Q

from apps.common.models import BaseModel, alive
from apps.content.models import CommunityPost, Language
from apps.fanengagement.models import FanProfile
from apps.matches.models import Match
from apps.teams.models import Team


class MemeTemplate(BaseModel):
    class Category(models.TextChoices):
        REACTION = "reaction", "Reaction"
        COMPARISON = "comparison", "Comparison"
        TOP_BOTTOM = "top_bottom", "Top/bottom caption"
        CELEBRATION = "celebration", "Celebration"
        HEARTBREAK = "heartbreak", "Heartbreak"

    name = models.CharField(max_length=80, help_text="Template name.")
    slug = models.SlugField(max_length=80, help_text="Unique identifier among active templates.")
    category = models.CharField(max_length=20, choices=Category.choices, help_text="Meme category.")
    layout_config = models.JSONField(
        default=dict, blank=True, help_text="Frontend rendering config: canvas size, text boxes, fonts."
    )
    preview_image_url = models.URLField(blank=True, help_text="Optional original or authorised preview image.")
    image = models.ImageField(
        upload_to="memes/templates/", blank=True,
        help_text="Optional background image (original or authorised). Without it a drawn background is used.",
    )
    is_active = models.BooleanField(default=True, help_text="Whether fans can use the template.")

    class Meta(BaseModel.Meta):
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=["slug"], condition=alive(), name="memetemplate_unique_active_slug")
        ]

    def __str__(self):
        return self.name


class MemeGenerationRequest(BaseModel):
    """One caption-generation job. ``provider == "mock"`` marks deterministic offline output."""

    class Style(models.TextChoices):
        ROAST = "roast", "Roast"
        RIVALRY = "rivalry", "Rivalry"
        REACTION = "reaction", "Reaction"
        FAN_PAIN = "fan_pain", "Relatable fan pain"
        FUNNY = "funny", "Funny"
        # earlier styles, still accepted
        WHOLESOME = "wholesome", "Wholesome"
        BANTER = "banter", "Friendly banter"
        SARCASTIC = "sarcastic", "Sarcastic"
        HYPE = "hype", "Hype"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    fan_profile = models.ForeignKey(
        FanProfile, on_delete=models.CASCADE, related_name="meme_requests", help_text="Requesting fan."
    )
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="Team to joke about."
    )
    match = models.ForeignKey(
        Match, null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="Match supplying facts."
    )
    topic = models.CharField(
        max_length=200, validators=[MinLengthValidator(3)], help_text="Fan-provided topic (3-200 characters)."
    )
    language = models.CharField(
        max_length=10, choices=Language.choices, default=Language.ENGLISH, help_text="Caption language."
    )
    style = models.CharField(
        max_length=20, choices=Style.choices, default=Style.BANTER, help_text="Requested humour style."
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, help_text="Processing state."
    )
    provider = models.CharField(max_length=40, blank=True, help_text="LLM provider used, or 'mock'.")
    model_name = models.CharField(max_length=80, blank=True, help_text="Model identifier used.")
    idempotency_key = models.CharField(
        max_length=100, help_text="Client-supplied key; repeats return the original request."
    )
    error_code = models.CharField(max_length=50, blank=True, help_text="Safe machine-readable failure code.")
    error_message = models.CharField(max_length=255, blank=True, help_text="Safe human-readable failure message.")
    usage_metadata = models.JSONField(default=dict, blank=True, help_text="Token usage and mock flag.")
    started_at = models.DateTimeField(null=True, blank=True, help_text="When processing started.")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="When processing finished.")

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["fan_profile", "idempotency_key"], condition=alive(), name="memerequest_unique_idempotency"
            ),
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(started_at__isnull=True) | Q(completed_at__gte=F("started_at")),
                name="memerequest_completed_after_started",
            ),
        ]

    def __str__(self):
        return f"{self.topic} ({self.status})"


class MemeUpload(BaseModel):
    """
    A fan-uploaded background image. The file is decoded, size-checked and re-encoded by the
    server before it is stored (see ``imaging.store_upload``), so only clean JPEG/PNG data is kept.
    """

    fan_profile = models.ForeignKey(
        FanProfile, on_delete=models.CASCADE, related_name="meme_uploads", help_text="Fan who uploaded the image."
    )
    image = models.ImageField(upload_to="memes/uploads/%Y/%m/", help_text="Re-encoded image file.")
    width = models.PositiveIntegerField(help_text="Stored width in pixels.")
    height = models.PositiveIntegerField(help_text="Stored height in pixels.")
    size_bytes = models.PositiveIntegerField(help_text="Stored file size in bytes.")
    sha256 = models.CharField(max_length=64, db_index=True, help_text="Hash of the stored file, for abuse review.")

    class Meta(BaseModel.Meta):
        pass

    def __str__(self):
        return f"Upload {self.pk}"


def default_text_style():
    return {"top_y": 0.04, "bottom_y": 0.78, "size": 1.0, "color": "#F5F7FA", "align": "center"}


class MemeDraft(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_REVIEW = "pending_review", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PUBLISHED = "published", "Published"

    fan_profile = models.ForeignKey(
        FanProfile, on_delete=models.CASCADE, related_name="meme_drafts", help_text="Owner of the draft."
    )
    generation_request = models.ForeignKey(
        MemeGenerationRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="drafts",
        help_text="Generation job that produced the draft, if any.",
    )
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="Related team."
    )
    match = models.ForeignKey(
        Match, null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="Related match."
    )
    template = models.ForeignKey(
        MemeTemplate, null=True, blank=True, on_delete=models.PROTECT, related_name="drafts", help_text="Chosen template."
    )
    caption = models.CharField(max_length=280, help_text="Selected caption.")
    top_text = models.CharField(max_length=140, blank=True, help_text="Caption drawn at the top of the image.")
    bottom_text = models.CharField(max_length=140, blank=True, help_text="Caption drawn at the bottom of the image.")
    text_style = models.JSONField(
        default=default_text_style, blank=True,
        help_text=("Caption style: top_y/bottom_y (0-1 of height), size/top_size/bottom_size (0.5-2), color (#RRGGBB), "
                   "align, font, caps, outline, band, collage."),
    )
    language = models.CharField(
        max_length=10, choices=Language.choices, default=Language.ENGLISH, help_text="Caption language."
    )
    upload = models.ForeignKey(
        MemeUpload, null=True, blank=True, on_delete=models.SET_NULL, related_name="drafts",
        help_text="Fan-uploaded background image, used instead of the template background.",
    )
    extra_uploads = models.JSONField(
        default=list, blank=True,
        help_text="Up to 3 more of the fan's upload ids for a collage (text_style.collage: side, stack or grid).",
    )
    rendered_image = models.ImageField(
        upload_to="memes/rendered/%Y/%m/", blank=True, help_text="Final image rendered by the server on submit."
    )
    alternate_captions = models.JSONField(default=list, blank=True, help_text="Other caption options.")
    source_references = models.JSONField(
        default=list, blank=True, help_text="Stored records supporting any factual claim in the caption."
    )
    rendered_image_url = models.URLField(null=True, blank=True, help_text="Rendered or uploaded image link.")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, help_text="Review state, synced from moderation."
    )
    published_post = models.ForeignKey(
        CommunityPost,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="meme_drafts",
        help_text="Community post created when the draft was submitted.",
    )

    class Meta(BaseModel.Meta):
        pass

    def __str__(self):
        return self.caption[:40]


class MemeContest(BaseModel):
    """
    "Meme of the Match" (or a team challenge). Phases come from the timestamps:
    submissions [submissions_open_at, submissions_close_at), voting [voting_open_at, voting_close_at).
    Results are fixed by ``finalize`` after voting closes; until then nothing is declared a winner.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft (hidden)"
        PUBLISHED = "published", "Published"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=120, help_text="Contest name shown to fans.")
    description = models.TextField(blank=True, help_text="Rules or theme for the contest.")
    match = models.ForeignKey(
        Match, null=True, blank=True, on_delete=models.PROTECT, related_name="meme_contests",
        help_text="Match the contest is about; entries must be about this match or one of its teams.",
    )
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.PROTECT, related_name="meme_contests",
        help_text="Team challenge: only memes for this team can enter.",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT,
                              help_text="Editorial state; fans only see published contests.")
    submissions_open_at = models.DateTimeField(help_text="When fans can start entering memes.")
    submissions_close_at = models.DateTimeField(help_text="When entries close.")
    voting_open_at = models.DateTimeField(help_text="When voting starts.")
    voting_close_at = models.DateTimeField(help_text="When voting ends.")
    max_entries_per_fan = models.PositiveSmallIntegerField(default=1, help_text="Entries allowed per fan.")
    requires_entry_review = models.BooleanField(
        default=False, help_text="Staff must approve each entry before it can receive votes."
    )
    winner = models.ForeignKey(
        "ContestEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="Winning entry, set when results are finalized.",
    )
    finalized_at = models.DateTimeField(null=True, blank=True, help_text="When results were finalized.")
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="Staff account that created the contest.",
    )

    class Meta(BaseModel.Meta):
        ordering = ("-voting_close_at",)
        constraints = [
            models.CheckConstraint(condition=Q(submissions_close_at__gt=F("submissions_open_at")),
                                   name="contest_submissions_window"),
            models.CheckConstraint(condition=Q(voting_close_at__gt=F("voting_open_at")), name="contest_voting_window"),
            models.CheckConstraint(condition=Q(voting_open_at__gte=F("submissions_open_at")),
                                   name="contest_voting_after_submissions_open"),
            models.CheckConstraint(condition=Q(max_entries_per_fan__gte=1), name="contest_max_entries_positive"),
            models.UniqueConstraint(fields=["match"], condition=alive(match__isnull=False, team__isnull=True),
                                    name="contest_one_per_match"),
        ]

    def __str__(self):
        return self.title

    def phase(self, now):
        if self.status == self.Status.CANCELLED:
            return "cancelled"
        if self.status == self.Status.DRAFT:
            return "draft"
        if self.finalized_at:
            return "finalized"
        if now < self.submissions_open_at:
            return "upcoming"
        accepting = self.submissions_open_at <= now < self.submissions_close_at
        voting = self.voting_open_at <= now < self.voting_close_at
        if accepting and voting:
            return "open"
        if accepting:
            return "submissions"
        if voting:
            return "voting"
        return "closed" if now >= self.voting_close_at else "submissions_closed"


class ContestEntry(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    contest = models.ForeignKey(MemeContest, on_delete=models.CASCADE, related_name="entries",
                                help_text="Contest entered.")
    post = models.ForeignKey(CommunityPost, on_delete=models.PROTECT, related_name="contest_entries",
                             help_text="Published meme entered.")
    fan_profile = models.ForeignKey(FanProfile, on_delete=models.CASCADE, related_name="contest_entries",
                                    help_text="Fan who entered (the meme's author).")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPROVED,
                              help_text="Entry review state; only approved entries can be voted for.")
    review_note = models.CharField(max_length=255, blank=True, help_text="Staff note when rejecting an entry.")
    final_votes = models.PositiveIntegerField(null=True, blank=True, help_text="Counted votes at finalization.")
    final_rank = models.PositiveIntegerField(null=True, blank=True, help_text="Rank at finalization (1 = winner).")

    class Meta(BaseModel.Meta):
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(fields=["contest", "post"], condition=alive(), name="entry_unique_post_per_contest"),
        ]

    def __str__(self):
        return f"{self.post} in {self.contest}"


class ContestVote(BaseModel):
    """One vote per fan per contest (changeable while voting is open). Staff can exclude suspicious votes."""

    contest = models.ForeignKey(MemeContest, on_delete=models.CASCADE, related_name="votes", help_text="Contest.")
    entry = models.ForeignKey(ContestEntry, on_delete=models.CASCADE, related_name="votes", help_text="Entry voted for.")
    fan_profile = models.ForeignKey(FanProfile, on_delete=models.CASCADE, related_name="contest_votes",
                                    help_text="Voting fan.")
    client_hash = models.CharField(max_length=32, blank=True, db_index=True,
                                   help_text="Salted hash of the voter's network address (never the address itself).")
    flag_reason = models.CharField(max_length=120, blank=True,
                                   help_text="Why the vote looks suspicious (new account, shared network...).")
    is_excluded = models.BooleanField(default=False, help_text="Staff excluded this vote from the count.")

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["contest", "fan_profile"], condition=alive(), name="contestvote_one_per_fan"),
        ]
        indexes = [models.Index(fields=["contest", "entry"], name="contestvote_tally_idx")]

    def __str__(self):
        return f"{self.fan_profile} -> {self.entry_id}"
