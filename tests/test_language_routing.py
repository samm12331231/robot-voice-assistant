"""Focused checks for multilingual routing and greeting ambiguity."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import language_utils
import live_info
from language_utils import choose_reply_language, has_confident_english_evidence
from main import SESSION_STATE, _current_language, _handle_transcript, _reset_session
from stt import is_transcript_unclear


@patch.dict("os.environ", {"LANGUAGE_MODE": ""})
class LanguageRoutingTests(unittest.TestCase):
    def test_clear_latin_english_greetings_route_to_english(self):
        for phrase in ("hello", "hi", "hey", "hello hello", "how are you", "thanks"):
            with self.subTest(phrase=phrase):
                self.assertEqual(_current_language(phrase, "it"), ("en", "English"))
                if phrase == "hello hello":
                    language, uncertain = choose_reply_language(phrase, "it", None)
                    self.assertEqual(language, ("en", "English"))
                    self.assertFalse(uncertain)

    def test_hola_variants_with_punctuation_route_to_spanish(self):
        for phrase in ("hola", "Hola, hola."):
            with self.subTest(phrase=phrase):
                self.assertEqual(_current_language(phrase, "so"), ("es", "Spanish"))

    def test_english_grammar_evidence_overrides_bad_stt_and_text_labels(self):
        examples = (
            ("Where does Drake live?", "af", "so"),
            ("Can you tell me a joke?", "fi", "fi"),
            ("What's the weather there?", "fr", "it"),
            ("What’s the weather there?", "fr", "it"),
            ("I didn't like that joke. Say another joke.", "so", "af"),
        )
        for transcript, stt_language, text_language in examples:
            with self.subTest(transcript=transcript):
                with patch.object(
                    language_utils, "detect_language_confident",
                    return_value=(text_language, text_language.upper()),
                ):
                    self.assertEqual(
                        _current_language(transcript, stt_language),
                        ("en", "English"),
                    )

    def test_short_acknowledgements_follow_session_or_event_language(self):
        examples = (
            ("Yes.", "fr", "en", "en"),
            ("No", "so", "es", "es"),
            ("Yeah", "fi", None, "en"),
            ("Okay", "it", "ur", "ur"),
            ("Thank you", "fr", "en", "en"),
        )
        for transcript, stt_language, previous, expected in examples:
            with self.subTest(transcript=transcript, previous=previous):
                with patch.object(
                    language_utils, "detect_language_confident",
                    return_value=(stt_language, stt_language.upper()),
                ) as detector:
                    language, uncertain = choose_reply_language(
                        transcript, stt_language, previous, default_language="en"
                    )
                self.assertEqual(language[0], expected)
                self.assertFalse(uncertain)
                detector.assert_not_called()

    def test_uncertain_one_word_does_not_replace_confirmed_session_language(self):
        with patch.object(
            language_utils, "detect_language_confident", return_value=("fr", "French")
        ) as detector:
            language, uncertain = choose_reply_language("oui", "fr", "en")
        self.assertEqual(language, ("en", "English"))
        self.assertTrue(uncertain)
        detector.assert_not_called()

    def test_english_evidence_does_not_override_other_latin_languages(self):
        examples = (
            ("Bonjour, comment allez-vous?", "fr"),
            ("Bonjour, comment ça va ?", "fr"),
            ("Muchas gracias por tu ayuda.", "es"),
            ("Merhaba, nasılsın?", "tr"),
            ("Kumusta ka? Maraming salamat.", "tl"),
            ("Obrigado por sua ajuda.", "pt"),
            ("Waar woon Drake?", "af"),
        )
        for transcript, expected in examples:
            with self.subTest(language=expected):
                self.assertFalse(has_confident_english_evidence(transcript))
                with patch.object(
                    language_utils, "detect_language_confident",
                    return_value=(expected, expected.upper()),
                ):
                    self.assertEqual(_current_language(transcript, expected)[0], expected)

    def test_halo_and_borrowed_script_greetings_stay_uncertain(self):
        for phrase in ("halo", "halo halo", "ہیلو", "ہیلو ہیلو", "هلو", "هيلو"):
            with self.subTest(phrase=phrase):
                language, uncertain = choose_reply_language(
                    phrase, "ur", "hi", default_language="en"
                )
                self.assertTrue(uncertain)
                self.assertEqual(language, ("en", "English"))

    def test_full_non_latin_sentences_keep_their_language(self):
        examples = (
            ("کیا حال ہے", "ur"),
            ("ہیلو، کیا حال ہے", "ur"),
            ("السلام عليكم كيف حالك", "ar"),
            ("مرحبا كيف حالك", "ar"),
            ("नमस्ते आप कैसे हो", "hi"),
            ("你好世界", "zh"),
            ("こんにちは世界", "ja"),
            ("Привет, как дела?", "ru"),
            ("این یک جمله فارسی است", "fa"),
        )
        for transcript, expected in examples:
            with self.subTest(language=expected):
                self.assertEqual(_current_language(transcript, "en")[0], expected)

    def test_arabic_greeting_phrases_override_wrong_persian_or_urdu_labels(self):
        cases = (
            ("السلام عليكم", "fa"),
            ("كيف حالك", "ur"),
            ("السلام علیکم، کیف حالک", "fa"),
        )
        for transcript, wrong_label in cases:
            with self.subTest(transcript=transcript):
                language, uncertain = choose_reply_language(transcript, wrong_label, None)
                self.assertEqual(language, ("ar", "Arabic"))
                self.assertFalse(uncertain)

    def test_persian_and_urdu_controls_do_not_match_arabic_greeting_override(self):
        controls = (("این یک جمله فارسی است", "fa"), ("کیا حال ہے", "ur"))
        for transcript, expected in controls:
            with self.subTest(transcript=transcript):
                self.assertEqual(choose_reply_language(transcript, "ar", None)[0][0], expected)

    def test_fresh_english_hindi_english_turns_override_session_memory(self):
        previous = SESSION_STATE["last_language_code"]
        try:
            SESSION_STATE["last_language_code"] = "en"
            self.assertEqual(_current_language("नमस्ते आप कैसे हो", "en")[0], "hi")
            SESSION_STATE["last_language_code"] = "hi"
            self.assertEqual(_current_language("Can you tell me a joke?", "hi"), ("en", "English"))
        finally:
            SESSION_STATE["last_language_code"] = previous

    def test_confirmed_english_survives_ack_then_full_french_replaces_it(self):
        previous_state = dict(SESSION_STATE)
        fake_llm_reply = Mock(return_value="A short reply.")
        fake_modules = {
            "live_info": live_info,
            "stt": SimpleNamespace(is_transcript_unclear=lambda _text: False),
            "safety": SimpleNamespace(
                check_transcript=lambda _text: True,
                check_reply=lambda reply, _language: reply,
                fallback_message=lambda *_args: "Please try again.",
            ),
            "rag": SimpleNamespace(get_context=lambda _text: ""),
            "logging_utils": SimpleNamespace(log_turn=Mock()),
            "llm": SimpleNamespace(get_llm_reply=fake_llm_reply),
        }
        try:
            _reset_session()
            with patch.dict(sys.modules, fake_modules), patch("main.RAG_ENABLED", False):
                with patch.object(
                    language_utils, "detect_language_confident",
                    return_value=("af", "Afrikaans"),
                ) as detector:
                    _handle_transcript("Where does Drake live?", "af", speak=False)
                    self.assertEqual(SESSION_STATE["last_language_code"], "en")
                    detector.assert_not_called()

                with patch.object(
                    language_utils, "detect_language_confident",
                    return_value=("fr", "French"),
                ) as detector:
                    _handle_transcript("Yes.", "fr", speak=False)
                    self.assertEqual(SESSION_STATE["last_language_code"], "en")
                    detector.assert_not_called()

                with patch.object(
                    language_utils, "detect_language_confident",
                    return_value=("fr", "French"),
                ) as detector:
                    _handle_transcript("oui", "fr", speak=False)
                    self.assertEqual(SESSION_STATE["last_language_code"], "en")
                    detector.assert_not_called()

                with patch.object(
                    language_utils, "detect_language_confident",
                    return_value=("fr", "French"),
                ) as detector:
                    _handle_transcript("Bonjour, comment ça va ?", "en", speak=False)
                    self.assertEqual(SESSION_STATE["last_language_code"], "fr")
                    detector.assert_called_once()
        finally:
            SESSION_STATE.clear()
            SESSION_STATE.update(previous_state)

    def test_short_greetings_are_not_rejected_as_unclear(self):
        for greeting in ("hi", "hey", "hello", "hola", "halo"):
            with self.subTest(greeting=greeting):
                self.assertFalse(is_transcript_unclear(greeting))


if __name__ == "__main__":
    unittest.main()

