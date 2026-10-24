import hashlib
import io
import re
from datetime import timedelta
from difflib import SequenceMatcher

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.content.models import CommunityPost, PostReaction
from apps.fanengagement.rewards import Activity, record_activity
from apps.fanengagement.services import Conflict

from . import imaging, pipeline
from .captioning import CaptionProviderError, join_caption
from .models import ContestEntry, ContestVote, MemeContest, MemeDraft, MemeGenerationRequest, MemeUpload

DUPLICATE_RATIO = 0.92
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalise(text):
    return " ".join(_PUNCT.sub(" ", (text or "").lower()).split())


def find_duplicate(text, exclude_post_id=None):
    """Return the id of a community meme/post whose text is (nearly) the same, or None."""
    target = normalise(text)
    if not target:
        return None
    posts = CommunityPost.objects.exclude(status__in=[CommunityPost.Status.REJECTED, CommunityPost.Status.DRAFT])
    if exclude_post_id:
        posts = posts.exclude(pk=exclude_post_id)
    for post_id, body in posts.order_by("-created_at").values_list("id", "body")[:500]:
        other = normalise(body)
        if other == target or SequenceMatcher(None, target, other).ratio() >= DUPLICATE_RATIO:
            return post_id
    return None


# ---------------------------------------------------------------- captions

def generate_captions(profile, data, idempotency_key):
    """
    Create (or replay) a generation request and its draft. Returns (request, created).
    Failures are recorded on the request with a safe error code instead of raising.
    """
    existing = MemeGenerationRequest.objects.filter(fan_profile=profile, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            request = MemeGenerationRequest.objects.create(
                fan_profile=profile, team=data.get("team"), match=data.get("match"), topic=data["topic"],
                language=data["language"], style=data["style"], idempotency_key=idempotency_key,
                status=MemeGenerationRequest.Status.RUNNING, started_at=timezone.now(),
            )
    except IntegrityError:
        return MemeGenerationRequest.objects.get(fan_profile=profile, idempotency_key=idempotency_key), False

    try:
        result, refs = pipeline.run(topic=data["topic"], language=data["language"], style=data["style"],
                                    team=data.get("team"), match=data.get("match"))
    except CaptionProviderError as exc:  # misconfiguration (unknown provider): fail clearly, don't guess
        return _fail(request, exc.code, exc.message), True
    request.provider, request.model_name = result.provider, result.model_name
    unique, seen = [], set()
    for option in result.options:
        text = join_caption(option["top"], option["bottom"])
        key = normalise(text)
        if key and key not in seen and not find_duplicate(text):
            seen.add(key)
            unique.append(option)
    if not unique:
        return _fail(request, "duplicate_content", "Every caption matched existing community content."), True

    first = unique[0]
    MemeDraft.objects.create(
        fan_profile=profile, generation_request=request, team=data.get("team"), match=data.get("match"),
        caption=join_caption(first["top"], first["bottom"]), top_text=first["top"], bottom_text=first["bottom"],
        language=data["language"], alternate_captions=unique[1:], source_references=refs,
    )
    request.status = MemeGenerationRequest.Status.COMPLETED
    request.usage_metadata = {**{k: v for k, v in result.usage.items() if v is not None}, "mock": result.is_mock,
                              "verified_facts": result.verified, "notices": result.notices, "dropped": result.dropped}
    if result.error:
        request.error_code, request.error_message = result.error.code, result.error.message[:255]
    request.completed_at = timezone.now()
    request.save(update_fields=["status", "provider", "model_name", "usage_metadata", "error_code", "error_message",
                                "completed_at", "updated_at"])
    return request, True


def _fail(request, code, message):
    request.status = MemeGenerationRequest.Status.FAILED
    request.error_code, request.error_message = code, message[:255]
    request.completed_at = timezone.now()
    request.save(update_fields=["status", "provider", "model_name", "error_code", "error_message",
                                "completed_at", "updated_at"])
    return request


# ---------------------------------------------------------------- rendering & publishing

def team_colours(team):
    if not team:
        return None
    return {"short_name": team.short_name, "primary_color": team.primary_color, "secondary_color": team.secondary_color}


def _image_source(file_field):
    """The stored image as an in-memory file, so rendering works with local disk and remote storage alike."""
    with file_field.open("rb") as f:
        return io.BytesIO(f.read())


def spec_for(*, template=None, upload=None, team=None, top_text="", bottom_text="", text_style=None, caption="",
             extra_uploads=()):
    background = None
    if upload is not None and upload.image:
        background = _image_source(upload.image)
    elif template is not None and template.image:
        background = _image_source(template.image)
    if not top_text and not bottom_text and caption:  # captions made before the top/bottom editor
        bottom_text = caption
    extra = [_image_source(u.image) for u in extra_uploads if u.image]
    if extra and background is None:  # a collage of only extra photos: the first one leads
        background, extra = extra[0], extra[1:]
    return imaging.MemeSpec(top_text=top_text, bottom_text=bottom_text, layout=(template.layout_config if template else {}),
                            background_path=background, extra_paths=extra, team=team_colours(team),
                            style=text_style or {})


def extra_upload_objects(ids):
    """The uploads behind ``MemeDraft.extra_uploads``, in the fan's chosen order (missing ones skipped)."""
    found = {str(u.pk): u for u in MemeUpload.objects.filter(pk__in=ids or [])}
    return [found[i] for i in ids or [] if i in found]


def draft_spec(draft):
    team = draft.team or getattr(draft.fan_profile.current_membership, "team", None)
    return spec_for(template=draft.template, upload=draft.upload, team=team, top_text=draft.top_text,
                    bottom_text=draft.bottom_text, text_style=draft.text_style, caption=draft.caption,
                    extra_uploads=extra_upload_objects(draft.extra_uploads))


@transaction.atomic
def submit_draft(draft):
    """
    Render the final image with Pillow and create the community post. It goes to the review
    queue unless MEME_REQUIRE_REVIEW is off. Raises ValidationError / Conflict.
    """
    draft = MemeDraft.objects.select_for_update(of=("self",)).select_related(
        "template", "upload", "team", "fan_profile", "generation_request").get(pk=draft.pk)
    if draft.status != MemeDraft.Status.DRAFT:
        raise ValidationError({"detail": "This draft has already been submitted."})
    text = join_caption(draft.top_text, draft.bottom_text) or draft.caption
    if len(text.strip()) < 2:
        raise ValidationError({"detail": "Add a caption before publishing."})
    if duplicate := find_duplicate(text):
        raise Conflict({"code": "duplicate_content", "detail": "A very similar meme already exists.",
                        "duplicate_of": str(duplicate)})
    image = imaging.render_meme(draft_spec(draft))
    draft.rendered_image.save(f"{draft.pk.hex}.jpg", ContentFile(imaging.to_jpeg(image)), save=False)
    generated_by = draft.generation_request.provider if draft.generation_request_id else ""
    post = CommunityPost.objects.create(
        author=draft.fan_profile, team=draft.team, match=draft.match, content_type=CommunityPost.ContentType.MEME,
        body=text, language=draft.language, media_url=draft.rendered_image.url,
        is_ai_generated=generated_by not in ("", "mock"), source_references=draft.source_references,
        status=CommunityPost.Status.PENDING_REVIEW,
    )
    draft.caption = text[:280]
    draft.published_post = post
    draft.status = MemeDraft.Status.PENDING_REVIEW
    if not settings.MEME_REQUIRE_REVIEW:
        post.publish()
        post.save(update_fields=["status", "published_at", "updated_at"])
        draft.status = MemeDraft.Status.PUBLISHED
        record_activity(post.author, Activity.POST_PUBLISHED, reference=post, idempotency_key=f"post_published:{post.pk}")
    draft.save(update_fields=["caption", "published_post", "status", "rendered_image", "updated_at"])
    return post


# ---------------------------------------------------------------- reactions

@transaction.atomic
def toggle_reaction(post, profile, kind):
    """Same emoji again removes it; a different emoji replaces it. Returns the fan's reaction kind or None."""
    if post.author_id == profile.pk:
        raise ValidationError({"detail": "You can't react to your own meme."})
    current = PostReaction.objects.select_for_update().filter(post=post, fan_profile=profile).first()
    if current and current.kind == kind:
        current.soft_delete()
        return None
    if current:
        current.kind = kind
        current.save(update_fields=["kind", "updated_at"])
        return kind
    try:
        with transaction.atomic():
            PostReaction.objects.create(post=post, fan_profile=profile, kind=kind)
    except IntegrityError:
        raise Conflict({"detail": "Reaction already recorded; try again."})
    return kind


# ---------------------------------------------------------------- contests

def client_hash(request):
    """Salted hash of the caller's address: lets staff spot vote rings without storing IPs."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    address = forwarded or request.META.get("REMOTE_ADDR", "")
    return hashlib.sha256(f"{settings.SECRET_KEY}:{address}".encode()).hexdigest()[:32] if address else ""


def eligible_for(contest, post):
    """Why the post can't enter the contest, or None."""
    if post.content_type != CommunityPost.ContentType.MEME or post.status != CommunityPost.Status.PUBLISHED:
        return "Only published memes can enter."
    if contest.team_id and post.team_id != contest.team_id:
        return f"This challenge is for {contest.team.name} memes."
    if contest.match_id:
        match = contest.match
        if post.match_id != match.pk and post.team_id not in match.team_ids:
            return "Enter a meme about this match or one of its two teams."
    return None


@transaction.atomic
def enter_contest(contest, profile, post):
    contest = MemeContest.objects.select_for_update(of=("self",)).select_related("match", "team").get(pk=contest.pk)
    phase = contest.phase(timezone.now())
    if phase not in ("submissions", "open"):
        raise ValidationError({"detail": "Entries aren't open for this contest."})
    if post.author_id != profile.pk:
        raise PermissionDenied("You can only enter your own memes.")
    if reason := eligible_for(contest, post):
        raise ValidationError({"post": reason})
    mine = contest.entries.filter(fan_profile=profile).exclude(status=ContestEntry.Status.REJECTED).count()
    if mine >= contest.max_entries_per_fan:
        raise Conflict({"detail": f"You can enter {contest.max_entries_per_fan} meme(s) in this contest."})
    status = ContestEntry.Status.PENDING if contest.requires_entry_review else ContestEntry.Status.APPROVED
    try:
        with transaction.atomic():
            return ContestEntry.objects.create(contest=contest, post=post, fan_profile=profile, status=status)
    except IntegrityError:
        raise Conflict({"detail": "That meme is already entered."})


@transaction.atomic
def cast_contest_vote(contest, profile, entry, request=None):
    """One vote per fan per contest; voting again moves it. Suspicious votes are flagged for staff, not dropped."""
    contest = MemeContest.objects.select_for_update().get(pk=contest.pk)
    if contest.phase(timezone.now()) not in ("voting", "open"):
        raise ValidationError({"detail": "Voting isn't open for this contest."})
    if entry.contest_id != contest.pk or entry.status != ContestEntry.Status.APPROVED or entry.deleted_at:
        raise ValidationError({"entry": "That entry can't receive votes."})
    if entry.post.status != CommunityPost.Status.PUBLISHED or entry.post.deleted_at:
        raise ValidationError({"entry": "That meme is no longer available."})
    if entry.fan_profile_id == profile.pk:
        raise ValidationError({"entry": "You can't vote for your own meme."})
    fingerprint = client_hash(request) if request is not None else ""
    flags = []
    user = profile.user
    if user and user.date_joined > timezone.now() - timedelta(hours=24):
        flags.append("account under 24h old")
    if fingerprint and contest.votes.filter(client_hash=fingerprint).exclude(fan_profile=profile).count() >= 2:
        flags.append("network shared with other voters")
    vote = ContestVote.objects.select_for_update().filter(contest=contest, fan_profile=profile).first()
    if vote:
        vote.entry, vote.client_hash, vote.flag_reason = entry, fingerprint, ", ".join(flags)
        vote.save(update_fields=["entry", "client_hash", "flag_reason", "updated_at"])
        return vote, False
    try:
        with transaction.atomic():
            return ContestVote.objects.create(contest=contest, entry=entry, fan_profile=profile,
                                              client_hash=fingerprint, flag_reason=", ".join(flags)), True
    except IntegrityError:
        raise Conflict({"detail": "Your vote is already recorded."})


def counted_votes(contest):
    """Votes that count: not excluded by staff, for approved entries whose meme is still published."""
    return ContestVote.objects.filter(
        contest=contest, is_excluded=False, entry__status=ContestEntry.Status.APPROVED, entry__deleted_at__isnull=True,
        entry__post__status=CommunityPost.Status.PUBLISHED, entry__post__deleted_at__isnull=True,
    )


def tally(contest):
    """{entry_id: votes} for every approved entry (zero included)."""
    counts = dict(counted_votes(contest).values_list("entry").annotate(n=Count("id")).values_list("entry", "n"))
    entries = contest.entries.filter(status=ContestEntry.Status.APPROVED)
    return {e: counts.get(e, 0) for e in entries.values_list("id", flat=True)}


@transaction.atomic
def finalize_contest(contest):
    """
    Fix the results once voting has closed. Ranking: most counted votes; ties go to the entry
    submitted first. A contest with no votes has no winner. Safe to call once; repeats are refused.
    """
    contest = MemeContest.objects.select_for_update().get(pk=contest.pk)
    if contest.finalized_at:
        raise ValidationError({"detail": "Results are already final."})
    if contest.status != MemeContest.Status.PUBLISHED:
        raise ValidationError({"detail": "Only published contests can be finalized."})
    if timezone.now() < contest.voting_close_at:
        raise ValidationError({"detail": "Voting hasn't closed yet."})
    votes = tally(contest)
    entries = sorted(contest.entries.filter(pk__in=votes).select_related("fan_profile"),
                     key=lambda e: (-votes[e.pk], e.created_at))
    for rank, entry in enumerate(entries, start=1):
        entry.final_votes, entry.final_rank = votes[entry.pk], rank
        entry.save(update_fields=["final_votes", "final_rank", "updated_at"])
    winner = entries[0] if entries and votes[entries[0].pk] > 0 else None
    contest.winner, contest.finalized_at = winner, timezone.now()
    contest.save(update_fields=["winner", "finalized_at", "updated_at"])
    if winner:
        record_activity(winner.fan_profile, Activity.MEME_CONTEST_WIN, reference=contest,
                        idempotency_key=f"meme_contest_win:{contest.pk}")
    return contest


def contest_window_for(match):
    """Default Meme of the Match window: entries from the start until 30h later, votes until 48h after the start."""
    start = match.starts_at
    return {"submissions_open_at": start, "submissions_close_at": start + timedelta(hours=30),
            "voting_open_at": start, "voting_close_at": start + timedelta(hours=48)}
