from apps.common.admin import register_all

from .models import AgentRun, AgentToolCall

register_all(AgentRun, AgentToolCall)
