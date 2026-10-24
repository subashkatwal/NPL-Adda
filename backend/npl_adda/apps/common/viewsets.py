from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, viewsets


class SoftDeleteModelViewSet(viewsets.ModelViewSet):
    """DELETE soft-deletes the row instead of removing it physically."""

    def perform_destroy(self, instance):
        instance.soft_delete()


class ModelCleanMixin:
    """Run the model's ``clean()`` during serializer validation so API and admin share rules."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        model = self.Meta.model
        instance = model(**{**self._current_values(), **attrs})
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
        return attrs

    def _current_values(self):
        if self.instance is None:
            return {}
        return {f.name: getattr(self.instance, f.name) for f in self.instance._meta.concrete_fields}
