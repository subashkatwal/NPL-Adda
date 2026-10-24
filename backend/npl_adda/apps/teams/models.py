from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel, alive

HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"
hex_color_validator = RegexValidator(HEX_COLOR, "Use a #RRGGBB hex colour.")
season_year_validators = [MinValueValidator(2000), MaxValueValidator(2100)]


class Team(BaseModel):
    """NPL franchise. Soft-deleted when retired; protected from physical deletion by matches and rosters."""

    name = models.CharField(max_length=80, help_text="Full team display name.")
    slug = models.SlugField(max_length=80, help_text="URL-friendly identifier, unique among active teams.")
    short_name = models.CharField(max_length=10, help_text="Compact name for scorecards, e.g. 'KTM'.")
    city = models.CharField(max_length=60, help_text="City the franchise represents.")
    description = models.TextField(blank=True, help_text="Optional team description.")
    primary_color = models.CharField(
        max_length=7, validators=[hex_color_validator], help_text="Primary brand colour as #RRGGBB."
    )
    secondary_color = models.CharField(
        max_length=7, validators=[hex_color_validator], help_text="Secondary brand colour as #RRGGBB."
    )
    asset_url = models.URLField(blank=True, help_text="Optional link to original or authorised team artwork.")
    is_active = models.BooleanField(default=True, help_text="Whether the team is shown to fans.")
    display_order = models.PositiveSmallIntegerField(default=0, help_text="Ascending sort order in the frontend.")

    class Meta(BaseModel.Meta):
        ordering = ("display_order", "name")
        constraints = [
            models.UniqueConstraint(fields=["slug"], condition=alive(), name="team_unique_active_slug"),
            models.UniqueConstraint(fields=["name"], condition=alive(), name="team_unique_active_name"),
            models.CheckConstraint(condition=Q(primary_color__regex=HEX_COLOR), name="team_primary_color_hex"),
            models.CheckConstraint(condition=Q(secondary_color__regex=HEX_COLOR), name="team_secondary_color_hex"),
        ]

    def __str__(self):
        return self.name


class Player(BaseModel):
    class Role(models.TextChoices):
        BATTER = "batter", "Batter"
        BOWLER = "bowler", "Bowler"
        ALL_ROUNDER = "all_rounder", "All-rounder"
        WICKET_KEEPER = "wicket_keeper", "Wicket-keeper"

    class BattingStyle(models.TextChoices):
        RIGHT_HAND = "right_hand", "Right-hand bat"
        LEFT_HAND = "left_hand", "Left-hand bat"

    class BowlingStyle(models.TextChoices):
        RIGHT_ARM_FAST = "right_arm_fast", "Right-arm fast"
        RIGHT_ARM_MEDIUM = "right_arm_medium", "Right-arm medium"
        RIGHT_ARM_OFF_SPIN = "right_arm_off_spin", "Right-arm off spin"
        RIGHT_ARM_LEG_SPIN = "right_arm_leg_spin", "Right-arm leg spin"
        LEFT_ARM_FAST = "left_arm_fast", "Left-arm fast"
        LEFT_ARM_MEDIUM = "left_arm_medium", "Left-arm medium"
        LEFT_ARM_ORTHODOX = "left_arm_orthodox", "Left-arm orthodox"
        LEFT_ARM_WRIST_SPIN = "left_arm_wrist_spin", "Left-arm wrist spin"

    full_name = models.CharField(max_length=120, help_text="Player's display name.")
    slug = models.SlugField(max_length=120, help_text="URL-friendly identifier, unique among active players.")
    nationality = models.CharField(max_length=60, help_text="Player's nationality, e.g. 'Nepal'.")
    role = models.CharField(max_length=20, choices=Role.choices, help_text="Primary playing role.")
    batting_style = models.CharField(
        max_length=20, choices=BattingStyle.choices, blank=True, help_text="Optional batting hand."
    )
    bowling_style = models.CharField(
        max_length=30, choices=BowlingStyle.choices, blank=True, help_text="Optional bowling style."
    )
    profile_image_url = models.URLField(blank=True, help_text="Optional link to an authorised player image.")
    biography = models.TextField(blank=True, help_text="Optional player biography.")
    is_active = models.BooleanField(default=True, help_text="Whether the player is shown to fans.")

    class Meta(BaseModel.Meta):
        ordering = ("full_name",)
        constraints = [
            models.UniqueConstraint(fields=["slug"], condition=alive(), name="player_unique_active_slug"),
        ]

    def __str__(self):
        return self.full_name


class TeamRoster(BaseModel):
    """A player's squad membership for one team and season. Kept for history; never physically deleted via API."""

    class RosterRole(models.TextChoices):
        REGULAR = "regular", "Regular"
        MARQUEE = "marquee", "Marquee"
        OVERSEAS = "overseas", "Overseas"
        RESERVE = "reserve", "Reserve"

    team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="rosters", help_text="Team the player is registered with."
    )
    player = models.ForeignKey(
        Player, on_delete=models.PROTECT, related_name="rosters", help_text="Registered player."
    )
    season_year = models.PositiveSmallIntegerField(
        validators=season_year_validators, help_text="Season year this roster entry applies to."
    )
    jersey_number = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(999)], help_text="Optional shirt number."
    )
    roster_role = models.CharField(
        max_length=20, choices=RosterRole.choices, default=RosterRole.REGULAR, help_text="Squad role this season."
    )
    is_captain = models.BooleanField(default=False, help_text="Whether the player captains the team this season.")
    is_active = models.BooleanField(default=True, help_text="Whether the player is currently in the squad.")

    class Meta(BaseModel.Meta):
        ordering = ("team", "-season_year", "player__full_name")
        constraints = [
            models.UniqueConstraint(
                fields=["team", "player", "season_year"], condition=alive(), name="roster_unique_team_player_season"
            ),
            models.UniqueConstraint(
                fields=["team", "season_year"],
                condition=alive(is_captain=True, is_active=True),
                name="roster_one_captain_per_team_season",
            ),
            models.UniqueConstraint(
                fields=["team", "season_year", "jersey_number"],
                condition=alive(jersey_number__isnull=False),
                name="roster_unique_jersey_per_team_season",
            ),
        ]

    def __str__(self):
        return f"{self.player} - {self.team} ({self.season_year})"
