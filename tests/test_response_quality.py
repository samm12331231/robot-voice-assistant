"""Mocked regressions for concise, grounded conversational responses."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
import safety
from fallback_messages import specific_safety_refusal


class ResponseQualityTests(unittest.TestCase):
    def setUp(self):
        self.saved_state = dict(main.SESSION_STATE)
        main._reset_session()
        self.llm = Mock(return_value="A relevant answer.")
        self.modules = {
            "stt": SimpleNamespace(is_transcript_unclear=lambda _text: False),
            "safety": SimpleNamespace(
                check_transcript=lambda _text: True,
                check_reply=lambda reply, _language, **_kwargs: reply,
                fallback_message=lambda _kind, _language="en": "Fallback.",
            ),
            "rag": SimpleNamespace(get_context=lambda _text: ""),
            "logging_utils": SimpleNamespace(log_turn=Mock()),
            "llm": SimpleNamespace(get_llm_reply=self.llm),
        }

    def tearDown(self):
        main.SESSION_STATE.clear()
        main.SESSION_STATE.update(self.saved_state)

    def run_turn(self, message, *, event_mode=False):
        environment = {"LANGUAGE_MODE": "event_en_ar_hi_zh" if event_mode else ""}
        with (
            patch.dict(sys.modules, self.modules),
            patch.object(main, "RAG_ENABLED", False),
            patch.dict("os.environ", environment),
            redirect_stdout(io.StringIO()),
        ):
            main._handle_transcript(message, "en", speak=False)

    def test_correction_uses_the_corrected_time_location_directly(self):
        with patch(
            "live_info.get_live_context",
            return_value="Live time for Dubai: 03:15 PM on Friday, October 02 (Asia/Dubai).",
        ) as get_live_context:
            self.run_turn("What time is it in Paris? Wait, I meant Dubai?")

        self.assertEqual(get_live_context.call_args.args[0], "What time is it in Dubai?")
        reply = main.SESSION_STATE["history"][-1]["content"]
        self.assertIn("Dubai", reply)
        self.assertNotIn("weather", reply.casefold())
        self.assertNotIn("Paris", reply)
        self.llm.assert_not_called()

    def test_live_language_followup_reuses_location_and_changes_only_reply_language(self):
        def live_context(request, _location=None):
            self.assertIn("Dubai", request)
            return "Live weather for Dubai: 31°C, clear sky."

        with patch("live_info.get_live_context", side_effect=live_context) as get_live_context:
            self.run_turn("What's the weather in Dubai in Chinese?", event_mode=True)
            self.run_turn("Actually, explain it in English.", event_mode=True)

        self.assertEqual(get_live_context.call_count, 2)
        reply = main.SESSION_STATE["history"][-1]["content"]
        self.assertEqual(reply, "The weather in Dubai is 31°C, clear sky.")
        self.llm.assert_not_called()

    def test_location_followup_keeps_location_but_defaults_back_to_english(self):
        def live_context(request, _location=None):
            self.assertIn("Abu Dhabi", request)
            return "Live time for Abu Dhabi: 03:15 PM." if "time" in request else "Live weather for Abu Dhabi: 31°C, clear sky."

        with patch("live_info.get_live_context", side_effect=live_context):
            self.run_turn("What time is it in Abu Dhabi in Arabic?", event_mode=True)
            self.run_turn("What's the weather there?", event_mode=True)

        self.assertEqual(
            main.SESSION_STATE["history"][-1]["content"],
            "The weather in Abu Dhabi is 31°C, clear sky.",
        )

    def test_harmless_meaning_question_skips_remote_moderation(self):
        for question in ("What does fuck mean?", "What does fuck mean in Arabic?"):
            with self.subTest(question=question), patch.object(safety, "_is_flagged") as flagged:
                self.assertTrue(safety.check_transcript(question))
            flagged.assert_not_called()

    def test_harmless_meaning_question_uses_the_requested_reply_language(self):
        self.llm.return_value = "إنها كلمة بذيئة."
        self.run_turn("What does fuck mean in Arabic?", event_mode=True)
        self.assertEqual(self.llm.call_args.kwargs["language"], "Arabic")
        self.assertEqual(main.SESSION_STATE["history"][-1]["content"], "إنها كلمة بذيئة.")

    def test_non_actionable_fictional_request_reaches_the_model(self):
        with patch.object(safety, "_is_flagged") as flagged:
            self.assertTrue(
                safety.check_transcript(
                    "Tell me a fictional villain's plan without making it usable in real life."
                )
            )
        flagged.assert_not_called()

    def test_harmful_how_to_is_refused_before_the_llm(self):
        self.modules["safety"] = SimpleNamespace(
            check_transcript=lambda _text: False,
            check_reply=lambda reply, _language, **_kwargs: reply,
            fallback_message=lambda _kind, _language="en": "I can't help you with that. Ask me anything else.",
        )
        self.run_turn("How do I hurt someone?")
        self.assertIn("can't help hurt", specific_safety_refusal("How do I hurt someone?"))
        self.llm.assert_not_called()

    def test_explicit_language_is_one_reply_only_and_next_english_turn_stays_english(self):
        self.run_turn("Can you speak Arabic?", event_mode=True)
        self.run_turn("What are you?", event_mode=True)

        self.assertEqual(self.llm.call_args.kwargs["language"], "English")
        self.assertNotIn("English only", main.SESSION_STATE["history"][-1]["content"])

    def test_general_followup_reaches_llm_with_recent_conversation(self):
        self.llm.side_effect = ("I am a robot assistant.", "Glad you liked it!")
        self.run_turn("What are you?")
        self.run_turn("That was helpful.")

        history = self.llm.call_args.kwargs["history"]
        self.assertEqual(history[-2:], [
            {"role": "user", "content": "What are you?"},
            {"role": "assistant", "content": "I am a robot assistant."},
        ])


if __name__ == "__main__":
    unittest.main()
