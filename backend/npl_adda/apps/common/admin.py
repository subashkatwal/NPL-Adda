from django.contrib import admin


class BaseModelAdmin(admin.ModelAdmin):
    """Admin for BaseModel subclasses: shows soft-deleted rows so they can be audited or restored."""

    readonly_fields = ("id", "created_at", "updated_at", "deleted_at")
    list_filter = ()

    def get_queryset(self, request):
        return self.model.all_objects.all()

    def get_list_display(self, request):
        return ("__str__", "created_at", "deleted_at")


def register_all(*models, admin_class=BaseModelAdmin):
    for model in models:
        admin.site.register(model, admin_class)
