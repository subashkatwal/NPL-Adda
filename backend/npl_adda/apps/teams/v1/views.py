from django.db.models import Max
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics

from apps.common.permissions import IsStaffOrReadOnly
from apps.common.viewsets import SoftDeleteModelViewSet

from ..models import Player, Team, TeamRoster
from .serializers import PlayerSerializer, TeamRosterSerializer, TeamSerializer


class StaffSeesInactiveMixin:
    """Non-staff only see rows flagged ``is_active``."""

    def get_queryset(self):
        qs = super().get_queryset()
        return qs if self.request.user.is_staff else qs.filter(is_active=True)


@extend_schema_view(**{a: extend_schema(tags=["teams"]) for a in
                       ("list", "create", "retrieve", "update", "partial_update", "destroy")})
class TeamViewSet(StaffSeesInactiveMixin, SoftDeleteModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [IsStaffOrReadOnly]
    filterset_fields = ("city", "is_active")
    search_fields = ("name", "short_name", "city")
    ordering_fields = ("display_order", "name")


@extend_schema_view(**{a: extend_schema(tags=["players"]) for a in
                       ("list", "create", "retrieve", "update", "partial_update", "destroy")})
class PlayerViewSet(StaffSeesInactiveMixin, SoftDeleteModelViewSet):
    queryset = Player.objects.all()
    serializer_class = PlayerSerializer
    permission_classes = [IsStaffOrReadOnly]
    filterset_fields = ("role", "nationality", "is_active")
    search_fields = ("full_name",)
    ordering_fields = ("full_name",)


@extend_schema_view(**{a: extend_schema(tags=["rosters"]) for a in
                       ("list", "create", "retrieve", "update", "partial_update", "destroy")})
class TeamRosterViewSet(SoftDeleteModelViewSet):
    queryset = TeamRoster.objects.select_related("team", "player")
    serializer_class = TeamRosterSerializer
    permission_classes = [IsStaffOrReadOnly]
    filterset_fields = ("team", "player", "season_year", "roster_role", "is_active", "is_captain")


@extend_schema(
    tags=["teams"],
    parameters=[OpenApiParameter("season_year", int, description="Defaults to the latest season on record.")],
)
class TeamRosterListView(generics.ListAPIView):
    """Active squad for one team and season."""

    serializer_class = TeamRosterSerializer
    pagination_class = None
    filter_backends = []

    def get_queryset(self):
        team = generics.get_object_or_404(Team.objects.filter(is_active=True), pk=self.kwargs["pk"])
        rosters = TeamRoster.objects.filter(team=team, is_active=True).select_related("player", "team")
        season = self.request.query_params.get("season_year") or rosters.aggregate(m=Max("season_year"))["m"]
        return rosters.filter(season_year=season).order_by("-is_captain", "player__full_name")
