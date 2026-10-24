"""Mounted at /api/v1/content."""
from django.urls import path

from apps.common.routing import resource_routes

from . import views

app_name = "content"

urlpatterns = [
    path("/mine", views.MyPostsView.as_view(), name="mine"),
    path("/<uuid:pk>/vote", views.PostVoteView.as_view(), name="post-vote"),
    *resource_routes(views.CommunityPostViewSet, "", "post"),
]
