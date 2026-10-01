"""Offline checks for targeted translation requests."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from fallback_messages import fallback_message
from translation import (
    local_event_translation, parse_multi_translation_intents,
    parse_translation_intent, translation_only_reply,
)


@patch.dict("os.environ", {"LANGUAGE_MODE": ""})
class TranslationIntentTests(unittest.TestCase):
    def test_supported_translation_patterns_parse_the_phrase_and_target(self):
        cases = (
            ("Say hello good morning in Arabic.", "hello good morning", "ar"),
            ("Can you say thank you for visiting in Urdu?", "thank you for visiting", "ur"),
            ("Could you say welcome in Hindi?", "welcome", "hi"),
            ("Please say good evening in French.", "good evening", "fr"),
            ("Translate hello to Arabic.", "hello", "ar"),
            ("Translate thank you in Hindi.", "thank you", "hi"),
            ("Translate welcome into Urdu.", "welcome", "ur"),
            ("Translate welcome into Hindi and explain when people use it.", "welcome", "hi"),
            ("How do I say AIRHUG welcome in French?", "AIRHUG welcome", "fr"),
        )
        for request, phrase, target in cases:
            with self.subTest(request=request):
                intent = parse_translation_intent(request)
                self.assertIsNotNone(intent)
                self.assertEqual((intent.phrase, intent.language_code), (phrase, target))

    def test_non_translation_question_does_not_parse_as_translation(self):
        self.assertIsNone(parse_translation_intent("Can you explain this robot?"))
        self.assertIsNone(parse_translation_intent("Can you say a joke?"))
        self.assertIsNone(parse_translation_intent("Sê yo welcome an orudor."))
        self.assertIsNone(parse_translation_intent("Can you say a joke in Arabic?"))
        self.assertIsNone(parse_translation_intent("Can you say a joke in Hindi?"))

    def test_common_event_translation_has_a_safe_local_fallback(self):
        self.assertEqual(local_event_translation("welcome", "hi"), "स्वागत है")

    def test_translation_reply_drops_an_extra_help_sentence(self):
        self.assertEqual(translation_only_reply("晚上好！欢迎来到活动现场。"), "晚上好！")

    def test_repeated_say_commands_parse_each_translation(self):
        intents = parse_multi_translation_intents(
            "Say hello in Arabic, say good morning in Hindi, and say welcome in Chinese."
        )
        self.assertEqual(
            [(intent.phrase, intent.language_code) for intent in intents],
            [("hello", "ar"), ("good morning", "hi"), ("welcome", "zh")],
        )

    def test_translation_uses_vetted_local_phrase_after_safe_moderation_fallback(self):
        saved_state = dict(main.SESSION_STATE)
        fake_llm = Mock(return_value="A model translation.")
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
                check_transcript=lambda _text: True,
                check_reply=lambda _reply, language: fallback_message("safe", language),
                fallback_message=fallback_message,
            ),
            "rag": SimpleNamespace(get_context=lambda _text: ""),
            "logging_utils": SimpleNamespace(log_turn=Mock()),
            "llm": SimpleNamespace(get_llm_reply=fake_llm),
        }
        try:
            main._reset_session()
            with patch.dict(sys.modules, fake_modules), patch.object(main, "RAG_ENABLED", False), redirect_stdout(io.StringIO()):
                main._handle_transcript("Translate welcome into Hindi and explain when people use it.", "en", speak=False)
            self.assertEqual(main.SESSION_STATE["history"][-1]["content"], "स्वागत है")
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_translation_uses_target_language_and_skips_live_info(self):
        saved_state = dict(main.SESSION_STATE)
        fake_llm = Mock(side_effect=("सुप्रभात", "شكرا لزيارتكم", "خوش آمدید", "Bienvenue AIRHUG"))
        live_context = Mock(return_value="")
        fake_modules = {
            "live_info": SimpleNamespace(
                EVENT_CITY="Dubai", extract_explicit_location=lambda _text: None,
                get_live_context=live_context, has_location_reference=lambda _text: False,
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
            "logging_utils": SimpleNamespace(log_turn=Mock()),
            "llm": SimpleNamespace(get_llm_reply=fake_llm),
        }
        cases = (
            ("Say good morning in Hindi.", "Hindi", "सुप्रभात"),
            ("Can you say thank you for visiting in Arabic?", "Arabic", "شكرا لزيارتكم"),
            ("How do I say welcome in Urdu?", "Urdu", "خوش آمدید"),
            ("How do I say AIRHUG welcome in French?", "French", "Bienvenue AIRHUG"),
        )
        try:
            main._reset_session()
            main.SESSION_STATE["last_language_code"] = "en"
            with patch.dict(sys.modules, fake_modules), patch("main.RAG_ENABLED", False), redirect_stdout(io.StringIO()):
                for request, language, expected in cases:
                    main._handle_transcript(request, "en", speak=False)
                    self.assertEqual(main.SESSION_STATE["history"][-1]["content"], expected)
                    self.assertEqual(main.SESSION_STATE["last_language_code"], "en")
                    self.assertEqual(fake_llm.call_args.kwargs["language"], language)
                    if language == "French":
                        self.assertEqual(fake_llm.call_args.args[0], "AIRHUG welcome")
                    self.assertFalse(fake_llm.call_args.kwargs["use_web"])
                    self.assertTrue(fake_llm.call_args.kwargs["translation_only"])
            live_context.assert_not_called()
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_non_translation_question_uses_normal_reply_path(self):
        saved_state = dict(main.SESSION_STATE)
        fake_llm = Mock(return_value="I can explain it.")
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
            "rag": SimpleNamespace(get_context=lambda _text: ""),
            "logging_utils": SimpleNamespace(log_turn=Mock()),
            "llm": SimpleNamespace(get_llm_reply=fake_llm),
        }
        try:
            main._reset_session()
            with patch.dict(sys.modules, fake_modules), patch("main.RAG_ENABLED", False), redirect_stdout(io.StringIO()):
                main._handle_transcript("Can you explain this robot?", "en", speak=False)
            self.assertNotIn("translation_only", fake_llm.call_args.kwargs)
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)


if __name__ == "__main__":
    unittest.main()
