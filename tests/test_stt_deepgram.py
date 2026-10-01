"""Mocked Deepgram Nova-3 provider checks with no network calls."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import stt


class DeepgramSttTests(unittest.TestCase):
    def _audio_file(self) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        handle.write(b"RIFFmock-wav")
        handle.close()
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        return Path(handle.name)

    def test_deepgram_response_parsing_uses_requested_language_when_no_hint_is_returned(self):
        payload = {"results": {"channels": [{"alternatives": [{"transcript": " hello there "}]}]}}
        self.assertEqual(stt._parse_deepgram_response(payload, "ur"), ("hello there", "ur"))

    def test_deepgram_rest_request_uses_timeout_explicit_language_and_keyterms(self):
        response = MagicMock()
        response.read.return_value = json.dumps({
            "results": {"channels": [{
                "detected_language": "ar",
                "alternatives": [{"transcript": "مرحبا"}],
            }]}
        }).encode("utf-8")
        urlopen = MagicMock()
        urlopen.return_value.__enter__.return_value = response
        with (
            patch.dict("os.environ", {
                "DEEPGRAM_API_KEY": "test-key",
                "DEEPGRAM_MODEL": "nova-3",
                "DEEPGRAM_LANGUAGE": "ar",
                "DEEPGRAM_TIMEOUT_SECONDS": "7.5",
                "DEEPGRAM_KEYTERMS": "Ibtikar Robotics, AIRHUG",
            }, clear=False),
            patch.object(stt, "urlopen", urlopen),
        ):
            transcript, language = stt._transcribe_deepgram(self._audio_file(), None)

        request = urlopen.call_args.args[0]
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 7.5)
        self.assertIn("model=nova-3", request.full_url)
        self.assertIn("language=ar", request.full_url)
        self.assertIn("keyterm=Ibtikar+Robotics", request.full_url)
        self.assertEqual((transcript, language), ("مرحبا", "ar"))

    def test_deepgram_provider_is_selected(self):
        audio_path = self._audio_file()
        with (
            patch.dict("os.environ", {"STT_PROVIDER": "deepgram"}, clear=False),
            patch.object(stt, "_transcribe_deepgram", return_value=("hello", "en")) as deepgram,
        ):
            self.assertEqual(stt.transcribe_audio(str(audio_path), return_language=True), ("hello", "en"))
        deepgram.assert_called_once_with(audio_path, None)

    def test_deepgram_timeout_uses_existing_openai_fallback(self):
        audio_path = self._audio_file()
        with (
            patch.dict("os.environ", {"STT_PROVIDER": "deepgram"}, clear=False),
            patch.object(stt, "_transcribe_deepgram", side_effect=RuntimeError("timed out")),
            patch.object(stt, "_transcribe_openai_with_local_fallback", return_value=("fallback", "en")) as fallback,
        ):
            self.assertEqual(stt.transcribe_audio(str(audio_path), return_language=True), ("fallback", "en"))
        fallback.assert_called_once_with(audio_path, "small", None)


if __name__ == "__main__":
    unittest.main()
