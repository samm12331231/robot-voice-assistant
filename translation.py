"""Narrow parsing for spoken translation requests."""

from dataclasses import dataclass
import re

from language_utils import LANGUAGE_NAMES


_TARGETS = {
    "english": "en",
    "arabic": "ar",
    "hindi": "hi",
    "urdu": "ur",
    "french": "fr",
    "chinese": "zh",
    "mandarin": "zh",
    "mandarin chinese": "zh",
}
LOCAL_EVENT_TRANSLATIONS = {
    ("welcome", "hi"): "स्वागत है",
    ("hello", "ar"): "مرحبًا",
    ("good morning", "hi"): "सुप्रभात",
    ("welcome", "zh"): "欢迎",
}
_REQUEST_PATTERNS = (
    r"^(?:say|can\s+you\s+say|could\s+you\s+say|please\s+say)\s+(.+?)\s+in\s+([a-z]+(?:\s+[a-z]+)?)[?.!]*$",
    r"^translate\s+(.+?)\s+(?:to|in|into)\s+([a-z]+(?:\s+[a-z]+)?)[?.!]*$",
    r"^how\s+do\s+i\s+say\s+(.+?)\s+in\s+([a-z]+(?:\s+[a-z]+)?)[?.!]*$",
)
_CREATIVE_REQUEST_PHRASES = {
    "joke", "a joke", "jokes", "a fun fact", "fun fact", "a story", "story", "a riddle", "riddle",
}


@dataclass(frozen=True)
class TranslationIntent:
    phrase: str
    language_code: str
    language_name: str


def local_event_translation(phrase: str, language_code: str) -> str | None:
    """Provide a vetted fallback for a small set of frequent event phrases."""
    normalized_phrase = re.sub(r"\s+", " ", (phrase or "").casefold()).strip(" .!?\"'")
    return LOCAL_EVENT_TRANSLATIONS.get((normalized_phrase, language_code))


def translation_only_reply(reply: str) -> str:
    """Keep a translation response to its first spoken sentence."""
    first_line = (reply or "").strip().splitlines()[0] if reply else ""
    match = re.match(r".+?[.!?؟。！]", first_line)
    return (match.group(0) if match else first_line).strip()


def parse_multi_translation_intents(text: str) -> tuple[TranslationIntent, ...]:
    """Parse repeated ``say <phrase> in <language>`` commands in one turn."""
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    matches = re.finditer(
        r"(?:^|,\s*|\band\s+)say\s+(.+?)\s+in\s+"
        r"(arabic|hindi|chinese|mandarin|mandarin chinese)(?=,|\s+and\s+say|[?.!]|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    intents = []
    for match in matches:
        phrase, target = match.groups()
        code = _TARGETS[target.casefold()]
        if phrase.strip():
            intents.append(TranslationIntent(phrase.strip(" '\""), code, LANGUAGE_NAMES[code]))
    return tuple(intents) if len(intents) > 1 else ()


def parse_translation_intent(text: str) -> TranslationIntent | None:
    """Return a requested phrase and supported target language, if explicitly stated."""
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    # Translation replies are intentionally phrase-only. A spoken follow-up such as
    # "and explain when people use it" must not turn an otherwise explicit request
    # into a general conversation request.
    normalized = re.sub(
        r"\s*(?:,?\s*and\s+(?:explain\b.*|when\s+should\s+i\s+use\s+it\b.*))$",
        "", normalized,
        flags=re.IGNORECASE,
    )
    for pattern in _REQUEST_PATTERNS:
        match = re.match(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        phrase, target = match.groups()
        code = _TARGETS.get(target.casefold())
        if phrase.casefold().strip(" .!?\"'") in _CREATIVE_REQUEST_PHRASES:
            return None
        if code and phrase.strip():
            return TranslationIntent(phrase.strip(" '\""), code, LANGUAGE_NAMES[code])
    return None
