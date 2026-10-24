from django.urls import path

COLLECTION_ACTIONS = {"get": "list", "post": "create"}
DETAIL_ACTIONS = {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}


def resource_routes(viewset, base, name):
    """
    Collection and detail routes for a viewset with no trailing slash.

    ``base`` is "" for a feature's main resource or "/<segment>" for a sub-resource,
    giving e.g. ``/api/v1/teams`` + ``/api/v1/teams/<uuid>``.
    """

    def bound(actions):
        return {method: action for method, action in actions.items() if hasattr(viewset, action)}

    return [
        path(base, viewset.as_view(bound(COLLECTION_ACTIONS)), name=f"{name}-list"),
        path(f"{base}/<uuid:pk>", viewset.as_view(bound(DETAIL_ACTIONS)), name=f"{name}-detail"),
    ]
