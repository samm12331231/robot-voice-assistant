"""Offline, deterministic regression matrix for assistant language routing."""
import sys
import unittest
from contextlib import redirect_stdout
import io
from types import SimpleNamespace
from unittest.mock import Mock, patch

import language_utils
from language_utils import choose_reply_language
from main import SESSION_STATE, _handle_transcript, _reset_session


ENGLISH_SENTENCES = {
    "greetings": (
        "Hello, how are you doing today?",
        "Good morning, how are you?",
        "Hi, can you help me please?",
        "Hey, where are you going?",
        "Hello, can you hear me?",
    ),
    "jokes and fun facts": (
        "Can you tell me a joke?",
        "Tell me another joke, please.",
        "I didn't like that joke. Say another joke.",
        "Could you make up a funny story for me?",
        "Give me a fun fact about space.",
    ),
    "weather and time": (
        "What's the weather there?",
        "What about the weather there?",
        "Can you check the weather in Tokyo today?",
        "What time is it in London right now?",
        "Could you tell me today's weather in Dubai?",
        "Is it raining there now?",
    ),
    "company and general knowledge": (
        "Where does Drake live?",
        "Who is the founder of this company?",
        "Can you explain what this robot does?",
        "Tell me how this product works.",
        "Could you explain the capital of Japan?",
        "Can I join NASA?",
        "Can I ask a question?",
        "Can I talk to you?",
    ),
    "follow-ups": (
        "Could you explain that again?",
        "Can you say that another way?",
        "Would you tell me more about it?",
        "What do you mean by that?",
        "We're talking about Dubai right now.",
    ),
    "contractions": (
        "I'm looking for the answer.",
        "Can't you tell me another joke?",
        "Don't worry, I understand.",
        "What's happening right now?",
        "You aren't supposed to wait.",
        "I won't do that again.",
    ),
    "informal English": (
        "That sounds really cool.",
        "I like that a lot.",
        "That's pretty cool, thanks.",
        "Yeah, that sounds good to me.",
        "No, I don't think so.",
    ),
    "polite requests": (
        "Could you help me with this?",
        "Would you please tell me the time?",
        "Can I ask you a question?",
        "Could you say that one more time?",
        "Please tell me what this means.",
    ),
}
WRONG_DETECTOR_LABELS = ("af", "fr", "fi", "so", "it", "et", "nl")
ACKNOWLEDGEMENTS = ("Yes.", "No.", "Yeah.", "Yep.", "Okay.", "Ok.", "Sure.", "Thanks.", "Thank you.")
SHORT_PHRASE_CASES = (
    # category, transcript, expected language, normal detector, normal STT, conflict labels
    ("English", "Hello", "en", "en", "en", WRONG_DETECTOR_LABELS),
    ("English", "Hello, hello.", "en", "en", "en", WRONG_DETECTOR_LABELS),
    ("English", "hi", "en", "en", "en", WRONG_DETECTOR_LABELS),
    ("English", "hey", "en", "en", "en", WRONG_DETECTOR_LABELS),
    ("English", "thank you", "en", "en", "en", WRONG_DETECTOR_LABELS),
    ("English", "can you dance?", "en", "en", "en", WRONG_DETECTOR_LABELS),
    ("English", "can you wave?", "en", "en", "en", WRONG_DETECTOR_LABELS),
    ("English", "what time is it?", "en", "en", "en", WRONG_DETECTOR_LABELS),
    ("English", "tell me a joke", "en", "en", "en", WRONG_DETECTOR_LABELS),
    ("English", "Who made you?", "en", "en", "en", ("so", "fi", "fr", "af", "it")),
    ("English", "Can you talk?", "en", "en", "en", ("tr", "fi", "fr", "af", "it")),
    ("English", "Can you speak Hindi?", "en", "en", "en", ("id", "fi", "fr", "af", "it")),
    ("English", "Can you speak Urdu?", "en", "en", "en", ("id", "fi", "fr", "af", "it")),
    ("English", "Can you understand me?", "en", "en", "en", ("so", "fi", "fr", "af", "it")),
    ("English", "What languages do you speak?", "en", "en", "en", ("no", "fi", "fr", "af", "it")),
    ("English", "Tell me something interesting.", "en", "en", "en", ("no", "fi", "fr", "af", "it")),
    ("Arabic", "السلام عليكم", "ar", "ar", "ar", ("fa", "ur")),
    ("Arabic", "كيف حالك؟", "ar", "ar", "ar", ("fa", "ur")),
    ("Hindi", "नमस्ते", "hi", "hi", "hi", ("fr", "fi")),
    ("Hindi", "आप कैसे हैं?", "hi", "hi", "hi", ("fr", "fi")),
    ("Urdu", "سلام، کیا حال ہے؟", "ur", "ur", "ur", ("ar", "fa")),
    ("Urdu", "کیا حال ہے؟", "ur", "ur", "ur", ("ar", "fa")),
    ("Persian/Dari", "سلام، چطوری؟", "fa", "fa", "fa", ("ar", "ur")),
    ("Persian/Dari", "حالت چطوره؟", "fa", "fa", "fa", ("ar", "ur")),
    ("French", "Bonjour", "fr", "fr", "fr", ()),
    ("French", "Comment ça va ?", "fr", "fr", "fr", ()),
    ("Spanish", "Hola", "es", "es", "es", ("fr", "fi")),
    ("Spanish", "Hola, hola.", "es", "es", "es", ("fr", "fi")),
    ("Spanish", "¿Cómo estás?", "es", "es", "es", ()),
    ("Chinese", "你好", "zh", "zh", "zh", ("fr", "fi")),
    ("Chinese", "你好吗？", "zh", "zh", "zh", ("fr", "fi")),
    ("Japanese", "こんにちは", "ja", "ja", "ja", ("fr", "fi")),
    ("Japanese", "元気ですか？", "ja", "ja", "ja", ("fr", "fi")),
    ("Bengali", "নমস্কার", "bn", "bn", "bn", ("fr", "fi")),
    ("Bengali", "আপনি কেমন আছেন?", "bn", "bn", "bn", ("fr", "fi")),
    ("Malayalam", "നമസ്കാരം", "ml", "ml", "ml", ("fr", "fi")),
    ("Malayalam", "സുഖമാണോ?", "ml", "ml", "ml", ("fr", "fi")),
)


def _detected(code: str):
    return patch.object(
        language_utils,
        "detect_language_confident",
        return_value=(code, code.upper()),
    )


@patch.dict("os.environ", {"LANGUAGE_MODE": ""})
class LanguageRegressionMatrixTests(unittest.TestCase):
    def test_ambiguous_short_latin_greeting_matrix(self):
        for transcript in ("hallo", "Hallo, hallo."):
            with self.subTest(transcript=transcript):
                with _detected("it"):
                    actual, uncertain = choose_reply_language(
                        transcript, "it", "fr", default_language="en"
                    )
                details = (
                    f"transcript={transcript!r}, detector='it', previous='fr', "
                    f"expected='en', actual={actual[0]!r}, uncertain={uncertain}"
                )
                self.assertEqual(actual[0], "en", details)
                self.assertTrue(uncertain, details)

    def test_short_phrase_matrix(self):
        for category, transcript, expected, normal_detector, normal_stt, conflicts in SHORT_PHRASE_CASES:
            with self.subTest(category=category, transcript=transcript, mode="normal"):
                with _detected(normal_detector):
                    actual, uncertain = choose_reply_language(
                        transcript, normal_stt, None, default_language="en"
                    )
                details = (
                    f"transcript={transcript!r}, detector={normal_detector!r}, "
                    f"previous=None, expected={expected!r}, actual={actual[0]!r}, "
                    f"uncertain={uncertain}"
                )
                self.assertEqual(actual[0], expected, details)
                self.assertFalse(uncertain, details)

            for conflicting_detector in conflicts:
                with self.subTest(category=category, transcript=transcript,
                                  mode="conflict", detector=conflicting_detector):
                    with _detected(conflicting_detector):
                        actual, uncertain = choose_reply_language(
                            transcript, conflicting_detector, None, default_language="en"
                        )
                    details = (
                        f"transcript={transcript!r}, detector={conflicting_detector!r}, "
                        f"previous=None, expected={expected!r}, actual={actual[0]!r}, "
                        f"uncertain={uncertain}"
                    )
                    self.assertEqual(actual[0], expected, details)
                    self.assertFalse(uncertain, details)

    def test_clearly_english_transcripts_ignore_wrong_detector_labels(self):
        case_number = 0
        for group, transcripts in ENGLISH_SENTENCES.items():
            for transcript in transcripts:
                for detector_language in WRONG_DETECTOR_LABELS:
                    case_number += 1
                    with self.subTest(group=group, case=case_number):
                        previous = "en" if transcript in ACKNOWLEDGEMENTS else None
                        with _detected(detector_language):
                            actual, uncertain = choose_reply_language(
                                transcript,
                                detector_language,
                                previous,
                                default_language="en",
                            )
                        details = (
                            f"transcript={transcript!r}, detector={detector_language!r}, "
                            f"previous={previous!r}, expected='en', actual={actual[0]!r}, "
                            f"uncertain={uncertain}"
                        )
                        self.assertEqual(actual[0], "en", details)
                        self.assertFalse(uncertain, details)

        # Each English acknowledgment is checked against every misleading label.
        for transcript in ACKNOWLEDGEMENTS:
            for detector_language in WRONG_DETECTOR_LABELS:
                with self.subTest(group="English-session acknowledgements", transcript=transcript,
                                  detector=detector_language):
                    with _detected(detector_language):
                        actual, uncertain = choose_reply_language(
                            transcript, detector_language, "en", default_language="en"
                        )
                    details = (
                        f"transcript={transcript!r}, detector={detector_language!r}, "
                        f"previous='en', expected='en', actual={actual[0]!r}, "
                        f"uncertain={uncertain}"
                    )
                    self.assertEqual(actual[0], "en", details)
                    self.assertFalse(uncertain, details)

    def test_non_english_controls_keep_their_actual_language(self):
        controls = (
            ("مرحبا كيف حالك", "ar", "fi"),
            ("کیا حال ہے", "ur", "fr"),
            ("این یک جمله فارسی است", "fa", "so"),
            ("नमस्ते आप कैसे हो", "hi", "it"),
            ("Hola, hola.", "es", "fr"),
            ("Bonjour, comment ça va ?", "fr", "af"),
            ("Waar woon Drake?", "af", "it"),
            ("Obrigado por sua ajuda.", "pt", "nl"),
            ("你好世界", "zh", "fi"),
            ("こんにちは世界", "ja", "so"),
        )
        for transcript, expected, simulated_stt in controls:
            with self.subTest(transcript=transcript, expected=expected):
                detector_language = expected if expected in {"es", "fr", "af", "pt"} else "en"
                with _detected(detector_language):
                    actual, uncertain = choose_reply_language(
                        transcript, simulated_stt, "en", default_language="en"
                    )
                details = (
                    f"transcript={transcript!r}, detector={detector_language!r}, "
                    f"previous='en', expected={expected!r}, actual={actual[0]!r}"
                )
                self.assertEqual(actual[0], expected, details)
                self.assertFalse(uncertain, details)

    def test_ambiguous_and_short_greetings_follow_documented_policy(self):
        cases = (
            ("hello", "fr", "ar", "en", False),
            ("hi", "so", "fr", "en", False),
            ("halo", "fi", "ar", "en", True),
            ("hola", "fr", "en", "es", False),
            ("ہیلو", "fr", "ar", "en", True),
            ("هلو", "so", "fr", "en", True),
            ("هيلو", "it", "es", "en", True),
        )
        for transcript, detector_language, previous, expected, expected_uncertain in cases:
            with self.subTest(transcript=transcript):
                with _detected(detector_language):
                    actual, uncertain = choose_reply_language(
                        transcript, detector_language, previous, default_language="en"
                    )
                details = (
                    f"transcript={transcript!r}, detector={detector_language!r}, "
                    f"previous={previous!r}, expected={expected!r}, actual={actual[0]!r}, "
                    f"uncertain={uncertain}"
                )
                self.assertEqual(actual[0], expected, details)
                self.assertEqual(uncertain, expected_uncertain, details)

    def test_session_transitions_preserve_confirmed_language(self):
        saved_state = dict(SESSION_STATE)
        fake_llm = Mock(return_value="A short reply.")
        fake_modules = {
            "live_info": SimpleNamespace(
                EVENT_CITY="Dubai",
                extract_explicit_location=lambda _text: None,
                get_live_context=lambda *_args: "",
                has_location_reference=lambda _text: False,
                is_ambiguous_time_location=lambda _location: False,
                is_location_clarification=lambda _text: False,
                live_info_kind=lambda _text: None,
                weather_followup_location=lambda *_args: None,
            ),
            "stt": SimpleNamespace(is_transcript_unclear=lambda _text: False),
            "safety": SimpleNamespace(
                check_transcript=lambda _text: True,
                check_reply=lambda reply, _language: reply,
                fallback_message=lambda *_args: "Please try again.",
            ),
            "rag": SimpleNamespace(get_context=lambda _text: ""),
            "logging_utils": SimpleNamespace(log_turn=Mock()),
            "llm": SimpleNamespace(get_llm_reply=fake_llm),
        }
        try:
            _reset_session()
            with (
                patch.dict(sys.modules, fake_modules),
                patch("main.RAG_ENABLED", False),
                redirect_stdout(io.StringIO()),
            ):
                with _detected("af"):
                    _handle_transcript("Where does Drake live?", "af", speak=False)
                self.assertEqual(SESSION_STATE["last_language_code"], "en")

                for transcript, label in (("Yes.", "fr"), ("Okay.", "so")):
                    with self.subTest(transcript=transcript), _detected(label):
                        _handle_transcript(transcript, label, speak=False)
                        self.assertEqual(SESSION_STATE["last_language_code"], "en")

                for transcript, label, expected in (
                    ("halo", "fr", "en"),
                    ("ہیلو", "so", "en"),
                ):
                    with self.subTest(transcript=transcript), _detected(label):
                        _handle_transcript(transcript, label, speak=False)
                        self.assertEqual(SESSION_STATE["last_language_code"], "en")

                for transcript, label, expected in (
                    ("Muchas gracias por tu ayuda.", "es", "es"),
                    ("Bonjour, comment ça va ?", "fr", "fr"),
                    ("السلام عليكم كيف حالك", "ar", "ar"),
                ):
                    with self.subTest(transcript=transcript), _detected(label):
                        _handle_transcript(transcript, "en", speak=False)
                        self.assertEqual(SESSION_STATE["last_language_code"], expected)

                with _detected("fr"):
                    _handle_transcript("oui", "fr", speak=False)
                    self.assertEqual(SESSION_STATE["last_language_code"], "ar")
        finally:
            SESSION_STATE.clear()
            SESSION_STATE.update(saved_state)


if __name__ == "__main__":
    unittest.main()
