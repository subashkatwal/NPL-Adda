"""
Caption pipeline: retrieve verified facts -> generate -> validate facts -> moderate.

Each step is a plain function over a small state object so it can later become a LangGraph
node (or run in the external AI service) without changing callers. The pipeline never
publishes anything: it returns caption options that the fan edits and submits themselves.
"""
import re
from dataclasses import dataclass, field

from apps.teams.models import Team

from .captioning import CaptionContext, CaptionProviderError, MockCaptionProvider, get_caption_provider
from .moderation import blocked_term

DEV_SOURCE = "development-sample"
DIGITS = re.compile(r"[0-9०-९]+")
NEPALI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


@dataclass
class PipelineResult:
    options: list
    provider: str
    model_name: str
    is_mock: bool
    usage: dict
    verified: bool
    notices: list = field(default_factory=list)
    dropped: dict = field(default_factory=dict)
    error: CaptionProviderError | None = None


# ---------------------------------------------------------------- 1. retrieve

def retrieve_facts(team=None, match=None):
    """
    Facts captions may state, from stored data only. A match counts as verified unless it is a
    development sample. Scheduled matches contribute fixture facts (teams, venue, date) only;
    results and scores are included only once a match is completed with stored innings.
    Returns (team_ctx, match_ctx, facts, verified, references).
    """
    team_ctx = {"name": team.name, "short_name": team.short_name, "city": team.city} if team else None
    refs = [{"type": "teams.team", "id": str(team.pk)}] if team else []
    if not match:
        return team_ctx, None, ({"fan_team": team.name} if team else {}), False, refs
    if match.data_source == DEV_SOURCE:
        return team_ctx, None, ({"fan_team": team.name} if team else {}), False, refs
    if not team:
        team = match.home_team
        team_ctx = {"name": team.name, "short_name": team.short_name, "city": team.city}
    opponent = match.away_team if match.home_team_id == team.pk else match.home_team
    facts = {
        "fixture": f"{match.home_team.name} vs {match.away_team.name}",
        "venue": match.venue,
        "date": match.starts_at.date().isoformat(),
        "status": match.status,
        "match_number": match.match_number,
    }
    if match.status == match.Status.COMPLETED:
        if match.winner_id:
            facts["winner"] = match.winner.name
        if match.result_text:
            facts["result"] = match.result_text
        innings = list(match.innings.all().order_by("innings_number"))
        if innings:
            facts["innings"] = [
                {"batting": i.batting_team.name, "runs": i.runs, "wickets": i.wickets, "overs": str(i.overs)}
                for i in innings
            ]
    match_ctx = {"opponent": opponent.name, "venue": match.venue, "date": facts["date"], "status": match.status}
    refs.append({"type": "matches.match", "id": str(match.pk), "data_source": match.data_source,
                 "last_synced_at": match.last_synced_at.isoformat() if match.last_synced_at else None})
    return team_ctx, match_ctx, facts, True, refs


# ---------------------------------------------------------------- 2. generate

def generate(context, provider=None):
    """Ask the configured provider; if it is unavailable, fall back to the offline templates."""
    provider = provider or get_caption_provider()
    try:
        return provider.generate(context), None
    except CaptionProviderError as exc:
        if isinstance(provider, MockCaptionProvider):
            raise
        return MockCaptionProvider().generate(context), exc


# ---------------------------------------------------------------- 3. validate facts

def allowed_numbers(facts, topic):
    """Numbers a caption may contain: those in the verified facts or typed by the fan in the topic."""
    text = f"{facts} {topic}".translate(NEPALI_DIGITS)
    return set(DIGITS.findall(text)) | {"20", "T20"}


def validate_facts(options, facts, topic, context_team_names):
    """Drop captions that state numbers or name NPL teams the verified facts don't support."""
    numbers = allowed_numbers(facts, topic)
    other_teams = [
        name for name in Team.objects.values_list("name", flat=True) if name not in context_team_names
    ]
    kept, dropped = [], 0
    for option in options:
        text = f"{option['top']} {option['bottom']}"
        stated = set(DIGITS.findall(text.translate(NEPALI_DIGITS)))
        names_other_team = any(name.casefold() in text.casefold() for name in other_teams)
        if stated - numbers or names_other_team:
            dropped += 1
            continue
        kept.append(option)
    return kept, dropped


# ---------------------------------------------------------------- 4. moderate

def moderate(options):
    kept = [o for o in options if not blocked_term(f"{o['top']} {o['bottom']}")]
    return kept, len(options) - len(kept)


def run(*, topic, language, style, team=None, match=None, provider=None):
    team_ctx, match_ctx, facts, verified, refs = retrieve_facts(team, match)
    context = CaptionContext(topic=topic, language=language, style=style, team=team_ctx, match=match_ctx,
                             facts=facts, verified=verified)
    result, error = generate(context, provider)
    notices = []
    if error:
        notices.append(f"AI captions unavailable ({error.message}) - showing template captions instead.")
    if match and not verified:
        notices.append("That match is sample data, so captions stay generic and state no match facts.")
    names = {n for n in ((team_ctx or {}).get("name"), (match_ctx or {}).get("opponent")) if n}
    options, bad_facts = validate_facts(result.options, facts, topic, names)
    options, bad_words = moderate(options)
    if not options and not result.is_mock:  # every AI option failed checks: offer safe templates instead
        fallback = MockCaptionProvider().generate(context)
        options, _ = moderate(validate_facts(fallback.options, facts, topic, names)[0])
        notices.append("The AI suggestions didn't pass our fact and safety checks, so here are template captions.")
        result = fallback
    return PipelineResult(
        options=options, provider=result.provider, model_name=result.model_name, is_mock=result.is_mock,
        usage=result.usage, verified=verified, notices=notices,
        dropped={"unsupported_facts": bad_facts, "moderation": bad_words}, error=error,
    ), refs
