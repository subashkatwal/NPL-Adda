from rest_framework import serializers

from apps.common.viewsets import ModelCleanMixin

from ..models import Player, Team, TeamRoster

BASE_READ_ONLY = ("id", "created_at", "updated_at")


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        exclude = ("deleted_at",)
        read_only_fields = BASE_READ_ONLY


class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        exclude = ("deleted_at",)
        read_only_fields = BASE_READ_ONLY


class TeamRosterSerializer(ModelCleanMixin, serializers.ModelSerializer):
    player_detail = PlayerSerializer(source="player", read_only=True)

    class Meta:
        model = TeamRoster
        exclude = ("deleted_at",)
        read_only_fields = BASE_READ_ONLY
        validators = []  # conditional unique constraints are enforced by the database (409/400 on conflict)
