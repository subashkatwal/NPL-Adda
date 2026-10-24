"""
Building blocks for the staff admin console API.

Every resource is an ``AdminViewSet`` registered with ``@register``. The registry drives
the URL router, the ``/admin/resources`` index the console builds its navigation from,
and the OPTIONS metadata the console builds its tables and forms from, so adding a
resource here is enough to make it manageable in the UI.
"""
from django.db import IntegrityError, models, transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, MethodNotAllowed, ValidationError
from rest_framework.filters import BaseFilterBackend, OrderingFilter, SearchFilter
from rest_framework.metadata import SimpleMetadata
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from apps.common.viewsets import ModelCleanMixin

BASE_READ_ONLY = ("id", "created_at", "updated_at", "deleted_at")
REGISTRY = []  # viewset classes in navigation order


def register(viewset):
    REGISTRY.append(viewset)
    return viewset


def resource_for_model(model):
    return next((v.resource for v in REGISTRY if v.model is model), None)


class IsAdminStaff(BasePermission):
    """Active staff accounts only. Finer rules (e.g. granting staff) live in the serializers."""

    message = "Staff access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_staff)


class AdminPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


class DeletedFilter(BaseFilterBackend):
    """``?deleted=exclude`` (default) | ``include`` | ``only`` on lists; detail routes always reach deleted rows."""

    def filter_queryset(self, request, queryset, view):
        if view.action not in ("list", "bulk") or not hasattr(queryset.model, "deleted_at"):
            return queryset
        mode = request.query_params.get("deleted", "exclude")
        if mode == "only":
            return queryset.filter(deleted_at__isnull=False)
        if mode == "include":
            return queryset
        return queryset.filter(deleted_at__isnull=True)


class AdminSerializer(serializers.ModelSerializer):
    """Adds ``_label`` (the row's ``str``) and ``<fk>_label`` for every relation, for display in the console."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["_label"] = str(instance)
        for name, field in self.fields.items():
            if isinstance(field, serializers.RelatedField) and not field.write_only and "." not in field.source:
                related = getattr(instance, field.source, None)
                data[f"{name}_label"] = str(related) if related is not None else None
        return data


def admin_serializer(model, *, fields="__all__", read_only=(), clean=False, base=AdminSerializer, **attrs):
    """Build an admin ModelSerializer. Conditional unique constraints are left to the database (409)."""
    meta = type("Meta", (), {
        "model": model,
        "fields": fields,
        "read_only_fields": BASE_READ_ONLY + tuple(read_only),
        "validators": [],
    })
    bases = (ModelCleanMixin, base) if clean else (base,)
    return type(f"Admin{model.__name__}Serializer", bases, {"Meta": meta, **attrs})


class AdminMetadata(SimpleMetadata):
    """OPTIONS describes the resource, every field (incl. read-only) and each custom action's inputs."""

    def determine_metadata(self, request, view):
        if not getattr(view, "resource", None):
            return super().determine_metadata(request, view)
        return {
            "name": view.label,
            "resource": view.describe(),
            "fields": self.describe_serializer(view.get_serializer()),
            "actions": [
                {**spec.public(), "fields": self.describe_serializer(spec.serializer())}
                for spec in view.action_specs
            ],
        }

    def describe_serializer(self, serializer):
        return {name: self.get_field_info(field) for name, field in serializer.fields.items()}

    def get_field_info(self, field):
        info = super().get_field_info(field)
        info["allow_null"] = getattr(field, "allow_null", False)
        if isinstance(field, serializers.JSONField):
            info["type"] = "json"
        if isinstance(field, serializers.ManyRelatedField):
            info["type"] = "related many"
            info.pop("choices", None)
        elif isinstance(field, serializers.RelatedField):
            info["type"] = "related"
            info.pop("choices", None)
            info["related"] = resource_for_model(self._related_model(field))
        elif isinstance(field, serializers.ChoiceField):
            info["choices"] = [{"value": k, "display_name": str(v)} for k, v in field.choices.items()]
            info["allow_blank"] = field.allow_blank
        if field.style.get("base_template") == "textarea.html":
            info["multiline"] = True
        if field.style.get("input_type") == "password":
            info["type"] = "password"
        return info

    @staticmethod
    def _related_model(field):
        if getattr(field, "queryset", None) is not None:
            return field.queryset.model
        try:
            return field.parent.Meta.model._meta.get_field(field.source).related_model
        except Exception:  # noqa: BLE001 - not a model relation; no link target
            return None


class ActionSpec:
    """
    A custom POST /<resource>/<uuid>/<name> operation, described to the console with its input form.

    ``when`` limits it to rows whose fields hold one of the listed values, e.g.
    ``{"status": ["pending_review"]}`` (``None`` in the list matches an empty field). ``quick``
    shows it as a one-click button on matching list rows, and makes it available for bulk runs.
    """

    def __init__(self, name, label, serializer, *, danger=False, confirm=None, help="", when=None, quick=False):
        self.name, self.label, self.serializer = name, label, serializer
        self.danger, self.confirm, self.help = danger, confirm, help
        self.when, self.quick = when or {}, quick

    def public(self):
        return {"name": self.name, "label": self.label, "danger": self.danger, "confirm": self.confirm,
                "help": self.help, "when": self.when, "quick": self.quick}

    def applies_to(self, instance):
        return all(getattr(instance, field, None) in allowed for field, allowed in self.when.items())


class EmptyInput(serializers.Serializer):
    pass


BULK_LIMIT = 2000


class BulkInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["delete", "restore"])
    ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=BULK_LIMIT)
    all = serializers.BooleanField(required=False, default=False,
                                   help_text="Apply to every row matching the current filters instead of `ids`.")

    def validate(self, attrs):
        if not attrs.get("all") and not attrs.get("ids"):
            raise serializers.ValidationError({"ids": "Select at least one row."})
        return attrs


def _first_message(detail):
    if isinstance(detail, dict):
        detail = next(iter(detail.values()), "")
    if isinstance(detail, list):
        detail = detail[0] if detail else ""
    return str(detail)


class AdminViewSet(viewsets.ModelViewSet):
    """
    Staff CRUD over one model, including soft-deleted rows (``?deleted=``) with soft delete and restore.

    Class attributes describe the resource to the console: ``resource`` (URL key), ``label``,
    ``group``, ``list_display`` and the ``allow_*`` flags.
    """

    permission_classes = [IsAdminStaff]
    pagination_class = AdminPagination
    metadata_class = AdminMetadata
    filter_backends = [DeletedFilter, DjangoFilterBackend, SearchFilter, OrderingFilter]
    ordering_fields = "__all__"
    lookup_value_regex = "[0-9a-f-]{36}"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    resource = None
    label = ""
    group = ""
    model = None
    list_display = ()
    select_related = ()
    prefetch_related = ()
    allow_create = True
    allow_update = True
    allow_delete = True  # soft delete + restore
    action_specs = ()
    note = ""
    # Red nav badges: ``attention`` = filter for rows waiting on staff (a review queue);
    # ``watch_new`` = also count rows created since this staff member last opened the section.
    attention = None
    watch_new = False

    def get_queryset(self):
        qs = self.model.all_objects.all()
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        if self.prefetch_related:
            qs = qs.prefetch_related(*self.prefetch_related)
        return qs

    @classmethod
    def describe(cls):
        return {
            "key": cls.resource,
            "label": cls.label,
            "group": cls.group,
            "note": cls.note,
            "list_display": list(cls.list_display),
            "search": bool(getattr(cls, "search_fields", ())),
            "filters": list(getattr(cls, "filterset_fields", ())),
            "can_create": cls.allow_create,
            "can_update": cls.allow_update,
            "can_delete": cls.allow_delete,
            "actions": [spec.public() for spec in cls.action_specs],
            "has_queue": cls.attention is not None,
        }

    def get_serializer_class(self):
        spec = self._spec()
        return spec.serializer if spec else super().get_serializer_class()

    def _spec(self):
        return next((s for s in self.action_specs if s.name == getattr(self, "action_name", None)), None)

    def create(self, request, *args, **kwargs):
        if not self.allow_create:
            raise MethodNotAllowed(request.method)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not self.allow_update:
            raise MethodNotAllowed(request.method)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not self.allow_delete:
            raise MethodNotAllowed(request.method)
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        instance.soft_delete()

    def perform_restore(self, instance):
        instance.restore()

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        if not self.allow_delete:
            raise MethodNotAllowed(request.method)
        instance = self.get_object()
        self.perform_restore(instance)
        return self.respond(instance)

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """
        Soft-delete or restore many rows: ``{"action": "delete"|"restore", "ids": [...]}`` or
        ``{"action": ..., "all": true}`` for every row matching the list's current query string
        (search, filters, ``deleted=``). Rows a rule refuses (e.g. your own account) are skipped and counted.
        """
        if not self.allow_delete:
            raise MethodNotAllowed(request.method)
        serializer = BulkInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = self.filter_queryset(self.get_queryset())
        if not data.get("all"):
            queryset = queryset.filter(pk__in=data.get("ids", []))
        deleting = data["action"] == "delete"
        queryset = queryset.filter(deleted_at__isnull=deleting)  # rows already in the target state are no-ops
        done, skipped = 0, []
        for instance in queryset[:BULK_LIMIT]:
            try:
                with transaction.atomic():
                    (self.perform_destroy if deleting else self.perform_restore)(instance)
                done += 1
            except (APIException, IntegrityError) as exc:
                detail = getattr(exc, "detail", None) or "Conflicts with an existing record."
                skipped.append({"id": str(instance.pk), "label": str(instance), "reason": _first_message(detail)})
        return Response({"done": done, "skipped": skipped})

    @action(detail=True, methods=["post"], url_path=r"run/(?P<action_name>[a-z-]+)")
    def run(self, request, pk=None, action_name=None):
        """Run one of the resource's ``action_specs`` with its validated input."""
        self.action_name = action_name
        spec = self._spec()
        if spec is None:
            return Response({"detail": "Unknown action."}, status=status.HTTP_404_NOT_FOUND)
        instance = self.get_object()
        serializer = spec.serializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        if not spec.applies_to(instance):
            raise ValidationError({"detail": f"“{spec.label}” doesn't apply to this record any more."})
        result = getattr(self, f"do_{action_name.replace('-', '_')}")(instance, serializer.validated_data)
        return result if isinstance(result, Response) else self.respond(instance)

    @action(detail=False, methods=["post"], url_path=r"bulk-run/(?P<action_name>[a-z-]+)")
    def bulk_run(self, request, action_name=None):
        """Run one quick action on many rows: ``{"ids": [...]}`` plus the action's own inputs, if any."""
        self.action_name = action_name
        spec = self._spec()
        if spec is None or not spec.quick:
            return Response({"detail": "Unknown action."}, status=status.HTTP_404_NOT_FOUND)
        ids = BulkInput(data={"action": "delete", "ids": request.data.get("ids", [])})
        ids.is_valid(raise_exception=True)
        inputs = spec.serializer(data=request.data, context=self.get_serializer_context())
        inputs.is_valid(raise_exception=True)
        handler = getattr(self, f"do_{action_name.replace('-', '_')}")
        done, skipped = 0, []
        for instance in self.get_queryset().filter(pk__in=ids.validated_data["ids"])[:BULK_LIMIT]:
            if not spec.applies_to(instance):
                skipped.append({"id": str(instance.pk), "label": str(instance), "reason": "Already handled."})
                continue
            try:
                with transaction.atomic():
                    handler(instance, inputs.validated_data)
                done += 1
            except (APIException, IntegrityError) as exc:
                detail = getattr(exc, "detail", None) or "Conflicts with an existing record."
                skipped.append({"id": str(instance.pk), "label": str(instance), "reason": _first_message(detail)})
        return Response({"done": done, "skipped": skipped})

    def respond(self, instance, status_code=status.HTTP_200_OK):
        self.action_name = None
        instance = self.get_queryset().get(pk=instance.pk)  # reload with annotations
        return Response(self.get_serializer(instance).data, status=status_code)


def count_by(queryset, field):
    return dict(queryset.values_list(field).annotate(n=models.Count("id")).values_list(field, "n"))
