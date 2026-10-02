"""Mocked checks for city-specific live info and safe follow-up routing."""
from datetime import datetime as FixedDateTime
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import language_utils
import live_info
from language_utils import choose_reply_language


class LiveInfoRoutingTests(unittest.TestCase):
    def test_english_contraction_sentence_overrides_afrikaans_label(self):
        transcript = "we're talking about like in Dubai right now"
        with patch.object(
            language_utils, "detect_language_confident", return_value=("af", "Afrikaans")
        ):
            language, uncertain = choose_reply_language(transcript, "af", None)
        self.assertEqual(language, ("en", "English"))
        self.assertFalse(uncertain)

    def test_fujairah_is_extracted_from_weather_question(self):
        question = "What's the weather like today in Fujairah?"
        self.assertEqual(live_info.extract_explicit_location(question), "Fujairah")
        self.assertEqual(live_info._requested_location(question), "Fujairah")

    def test_named_city_wins_over_language_word_in_long_request(self):
        question = "I do not speak Arabic. English. What is the weather in Dubai in Arabic?"
        self.assertEqual(live_info.extract_explicit_location(question), "Dubai")

    def test_tokyo_time_uses_resolved_timezone(self):
        geocoded = {"name": "Tokyo", "timezone": "Asia/Tokyo", "feature_code": "PPLC"}
        with (
            patch.object(live_info, "_geocode_location", return_value=geocoded),
            patch.object(live_info, "datetime") as mocked_datetime,
        ):
            mocked_datetime.now.return_value = FixedDateTime(2026, 9, 28, 12, 0)
            context = live_info.get_live_context("What's the time in Tokyo?")

        self.assertIn("Live time for Tokyo", context)
        self.assertIn("Asia/Tokyo", context)
        self.assertEqual(mocked_datetime.now.call_args.args[0], ZoneInfo("Asia/Tokyo"))

    def test_canada_time_stays_ambiguous_without_geocoding(self):
        with patch.object(live_info, "_geocode_location") as geocode:
            context = live_info.get_live_context("What's the time in Canada?")
        self.assertIn("ambiguous", context)
        self.assertIn("city or province", context)
        geocode.assert_not_called()

    def test_weather_clarification_uses_only_remembered_session_location(self):
        message = "we're talking about like in Dubai right now"
        remembered = {"kind": "weather", "location": "Dubai"}
        self.assertEqual(live_info.weather_followup_location(message, remembered), "Dubai")
        self.assertIsNone(live_info.weather_followup_location(message, None))

        with patch.object(live_info, "_current_weather_context") as weather:
            context = live_info.get_live_context(message)
        self.assertEqual(context, "")
        weather.assert_not_called()

    def test_unavailable_weather_keeps_swimming_answer_safe_and_local(self):
        reply = live_info.live_info_failure_reply(
            "weather",
            "hi",
            "Live weather for Dubai is unavailable. Do not guess.",
            "Can you tell me the weather in Dubai in Hindi and explain whether swimming is safe?",
        )
        self.assertIn("मौसम", reply)
        self.assertIn("तैराकी", reply)

    def test_successful_live_context_is_formatted_in_requested_language(self):
        reply = live_info.live_info_direct_reply(
            "time", "ar", "Live time for Dubai: 03:15 PM on Tuesday (Asia/Dubai)."
        )
        self.assertIn("الوقت الحالي", reply)
        self.assertIn("دبي", reply)
        self.assertNotIn("Tuesday", reply)
        self.assertNotIn("Asia/Dubai", reply)

    def test_successful_time_reply_hides_timezone_identifier(self):
        reply = live_info.live_info_direct_reply(
            "time", "en", "Live time for Tokyo: 05:31 PM on Friday, October 02 (Asia/Tokyo)."
        )
        self.assertEqual(
            reply,
            "The current time in Tokyo is 05:31 PM on Friday, October 02",
        )

    def test_weather_reply_translates_location_and_condition(self):
        reply = live_info.live_info_direct_reply(
            "weather", "zh", "Live weather for Abu Dhabi, United Arab Emirates: 30°C, clear sky."
        )
        self.assertIn("阿布扎比", reply)
        self.assertIn("晴朗", reply)
        self.assertNotIn("clear sky", reply)

    def test_successful_weather_includes_safe_swimming_guidance(self):
        reply = live_info.live_info_direct_reply(
            "weather", "en", "Live weather for Dubai: 30°C, clear sky.",
            "What is the weather in Dubai right now, and would you recommend swimming?",
        )
        self.assertIn("local lifeguard", reply)

    def test_other_languages_are_not_forced_to_english(self):
        examples = (
            ("Hola, ¿cómo estás?", "es"),
            ("السلام عليكم كيف حالك", "ar"),
            ("کیا حال ہے", "ur"),
            ("नमस्ते आप कैसे हो", "hi"),
        )
        for transcript, expected in examples:
            with self.subTest(language=expected):
                language, _ = choose_reply_language(transcript, "en", None)
                self.assertEqual(language[0], expected)


if __name__ == "__main__":
    unittest.main()
