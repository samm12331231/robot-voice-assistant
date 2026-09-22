"""Coordinate file or microphone input, safety checks, AI replies, and speech output."""

import os
from pathlib import Path
import sys

import suppress_warnings  # Must run before pygame is imported by tts.py.
from language_utils import detect_language, normalize_language, should_use_previous_language
from llm import get_llm_reply, warm_up_llm
from logging_utils import log_turn
from rag import get_context
from safety import NETWORK_FALLBACK, SAFE_FALLBACK, check_reply, check_transcript, warm_up_moderation
from stt import is_transcript_unclear, transcribe_audio, warm_up_stt
from tts import speak_text


WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE") or None
RAG_ENABLED = os.getenv("RAG_ENABLED", "false").lower() == "true"
UNCLEAR_FALLBACK = "I didn’t quite understand that. Could you repeat it again?"
SESSION_STATE = {"last_language_code": None, "turn_count": 0}


def _speak(text: str, language: str = "en") -> None:
    """Speak a reply without exposing a traceback if the audio service fails."""
    try:
        output_path = speak_text(text, language=language)
        print(f"Saved TTS audio: {output_path}")
    except RuntimeError as error:
        print(f"TTS unavailable: {error}")


def _current_language(transcript: str, whisper_language: str | None) -> tuple[str, str]:
    if should_use_previous_language(transcript) and SESSION_STATE["last_language_code"]:
        return normalize_language(SESSION_STATE["last_language_code"]) or ("en", "English")
    return normalize_language(whisper_language) or detect_language(transcript)


def _handle_unclear(transcript: str = "") -> None:
    print("Transcript unclear.")
    _speak(UNCLEAR_FALLBACK)
    log_turn(
        turn=SESSION_STATE["turn_count"], transcript=transcript, language="en",
        transcript_flagged=False, reply=UNCLEAR_FALLBACK, reply_replaced=False, stt_unclear=True,
    )


def _handle_transcript(user_message: str, whisper_language: str | None) -> None:
    """Run quality, safety, RAG, LLM, reply safety, and TTS for one transcript."""
    SESSION_STATE["turn_count"] += 1
    turn = SESSION_STATE["turn_count"]
    if is_transcript_unclear(user_message):
        _handle_unclear(user_message)
        return

    language_code, language_name = _current_language(user_message, whisper_language)
    print(f"You said: {user_message}")
    print(f"Detected language: {language_name} ({language_code})")

    if not check_transcript(user_message):
        print("Transcript blocked by safety check.")
        _speak(SAFE_FALLBACK, language_code)
        log_turn(
            turn=turn, transcript=user_message, language=language_code, transcript_flagged=True,
            reply=SAFE_FALLBACK, reply_replaced=True, stt_unclear=False,
        )
        return

    context = ""
    if RAG_ENABLED:
        context = get_context(user_message)
        print("RAG context: found" if context else "RAG context: not found")
    else:
        print("RAG context: disabled")

    try:
        reply = get_llm_reply(user_message, context=context, language=language_name)
    except RuntimeError as error:
        print(f"LLM unavailable: {error}")
        reply = NETWORK_FALLBACK

    safe_reply = check_reply(reply)
    reply_replaced = safe_reply != reply
    print(f"Assistant: {safe_reply}")
    _speak(safe_reply, language_code)
    SESSION_STATE["last_language_code"] = language_code
    log_turn(
        turn=turn, transcript=user_message, language=language_code, transcript_flagged=False,
        reply=safe_reply, reply_replaced=reply_replaced, stt_unclear=False,
    )


def _transcribe(audio_path: str) -> tuple[str, str | None] | None:
    try:
        return transcribe_audio(
            audio_path, model_name=WHISPER_MODEL, language=WHISPER_LANGUAGE,
            return_language=True,
        )
    except FileNotFoundError as error:
        print(f"File error: {error}")
    except RuntimeError as error:
        print(f"Transcription error: {error}")
    return None


def run_file_mode(audio_path: str) -> None:
    """Run the existing one-file sample workflow."""
    result = _transcribe(audio_path)
    if result:
        _handle_transcript(*result)


def run_mic_mode() -> None:
    """Run the press-to-record public-demo microphone loop."""
    try:
        from mic import audio_device_summary, record_from_mic, validate_configured_devices

        print("Detected audio devices:")
        print("\n".join(audio_device_summary()) or "  No audio devices found.")
        validate_configured_devices()
    except RuntimeError as error:
        print(f"Microphone setup error: {error}")
        return

    print("Mic mode ready. Press Enter to record, Q then Enter to reset, Ctrl+C to quit.")
    try:
        while True:
            command = input("\nPress Enter to record... ").strip().lower()
            if command == "q":
                SESSION_STATE.update(last_language_code=None, turn_count=0)
                print("Session reset.")
                continue
            try:
                audio_path = record_from_mic()
            except RuntimeError as error:
                print(f"Microphone error: {error}")
                continue

            if audio_path is None:
                SESSION_STATE["turn_count"] += 1
                _handle_unclear()
                continue

            try:
                result = _transcribe(audio_path)
            finally:
                try:
                    Path(audio_path).unlink(missing_ok=True)
                except OSError:
                    pass
            if result:
                _handle_transcript(*result)
    except KeyboardInterrupt:
        print("\nStopping mic mode. Goodbye.")


def _warm_up() -> None:
    print("Warming up...")
    for label, action in (
        ("Whisper", lambda: warm_up_stt(WHISPER_MODEL)),
        ("moderation", warm_up_moderation),
        ("LLM", warm_up_llm),
    ):
        try:
            action()
        except RuntimeError as error:
            print(f"{label} warmup skipped: {error}")
    print("System ready.")


def main() -> None:
    _warm_up()
    if len(sys.argv) == 1:
        run_mic_mode()
    elif len(sys.argv) == 2:
        run_file_mode(sys.argv[1])
    else:
        print("Usage: python3 main.py [audio-or-video-file]")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
