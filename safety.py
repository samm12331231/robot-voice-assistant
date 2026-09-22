"""Small public-demo safety checks for input and spoken output."""

import os

from dotenv import load_dotenv


load_dotenv()

SAFE_FALLBACK = "I'm here to help with respectful questions. What would you like to know?"
NETWORK_FALLBACK = "I'm sorry, I can't respond right now. Please try again in a moment."
EMERGENCY_BLOCK: list[str] = []


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


def check_reply(reply: str) -> str:
    """Return a safe reply; never speak an unmoderated reply after an API failure."""
    if _contains_emergency_block(reply):
        return SAFE_FALLBACK
    try:
        return SAFE_FALLBACK if _is_flagged(reply) else reply
    except RuntimeError:
        return NETWORK_FALLBACK


def warm_up_moderation() -> None:
    """Make one harmless request so moderation connection problems appear at startup."""
    _is_flagged("Hello")
