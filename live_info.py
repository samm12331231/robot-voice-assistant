"""Small live-information helpers for time and current weather questions."""

from datetime import datetime
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from runtime_cache import TTLCache


load_dotenv()

EVENT_CITY = os.getenv("EVENT_CITY", "Dubai")
EVENT_TIMEZONE = os.getenv("EVENT_TIMEZONE", "Asia/Dubai")
REQUEST_TIMEOUT_SECONDS = 5
WEATHER_CACHE_SECONDS = int(os.getenv("WEATHER_CACHE_SECONDS", "300"))
WEATHER_FAILURE_CACHE_SECONDS = int(os.getenv("WEATHER_FAILURE_CACHE_SECONDS", "60"))
_weather_cache = TTLCache(WEATHER_CACHE_SECONDS)
_weather_failure_cache = TTLCache(WEATHER_FAILURE_CACHE_SECONDS)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
LOCATION_PATTERN = re.compile(
    r"\b(?:in|for|near|around|at|en|في|در)\s+(.+?)"
    r"(?=\s+(?:today|right now|currently|now|weather|clima|tiempo|الطقس|موسم|هوا|آب و هوا|چطور|چگونه)\b|[?!.;,؟،]|$)",
    re.IGNORECASE,
)
SUFFIX_LOCATION_PATTERN = re.compile(r"(.+?)\s+(?:में|میں)(?=\s|[?!.;,؟،]|$)")
PERSIAN_LOCATION_PATTERN = re.compile(
    r"(?:هوای|آب و هوای)\s+(.+?)"
    r"(?=\s+(?:چطور|چگونه|است)\b|[?!.;,؟،]|$)"
)
LOCATION_ALIASES = {
    "لندن": "London",
    "लंदन": "London",
    "ابوظہبی": "Abu Dhabi",
    "دبي": "Dubai",
    "دبئی": "Dubai",
    "मुंबई": "Mumbai",
    "طوكيو": "Tokyo",
    "القاهرة": "Cairo",
    "تهران": "Tehran",
}
KNOWN_LOCATION_MENTIONS = {
    "abu dhabi": "Abu Dhabi", "أبوظبي": "Abu Dhabi", "ابوظبي": "Abu Dhabi",
    "fujairah": "Fujairah", "الفجيرة": "Fujairah",
    "dubai": "Dubai", "دبي": "Dubai", "دبئی": "Dubai",
    "tokyo": "Tokyo", "طوكيو": "Tokyo",
    "london": "London", "لندن": "London",
    "cairo": "Cairo", "القاهرة": "Cairo",
    "mumbai": "Mumbai", "मुंबई": "Mumbai",
    "tehran": "Tehran", "تهران": "Tehran",
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
AMBIGUOUS_TIME_LOCATIONS = {"canada", "springfield", "washington"}
LOCATION_FOLLOWUP_CUES = (
    "talking about", "i mean", "we mean", "meant", "the location", "that location",
)
LOCATION_REFERENCE_PATTERN = re.compile(
    r"\b(?:there|that place|that city|the same place)\b", re.IGNORECASE
)

WEATHER_WORDS = (
    "weather", "temperature", "rain", "raining", "forecast",
    "الطقس", "الحرارة", "مطر", "هوا", "هوای", "دما", "آب و هوا",
    "موسم کیسا", "آج موسم", "درجہ حرارت", "بارش", "मौसम", "तापमान", "बारिश",
    "clima", "tiempo", "météo", "wetter", "погода", "температура",
    "天气", "温度", "天気", "날씨",
)
TIME_WORDS = (
    "what time", "time is it", "the time", "clock", "current time",
    "الساعة", "الوقت", "ساعت", "زمان", "وقت", "ٹائم", "समय", "बजे",
    "qué hora", "quelle heure", "uhrzeit", "сколько времени", "который час",
    "几点", "时间", "何時", "시간",
)

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow",
    75: "heavy snow", 80: "rain showers", 81: "rain showers", 82: "heavy rain showers",
    95: "thunderstorms",
}

LIVE_INFO_FAILURE_REPLIES = {
    "weather": {
        "en": "Sorry, I can't retrieve the weather right now.",
        "ar": "عذرًا، لا أستطيع الحصول على معلومات الطقس الآن.",
        "hi": "माफ़ कीजिए, मैं अभी मौसम की जानकारी प्राप्त नहीं कर सकता।",
        "zh": "抱歉，我现在无法获取天气信息。",
    },
    "time": {
        "en": "Sorry, I can't retrieve the current time right now.",
        "ar": "عذرًا، لا أستطيع الحصول على الوقت الحالي الآن.",
        "hi": "माफ़ कीजिए, मैं अभी वर्तमान समय प्राप्त नहीं कर सकता।",
        "zh": "抱歉，我现在无法获取当前时间。",
    },
}
SWIMMING_WITHOUT_WEATHER_REPLIES = {
    "en": "I can't assess swimming conditions without current weather information.",
    "ar": "لا أستطيع تقييم ظروف السباحة من دون معلومات طقس حالية.",
    "hi": "मैं वर्तमान मौसम की जानकारी के बिना तैराकी की स्थितियों का आकलन नहीं कर सकता।",
    "zh": "没有当前天气信息，我无法评估游泳条件。",
}
SWIMMING_WITH_WEATHER_REPLIES = {
    "en": "I can describe the weather, but check local lifeguard advice before swimming.",
    "ar": "يمكنني وصف الطقس، لكن تحقق من إرشادات المنقذين المحليين قبل السباحة.",
    "hi": "मैं मौसम बता सकता हूँ, लेकिन तैरने से पहले स्थानीय लाइफगार्ड की सलाह देखें।",
    "zh": "我可以说明天气，但游泳前请查看当地救生员的建议。",
}
LIVE_LOCATION_NAMES = {
    "ar": {
        "dubai": "دبي", "abu dhabi": "أبوظبي", "fujairah": "الفجيرة",
        "tokyo": "طوكيو", "united arab emirates": "الإمارات العربية المتحدة",
    },
    "hi": {
        "dubai": "दुबई", "abu dhabi": "अबू धाबी", "fujairah": "फुजैरा",
        "tokyo": "टोक्यो", "united arab emirates": "संयुक्त अरब अमीरात",
    },
    "zh": {
        "dubai": "迪拜", "abu dhabi": "阿布扎比", "fujairah": "富查伊拉",
        "tokyo": "东京", "united arab emirates": "阿拉伯联合酋长国",
    },
}
LIVE_WEATHER_DESCRIPTIONS = {
    "ar": {"clear sky": "سماء صافية", "mainly clear": "صحو غالبًا", "partly cloudy": "غائم جزئيًا", "overcast": "غائم"},
    "hi": {"clear sky": "आसमान साफ़", "mainly clear": "ज़्यादातर साफ़", "partly cloudy": "आंशिक बादल", "overcast": "बादल छाए हुए"},
    "zh": {"clear sky": "晴朗", "mainly clear": "大致晴朗", "partly cloudy": "局部多云", "overcast": "阴天"},
}


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    """Return whether a normalized message contains a whole known phrase."""
    normalized = text.casefold()
    return any(
        re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", normalized)
        for phrase in phrases
    )


def live_info_failure_reply(
    kind: str | None, language_code: str, context: str, user_message: str = ""
) -> str | None:
    """Return a local reply when a live lookup explicitly failed.

    The context is trusted status text generated by this module. Returning a local
    reply prevents a language model from restating a failed lookup in another language.
    """
    if kind not in LIVE_INFO_FAILURE_REPLIES:
        return None
    normalized = (context or "").casefold()
    if not any(phrase in normalized for phrase in ("unavailable", "could not be resolved", "lookup failed")):
        return None
    reply = LIVE_INFO_FAILURE_REPLIES[kind].get(
        language_code, LIVE_INFO_FAILURE_REPLIES[kind]["en"]
    )
    if kind == "weather" and re.search(r"\b(?:swim|swimming)\b", user_message.casefold()):
        swimming_reply = SWIMMING_WITHOUT_WEATHER_REPLIES.get(
            language_code, SWIMMING_WITHOUT_WEATHER_REPLIES["en"]
        )
        return f"{reply} {swimming_reply}"
    return reply


def live_info_direct_reply(
    kind: str | None, language_code: str, context: str, user_message: str = ""
) -> str | None:
    """Format successful trusted live data locally in the selected event language."""
    if kind == "time":
        match = re.fullmatch(r"Live time for (.+?): (.+)", (context or "").strip())
        if not match:
            return None
        location, value = match.groups()
        localized_location = _localize_live_location(location, language_code)
        localized_value = _localize_time_value(value, language_code)
        templates = {
            "en": "The current time in {location} is {value}",
            "ar": "الوقت الحالي في {location} هو {value}",
            "hi": "{location} में वर्तमान समय {value} है",
            "zh": "{location} 当前时间是 {value}",
        }
    elif kind == "weather":
        match = re.fullmatch(r"Live weather for (.+?): (.+)", (context or "").strip())
        if not match:
            return None
        location, value = match.groups()
        localized_location = _localize_live_location(location, language_code)
        localized_value = _localize_weather_value(value, language_code)
        templates = {
            "en": "The weather in {location} is {value}",
            "ar": "الطقس في {location} هو {value}",
            "hi": "{location} में मौसम {value} है",
            "zh": "{location} 的天气是 {value}",
        }
    else:
        return None
    reply = templates.get(language_code, templates["en"]).format(
        location=localized_location, value=localized_value
    )
    if kind == "weather" and re.search(r"\b(?:swim|swimming)\b", user_message.casefold()):
        swimming_reply = SWIMMING_WITH_WEATHER_REPLIES.get(
            language_code, SWIMMING_WITH_WEATHER_REPLIES["en"]
        )
        return f"{reply}. {swimming_reply}"
    return reply


def _localize_live_location(location: str, language_code: str) -> str:
    """Translate common event locations without changing unknown place names."""
    names = LIVE_LOCATION_NAMES.get(language_code, {})
    return ", ".join(names.get(part.casefold().strip(), part.strip()) for part in location.split(","))


def _localize_time_value(value: str, language_code: str) -> str:
    """Avoid leaking English weekday, month, and timezone labels into local replies."""
    value = re.sub(r"\s*\([A-Za-z_]+/[A-Za-z_]+\)\.?$", "", value).strip()
    if language_code == "en":
        return value
    match = re.match(r"(\d{1,2}:\d{2})\s*(?:AM|PM)?", value, flags=re.IGNORECASE)
    return match.group(1) if match else value


def _localize_weather_value(value: str, language_code: str) -> str:
    """Translate the Open-Meteo condition description while retaining the measurement."""
    if language_code == "en":
        return value
    temperature, separator, description = value.partition(",")
    if not separator:
        return value
    translated = LIVE_WEATHER_DESCRIPTIONS.get(language_code, {}).get(
        description.strip().rstrip(".").casefold(), description.strip()
    )
    return f"{temperature.strip()}, {translated}"


def _read_json(url: str, parameters: dict[str, str | int | float]) -> dict:
    query = urlencode(parameters)
    with urlopen(f"{url}?{query}", timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_location(location: str) -> str:
    """Normalize a user location for matching and cache keys."""
    return re.sub(r"\s+", " ", location.casefold()).strip(" ,؟?,.!؛،")


def _location_alias(location: str) -> str:
    return LOCATION_ALIASES.get(_normalize_location(location), location)


def extract_explicit_location(user_message: str) -> str | None:
    """Extract a place stated directly in a message, without a default location."""
    normalized_message = (user_message or "").casefold()
    # Prefer an explicitly named known city over a broad conversational preposition
    # match such as "in English" in a long multilingual request.
    for mention, location in sorted(KNOWN_LOCATION_MENTIONS.items(), key=lambda item: -len(item[0])):
        if re.search(rf"(?<!\w){re.escape(mention)}(?!\w)", normalized_message):
            return location

    patterns = (LOCATION_PATTERN, SUFFIX_LOCATION_PATTERN, PERSIAN_LOCATION_PATTERN)
    for pattern in patterns:
        for match in pattern.finditer(user_message):
            candidate = match.group(1).strip()
            # Strip trailing language indicators like "in Arabic", "in Hindi"
            candidate = re.sub(
                r"\s+in\s+[a-zA-Z\s]+$", "", candidate, flags=re.IGNORECASE
            ).strip(" ,?.!؛،")
            candidate = re.sub(
                r"\s+(?:please|thanks)$", "", candidate, flags=re.IGNORECASE
            ).strip(" ,?.!؛،")
            location = _location_alias(candidate)
            if not location or len(location) > 80:
                continue
            normalized_cand = _normalize_location(location)
            if (
                normalized_cand in LANGUAGE_LOCATION_BLACKLIST
                or normalized_cand in {
                    "today", "now", "currently", "right now",
                    "there", "that place", "that city", "the same place", "here",
                }
            ):
                continue
            return location
    return None


def _requested_location(user_message: str) -> str:
    """Extract a short explicit place, or use the configured event city."""
    return extract_explicit_location(user_message) or EVENT_CITY


def _geocode_location(location: str) -> dict | None:
    """Resolve a location from Open-Meteo's first exact city match."""
    response = _read_json(
        GEOCODING_URL,
        {"name": location, "count": 5, "language": "en", "format": "json"},
    )
    results = response.get("results", [])
    if not results or not isinstance(results[0], dict):
        return None

    normalized_location = _normalize_location(location)
    first_result = results[0]
    if not {"name", "latitude", "longitude"}.issubset(first_result):
        return None
    if _normalize_location(str(first_result["name"])) != normalized_location:
        return None
    return first_result


def _current_time_context(location: str | None = None) -> str:
    """Return current time only when the requested location has a resolved timezone."""
    timezone_name = EVENT_TIMEZONE
    display_location = EVENT_CITY
    if location:
        if _normalize_location(location) in AMBIGUOUS_TIME_LOCATIONS:
            return (
                f"Live time for {location} is ambiguous. Ask for a city or province; "
                "do not guess a timezone."
            )
        result = _geocode_location(location)
        if not result:
            return f"Live time for {location} could not be resolved. Do not guess a timezone."
        if result.get("feature_code") == "PCLI":
            return (
                f"Live time for {location} is ambiguous. Ask for a city or province; "
                "do not guess a timezone."
            )
        timezone_name = result.get("timezone")
        if not timezone_name:
            return f"Live timezone for {location} could not be resolved. Do not guess."
        display_location = result.get("name", location)
    try:
        now = datetime.now(ZoneInfo(timezone_name))
        return (
            f"Live time for {display_location}: {now.strftime('%I:%M %p on %A, %B %d')} "
            f"({timezone_name})."
        )
    except Exception:
        return f"Live time lookup failed for {display_location}. Do not guess the current time."


def _weather_failure(cache_key: str, location: str) -> str:
    """Return and briefly cache a weather failure to avoid repeated slow timeouts."""
    message = (
        f"Live weather for {location} is unavailable. "
        "Say that you cannot retrieve it right now; do not guess."
    )
    _weather_failure_cache.set(cache_key, message)
    return message


def _current_weather_context(location: str = EVENT_CITY) -> str:
    """Fetch current conditions for a resolved location from Open-Meteo."""
    cache_key = _normalize_location(location)
    cached = _weather_cache.get(cache_key)
    if cached:
        return cached
    failed = _weather_failure_cache.get(cache_key)
    if failed:
        return failed
    try:
        result = _geocode_location(location)
        if not result:
            return _weather_failure(cache_key, location)

        weather = _read_json(
            FORECAST_URL,
            {
                "latitude": result["latitude"],
                "longitude": result["longitude"],
                "current": "temperature_2m,weather_code",
                "timezone": "auto",
            },
        )
        current = weather.get("current", {})
        temperature = current.get("temperature_2m")
        weather_code = current.get("weather_code")
        if temperature is None or weather_code not in WEATHER_CODES:
            return _weather_failure(cache_key, location)
        description = WEATHER_CODES[weather_code]
        city = result.get("name", location)
        country = result.get("country")
        display_location = f"{city}, {country}" if country else city
        context = f"Live weather for {display_location}: {temperature}°C, {description}."
        _weather_cache.set(cache_key, context)
        return context
    except Exception:
        return _weather_failure(cache_key, location)


def is_weather_request(user_message: str) -> bool:
    """Return whether a message explicitly asks about weather."""
    return _contains_any(user_message, WEATHER_WORDS)


def live_info_kind(user_message: str) -> str | None:
    """Identify whether a message asks for live weather or time."""
    if is_weather_request(user_message):
        return "weather"
    if _contains_any(user_message, TIME_WORDS):
        return "time"
    return None


def has_location_reference(user_message: str) -> bool:
    """Return whether a live question refers to a previously named place."""
    return bool(LOCATION_REFERENCE_PATTERN.search(user_message))


def is_ambiguous_time_location(location: str | None) -> bool:
    """Return whether a named place needs a state, province, or city clarification."""
    return bool(location) and _normalize_location(location) in AMBIGUOUS_TIME_LOCATIONS


def is_location_clarification(user_message: str) -> bool:
    """Recognize an explicit place correction such as 'we mean in Dubai'."""
    normalized = user_message.casefold()
    return bool(extract_explicit_location(user_message)) and any(
        cue in normalized for cue in LOCATION_FOLLOWUP_CUES
    )


def weather_followup_location(
    user_message: str, remembered_live_info: dict | None
) -> str | None:
    """Resolve a place reference only from the immediately preceding live-info turn."""
    if not remembered_live_info:
        return None
    remembered_location = remembered_live_info.get("location")
    remembered_kind = remembered_live_info.get("kind")
    if not remembered_location or remembered_kind not in {"weather", "time"}:
        return None
    if live_info_kind(user_message):
        return remembered_location if has_location_reference(user_message) else None
    explicit_location = extract_explicit_location(user_message)
    if remembered_kind == "weather" and is_location_clarification(user_message):
        return explicit_location
    return None


def get_live_context(
    user_message: str, location_override: str | None = None
) -> str:
    """Return trusted live context for simple time or weather questions, otherwise empty."""
    kind = live_info_kind(user_message)
    if kind == "weather":
        return _current_weather_context(location_override or _requested_location(user_message))
    if kind == "time":
        return _current_time_context(
            location_override or extract_explicit_location(user_message)
        )
    return ""
