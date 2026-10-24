from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import is_moderator
from apps.fanengagement.identity import HasFanProfile, get_fan_profile
from apps.fanengagement.rewards import Activity, record_activity

from ..models import CommunityPost, ContentVote
from .serializers import CommunityPostSerializer, ContentVoteSerializer

Status = CommunityPost.Status
AUTHOR_EDITABLE = {Status.DRAFT, Status.PENDING_REVIEW, Status.REJECTED, Status.PUBLISHED}


def with_score(qs):
    alive = Q(votes__deleted_at__isnull=True)
    # Meta.ordering is ignored on aggregated querysets, so order explicitly for stable pagination.
    return qs.annotate(
        score=Count("votes", filter=alive & Q(votes__vote_type="up"))
        - Count("votes", filter=alive & Q(votes__vote_type="down"))
    ).order_by("-published_at", "-created_at")


@extend_schema_view(**{a: extend_schema(tags=["content"]) for a in
                       ("list", "create", "retrieve", "partial_update", "destroy")})
class CommunityPostViewSet(viewsets.ModelViewSet):
    """
    Lists only published posts (moderators may filter by any ``status``). Authors can read,
    edit and soft-delete their own posts in any non-hidden state. Editing a published post
    sends it back to review.
    """

    serializer_class = CommunityPostSerializer
    http_method_names = ["get", "post", "patch", "delete"]
    filterset_fields = ("team", "match", "content_type", "language", "author", "status")
    search_fields = ("title", "body")
    ordering_fields = ("published_at", "created_at", "score")

    def get_permissions(self):
        return [] if self.action in ("list", "retrieve") else [HasFanProfile()]

    def get_queryset(self):
        qs = with_score(CommunityPost.objects.select_related("author").prefetch_related("meme_drafts__template"))
        if self.action == "list":
            if is_moderator(self.request.user) and "status" in self.request.query_params:
                return qs
            return qs.filter(status=Status.PUBLISHED)
        if is_moderator(self.request.user):
            return qs
        profile = get_fan_profile(self.request)
        return qs.filter(Q(status=Status.PUBLISHED) | (Q(author=profile) if profile else Q(pk=None)))

    def get_object(self):
        post = super().get_object()
        if self.action in ("partial_update", "destroy"):
            if post.author_id != getattr(get_fan_profile(self.request), "pk", None):
                raise PermissionDenied("You can only change your own posts.")
            if self.action == "partial_update" and post.status not in AUTHOR_EDITABLE:
                raise PermissionDenied("This post can no longer be edited.")
        return post

    def perform_create(self, serializer):
        submit = serializer.validated_data.pop("submit_for_review", False)
        post = serializer.save(author=get_fan_profile(self.request), status=Status.DRAFT)
        if submit:
            self._submit(post)

    def perform_update(self, serializer):
        submit = serializer.validated_data.pop("submit_for_review", False)
        post = serializer.instance
        if settings.POST_REQUIRE_REVIEW and post.status == Status.PUBLISHED:
            serializer.save(status=Status.PENDING_REVIEW)  # edits go back to the queue only when review is on
            return
        post = serializer.save()
        if submit and post.status in (Status.DRAFT, Status.REJECTED):
            self._submit(post)

    @staticmethod
    def _submit(post):
        """Publish straight away (the default), or queue for review when POST_REQUIRE_REVIEW is on."""
        if settings.POST_REQUIRE_REVIEW:
            post.status = Status.PENDING_REVIEW
            post.save(update_fields=["status", "updated_at"])
            return
        post.publish()
        post.save(update_fields=["status", "published_at", "updated_at"])
        record_activity(post.author, Activity.POST_PUBLISHED, reference=post, idempotency_key=f"post_published:{post.pk}")

    def perform_destroy(self, instance):
        instance.soft_delete()


@extend_schema(tags=["content"])
class MyPostsView(generics.ListAPIView):
    serializer_class = CommunityPostSerializer
    permission_classes = [HasFanProfile]
    filterset_fields = ("status", "content_type")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CommunityPost.objects.none()
        return with_score(CommunityPost.objects.filter(author=get_fan_profile(self.request))
                          .prefetch_related("meme_drafts__template"))


@extend_schema(tags=["content"])
class PostVoteView(APIView):
    """One vote per fan per post; POST again to change it, DELETE to withdraw it."""

    permission_classes = [HasFanProfile]

    def _post(self, pk):
        return generics.get_object_or_404(CommunityPost.objects.filter(status=Status.PUBLISHED), pk=pk)

    @extend_schema(request=ContentVoteSerializer, responses={200: ContentVoteSerializer, 201: ContentVoteSerializer})
    def post(self, request, pk):
        post = self._post(pk)
        serializer = ContentVoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_fan_profile(request)
        if post.author_id == profile.pk:
            raise ValidationError({"detail": "You cannot vote on your own post."})
        vote_type = serializer.validated_data["vote_type"]
        with transaction.atomic():
            vote = ContentVote.objects.select_for_update().filter(post=post, fan_profile=profile).first()
            created = vote is None
            if created:
                try:
                    with transaction.atomic():
                        vote = ContentVote.objects.create(post=post, fan_profile=profile, vote_type=vote_type)
                except IntegrityError:
                    raise ValidationError({"detail": "Vote already recorded; retry."})
            else:
                vote.vote_type, vote.voted_at = vote_type, timezone.now()
                vote.save(update_fields=["vote_type", "voted_at", "updated_at"])
        return Response(ContentVoteSerializer(vote).data, status=201 if created else 200)

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        vote = ContentVote.objects.filter(post=self._post(pk), fan_profile=get_fan_profile(request)).first()
        if vote:
            vote.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
