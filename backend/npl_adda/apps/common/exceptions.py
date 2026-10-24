from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """DRF's handler, plus database constraint violations reported as 409 instead of 500."""
    if isinstance(exc, IntegrityError):
        return Response(
            {"detail": "This conflicts with an existing record or violates a data rule."},
            status=status.HTTP_409_CONFLICT,
        )
    return exception_handler(exc, context)
