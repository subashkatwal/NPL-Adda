import django_filters
from django.db.models import Prefetch, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.common.permissions import IsStaffOrReadOnly
from apps.common.viewsets import SoftDeleteModelViewSet

from ..models import Match, MatchInnings, PlayerMatchPerformance, Season
from .serializers import MatchInningsSerializer, MatchSerializer, PlayerMatchPerformanceSerializer, SeasonSerializer

ACTIONS = ("list", "create", "retrieve", "update", "partial_update", "destroy")


def tagged(tag):
    return extend_schema_view(**{a: extend_schema(tags=[tag]) for a in ACTIONS})


class MatchFilter(django_filters.FilterSet):
    team = django_filters.UUIDFilter(method="filter_team", label="Home or away team UUID")
    starts_after = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="gte")
    starts_before = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="lt")

    class Meta:
        model = Match
        fields = ("season", "status")

    def filter_team(self, queryset, name, value):
        return queryset.filter(Q(home_team_id=value) | Q(away_team_id=value))


@tagged("matches")
class MatchViewSet(SoftDeleteModelViewSet):
    queryset = Match.objects.select_related("season", "home_team", "away_team").prefetch_related(
        Prefetch("innings", queryset=MatchInnings.objects.order_by("innings_number"))
    )
    serializer_class = MatchSerializer
    permission_classes = [IsStaffOrReadOnly]
    filterset_class = MatchFilter
    ordering_fields = ("starts_at", "match_number")
    search_fields = ("venue",)


@tagged("seasons")
class SeasonViewSet(SoftDeleteModelViewSet):
    queryset = Season.objects.all()
    serializer_class = SeasonSerializer
    permission_classes = [IsStaffOrReadOnly]
    filterset_fields = ("status", "year")


@tagged("innings")
class MatchInningsViewSet(SoftDeleteModelViewSet):
    queryset = MatchInnings.objects.all()
    serializer_class = MatchInningsSerializer
    permission_classes = [IsStaffOrReadOnly]
    filterset_fields = ("match", "batting_team")


@tagged("performances")
class PerformanceViewSet(SoftDeleteModelViewSet):
    queryset = PlayerMatchPerformance.objects.select_related("player")
    serializer_class = PlayerMatchPerformanceSerializer
    permission_classes = [IsStaffOrReadOnly]
    filterset_fields = ("match", "player", "team")


@extend_schema_view(get=extend_schema(tags=["matches"], operation_id="v1_matches_player_statistics"))
class MatchPerformanceListView(generics.ListAPIView):
    """Stored player statistics for one match."""

    serializer_class = PlayerMatchPerformanceSerializer
    pagination_class = None
    filter_backends = []

    def get_queryset(self):
        match = generics.get_object_or_404(Match, pk=self.kwargs["pk"])
        return PlayerMatchPerformance.objects.filter(match=match).select_related("player")
