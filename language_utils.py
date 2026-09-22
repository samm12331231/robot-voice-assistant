"""Small helpers for choosing one language across the assistant flow."""

LANGUAGE_NAMES = {
    "en": "English",
    "ar": "Arabic",
    "hi": "Hindi",
    "ru": "Russian",
}


def normalize_language(language_code: str | None) -> tuple[str, str] | None:
    """Return one supported language, or ``None`` for an unsupported code."""
    if not language_code:
        return None
    code = language_code.lower().split("-")[0]
    if code not in LANGUAGE_NAMES:
        return None
    return code, LANGUAGE_NAMES[code]


def detect_language(text: str) -> tuple[str, str]:
    """Return a language code and label, defaulting safely to English."""
    if len(text.strip()) < 4:
        return "en", "English"

    try:
        from langdetect import DetectorFactory, detect_langs

        DetectorFactory.seed = 0
        result = detect_langs(text)[0]
        if result.prob < 0.70:
            return "en", "English"
        code = result.lang
    except Exception:
        return "en", "English"

    return normalize_language(code) or ("en", "English")
