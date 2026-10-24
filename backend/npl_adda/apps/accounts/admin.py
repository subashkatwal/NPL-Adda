from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.common.admin import BaseModelAdmin

from .models import GuestSession, SocialAccount, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-created_at",)
    list_display = ("email", "username", "display_name", "is_staff", "is_active", "created_at", "deleted_at")
    search_fields = ("email", "username", "display_name")
    readonly_fields = ("id", "created_at", "updated_at", "deleted_at", "last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        ("Profile", {"fields": ("username", "display_name", "email_verified_at", "last_seen_at")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined", "created_at", "updated_at", "deleted_at")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)

    def get_queryset(self, request):
        return User.all_objects.all()


@admin.register(GuestSession)
class GuestSessionAdmin(BaseModelAdmin):
    readonly_fields = BaseModelAdmin.readonly_fields + ("token_hash",)


@admin.register(SocialAccount)
class SocialAccountAdmin(BaseModelAdmin):
    readonly_fields = BaseModelAdmin.readonly_fields + ("uid", "last_used_at")
