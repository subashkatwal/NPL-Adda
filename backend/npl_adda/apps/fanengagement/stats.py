"""Deterministic leaderboards and season summaries computed from the FanActivity ledger."""
from datetime import date, datetime, time, timedelta

from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.matches.models import Season
from apps.teams.models import Team

from .models import FanActivity, TeamMembership


def default_season():
    """The season covering today, else the active one, else the most recent."""
    now = timezone.now()
    for season in Season.objects.order_by("-year"):
        start, end = season_window(season)
        if start <= now < end:
            return season
    return Season.objects.filter(status=Season.Status.ACTIVE).order_by("-year").first() or Season.objects.first()


def season_window(season):
    """[start, end) datetimes covering a season; falls back to the calendar year when dates are unset."""
    start = season.starts_at or date(season.year, 1, 1)
    end = season.ends_at or date(season.year, 12, 31)
    tz = timezone.get_current_timezone()
    return (datetime.combine(start, time.min, tzinfo=tz), datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz))


def activities_in(season):
    qs = FanActivity.objects.all()
    if season:
        start, end = season_window(season)
        qs = qs.filter(occurred_at__gte=start, occurred_at__lt=end)
    return qs


def dense_ranks(rows, key):
    rank, previous = 0, object()
    for row in rows:
        if row[key] != previous:
            rank += 1
            previous = row[key]
        row["rank"] = rank
    return rows


def team_leaderboard(season=None):
    """Teams ranked by points their fans earned while supporting them, plus current member counts."""
    points = (
        activities_in(season).filter(team=OuterRef("pk")).values("team")
        .annotate(total=Sum("points_delta")).values("total")
    )
    members = (
        TeamMembership.objects.filter(team=OuterRef("pk"), left_at__isnull=True, fan_profile__deleted_at__isnull=True)
        .values("team").annotate(n=Count("id")).values("n")
    )
    activity = activities_in(season).filter(team=OuterRef("pk")).values("team").annotate(n=Count("id")).values("n")
    teams = Team.objects.filter(is_active=True).annotate(
        points=Coalesce(Subquery(points, output_field=IntegerField()), 0),
        members=Coalesce(Subquery(members, output_field=IntegerField()), 0),
        activity_count=Coalesce(Subquery(activity, output_field=IntegerField()), 0),
    ).order_by("-points", "-members", "display_order")
    rows = [
        {"team": t, "points": t.points, "members": t.members, "activity_count": t.activity_count}
        for t in teams
    ]
    return dense_ranks(rows, "points")


def season_summary(profile, season):
    ledger = activities_in(season).filter(fan_profile=profile)
    points = ledger.aggregate(total=Coalesce(Sum("points_delta"), 0))["total"]
    by_type = dict(ledger.values_list("activity_type").annotate(n=Count("id")).values_list("activity_type", "n"))
    predictions = profile.predictions.filter(match__season=season) if season else profile.predictions.all()
    ahead = (
        activities_in(season).filter(fan_profile__is_public=True).values("fan_profile")
        .annotate(total=Sum("points_delta")).filter(total__gt=points).count()
    )
    start_end = season_window(season) if season else (None, None)
    badges = profile.badges.all()
    if season:
        badges = badges.filter(awarded_at__gte=start_end[0], awarded_at__lt=start_end[1])
    return {
        "season": season,
        "points": points,
        "rank": ahead + 1 if points > 0 else None,
        "activities_by_type": by_type,
        "votes": by_type.get(FanActivity.ActivityType.POLL_VOTE, 0),
        "predictions_made": predictions.count(),
        "predictions_correct": predictions.filter(scored_at__isnull=False, points_awarded__gt=0).count(),
        "predictions_pending": predictions.filter(scored_at__isnull=True).count(),
        "badges_earned": badges.count(),
        "posts_published": by_type.get(FanActivity.ActivityType.POST_PUBLISHED, 0),
        "teams_supported": profile.memberships.filter(
            Q(left_at__isnull=True) | Q(left_at__gte=start_end[0]) if season else Q()
        ).values("team").distinct().count(),
    }
