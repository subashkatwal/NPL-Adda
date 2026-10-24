from rest_framework.permissions import SAFE_METHODS, BasePermission

MODERATE_PERMISSION = "moderation.moderate_content"


def is_moderator(user):
    return bool(user and user.is_authenticated and user.is_active and user.has_perm(MODERATE_PERMISSION))


class IsStaffOrReadOnly(BasePermission):
    """Anyone may read; only staff may write reference data (teams, matches, templates)."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or bool(request.user and request.user.is_staff)


class IsModerator(BasePermission):
    message = "Moderator permission required."

    def has_permission(self, request, view):
        return is_moderator(request.user)
