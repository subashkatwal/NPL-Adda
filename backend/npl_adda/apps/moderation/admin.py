from apps.common.admin import register_all

from .models import ModerationAction, ModerationReport

register_all(ModerationAction, ModerationReport)
