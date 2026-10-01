"""Mock-only coverage for the opt-in public-event language restriction."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

import language_utils
import live_info
import main
from fallback_messages import fallback_message
from language_utils import (
    choose_reply_language,
    event_language_capability_reply,
    event_generic_language_reply,
    event_requested_language_code,
    event_requested_reply_language,
    event_supported_language_message,
    strip_event_reply_language_suffix,
)


def _modules(llm):
    return {
        "live_info": SimpleNamespace(
            EVENT_CITY="Dubai", extract_explicit_location=lambda _text: None,
            get_live_context=Mock(return_value=""), has_location_reference=lambda _text: False,
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
        "llm": SimpleNamespace(get_llm_reply=llm),
    }


class EventLanguageModeTests(unittest.TestCase):
    def test_event_language_requests_send_general_replies_in_requested_language(self):
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(side_effect=("نكتة قصيرة.", "एक छोटा मज़ाक।", "一个小笑话。"))
        cases = (
            ("Can you tell me a joke in Arabic?", "Arabic", "نكتة قصيرة."),
            ("Tell me a joke in Hindi.", "Hindi", "एक छोटा मज़ाक।"),
            ("Please tell me a joke in Mandarin Chinese.", "Chinese", "一个小笑话。"),
        )
        try:
            main._reset_session()
            main.SESSION_STATE["last_language_code"] = "en"
            with (
                patch.dict(sys.modules, _modules(llm)),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
                patch("main.RAG_ENABLED", False),
                redirect_stdout(io.StringIO()),
            ):
                for request, language_name, expected_reply in cases:
                    main._handle_transcript(request, "en", speak=False)
                    self.assertEqual(llm.call_args.kwargs["language"], language_name)
                    self.assertEqual(main.SESSION_STATE["last_language_code"], "en")
                    self.assertEqual(main.SESSION_STATE["history"][-1]["content"], expected_reply)
            self.assertEqual(event_requested_reply_language(
                "Can you tell me a joke in Arabic?"), ("ar", "Arabic")
            )
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_supported_language_capability_requests_reply_in_that_language(self):
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(return_value="Should not be used.")
        cases = (
            ("Can you speak English?", "Yes, I can speak English. Hello!", "en"),
            ("Can you talk in Arabic?", "نعم، أستطيع التحدث بالعربية. مرحبًا!", "ar"),
            ("Can you speak Hindi?", "हाँ, मैं हिंदी बोल सकता हूँ। नमस्ते!", "hi"),
            ("Could you communicate in Mandarin Chinese?", "是的，我会说普通话。你好！", "zh"),
        )
        try:
            main._reset_session()
            main.SESSION_STATE["last_language_code"] = "en"
            output = io.StringIO()
            with (
                patch.dict(sys.modules, _modules(llm)),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
                redirect_stdout(output),
            ):
                for request, reply, language_code in cases:
                    main._handle_transcript(request, "en", speak=False)
                    self.assertIn(f"Assistant: {reply}", output.getvalue())
                    self.assertEqual(main.SESSION_STATE["last_language_code"], "en")
                    output.truncate(0)
                    output.seek(0)
            llm.assert_not_called()
            self.assertIsNone(event_language_capability_reply(
                "Can you talk in Arabic and curse my friend?"
            ))
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_can_or_could_do_this_in_language_is_local_and_refuses_unsupported_targets(self):
        """Generic language requests confirm support without an LLM call."""
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(return_value="Should not be used.")
        supported_cases = (
            ("Can you say this in English?", "en", "Yes, I can help in English."),
            ("Can you say this in Arabic?", "ar", "نعم، أستطيع المساعدة بالعربية."),
            ("Could you explain this in Hindi?", "hi", "हाँ, मैं हिंदी में मदद कर सकता हूँ।"),
            ("Could you do this in Mandarin Chinese?", "zh", "是的，我可以用中文帮忙。"),
        )
        try:
            main._reset_session()
            main.SESSION_STATE["last_language_code"] = "en"
            output = io.StringIO()
            with (
                patch.dict(sys.modules, _modules(llm)),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
                redirect_stdout(output),
            ):
                for request, expected_code, expected_reply_start in supported_cases:
                    with self.subTest(request=request):
                        main._handle_transcript(request, "en", speak=False)
                        self.assertIn(expected_reply_start, output.getvalue())
                        self.assertEqual(main.SESSION_STATE["last_language_code"], "en")
                        self.assertEqual(event_requested_language_code(request), expected_code)
                        self.assertEqual(event_generic_language_reply(request)[0], expected_code)
                        output.truncate(0)
                        output.seek(0)

                main._handle_transcript("Could you explain this in French?", "en", speak=False)
                self.assertIn(event_supported_language_message("en"), output.getvalue())
            llm.assert_not_called()
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_live_location_is_separate_from_supported_reply_language(self):
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(side_effect=(
            "الوقت في دبي。", "दुबई का समय।", "迪拜的天气。",
            "भारत का समय।", "中国的时间。", "法国的时间。",
        ))
        live_context = Mock(return_value="Live weather for Dubai: 30°C, clear sky.")
        modules = _modules(llm)
        modules["live_info"] = SimpleNamespace(
            EVENT_CITY="Dubai",
            extract_explicit_location=live_info.extract_explicit_location,
            get_live_context=live_context,
            has_location_reference=lambda _text: False,
            is_ambiguous_time_location=lambda _location: False,
            is_location_clarification=lambda _text: False,
            live_info_kind=lambda message: "weather" if "weather" in message else "time",
            weather_followup_location=lambda *_args: None,
            live_info_failure_reply=live_info.live_info_failure_reply,
        )
        cases = (
            ("Can you tell me the time in Dubai in Arabic?", "Arabic", "Can you tell me the time in Dubai"),
            ("Can you tell me the time in Dubai in Hindi?", "Hindi", "Can you tell me the time in Dubai"),
            ("Can you tell me the weather in Dubai in Mandarin Chinese?", "Chinese", "Can you tell me the weather in Dubai"),
            ("Can you tell me the time in India in Arabic?", "Arabic", "Can you tell me the time in India"),
            ("Can you tell me the time in China in Hindi?", "Hindi", "Can you tell me the time in China"),
            ("Can you tell me the time in France in Chinese?", "Chinese", "Can you tell me the time in France"),
        )
        try:
            main._reset_session()
            with (
                patch.dict(sys.modules, modules),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
                patch("main.RAG_ENABLED", False),
                redirect_stdout(io.StringIO()),
            ):
                for request, expected_language, expected_lookup in cases:
                    with self.subTest(request=request):
                        calls_before = llm.call_count
                        main._handle_transcript(request, "en", speak=False)
                        self.assertEqual(live_context.call_args.args[0], expected_lookup)
                        if "weather" in expected_lookup:
                            self.assertEqual(llm.call_count, calls_before)
                        else:
                            self.assertEqual(llm.call_args.args[0], expected_lookup)
                            self.assertEqual(llm.call_args.kwargs["language"], expected_language)
            self.assertEqual(
                strip_event_reply_language_suffix("Can you tell me the weather in Dubai in Arabic?"),
                "Can you tell me the weather in Dubai",
            )
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_live_lookup_failure_is_localized_and_skips_llm(self):
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(return_value="Should not be used.")
        modules = _modules(llm)
        modules["live_info"] = SimpleNamespace(
            EVENT_CITY="Dubai",
            extract_explicit_location=lambda message: "Dubai" if "Dubai" in message else None,
            get_live_context=Mock(return_value="Live weather for Dubai is unavailable. Do not guess."),
            has_location_reference=lambda _text: False,
            is_ambiguous_time_location=lambda _location: False,
            is_location_clarification=lambda _text: False,
            live_info_kind=lambda _message: "weather",
            weather_followup_location=lambda *_args: None,
            live_info_failure_reply=live_info.live_info_failure_reply,
        )
        try:
            main._reset_session()
            output = io.StringIO()
            with (
                patch.dict(sys.modules, modules),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
                redirect_stdout(output),
            ):
                main._handle_transcript("Can you tell me the weather in Dubai in Arabic?", "en", speak=False)
            self.assertIn("عذرًا، لا أستطيع الحصول على معلومات الطقس الآن.", output.getvalue())
            llm.assert_not_called()
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_benign_arabic_joke_falls_back_to_a_real_joke_after_safe_moderation_reply(self):
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(return_value="A model joke.")
        modules = _modules(llm)
        modules["safety"] = SimpleNamespace(
            check_transcript=lambda _text: True,
            check_reply=lambda _reply, language: fallback_message("safe", language),
            fallback_message=fallback_message,
        )
        try:
            main._reset_session()
            with (
                patch.dict(sys.modules, modules),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
                patch("main.RAG_ENABLED", False),
                redirect_stdout(io.StringIO()),
            ):
                main._handle_transcript("Can you talk in Arabic and tell me a joke in Arabic?", "en", speak=False)
            self.assertIn("خريطة", main.SESSION_STATE["history"][-1]["content"])
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_mixed_live_request_keeps_location_and_each_requested_language(self):
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(return_value="Should not be used.")
        modules = _modules(llm)
        live_context = Mock(side_effect=(
            "Live time for Dubai: 03:15 PM (Asia/Dubai).",
            "Live weather for Dubai: 30°C, clear sky.",
        ))
        modules["live_info"] = SimpleNamespace(
            EVENT_CITY="Dubai", extract_explicit_location=lambda _text: None,
            get_live_context=live_context, has_location_reference=lambda _text: False,
            is_ambiguous_time_location=lambda _location: False,
            is_location_clarification=lambda _text: False,
            live_info_kind=lambda _text: None, weather_followup_location=lambda *_args: None,
        )
        try:
            main._reset_session()
            output = io.StringIO()
            with (
                patch.dict(sys.modules, modules),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
                redirect_stdout(output),
            ):
                main._handle_transcript(
                    "Can you tell me the time in Dubai in Arabic and the weather in Hindi?",
                    "en", speak=False,
                )
            self.assertIn("الوقت الحالي", output.getvalue())
            self.assertIn("मौसम", output.getvalue())
            self.assertEqual(
                live_context.call_args_list[0].args[0], "What time is it in dubai?"
            )
            self.assertEqual(
                live_context.call_args_list[1].args[0], "What's the weather in dubai?"
            )
            llm.assert_not_called()
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_empty_transcript_uses_local_repeat_prompt_before_event_routing(self):
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(return_value="Should not be used.")
        modules = _modules(llm)
        log_turn = Mock()
        modules["stt"] = SimpleNamespace(is_transcript_unclear=lambda _text: True)
        modules["safety"] = SimpleNamespace(
            check_transcript=lambda _text: True,
            check_reply=lambda reply, _language: reply,
            fallback_message=fallback_message,
        )
        modules["logging_utils"] = SimpleNamespace(log_turn=log_turn)
        try:
            main._reset_session()
            output = io.StringIO()
            with (
                patch.dict(sys.modules, modules),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
                redirect_stdout(output),
            ):
                main._handle_transcript("", "ja", speak=False)

            self.assertIn("Transcript unclear.", output.getvalue())
            self.assertEqual(
                "I didn't quite get that, sorry. Could you repeat it again?",
                log_turn.call_args.kwargs["reply"],
            )
            llm.assert_not_called()
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_clear_english_overrides_misleading_labels(self):
        for transcript in ("Can you talk?", "Who made you?", "Tell me a joke"):
            for wrong_label in ("fr", "fi", "so", "id"):
                with self.subTest(transcript=transcript, label=wrong_label):
                    with patch.object(
                        language_utils, "detect_language_confident", return_value=(wrong_label, wrong_label)
                    ):
                        language, uncertain = choose_reply_language(transcript, wrong_label, None)
                    self.assertEqual(language[0], "en")
                    self.assertFalse(uncertain)

    def test_allowed_native_scripts_route_to_their_language(self):
        cases = (("مرحبا، كيف حالك؟", "ar"), ("नमस्ते, आप कैसे हैं?", "hi"), ("你好，你好吗？", "zh"))
        for transcript, expected in cases:
            with self.subTest(transcript=transcript):
                language, uncertain = choose_reply_language(transcript, "fr", None)
                self.assertEqual(language[0], expected)
                self.assertFalse(uncertain)

    def test_unsupported_languages_return_local_message_without_llm(self):
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(return_value="Should not be used.")
        cases = (
            ("Bonjour", "fr"), ("کیا حال ہے؟", "ur"), ("سلام، چطوری؟", "fa"),
            ("নমস্কার", "bn"), ("നമസ്കാരം", "ml"), ("こんにちは", "ja"),
            ("Translate hello into French.", "en"),
        )
        try:
            main._reset_session()
            output = io.StringIO()
            with patch.dict(sys.modules, _modules(llm)), patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}), redirect_stdout(output):
                for transcript, detected in cases:
                    main._handle_transcript(transcript, detected, speak=False)
                    self.assertEqual(
                        main.SESSION_STATE["history"], [],
                    )
            self.assertEqual(
                output.getvalue().count(event_supported_language_message("fr")), len(cases)
            )
            llm.assert_not_called()
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_supported_event_translations_keep_english_session_language(self):
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(side_effect=("صباح الخير", "सुप्रभात", "你好", "I am a robot assistant."))
        requests = (
            ("Say good morning in Arabic.", "Arabic"),
            ("Say good morning in Hindi.", "Hindi"),
            ("Say hello in Mandarin Chinese.", "Chinese"),
        )
        try:
            main._reset_session()
            main.SESSION_STATE["last_language_code"] = "en"
            with patch.dict(sys.modules, _modules(llm)), patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}), patch("main.RAG_ENABLED", False), redirect_stdout(io.StringIO()):
                for request, target_language in requests:
                    main._handle_transcript(request, "en", speak=False)
                    self.assertEqual(llm.call_args.kwargs["language"], target_language)
                    self.assertEqual(main.SESSION_STATE["last_language_code"], "en")
                main._handle_transcript("Who made you?", "fi", speak=False)
            self.assertEqual(main.SESSION_STATE["last_language_code"], "en")
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_mode_off_keeps_broader_language_path(self):
        saved_state = dict(main.SESSION_STATE)
        llm = Mock(return_value="Bonjour.")
        try:
            main._reset_session()
            with patch.dict(sys.modules, _modules(llm)), patch.dict("os.environ", {"LANGUAGE_MODE": ""}), patch("main.RAG_ENABLED", False), redirect_stdout(io.StringIO()):
                main._handle_transcript("Bonjour", "fr", speak=False)
            llm.assert_called_once()
            self.assertEqual(main.SESSION_STATE["last_language_code"], "fr")
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)


if __name__ == "__main__":
    unittest.main()
