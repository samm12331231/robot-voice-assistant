"""Small public-demo safety checks for input and spoken output."""

import os
import re

from dotenv import load_dotenv
from fallback_messages import fallback_message


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
    "zh": {
        "unclear": "我没听清楚，抱歉。您能再说一遍吗？",
        "safe": "我随时为您提供帮助。您想了解什么？",
        "network": "抱歉，我现在无法回答。请稍后再试。",
    },
}
SAFE_FALLBACK = FALLBACK_MESSAGES["en"]["safe"]
NETWORK_FALLBACK = FALLBACK_MESSAGES["en"]["network"]
EMERGENCY_BLOCK: list[str] = []


def _is_harmless_meaning_question(text: str) -> bool:
    """Allow educational definitions without treating a quoted rude word as abuse."""
    normalized = " ".join((text or "").casefold().split())
    return bool(re.match(
        r"^(?:what does|what is the meaning of|what's the meaning of|define|meaning of)\b.+\b(?:mean|meaning)(?:\s+in\s+[\w\s]+)?\??$",
        normalized,
    ))


def _is_non_actionable_fictional_request(text: str) -> bool:
    """Allow clearly fictional prompts that explicitly reject real-world usability."""
    normalized = " ".join((text or "").casefold().split())
    return (
        "fictional" in normalized
        and bool(re.search(r"\b(?:villain|story|character|plot)\b", normalized))
        and bool(re.search(r"\b(?:not|without)\b.*\b(?:actionable|usable|real life)\b", normalized))
    )


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
    if _is_harmless_meaning_question(transcript):
        return True
    if _is_non_actionable_fictional_request(transcript):
        return True
    try:
        return not _is_flagged(transcript)
    except RuntimeError:
        return True


def check_reply(reply: str, language: str = "en", _diagnostic_id: str = "") -> str:
    """Return a safe reply; never speak an unmoderated reply after an API failure.
    
    Args:
        reply: The text to check for safety
        language: Language code for fallback messages
        _diagnostic_id: Internal ID for diagnostic logging (do not set externally)
    
    Returns:
        Safe reply text or fallback message
    """
    diag_tag = f"[SAFETY::{_diagnostic_id}]" if _diagnostic_id else "[SAFETY]"
    
    if _contains_emergency_block(reply):
        fallback = fallback_message("safe", language)
        print(f"{diag_tag} EMERGENCY_BLOCK triggered → fallback")
        return fallback
    
    try:
        flagged = _is_flagged(reply)
        if flagged:
            fallback = fallback_message("safe", language)
            print(f"{diag_tag} MODERATION_FLAG (reply truncated to 80 chars)")
            print(f"{diag_tag}   LLM reply: {reply[:80]}...")
            print(f"{diag_tag}   Fallback:  {fallback[:80]}...")
            return fallback
        else:
            print(f"{diag_tag} MODERATION_PASS (reply truncated to 80 chars)")
            print(f"{diag_tag}   Reply: {reply[:80]}...")
            return reply
    except RuntimeError as error:
        fallback = fallback_message("network", language)
        print(f"{diag_tag} MODERATION_ERROR: {type(error).__name__}")
        print(f"{diag_tag}   Network fallback used")
        return fallback


def warm_up_moderation() -> None:
    """Make one harmless request so moderation connection problems appear at startup."""
    _is_flagged("Hello")
