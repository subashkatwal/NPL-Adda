from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness probe for load balancers and container orchestration."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["common"],
        responses=inline_serializer("Health", {"status": serializers.CharField()}),
    )
    def get(self, request):
        return Response({"status": "ok"})
