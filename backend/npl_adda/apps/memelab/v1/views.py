from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsModerator, IsStaffOrReadOnly, is_moderator
from apps.common.viewsets import SoftDeleteModelViewSet
from apps.content.models import CommunityPost, PostComment
from apps.content.v1.serializers import CommunityPostSerializer
from apps.fanengagement.card import points_subquery
from apps.fanengagement.identity import HasFanProfile, get_fan_profile
from apps.fanengagement.services import Conflict
from apps.moderation.models import ModerationReport

from .. import imaging, services, stats
from ..captioning import join_caption
from ..models import ContestEntry, MemeContest, MemeDraft, MemeGenerationRequest, MemeTemplate, MemeUpload
from ..throttles import (
    MemeCommentThrottle, MemeEngageThrottle, MemeGenerationThrottle, MemeRenderThrottle, MemeUploadThrottle,
)
from . import serializers as s

ACTIONS = ("list", "create", "retrieve", "update", "partial_update", "destroy")
TAGS = ["memelab"]


def ctx(request):
    return {"request": request, "profile": get_fan_profile(request)}


@extend_schema_view(**{a: extend_schema(tags=TAGS) for a in ACTIONS})
class MemeTemplateViewSet(SoftDeleteModelViewSet):
    serializer_class = s.MemeTemplateSerializer
    permission_classes = [IsStaffOrReadOnly]
    filterset_fields = ("category",)

    def get_queryset(self):
        qs = MemeTemplate.objects.all()
        return qs if self.request.user.is_staff else qs.filter(is_active=True)


MOCK_NOTICE = "Captions from the offline templates (fixed lines filled with stored facts), not an AI model."
ERROR_STATUS = {"duplicate_content": 409, "provider_not_configured": 503}


@extend_schema_view(
    list=extend_schema(tags=TAGS),
    retrieve=extend_schema(tags=TAGS),
    create=extend_schema(
        tags=TAGS, request=s.GenerationCreateSerializer,
        parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=False)],
        responses={200: s.GenerationResultSerializer, 201: s.GenerationResultSerializer,
                   409: s.GenerationErrorSerializer, 503: s.GenerationErrorSerializer},
    ),
)
class MemeGenerationRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                                   viewsets.GenericViewSet):
    """
    POST suggests three caption options (Gemini when configured, offline templates otherwise or
    when the AI is unavailable) and saves them as a draft the fan edits. Nothing is published.
    Repeating a request with the same idempotency key returns the original result (200).
    """

    serializer_class = s.MemeGenerationRequestSerializer
    permission_classes = [HasFanProfile]
    filterset_fields = ("status",)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MemeGenerationRequest.objects.none()
        return MemeGenerationRequest.objects.filter(fan_profile=get_fan_profile(self.request))

    def get_throttles(self):
        return [MemeGenerationThrottle()] if self.action == "create" else super().get_throttles()

    def create(self, request, *args, **kwargs):
        serializer = s.GenerationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key") or serializer.validated_data.get("idempotency_key")
        if not key:
            raise ValidationError({"idempotency_key": "Send an Idempotency-Key header or idempotency_key field."})
        gen, created = services.generate_captions(get_fan_profile(request), serializer.validated_data, key[:100])
        if gen.status == MemeGenerationRequest.Status.FAILED:
            return Response({"code": gen.error_code, "detail": gen.error_message,
                             "request": s.MemeGenerationRequestSerializer(gen).data},
                            status=ERROR_STATUS.get(gen.error_code, 502))
        draft = gen.drafts.order_by("created_at").first()
        options = []
        if draft:
            options = [{"top": draft.top_text, "bottom": draft.bottom_text}]
            for alt in draft.alternate_captions:
                options.append(alt if isinstance(alt, dict) else {"top": "", "bottom": alt})
        is_mock = gen.provider == "mock"
        notices = list(gen.usage_metadata.get("notices", []))
        if is_mock and not notices:
            notices.append(MOCK_NOTICE)
        payload = {"request": gen, "draft": draft, "options": options,
                   "captions": [join_caption(o.get("top", ""), o.get("bottom", "")) for o in options],
                   "is_mock": is_mock, "provider": gen.provider,
                   "verified_facts": bool(gen.usage_metadata.get("verified_facts")),
                   "notice": " ".join(notices) or None}
        return Response(s.GenerationResultSerializer(payload, context=ctx(request)).data,
                        status=201 if created else 200)


@extend_schema_view(**{a: extend_schema(tags=TAGS) for a in ("list", "create", "retrieve", "partial_update", "destroy")})
class MemeDraftViewSet(viewsets.ModelViewSet):
    """Your meme drafts. Drafts can be edited until submitted."""

    serializer_class = s.MemeDraftSerializer
    permission_classes = [HasFanProfile]
    http_method_names = ["get", "post", "patch", "delete"]
    filterset_fields = ("status", "team", "match")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MemeDraft.objects.none()
        return MemeDraft.objects.filter(fan_profile=get_fan_profile(self.request)).select_related("upload")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "profile": get_fan_profile(self.request)}

    def perform_create(self, serializer):
        serializer.save(fan_profile=get_fan_profile(self.request))

    def perform_update(self, serializer):
        if serializer.instance.status != MemeDraft.Status.DRAFT:
            raise ValidationError({"detail": "Only drafts can be edited."})
        serializer.save()

    def perform_destroy(self, instance):
        instance.soft_delete()


@extend_schema(tags=TAGS)
class SubmitDraftView(APIView):
    """Render the final image with Pillow and create the meme post (review queue unless MEME_REQUIRE_REVIEW is off)."""

    permission_classes = [HasFanProfile]

    @extend_schema(request=None, responses={201: CommunityPostSerializer})
    def post(self, request, pk):
        draft = generics.get_object_or_404(MemeDraft.objects.filter(fan_profile=get_fan_profile(request)), pk=pk)
        try:
            post = services.submit_draft(draft)
        except Conflict as exc:
            return Response(exc.detail, status=status.HTTP_409_CONFLICT)
        return Response(CommunityPostSerializer(post).data, status=status.HTTP_201_CREATED)


class JPEGRenderer(BaseRenderer):
    """Lets image endpoints satisfy ``Accept: image/*``; the views return the JPEG bytes themselves."""

    media_type = "image/jpeg"
    format = "jpg"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, bytes):
            return data
        # error payloads (validation, throttling) still go out as JSON text
        if renderer_context and renderer_context.get("response") is not None:
            renderer_context["response"]["Content-Type"] = "application/json"
        return JSONRenderer().render(data)


IMAGE_RENDERERS = [JSONRenderer, JPEGRenderer]  # JSON first so validation errors stay readable


def jpeg_response(image, *, filename=None, quality=88):
    response = HttpResponse(imaging.to_jpeg(image, quality=quality), content_type="image/jpeg")
    response["Cache-Control"] = "no-store"
    if filename:
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@extend_schema(tags=TAGS)
class DraftImageView(APIView):
    """Download a draft as a JPEG rendered by the server (before publishing)."""

    permission_classes = [HasFanProfile]
    renderer_classes = IMAGE_RENDERERS

    @extend_schema(responses={(200, "image/jpeg"): bytes})
    def get(self, request, pk):
        draft = generics.get_object_or_404(MemeDraft.objects.filter(fan_profile=get_fan_profile(request))
                                           .select_related("template", "upload", "team"), pk=pk)
        return jpeg_response(imaging.render_meme(services.draft_spec(draft)), filename=f"npl-adda-meme-{draft.pk.hex[:8]}.jpg")


@extend_schema(tags=TAGS)
class RenderPreviewView(APIView):
    """Live preview: render captions onto a template or your upload and return a JPEG. Rate limited."""

    permission_classes = [HasFanProfile]
    throttle_classes = [MemeRenderThrottle]
    renderer_classes = IMAGE_RENDERERS

    @extend_schema(request=s.RenderPreviewSerializer, responses={(200, "image/jpeg"): bytes})
    def post(self, request):
        serializer = s.RenderPreviewSerializer(data=request.data, context=ctx(request))
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        team = data.get("team") or getattr(get_fan_profile(request).current_membership, "team", None)
        spec = services.spec_for(template=data.get("template"), upload=data.get("upload"), team=team,
                                 top_text=data["top_text"], bottom_text=data["bottom_text"], text_style=data["text_style"],
                                 extra_uploads=services.extra_upload_objects(data["extra_uploads"]))
        image = imaging.render_meme(spec)
        image.thumbnail((720, 720))
        return jpeg_response(image, quality=80)


@extend_schema_view(list=extend_schema(tags=TAGS), create=extend_schema(tags=TAGS, request={
    "multipart/form-data": s.UploadCreateSerializer}, responses={201: s.MemeUploadSerializer}))
class MemeUploadViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    """Upload a background image (JPEG/PNG/WebP). It is validated and re-encoded server-side."""

    serializer_class = s.MemeUploadSerializer
    permission_classes = [HasFanProfile]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MemeUpload.objects.none()
        return MemeUpload.objects.filter(fan_profile=get_fan_profile(self.request))

    def get_throttles(self):
        return [MemeUploadThrottle()] if self.action == "create" else super().get_throttles()

    def create(self, request, *args, **kwargs):
        file_obj = request.FILES.get("image")
        if file_obj is None:
            raise ValidationError({"image": "Choose an image to upload."})
        try:
            content, width, height, digest = imaging.store_upload(file_obj)
        except imaging.ImageRejected as exc:
            raise ValidationError({"image": exc.message})
        upload = MemeUpload(fan_profile=get_fan_profile(request), width=width, height=height,
                            size_bytes=content.size, sha256=digest)
        upload.image.save(content.name, content, save=True)
        return Response(s.MemeUploadSerializer(upload).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------- feed & detail

@extend_schema_view(
    list=extend_schema(tags=TAGS, parameters=[
        OpenApiParameter("sort", str, enum=["trending", "new", "top"]),
        OpenApiParameter("period", str, enum=list(stats.PERIODS), description="Only with sort=top."),
        OpenApiParameter("team", str), OpenApiParameter("match", str), OpenApiParameter("author", str),
        OpenApiParameter("featured", bool), OpenApiParameter("ids", str, description="Comma-separated meme ids."),
    ]),
    retrieve=extend_schema(tags=TAGS),
)
class MemeFeedViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Published memes with votes, reactions and comment counts. Public; your own vote/reaction when logged in."""

    serializer_class = s.MemeSerializer
    permission_classes = [AllowAny]
    filter_backends = []

    def get_queryset(self):
        profile = get_fan_profile(self.request)
        qs = stats.with_engagement(stats.memes(), profile)
        params = self.request.query_params
        for key in ("team", "match", "author"):
            if value := params.get(key):
                qs = qs.filter(**{f"{key}_id": value})
        if params.get("featured") in ("1", "true"):
            qs = qs.filter(featured_at__isnull=False)
        if ids := params.get("ids"):
            qs = qs.filter(pk__in=[i for i in ids.split(",") if i][:50])
        mode = params.get("sort", "trending")
        if mode == "top":
            qs = stats.in_period(qs, params.get("period", "all"))
        return stats.sort(qs, mode)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "profile": get_fan_profile(self.request)}

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except (ValueError, DjangoValidationError):
            raise ValidationError({"detail": "Invalid filter value."})


def published_meme(pk):
    return generics.get_object_or_404(stats.memes(), pk=pk)


@extend_schema(tags=TAGS)
class ReactView(APIView):
    """Toggle your reaction: the same emoji again removes it, another emoji replaces it."""

    permission_classes = [HasFanProfile]
    throttle_classes = [MemeEngageThrottle]

    @extend_schema(request=s.ReactionInput, responses={200: s.MemeSerializer})
    def post(self, request, pk):
        post = published_meme(pk)
        serializer = s.ReactionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.toggle_reaction(post, get_fan_profile(request), serializer.validated_data["kind"])
        fresh = stats.with_engagement(stats.memes(), get_fan_profile(request)).get(pk=post.pk)
        return Response(s.MemeSerializer(fresh, context=ctx(request)).data)


class CommentPagination(generics.GenericAPIView.pagination_class):
    page_size = 20


@extend_schema(tags=TAGS)
class CommentListView(generics.ListCreateAPIView):
    """Comments on a published meme (top level, newest last, with replies). Login needed to post."""

    serializer_class = s.CommentSerializer
    pagination_class = CommentPagination
    filter_backends = []

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [HasFanProfile()]

    def get_throttles(self):
        return [MemeCommentThrottle()] if self.request.method == "POST" else super().get_throttles()

    def get_queryset(self):
        post = published_meme(self.kwargs["pk"])
        points = points_subquery("author")  # commenter fan levels in the same queries
        replies = PostComment.objects.select_related("author").annotate(author_points=points).order_by("created_at")
        return (PostComment.objects.filter(post=post, parent__isnull=True).select_related("author")
                .annotate(author_points=points)
                .prefetch_related(Prefetch("replies", queryset=replies)).order_by("created_at"))

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "profile": get_fan_profile(self.request)}

    @extend_schema(request=s.CommentCreateSerializer, responses={201: s.CommentSerializer})
    def post(self, request, pk):
        post = published_meme(pk)
        serializer = s.CommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_fan_profile(request)
        parent = None
        if parent_id := serializer.validated_data.get("parent"):
            parent = generics.get_object_or_404(PostComment.objects.filter(post=post), pk=parent_id)
            if parent.parent_id:  # one level of replies: answer the thread, not the reply
                parent = parent.parent
        body = serializer.validated_data["body"]
        recent = timezone.now() - timedelta(minutes=2)
        if PostComment.objects.filter(post=post, author=profile, body=body, created_at__gte=recent).exists():
            raise Conflict({"detail": "You just posted that comment."})
        comment = PostComment.objects.create(post=post, author=profile, parent=parent, body=body)
        return Response(s.CommentSerializer(comment, context=ctx(request)).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAGS)
class CommentDetailView(APIView):
    """Delete your own comment (moderators may delete any)."""

    permission_classes = [HasFanProfile]

    def delete(self, request, pk):
        comment = generics.get_object_or_404(PostComment, pk=pk)
        if comment.author_id != get_fan_profile(request).pk and not is_moderator(request.user):
            raise PermissionDenied("You can only delete your own comments.")
        comment.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=TAGS)
class CommentReportView(APIView):
    permission_classes = [HasFanProfile]
    throttle_classes = [MemeEngageThrottle]

    @extend_schema(request=s.CommentReportInput, responses={201: None})
    def post(self, request, pk):
        comment = generics.get_object_or_404(PostComment.objects.filter(is_hidden=False), pk=pk)
        serializer = s.CommentReportInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_fan_profile(request)
        if comment.author_id == profile.pk:
            raise ValidationError({"detail": "You can't report your own comment."})
        if ModerationReport.objects.filter(reporter=profile, comment=comment, status__in=["open", "under_review"]).exists():
            raise Conflict({"detail": "You already reported this comment."})
        ModerationReport.objects.create(reporter=profile, post=comment.post, comment=comment, **serializer.validated_data)
        return Response({"detail": "Thanks - a moderator will review it."}, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAGS)
class CommentHideView(APIView):
    """Moderators: hide (or with ``"hidden": false`` restore) a comment."""

    permission_classes = [IsModerator]

    @extend_schema(request=s.HideCommentInput, responses={200: s.CommentSerializer})
    def post(self, request, pk):
        comment = generics.get_object_or_404(PostComment, pk=pk)
        hide = request.data.get("hidden", True) not in (False, "false", 0, "0")
        reason = ""
        if hide:
            serializer = s.HideCommentInput(data=request.data)
            serializer.is_valid(raise_exception=True)
            reason = serializer.validated_data["reason"]
        comment.is_hidden, comment.hidden_reason = hide, reason
        comment.save(update_fields=["is_hidden", "hidden_reason", "updated_at"])
        return Response(s.CommentSerializer(comment, context=ctx(request)).data)


# ---------------------------------------------------------------- contests

def contest_queryset(request):
    qs = MemeContest.objects.select_related("match__home_team", "match__away_team", "team", "winner__post__author")
    qs = qs.annotate(entry_count=Count("entries", filter=Q(entries__status=ContestEntry.Status.APPROVED,
                                                           entries__deleted_at__isnull=True)))
    return qs if request.user.is_staff else qs.filter(status=MemeContest.Status.PUBLISHED)


@extend_schema_view(list=extend_schema(tags=TAGS, parameters=[
    OpenApiParameter("phase", str, description="active (default) | finished | all")]), retrieve=extend_schema(tags=TAGS))
class ContestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Meme of the Match and team challenges. Public."""

    serializer_class = s.ContestSerializer
    permission_classes = [AllowAny]
    filter_backends = []

    def get_queryset(self):
        qs = contest_queryset(self.request)
        if self.action == "list":
            phase = self.request.query_params.get("phase", "active")
            now = timezone.now()
            if phase == "active":
                qs = qs.filter(finalized_at__isnull=True, voting_close_at__gt=now).order_by("submissions_open_at")
            elif phase == "finished":
                qs = qs.filter(Q(finalized_at__isnull=False) | Q(voting_close_at__lte=now)).order_by("-voting_close_at")
        return qs

    def retrieve(self, request, *args, **kwargs):
        contest = self.get_object()
        profile = get_fan_profile(request)
        visible = Q(status=ContestEntry.Status.APPROVED) | (Q(fan_profile=profile) if profile else Q(pk=None))
        entries = (contest.entries.filter(visible).select_related("post__author", "post__team")
                   .order_by("final_rank", "created_at"))
        tally = services.tally(contest)
        context = {**ctx(request), "tally": tally}
        my_vote = contest.votes.filter(fan_profile=profile).values_list("entry_id", flat=True).first() if profile else None
        data = s.ContestSerializer(contest, context=context).data
        data["entries"] = s.ContestEntrySerializer(entries, many=True, context=context).data
        if not contest.finalized_at:  # live order: votes, then earliest entry
            data["entries"].sort(key=lambda e: (-e["votes"], e["created_at"]))
        data["my_vote"] = str(my_vote) if my_vote else None
        data["rules"] = ("One vote per fan per contest (you can move it while voting is open). You can't vote for "
                         "your own meme. Most counted votes wins; ties go to the earlier entry. Staff may exclude "
                         "suspicious votes before results are finalized.")
        return Response(data)


@extend_schema(tags=TAGS)
class ContestEnterView(APIView):
    permission_classes = [HasFanProfile]

    @extend_schema(request=s.EnterContestInput, responses={201: s.ContestEntrySerializer})
    def post(self, request, pk):
        contest = generics.get_object_or_404(MemeContest.objects.filter(status=MemeContest.Status.PUBLISHED), pk=pk)
        serializer = s.EnterContestInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = services.enter_contest(contest, get_fan_profile(request), serializer.validated_data["post"])
        return Response(s.ContestEntrySerializer(entry, context=ctx(request)).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAGS)
class ContestVoteView(APIView):
    permission_classes = [HasFanProfile]
    throttle_classes = [MemeEngageThrottle]

    @extend_schema(request=s.ContestVoteInput, responses={200: None, 201: None})
    def post(self, request, pk):
        contest = generics.get_object_or_404(MemeContest.objects.filter(status=MemeContest.Status.PUBLISHED), pk=pk)
        serializer = s.ContestVoteInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        vote, created = services.cast_contest_vote(contest, get_fan_profile(request),
                                                   serializer.validated_data["entry"], request)
        return Response({"entry": str(vote.entry_id), "changed": not created},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        contest = generics.get_object_or_404(MemeContest.objects.filter(status=MemeContest.Status.PUBLISHED), pk=pk)
        if contest.phase(timezone.now()) not in ("voting", "open"):
            raise ValidationError({"detail": "Voting isn't open for this contest."})
        vote = contest.votes.filter(fan_profile=get_fan_profile(request)).first()
        if vote:
            vote.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- rankings

def _period(request):
    period = request.query_params.get("period", "week")
    if period not in stats.PERIODS:
        raise ValidationError({"period": f"Use one of {', '.join(stats.PERIODS)}."})
    return period


@extend_schema(tags=TAGS, parameters=[OpenApiParameter("period", str, enum=list(stats.PERIODS))])
class HallOfFameView(APIView):
    """Top memes, top creators and team rankings for a period, with the scoring rules spelled out."""

    permission_classes = [AllowAny]

    def get(self, request):
        data = dict(stats.hall_of_fame(_period(request)))
        ids = data.pop("top_meme_ids")
        memes = {str(m.pk): m for m in stats.with_engagement(stats.memes(), get_fan_profile(request)).filter(pk__in=ids)}
        data["top_memes"] = [s.MemeSerializer(memes[i], context=ctx(request)).data for i in ids if i in memes]
        winners = (MemeContest.objects.filter(status=MemeContest.Status.PUBLISHED, winner__isnull=False)
                   .select_related("winner__post__author", "match__home_team", "match__away_team", "team")
                   .order_by("-finalized_at")[:6])
        data["contest_winners"] = s.ContestSerializer(winners, many=True, context=ctx(request)).data
        return Response(data)


@extend_schema(tags=TAGS, parameters=[OpenApiParameter("period", str, enum=list(stats.PERIODS))])
class TeamWarsView(APIView):
    """Teams ranked by their fans' meme activity, plus open team challenges."""

    permission_classes = [AllowAny]

    def get(self, request):
        data = dict(stats.team_wars(_period(request)))
        challenges = contest_queryset(request).filter(team__isnull=False, finalized_at__isnull=True,
                                                      voting_close_at__gt=timezone.now())
        data["challenges"] = s.ContestSerializer(challenges, many=True, context=ctx(request)).data
        return Response(data)


@extend_schema(tags=TAGS)
class CaptionStatusView(APIView):
    """Which caption source is active, so the UI can label suggestions honestly."""

    permission_classes = [AllowAny]

    def get(self, request):
        from ..captioning import get_caption_provider
        try:
            provider = get_caption_provider()
            name, model = provider.name, provider.model_name
        except Exception:  # noqa: BLE001 - misconfiguration is reported, not raised
            name, model = "unavailable", ""
        return Response({"provider": name, "model": model, "ai": name not in ("mock", "unavailable"),
                         "rendering": imaging.rendering_status()})
