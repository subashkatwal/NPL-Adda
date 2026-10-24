from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.matches.models import Match

from .models import FanProfile, Poll, Prediction, TeamMembership, Vote
from .rewards import Activity, record_activity

PREDICTION_CORRECT_POINTS = 10


class Conflict(ValidationError):
    status_code = 409


@transaction.atomic
def switch_team(profile, team, source=TeamMembership.JoinSource.SWITCH):
    """Close the open membership and open a new one. History rows are never deleted."""
    FanProfile.objects.select_for_update().get(pk=profile.pk)
    current = profile.memberships.filter(left_at__isnull=True).first()
    if current and current.team_id == team.pk:
        return current, False
    now = timezone.now()
    if current:
        current.left_at = now
        current.save(update_fields=["left_at", "updated_at"])
    membership = TeamMembership.objects.create(fan_profile=profile, team=team, joined_at=now, join_source=source)
    record_activity(
        profile, Activity.TEAM_JOINED, reference=team, team=team,
        idempotency_key=f"team_joined:{profile.pk}:{team.pk}",
    )
    return membership, True


@transaction.atomic
def cast_vote(profile, poll, option):
    poll = Poll.objects.select_for_update().get(pk=poll.pk)
    if not poll.is_accepting_votes():
        raise ValidationError({"poll": "This poll is not accepting votes."})
    if option.poll_id != poll.pk:
        raise ValidationError({"option": "Option does not belong to this poll."})
    try:
        with transaction.atomic():
            vote = Vote.objects.create(poll=poll, option=option, fan_profile=profile)
    except IntegrityError:
        raise Conflict({"poll": "You have already voted in this poll."})
    record_activity(profile, Activity.POLL_VOTE, reference=poll, idempotency_key=f"vote:{poll.pk}:{profile.pk}")
    return vote


@transaction.atomic
def submit_prediction(profile, match, predicted_winner):
    """Create or change a winner prediction until the match's prediction deadline."""
    match = Match.objects.select_for_update().get(pk=match.pk)
    if match.status != Match.Status.SCHEDULED or timezone.now() >= match.prediction_deadline:
        raise ValidationError({"match": "Predictions for this match are closed."})
    if predicted_winner.pk not in match.team_ids:
        raise ValidationError({"predicted_winner": "Pick one of the two teams in this match."})
    prediction = Prediction.objects.select_for_update().filter(fan_profile=profile, match=match).first()
    if prediction:
        prediction.predicted_winner = predicted_winner
        prediction.submitted_at = timezone.now()
        prediction.save(update_fields=["predicted_winner", "submitted_at", "updated_at"])
    else:
        prediction = Prediction.objects.create(fan_profile=profile, match=match, predicted_winner=predicted_winner)
    record_activity(
        profile, Activity.PREDICTION_SUBMITTED, reference=match,
        idempotency_key=f"prediction:{match.pk}:{profile.pk}",
    )
    return prediction


@transaction.atomic
def score_match_predictions(match):
    """Score unscored predictions for a completed match. Safe to re-run: scored rows are skipped."""
    match = Match.objects.select_for_update().get(pk=match.pk)
    if match.status != Match.Status.COMPLETED:
        raise ValidationError({"match": "Only completed matches can be scored."})
    now = timezone.now()
    scored = 0
    for prediction in Prediction.objects.select_for_update().filter(match=match, scored_at__isnull=True):
        correct = match.winner_id is not None and prediction.predicted_winner_id == match.winner_id
        prediction.points_awarded = PREDICTION_CORRECT_POINTS if correct else 0
        prediction.scored_at = now
        prediction.save(update_fields=["points_awarded", "scored_at", "updated_at"])
        if correct:
            record_activity(
                prediction.fan_profile, Activity.PREDICTION_CORRECT, reference=match,
                points=PREDICTION_CORRECT_POINTS, idempotency_key=f"prediction_correct:{prediction.pk}",
            )
        scored += 1
    return scored


@transaction.atomic
def migrate_guest_to_user(guest_session, user):
    """
    Move a guest's fan data to an account atomically.

    No user profile yet: the guest profile simply changes owner. Otherwise eligible
    records are moved without duplicates (votes/predictions the user already has stay
    with the user's own copy), and the guest profile is soft-deleted. The session is revoked.
    """
    guest_profile = FanProfile.objects.select_for_update().filter(guest_session=guest_session).first()
    user_profile = FanProfile.objects.select_for_update().filter(user=user).first()
    result = guest_profile
    if guest_profile and not user_profile:
        guest_profile.user, guest_profile.guest_session = user, None
        guest_profile.save(update_fields=["user", "guest_session", "updated_at"])
    elif guest_profile and user_profile:
        _merge_profiles(source=guest_profile, target=user_profile)
        result = user_profile
    else:
        result = user_profile
    guest_session.linked_user = user
    guest_session.save(update_fields=["linked_user", "updated_at"])
    guest_session.revoke()
    return result


def _merge_profiles(source, target):
    voted = set(target.votes.values_list("poll_id", flat=True))
    source.votes.exclude(poll_id__in=voted).update(fan_profile=target)
    predicted = set(target.predictions.values_list("match_id", flat=True))
    source.predictions.exclude(match_id__in=predicted).update(fan_profile=target)
    held = set(target.badges.values_list("badge_id", flat=True))
    source.badges.exclude(badge_id__in=held).update(fan_profile=target)
    source.posts.update(author=target)
    source.meme_drafts.update(fan_profile=target)
    source.activities.update(fan_profile=target)
    if not target.memberships.filter(left_at__isnull=True).exists():
        source.memberships.update(fan_profile=target)
    else:
        source.memberships.filter(left_at__isnull=True).update(left_at=timezone.now())
        source.memberships.update(fan_profile=target)
    source.soft_delete()
