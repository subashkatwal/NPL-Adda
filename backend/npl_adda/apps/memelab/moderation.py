"""
Lightweight text moderation for Meme Zone (topics, AI captions, meme text, comments).

A built-in list of slurs and strong profanity in English, Nepali and Romanized Nepali,
plus anything in ``MEME_BLOCKED_TERMS``. Matching is on whole words after case-folding,
so ordinary words that merely contain a blocked string are not refused. This is a floor,
not a replacement for human moderation: memes still go through the review queue.
"""
import re

from django.conf import settings

BUILT_IN = {
    # English
    "fuck", "fucking", "motherfucker", "shit", "bitch", "bastard", "cunt", "slut", "whore", "retard",
    "nigger", "nigga", "faggot", "rape", "rapist",
    # Romanized Nepali
    "muji", "mugi", "randi", "machikne", "machikney", "chikne", "chikney", "gandu", "lado", "puti", "bhalu",
    "kukur ko chhora", "randi ko ban",
    # Devanagari
    "मुजी", "रण्डी", "रन्डी", "माचिक्ने", "चिक्ने", "लाडो", "पुती", "भालु", "गान्डु",
}
LINK = re.compile(r"https?://|www\.", re.IGNORECASE)


def _terms():
    return BUILT_IN | {t.casefold() for t in settings.MEME_BLOCKED_TERMS}


def blocked_term(text):
    """Return the first blocked term found in ``text`` (whole word or phrase), else None."""
    folded = f" {' '.join(re.findall(r'[\wऀ-ॿ]+', (text or '').casefold()))} "
    for term in _terms():
        if f" {term} " in folded:
            return term
    return None


def check_text(text, *, allow_links=False):
    """Return a fan-facing problem with the text, or None when it is acceptable."""
    if not allow_links and LINK.search(text or ""):
        return "Links are not allowed here."
    if blocked_term(text):
        return "Please keep it fun: that wording isn't allowed on NPL Adda."
    return None
