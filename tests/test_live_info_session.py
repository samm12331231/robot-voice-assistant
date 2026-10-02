"""Session-scoped live location follow-up tests using mocked service paths."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import live_info
import main


@patch.dict("os.environ", {"LANGUAGE_MODE": ""})
class LiveInfoSessionTests(unittest.TestCase):
    def setUp(self):
        self.saved_state = dict(main.SESSION_STATE)
        main._reset_session()
        self.llm_reply = Mock(return_value="A short live-information reply.")
        self.fake_modules = {
            "stt": SimpleNamespace(is_transcript_unclear=lambda _text: False),
            "safety": SimpleNamespace(
                check_transcript=lambda _text: True,
                check_reply=lambda reply, _language: reply,
                fallback_message=lambda *_args: "Please try again.",
            ),
            "rag": SimpleNamespace(get_context=lambda _text: ""),
            "logging_utils": SimpleNamespace(log_turn=Mock()),
            "llm": SimpleNamespace(get_llm_reply=self.llm_reply),
        }

    def tearDown(self):
        main.SESSION_STATE.clear()
        main.SESSION_STATE.update(self.saved_state)

    def run_turn(self, message):
        with (
            patch.dict(sys.modules, self.fake_modules),
            patch.object(main, "RAG_ENABLED", False),
        ):
            main._handle_transcript(message, "en", speak=False)

    def test_time_weather_followups_switch_locations_within_the_session(self):
        with (
            patch.object(
                live_info, "_current_time_context", side_effect=lambda place: f"mock time: {place}"
            ) as current_time,
            patch.object(
                live_info, "_current_weather_context", side_effect=lambda place: f"mock weather: {place}"
            ) as current_weather,
        ):
            self.run_turn("What time is it in Dubai?")
            self.assertEqual(main.SESSION_STATE["last_live_info"], {
                "kind": "time", "location": "Dubai"
            })

            self.run_turn("What about the weather there?")
            self.assertEqual(current_weather.call_args.args, ("Dubai",))
            self.assertEqual(
                self.llm_reply.call_args.args[0],
                "What's the weather like right now in Dubai?",
            )
            self.assertEqual(main.SESSION_STATE["last_live_info"], {
                "kind": "weather", "location": "Dubai"
            })

            self.run_turn("What's the weather in Tokyo?")
            self.assertEqual(current_weather.call_args.args, ("Tokyo",))
            self.assertEqual(main.SESSION_STATE["last_live_info"], {
                "kind": "weather", "location": "Tokyo"
            })

            self.run_turn("What time is it there?")
            self.assertEqual(current_time.call_args.args, ("Tokyo",))
            self.assertEqual(
                self.llm_reply.call_args.args[0], "What time is it in Tokyo?"
            )

    def test_unrelated_turn_clears_location_and_unresolved_reference_clarifies(self):
        with patch.object(live_info, "_current_weather_context", return_value="mock weather") as weather:
            self.run_turn("What's the weather in Tokyo?")
            self.assertEqual(main.SESSION_STATE["last_live_info"]["location"], "Tokyo")

            self.run_turn("Tell me a joke.")
            self.assertIsNone(main.SESSION_STATE["last_live_info"])
            weather.reset_mock()

            self.run_turn("What about the weather there?")

        weather.assert_not_called()
        self.assertIsNone(main.SESSION_STATE["last_live_info"])
        self.assertEqual(
            main.SESSION_STATE["history"][-1]["content"], "Which city or place do you mean?"
        )

    def test_language_followup_reuses_previous_live_request(self):
        with patch.object(
            live_info, "_current_weather_context", return_value="mock weather: Dubai"
        ) as weather:
            self.run_turn("What's the weather in Dubai in Chinese?")
            self.run_turn("Actually, explain it in English.")

        self.assertEqual(weather.call_args.args, ("Dubai",))
        self.assertEqual(
            self.llm_reply.call_args.args[0],
            "What's the weather like right now in Dubai?",
        )

    def test_time_correction_uses_the_corrected_city(self):
        with patch.object(
            live_info,
            "get_live_context",
            return_value="Live time for Dubai: 03:15 PM.",
        ) as get_live_context:
            self.run_turn(
                "What time is it in Paris? Wait, I meant what time is it in Dubai?"
            )

        self.assertIn("Dubai", main.SESSION_STATE["history"][-1]["content"])
        self.assertNotIn("weather", main.SESSION_STATE["history"][-1]["content"].casefold())
        self.assertIn("Dubai", get_live_context.call_args.args[0])

    def test_canada_time_does_not_store_an_ambiguous_location(self):
        self.run_turn("What time is it in Canada?")
        self.assertIsNone(main.SESSION_STATE["last_live_info"])

    def test_session_reset_clears_remembered_live_location(self):
        main.SESSION_STATE["last_live_info"] = {"kind": "weather", "location": "Tokyo"}
        main.SESSION_STATE["history"] = [{"role": "user", "content": "weather"}]

        main._reset_session()

        self.assertIsNone(main.SESSION_STATE["last_live_info"])
        self.assertEqual(main.SESSION_STATE["history"], [])


if __name__ == "__main__":
    unittest.main()
