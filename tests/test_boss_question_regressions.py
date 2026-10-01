"""Offline regressions for representative public-event visitor questions."""

import unittest
from unittest.mock import patch

import language_utils
from fallback_messages import fallback_message, specific_safety_refusal
from language_utils import (
    arabic_hindi_then_arabic_time_request,
    arabic_hindi_time_arabic_weather_request,
    choose_reply_language,
    event_language_capability_reply,
    event_language_policy_reply,
    event_unsafe_language_request_reply,
    event_generic_language_reply,
    event_mixed_live_request,
    event_requested_reply_language,
    physical_action_unavailable_reply,
    public_event_joke_reply,
)


class BossQuestionRegressionTests(unittest.TestCase):
    def test_real_english_questions_ignore_wrong_detector_labels(self):
        prompts = (
            "One two three, hello, hello, one two three.",
            "Give me the name of the person standing beside me.",
            "Can you tell me what's the weather like in Dubai right now? And can I go swimming?",
            "Can you make the volume up?",
            "What are you? Are you a robot? Are you a human?",
            "Can you talk in Arabic please?",
            "Can you tell me what is the meaning of this word in English?",
        )
        for prompt in prompts:
            for incorrect_label in ("af", "fi", "fr", "so", "it"):
                with self.subTest(prompt=prompt, label=incorrect_label):
                    with patch.object(
                        language_utils,
                        "detect_language_confident",
                        return_value=(incorrect_label, incorrect_label.upper()),
                    ):
                        language, uncertain = choose_reply_language(
                            prompt, incorrect_label, None
                        )
                    self.assertEqual(language[0], "en")
                    self.assertFalse(uncertain)

    def test_supported_language_capability_and_joke_requests(self):
        cases = (
            ("Can you talk in Arabic?", ("ar", "نعم، أستطيع التحدث بالعربية. مرحبًا!")),
            ("Can you speak Hindi?", ("hi", "हाँ, मैं हिंदी बोल सकता हूँ। नमस्ते!")),
            ("Could you communicate in Mandarin Chinese?", ("zh", "是的，我会说普通话。你好！")),
            ("Can you tell me a joke in Arabic?", ("ar", "Arabic")),
            ("Tell me a joke in Hindi.", ("hi", "Hindi")),
            ("Please tell me a joke in Mandarin Chinese.", ("zh", "Chinese")),
        )
        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                actual = event_language_capability_reply(prompt) or event_requested_reply_language(prompt)
                self.assertEqual(actual, expected)

    def test_harmful_language_requests_do_not_take_the_capability_shortcut(self):
        prompt = "Can you talk in Arabic and curse my friend?"
        self.assertIsNone(event_language_capability_reply(prompt))
        self.assertIsNone(event_requested_reply_language(prompt))

    def test_harmful_language_requests_keep_the_explicit_reply_language(self):
        cases = (
            ("Talk in Arabic and can curse my friend in Arabic.", "ar"),
            ("Can you speak Hindi and swear at my friend in Hindi?", "hi"),
            ("Tell me an offensive phrase in Chinese.", "zh"),
            ("Speak Arabic and insult my friend, but make it sound polite.", "ar"),
            ("Can you make fun of my friend in Arabic, but say it in a nice way?", "ar"),
        )
        for prompt, language in cases:
            with self.subTest(prompt=prompt):
                actual = event_unsafe_language_request_reply(prompt)
                self.assertIsNotNone(actual)
                self.assertEqual(actual[0], language)
                self.assertNotIn("English only", actual[1])

    def test_combined_language_requests_reach_the_requested_language_path(self):
        cases = (
            ("Can you talk in Arabic and tell me a joke in Arabic?", "Arabic"),
            ("Can you speak Hindi and explain what this robot does in Hindi?", "Hindi"),
            ("Could you say hello in Arabic, then tell me the time in Dubai in Arabic?", "Arabic"),
        )
        for prompt, language in cases:
            with self.subTest(prompt=prompt):
                self.assertIsNone(event_language_capability_reply(prompt))
                self.assertEqual(event_requested_reply_language(prompt)[1], language)

    def test_word_meaning_is_not_intercepted_by_a_generic_language_confirmation(self):
        prompt = "What does shukran mean in English, and can you use it in a sentence?"
        self.assertIsNone(event_generic_language_reply(prompt))

    def test_word_meaning_can_request_an_english_reply_after_chinese_text(self):
        self.assertEqual(
            event_requested_reply_language("What does 你好 mean in English, not Chinese?"),
            ("en", "English"),
        )

    def test_live_questions_can_request_two_supported_reply_languages(self):
        # 1. Weather Dubai Arabic, then time Dubai Hindi
        self.assertEqual(
            event_mixed_live_request(
                "Tell me the weather in Dubai in Arabic, but tell me the time in Dubai in Hindi."
            ),
            ("dubai", ("weather", "ar"), "dubai", ("time", "hi")),
        )
        # 2. Time Dubai Hindi, then weather Dubai Arabic
        self.assertEqual(
            event_mixed_live_request(
                "Tell me the time in Dubai in Hindi, then the weather in Dubai in Arabic."
            ),
            ("dubai", ("time", "hi"), "dubai", ("weather", "ar")),
        )
        # 3. Time and weather Dubai, both Arabic
        self.assertEqual(
            event_mixed_live_request("Can you tell me the time and the weather in Dubai in Arabic?"),
            ("dubai", ("time", "ar"), "dubai", ("weather", "ar")),
        )
        # 4. Weather Abu Dhabi Chinese, then time Tokyo Hindi
        self.assertEqual(
            event_mixed_live_request(
                "Give me the weather in Abu Dhabi in Chinese, then the time in Tokyo in Hindi."
            ),
            ("abu dhabi", ("weather", "zh"), "tokyo", ("time", "hi")),
        )
        # 5. Time Tokyo Hindi, then weather Abu Dhabi Chinese
        self.assertEqual(
            event_mixed_live_request(
                "Tell me the time in Tokyo in Hindi, then the weather in Abu Dhabi in Chinese."
            ),
            ("tokyo", ("time", "hi"), "abu dhabi", ("weather", "zh")),
        )
        # 6. Time Abu Dhabi and weather Dubai, both Arabic
        self.assertEqual(
            event_mixed_live_request(
                "Tell me the time in Abu Dhabi and the weather in Dubai in Arabic."
            ),
            ("abu dhabi", ("time", "ar"), "dubai", ("weather", "ar")),
        )
        self.assertEqual(
            event_mixed_live_request(
                "Tell me the time in Abu Dhabi and the weather in Dubai, both in Arabic."
            ),
            ("abu dhabi", ("time", "ar"), "dubai", ("weather", "ar")),
        )
        # 7. Dubai weather Hindi and Dubai time Arabic using 'there'
        self.assertEqual(
            event_mixed_live_request(
                "What is the weather in Dubai in Hindi, and what time is it there in Arabic?"
            ),
            ("dubai", ("weather", "hi"), "dubai", ("time", "ar")),
        )
        # 8. Time Dubai Arabic and weather Hindi
        self.assertEqual(
            event_mixed_live_request(
                "Can you tell me the time in Dubai in Arabic and the weather in Hindi?"
            ),
            ("dubai", ("time", "ar"), "dubai", ("weather", "hi")),
        )
        # 9. Arabic requests
        self.assertTrue(arabic_hindi_then_arabic_time_request(
            "سوي لي شي، كلم وياي في اللغة هندي وعربي، ورد علي في الهندي أول شي وبعدين عربي، شنو الوقت حالياً في دبي؟"
        ))
        self.assertTrue(arabic_hindi_time_arabic_weather_request(
            "أخبرني أولاً بالوقت في دبي باللغة الهندية ثم بالطقس في دبي باللغة العربية."
        ))

    def test_compliment_can_request_a_supported_reply_language(self):
        self.assertEqual(
            event_requested_reply_language("Can you compliment my friend in Arabic?"),
            ("ar", "Arabic"),
        )

    def test_arabic_dialect_question_lists_actual_event_languages(self):
        reply = event_language_policy_reply(
            "What dialect is this? It does not sound Emirati or Saudi Arabic."
        )
        self.assertEqual(reply[0], "en")
        self.assertIn("Modern Standard Arabic", reply[1])
        self.assertNotIn("English only", reply[1])
        self.assertEqual(
            event_requested_reply_language("What is the weather in Abu Dhabi in Chinese?"),
            ("zh", "Chinese"),
        )

    def test_physical_actions_are_not_promised(self):
        reply = physical_action_unavailable_reply(
            "Turn the volume up, move closer, and wave at my boss.", "en"
        )
        self.assertIn("can't", reply)
        self.assertIn("move closer", reply)
        self.assertIn("can't", physical_action_unavailable_reply("Can you wave?", "en"))

    def test_safe_local_joke_exists_when_a_benign_model_joke_is_rejected(self):
        reply = public_event_joke_reply("Can you tell me a joke in Arabic?", "ar")
        self.assertIsNotNone(reply)
        self.assertNotIn("أنا هنا للمساعدة", reply)

    def test_fight_question_has_a_direct_deescalation_reply(self):
        reply = specific_safety_refusal(
            "My friend just made fun of my haircut. Should I beat him up?"
        )
        self.assertIn("can't help hurt", reply)

    def test_generic_blocked_reply_is_a_clear_redirect(self):
        self.assertEqual(
            fallback_message("blocked", "en"),
            "I can't help you with that. Ask me anything else.",
        )

    def test_long_prompt_containing_english_and_arabic_extracts_dubai(self):
        from live_info import extract_explicit_location
        prompts = (
            "I don't speak Arabic. English. What's the weather in Dubai in Arabic?",
            "What the fuck? I don't speak Arabic. English. What's the weather in Dubai in Arabic? Reply in Arabic.",
            "I don't speak in Arabic. English. What's the weather in Dubai?",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(extract_explicit_location(prompt), "Dubai")

    def test_arabic_hindi_first_request_in_session(self):
        import io
        from contextlib import redirect_stdout
        import main

        saved_state = dict(main.SESSION_STATE)
        try:
            main._reset_session()
            prompt = "أخبرني أولاً بالوقت في دبي باللغة الهندية ثم بالطقس في دبي باللغة العربية."
            with (
                patch.object(main, "_speak") as mock_speak,
                patch(
                    "live_info.get_live_context",
                    side_effect=lambda req: "Live time for Dubai: 12:30 PM." if "time" in req else "Live weather for Dubai: 35°C, clear sky."
                ),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
            ):
                out = io.StringIO()
                with redirect_stdout(out):
                    main.run_text_mode(prompt)
                reply_line = [l for l in out.getvalue().splitlines() if l.startswith("Assistant:")][0]
                # Hindi time first, Arabic weather second
                self.assertIn("दुबई में वर्तमान समय", reply_line)
                self.assertIn("الطقس في دبي", reply_line)
                hindi_pos = reply_line.find("दुबई")
                arabic_pos = reply_line.find("الطقس")
                self.assertLess(hindi_pos, arabic_pos)
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_mixed_live_request_with_pronoun_there_end_to_end(self):
        import io
        from contextlib import redirect_stdout
        import main

        saved_state = dict(main.SESSION_STATE)
        try:
            main._reset_session()
            prompt = "What is the weather in Dubai in Hindi, and what time is it there in Arabic?"
            with (
                patch.object(main, "_speak") as mock_speak,
                patch(
                    "live_info.get_live_context",
                    side_effect=lambda req: "Live weather for Dubai: 32°C, clear sky." if "weather" in req else "Live time for Dubai: 02:00 PM."
                ),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
            ):
                out = io.StringIO()
                with redirect_stdout(out):
                    main.run_text_mode(prompt)
                reply_line = [l for l in out.getvalue().splitlines() if l.startswith("Assistant:")][0]
                self.assertIn("दुबई में मौसम", reply_line)
                self.assertIn("الوقت الحالي في دبي", reply_line)
                # Weather (Hindi) first, Time (Arabic) second
                hindi_weather_pos = reply_line.find("दुबई में मौसम")
                arabic_time_pos = reply_line.find("الوقت الحالي")
                self.assertLess(hindi_weather_pos, arabic_time_pos)
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_mixed_live_lookup_one_fails_preserves_both_clauses(self):
        import io
        from contextlib import redirect_stdout
        import main

        saved_state = dict(main.SESSION_STATE)
        try:
            main._reset_session()
            prompt = "Tell me the weather in Dubai in Arabic, but tell me the time in Dubai in Hindi."
            # Weather succeeds, time fails
            with (
                patch.object(main, "_speak"),
                patch(
                    "live_info.get_live_context",
                    side_effect=lambda req: "Live weather for Dubai: 35°C, clear sky." if "weather" in req else "Live time for Dubai could not be resolved. Do not guess a timezone."
                ),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
            ):
                out = io.StringIO()
                with redirect_stdout(out):
                    main.run_text_mode(prompt)
                reply_line = [l for l in out.getvalue().splitlines() if l.startswith("Assistant:")][0]
                # Preserves successful Arabic weather
                self.assertIn("الطقس في دبي", reply_line)
                # Localized failure reply for Hindi time
                self.assertIn("माफ़ कीजिए, मैं अभी वर्तमान समय प्राप्त नहीं कर सकता।", reply_line)
                # Weather first, then time
                arabic_pos = reply_line.find("الطقس في دبي")
                hindi_pos = reply_line.find("माफ़ कीजिए")
                self.assertLess(arabic_pos, hindi_pos)
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)

    def test_mixed_live_lookup_weather_fails_time_succeeds_preserves_both(self):
        import io
        from contextlib import redirect_stdout
        import main

        saved_state = dict(main.SESSION_STATE)
        try:
            main._reset_session()
            prompt = "Tell me the time in Dubai in Hindi, then the weather in Dubai in Arabic."
            # Time succeeds, weather fails
            with (
                patch.object(main, "_speak"),
                patch(
                    "live_info.get_live_context",
                    side_effect=lambda req: "Live time for Dubai: 04:30 PM." if "time" in req else "Live weather for Dubai is unavailable. Do not guess."
                ),
                patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
            ):
                out = io.StringIO()
                with redirect_stdout(out):
                    main.run_text_mode(prompt)
                reply_line = [l for l in out.getvalue().splitlines() if l.startswith("Assistant:")][0]
                # Preserves successful Hindi time first
                self.assertIn("दुबई में वर्तमान समय", reply_line)
                # Localized failure reply for Arabic weather second
                self.assertIn("عذرًا، لا أستطيع الحصول على معلومات الطقس الآن", reply_line)
                time_pos = reply_line.find("दुबई में वर्तमान समय")
                weather_pos = reply_line.find("عذرًا")
                self.assertLess(time_pos, weather_pos)
        finally:
            main.SESSION_STATE.clear()
            main.SESSION_STATE.update(saved_state)


if __name__ == "__main__":
    unittest.main()
