"""
Meme Zone engagement scores, feeds and rankings.

Score of a meme = 2 x upvotes - downvotes + reactions. Every input is limited to one per fan
per meme by database constraints, fans cannot vote or react on their own memes, and only
active (non-deleted) rows count, so repeated clicks or requests cannot inflate a score.

Ranking periods are calendar windows in Nepal time: ``week`` starts Monday 00:00, ``month``
on the 1st, ``season`` is the current NPL season window, ``all`` has no bound. A meme belongs
to the period it was published in. Ties: higher score, then more upvotes, then published first.
"""
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db.models import Count, ExpressionWrapper, F, FloatField, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Cast, Coalesce, Extract, Now, Power
from django.utils import timezone

from apps.common.cache import cached
from apps.content.models import CommunityPost, ContentVote, PostComment, PostReaction
from apps.fanengagement.card import points_subquery
from apps.fanengagement.models import TeamMembership
from apps.fanengagement.stats import default_season, season_window
from apps.teams.models import Team

PERIODS = ("week", "month", "season", "all")
REACTION_KINDS = [k for k, _ in PostReaction.Kind.choices]


def _count(model, **filters):
    qs = model.objects.filter(post=OuterRef("pk"), **filters).values("post").annotate(n=Count("id")).values("n")
    return Coalesce(Subquery(qs, output_field=IntegerField()), 0)


def memes():
    """Published memes (deleted ones are excluded by the default manager)."""
    return CommunityPost.objects.filter(content_type=CommunityPost.ContentType.MEME,
                                        status=CommunityPost.Status.PUBLISHED)


def with_engagement(qs, profile=None):
    """Annotate counts with correlated subqueries (no join fan-out), plus the caller's own vote/reaction."""
    qs = qs.annotate(
        upvotes=_count(ContentVote, vote_type="up"),
        downvotes=_count(ContentVote, vote_type="down"),
        reaction_count=_count(PostReaction),
        comment_count=_count(PostComment, is_hidden=False),
        **{f"r_{kind}": _count(PostReaction, kind=kind) for kind in REACTION_KINDS},
    ).annotate(engagement=F("upvotes") * 2 - F("downvotes") + F("reaction_count"),
               author_points=points_subquery("author"))  # author's fan level, without a query per meme
    if profile is not None:
        qs = qs.annotate(
            my_vote=Subquery(ContentVote.objects.filter(post=OuterRef("pk"), fan_profile=profile).values("vote_type")[:1]),
            my_reaction=Subquery(PostReaction.objects.filter(post=OuterRef("pk"), fan_profile=profile).values("kind")[:1]),
        )
    return qs.select_related("author", "team", "match__home_team", "match__away_team").prefetch_related(
        "meme_drafts__template")


def sort(qs, mode):
    if mode == "new":
        return qs.order_by("-published_at", "-created_at")
    if mode == "top":
        return qs.order_by("-engagement", "-upvotes", "published_at")
    # trending: score decays with age, (score + 1) / (hours + 2)^1.5
    hours = ExpressionWrapper(Extract(Now() - F("published_at"), "epoch") / 3600.0, output_field=FloatField())
    hot = ExpressionWrapper(
        (Cast(F("engagement"), FloatField()) + Value(1.0)) / Power(hours + Value(2.0), Value(1.5)),
        output_field=FloatField(),
    )
    return qs.annotate(hot=hot).order_by("-hot", "-published_at")


def period_window(period, now=None):
    """(start, end, label) for a ranking period; start is None for all time."""
    now = now or timezone.now()
    local = timezone.localtime(now)
    tz = timezone.get_current_timezone()
    if period == "week":
        start = datetime.combine((local - timedelta(days=local.weekday())).date(), time.min, tzinfo=tz)
        return start, now, "This week (from Monday, Nepal time)"
    if period == "month":
        start = datetime.combine(local.date().replace(day=1), time.min, tzinfo=tz)
        return start, now, "This month"
    if period == "season":
        season = default_season()
        if season:
            start, end = season_window(season)
            return start, end, season.name
        return None, now, "All time"
    return None, now, "All time"


def in_period(qs, period):
    start, end, _ = period_window(period)
    if start:
        qs = qs.filter(published_at__gte=start, published_at__lt=end)
    return qs


def _ranked_rows(period):
    rows = in_period(with_engagement(memes()), period).values(
        "id", "author_id", "author__nickname", "team_id", "engagement", "upvotes", "published_at", "media_url", "body")
    return sorted(rows, key=lambda r: (-r["engagement"], -r["upvotes"], r["published_at"]))


def hall_of_fame(period="week"):
    def compute():
        start, end, label = period_window(period)
        rows = _ranked_rows(period)
        creators = {}
        for row in rows:
            c = creators.setdefault(row["author_id"], {"fan_id": str(row["author_id"]), "nickname": row["author__nickname"],
                                                       "score": 0, "memes": 0, "best_meme": str(row["id"]),
                                                       "first_published": row["published_at"]})
            c["score"] += row["engagement"]
            c["memes"] += 1
        top_creators = sorted(creators.values(), key=lambda c: (-c["score"], -c["memes"], c["first_published"]))
        for c in top_creators:
            c.pop("first_published")
        return {
            "period": period, "label": label,
            "starts_at": start.isoformat() if start else None, "ends_at": end.isoformat() if end else None,
            "scoring": "Meme score = 2 x upvotes - downvotes + reactions. One vote and one reaction per fan per "
                       "meme; no voting on your own memes. Ties: more upvotes, then published first.",
            "top_meme_ids": [str(r["id"]) for r in rows[:10]],
            "top_creators": dense_rank(top_creators[:20], "score"),
            "teams": team_table(rows),
        }
    return cached(f"memezone:hof:{period}", settings.LEADERBOARD_CACHE_SECONDS, compute)


def team_table(rows):
    teams = {t.pk: t for t in Team.objects.filter(is_active=True)}
    members = dict(TeamMembership.objects.filter(left_at__isnull=True, fan_profile__deleted_at__isnull=True)
                   .values_list("team").annotate(n=Count("id")).values_list("team", "n"))
    table = {pk: {"team_id": str(pk), "name": t.name, "short_name": t.short_name, "primary_color": t.primary_color,
                  "secondary_color": t.secondary_color, "memes": 0, "score": 0, "members": members.get(pk, 0),
                  "top_meme": None}
             for pk, t in teams.items()}
    for row in rows:  # rows are already in rank order, so the first one seen per team is its top meme
        entry = table.get(row["team_id"])
        if entry:
            entry["memes"] += 1
            entry["score"] += row["engagement"]
            entry["top_meme"] = entry["top_meme"] or str(row["id"])
    ranked = sorted(table.values(), key=lambda t: (-t["score"], -t["memes"], t["name"]))
    return dense_rank(ranked, "score")


def team_wars(period="week"):
    def compute():
        start, end, label = period_window(period)
        return {"period": period, "label": label, "teams": team_table(_ranked_rows(period))}
    return cached(f"memezone:teamwars:{period}", settings.LEADERBOARD_CACHE_SECONDS, compute)


def dense_rank(rows, key):
    rank, previous = 0, object()
    for row in rows:
        if row[key] != previous:
            rank, previous = rank + 1, row[key]
        row["rank"] = rank
    return rows


def reaction_counts(post):
    return {kind: getattr(post, f"r_{kind}", 0) for kind in REACTION_KINDS}
