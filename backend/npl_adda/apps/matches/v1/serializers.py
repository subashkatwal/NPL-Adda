from rest_framework import serializers

from apps.common.viewsets import ModelCleanMixin
from apps.teams.v1.serializers import TeamSerializer

from ..models import Match, MatchInnings, PlayerMatchPerformance, Season

BASE_READ_ONLY = ("id", "created_at", "updated_at")


class SeasonSerializer(ModelCleanMixin, serializers.ModelSerializer):
    class Meta:
        model = Season
        exclude = ("deleted_at",)
        read_only_fields = BASE_READ_ONLY
        validators = []


class MatchInningsSerializer(ModelCleanMixin, serializers.ModelSerializer):
    overs = serializers.CharField(read_only=True, help_text="Derived from legal balls, e.g. '18.4'.")
    run_rate = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True, allow_null=True)
    required_run_rate = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True, allow_null=True)

    class Meta:
        model = MatchInnings
        exclude = ("deleted_at",)
        read_only_fields = BASE_READ_ONLY
        validators = []


class PlayerMatchPerformanceSerializer(ModelCleanMixin, serializers.ModelSerializer):
    player_name = serializers.CharField(source="player.full_name", read_only=True)
    strike_rate = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True, allow_null=True)
    economy = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True, allow_null=True)

    class Meta:
        model = PlayerMatchPerformance
        exclude = ("deleted_at",)
        read_only_fields = BASE_READ_ONLY
        validators = []


class MatchSerializer(ModelCleanMixin, serializers.ModelSerializer):
    home_team_detail = TeamSerializer(source="home_team", read_only=True)
    away_team_detail = TeamSerializer(source="away_team", read_only=True)
    innings = MatchInningsSerializer(many=True, read_only=True)

    class Meta:
        model = Match
        exclude = ("deleted_at",)
        read_only_fields = BASE_READ_ONLY
        validators = []
