"""Small helpers for choosing one language across the assistant flow."""

import re
import unicodedata

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

EVENT_LANGUAGE_MODE = "event_en_ar_hi_zh"
EVENT_SUPPORTED_LANGUAGE_CODES = frozenset({"en", "ar", "hi", "zh"})
EVENT_LANGUAGE_MESSAGES = {
    "en": "I can speak English, Arabic, Hindi, and Chinese.",
    "ar": "أدعم حاليًا الإنجليزية والعربية والهندية والصينية المندرينية.",
    "hi": "मैं वर्तमान में अंग्रेज़ी, अरबी, हिंदी और मंदारिन चीनी का समर्थन करता हूँ।",
    "zh": "我目前支持英语、阿拉伯语、印地语和简体中文。",
}
EVENT_LANGUAGE_CAPABILITY_REPLIES = {
    "en": "Yes, I can speak English. Hello!",
    "ar": "نعم، أستطيع التحدث بالعربية. مرحبًا!",
    "hi": "हाँ, मैं हिंदी बोल सकता हूँ। नमस्ते!",
    "zh": "是的，我会说普通话。你好！",
}
EVENT_LANGUAGE_CAPABILITY_NAMES = {
    "english": "en",
    "arabic": "ar",
    "hindi": "hi",
    "chinese": "zh",
    "mandarin": "zh",
    "mandarin chinese": "zh",
}
EVENT_LANGUAGE_REQUEST_CODES = {
    **EVENT_LANGUAGE_CAPABILITY_NAMES,
    "french": "fr", "spanish": "es", "urdu": "ur", "persian": "fa",
    "dari": "fa", "bengali": "bn", "malayalam": "ml", "japanese": "ja",
    "italian": "it", "finnish": "fi", "afrikaans": "af", "somali": "so",
    "indonesian": "id",
}
EVENT_LANGUAGE_GENERIC_REPLIES = {
    "en": "Yes, I can help in English. What would you like me to say or explain?",
    "ar": "نعم، أستطيع المساعدة بالعربية. ماذا تريد أن أقول أو أشرح؟",
    "hi": "हाँ, मैं हिंदी में मदद कर सकता हूँ। आप क्या कहलवाना या समझाना चाहते हैं?",
    "zh": "是的，我可以用中文帮忙。您想让我说什么或解释什么？",
}
EVENT_LANGUAGE_RESET_REPLIES = {
    "en": "Okay, I'll answer in English.",
    "ar": "حسنًا، سأجيب بالعربية.",
    "hi": "ठीक है, मैं हिंदी में जवाब दूँगा।",
    "zh": "好的，我会用中文回答。",
}
PHYSICAL_ACTION_UNAVAILABLE_REPLIES = {
    "en": "I can't change my volume, move closer, or wave, but I can answer your questions.",
    "ar": "لا أستطيع تغيير مستوى الصوت أو الاقتراب أو التلويح، لكن يمكنني الإجابة عن أسئلتك.",
    "hi": "मैं आवाज़ बदल नहीं सकता, पास नहीं आ सकता और हाथ नहीं हिला सकता, लेकिन मैं आपके सवालों का जवाब दे सकता हूँ।",
    "zh": "我不能调节音量、靠近或挥手，但我可以回答您的问题。",
}
PUBLIC_EVENT_JOKES = {
    "en": "Why did the robot bring a map? It did not want to lose its way!",
    "ar": "لماذا أحضر الروبوت خريطة؟ لأنه لا يريد أن يضيع طريقه!",
    "hi": "रोबोट नक्शा क्यों लाया? क्योंकि वह रास्ता नहीं भूलना चाहता था!",
    "zh": "机器人为什么带地图？因为它不想迷路！",
}
EVENT_UNSAFE_LANGUAGE_REPLIES = {
    "en": "I can help in English, Arabic, Hindi, and Chinese, but I can't help with insults or harmful language.",
    "ar": "يمكنني المساعدة بالإنجليزية والعربية والهندية والصينية، لكن لا أستطيع المساعدة في الإهانات أو اللغة المؤذية.",
    "hi": "मैं अंग्रेज़ी, अरबी, हिंदी और चीनी में मदद कर सकता हूँ, लेकिन अपमान या हानिकारक भाषा में मदद नहीं कर सकता।",
    "zh": "我可以用英语、阿拉伯语、印地语和中文提供帮助，但不能帮助进行侮辱或使用有害语言。",
}

CURRENT_FACT_PATTERNS = (
    r"\bwho is the (?:current )?(?:president|prime minister)\b",
    r"\b(?:current|latest|exact current) (?:price|value) of\b",
    r"\bwhat happened in (?:the )?news today\b",
    r"\b(?:latest|today'?s) news\b",
)


def resolve_self_correction(text: str) -> str:
    """Return the corrected request when a visitor explicitly abandons one subject."""
    normalized = " ".join((text or "").split()).strip()
    match = re.match(
        r"^(?P<before>.+?)[.?!]*\s*(?:sorry|wait)\s*,?\s*i meant\s+(?P<after>.+?)[.?!]*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return normalized

    before = match.group("before").strip(" .?!")
    correction = match.group("after").strip(" .?!")
    if re.match(r"^(?:what|who|where|when|why|how|tell|give|explain)\b", correction, re.IGNORECASE):
        return f"{correction}?"
    question = re.match(r"^(?P<stem>.*?\b(?:of|in|for)\s+).+$", before, re.IGNORECASE)
    return f"{question.group('stem')}{correction}?" if question else correction


def requires_verified_current_information(text: str) -> bool:
    """Identify facts that must not be answered from a model's stale memory."""
    normalized = (text or "").casefold()
    return any(re.search(pattern, normalized) for pattern in CURRENT_FACT_PATTERNS)


def is_event_language_mode(mode: str | None) -> bool:
    """Return whether the configured public-event language restriction is active."""
    return (mode or "").strip().casefold() == EVENT_LANGUAGE_MODE


def event_supported_language_message(language_code: str) -> str:
    """Return the concise local event-language availability message."""
    return EVENT_LANGUAGE_MESSAGES.get(language_code, EVENT_LANGUAGE_MESSAGES["en"])


def event_language_policy_reply(text: str) -> tuple[str, str] | None:
    """Answer direct event-language or Arabic-dialect questions without LLM drift."""
    normalized = (text or "").casefold()
    if "dialect" in normalized and "arabic" in normalized:
        return (
            "en",
            "I use Modern Standard Arabic. I can speak English, Arabic, Hindi, and Mandarin Chinese.",
        )
    return None


def event_language_capability_reply(text: str) -> tuple[str, str] | None:
    """Handle a safe, explicit request to speak one event-supported language."""
    normalized = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    if not re.search(r"\b(?:can|could)\s+you\s+(?:talk|speak|communicate)\b", normalized):
        return None
    if re.search(r"\b(?:curse|insult|swear|offensive|derogatory|make fun of)\b", normalized):
        return None
    for name, code in sorted(EVENT_LANGUAGE_CAPABILITY_NAMES.items(), key=lambda item: -len(item[0])):
        match = re.search(rf"\b(?:in\s+)?{re.escape(name)}\b", normalized)
        if match and normalized[match.end():].strip(" ?!.,") in {"", "please", "thanks"}:
            return code, EVENT_LANGUAGE_CAPABILITY_REPLIES[code]
    return None


def event_unsafe_language_request_reply(text: str) -> tuple[str, str] | None:
    """Refuse harmful language requests in the explicitly requested language."""
    normalized = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    if not re.search(r"\b(?:curse|insult\w*|swear|offensiv\w*|derogator\w*|make fun of)\b", normalized):
        return None
    if not re.search(
        r"\b(?:talk|speak|communicate|say|tell|translate|make|make\s+fun\s+of)\b",
        normalized,
    ):
        return None
    for name, code in sorted(EVENT_LANGUAGE_CAPABILITY_NAMES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b(?:in|talk|speak|communicate)\s+{re.escape(name)}\b", normalized):
            return code, EVENT_UNSAFE_LANGUAGE_REPLIES[code]
    return None


def event_requested_language_code(text: str) -> str | None:
    """Extract a named language from a can/could-you request without guessing."""
    normalized = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    if not re.search(r"\b(?:can|could)\s+you\b", normalized):
        return None
    for name, code in sorted(EVENT_LANGUAGE_REQUEST_CODES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b(?:in\s+)?{re.escape(name)}\b", normalized):
            return code
    return None


def event_generic_language_reply(text: str) -> tuple[str, str] | None:
    """Confirm generic can/could-you requests in a supported target language."""
    normalized = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    for name, code in sorted(EVENT_LANGUAGE_CAPABILITY_NAMES.items(), key=lambda item: -len(item[0])):
        if code not in EVENT_SUPPORTED_LANGUAGE_CODES:
            continue
        pattern = (
            rf"^(?:can|could)\s+you\s+(?:say|do)\s+(?:this|that|it)\s+in\s+{re.escape(name)}"
            rf"[?!.]*$|^(?:can|could)\s+you\s+explain\s+(?:me\s+)?(?:this|that|it)\s+in\s+{re.escape(name)}[?!.]*$"
        )
        if re.fullmatch(pattern, normalized):
            return code, EVENT_LANGUAGE_GENERIC_REPLIES[code]
    return None


def event_language_reset_reply(text: str) -> tuple[str, str] | None:
    """Acknowledge a request to stop translating without invoking stale history."""
    normalized = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    if not re.search(r"\b(?:stop translating|answer normally|reply normally)\b", normalized):
        return None
    for name, code in sorted(EVENT_LANGUAGE_CAPABILITY_NAMES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b(?:in\s+)?{re.escape(name)}\b", normalized):
            return code, EVENT_LANGUAGE_RESET_REPLIES[code]
    return None


def strip_event_reply_language_suffix(text: str) -> str:
    """Remove a final supported-language wording clause before a live lookup.

    For example, the location in ``weather in Dubai in Arabic`` is Dubai;
    Arabic specifies the reply language rather than part of the place name.
    """
    normalized = (text or "").strip()
    names = "|".join(
        re.escape(name)
        for name in sorted(EVENT_LANGUAGE_CAPABILITY_NAMES, key=len, reverse=True)
    )
    normalized = re.sub(
        rf"\s*(?:[?!.]\s*)?(?:reply|answer|say\s+it)\s+in\s+(?:{names})\s*[?!.]*\s*$",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    return re.sub(rf"\s+in\s+(?:{names})\s*[?!.]*\s*$", "", normalized, flags=re.IGNORECASE)


def event_requested_reply_language(text: str) -> tuple[str, str] | None:
    """Recognize a safe request for a normal reply in one supported event language."""
    normalized = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    if re.search(r"\b(?:curse|insult\w*|swear|offensiv\w*|derogator\w*|make fun of)\b", normalized):
        return None
    if not re.search(
        r"\b(?:joke|say|say something|reply|respond|answer|explain|talk|speak|communicate|tell me|give me|show me|"
        r"compliment|mean\s+in|weather|time)\b",
        normalized,
    ):
        return None
    names = "|".join(
        re.escape(name) for name in sorted(EVENT_LANGUAGE_CAPABILITY_NAMES, key=len, reverse=True)
    )
    target = re.search(
        rf"\b(?:say|reply|respond|answer|explain|talk|speak|communicate)\b.*?\bin\s+(?P<language>{names})\b",
        normalized,
    )
    if target:
        code = EVENT_LANGUAGE_CAPABILITY_NAMES[target.group("language")]
        return code, LANGUAGE_NAMES[code]
    for name, code in sorted(EVENT_LANGUAGE_CAPABILITY_NAMES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b(?:in|mean\s+in)\s+{re.escape(name)}\b", normalized):
            return code, LANGUAGE_NAMES[code]
    return None


def event_multi_response_languages(text: str) -> tuple[tuple[str, str], tuple[str, str]] | None:
    """Parse an answer plus summary request that names two event languages."""
    normalized = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    names = "|".join(
        re.escape(name) for name in sorted(EVENT_LANGUAGE_CAPABILITY_NAMES, key=len, reverse=True)
    )
    match = re.search(
        rf"\b(?:answer|reply|respond|explain)\b.*?\bin\s+(?P<first>{names})\b"
        rf"\s*,?\s*(?:then|and then)\s+(?P<action>summarize|summary)\b.*?\bin\s+(?P<second>{names})\b",
        normalized,
    )
    if not match:
        return None
    return (
        ("answer", EVENT_LANGUAGE_CAPABILITY_NAMES[match.group("first")]),
        ("summarize", EVENT_LANGUAGE_CAPABILITY_NAMES[match.group("second")]),
    )


KNOWN_LOCATION_MENTIONS = {
    "abu dhabi": "abu dhabi", "أبوظبي": "abu dhabi", "ابوظبي": "abu dhabi",
    "fujairah": "fujairah", "الفجيرة": "fujairah",
    "dubai": "dubai", "دبي": "dubai", "دبئی": "dubai",
    "tokyo": "tokyo", "طوكيو": "tokyo",
    "london": "london", "لندن": "london",
    "cairo": "cairo", "القاهرة": "cairo",
    "mumbai": "mumbai", "मुंबई": "mumbai",
    "tehran": "tehran", "تهران": "tehran",
}
LANGUAGE_LOCATION_BLACKLIST = frozenset({
    "english", "arabic", "hindi", "chinese", "mandarin", "mandarin chinese", "urdu",
    "french", "spanish", "german", "russian", "japanese", "korean",
    "italian", "portuguese", "dutch", "bengali", "persian", "dari",
    "pashto", "tagalog", "filipino", "swahili", "amharic", "somali",
    "afrikaans", "turkish", "malayalam", "tamil", "telugu", "marathi",
    "gujarati", "punjabi", "kannada", "ukrainian", "polish", "romanian",
    "greek", "swedish", "norwegian", "danish", "finnish", "indonesian",
    "عربي", "عربية", "بالعربية", "هندي", "هندية", "بالهندية",
    "صيني", "صينية", "بالصينية", "انجليزي", "إنجليزية", "بالانجليزية", "اردو",
})


def _extract_live_clause_info(clause: str, names: str) -> tuple[str | None, str | None, str | None]:
    """Extract (kind, location, language_code) from a single clause of a mixed request."""
    norm = clause.casefold().strip()
    kind = None
    if re.search(r"\b(?:weather|temperature)\b", norm):
        kind = "weather"
    elif re.search(r"\b(?:time|clock)\b", norm):
        kind = "time"

    lang = None
    lang_match = re.search(rf"\b(?:both\s+in\s+|both\s+|in\s+)?({names})\b[?.!]*$", norm)
    if not lang_match:
        lang_match = re.search(rf"\b(?:both\s+in\s+|in\s+)({names})\b", norm)
    if lang_match:
        lang = EVENT_LANGUAGE_CAPABILITY_NAMES.get(lang_match.group(1))

    loc = None
    if re.search(r"\b(?:there|that place|that city|the same place)\b", norm):
        loc = "__THERE__"
    else:
        for mention, location in sorted(KNOWN_LOCATION_MENTIONS.items(), key=lambda item: -len(item[0])):
            if re.search(rf"(?<!\w){re.escape(mention)}(?!\w)", norm):
                loc = location
                break
        if not loc:
            loc_match = re.search(
                r"\b(?:in|at|for|near)\s+([a-zA-Z\s]+?)(?=\s+(?:in|both|there|today|now|right now)\b|[?!.,;]|$)",
                norm,
            )
            if loc_match:
                cand = loc_match.group(1).strip().casefold()
                if cand not in EVENT_LANGUAGE_CAPABILITY_NAMES and cand not in LANGUAGE_LOCATION_BLACKLIST:
                    loc = cand
    return kind, loc, lang


def event_mixed_live_request(
    text: str,
    previous_live_info: dict | None = None,
) -> tuple[str, tuple[str, str], str, tuple[str, str]] | None:
    """Parse a time and weather request that asks for two supported reply languages.

    Returns (loc1, (kind1, lang1), loc2, (kind2, lang2)) preserving the exact
    requested order of the clauses.
    """
    normalized = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    names = "|".join(
        re.escape(name) for name in sorted(EVENT_LANGUAGE_CAPABILITY_NAMES, key=len, reverse=True)
    )

    # 1. Handle conjoined requests like "time and the weather in Dubai in Arabic"
    shared_match = re.search(
        rf"\b(?:(?P<t_first>time)\s+and\s+(?:the\s+)?weather|(?P<w_first>weather)\s+and\s+(?:the\s+)?time)\s+in\s+(.+?)\s+in\s+({names})\b",
        normalized,
    )
    if shared_match:
        first_kind = "weather" if shared_match.group("w_first") else "time"
        second_kind = "time" if first_kind == "weather" else "weather"
        location = shared_match.group(3).strip(" ,?.!")
        code = EVENT_LANGUAGE_CAPABILITY_NAMES[shared_match.group(4)]
        return location, (first_kind, code), location, (second_kind, code)

    # Handle the same shared request when no reply language is specified.
    shared_no_language_match = re.search(
        r"\b(?:(?P<t_first>time)\s+and\s+(?:the\s+)?weather|"
        r"(?P<w_first>weather)\s+and\s+(?:the\s+)?time)\s+in\s+(.+?)\s*$",
        normalized,
    )
    if shared_no_language_match:
        first_kind = "weather" if shared_no_language_match.group("w_first") else "time"
        second_kind = "time" if first_kind == "weather" else "weather"
        location = shared_no_language_match.group(3).strip(" ,?.!")
        return location, (first_kind, "en"), location, (second_kind, "en")

    # 2. Split into two clauses
    parts = re.split(
        r",?\s*(?:and|or|then|but|while)\s+|,\s*(?=(?:the\s+)?(?:time|weather)\b)",
        normalized,
        maxsplit=1,
    )
    if len(parts) != 2:
        return None

    k1, l1, g1 = _extract_live_clause_info(parts[0], names)
    k2, l2, g2 = _extract_live_clause_info(parts[1], names)

    if not (k1 and k2 and k1 != k2):
        return None

    # Preserve a final same-language suffix like "... and ... in Arabic" when the
    # request clearly applies to both clauses. Otherwise, default each missing clause
    # independently instead of copying an explicit language from one side to the other.
    sentence_lang_match = re.search(
        rf"(?:time|weather)\s+in\s+.+?(?:and|or|then|but|while)\s+(?:the\s+)?(?:time|weather)\s+in\s+.+?\s+in\s+({names})\b",
        normalized,
    )
    if sentence_lang_match:
        shared_code = EVENT_LANGUAGE_CAPABILITY_NAMES[sentence_lang_match.group(1)]
        if not g1:
            g1 = shared_code
        if not g2:
            g2 = shared_code
    elif not g1 and not g2:
        g1 = g2 = "en"
    elif not g1:
        g1 = "en"
    elif not g2:
        g2 = "en"
    if not (g1 and g2):
        return None

    # Resolve location and pronoun "there" without inventing a city.
    remembered_location = (previous_live_info or {}).get("location") if previous_live_info else None

    if l1 == "__THERE__" and l2 == "__THERE__":
        if remembered_location:
            l1 = l2 = remembered_location
        else:
            return None
    if l1 == "__THERE__":
        if remembered_location and not l2:
            l1 = remembered_location
        elif not l2 or l2 == "__THERE__":
            return None
        else:
            l1 = l2
    if l2 == "__THERE__":
        if remembered_location and not l1:
            l2 = remembered_location
        elif not l1 or l1 == "__THERE__":
            return None
        else:
            l2 = l1
    if not l1:
        l1 = l2
    if not l2:
        l2 = l1
    if not (l1 and l2):
        return None

    return l1.strip(" ,?.!"), (k1, g1), l2.strip(" ,?.!"), (k2, g2)


def arabic_hindi_then_arabic_time_request(text: str) -> bool:
    """Recognize an Arabic request to state the current time in Hindi then Arabic."""
    normalized = (text or "").casefold()
    has_time = any(phrase in normalized for phrase in ("الوقت", "الساعة", "شنو الوقت"))
    has_weather = any(phrase in normalized for phrase in ("الطقس", "موسم"))
    return has_time and not has_weather and "هندي" in normalized and "عربي" in normalized


def arabic_hindi_time_arabic_weather_request(text: str) -> bool:
    """Recognize Hindi-time then Arabic-weather requests spoken in Arabic."""
    normalized = (text or "").casefold()
    has_time = any(phrase in normalized for phrase in ("الوقت", "الساعة", "شنو الوقت"))
    has_weather = any(phrase in normalized for phrase in ("الطقس", "موسم"))
    return has_time and has_weather and "هندي" in normalized and "عربي" in normalized


def arabic_request_time_first(text: str) -> bool:
    """Return True if the Arabic request asks for time before weather."""
    normalized = (text or "").casefold()
    time_pos = min(
        (normalized.find(w) for w in ("الوقت", "الساعة", "شنو الوقت", "وقت") if w in normalized),
        default=len(normalized),
    )
    weather_pos = min(
        (normalized.find(w) for w in ("الطقس", "موسم", "حرارة") if w in normalized),
        default=len(normalized),
    )
    return time_pos <= weather_pos


def physical_action_unavailable_reply(text: str, language_code: str) -> str | None:
    """State the robot's current physical limits instead of promising an action."""
    normalized = (text or "").casefold()
    if not re.search(
        r"\b(?:turn\s+(?:the\s+)?volume\s+up|(?:make|set)\s+(?:the\s+)?volume\s+up|"
        r"move\s+closer|come\s+closer|wave\s+(?:at|to)|can\s+you\s+wave|"
        r"(?:make|set)\s+(?:the\s+)?volume\s+louder|volume\s+louder)\b",
        normalized,
    ):
        return None
    if re.search(r"\b(?:what|why|how|explain|tell me)\b", normalized):
        return None
    return PHYSICAL_ACTION_UNAVAILABLE_REPLIES.get(
        language_code, PHYSICAL_ACTION_UNAVAILABLE_REPLIES["en"]
    )


def public_event_joke_reply(text: str, language_code: str) -> str | None:
    """Return one short, pre-approved joke if moderation rejects a benign model joke."""
    if not re.search(r"\bjokes?\b", (text or "").casefold()):
        return None
    return PUBLIC_EVENT_JOKES.get(language_code)

SHORT_ENGLISH_PHRASES = {
    "hello", "hello hello", "hi", "hey",
    "how are you", "what is your name",
    "can you dance", "can you wave", "come here",
    "what's your name",
    "hello how are you",
    "lets kiss",
    "let's kiss",
    "lets dance",
    "let's dance",
    "i love this",
}
COMPANY_FACT_TERMS = (
    "founder", "ceo", "chief executive", "coo", "chief operating", "cto",
    "chief technology", "leadership", "leader", "staff", "employee", "employees",
    "product", "products", "headquarters", "located", "location", "based in",
    "event details", "does", "do", "build", "make", "description", "describe",
    "office", "address", "phone", "contact", "email", "website",
)
COMPANY_REFERENCE_TERMS = (
    "company", "corporation", "corp", "inc", "ltd", "llc", "robotics",
    "startup", "organization", "organisation",
)
COMPANY_FACTS_UNAVAILABLE = {
    "en": "I don’t have verified information about that company right now.",
    "ar": "ليس لدي معلومات موثقة عن تلك الشركة الآن.",
    "hi": "मैं अभी उस कंपनी की जानकारी सत्यापित नहीं कर सकता।",
    "ur": "میں ابھی کمپنی کی معلومات کی تصدیق نہیں کر سکتا۔",
}
SCRIPT_MARKERS = {
    "ps": "ټډړڼګښږڅځېۍ",
    "ur": "ٹڈڑںھہۃےۓ",
    "fa": "پچژگڤگک",
}
AMBIGUOUS_BORROWED_GREETING_TOKENS = {"ہیلو", "هلو", "هيلو"}
ARABIC_GREETING_PHRASES = {"السلام عليكم", "كيف حالك"}
ENGLISH_ACKNOWLEDGEMENTS = {
    "yes", "no", "yeah", "yep", "okay", "ok", "sure", "thanks", "thank you",
}


def detect_short_english(text: str) -> tuple[str, str] | None:
    """Recognize a few common short English social requests safely."""
    normalized = text.casefold().replace("’", "'").replace("‘", "'")
    normalized = re.sub(r"[^\w\s']", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in SHORT_ENGLISH_PHRASES:
        return "en", LANGUAGE_NAMES["en"]
    return None


def _is_ambiguous_borrowed_greeting(text: str) -> bool:
    """Only isolated greeting-only transliterations are genuinely uncertain."""
    if not text:
        return False
    normalized = re.sub(r"[^\w\s]", " ", text.casefold())
    tokens = normalized.split()
    if not tokens or len(tokens) > 2:
        return False
    allowed = {"hello", "hi", "hey", "halo", "hallo"} | AMBIGUOUS_BORROWED_GREETING_TOKENS
    return all(token in allowed for token in tokens)


def _normalized_arabic_greeting_text(text: str) -> str:
    """Normalize only glyph variants relevant to common Arabic greeting phrases."""
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = re.sub(r"[\u064b-\u065f\u0670]", "", normalized)
    normalized = normalized.translate(str.maketrans({"ی": "ي", "ى": "ي", "ے": "ي", "ک": "ك"}))
    return re.sub(r"[^\u0600-\u06ff\s]", " ", normalized).strip()


def detect_arabic_greeting(text: str) -> tuple[str, str] | None:
    """Recognize specific Arabic greetings before broader Persian/Urdu script routing."""
    normalized = _normalized_arabic_greeting_text(text)
    if any(re.search(rf"(?<!\S){re.escape(phrase)}(?!\S)", normalized) for phrase in ARABIC_GREETING_PHRASES):
        return "ar", LANGUAGE_NAMES["ar"]
    return None


ENGLISH_GRAMMAR_WORDS = {
    "am", "is", "are", "was", "were", "do", "does", "did", "can", "could",
    "will", "would", "should", "have", "has", "had", "tell", "give", "show",
    "help", "say", "come", "go", "live", "sounds", "what", "how", "where", "made",
    "like",
}
ENGLISH_COMMON_WORDS = {
    "i", "you", "he", "she", "it", "we", "they", "my", "your", "his", "her",
    "our", "their", "the", "a", "an", "this", "that", "what", "how", "where",
    "when", "why", "who", "to", "of", "for", "with", "and", "but", "please",
    "tell", "me", "joke", "time", "today", "happy", "help", "want", "need",
    "about", "like", "in", "right", "now", "talking", "weather", "there", "another",
    "what", "time", "we", "not", "worry", "understand", "yeah", "good", "really",
    "cool", "no", "think", "so", "again", "explain", "could", "that", "sounds", "lot",
}
ENGLISH_CONTRACTIONS = {
    "i'm": ("i", "am"), "you're": ("you", "are"), "we're": ("we", "are"),
    "they're": ("they", "are"), "he's": ("he", "is"), "she's": ("she", "is"),
    "it's": ("it", "is"), "that's": ("that", "is"), "what's": ("what", "is"),
    "there's": ("there", "is"), "i've": ("i", "have"), "we've": ("we", "have"),
    "they've": ("they", "have"), "i'll": ("i", "will"), "we'll": ("we", "will"),
    "they'll": ("they", "will"), "don't": ("do", "not"), "doesn't": ("does", "not"),
    "didn't": ("did", "not"), "can't": ("can", "not"), "won't": ("will", "not"),
    "isn't": ("is", "not"), "aren't": ("are", "not"), "wasn't": ("was", "not"),
    "weren't": ("were", "not"), "haven't": ("have", "not"), "hasn't": ("has", "not"),
}


def has_confident_english_evidence(text: str) -> bool:
    """Require several English words and a grammar cue before correcting a weak label."""
    letters = [character for character in text if character.isalpha()]
    if not letters or any("LATIN" not in unicodedata.name(char, "") for char in letters):
        return False

    normalized = text.casefold().replace("’", "'").replace("‘", "'")
    raw_tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", normalized)
    tokens = [
        word
        for token in raw_tokens
        for word in ENGLISH_CONTRACTIONS.get(token, (token,))
    ]
    words = set(tokens)
    evidence_words = ENGLISH_COMMON_WORDS | ENGLISH_GRAMMAR_WORDS
    short_english_clause = bool(re.search(
        r"\b(?:can\s+you|could\s+you|can\s+i|could\s+i|tell\s+me|are\s+you)\s+[a-z]",
        normalized,
    ))
    # Requiring multiple function/common words plus a grammar cue avoids using
    # a detector label as the deciding signal for natural English clauses.
    can_i_question = bool(re.search(r"\bcan\s+i\s+[a-z]", normalized))
    counting_greeting = (
        "hello" in words
        and len(words & {"one", "two", "three", "four", "five"}) >= 2
    )
    return (
        can_i_question
        or counting_greeting
        or short_english_clause
        or (
        len(tokens) >= 3
        and len(words & evidence_words) >= 3
        and bool(words & ENGLISH_GRAMMAR_WORDS)
        )
    )


def choose_reply_language(
    transcript: str,
    stt_language: str | None,
    previous_language: str | None,
    default_language: str = "en",
) -> tuple[tuple[str, str], bool]:
    """Prefer script and strong grammar evidence before probabilistic language labels."""
    default_result = normalize_language(default_language) or ("en", "English")
    cleaned = re.sub(r"[^\w\s]", " ", (transcript or "").casefold()).strip()
    if not cleaned:
        return default_result, True

    cleaned = re.sub(r"\s+", " ", cleaned)

    english_result = detect_short_english(transcript)
    if _is_ambiguous_borrowed_greeting(transcript) and not english_result:
        return default_result, True

    arabic_greeting = detect_arabic_greeting(transcript)
    if arabic_greeting:
        return arabic_greeting, False

    script_result = detect_script_language(transcript)
    if script_result:
        return script_result, False

    if cleaned in {"hola", "hola hola"}:
        return ("es", "Spanish"), False
    if cleaned == "bonjour":
        return ("fr", "French"), False

    previous_result = normalize_language(previous_language)
    if cleaned in ENGLISH_ACKNOWLEDGEMENTS:
        return previous_result or default_result, False

    if has_confident_english_evidence(transcript):
        return ("en", LANGUAGE_NAMES["en"]), False

    if english_result:
        return english_result, False

    letters = [character for character in transcript if character.isalpha()]
    if len(cleaned.split()) == 1 and letters and all(
        "LATIN" in unicodedata.name(char, "") for char in letters
    ):
        return previous_result or default_result, True

    text_result = detect_language_confident(transcript)
    whisper_result = normalize_language(stt_language)

    if text_result and whisper_result and text_result[0] != whisper_result[0]:
        return text_result, False
    if text_result:
        return text_result, False
    if whisper_result:
        return whisper_result, False
    if previous_result:
        return previous_result, False
    return default_result, False


def is_company_fact_request(text: str) -> bool:
    """Return whether a message asks for a specific company's factual details."""
    normalized = re.sub(r"\s+", " ", text.casefold()).strip()
    has_fact_term = any(
        re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized)
        for term in COMPANY_FACT_TERMS
    )
    has_company_reference = any(
        re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized)
        for term in COMPANY_REFERENCE_TERMS
    )
    has_named_subject = bool(re.search(
        r"\b(?:of|at|for)\s+(?:the\s+)?[A-Z][\w-]*(?:\s+[A-Z][\w-]*)*",
        text,
    ))
    has_named_company = bool(re.search(
        r"\b(?:[A-Z][\w-]*\s+){0,3}"
        r"(?:Robotics|Robot|Technologies|Technology|Solutions|Systems|Inc|Ltd|LLC)\b",
        text,
    ))
    has_company_question_form = bool(re.match(
        r"(?:what|who|where|how|tell)\b", normalized
    ))
    has_arabic_company_question = "شركة" in normalized and bool(re.search(r"[\u0600-\u06ff]", text))
    return (
        (has_fact_term and (
            has_company_reference
            or has_named_company
            or (has_named_subject and has_company_question_form)
        ))
        or (has_named_company and bool(re.search(r"\b(?:what|who|where|how|does|do|tell|describe)\b", normalized)))
        or has_arabic_company_question
    )


def company_facts_unavailable(language_code: str) -> str:
    """Return the localized refusal used when company facts cannot be verified."""
    code = language_code.lower().split("-")[0]
    return COMPANY_FACTS_UNAVAILABLE.get(code, COMPANY_FACTS_UNAVAILABLE["en"])


def detect_script_language(text: str) -> tuple[str, str] | None:
    """Return script-based language hints for full sentences, while greeting-only ambiguity stays uncertain."""
    script_patterns = {
        "ja": r"[\u3040-\u30ff]",
        "ko": r"[\uac00-\ud7af]",
        "hi": r"[\u0900-\u097f]",
        "bn": r"[\u0980-\u09ff]",
        "ml": r"[\u0d00-\u0d7f]",
    }
    for code, pattern in script_patterns.items():
        if re.search(pattern, text):
            return code, LANGUAGE_NAMES[code]

    for code, markers in (("ur", SCRIPT_MARKERS["ur"]), ("fa", SCRIPT_MARKERS["fa"]), ("ps", SCRIPT_MARKERS["ps"])):
        if any(marker in text for marker in markers):
            return code, LANGUAGE_NAMES[code]

    if re.search(r"[\u0600-\u06ff]", text):
        if re.search(r"[\u067e\u0686\u0698\u06af\u06cc]", text):
            return "fa", LANGUAGE_NAMES["fa"]
        return "ar", LANGUAGE_NAMES["ar"]
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru", LANGUAGE_NAMES["ru"]
    if re.search(r"[\u3400-\u9fff]", text):
        return "zh", LANGUAGE_NAMES["zh"]
    return None


def has_non_latin_script(text: str) -> bool:
    """Return True when text contains a script that can correct a wrong English label."""
    return bool(re.search(r"[\u0400-\u04ff\u0600-\u06ff\u0900-\u097f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", text))


def _script_family_fallback(text: str) -> tuple[str, str] | None:
    """Use a broad script only when no specific language signal is available."""
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar", "Arabic"
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru", "Russian"
    if re.search(r"[\u3400-\u9fff]", text):
        return "zh", "Chinese"
    return None


def normalize_language(language_code: str | None) -> tuple[str, str] | None:
    """Return a language code and label, preserving unknown Whisper codes."""
    if not language_code:
        return None
    code = language_code.lower().split("-")[0]
    if not code:
        return None
    return code, LANGUAGE_NAMES.get(code, code.upper())


def detect_language_confident(text: str) -> tuple[str, str] | None:
    """Return a fresh language signal when text supplies enough evidence."""
    if _is_ambiguous_borrowed_greeting(text):
        return None

    script_language = detect_script_language(text)
    if script_language:
        return script_language

    try:
        from langdetect import DetectorFactory, detect_langs

        DetectorFactory.seed = 0
        result = detect_langs(text)[0]
        if result.prob >= 0.70:
            return normalize_language(result.lang)
    except Exception:
        pass
    return _script_family_fallback(text)


def detect_language(text: str) -> tuple[str, str]:
    """Return a language code and label, defaulting safely to English."""
    return detect_language_confident(text) or ("en", "English")


def should_use_previous_language(transcript: str) -> bool:
    """Short replies often do not contain enough speech for reliable detection."""
    return len(transcript.split()) <= 3
