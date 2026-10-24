"""
Caption providers for Meme Zone.

Every provider takes a ``CaptionContext`` (topic, language, humour style and only *verified*
facts) and returns top/bottom caption pairs. Two ship today:

* ``MockCaptionProvider`` - deterministic, offline, always available. It fills hand-written
  generic templates and is reported as ``provider="mock"``, never as an AI model.
* ``GeminiCaptionProvider`` - Google's Gemini Flash over HTTPS (``GOOGLE_GEMINI_API_KEY``).

``get_caption_provider()`` picks one from ``MEME_CAPTION_PROVIDER`` (``auto`` | ``gemini`` | ``mock``).
A LangChain/LangGraph or external-service provider only needs ``name``, ``model_name`` and
``generate(context) -> CaptionResult``; the pipeline in ``pipeline.py`` does validation around it.
"""
import hashlib
import json
from dataclasses import dataclass, field

import requests
from django.conf import settings


@dataclass(frozen=True)
class CaptionContext:
    topic: str
    language: str  # en | ne | ne_rom | mixed
    style: str  # roast | rivalry | reaction | fan_pain (older: wholesome | banter | sarcastic | hype)
    team: dict | None = None  # {"name", "short_name", "city"}
    match: dict | None = None  # verified fixture facts: {"opponent", "venue", "date", "status", ...}
    facts: dict = field(default_factory=dict)  # everything the captions may state as fact
    verified: bool = False  # True only when facts come from a real (non-sample) stored match


@dataclass
class CaptionResult:
    options: list  # [{"top": str, "bottom": str}]
    provider: str
    model_name: str
    is_mock: bool
    usage: dict = field(default_factory=dict)

    @property
    def captions(self):
        return [join_caption(o["top"], o["bottom"]) for o in self.options]


class CaptionProviderError(Exception):
    """Predictable provider failure with a safe, client-facing code and message."""

    def __init__(self, code, message, status=503):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def join_caption(top, bottom):
    return " / ".join(p.strip() for p in (top, bottom) if p and p.strip())[:280]


# ------------------------------------------------------------------ mock

LINES = {
    "en": [
        "{team} fans when {topic}: calm outside, final over inside",
        "Explaining {topic} to my family: like it's a super over",
        "{team} adda tonight: one topic only, {topic}",
        "Nobody: ... {team} fans: {topic} changes the whole season",
        "Me pretending I'm not refreshing for {topic}: every few seconds",
    ],
    "ne": [
        "{topic} हुँदा {team} का फ्यान: बाहिर शान्त, भित्र अन्तिम ओभर",
        "घरमा {topic} बुझाउँदा: सुपर ओभरको जस्तो तनाव",
        "आजको अड्डामा एउटै कुरा: {topic}",
        "{team} समर्थक भन्छन्: {topic} ले पूरै सिजन बदल्छ",
        "{topic} को खबरका लागि: हरेक केही सेकेन्डमा रिफ्रेस",
    ],
    "mixed": [
        "{team} fans jaba {topic}: bahira calm, bhitra last over",
        "Ghar ma {topic} explain garda: super over ko pressure",
        "Aajako adda ma ekai topic: {topic}",
        "{team} supporters: {topic} le pura season change garcha",
        "{topic} ko update ko lagi: har ek chin ma refresh",
    ],
}
LINES["ne_rom"] = LINES["mixed"]

MATCH_LINES = {
    "en": "{team} vs {opponent} at {venue}: {topic}",
    "ne": "{venue} मा {team} बनाम {opponent}: {topic}",
    "mixed": "{venue} ma {team} vs {opponent}: {topic}",
}
MATCH_LINES["ne_rom"] = MATCH_LINES["mixed"]

STYLE_TAGS = {
    "roast": {"en": "No mercy.", "ne": "दया छैन।", "mixed": "Daya chaina."},
    "rivalry": {"en": "See you at Kirtipur.", "ne": "किर्तिपुरमा भेटौंला।", "mixed": "Kirtipur ma bhetaula."},
    "reaction": {"en": "Me rn.", "ne": "म अहिले।", "mixed": "Ma ahile."},
    "fan_pain": {"en": "Every. Single. Season.", "ne": "हरेक सिजन यस्तै।", "mixed": "Har season yestai."},
    "funny": {"en": "I can't stop laughing.", "ne": "हाँसो रोकिएन।", "mixed": "Hasso rokiyena."},
    "hype": {"en": "Let's go!", "ne": "जाऔं!", "mixed": "Jaam!"},
    "wholesome": {"en": "Love this game.", "ne": "क्रिकेट नै माया।", "mixed": "Cricket nai maya."},
    "sarcastic": {"en": "Totally fine. Totally.", "ne": "एकदम ठीक छ, हो नि।", "mixed": "Ekdam thik cha, haina ra."},
    "banter": {"en": "", "ne": "", "mixed": ""},
}


class MockCaptionProvider:
    name = "mock"
    model_name = "mock-templates-v2"

    def generate(self, context: CaptionContext, count=3) -> CaptionResult:
        lang = context.language if context.language in LINES else "en"
        tag_lang = "mixed" if lang == "ne_rom" else lang
        team = (context.team or {}).get("name") or "NPL"
        values = {"team": team, "topic": context.topic}
        pool = list(LINES[lang])
        if context.match:
            values.update(opponent=context.match["opponent"], venue=context.match["venue"])
        # Deterministic rotation: the same request always yields the same captions.
        seed = int(hashlib.sha256(f"{context.topic}|{lang}|{context.style}|{team}".encode()).hexdigest(), 16)
        start = seed % len(pool)
        ordered = pool[start:] + pool[:start]
        if context.match:  # the fixture-grounded line first when a verified match was given
            ordered.insert(0, MATCH_LINES[lang])
        tag = STYLE_TAGS.get(context.style, STYLE_TAGS["banter"])[tag_lang]
        options = []
        for line in ordered[:count]:
            top, _, bottom = line.format(**values).partition(": ")
            if not bottom:
                top, bottom = "", top
            options.append({"top": top[:140], "bottom": (f"{bottom} {tag}".strip() if tag else bottom)[:140]})
        return CaptionResult(options=options, provider=self.name, model_name=self.model_name, is_mock=True,
                             usage={"mock": True, "tokens": 0})


# ------------------------------------------------------------------ Gemini

LANGUAGE_NAMES = {
    "en": "English",
    "ne": "Nepali in Devanagari script",
    "ne_rom": "Romanized Nepali (Nepali words written in Latin letters, the way fans text)",
    "mixed": "a natural mix of English and Romanized Nepali",
}
STYLE_BRIEFS = {
    "roast": "a playful roast of the rival team or the situation - teasing, never hateful or personal",
    "rivalry": "friendly rivalry between two fan bases",
    "reaction": "a reaction-meme moment: how a fan feels right now",
    "fan_pain": "relatable fan pain: the suffering every supporter knows",
    "funny": ("pure comedy: silly, absurd, laugh-out-loud jokes about the moment - exaggeration, wordplay and "
              "everyday Nepali life (chai, load-shedding, traffic, mum's calls). Every caption must be genuinely "
              "funny; no roasting, no sadness, no serious lines"),
    "banter": "friendly banter", "hype": "pure hype", "wholesome": "wholesome", "sarcastic": "light sarcasm",
}
SYSTEM_PROMPT = """You write short, funny cricket meme captions for NPL ADDA, an independent fan community for the
Nepal Premier League (T20). Rules you must follow:
- Only state facts that appear in VERIFIED_FACTS. Never invent scores, wickets, overs, player names, results,
  records or events. If VERIFIED_FACTS is empty, write generic fan humour with no factual claims or numbers.
- No slurs, hate, harassment of real people, sexual content, violence, betting or politics. Teasing a team is fine.
- Each caption is a classic meme: a short TOP line (setup, may be empty) and a BOTTOM line (punchline).
  Keep each line under 70 characters.
- Write in the requested language only.
Return JSON: {"captions": [{"top": "...", "bottom": "..."}, ...]} with exactly three captions."""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {"captions": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"top": {"type": "STRING"}, "bottom": {"type": "STRING"}},
        "required": ["top", "bottom"],
    }}},
    "required": ["captions"],
}
SAFETY = [{"category": c, "threshold": "BLOCK_MEDIUM_AND_ABOVE"} for c in (
    "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT")]


class GeminiCaptionProvider:
    name = "gemini"
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key=None, model=None, timeout=None, session=None, fallback_model=None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model or settings.GEMINI_MODEL
        self.fallback_model = settings.GEMINI_FALLBACK_MODEL if fallback_model is None else fallback_model
        self.timeout = timeout or settings.GEMINI_TIMEOUT_SECONDS
        self.session = session or requests

    def build_prompt(self, context: CaptionContext):
        brief = {
            "topic": context.topic,
            "language": LANGUAGE_NAMES.get(context.language, "English"),
            "humour_style": STYLE_BRIEFS.get(context.style, "friendly banter"),
            "fan_team": (context.team or {}).get("name"),
            "VERIFIED_FACTS": context.facts if context.verified or context.facts else {},
        }
        return "Write three meme captions for this brief:\n" + json.dumps(brief, ensure_ascii=False, indent=2)

    def generate(self, context: CaptionContext) -> CaptionResult:
        if not self.api_key:
            raise CaptionProviderError("provider_not_configured", "AI captions are not configured on this server.")
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": self.build_prompt(context)}]}],
            "generationConfig": {"temperature": 0.95, "maxOutputTokens": 800, "responseMimeType": "application/json",
                                 "responseSchema": RESPONSE_SCHEMA, "thinkingConfig": {"thinkingBudget": 0}},
            "safetySettings": SAFETY,
        }
        fallbacks = [m.strip() for m in (self.fallback_model or "").split(",") if m.strip()]
        models = [self.model_name] + [m for m in fallbacks if m != self.model_name]
        response = None
        for model in models:  # retired (404), overloaded (429/503) or timed-out models fall through to the next
            try:
                response = self.session.post(
                    self.endpoint.format(model=model), json=body, timeout=self.timeout,
                    headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                )
            except requests.RequestException:
                response = None
                continue
            if response.status_code not in (404, 429, 503):
                break
        self.model_name = model
        if response is None:
            raise CaptionProviderError("provider_unavailable", "The AI caption service could not be reached.")
        if response.status_code in (404, 503):
            raise CaptionProviderError("provider_unavailable", "The AI caption service is unavailable right now.")
        if response.status_code == 429:
            raise CaptionProviderError("provider_busy", "The AI caption service is busy. Try again shortly.", 503)
        if response.status_code >= 400:
            raise CaptionProviderError("provider_error", "The AI caption service returned an error.", 502)
        try:
            payload = response.json()
            candidate = payload["candidates"][0]
            if candidate.get("finishReason") == "SAFETY":
                raise CaptionProviderError("provider_refused", "The AI declined that topic. Try another one.", 422)
            text = "".join(p.get("text", "") for p in candidate["content"]["parts"])
            raw = json.loads(text)["captions"]
            options = [{"top": str(o.get("top", "")).strip()[:140], "bottom": str(o.get("bottom", "")).strip()[:140]}
                       for o in raw if isinstance(o, dict)]
        except CaptionProviderError:
            raise
        except (KeyError, IndexError, TypeError, ValueError):
            raise CaptionProviderError("provider_bad_response", "The AI caption service sent an unusable reply.", 502)
        options = [o for o in options if o["top"] or o["bottom"]]
        if not options:
            raise CaptionProviderError("provider_bad_response", "The AI caption service sent no captions.", 502)
        usage = payload.get("usageMetadata", {})
        return CaptionResult(
            options=options[:3], provider=self.name, model_name=self.model_name, is_mock=False,
            usage={"prompt_tokens": usage.get("promptTokenCount"), "output_tokens": usage.get("candidatesTokenCount")},
        )


def get_caption_provider(name=None):
    name = name or settings.MEME_CAPTION_PROVIDER
    if name == "auto":
        name = "gemini" if settings.GEMINI_API_KEY else "mock"
    if name == "mock":
        return MockCaptionProvider()
    if name == "gemini":
        return GeminiCaptionProvider()
    raise CaptionProviderError("provider_not_configured", f"Caption provider '{name}' is not available.")
