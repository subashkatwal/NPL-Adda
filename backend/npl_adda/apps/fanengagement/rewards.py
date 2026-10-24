"""
Server-side points ledger and badge rules. The frontend never sends point values;
every reward has an idempotency key so retries cannot double-award.
"""
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from .models import Badge, FanActivity, FanBadge

Activity = FanActivity.ActivityType

POINTS = {
    Activity.TEAM_JOINED: 10,
    Activity.POLL_VOTE: 2,
    Activity.PREDICTION_SUBMITTED: 1,
    Activity.PREDICTION_CORRECT: 10,
    Activity.POST_PUBLISHED: 5,
    Activity.BADGE_AWARDED: 0,
    Activity.MEME_CONTEST_WIN: 25,
}

# Each badge rule is "reach `target` ledger rows of `activity_type`"; the same numbers drive
# badge awards and the challenge progress shown to fans.
BADGE_TARGETS = {
    Badge.Rule.TEAM_MEMBER: (Activity.TEAM_JOINED, 1),
    Badge.Rule.FIRST_VOTE: (Activity.POLL_VOTE, 1),
    Badge.Rule.FIRST_PREDICTION: (Activity.PREDICTION_SUBMITTED, 1),
    Badge.Rule.PREDICTION_ACE: (Activity.PREDICTION_CORRECT, 5),
    Badge.Rule.FIRST_POST: (Activity.POST_PUBLISHED, 1),
}


def activity_counts(profile):
    """Ledger rows per activity type for the badge rules, in one query."""
    types = {activity_type for activity_type, _ in BADGE_TARGETS.values()}
    rows = profile.activities.filter(activity_type__in=types).values_list("activity_type").annotate(n=Count("id"))
    return dict(rows)


def badge_progress(counts, rule_key):
    """Returns (current, target) for a badge rule, with current capped at target. ``counts`` is ``activity_counts()``."""
    activity_type, target = BADGE_TARGETS[rule_key]
    return min(counts.get(activity_type, 0), target), target


def record_activity(profile, activity_type, *, reference=None, idempotency_key=None, team=None,
                    points=None, metadata=None, evaluate=True):
    """Append a ledger row. Returns (activity, created); a repeated idempotency key returns the original."""
    if idempotency_key:
        existing = FanActivity.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing, False
    if team is None and (membership := profile.current_membership):
        team = membership.team
    try:
        with transaction.atomic():
            activity = FanActivity.objects.create(
                fan_profile=profile,
                team=team,
                activity_type=activity_type,
                reference_type=reference._meta.label_lower if reference is not None else "",
                reference_uuid=reference.pk if reference is not None else None,
                points_delta=POINTS.get(activity_type, 0) if points is None else points,
                idempotency_key=idempotency_key,
                metadata=metadata or {},
            )
    except IntegrityError:
        if idempotency_key:
            return FanActivity.objects.get(idempotency_key=idempotency_key), False
        raise
    if evaluate:
        evaluate_badges(profile)
    return activity, True


def evaluate_badges(profile):
    held = profile.badges.values_list("badge_id", flat=True)
    pending = list(Badge.objects.filter(is_active=True, rule_key__in=BADGE_TARGETS).exclude(id__in=held))
    counts = activity_counts(profile) if pending else {}
    for badge in pending:
        current, target = badge_progress(counts, badge.rule_key)
        if current >= target:
            award_badge(profile, badge, reason=badge.description)


def award_badge(profile, badge, reason=""):
    try:
        with transaction.atomic():
            fan_badge = FanBadge.objects.create(fan_profile=profile, badge=badge, reason=reason)
    except IntegrityError:
        return None
    record_activity(
        profile, Activity.BADGE_AWARDED, reference=badge,
        idempotency_key=f"badge:{profile.pk}:{badge.pk}", evaluate=False,
    )
    return fan_badge


def total_points(profile):
    return profile.activities.aggregate(total=Coalesce(Sum("points_delta"), 0))["total"]
