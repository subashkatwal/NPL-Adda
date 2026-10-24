from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.common import cricket
from apps.common.models import BaseModel, alive
from apps.teams.models import Player, Team, season_year_validators


class Season(BaseModel):
    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"

    name = models.CharField(max_length=60, help_text="Season display name, e.g. 'NPL 2025'.")
    year = models.PositiveSmallIntegerField(
        validators=season_year_validators, help_text="Season year, unique among active seasons."
    )
    starts_at = models.DateField(null=True, blank=True, help_text="Tournament start date, if announced.")
    ends_at = models.DateField(null=True, blank=True, help_text="Tournament end date, if announced.")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.UPCOMING, help_text="Tournament lifecycle state."
    )
    source_metadata = models.JSONField(
        default=dict, blank=True, help_text="Where the season data came from (provider, reference IDs)."
    )

    class Meta(BaseModel.Meta):
        ordering = ("-year",)
        constraints = [
            models.UniqueConstraint(fields=["year"], condition=alive(), name="season_unique_active_year"),
            models.CheckConstraint(
                condition=Q(starts_at__isnull=True) | Q(ends_at__isnull=True) | Q(ends_at__gte=F("starts_at")),
                name="season_ends_after_start",
            ),
        ]

    def __str__(self):
        return self.name


class Match(BaseModel):
    """A fixture. Results must come from stored source data, never generated."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        LIVE = "live", "Live"
        COMPLETED = "completed", "Completed"
        ABANDONED = "abandoned", "Abandoned"
        POSTPONED = "postponed", "Postponed"

    class TossDecision(models.TextChoices):
        BAT = "bat", "Bat"
        FIELD = "field", "Field"

    season = models.ForeignKey(
        Season, on_delete=models.PROTECT, related_name="matches", help_text="Season this match belongs to."
    )
    match_number = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Optional fixture number within the season."
    )
    home_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="home_matches", help_text="Home (first-listed) team."
    )
    away_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="away_matches", help_text="Away (second-listed) team."
    )
    venue = models.CharField(max_length=120, help_text="Ground name.")
    starts_at = models.DateTimeField(db_index=True, help_text="Scheduled start time.")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED, help_text="Current match state."
    )
    toss_winner = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tosses_won",
        help_text="Team that won the toss; must be one of the two teams.",
    )
    toss_decision = models.CharField(
        max_length=10, choices=TossDecision.choices, blank=True, help_text="Toss winner's choice; set with toss_winner."
    )
    winner = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="matches_won",
        help_text="Winning team; only for completed matches and must be one of the two teams.",
    )
    result_text = models.CharField(max_length=200, blank=True, help_text="Result summary, e.g. 'Won by 5 wickets'.")
    data_source = models.CharField(
        max_length=50, default="manual", help_text="Identifier of the data provider, e.g. 'manual'."
    )
    source_url = models.URLField(blank=True, help_text="Optional link to the source of this match data.")
    last_synced_at = models.DateTimeField(
        null=True, blank=True, help_text="When the data was last synced from its source."
    )

    class Meta(BaseModel.Meta):
        ordering = ("starts_at",)
        indexes = [
            models.Index(fields=["status", "starts_at"]),
            models.Index(fields=["season", "starts_at"]),
            # team schedules filter home OR away team; one index per side lets Postgres use a bitmap OR
            models.Index(fields=["home_team", "starts_at"], name="match_home_schedule_idx"),
            models.Index(fields=["away_team", "starts_at"], name="match_away_schedule_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=~Q(home_team=F("away_team")), name="match_distinct_teams"),
            models.CheckConstraint(
                condition=Q(toss_winner__isnull=True)
                | Q(toss_winner=F("home_team"))
                | Q(toss_winner=F("away_team")),
                name="match_toss_winner_in_match",
            ),
            models.CheckConstraint(
                condition=Q(winner__isnull=True) | Q(winner=F("home_team")) | Q(winner=F("away_team")),
                name="match_winner_in_match",
            ),
            models.CheckConstraint(
                condition=Q(toss_winner__isnull=True, toss_decision="")
                | (Q(toss_winner__isnull=False) & ~Q(toss_decision="")),
                name="match_toss_decision_with_winner",
            ),
            models.CheckConstraint(
                condition=Q(winner__isnull=True) | Q(status="completed"), name="match_winner_only_when_completed"
            ),
            models.UniqueConstraint(
                fields=["season", "match_number"],
                condition=alive(match_number__isnull=False),
                name="match_unique_number_per_season",
            ),
        ]

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} ({self.starts_at:%Y-%m-%d})"

    @property
    def team_ids(self):
        return {self.home_team_id, self.away_team_id}

    @property
    def prediction_deadline(self):
        return self.starts_at - timedelta(minutes=settings.PREDICTION_LOCK_MINUTES)

    def clean(self):
        errors = {}
        if self.home_team_id and self.home_team_id == self.away_team_id:
            errors["away_team"] = "Home and away teams must differ."
        if self.toss_winner_id and self.toss_winner_id not in self.team_ids:
            errors["toss_winner"] = "Toss winner must be one of the match teams."
        if bool(self.toss_winner_id) != bool(self.toss_decision):
            errors["toss_decision"] = "Toss winner and toss decision must be set together."
        if self.winner_id and self.winner_id not in self.team_ids:
            errors["winner"] = "Winner must be one of the match teams."
        if self.winner_id and self.status != self.Status.COMPLETED:
            errors["winner"] = "Only completed matches can have a winner."
        if errors:
            raise ValidationError(errors)


class MatchInnings(BaseModel):
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="innings", help_text="Match this innings belongs to."
    )
    innings_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(4)], help_text="Innings sequence (1-4, incl. super overs)."
    )
    batting_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="+", help_text="Team batting in this innings."
    )
    bowling_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="+", help_text="Team bowling in this innings."
    )
    runs = models.PositiveSmallIntegerField(default=0, help_text="Total runs including extras.")
    wickets = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(10)], help_text="Wickets lost (0-10)."
    )
    legal_balls = models.PositiveSmallIntegerField(
        default=0, help_text="Legal deliveries bowled; overs are derived from this integer."
    )
    extras = models.PositiveSmallIntegerField(default=0, help_text="Total extras conceded; included in runs.")
    target_runs = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Runs required to win, for a chasing innings."
    )
    is_complete = models.BooleanField(default=False, help_text="Whether the innings has finished.")

    class Meta(BaseModel.Meta):
        ordering = ("match", "innings_number")
        verbose_name_plural = "match innings"
        constraints = [
            models.UniqueConstraint(
                fields=["match", "innings_number"], condition=alive(), name="innings_unique_number_per_match"
            ),
            models.CheckConstraint(condition=~Q(batting_team=F("bowling_team")), name="innings_distinct_teams"),
            models.CheckConstraint(condition=Q(wickets__lte=10), name="innings_max_ten_wickets"),
            models.CheckConstraint(condition=Q(extras__lte=F("runs")), name="innings_extras_within_runs"),
            models.CheckConstraint(
                condition=Q(innings_number__gte=1, innings_number__lte=4), name="innings_number_range"
            ),
        ]

    def __str__(self):
        return f"{self.match} - innings {self.innings_number}"

    @property
    def overs(self):
        return cricket.overs(self.legal_balls)

    @property
    def run_rate(self):
        return cricket.run_rate(self.runs, self.legal_balls)

    @property
    def required_run_rate(self):
        if self.target_runs is None:
            return None
        return cricket.required_run_rate(
            self.target_runs, self.runs, self.legal_balls, settings.BALLS_PER_INNINGS
        )

    def clean(self):
        errors = {}
        if self.match_id:
            teams = Match.all_objects.filter(pk=self.match_id).values_list("home_team_id", "away_team_id").first()
            teams = set(teams or ())
            if self.batting_team_id and self.batting_team_id not in teams:
                errors["batting_team"] = "Batting team must play in this match."
            if self.bowling_team_id and self.bowling_team_id not in teams:
                errors["bowling_team"] = "Bowling team must play in this match."
        if self.batting_team_id and self.batting_team_id == self.bowling_team_id:
            errors["bowling_team"] = "Batting and bowling teams must differ."
        if (self.extras or 0) > (self.runs or 0):
            errors["extras"] = "Extras cannot exceed total runs."
        if errors:
            raise ValidationError(errors)


class PlayerMatchPerformance(BaseModel):
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="performances", help_text="Match the statistics are for."
    )
    player = models.ForeignKey(
        Player, on_delete=models.PROTECT, related_name="performances", help_text="Player the statistics belong to."
    )
    team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="+", help_text="Team the player represented in this match."
    )
    runs_scored = models.PositiveSmallIntegerField(default=0, help_text="Runs scored with the bat.")
    balls_faced = models.PositiveSmallIntegerField(default=0, help_text="Legal balls faced.")
    fours = models.PositiveSmallIntegerField(default=0, help_text="Boundary fours hit.")
    sixes = models.PositiveSmallIntegerField(default=0, help_text="Sixes hit.")
    is_not_out = models.BooleanField(default=False, help_text="Whether the batter finished not out.")
    bowling_balls = models.PositiveSmallIntegerField(default=0, help_text="Legal balls bowled.")
    runs_conceded = models.PositiveSmallIntegerField(default=0, help_text="Runs conceded while bowling.")
    wickets_taken = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(10)], help_text="Wickets taken while bowling."
    )
    maidens = models.PositiveSmallIntegerField(default=0, help_text="Maiden overs bowled.")
    catches = models.PositiveSmallIntegerField(default=0, help_text="Catches taken in the field.")
    run_outs = models.PositiveSmallIntegerField(default=0, help_text="Run-outs effected in the field.")

    class Meta(BaseModel.Meta):
        ordering = ("match", "-runs_scored")
        constraints = [
            models.UniqueConstraint(
                fields=["match", "player"], condition=alive(), name="performance_unique_player_per_match"
            ),
            models.CheckConstraint(
                condition=Q(runs_scored__gte=F("fours") * 4 + F("sixes") * 6), name="performance_boundaries_within_runs"
            ),
            models.CheckConstraint(
                condition=Q(balls_faced__gte=F("fours") + F("sixes")), name="performance_boundaries_within_balls"
            ),
            models.CheckConstraint(
                condition=Q(bowling_balls__gte=F("maidens") * 6), name="performance_maidens_within_balls"
            ),
            models.CheckConstraint(condition=Q(wickets_taken__lte=10), name="performance_max_ten_wickets"),
        ]

    def __str__(self):
        return f"{self.player} in {self.match}"

    @property
    def strike_rate(self):
        return cricket.strike_rate(self.runs_scored, self.balls_faced)

    @property
    def economy(self):
        return cricket.economy(self.runs_conceded, self.bowling_balls)

    def clean(self):
        errors = {}
        if self.match_id and self.team_id:
            teams = Match.all_objects.filter(pk=self.match_id).values_list("home_team_id", "away_team_id").first()
            if self.team_id not in set(teams or ()):
                errors["team"] = "Team must play in this match."
        if (self.fours or 0) * 4 + (self.sixes or 0) * 6 > (self.runs_scored or 0):
            errors["runs_scored"] = "Boundary runs exceed runs scored."
        if (self.maidens or 0) * 6 > (self.bowling_balls or 0):
            errors["maidens"] = "Maidens exceed overs bowled."
        if errors:
            raise ValidationError(errors)
