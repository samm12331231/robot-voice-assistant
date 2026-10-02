"""Mocked tests for cache and recent-history handling of creative replies."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

# Import the module without loading local .env settings or making a provider call.
with patch("dotenv.load_dotenv"):
    import llm
from runtime_cache import TTLCache


class CreativeReplyTests(unittest.TestCase):
    def setUp(self):
        self.cache_patch = patch.object(llm, "_web_reply_cache", TTLCache(900))
        self.cache = self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

    def _configure_web_path(self, client):
        patches = [
            patch.object(llm, "_get_client", return_value=client),
            patch.object(llm, "_web_search_enabled", return_value=True),
            patch.object(llm, "_web_search_provider", return_value="openai"),
        ]
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def test_identical_factual_request_uses_existing_cache(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text="Paris is the capital of France.",
            output=[SimpleNamespace(type="web_search_call")],
        )
        self._configure_web_path(client)

        first = llm.get_llm_reply("What is the capital of France?")
        second = llm.get_llm_reply("What is the capital of France?")

        self.assertEqual(first, second)
        self.assertEqual(client.responses.create.call_count, 1)

    def test_identical_joke_request_bypasses_stale_cached_reply(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text="A fresh joke for this turn.", output=[]
        )
        self._configure_web_path(client)
        message = "Can you tell me a joke?"
        cache_key = f"english::{message.casefold().strip()}"
        self.cache.set(cache_key, "The stale robot-bytes joke.")

        reply = llm.get_llm_reply(message)

        self.assertEqual(reply, "A fresh joke for this turn.")
        self.assertEqual(client.responses.create.call_count, 1)

    def test_recent_joke_history_reaches_creative_reply_prompt(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="A different joke."))]
        )
        history = [
            {"role": "user", "content": "Tell me a joke."},
            {"role": "assistant", "content": "Why did the robot byte? It needed more bits."},
        ]

        with patch.object(llm, "_get_client", return_value=client):
            llm.get_llm_reply("Tell me another joke.", history=history, use_web=False)

        messages = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(messages[1:3], history)
        self.assertIn("Do not repeat a recent joke", messages[0]["content"])

    def test_event_mode_prompt_never_claims_english_only(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="I use Modern Standard Arabic."))]
        )
        with (
            patch.object(llm, "_get_client", return_value=client),
            patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
        ):
            llm.get_llm_reply("What dialect is this?", use_web=False)
        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("English, Arabic, Hindi, and Mandarin Chinese", prompt)
        self.assertIn("Never say that you support English only", prompt)

    def test_general_prompt_requires_direct_grounded_answers(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="A direct answer."))]
        )
        with patch.object(llm, "_get_client", return_value=client):
            llm.get_llm_reply(
                "What are you?",
                history=[{"role": "user", "content": "We are in Dubai."}],
                use_web=False,
            )

        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Answer the visitor's actual question first", prompt)
        self.assertIn("Do not use generic greetings", prompt)
        self.assertIn("Do not begin a useful answer", prompt)
        self.assertIn("answer each clear part in the order asked", prompt)
        self.assertIn("never proof of a factual claim", prompt)
        self.assertIn("Never claim to have performed a physical action", prompt)
        self.assertIn("keep named technical terms", prompt)
        self.assertIn("clearly fictional request", prompt)

    def test_wrong_script_is_retried_once_for_the_requested_language(self):
        client = Mock()
        client.chat.completions.create.side_effect = (
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="هذا رد عربي."))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="这是中文回答。"))]),
        )
        with patch.object(llm, "_get_client", return_value=client):
            reply = llm.get_llm_reply("Explain this in Chinese.", language="Chinese", use_web=False)

        self.assertEqual(reply, "这是中文回答。")
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_prompt_allows_neutral_offensive_word_definitions(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="A neutral definition."))]
        )
        with patch.object(llm, "_get_client", return_value=client):
            llm.get_llm_reply("What does fuck mean in Arabic?", use_web=False)

        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("define or translate an offensive word is educational", prompt)

    def test_gpt5_uses_completion_token_parameter(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="A GPT-5 answer."))]
        )
        with (
            patch.object(llm, "_get_client", return_value=client),
            patch.dict("os.environ", {"OPENAI_MODEL": "gpt-5.4"}),
        ):
            llm.get_llm_reply("What are you?", use_web=False)

        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["max_completion_tokens"], 80)
        self.assertNotIn("max_tokens", request)

    def test_non_gpt5_keeps_legacy_token_parameter(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="A standard answer."))]
        )
        with (
            patch.object(llm, "_get_client", return_value=client),
            patch.dict("os.environ", {"OPENAI_MODEL": "gpt-4o"}),
        ):
            llm.get_llm_reply("What are you?", use_web=False)

        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["max_tokens"], 80)
        self.assertNotIn("max_completion_tokens", request)

    def test_event_mode_rejects_english_only_claims(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="I can only speak English."))]
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="I can help in English, Arabic, Hindi, and Mandarin Chinese."))]
            ),
        ]
        with (
            patch.object(llm, "_get_client", return_value=client),
            patch.dict(
                "os.environ",
                {"OPENAI_MODEL": "gpt-5.4", "LANGUAGE_MODE": "event_en_ar_hi_zh"},
            ),
        ):
            reply = llm.get_llm_reply("What can you do?", language="Arabic", use_web=False)

        self.assertNotIn("only speak English", reply.casefold())
        self.assertEqual(client.chat.completions.create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
