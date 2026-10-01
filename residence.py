"""Local policy for requests that seek a living person's current residence."""

import re


_RESIDENCE_TERMS = r"live|lives|living|reside|resides|residing|home|address|residence|whereabouts|house|apartment"
_REFUSALS = {
    "en": "I can’t help verify someone’s current residence.",
    "es": "No puedo ayudar a verificar la residencia actual de una persona.",
    "fr": "Je ne peux pas aider à vérifier le lieu de résidence actuel d’une personne.",
    "af": "Ek kan nie help om iemand se huidige woonplek te verifieer nie.",
    "pt": "Não posso ajudar a verificar a residência atual de alguém.",
    "ar": "لا أستطيع المساعدة في التحقق من مكان إقامة شخص حاليًا.",
    "ur": "میں کسی کی موجودہ رہائش کی تصدیق میں مدد نہیں کر سکتا۔",
    "fa": "نمی‌توانم در تأیید محل سکونت فعلی یک شخص کمک کنم.",
    "hi": "मैं किसी के वर्तमान निवास की पुष्टि करने में मदद नहीं कर सकता।",
    "zh": "我无法帮助核实某人目前的住所。",
    "ja": "人物の現在の居住地の確認には協力できません。",
}


def is_current_residence_request(text: str) -> bool:
    """Match questions seeking a living person's current home or whereabouts."""
    normalized = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    if not normalized:
        return False

    where_pattern = rf"\bwhere\b.{{0,100}}\b(?:{_RESIDENCE_TERMS})\b"
    direct_pattern = rf"\b(?:address|home address|residence|whereabouts)\b"
    return bool(re.search(where_pattern, normalized) or re.search(direct_pattern, normalized))


def current_residence_refusal(language_code: str) -> str:
    """Return a concise localized refusal, defaulting to the required English text."""
    code = (language_code or "en").lower().split("-")[0]
    return _REFUSALS.get(code, _REFUSALS["en"])
