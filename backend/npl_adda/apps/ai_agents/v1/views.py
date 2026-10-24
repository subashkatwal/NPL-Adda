from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, serializers, viewsets
from rest_framework.permissions import IsAdminUser

from ..models import AgentRun, AgentToolCall


class AgentRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentRun
        exclude = ("deleted_at",)


class AgentToolCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentToolCall
        exclude = ("deleted_at",)


@extend_schema_view(**{a: extend_schema(tags=["ai-agents"]) for a in ("list", "retrieve")})
class AgentRunViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff audit view of agent runs recorded by the AI service."""

    queryset = AgentRun.objects.all()
    serializer_class = AgentRunSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ("workflow_name", "status", "match")


@extend_schema(tags=["ai-agents"])
class AgentToolCallListView(generics.ListAPIView):
    serializer_class = AgentToolCallSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None
    filter_backends = []

    def get_queryset(self):
        return AgentToolCall.objects.filter(agent_run_id=self.kwargs["pk"])
