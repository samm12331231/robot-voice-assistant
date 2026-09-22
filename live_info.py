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

WEATHER_WORDS = (
    "weather", "temperature", "rain", "raining", "forecast",
    "الطقس", "الحرارة", "مطر", "هوا", "دما", "آب و هوا",
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


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    """Return whether a normalized message contains a whole known phrase."""
    normalized = text.casefold()
    return any(
        re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", normalized)
        for phrase in phrases
    )


def _read_json(url: str, parameters: dict[str, str | int | float]) -> dict:
    query = urlencode(parameters)
    with urlopen(f"{url}?{query}", timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _current_time_context() -> str:
    try:
        now = datetime.now(ZoneInfo(EVENT_TIMEZONE))
        return f"Live time for {EVENT_CITY}: {now.strftime('%I:%M %p on %A, %B %d')} ({EVENT_TIMEZONE})."
    except Exception:
        return "Live time lookup failed. Do not guess the current time."


def _weather_failure(cache_key: str) -> str:
    """Return and briefly cache a weather failure to avoid repeated slow timeouts."""
    message = "Live weather lookup failed. Do not guess the current weather."
    _weather_failure_cache.set(cache_key, message)
    return message


def _current_weather_context() -> str:
    """Fetch current conditions for the configured event city from Open-Meteo."""
    cache_key = EVENT_CITY.casefold()
    cached = _weather_cache.get(cache_key)
    if cached:
        return cached
    failed = _weather_failure_cache.get(cache_key)
    if failed:
        return failed
    try:
        geocoding = _read_json(
            "https://geocoding-api.open-meteo.com/v1/search",
            {"name": EVENT_CITY, "count": 1, "language": "en", "format": "json"},
        )
        result = geocoding.get("results", [None])[0]
        if not result:
            return _weather_failure(cache_key)

        weather = _read_json(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": result["latitude"],
                "longitude": result["longitude"],
                "current": "temperature_2m,weather_code",
                "timezone": EVENT_TIMEZONE,
            },
        )
        current = weather.get("current", {})
        temperature = current.get("temperature_2m")
        if temperature is None:
            return _weather_failure(cache_key)
        description = WEATHER_CODES.get(current.get("weather_code"), "unknown conditions")
        city = result.get("name", EVENT_CITY)
        context = f"Live weather for {city}: {temperature}°C, {description}."
        _weather_cache.set(cache_key, context)
        return context
    except Exception:
        return _weather_failure(cache_key)


def get_live_context(user_message: str) -> str:
    """Return trusted live context for simple time or weather questions, otherwise empty."""
    if _contains_any(user_message, WEATHER_WORDS):
        return _current_weather_context()
    if _contains_any(user_message, TIME_WORDS):
        return _current_time_context()
    return ""
