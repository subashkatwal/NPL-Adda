from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, F, OuterRef, Prefetch, Q, Subquery, Sum, Window
from django.db.models.functions import Coalesce, DenseRank
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.cache import cached
from apps.common.permissions import IsStaffOrReadOnly
from apps.matches.models import Match, Season
from apps.memelab.imaging import ImageRejected
from apps.memelab.throttles import FanRateThrottle

from .. import card, services, stats
from ..identity import HasFanIdentity, HasFanProfile, get_fan_profile
from ..rewards import BADGE_TARGETS, activity_counts, badge_progress
from ..models import Badge, FanActivity, FanProfile, Poll, PollOption, Prediction, TeamMembership, Vote

ACTIVE_MEMBERSHIP = Prefetch(
    "memberships", queryset=TeamMembership.objects.filter(left_at__isnull=True).select_related("team"),
    to_attr="active_memberships",
)
from .serializers import (
    AvatarUploadSerializer,
    BadgeSerializer,
    FanCardSerializer,
    ChallengeSerializer,
    FanActivitySerializer,
    FanBadgeSerializer,
    FanProfileCreateSerializer,
    FanProfileSerializer,
    JoinTeamSerializer,
    LeaderboardEntrySerializer,
    PollResultsSerializer,
    PollSerializer,
    PredictionSerializer,
    PredictionSummarySerializer,
    ScoreResultSerializer,
    SeasonSummarySerializer,
    TeamLeaderboardEntrySerializer,
    TeamMembershipSerializer,
    VoteSerializer,
)

TAGS = ["fanpage"]


def tagged(*actions, tag="fanpage"):
    return extend_schema_view(**{a: extend_schema(tags=[tag]) for a in actions})


@tagged("list", "create", "retrieve", "partial_update", "destroy")
class FanProfileViewSet(viewsets.ModelViewSet):
    """Public profiles are readable by anyone; only the owner may edit or delete (soft) their profile."""

    serializer_class = FanProfileSerializer
    http_method_names = ["get", "post", "patch", "delete"]
    search_fields = ("nickname",)
    filterset_fields = ("fan_personality",)

    def get_queryset(self):
        profile = get_fan_profile(self.request)
        visible = Q(is_public=True) | (Q(pk=profile.pk) if profile else Q(pk=None))
        return FanProfile.objects.filter(visible).prefetch_related(ACTIVE_MEMBERSHIP)  # current team in 1 query

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return []
        if self.action == "create":
            return [HasFanIdentity()]
        return [HasFanProfile()]

    def get_serializer_class(self):
        return FanProfileCreateSerializer if self.action == "create" else FanProfileSerializer

    def get_object(self):
        obj = super().get_object()
        if self.action in ("partial_update", "destroy") and obj != get_fan_profile(self.request):
            raise PermissionDenied("You can only change your own profile.")
        return obj

    @transaction.atomic
    def perform_create(self, serializer):
        if get_fan_profile(self.request):
            raise services.Conflict({"detail": "You already have a fan profile."})
        team = serializer.validated_data.pop("team", None)
        try:
            with transaction.atomic():
                profile = serializer.save(user=self.request.user, guest_session=None)
        except IntegrityError:
            raise services.Conflict({"detail": "You already have a fan profile."})
        self.request._fan_profile = profile
        if team:
            services.switch_team(profile, team, source=TeamMembership.JoinSource.ONBOARDING)

    def perform_destroy(self, instance):
        instance.soft_delete()


@extend_schema(tags=TAGS)
class MyProfileView(APIView):
    permission_classes = [HasFanProfile]

    @extend_schema(responses=FanProfileSerializer)
    def get(self, request):
        return Response(FanProfileSerializer(get_fan_profile(request), context={"request": request}).data)


class AvatarUploadThrottle(FanRateThrottle):
    scope = "avatar_upload"


@extend_schema(tags=TAGS, responses=FanCardSerializer)
class MyCardView(APIView):
    """Your fan card with everything on it, plus the privacy switches that control the public version."""

    permission_classes = [HasFanProfile]

    def get(self, request):
        return Response(card.build_card(get_fan_profile(request), owner=True))


@extend_schema(tags=TAGS, responses=FanCardSerializer)
class FanCardView(APIView):
    """A fan's public card: only what they chose to show. Private profiles are not found (404)."""

    permission_classes = []

    def get(self, request, pk):
        viewer = get_fan_profile(request)
        profile = generics.get_object_or_404(FanProfile, pk=pk)
        owner = bool(viewer and viewer.pk == profile.pk)
        if not (profile.is_public or owner):
            raise NotFound("This fan card is private.")
        return Response(card.build_card(profile, owner=owner))


@extend_schema(tags=TAGS)
class MyAvatarView(APIView):
    """POST a photo to use as your avatar (validated, cropped, metadata stripped); DELETE removes it."""

    permission_classes = [HasFanProfile]
    parser_classes = [MultiPartParser, FormParser]

    def get_throttles(self):
        return [AvatarUploadThrottle()] if self.request.method == "POST" else []

    @extend_schema(request={"multipart/form-data": AvatarUploadSerializer}, responses={200: FanProfileSerializer})
    def post(self, request):
        file_obj = request.FILES.get("image")
        if file_obj is None:
            raise ValidationError({"image": "Choose an image to upload."})
        try:
            content = card.store_avatar(file_obj)
        except ImageRejected as exc:
            raise ValidationError({"image": exc.message})
        profile = get_fan_profile(request)
        old = profile.avatar.name if profile.avatar else None
        profile.avatar.save(content.name, content, save=False)
        profile.save(update_fields=["avatar", "updated_at"])
        if old:
            profile.avatar.storage.delete(old)
        return Response(FanProfileSerializer(profile, context={"request": request}).data)

    @extend_schema(responses={200: FanProfileSerializer})
    def delete(self, request):
        profile = get_fan_profile(request)
        if profile.avatar:
            profile.avatar.delete(save=False)
            profile.avatar = ""
            profile.save(update_fields=["avatar", "updated_at"])
        return Response(FanProfileSerializer(profile, context={"request": request}).data)


@extend_schema(tags=TAGS)
class MyMembershipView(APIView):
    """GET the current team; POST to join or switch team (the old membership is closed, never deleted)."""

    permission_classes = [HasFanProfile]

    @extend_schema(responses=TeamMembershipSerializer)
    def get(self, request):
        membership = get_fan_profile(request).current_membership
        if membership is None:
            raise NotFound("You have not joined a team yet.")
        return Response(TeamMembershipSerializer(membership).data)

    @extend_schema(request=JoinTeamSerializer, responses={200: TeamMembershipSerializer, 201: TeamMembershipSerializer})
    def post(self, request):
        serializer = JoinTeamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_fan_profile(request)
        source = TeamMembership.JoinSource.SWITCH if profile.current_membership else TeamMembership.JoinSource.ONBOARDING
        membership, created = services.switch_team(profile, serializer.validated_data["team"], source=source)
        return Response(TeamMembershipSerializer(membership).data, status=201 if created else 200)


@extend_schema(tags=TAGS)
class MyMembershipHistoryView(generics.ListAPIView):
    serializer_class = TeamMembershipSerializer
    permission_classes = [HasFanProfile]
    filter_backends = []

    def get_queryset(self):
        return get_fan_profile(self.request).memberships.select_related("team")


@extend_schema(tags=TAGS)
class MyActivityView(generics.ListAPIView):
    """Your points ledger. Points are only ever written by the server."""

    serializer_class = FanActivitySerializer
    permission_classes = [HasFanProfile]
    filterset_fields = ("activity_type",)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return FanActivity.objects.none()
        return get_fan_profile(self.request).activities.all()


@extend_schema(tags=TAGS)
class MyBadgesView(generics.ListAPIView):
    serializer_class = FanBadgeSerializer
    permission_classes = [HasFanProfile]
    pagination_class = None
    filter_backends = []

    def get_queryset(self):
        return get_fan_profile(self.request).badges.select_related("badge")


@extend_schema(tags=TAGS)
class BadgeListView(generics.ListAPIView):
    queryset = Badge.objects.filter(is_active=True)
    serializer_class = BadgeSerializer
    pagination_class = None
    filter_backends = []
    permission_classes = []


SEASON_PARAM = OpenApiParameter("season", str, description="Season UUID; defaults to all-time (fans) or the active season.")


def season_from(request, default_to_active=False):
    season_id = request.query_params.get("season")
    if season_id:
        return generics.get_object_or_404(Season, pk=season_id)
    return stats.default_season() if default_to_active else None


@extend_schema(tags=TAGS, parameters=[OpenApiParameter("team", str, description="Current team UUID"), SEASON_PARAM])
class LeaderboardView(generics.ListAPIView):
    """Public profiles ranked (dense rank) by the sum of their ledger points, all-time or for one season."""

    serializer_class = LeaderboardEntrySerializer
    permission_classes = []
    filter_backends = []

    def get_queryset(self):
        qs = FanProfile.objects.filter(is_public=True)
        if team := self.request.query_params.get("team"):
            qs = qs.filter(memberships__team_id=team, memberships__left_at__isnull=True,
                           memberships__deleted_at__isnull=True)
        in_window = Q()
        if season := season_from(self.request):
            start, end = stats.season_window(season)
            in_window = Q(activities__occurred_at__gte=start, activities__occurred_at__lt=end)
        qs = qs.annotate(points=Coalesce(Sum("activities__points_delta", filter=in_window), 0))
        if season:  # levels are always all-time; the season total alone would understate them
            qs = qs.annotate(total_points=card.points_subquery())
        return qs.annotate(rank=Window(DenseRank(), order_by=F("points").desc())).order_by("-points", "created_at")

    def list(self, request, *args, **kwargs):
        # Same answer for every caller, so cache the whole page briefly (key = full query string).
        key = f"lb:fans:{request.get_full_path()}"
        data = cached(key, settings.LEADERBOARD_CACHE_SECONDS, lambda: super(LeaderboardView, self).list(request).data)
        return Response(data)


@extend_schema(tags=TAGS, parameters=[SEASON_PARAM], responses=TeamLeaderboardEntrySerializer(many=True))
class TeamLeaderboardView(APIView):
    """Team participation ranking: points fans earned while backing each team, and current members."""

    permission_classes = []

    def get(self, request):
        season = season_from(request)
        data = cached(
            f"lb:teams:{season.pk if season else 'all'}", settings.LEADERBOARD_CACHE_SECONDS,
            lambda: TeamLeaderboardEntrySerializer(stats.team_leaderboard(season), many=True).data,
        )
        return Response(data)


@extend_schema(tags=TAGS, parameters=[SEASON_PARAM], responses=SeasonSummarySerializer)
class MySeasonSummaryView(APIView):
    """Your activity for one season (default: the active season)."""

    permission_classes = [HasFanProfile]

    def get(self, request):
        summary = stats.season_summary(get_fan_profile(request), season_from(request, default_to_active=True))
        return Response(SeasonSummarySerializer(summary).data)


@extend_schema(tags=TAGS, responses=ChallengeSerializer(many=True))
class MyChallengesView(APIView):
    """Fan challenges: progress towards each active badge, computed from your ledger."""

    permission_classes = [HasFanProfile]

    def get(self, request):
        profile = get_fan_profile(request)
        awarded = dict(profile.badges.values_list("badge_id", "awarded_at"))
        counts = activity_counts(profile)
        rows = []
        for badge in Badge.objects.filter(is_active=True, rule_key__in=BADGE_TARGETS).order_by("name"):
            current, target = badge_progress(counts, badge.rule_key)
            rows.append({"badge": badge, "current": current, "target": target,
                         "completed": badge.pk in awarded, "awarded_at": awarded.get(badge.pk)})
        return Response(ChallengeSerializer(rows, many=True).data)


@extend_schema(tags=["predictions"], responses=PredictionSummarySerializer)
class PredictionSummaryView(APIView):
    """How fans predicted a match. Hidden until predictions close so the split can't sway picks."""

    permission_classes = []

    def get(self, request, pk):
        match = generics.get_object_or_404(Match.objects.select_related("home_team", "away_team"), pk=pk)
        if match.status == Match.Status.SCHEDULED and timezone.now() < match.prediction_deadline:
            raise PermissionDenied("The prediction split is shown after predictions close.")
        counts = dict(
            match.predictions.values_list("predicted_winner").annotate(n=Count("id")).values_list("predicted_winner", "n")
        )
        split = [{"team": t.pk, "name": t.name, "count": counts.get(t.pk, 0)} for t in (match.home_team, match.away_team)]
        return Response({"match": match.pk, "total": sum(s["count"] for s in split), "split": split})


@tagged("list", "create", "retrieve", "partial_update", "destroy", tag="polls")
class PollViewSet(viewsets.ModelViewSet):
    serializer_class = PollSerializer
    permission_classes = [IsStaffOrReadOnly]
    http_method_names = ["get", "post", "patch", "delete"]
    filterset_fields = ("status", "team", "match")

    def get_queryset(self):
        # Vote counts and the caller's own vote are loaded with the page, not one query per poll.
        options = Prefetch("options", queryset=PollOption.objects.annotate(
            vote_count=Count("votes", filter=Q(votes__deleted_at__isnull=True))).order_by("display_order", "created_at"))
        qs = Poll.objects.prefetch_related(options)
        if profile := get_fan_profile(self.request):
            mine = Vote.objects.filter(poll=OuterRef("pk"), fan_profile=profile).values("option_id")[:1]
            qs = qs.annotate(my_vote_id=Subquery(mine))
        return qs if self.request.user.is_staff else qs.exclude(status=Poll.Status.DRAFT)

    def perform_destroy(self, instance):
        instance.soft_delete()


@extend_schema(tags=["polls"])
class PollVoteView(APIView):
    permission_classes = [HasFanProfile]

    @extend_schema(request=VoteSerializer, responses={201: PollResultsSerializer})
    def post(self, request, pk):
        poll = generics.get_object_or_404(Poll.objects.exclude(status=Poll.Status.DRAFT), pk=pk)
        serializer = VoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        option = poll.options.filter(pk=serializer.validated_data["option"]).first()
        if option is None:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"option": "Option does not belong to this poll."})
        services.cast_vote(get_fan_profile(request), poll, option)
        return Response(PollResultsSerializer.build(poll), status=status.HTTP_201_CREATED)


@extend_schema(tags=["polls"])
class PollResultsView(APIView):
    permission_classes = []

    @extend_schema(responses=PollResultsSerializer)
    def get(self, request, pk):
        poll = generics.get_object_or_404(Poll.objects.exclude(status=Poll.Status.DRAFT), pk=pk)
        if not PollResultsSerializer.can_view(poll, request, get_fan_profile(request)):
            raise PermissionDenied("Results are not visible yet.")
        return Response(PollResultsSerializer.build(poll))


@tagged("list", "create", "retrieve", tag="predictions")
class PredictionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    """Your own predictions. POST creates or changes the prediction for a match until its deadline."""

    serializer_class = PredictionSerializer
    permission_classes = [HasFanProfile]
    filterset_fields = ("match",)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Prediction.objects.none()
        return get_fan_profile(self.request).predictions.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prediction = services.submit_prediction(
            get_fan_profile(request), serializer.validated_data["match"], serializer.validated_data["predicted_winner"]
        )
        return Response(self.get_serializer(prediction).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["predictions"])
class ScorePredictionsView(APIView):
    """Staff only: score predictions for a completed match. Re-running is safe."""

    permission_classes = [IsAdminUser]

    @extend_schema(request=None, responses=ScoreResultSerializer)
    def post(self, request, pk):
        match = generics.get_object_or_404(Match, pk=pk)
        return Response({"scored": services.score_match_predictions(match)})
