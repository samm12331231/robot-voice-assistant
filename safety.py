"""Small public-demo safety checks for input and spoken output."""

import os

from dotenv import load_dotenv


load_dotenv()

FALLBACK_MESSAGES = {
    "en": {
        "unclear": "I didn't quite understand that. Could you repeat it again?",
        "safe": "I'm here to help. What would you like to know?",
        "network": "I'm sorry, I can't respond right now. Please try again in a moment.",
    },
    "ar": {
        "unclear": "لم أفهمك جيدًا. هل يمكنك تكرار ذلك من فضلك؟",
        "safe": "أنا هنا للمساعدة. كيف يمكنني مساعدتك؟",
        "network": "عذرًا، لا أستطيع الرد الآن. يرجى المحاولة مرة أخرى بعد قليل.",
    },
    "hi": {
        "unclear": "मैं आपको ठीक से समझ नहीं पाया। क्या आप दोबारा कह सकते हैं?",
        "safe": "मैं मदद के लिए यहाँ हूँ। मैं आपकी कैसे मदद कर सकता हूँ?",
        "network": "माफ़ कीजिए, मैं अभी जवाब नहीं दे सकता। कृपया थोड़ी देर बाद फिर कोशिश करें।",
    },
    "ur": {
        "unclear": "میں آپ کو ٹھیک سے سمجھ نہیں سکا۔ کیا آپ دوبارہ کہہ سکتے ہیں؟",
        "safe": "میں مدد کے لیے یہاں ہوں۔ میں آپ کی کیسے مدد کر سکتا ہوں؟",
        "network": "معذرت، میں ابھی جواب نہیں دے سکتا۔ براہ کرم تھوڑی دیر بعد دوبارہ کوشش کریں۔",
    },
}
SAFE_FALLBACK = FALLBACK_MESSAGES["en"]["safe"]
NETWORK_FALLBACK = FALLBACK_MESSAGES["en"]["network"]
EMERGENCY_BLOCK: list[str] = []


def fallback_message(kind: str, language: str = "en") -> str:
    """Return a localized fallback, with English as the safe default."""
    code = language.lower().split("-")[0]
    return FALLBACK_MESSAGES.get(code, FALLBACK_MESSAGES["en"])[kind]


def _contains_emergency_block(text: str) -> bool:
    lower_text = text.lower()
    return any(term.lower() in lower_text for term in EMERGENCY_BLOCK if term.strip())


def _is_flagged(text: str) -> bool:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    try:
        from openai import OpenAI
        response = OpenAI(api_key=api_key, timeout=8).moderations.create(
            model="omni-moderation-latest", input=text
        )
        return bool(response.results[0].flagged)
    except Exception as error:
        raise RuntimeError(f"Moderation request failed: {error}") from error


def check_transcript(transcript: str) -> bool:
    """Return False for blocked input; network failures remain usable for the demo."""
    if _contains_emergency_block(transcript):
        return False
    try:
        return not _is_flagged(transcript)
    except RuntimeError:
        return True


def check_reply(reply: str, language: str = "en") -> str:
    """Return a safe reply; never speak an unmoderated reply after an API failure."""
    if _contains_emergency_block(reply):
        return fallback_message("safe", language)
    try:
        return fallback_message("safe", language) if _is_flagged(reply) else reply
    except RuntimeError:
        return fallback_message("network", language)


def warm_up_moderation() -> None:
    """Make one harmless request so moderation connection problems appear at startup."""
    _is_flagged("Hello")
