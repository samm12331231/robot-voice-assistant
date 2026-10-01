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


if __name__ == "__main__":
    unittest.main()
