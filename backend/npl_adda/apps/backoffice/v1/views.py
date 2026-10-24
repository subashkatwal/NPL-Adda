"""
Staff admin console resources. Order of registration is the console's navigation order.

Every resource can be edited and soft-deleted (and restored). Rows the app writes itself
(memberships, ledger, votes, predictions, moderation actions, agent runs) cannot be created
here, and post status only changes through audited moderation actions.
"""
from datetime import timedelta

from django.db.models import Case, Count, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import GuestSession, SocialAccount, User
from apps.ai_agents.models import AgentRun, AgentToolCall
from apps.common.permissions import is_moderator
from apps.content.models import CommunityPost, ContentVote, PostComment, PostReaction
from apps.fanengagement import services as fan_services
from apps.fanengagement.models import (
    Badge, FanActivity, FanBadge, FanProfile, Poll, PollOption, Prediction, TeamMembership, Vote,
)
from apps.fanengagement.rewards import Activity, award_badge, record_activity
from apps.fanengagement.services import Conflict
from apps.matches.models import Match, MatchInnings, PlayerMatchPerformance, Season
from apps.memelab import services as meme_services
from apps.memelab.models import (
    ContestEntry, ContestVote, MemeContest, MemeDraft, MemeGenerationRequest, MemeTemplate, MemeUpload,
)
from apps.moderation import services as moderation_services
from apps.moderation.models import ModerationAction, ModerationReport
from apps.teams.models import Player, Team, TeamRoster

from ..models import SeenMarker
from . import serializers as s
from .base import REGISTRY, ActionSpec, AdminViewSet, EmptyInput, IsAdminStaff, admin_serializer, count_by, register

ACCOUNTS, TEAMS, MATCHES, FANS, CONTENT, MEMES, MODERATION, AI = (
    "Accounts", "Teams & players", "Matches", "Fan pages", "Community", "Meme Zone", "Moderation", "AI agents",
)


class ReadOnly:
    """Rows the app itself writes (history, ledger, audit). Staff can still correct or delete them."""

    allow_create = False


# ===================== Accounts =====================

@register
class UserAdminViewSet(AdminViewSet):
    resource, label, group, model = "users", "Users", ACCOUNTS, User
    serializer_class = s.AdminUserSerializer
    list_display = ("email", "display_name", "username", "is_active", "is_staff", "is_moderator", "date_joined")
    prefetch_related = ("social_accounts", "user_permissions", "groups__permissions")
    search_fields = ("email", "username", "display_name")
    filterset_fields = ("is_active", "is_staff", "is_superuser")
    note = "Deleting an account deactivates it; it can be restored. Only superusers can grant staff or moderator access."
    watch_new = True
    action_specs = (ActionSpec("verify-email", "Verify email", EmptyInput, quick=True, when={"email_verified_at": [None]},
                               help="Mark the email address as confirmed (e.g. after checking it with the fan)."),)

    def do_verify_email(self, instance, data):
        instance.email_verified_at = timezone.now()
        instance.save(update_fields=["email_verified_at"])

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise ValidationError({"detail": "You cannot delete your own account."})
        if instance.is_superuser and not self.request.user.is_superuser:
            raise PermissionDenied("Only superusers can delete a superuser account.")
        instance.soft_delete()

    def perform_restore(self, instance):
        instance.restore()
        instance.is_active = True
        instance.save(update_fields=["is_active"])


@register
class SocialAccountAdminViewSet(AdminViewSet):
    resource, label, group, model = "social-accounts", "Google sign-ins", ACCOUNTS, SocialAccount
    serializer_class = admin_serializer(SocialAccount, read_only=("user", "provider", "uid", "email", "email_verified",
                                                                  "extra_data", "last_used_at"))
    list_display = ("email", "user", "provider", "email_verified", "last_used_at")
    select_related = ("user",)
    search_fields = ("email", "user__email")
    filterset_fields = ("provider", "user")
    allow_create = False
    note = "Deleting unlinks the Google identity. Make sure the user still has a password first."


@register
class GuestSessionAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "guest-sessions", "Guest sessions", ACCOUNTS, GuestSession
    serializer_class = admin_serializer(GuestSession, fields=("id", "linked_user", "expires_at", "revoked_at",
                                                              "last_seen_at", "metadata", "created_at", "updated_at",
                                                              "deleted_at"))
    list_display = ("created_at", "linked_user", "expires_at", "revoked_at", "last_seen_at")
    select_related = ("linked_user",)
    action_specs = (ActionSpec("revoke", "Revoke session", EmptyInput, danger=True,
                               confirm="Revoke this guest session? Its token stops working immediately."),)

    def do_revoke(self, instance, data):
        instance.revoke()


# ===================== Teams =====================

@register
class TeamAdminViewSet(AdminViewSet):
    resource, label, group, model = "teams", "Teams", TEAMS, Team
    serializer_class = admin_serializer(Team)
    list_display = ("name", "short_name", "city", "primary_color", "is_active", "display_order")
    search_fields = ("name", "short_name", "city")
    filterset_fields = ("is_active", "city")
    note = "Unticking “active” hides a team from fans without losing its history."


@register
class PlayerAdminViewSet(AdminViewSet):
    resource, label, group, model = "players", "Players", TEAMS, Player
    serializer_class = admin_serializer(Player)
    list_display = ("full_name", "role", "nationality", "batting_style", "is_active")
    search_fields = ("full_name", "nationality")
    filterset_fields = ("role", "is_active", "nationality")


@register
class RosterAdminViewSet(AdminViewSet):
    resource, label, group, model = "rosters", "Squads", TEAMS, TeamRoster
    serializer_class = admin_serializer(TeamRoster)
    list_display = ("player", "team", "season_year", "jersey_number", "roster_role", "is_captain", "is_active")
    select_related = ("team", "player")
    search_fields = ("player__full_name", "team__name")
    filterset_fields = ("team", "player", "season_year", "roster_role", "is_captain", "is_active")


# ===================== Matches =====================

@register
class SeasonAdminViewSet(AdminViewSet):
    resource, label, group, model = "seasons", "Seasons", MATCHES, Season
    serializer_class = admin_serializer(Season)
    list_display = ("name", "year", "status", "starts_at", "ends_at")
    search_fields = ("name",)
    filterset_fields = ("status", "year")


@register
class MatchAdminViewSet(AdminViewSet):
    resource, label, group, model = "matches", "Matches", MATCHES, Match
    serializer_class = admin_serializer(Match, clean=True)
    list_display = ("starts_at", "home_team", "away_team", "season", "status", "winner", "venue")
    select_related = ("season", "home_team", "away_team", "toss_winner", "winner")
    search_fields = ("venue", "home_team__name", "away_team__name", "result_text")
    filterset_fields = ("season", "status", "home_team", "away_team")
    action_specs = (ActionSpec("score-predictions", "Score predictions", EmptyInput,
                               help="Award points for correct winner predictions. Safe to repeat."),)
    note = "Set status to completed and pick a winner before scoring predictions."

    def do_score_predictions(self, instance, data):
        scored = fan_services.score_match_predictions(instance)
        response = self.respond(instance)
        response.data["_message"] = f"Scored {scored} prediction(s)."
        return response


@register
class InningsAdminViewSet(AdminViewSet):
    resource, label, group, model = "innings", "Innings", MATCHES, MatchInnings
    serializer_class = admin_serializer(MatchInnings, clean=True)
    list_display = ("match", "innings_number", "batting_team", "runs", "wickets", "legal_balls", "is_complete")
    select_related = ("match__home_team", "match__away_team", "batting_team", "bowling_team")
    filterset_fields = ("match", "batting_team", "is_complete")


@register
class PerformanceAdminViewSet(AdminViewSet):
    resource, label, group, model = "performances", "Player stats", MATCHES, PlayerMatchPerformance
    serializer_class = admin_serializer(PlayerMatchPerformance, clean=True)
    list_display = ("player", "match", "team", "runs_scored", "balls_faced", "wickets_taken")
    select_related = ("player", "team", "match__home_team", "match__away_team")
    search_fields = ("player__full_name",)
    filterset_fields = ("match", "player", "team")


# ===================== Fan pages =====================

def _points():
    ledger = FanActivity.objects.filter(fan_profile=OuterRef("pk")).values("fan_profile")
    return Coalesce(Subquery(ledger.annotate(t=Sum("points_delta")).values("t"), output_field=IntegerField()), 0)


@register
class FanProfileAdminViewSet(AdminViewSet):
    resource, label, group, model = "fan-profiles", "Fan profiles", FANS, FanProfile
    serializer_class = s.AdminFanProfileSerializer
    list_display = ("nickname", "user", "current_team_label", "points", "fan_personality", "is_public", "created_at")
    select_related = ("user", "guest_session")
    search_fields = ("nickname", "user__email", "bio")
    filterset_fields = ("fan_personality", "card_theme", "is_public")
    allow_create = False
    action_specs = (
        ActionSpec("switch-team", "Change team", s.SwitchTeamInput,
                   help="Closes the current membership and opens a new one (recorded as an admin change)."),
        ActionSpec("adjust-points", "Adjust points", s.AdjustPointsInput,
                   help="Adds a manual adjustment row to the points ledger."),
        ActionSpec("award-badge", "Award badge", s.AwardBadgeInput),
    )
    note = "Fans create their own profiles. Deleting hides the profile; restore brings it back."
    watch_new = True

    def get_queryset(self):
        open_membership = TeamMembership.objects.filter(
            fan_profile=OuterRef("pk"), left_at__isnull=True, deleted_at__isnull=True
        )
        return super().get_queryset().annotate(
            points=_points(),
            current_team=Subquery(open_membership.values("team")[:1]),
            current_team_label=Subquery(open_membership.values("team__name")[:1]),
            post_count=Coalesce(Subquery(
                CommunityPost.all_objects.filter(author=OuterRef("pk")).values("author")
                .annotate(n=Count("id")).values("n"), output_field=IntegerField()), 0),
        )

    def do_switch_team(self, instance, data):
        fan_services.switch_team(instance, data["team"], source=TeamMembership.JoinSource.ADMIN)

    def do_adjust_points(self, instance, data):
        record_activity(
            instance, Activity.ADJUSTMENT, points=data["points"],
            metadata={"reason": data["reason"], "by": self.request.user.email},
        )

    def do_award_badge(self, instance, data):
        if award_badge(instance, data["badge"], reason=data.get("reason") or "Awarded by admin") is None:
            raise Conflict({"badge": "This fan already has that badge."})


@register
class MembershipAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "memberships", "Team memberships", FANS, TeamMembership
    serializer_class = admin_serializer(TeamMembership)
    list_display = ("fan_profile", "team", "joined_at", "left_at", "join_source")
    select_related = ("fan_profile", "team")
    search_fields = ("fan_profile__nickname",)
    filterset_fields = ("team", "fan_profile", "join_source")
    note = "History is kept. Change a fan's team from their profile."


@register
class ActivityAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "activities", "Points ledger", FANS, FanActivity
    serializer_class = s.AdminActivitySerializer
    list_display = ("occurred_at", "fan_profile", "activity_type", "points_delta", "team")
    select_related = ("fan_profile", "team")
    search_fields = ("fan_profile__nickname",)
    filterset_fields = ("activity_type", "fan_profile", "team")
    note = "Written by the app. Prefer “Adjust points” on a fan profile so every correction stays traceable."


@register
class BadgeAdminViewSet(AdminViewSet):
    resource, label, group, model = "badges", "Badges", FANS, Badge
    serializer_class = admin_serializer(Badge)
    list_display = ("name", "code", "rule_key", "icon_name", "is_active")
    search_fields = ("name", "code")
    filterset_fields = ("rule_key", "is_active")


@register
class FanBadgeAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "fan-badges", "Badges earned", FANS, FanBadge
    serializer_class = admin_serializer(FanBadge)
    list_display = ("fan_profile", "badge", "awarded_at", "reason")
    select_related = ("fan_profile", "badge")
    search_fields = ("fan_profile__nickname", "badge__name")
    filterset_fields = ("badge", "fan_profile")


@register
class PollAdminViewSet(AdminViewSet):
    resource, label, group, model = "polls", "Polls", FANS, Poll
    serializer_class = s.AdminPollSerializer
    list_display = ("question", "status", "opens_at", "closes_at", "team", "match")
    select_related = ("team", "match__home_team", "match__away_team", "created_by")
    search_fields = ("question",)
    filterset_fields = ("status", "team", "match", "results_visibility")
    note = "Options with votes can't be removed, so edit option text under Poll options if needed."

    def get_queryset(self):
        options = PollOption.all_objects.annotate(
            vote_count=Count("votes", filter=Q(votes__deleted_at__isnull=True))
        ).order_by("display_order", "created_at")
        return super().get_queryset().prefetch_related(Prefetch("options", queryset=options))


@register
class PollOptionAdminViewSet(AdminViewSet):
    resource, label, group, model = "poll-options", "Poll options", FANS, PollOption
    serializer_class = admin_serializer(PollOption)
    list_display = ("text", "poll", "display_order")
    select_related = ("poll",)
    search_fields = ("text", "poll__question")
    filterset_fields = ("poll",)


@register
class VoteAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "votes", "Poll votes", FANS, Vote
    serializer_class = admin_serializer(Vote)
    list_display = ("voted_at", "fan_profile", "poll", "option")
    select_related = ("fan_profile", "poll", "option")
    filterset_fields = ("poll", "option", "fan_profile")


@register
class PredictionAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "predictions", "Predictions", FANS, Prediction
    serializer_class = admin_serializer(Prediction)
    list_display = ("submitted_at", "fan_profile", "match", "predicted_winner", "points_awarded", "scored_at")
    select_related = ("fan_profile", "match__home_team", "match__away_team", "predicted_winner")
    filterset_fields = ("match", "fan_profile", "predicted_winner")


# ===================== Community =====================

@register
class PostAdminViewSet(AdminViewSet):
    resource, label, group, model = "posts", "Posts", CONTENT, CommunityPost
    serializer_class = s.AdminPostSerializer
    list_display = ("title", "author", "content_type", "status", "open_reports", "score", "published_at")
    select_related = ("author", "team", "match__home_team", "match__away_team")
    search_fields = ("title", "body", "author__nickname")
    filterset_fields = ("status", "content_type", "language", "team", "author", "is_ai_generated")
    allow_create = False
    attention, watch_new = Q(status=CommunityPost.Status.PENDING_REVIEW), True
    action_specs = (
        ActionSpec("verify", "Verify & publish", EmptyInput, quick=True,
                   when={"status": [CommunityPost.Status.PENDING_REVIEW]},
                   help="Publish this post. Recorded in the audit log like any moderation decision."),
        ActionSpec("reject", "Reject", s.ReasonInput, danger=True, quick=True,
                   when={"status": [CommunityPost.Status.PENDING_REVIEW]}, help="Tell the author why; it's audited."),
        ActionSpec("moderate", "Moderate", s.ModerateInput,
                   help="Approve, reject, hide, remove or restore. Every decision is audited."),
        ActionSpec("feature", "Feature in Meme Zone", EmptyInput, help="Pin to the featured strip."),
        ActionSpec("unfeature", "Unfeature", EmptyInput),
    )

    def do_feature(self, instance, data):
        if instance.status != CommunityPost.Status.PUBLISHED or instance.deleted_at:
            raise ValidationError({"detail": "Only published posts can be featured."})
        instance.featured_at = timezone.now()
        instance.save(update_fields=["featured_at", "updated_at"])

    def do_unfeature(self, instance, data):
        instance.featured_at = None
        instance.save(update_fields=["featured_at", "updated_at"])
    note = "Status changes go through “Moderate” so every decision lands in the audit log."

    def get_queryset(self):
        return super().get_queryset().annotate(
            open_reports=Count("reports", filter=Q(reports__status__in=["open", "under_review"],
                                                   reports__deleted_at__isnull=True), distinct=True),
            score=Coalesce(Subquery(
                ContentVote.objects.filter(post=OuterRef("pk")).values("post").annotate(
                    t=Sum(Case(When(vote_type="up", then=Value(1)), default=Value(-1), output_field=IntegerField()))
                ).values("t"), output_field=IntegerField()), 0),
        ).order_by("-created_at")  # aggregation drops Meta.ordering

    def _require_moderator(self):
        if not is_moderator(self.request.user):
            raise PermissionDenied("Moderator access is required. A superuser can grant it under Users.")

    def do_verify(self, instance, data):
        self._require_moderator()
        moderation_services.apply_action(instance, self.request.user, ModerationAction.ActionType.APPROVED,
                                         "Verified in the admin review queue.")

    def do_reject(self, instance, data):
        self._require_moderator()
        moderation_services.apply_action(instance, self.request.user, ModerationAction.ActionType.REJECTED,
                                         data["reason"])

    def do_moderate(self, instance, data):
        self._require_moderator()
        report = data.get("report")
        if report is not None and report.post_id != instance.pk:
            raise ValidationError({"report": "That report is about a different post."})
        moderation_services.apply_action(instance, self.request.user, data["action_type"], data["reason"], report)


@register
class ContentVoteAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "post-votes", "Post votes", CONTENT, ContentVote
    serializer_class = admin_serializer(ContentVote)
    list_display = ("voted_at", "fan_profile", "post", "vote_type")
    select_related = ("fan_profile", "post")
    filterset_fields = ("post", "fan_profile", "vote_type")


# ===================== Meme Zone =====================

@register
class MemeTemplateAdminViewSet(AdminViewSet):
    resource, label, group, model = "meme-templates", "Meme templates", MEMES, MemeTemplate
    serializer_class = admin_serializer(MemeTemplate, read_only=("image",))
    list_display = ("name", "slug", "category", "is_active")
    search_fields = ("name", "slug")
    filterset_fields = ("category", "is_active")


@register
class MemeDraftAdminViewSet(AdminViewSet):
    resource, label, group, model = "meme-drafts", "Meme drafts", MEMES, MemeDraft
    serializer_class = admin_serializer(MemeDraft, read_only=("fan_profile", "generation_request", "status",
                                                              "published_post", "rendered_image"))
    list_display = ("caption", "fan_profile", "template", "status", "created_at")
    select_related = ("fan_profile", "template", "team", "generation_request", "published_post",
                      "match__home_team", "match__away_team")
    search_fields = ("caption", "fan_profile__nickname")
    filterset_fields = ("status", "template", "fan_profile", "team")
    allow_create = False
    note = "A submitted meme becomes a community post; moderate it under Posts and the draft status follows."


@register
class MemeContestAdminViewSet(AdminViewSet):
    resource, label, group, model = "meme-contests", "Meme contests", MEMES, MemeContest
    serializer_class = admin_serializer(MemeContest, read_only=("winner", "finalized_at", "created_by"))
    list_display = ("title", "status", "match", "team", "submissions_open_at", "voting_close_at", "winner")
    select_related = ("match__home_team", "match__away_team", "team", "winner__post")
    search_fields = ("title",)
    filterset_fields = ("status", "match", "team")
    action_specs = (
        ActionSpec("publish", "Publish", EmptyInput, help="Make the contest visible to fans.", quick=True,
                   when={"status": [MemeContest.Status.DRAFT]}),
        ActionSpec("finalize", "Finalize results", EmptyInput,
                   help="After voting closes: rank entries by counted votes (ties: earlier entry) and award the winner.",
                   confirm="Finalize this contest? Results can't be changed afterwards."),
        ActionSpec("cancel", "Cancel contest", EmptyInput, danger=True, confirm="Cancel this contest for everyone?"),
    )
    note = ("Exclude suspicious votes under Contest votes before finalizing. "
            "`manage.py create_match_meme_contests` creates one draft contest per fixture.")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def do_publish(self, instance, data):
        instance.status = MemeContest.Status.PUBLISHED
        instance.save(update_fields=["status", "updated_at"])

    def do_finalize(self, instance, data):
        contest = meme_services.finalize_contest(instance)
        response = self.respond(contest)
        response.data["_message"] = (f"Winner: {contest.winner.post}" if contest.winner_id
                                     else "Finalized with no votes, so there is no winner.")
        return response

    def do_cancel(self, instance, data):
        instance.status = MemeContest.Status.CANCELLED
        instance.save(update_fields=["status", "updated_at"])


@register
class ContestEntryAdminViewSet(AdminViewSet):
    resource, label, group, model = "contest-entries", "Contest entries", MEMES, ContestEntry
    serializer_class = admin_serializer(ContestEntry, read_only=("contest", "post", "fan_profile", "final_votes",
                                                                 "final_rank"))
    list_display = ("post", "contest", "fan_profile", "status", "final_votes", "final_rank", "created_at")
    select_related = ("contest", "post", "fan_profile")
    filterset_fields = ("contest", "status", "fan_profile")
    allow_create = False
    attention, watch_new = Q(status=ContestEntry.Status.PENDING), True
    action_specs = (
        ActionSpec("approve", "Approve entry", EmptyInput, quick=True, when={"status": [ContestEntry.Status.PENDING]}),
        ActionSpec("reject", "Reject entry", s.ReasonInput, danger=True, quick=True,
                   when={"status": [ContestEntry.Status.PENDING]}),
    )

    def do_approve(self, instance, data):
        instance.status, instance.review_note = ContestEntry.Status.APPROVED, ""
        instance.save(update_fields=["status", "review_note", "updated_at"])

    def do_reject(self, instance, data):
        instance.status, instance.review_note = ContestEntry.Status.REJECTED, data["reason"][:255]
        instance.save(update_fields=["status", "review_note", "updated_at"])


@register
class ContestVoteAdminViewSet(AdminViewSet):
    resource, label, group, model = "contest-votes", "Contest votes", MEMES, ContestVote
    serializer_class = admin_serializer(ContestVote, read_only=("contest", "entry", "fan_profile", "client_hash"))
    list_display = ("created_at", "contest", "entry", "fan_profile", "flag_reason", "is_excluded")
    select_related = ("contest", "entry__post", "fan_profile")
    filterset_fields = ("contest", "is_excluded", "client_hash")
    search_fields = ("flag_reason", "fan_profile__nickname")
    allow_create = False
    note = "Votes with a flag reason look suspicious (new account, shared network). Tick “Is excluded” to stop one counting."


@register
class MemeUploadAdminViewSet(AdminViewSet):
    resource, label, group, model = "meme-uploads", "Meme uploads", MEMES, MemeUpload
    serializer_class = admin_serializer(MemeUpload, fields=("id", "fan_profile", "width", "height", "size_bytes",
                                                            "sha256", "created_at", "updated_at", "deleted_at"),
                                        read_only=("fan_profile", "width", "height", "size_bytes", "sha256"))
    list_display = ("created_at", "fan_profile", "width", "height", "size_bytes")
    select_related = ("fan_profile",)
    filterset_fields = ("fan_profile", "sha256")
    allow_create = False


@register
class CommentAdminViewSet(AdminViewSet):
    resource, label, group, model = "comments", "Comments", CONTENT, PostComment
    serializer_class = admin_serializer(PostComment, read_only=("post", "author", "parent"))
    list_display = ("created_at", "author", "post", "body", "is_hidden")
    select_related = ("author", "post")
    search_fields = ("body", "author__nickname")
    filterset_fields = ("post", "author", "is_hidden")
    allow_create = False
    note = "Tick “Is hidden” and give a reason to hide a comment; the thread keeps a placeholder."
    watch_new = True


@register
class ReactionAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "reactions", "Reactions", CONTENT, PostReaction
    serializer_class = admin_serializer(PostReaction)
    list_display = ("created_at", "fan_profile", "post", "kind")
    select_related = ("fan_profile", "post")
    filterset_fields = ("post", "fan_profile", "kind")


@register
class MemeRequestAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "meme-requests", "Caption requests", MEMES, MemeGenerationRequest
    serializer_class = admin_serializer(MemeGenerationRequest)
    list_display = ("created_at", "fan_profile", "topic", "style", "status", "provider")
    select_related = ("fan_profile", "team", "match__home_team", "match__away_team")
    search_fields = ("topic", "fan_profile__nickname")
    filterset_fields = ("status", "style", "language", "provider")


# ===================== Moderation =====================

@register
class ReportAdminViewSet(AdminViewSet):
    resource, label, group, model = "reports", "Reports", MODERATION, ModerationReport
    serializer_class = s.AdminReportSerializer
    list_display = ("created_at", "post", "reason", "status", "reporter", "assigned_to")
    select_related = ("post", "reporter", "assigned_to")
    search_fields = ("description", "post__title", "post__body")
    filterset_fields = ("status", "reason", "assigned_to", "post")
    allow_create = False
    note = "To act on the reported post, open it under Posts → Moderate and pick this report."
    attention, watch_new = Q(status__in=[ModerationReport.Status.OPEN, ModerationReport.Status.UNDER_REVIEW]), True
    _open = {"status": [ModerationReport.Status.OPEN, ModerationReport.Status.UNDER_REVIEW]}
    action_specs = (
        ActionSpec("resolve", "Resolve", s.ReasonInput, quick=True, when=_open,
                   help="The post was dealt with. Your note is kept with the report."),
        ActionSpec("dismiss", "Dismiss", s.ReasonInput, quick=True, when=_open,
                   help="Nothing wrong with the post. Your note is kept with the report."),
    )

    def _close(self, instance, status, note):
        instance.status, instance.resolution_note, instance.resolved_at = status, note, timezone.now()
        instance.save(update_fields=["status", "resolution_note", "resolved_at", "updated_at"])

    def do_resolve(self, instance, data):
        self._close(instance, ModerationReport.Status.RESOLVED, data["reason"])

    def do_dismiss(self, instance, data):
        self._close(instance, ModerationReport.Status.DISMISSED, data["reason"])


@register
class ModerationActionAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "moderation-actions", "Audit log", MODERATION, ModerationAction
    serializer_class = admin_serializer(ModerationAction)
    list_display = ("created_at", "action_type", "post", "moderator", "previous_status", "new_status")
    select_related = ("post", "moderator")
    search_fields = ("reason",)
    filterset_fields = ("action_type", "moderator", "post")


# ===================== AI agents =====================

@register
class AgentRunAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "agent-runs", "Agent runs", AI, AgentRun
    serializer_class = admin_serializer(AgentRun)
    list_display = ("created_at", "workflow_name", "status", "provider", "model_name", "requested_by")
    select_related = ("requested_by", "fan_profile", "team", "match__home_team", "match__away_team")
    filterset_fields = ("workflow_name", "status", "provider")


@register
class ToolCallAdminViewSet(ReadOnly, AdminViewSet):
    resource, label, group, model = "tool-calls", "Agent tool calls", AI, AgentToolCall
    serializer_class = admin_serializer(AgentToolCall)
    list_display = ("created_at", "tool_name", "agent_run", "attempt_number", "status")
    select_related = ("agent_run",)
    search_fields = ("tool_name",)
    filterset_fields = ("agent_run", "status", "tool_name")


# ===================== Index and dashboard =====================

@extend_schema(tags=["admin"])
class ResourceIndexView(APIView):
    """Every manageable resource, grouped for the console's navigation."""

    permission_classes = [IsAdminStaff]

    def get(self, request):
        user = request.user
        return Response({
            "me": {"id": str(user.pk), "email": user.email, "is_superuser": user.is_superuser,
                   "is_moderator": is_moderator(user)},
            "resources": [v.describe() for v in REGISTRY],
        })


FIRST_VISIT_WINDOW = timedelta(days=7)  # before a staff member's first visit, "new" means the last week


@extend_schema(tags=["admin"])
class AttentionView(APIView):
    """
    Red badge counts for the console nav, per resource: ``pending`` = rows waiting in a review
    queue; ``new`` = rows created since *you* last opened that section. POST ``{"resource": key}``
    when a section is opened to reset its ``new`` count.
    """

    permission_classes = [IsAdminStaff]

    def get(self, request):
        seen = dict(SeenMarker.objects.filter(user=request.user).values_list("resource", "seen_at"))
        default_since = timezone.now() - FIRST_VISIT_WINDOW
        counts = {}
        for view in REGISTRY:
            if view.attention is None and not view.watch_new:
                continue
            alive = view.model.objects.all()  # default manager: not soft-deleted
            entry = {}
            if view.attention is not None:
                entry["pending"] = alive.filter(view.attention).count()
            if view.watch_new:
                stamp = "date_joined" if view.model is User else "created_at"
                entry["new"] = alive.filter(**{f"{stamp}__gt": seen.get(view.resource, default_since)}).count()
            counts[view.resource] = entry
        return Response(counts)

    def post(self, request):
        resource = request.data.get("resource")
        if resource not in {v.resource for v in REGISTRY}:
            raise ValidationError({"resource": "Unknown section."})
        SeenMarker.objects.update_or_create(user=request.user, resource=resource,
                                            defaults={"seen_at": timezone.now()})
        return Response(status=204)


@extend_schema(tags=["admin"])
class DashboardView(APIView):
    """Headline numbers and work queues for the console's home page."""

    permission_classes = [IsAdminStaff]

    def get(self, request):
        now = timezone.now()
        week = now - timedelta(days=7)
        posts = CommunityPost.objects.all()
        members = count_by(TeamMembership.objects.filter(left_at__isnull=True, fan_profile__deleted_at__isnull=True),
                           "team")
        teams = [
            {"id": str(t.pk), "name": t.name, "short_name": t.short_name, "primary_color": t.primary_color,
             "members": members.get(t.pk, 0)}
            for t in Team.objects.filter(is_active=True)
        ]
        teams.sort(key=lambda t: -t["members"])
        return Response({
            "totals": {
                "users": User.objects.count(),
                "users_new_7d": User.objects.filter(date_joined__gte=week).count(),
                "staff": User.objects.filter(is_staff=True).count(),
                "fans": FanProfile.objects.count(),
                "teams": Team.objects.filter(is_active=True).count(),
                "players": Player.objects.filter(is_active=True).count(),
                "matches_upcoming": Match.objects.filter(status=Match.Status.SCHEDULED, starts_at__gte=now).count(),
                "matches_live": Match.objects.filter(status=Match.Status.LIVE).count(),
                "posts_published": posts.filter(status=CommunityPost.Status.PUBLISHED).count(),
                "posts_pending": posts.filter(status=CommunityPost.Status.PENDING_REVIEW).count(),
                "reports_open": ModerationReport.objects.filter(status__in=["open", "under_review"]).count(),
                "memes_drafts": MemeDraft.objects.count(),
                "memes_7d": MemeGenerationRequest.objects.filter(created_at__gte=week).count(),
                "polls_open": Poll.objects.filter(status=Poll.Status.OPEN).count(),
                "predictions": Prediction.objects.count(),
                "points_7d": FanActivity.objects.filter(occurred_at__gte=week)
                .aggregate(t=Coalesce(Sum("points_delta"), 0))["t"],
            },
            "teams": teams,
            "pending_posts": [
                {"id": str(p.pk), "title": p.title or p.body[:80], "author": str(p.author),
                 "content_type": p.content_type, "created_at": p.created_at}
                for p in posts.filter(status=CommunityPost.Status.PENDING_REVIEW).select_related("author")
                .order_by("created_at")[:6]
            ],
            "open_reports": [
                {"id": str(r.pk), "reason": r.get_reason_display(), "post": str(r.post), "created_at": r.created_at}
                for r in ModerationReport.objects.filter(status__in=["open", "under_review"]).select_related("post")
                .order_by("created_at")[:6]
            ],
            "recent_users": [
                {"id": str(u.pk), "email": u.email, "display_name": u.display_name, "date_joined": u.date_joined}
                for u in User.objects.order_by("-date_joined")[:6]
            ],
        })
