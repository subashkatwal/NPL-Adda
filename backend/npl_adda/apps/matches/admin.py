from apps.common.admin import register_all

from .models import Match, MatchInnings, PlayerMatchPerformance, Season

register_all(Match, MatchInnings, PlayerMatchPerformance, Season)
