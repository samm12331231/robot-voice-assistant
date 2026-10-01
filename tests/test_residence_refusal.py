"""Offline tests for concise current-residence refusals."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from residence import current_residence_refusal, is_current_residence_request


@patch.dict("os.environ", {"LANGUAGE_MODE": ""})
class ResidenceRefusalTests(unittest.TestCase):
    def test_residence_intent_does_not_match_origin_questions(self):
        requests = (
            "Where does Drake live?",
            "Where does Drake reside?",
            "What is Drake's current home address?",
            "Where is Drake's house?",
            "What is Drake's residence?",
        )
        for transcript in requests:
            with self.subTest(transcript=transcript):
                self.assertTrue(is_current_residence_request(transcript))

        self.assertFalse(is_current_residence_request("Where is Drake from?"))

    def test_final_residence_reply_is_only_the_refusal(self):
        saved_state = dict(main.SESSION_STATE)
        fake_live_context = Mock(return_value="")
        fake_llm = Mock(return_value=(
            "I can't provide his residence. He has properties in Toronto and Los Angeles."
        ))
        fake_log = Mock()
        fake_modules = {
            "live_info": SimpleNamespace(
                EVENT_CITY="Dubai",
                extract_explicit_location=lambda _text: None,
                get_live_context=fake_live_context,
                has_location_reference=lambda _text: False,
                is_ambiguous_time_location=lambda _location: False,
                is_location_clarification=lambda _text: False,
                live_info_kind=lambda _text: None,
                weather_followup_location=lambda *_args: None,
            ),
            "logging_utils": SimpleNamespace(log_turn=fake_log),
            "rag": SimpleNamespace(get_context=Mock(return_value="")),
            "safety": SimpleNamespace(
                check_transcript=lambda _text: True,
                check_reply=lambda reply, _language: reply,
                fallback_message=lambda *_args: "Please try again.",
            ),
            "stt": SimpleNamespace(is_transcript_unclear=lambda _text: False),
            "llm": SimpleNamespace(get_llm_reply=fake_llm),
        }
        try:
            main._reset_session()
            output = io.StringIO()
            with (
                patch.dict(sys.modules, fake_modules),
                patch("main.RAG_ENABLED", False),
                patch("main._speak"),
                redirect_stdout(output),
            ):
                main._handle_transcript("Where does Drake live?", None, speak=False)

            expected = "I can’t help verify someone’s current residence."
            self.assertIn(f"Assistant: {expected}", output.getvalue())
            self.assertEqual(main.SESSION_STATE["history"][-1]["content"], expected)
            self.assertEqual(fake_log.call_args.kwargs["reply"], expected)
            self.assertNotIn("Toronto", output.getvalue())
            self.assertNotIn("Los Angeles", output.getvalue())
            fake_live_context.assert_not_called()
            fake_llm.assert_not_called()
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_refusal_uses_selected_reply_language(self):
        self.assertEqual(
            current_residence_refusal("fr"),
            "Je ne peux pas aider à vérifier le lieu de résidence actuel d’une personne.",
        )

    def test_origin_question_continues_to_general_knowledge_path(self):
        self.assertFalse(is_current_residence_request("Where is Drake from?"))


if __name__ == "__main__":
    unittest.main()
