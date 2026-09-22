"""Run the file-to-text-to-LLM-to-speech robot assistant prototype."""

import os
import sys

from language_utils import detect_language, normalize_language
from llm import get_llm_reply
from rag import get_context
from stt import transcribe_audio
from tts import speak_text


WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE") or None
RAG_ENABLED = os.getenv("RAG_ENABLED", "false").lower() == "true"


def run_file_mode(audio_path: str) -> None:
    """Transcribe one local media file, then ask the LLM about its text."""
    try:
        user_message, whisper_language = transcribe_audio(
            audio_path,
            model_name=WHISPER_MODEL,
            language=WHISPER_LANGUAGE,
            return_language=True,
        )
    except FileNotFoundError as error:
        print(f"File error: {error}")
        return
    except RuntimeError as error:
        print(f"Transcription error: {error}")
        return

    detected_language = normalize_language(whisper_language)
    language_code, language_name = detected_language or detect_language(user_message)
    print(f"You said: {user_message}")
    print(f"Detected language: {language_name} ({language_code})")

    context = ""
    if RAG_ENABLED:
        context = get_context(user_message)
        print("RAG context: found" if context else "RAG context: not found")
    else:
        print("RAG context: disabled")

    try:
        reply = get_llm_reply(user_message, context=context, language=language_name)
    except RuntimeError as error:
        print(f"Configuration or LLM error: {error}")
        return
    except Exception as error:
        print(f"OpenRouter request failed: {error}")
        return

    print(f"Assistant: {reply}")

    try:
        output_path = speak_text(reply, language=language_code)
    except RuntimeError as error:
        print(f"TTS error: {error}")
        return

    print(f"Saved TTS audio: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 main.py <audio-or-video-file>")
        sys.exit(1)

    run_file_mode(sys.argv[1])
