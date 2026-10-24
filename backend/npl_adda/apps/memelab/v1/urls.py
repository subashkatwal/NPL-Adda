"""Mounted at /api/v1/memelab."""
from django.urls import path

from apps.common.routing import resource_routes

from . import views

app_name = "memelab"

urlpatterns = [
    *resource_routes(views.MemeTemplateViewSet, "/templates", "template"),
    *resource_routes(views.MemeGenerationRequestViewSet, "/generations", "generation"),
    *resource_routes(views.MemeDraftViewSet, "/drafts", "draft"),
    path("/drafts/<uuid:pk>/submit", views.SubmitDraftView.as_view(), name="draft-submit"),
    path("/drafts/<uuid:pk>/image", views.DraftImageView.as_view(), name="draft-image"),
    *resource_routes(views.MemeUploadViewSet, "/uploads", "upload"),
    path("/render", views.RenderPreviewView.as_view(), name="render"),
    path("/caption-status", views.CaptionStatusView.as_view(), name="caption-status"),
    *resource_routes(views.MemeFeedViewSet, "/memes", "meme"),
    path("/memes/<uuid:pk>/react", views.ReactView.as_view(), name="meme-react"),
    path("/memes/<uuid:pk>/comments", views.CommentListView.as_view(), name="meme-comments"),
    path("/comments/<uuid:pk>", views.CommentDetailView.as_view(), name="comment-detail"),
    path("/comments/<uuid:pk>/report", views.CommentReportView.as_view(), name="comment-report"),
    path("/comments/<uuid:pk>/hide", views.CommentHideView.as_view(), name="comment-hide"),
    *resource_routes(views.ContestViewSet, "/contests", "contest"),
    path("/contests/<uuid:pk>/enter", views.ContestEnterView.as_view(), name="contest-enter"),
    path("/contests/<uuid:pk>/vote", views.ContestVoteView.as_view(), name="contest-vote"),
    path("/hall-of-fame", views.HallOfFameView.as_view(), name="hall-of-fame"),
    path("/team-wars", views.TeamWarsView.as_view(), name="team-wars"),
]
