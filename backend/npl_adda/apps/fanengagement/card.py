"""
Fan card: levels, public fan code, verified stats and the privacy-filtered card payload.

Everything on the card comes from server data. Points and counts are sums of the FanActivity
ledger, which only backend services write, so a fan cannot raise their own level or stats.
"""
import base64
import hashlib
import hmac
import io
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from PIL import Image, ImageOps

from apps.memelab import imaging

from .models import Badge, FanActivity

Activity = FanActivity.ActivityType

# (minimum points, key, name). Points come only from verified activity in the ledger.
LEVELS = (
    (0, "rookie", "Rookie"),
    (50, "super_fan", "Super Fan"),
    (200, "die_hard", "Die-hard"),
    (500, "legend", "Legend"),
)
AVATAR_SIDE = 512


def fan_level(points):
    """Level for a points total, with progress towards the next one (``next`` is None at the top)."""
    points = max(points or 0, 0)
    index = max(i for i, (floor, _, _) in enumerate(LEVELS) if points >= floor)
    floor, key, name = LEVELS[index]
    nxt = LEVELS[index + 1] if index + 1 < len(LEVELS) else None
    progress = 1.0 if nxt is None else round((points - floor) / (nxt[0] - floor), 3)
    return {
        "key": key, "name": name, "rank": index + 1, "points": points, "floor": floor,
        "next": {"key": nxt[1], "name": nxt[2], "at": nxt[0]} if nxt else None,
        "progress": progress,
    }


def fan_code(profile):
    """Stable public code such as ``NPL-7K3Q-9XA2``. Keyed hash of the id: cannot be reversed to it."""
    digest = hmac.new(settings.SECRET_KEY.encode(), f"fan-card:{profile.pk}".encode(), hashlib.sha256).digest()
    code = base64.b32encode(digest).decode().replace("O", "8").replace("I", "9")[:8]
    return f"NPL-{code[:4]}-{code[4:]}"


def points_subquery(outer="pk"):
    """Correlated SUM of ledger points for annotating querysets (one query for the whole page)."""
    ledger = FanActivity.objects.filter(fan_profile=OuterRef(outer)).values("fan_profile")
    return Coalesce(Subquery(ledger.annotate(t=Sum("points_delta")).values("t"), output_field=IntegerField()), 0)


def card_stats(profile):
    """Points and activity counts in a single aggregate over the ledger."""
    def n(kind):
        return Count("id", filter=Q(activity_type=kind))

    from apps.content.models import CommunityPost, PostComment

    stats = profile.activities.aggregate(
        points=Coalesce(Sum("points_delta"), 0),
        votes=n(Activity.POLL_VOTE),
        predictions=n(Activity.PREDICTION_SUBMITTED),
        predictions_correct=n(Activity.PREDICTION_CORRECT),
        posts=n(Activity.POST_PUBLISHED),
        contest_wins=n(Activity.MEME_CONTEST_WIN),
    )
    # Approved (published) memes and visible comments, counted from the content tables themselves.
    stats["memes"] = CommunityPost.objects.filter(
        author=profile, content_type=CommunityPost.ContentType.MEME, status=CommunityPost.Status.PUBLISHED).count()
    stats["comments"] = PostComment.objects.filter(author=profile, is_hidden=False).count()
    return stats


def level_ladder():
    return [{"key": key, "name": name, "from": floor, "to": (LEVELS[i + 1][0] - 1) if i + 1 < len(LEVELS) else None}
            for i, (floor, key, name) in enumerate(LEVELS)]


def avatar_src(profile):
    return profile.avatar.url if profile.avatar else ""


def fan_identity(profile, points=None):
    """
    Compact identity shown beside memes and comments. ``points`` comes from a queryset
    annotation (``points_subquery``) so lists never query per row; level is omitted without it.
    """
    level = fan_level(points) if points is not None else None
    return {
        "id": str(profile.pk), "nickname": profile.nickname, "is_public": profile.is_public,
        "personality": profile.fan_personality,
        "avatar_url": avatar_src(profile) if profile.card_show_avatar else "",
        "level": {"key": level["key"], "name": level["name"]} if level else None,
    }


def build_card(profile, *, owner):
    """
    The card payload. Owners see everything plus their privacy switches; everyone else gets
    only what the owner allowed. Never includes email, account or database ids.
    """
    from apps.teams.v1.serializers import TeamSerializer

    stats = card_stats(profile)
    membership = profile.current_membership
    show = {
        "avatar": profile.card_show_avatar, "stats": profile.card_show_stats,
        "badges": profile.card_show_badges, "since": profile.card_show_since,
    }
    visible = (lambda key: True) if owner else (lambda key: show[key])
    badges = [
        {"code": fb.badge.code, "name": fb.badge.name, "description": fb.badge.description,
         "icon_name": fb.badge.icon_name, "awarded_at": fb.awarded_at}
        for fb in profile.badges.filter(badge__is_active=True).select_related("badge")
    ]
    data = {
        "fan_code": fan_code(profile),
        "nickname": profile.nickname,
        "tagline": profile.tagline,
        "fan_personality": profile.fan_personality,
        "theme": profile.card_theme,
        "team": TeamSerializer(membership.team).data if membership else None,
        "level": fan_level(stats["points"]),
        "avatar_url": avatar_src(profile) if visible("avatar") else "",
        "stats": {k: v for k, v in stats.items()} if visible("stats") else None,
        "badges": badges if visible("badges") else None,
        "badges_total": Badge.objects.filter(is_active=True).count(),
        "levels": level_ladder(),
        "season": _season_year(),
        "member_since": profile.created_at.year if visible("since") else None,
        "is_owner": owner,
    }
    if owner:
        data["privacy"] = show
        data["profile_id"] = str(profile.pk)  # the owner's own id, needed to edit; never on public cards
        data["is_public"] = profile.is_public
    return data


def _season_year():
    from .stats import default_season

    season = default_season()
    return season.year if season else None


def store_avatar(file_obj):
    """Validate (type, bytes, pixels) and re-encode via the meme pipeline, then crop to a square."""
    content, _, _, _ = imaging.store_upload(file_obj)
    with Image.open(content) as img:
        square = ImageOps.fit(img.convert("RGB"), (AVATAR_SIDE, AVATAR_SIDE), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        square.save(out, "JPEG", quality=88, optimize=True)
    return ContentFile(out.getvalue(), name=f"{uuid.uuid4().hex}.jpg")
