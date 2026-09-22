"""Coordinate file or microphone input, safety checks, AI replies, and speech output."""

import os
from pathlib import Path
import sys

import suppress_warnings  # Must run before pygame is imported by tts.py.
from language_utils import (
    detect_language_confident,
    detect_script_language,
    has_non_latin_script,
    normalize_language,
)
from llm import get_llm_reply, warm_up_llm
from live_info import get_live_context
from logging_utils import log_turn
from rag import get_context
from safety import check_reply, check_transcript, fallback_message, warm_up_moderation
from stt import is_transcript_unclear, transcribe_audio, warm_up_stt
from tts import speak_text


WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE") or None
RAG_ENABLED = os.getenv("RAG_ENABLED", "false").lower() == "true"
SESSION_STATE = {"last_language_code": None, "turn_count": 0, "history": []}


def _speak(text: str, language: str = "en") -> None:
    """Speak a reply without exposing a traceback if the audio service fails."""
    try:
        output_path = speak_text(text, language=language)
        print(f"Saved TTS audio: {output_path}")
    except RuntimeError as error:
        print(f"TTS unavailable: {error}")


def _current_language(transcript: str, whisper_language: str | None) -> tuple[str, str]:
    """Choose the best fresh language signal, using session memory only as a fallback."""
    whisper_result = normalize_language(whisper_language)
    text_result = detect_language_confident(transcript)
    script_result = detect_script_language(transcript)

    if whisper_result:
        if text_result and text_result[0] != whisper_result[0]:
            if whisper_result[0] == "en" and has_non_latin_script(transcript):
                return text_result
            if text_result[0] == "en" and not has_non_latin_script(transcript):
                return text_result
        return whisper_result
    if text_result:
        return text_result
    if script_result:
        return script_result
    previous_code = SESSION_STATE["last_language_code"]
    return normalize_language(previous_code) or ("en", "English")


def _handle_unclear(transcript: str = "", language: str | None = None, speak: bool = True) -> None:
    print("Transcript unclear.")
    language_code = language or SESSION_STATE["last_language_code"] or "en"
    reply = fallback_message("unclear", language_code)
    if speak:
        _speak(reply, language_code)
    log_turn(
        turn=SESSION_STATE["turn_count"], transcript=transcript, language=language_code,
        transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=True,
    )


def _handle_transcript(user_message: str, whisper_language: str | None, speak: bool = True) -> None:
    """Run quality, safety, RAG, LLM, reply safety, and TTS for one transcript."""
    SESSION_STATE["turn_count"] += 1
    turn = SESSION_STATE["turn_count"]
    language_code, language_name = _current_language(user_message, whisper_language)
    if is_transcript_unclear(user_message):
        _handle_unclear(user_message, language_code, speak)
        return

    print(f"You said: {user_message}")
    print(f"Detected language: {language_name} ({language_code})")

    if not check_transcript(user_message):
        print("Transcript blocked by safety check.")
        reply = fallback_message("safe", language_code)
        if speak:
            _speak(reply, language_code)
        log_turn(
            turn=turn, transcript=user_message, language=language_code, transcript_flagged=True,
            reply=reply, reply_replaced=True, stt_unclear=False,
        )
        return

    context_parts = []
    live_context = get_live_context(user_message)
    if live_context:
        context_parts.append(live_context)
        print("Live information: unavailable" if "lookup failed" in live_context else "Live information: found")
    if RAG_ENABLED:
        rag_context = get_context(user_message)
        if rag_context:
            context_parts.append(rag_context)
        print("RAG context: found" if rag_context else "RAG context: not found")
    else:
        print("RAG context: disabled")
    context = "\n\n".join(context_parts)

    try:
        reply = get_llm_reply(
            user_message,
            context=context,
            language=language_name,
            history=SESSION_STATE["history"],
        )
    except RuntimeError as error:
        print(f"LLM unavailable: {error}")
        reply = fallback_message("network", language_code)

    safe_reply = check_reply(reply, language_code)
    reply_replaced = safe_reply != reply
    print(f"Assistant: {safe_reply}")
    if speak:
        _speak(safe_reply, language_code)
    SESSION_STATE["last_language_code"] = language_code
    SESSION_STATE["history"] = [
        *SESSION_STATE["history"],
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": safe_reply},
    ][-4:]
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


def run_text_mode(user_message: str) -> None:
    """Run the normal reply flow without recording or playing audio."""
    _handle_transcript(user_message, whisper_language=None, speak=False)


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
                SESSION_STATE.update(last_language_code=None, turn_count=0, history=[])
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
    arguments = sys.argv[1:]
    if not arguments:
        _warm_up()
        run_mic_mode()
    elif arguments[0] == "--text":
        if len(arguments) != 2:
            print("Usage: python3 main.py --text \"your question\"")
            raise SystemExit(1)
        _warm_up()
        run_text_mode(arguments[1])
    elif len(arguments) == 1 and not arguments[0].startswith("-"):
        _warm_up()
        run_file_mode(arguments[0])
    else:
        print("Usage: python3 main.py [audio-or-video-file] | --text \"your question\"")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
