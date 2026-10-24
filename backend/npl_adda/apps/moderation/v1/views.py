from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsModerator
from apps.content.models import CommunityPost
from apps.fanengagement.identity import HasFanProfile, get_fan_profile
from apps.fanengagement.services import Conflict

from .. import services
from ..models import ModerationAction, ModerationReport
from .serializers import ActionCreateSerializer, ActionSerializer, ReportCreateSerializer, ReportSerializer

TAGS = ["moderation"]


@extend_schema_view(**{a: extend_schema(tags=TAGS) for a in ("list", "create", "retrieve", "partial_update")})
class ReportViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                    mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Any fan can file a report; only moderators can list, assign or resolve reports."""

    queryset = ModerationReport.objects.select_related("post")
    http_method_names = ["get", "post", "patch"]
    filterset_fields = ("status", "reason", "assigned_to", "post")

    def get_permissions(self):
        return [HasFanProfile()] if self.action == "create" else [IsModerator()]

    def get_serializer_class(self):
        return ReportCreateSerializer if self.action == "create" else ReportSerializer

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save(reporter=get_fan_profile(self.request))
        except IntegrityError:
            raise Conflict({"detail": "You already have an open report on this post."})

    def perform_update(self, serializer):
        closing = serializer.validated_data.get("status") in (
            ModerationReport.Status.RESOLVED, ModerationReport.Status.DISMISSED
        )
        serializer.save(**({"resolved_at": timezone.now()} if closing else {}))


@extend_schema(tags=TAGS)
class ActionListCreateView(APIView):
    """Moderators: record a decision (approve, reject, hide, remove, restore). Every decision is audited."""

    permission_classes = [IsModerator]

    @extend_schema(responses=ActionSerializer(many=True))
    def get(self, request):
        actions = ModerationAction.objects.all()
        if post := request.query_params.get("post"):
            actions = actions.filter(post_id=post)
        return Response(ActionSerializer(actions[:200], many=True).data)

    @extend_schema(request=ActionCreateSerializer, responses={201: ActionSerializer})
    def post(self, request):
        serializer = ActionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        post = generics.get_object_or_404(CommunityPost.all_objects, pk=data["post"])
        report = None
        if data.get("report"):
            report = generics.get_object_or_404(ModerationReport, pk=data["report"], post=post)
        action = services.apply_action(post, request.user, data["action_type"], data["reason"], report=report)
        return Response(ActionSerializer(action).data, status=status.HTTP_201_CREATED)
