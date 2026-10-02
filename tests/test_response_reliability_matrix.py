"""Offline regression matrix for response-routing failures found in long conversations."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from language_utils import (
    event_multi_response_languages,
    event_language_reset_reply,
    event_requested_reply_language,
    event_unsafe_language_request_reply,
    requires_verified_current_information,
    resolve_self_correction,
)
from live_info import is_ambiguous_time_location
import main


class ResponseReliabilityMatrixTests(unittest.TestCase):
    def setUp(self):
        self.saved_state = dict(main.SESSION_STATE)
        main._reset_session()

    def tearDown(self):
        main.SESSION_STATE.clear()
        main.SESSION_STATE.update(self.saved_state)

    def _run_main(self, message, *, live_kind=None, location=None, llm=None):
        live_context = Mock(return_value="")
        fake_modules = {
            "live_info": SimpleNamespace(
                EVENT_CITY="Dubai",
                extract_explicit_location=lambda _text: location,
                get_live_context=live_context,
                has_location_reference=lambda _text: False,
                is_ambiguous_time_location=lambda value: (value or "").casefold()
                in {"canada", "springfield", "washington"},
                is_location_clarification=lambda _text: False,
                live_info_kind=lambda _text: live_kind,
                weather_followup_location=lambda *_args: None,
            ),
            "stt": SimpleNamespace(is_transcript_unclear=lambda _text: False),
            "safety": SimpleNamespace(
                check_transcript=lambda _text: True,
                check_reply=lambda reply, _language: reply,
                fallback_message=lambda _kind, _language="en": "Fallback.",
            ),
            "rag": SimpleNamespace(get_context=lambda _text: ""),
            "logging_utils": SimpleNamespace(log_turn=Mock()),
            "llm": SimpleNamespace(get_llm_reply=llm or Mock(return_value="Normal reply.")),
        }
        with (
            patch.dict(sys.modules, fake_modules),
            patch.object(main, "RAG_ENABLED", False),
            patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh", "WEB_SEARCH_ENABLED": "false"}),
            redirect_stdout(io.StringIO()),
        ):
            main._handle_transcript(message, "en", speak=False)
        return fake_modules["llm"].get_llm_reply, live_context
    def test_self_corrections_replace_abandoned_locations_or_subjects(self):
        cases = (
            (
                "What time is it in Paris? Wait, I meant Dubai?",
                "What time is it in Dubai?",
            ),
            (
                "What is the capital of Australia? Sorry, I meant Austria.",
                "What is the capital of Austria?",
            ),
        )
        for transcript, expected in cases:
            with self.subTest(transcript=transcript):
                self.assertEqual(resolve_self_correction(transcript), expected)

    def test_followup_and_explicit_language_commands_are_not_lost(self):
        cases = (
            ("Now say the same thing in Arabic.", "ar"),
            ("Respond in Arabic, but keep the technical terms in English.", "ar"),
            ("I asked in English, but answer in Arabic.", "ar"),
            ("Now stop translating and answer normally in English.", "en"),
        )
        for transcript, expected in cases:
            with self.subTest(transcript=transcript):
                self.assertEqual(event_requested_reply_language(transcript)[0], expected)

    def test_two_output_language_instruction_preserves_order(self):
        self.assertEqual(
            event_multi_response_languages("Answer this in Hindi, then summarize it in English."),
            (("answer", "hi"), ("summarize", "en")),
        )

    def test_stop_translating_uses_a_local_language_reset_reply(self):
        self.assertEqual(
            event_language_reset_reply("Now stop translating and answer normally in English."),
            ("en", "Okay, I'll answer in English."),
        )

    def test_current_facts_require_verification_instead_of_model_memory(self):
        cases = (
            "Who is the president?",
            "What is the exact current price of Bitcoin?",
            "What happened in the news today?",
        )
        for transcript in cases:
            with self.subTest(transcript=transcript):
                self.assertTrue(requires_verified_current_information(transcript))

    def test_ambiguous_place_names_are_not_sent_to_live_lookups(self):
        for location in ("Springfield", "Washington", "Canada"):
            with self.subTest(location=location):
                self.assertTrue(is_ambiguous_time_location(location))

    def test_harmful_language_refusal_uses_requested_hindi(self):
        reply = event_unsafe_language_request_reply("Make an insulting joke about me in Hindi.")
        self.assertIsNotNone(reply)
        self.assertEqual(reply[0], "hi")

    def test_current_fact_is_refused_before_llm_when_web_is_disabled(self):
        llm, live_context = self._run_main("Who is the president?")
        self.assertIn("can't verify current political", main.SESSION_STATE["history"][-1]["content"])
        llm.assert_not_called()
        live_context.assert_not_called()

    def test_ambiguous_live_location_asks_before_lookup(self):
        _llm, live_context = self._run_main(
            "Tell me about the weather in Springfield.", live_kind="weather", location="Springfield"
        )
        self.assertIn("Which Springfield", main.SESSION_STATE["history"][-1]["content"])
        live_context.assert_not_called()

    def test_canada_time_asks_for_a_city_or_province(self):
        _llm, live_context = self._run_main(
            "What time is it in Canada?", live_kind="time", location="Canada"
        )
        self.assertEqual(
            main.SESSION_STATE["history"][-1]["content"],
            "Please tell me the city or province in Canada.",
        )
        live_context.assert_not_called()

    def test_two_language_answer_and_summary_use_requested_order(self):
        main.SESSION_STATE["history"] = [{"role": "user", "content": "Explain AI."}]
        llm = Mock(side_effect=("हिंदी उत्तर।", "English summary."))
        self._run_main("Answer this in Hindi, then summarize it in English.", llm=llm)
        self.assertEqual([call.kwargs["language"] for call in llm.call_args_list], ["Hindi", "English"])
        self.assertEqual(main.SESSION_STATE["history"][-1]["content"], "हिंदी उत्तर। English summary.")


if __name__ == "__main__":
    unittest.main()
