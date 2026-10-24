from apps.common.admin import register_all

from .models import Badge, FanActivity, FanBadge, FanProfile, Poll, PollOption, Prediction, TeamMembership, Vote

register_all(Badge, FanActivity, FanBadge, FanProfile, Poll, PollOption, Prediction, TeamMembership, Vote)
