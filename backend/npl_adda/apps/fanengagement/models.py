from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.accounts.models import GuestSession
from apps.common.models import BaseModel, alive
from apps.matches.models import Match
from apps.teams.models import Team


class FanProfile(BaseModel):
    """Public fan identity, owned by exactly one registered user or one guest session."""

    class Personality(models.TextChoices):
        DIE_HARD = "die_hard", "Die-hard"
        ANALYST = "analyst", "Analyst"
        MEME_MAKER = "meme_maker", "Meme maker"
        CASUAL = "casual", "Casual"
        NEWCOMER = "newcomer", "Newcomer"

    class CardTheme(models.TextChoices):
        CLASSIC = "classic", "Classic Fan"
        STADIUM = "stadium", "Stadium Night"
        MATCHDAY = "matchday", "Matchday Edition"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="fan_profiles",
        help_text="Registered owner; unique among active profiles. Empty for guest-owned profiles.",
    )
    guest_session = models.ForeignKey(
        GuestSession,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="fan_profiles",
        help_text="Guest owner; unique among active profiles. Cleared when migrated to an account.",
    )
    nickname = models.CharField(
        max_length=40, validators=[MinLengthValidator(2)], help_text="Public display name (2-40 characters)."
    )
    fan_personality = models.CharField(
        max_length=20, choices=Personality.choices, default=Personality.CASUAL, help_text="Self-selected fan type."
    )
    bio = models.CharField(max_length=280, blank=True, help_text="Optional short profile description.")
    avatar_url = models.URLField(blank=True, help_text="Legacy avatar link; no longer shown. Fans upload ``avatar``.")
    avatar = models.ImageField(
        upload_to="avatars/%Y/%m/", blank=True,
        help_text="Square avatar, validated and re-encoded by the server (no metadata).",
    )
    tagline = models.CharField(max_length=80, blank=True, help_text="Short line shown on the fan card.")
    card_theme = models.CharField(
        max_length=20, choices=CardTheme.choices, default=CardTheme.CLASSIC, help_text="Fan card visual theme."
    )
    is_public = models.BooleanField(default=True, help_text="Whether other fans can view the profile.")
    # What the shareable/public fan card shows. Nickname, team and level are always shown.
    card_show_avatar = models.BooleanField(default=True, help_text="Show the avatar on the public fan card.")
    card_show_stats = models.BooleanField(default=True, help_text="Show activity statistics on the public fan card.")
    card_show_badges = models.BooleanField(default=True, help_text="Show earned badges on the public fan card.")
    card_show_since = models.BooleanField(default=True, help_text="Show the 'fan since' year on the public fan card.")

    class Meta(BaseModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(user__isnull=False, guest_session__isnull=True)
                | Q(user__isnull=True, guest_session__isnull=False),
                name="fanprofile_exactly_one_owner",
            ),
            models.UniqueConstraint(
                fields=["user"], condition=alive(user__isnull=False), name="fanprofile_unique_active_user"
            ),
            models.UniqueConstraint(
                fields=["guest_session"],
                condition=alive(guest_session__isnull=False),
                name="fanprofile_unique_active_guest",
            ),
        ]

    def __str__(self):
        return self.nickname

    @property
    def current_membership(self):
        return self.memberships.filter(left_at__isnull=True).select_related("team").first()


class TeamMembership(BaseModel):
    """Historical team support. One open (left_at empty) membership per profile; switching closes the old one."""

    class JoinSource(models.TextChoices):
        ONBOARDING = "onboarding", "Onboarding"
        SWITCH = "switch", "Team switch"
        GUEST_MIGRATION = "guest_migration", "Guest migration"
        ADMIN = "admin", "Admin"

    fan_profile = models.ForeignKey(
        FanProfile, on_delete=models.CASCADE, related_name="memberships", help_text="Supporting fan."
    )
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="memberships", help_text="Supported team.")
    joined_at = models.DateTimeField(default=timezone.now, help_text="When support for this team began.")
    left_at = models.DateTimeField(null=True, blank=True, help_text="When support ended; empty if current.")
    join_source = models.CharField(
        max_length=20, choices=JoinSource.choices, default=JoinSource.ONBOARDING, help_text="How the membership began."
    )

    class Meta(BaseModel.Meta):
        ordering = ("-joined_at",)
        indexes = [
            models.Index(fields=["team", "left_at"]),
            # current member counts per team (partial: open memberships only)
            models.Index(fields=["team"], condition=Q(left_at__isnull=True, deleted_at__isnull=True),
                         name="membership_active_team_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["fan_profile"], condition=alive(left_at__isnull=True), name="membership_one_active_per_profile"
            ),
            models.CheckConstraint(
                condition=Q(left_at__isnull=True) | Q(left_at__gte=F("joined_at")), name="membership_left_after_joined"
            ),
        ]

    def __str__(self):
        return f"{self.fan_profile} -> {self.team}"


class FanActivity(BaseModel):
    """
    Append-only activity and points ledger. Points are set only by backend services;
    rows are never edited or deleted through the API. Totals and rankings are sums of this table.
    """

    class ActivityType(models.TextChoices):
        TEAM_JOINED = "team_joined", "Joined a team"
        POLL_VOTE = "poll_vote", "Voted in a poll"
        PREDICTION_SUBMITTED = "prediction_submitted", "Submitted a prediction"
        PREDICTION_CORRECT = "prediction_correct", "Correct prediction"
        POST_PUBLISHED = "post_published", "Post published"
        BADGE_AWARDED = "badge_awarded", "Badge awarded"
        ADJUSTMENT = "adjustment", "Manual adjustment"
        MEME_CONTEST_WIN = "meme_contest_win", "Won a meme contest"

    fan_profile = models.ForeignKey(
        FanProfile, on_delete=models.CASCADE, related_name="activities", help_text="Fan the activity belongs to."
    )
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Team the fan supported when the activity happened.",
    )
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices, help_text="Kind of activity.")
    reference_type = models.CharField(
        max_length=50, blank=True, help_text="Model label of the referenced object, e.g. 'matches.match'."
    )
    reference_uuid = models.UUIDField(null=True, blank=True, help_text="UUID of the referenced object.")
    points_delta = models.IntegerField(default=0, help_text="Points earned (positive) or deducted (negative).")
    idempotency_key = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        unique=True,
        help_text="Unique operation key that stops the same reward being issued twice.",
    )
    metadata = models.JSONField(default=dict, blank=True, help_text="Extra non-sensitive details about the activity.")
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True, help_text="When the activity happened.")

    class Meta(BaseModel.Meta):
        ordering = ("-occurred_at",)
        verbose_name_plural = "fan activities"
        indexes = [
            models.Index(fields=["fan_profile", "occurred_at"]),
            models.Index(fields=["activity_type"]),
            # team leaderboard: SUM(points) per team within a season window
            models.Index(fields=["team", "occurred_at"], name="activity_team_time_idx"),
            # badge/challenge progress: COUNT per (profile, activity type)
            models.Index(fields=["fan_profile", "activity_type"], name="activity_profile_type_idx"),
        ]

    def __str__(self):
        return f"{self.fan_profile}: {self.activity_type} ({self.points_delta:+d})"


class Badge(BaseModel):
    class Rule(models.TextChoices):
        TEAM_MEMBER = "team_member", "Joined a team"
        FIRST_VOTE = "first_vote", "First poll vote"
        FIRST_PREDICTION = "first_prediction", "First prediction"
        PREDICTION_ACE = "prediction_ace", "Five correct predictions"
        FIRST_POST = "first_post", "First published post"

    code = models.SlugField(max_length=50, help_text="Unique badge identifier among active badges.")
    name = models.CharField(max_length=80, help_text="Badge name shown to fans.")
    description = models.CharField(max_length=255, help_text="What the fan did to earn the badge.")
    icon_name = models.CharField(max_length=50, help_text="Approved frontend icon identifier.")
    rule_key = models.CharField(max_length=30, choices=Rule.choices, help_text="Backend rule that awards the badge.")
    is_active = models.BooleanField(default=True, help_text="Whether the badge can currently be earned.")

    class Meta(BaseModel.Meta):
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=["code"], condition=alive(), name="badge_unique_active_code")]

    def __str__(self):
        return self.name


class FanBadge(BaseModel):
    fan_profile = models.ForeignKey(
        FanProfile, on_delete=models.CASCADE, related_name="badges", help_text="Fan who earned the badge."
    )
    badge = models.ForeignKey(Badge, on_delete=models.PROTECT, related_name="awards", help_text="Badge earned.")
    awarded_at = models.DateTimeField(default=timezone.now, help_text="When the badge was awarded.")
    reason = models.CharField(max_length=255, blank=True, help_text="Optional explanation of the award.")

    class Meta(BaseModel.Meta):
        ordering = ("-awarded_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["fan_profile", "badge"], condition=alive(), name="fanbadge_unique_per_profile"
            )
        ]

    def __str__(self):
        return f"{self.fan_profile} - {self.badge}"


class Poll(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    class ResultsVisibility(models.TextChoices):
        ALWAYS = "always", "Always visible"
        AFTER_VOTE = "after_vote", "After the fan votes"
        AFTER_CLOSE = "after_close", "After voting closes"

    question = models.CharField(max_length=200, help_text="Poll question.")
    description = models.TextField(blank=True, help_text="Optional context for the question.")
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.PROTECT, related_name="polls", help_text="Related team, if any."
    )
    match = models.ForeignKey(
        Match, null=True, blank=True, on_delete=models.PROTECT, related_name="polls", help_text="Related match, if any."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="polls_created",
        help_text="Staff account that created the poll.",
    )
    opens_at = models.DateTimeField(help_text="When voting opens.")
    closes_at = models.DateTimeField(help_text="When voting closes (exclusive).")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, help_text="Editorial state of the poll."
    )
    results_visibility = models.CharField(
        max_length=20,
        choices=ResultsVisibility.choices,
        default=ResultsVisibility.AFTER_VOTE,
        help_text="When fans may see vote counts.",
    )

    class Meta(BaseModel.Meta):
        ordering = ("-opens_at",)
        indexes = [models.Index(fields=["status", "opens_at"])]
        constraints = [
            models.CheckConstraint(condition=Q(closes_at__gt=F("opens_at")), name="poll_closes_after_opens")
        ]

    def __str__(self):
        return self.question

    def is_accepting_votes(self, now=None):
        now = now or timezone.now()
        return self.status in (self.Status.SCHEDULED, self.Status.OPEN) and self.opens_at <= now < self.closes_at

    def clean(self):
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            raise ValidationError({"closes_at": "Voting must close after it opens."})


class PollOption(BaseModel):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options", help_text="Poll offering this option.")
    text = models.CharField(max_length=120, help_text="Option text.")
    display_order = models.PositiveSmallIntegerField(default=0, help_text="Ascending display order.")

    class Meta(BaseModel.Meta):
        ordering = ("display_order", "created_at")
        constraints = [
            models.UniqueConstraint(fields=["poll", "text"], condition=alive(), name="polloption_unique_text_per_poll")
        ]

    def __str__(self):
        return self.text


class Vote(BaseModel):
    """One vote per profile per poll; the option must belong to the poll (checked in services/clean)."""

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes", help_text="Poll voted in.")
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name="votes", help_text="Chosen option.")
    fan_profile = models.ForeignKey(FanProfile, on_delete=models.CASCADE, related_name="votes", help_text="Voter.")
    voted_at = models.DateTimeField(default=timezone.now, help_text="When the vote was cast.")

    class Meta(BaseModel.Meta):
        ordering = ("-voted_at",)
        indexes = [models.Index(fields=["poll", "option"], name="vote_poll_option_idx")]  # result counts
        constraints = [
            models.UniqueConstraint(fields=["poll", "fan_profile"], condition=alive(), name="vote_one_per_profile_poll")
        ]

    def clean(self):
        if self.option_id and self.poll_id and self.option.poll_id != self.poll_id:
            raise ValidationError({"option": "Option does not belong to this poll."})


class Prediction(BaseModel):
    """Match-winner prediction. Points are calculated only by the scoring service."""

    fan_profile = models.ForeignKey(
        FanProfile, on_delete=models.CASCADE, related_name="predictions", help_text="Predicting fan."
    )
    match = models.ForeignKey(Match, on_delete=models.PROTECT, related_name="predictions", help_text="Predicted match.")
    predicted_winner = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Team predicted to win; must play in the match.",
    )
    submitted_at = models.DateTimeField(default=timezone.now, help_text="When the prediction was last submitted.")
    points_awarded = models.PositiveIntegerField(default=0, help_text="Points granted by server-side scoring.")
    scored_at = models.DateTimeField(null=True, blank=True, help_text="When the prediction was scored.")

    class Meta(BaseModel.Meta):
        ordering = ("-submitted_at",)
        indexes = [
            models.Index(fields=["match", "predicted_winner"], name="prediction_split_idx"),
            # scoring job only touches unscored rows
            models.Index(fields=["match"], condition=Q(scored_at__isnull=True), name="prediction_unscored_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["fan_profile", "match"], condition=alive(), name="prediction_one_per_profile_match"
            )
        ]

    def __str__(self):
        return f"{self.fan_profile}: {self.match}"
