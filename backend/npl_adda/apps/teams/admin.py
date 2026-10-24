from apps.common.admin import register_all

from .models import Player, Team, TeamRoster

register_all(Player, Team, TeamRoster)
