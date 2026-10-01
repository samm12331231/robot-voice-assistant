"""Offline checks that unverified company questions cannot reach the general LLM."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from language_utils import company_facts_unavailable, is_company_fact_request


@patch.dict("os.environ", {"LANGUAGE_MODE": ""})
class CompanyGroundingTests(unittest.TestCase):
    def test_company_description_leadership_and_contact_requests_are_recognized(self):
        requests = (
            "What is Ibtikar Robotics?",
            "What exactly does Aptech Robotics do? Do they build robots?",
            "Who is the CEO of Ibtikar Robotics?",
            "What is the office address for Aptech Robotics?",
            "عندي سؤال الابتكار روبوتيكس هاي شو شركة هاي؟",
        )
        for request in requests:
            with self.subTest(request=request):
                self.assertTrue(is_company_fact_request(request))

    def test_song_requests_with_a_capitalized_title_are_not_company_questions(self):
        self.assertFalse(is_company_fact_request(
            "Do is this, do is this. Can you read out the lyrics for Not Like Us by Kendrick?"
        ))

    def test_rag_disabled_company_questions_return_localized_refusal_without_llm(self):
        saved_state = dict(main.SESSION_STATE)
        fake_llm = Mock(return_value="Unverified company detail.")
        fake_log = Mock()
        fake_modules = {
            "live_info": SimpleNamespace(
                EVENT_CITY="Dubai", extract_explicit_location=lambda _text: None,
                get_live_context=lambda *_args: "", has_location_reference=lambda _text: False,
                is_ambiguous_time_location=lambda _location: False,
                is_location_clarification=lambda _text: False,
                live_info_kind=lambda _text: None, weather_followup_location=lambda *_args: None,
            ),
            "stt": SimpleNamespace(is_transcript_unclear=lambda _text: False),
            "safety": SimpleNamespace(
                check_transcript=lambda _text: True, check_reply=lambda reply, _language: reply,
                fallback_message=lambda *_args: "Unavailable.",
            ),
            "rag": SimpleNamespace(get_context=Mock(return_value="")),
            "logging_utils": SimpleNamespace(log_turn=fake_log),
            "llm": SimpleNamespace(get_llm_reply=fake_llm),
        }
        cases = (
            ("What is Ibtikar Robotics?", "en"),
            ("What exactly does Aptech Robotics do? Do they build robots?", "en"),
            ("عندي سؤال الابتكار روبوتيكس هاي شو شركة هاي؟", "ar"),
        )
        try:
            main._reset_session()
            with patch.dict(sys.modules, fake_modules), patch("main.RAG_ENABLED", False), redirect_stdout(io.StringIO()):
                for request, language in cases:
                    main._handle_transcript(request, language, speak=False)
                    expected = company_facts_unavailable(language)
                    self.assertEqual(main.SESSION_STATE["history"][-1]["content"], expected)
                    self.assertEqual(fake_log.call_args.kwargs["reply"], expected)
            fake_llm.assert_not_called()
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_english_refusal_matches_required_wording(self):
        self.assertEqual(
            company_facts_unavailable("en"),
            "I don’t have verified information about that company right now.",
        )


if __name__ == "__main__":
    unittest.main()
