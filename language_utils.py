"""Small helpers for choosing one language across the assistant flow."""

import re

LANGUAGE_NAMES = {
    "en": "English",
    "ar": "Arabic",
    "ur": "Urdu",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "ml": "Malayalam",
    "kn": "Kannada",
    "ru": "Russian",
    "uk": "Ukrainian",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "nl": "Dutch",
    "pl": "Polish",
    "ro": "Romanian",
    "el": "Greek",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "fa": "Persian (Dari)",
    "ps": "Pashto",
    "tl": "Tagalog (Filipino)",
    "sw": "Swahili",
    "am": "Amharic",
    "so": "Somali",
    "af": "Afrikaans",
    "ha": "Hausa",
    "ig": "Igbo",
    "yo": "Yoruba",
    "zu": "Zulu",
    "tr": "Turkish",
    "it": "Italian",
    "pt": "Portuguese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}


def detect_script_language(text: str) -> tuple[str, str] | None:
    """Recognize scripts that are more reliable than a conflicting STT label."""
    script_patterns = {
        "ar": r"[\u0600-\u06ff]",
        "hi": r"[\u0900-\u097f]",
        "ru": r"[\u0400-\u04ff]",
        "zh": r"[\u4e00-\u9fff]",
        "ja": r"[\u3040-\u30ff]",
        "ko": r"[\uac00-\ud7af]",
    }
    for code, pattern in script_patterns.items():
        if re.search(pattern, text):
            return code, LANGUAGE_NAMES[code]
    return None


def normalize_language(language_code: str | None) -> tuple[str, str] | None:
    """Return a language code and label, preserving unknown Whisper codes."""
    if not language_code:
        return None
    code = language_code.lower().split("-")[0]
    if not code:
        return None
    return code, LANGUAGE_NAMES.get(code, code.upper())


def detect_language(text: str) -> tuple[str, str]:
    """Return a language code and label, defaulting safely to English."""
    script_language = detect_script_language(text)
    if script_language:
        return script_language
    if len(text.strip()) < 4:
        return "en", "English"

    try:
        from langdetect import DetectorFactory, detect_langs

        DetectorFactory.seed = 0
        result = detect_langs(text)[0]
        if result.prob >= 0.70:
            return normalize_language(result.lang) or ("en", "English")
    except Exception:
        pass
    return "en", "English"


def should_use_previous_language(transcript: str) -> bool:
    """Short replies often do not contain enough speech for reliable detection."""
    return len(transcript.split()) <= 3
