"""Coordinate file or microphone input, safety checks, AI replies, and speech output."""

import os
from pathlib import Path
import sys
import time

import suppress_warnings  # Must run before pygame is imported by tts.py.
from fallback_messages import specific_safety_refusal
from live_info import live_info_direct_reply, live_info_failure_reply
from language_utils import (
    arabic_hindi_then_arabic_time_request,
    arabic_hindi_time_arabic_weather_request,
    arabic_request_time_first,
    choose_reply_language,
    company_facts_unavailable,
    event_language_capability_reply,
    event_language_policy_reply,
    event_unsafe_language_request_reply,
    event_generic_language_reply,
    event_mixed_live_request,
    event_requested_language_code,
    event_requested_reply_language,
    event_supported_language_message,
    physical_action_unavailable_reply,
    public_event_joke_reply,
    strip_event_reply_language_suffix,
    is_event_language_mode,
    is_company_fact_request,
)


WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE") or None
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "en")
LANGUAGE_MODE = os.getenv("LANGUAGE_MODE", "")


def _event_language_mode_enabled() -> bool:
    """Read the current environment after CLI configuration has loaded."""
    return is_event_language_mode(os.getenv("LANGUAGE_MODE", "").strip().lower())
RAG_ENABLED = os.getenv("RAG_ENABLED", "false").lower() == "true"
SESSION_STATE = {
    "last_language_code": None,
    "turn_count": 0,
    "history": [],
    "last_live_info": None,
}


def _reset_session() -> None:
    """Clear in-memory visitor context when the session is reset."""
    SESSION_STATE.update(
        last_language_code=None, turn_count=0, history=[], last_live_info=None
    )


def _debug_timing(stage: str, started_at: float) -> None:
    """Emit opt-in stage timing without changing the normal console output."""
    if os.getenv("MIC_DEBUG") == "1":
        print(f"MIC_DEBUG: {stage}_duration={time.perf_counter() - started_at:.3f}s")


def _speak(text: str, language: str = "en") -> None:
    """Speak a reply without exposing a traceback if the audio service fails."""
    from tts import speak_text

    try:
        started_at = time.perf_counter()
        output_path = speak_text(text, language=language)
        _debug_timing("tts_total", started_at)
        print(f"Saved TTS audio: {output_path}")
    except RuntimeError as error:
        print(f"TTS unavailable: {error}")


def _current_language(transcript: str, whisper_language: str | None) -> tuple[str, str]:
    """Choose the best fresh language signal, using session memory only as a fallback."""
    language_choice, _ = choose_reply_language(
        transcript,
        whisper_language,
        SESSION_STATE["last_language_code"],
        default_language=WHISPER_LANGUAGE or DEFAULT_LANGUAGE,
    )
    return language_choice


def _handle_unclear(transcript: str = "", language: str | None = None, speak: bool = True) -> None:
    from logging_utils import log_turn
    from safety import fallback_message

    SESSION_STATE["last_live_info"] = None
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
    from live_info import (
        EVENT_CITY,
        extract_explicit_location,
        get_live_context,
        has_location_reference,
        is_ambiguous_time_location,
        is_location_clarification,
        live_info_kind,
        weather_followup_location,
    )
    from logging_utils import log_turn
    from residence import current_residence_refusal, is_current_residence_request
    from rag import get_context
    from safety import check_reply, check_transcript, fallback_message
    from stt import is_transcript_unclear
    from translation import (
        local_event_translation, parse_multi_translation_intents,
        parse_translation_intent, translation_only_reply,
    )

    SESSION_STATE["turn_count"] += 1
    turn = SESSION_STATE["turn_count"]
    language_choice, is_uncertain = choose_reply_language(
        user_message,
        whisper_language,
        SESSION_STATE["last_language_code"],
        default_language=WHISPER_LANGUAGE or DEFAULT_LANGUAGE,
    )
    language_code, language_name = language_choice
    event_mode = _event_language_mode_enabled()
    unsafe_language_reply = (
        event_unsafe_language_request_reply(user_message) if event_mode else None
    )
    if is_transcript_unclear(user_message):
        if os.getenv("MIC_DEBUG") == "1":
            print("MIC_DEBUG: transcript was unclear; LLM was skipped.")
        _handle_unclear(user_message, language_code, speak)
        return

    translation = parse_translation_intent(user_message)
    multi_translations = parse_multi_translation_intents(user_message)
    lookup_message = (
        strip_event_reply_language_suffix(user_message) if event_mode else user_message
    )
    previous_live_info = SESSION_STATE.get("last_live_info")
    SESSION_STATE["last_live_info"] = None
    live_kind = live_info_kind(lookup_message)
    explicit_location = extract_explicit_location(lookup_message)
    followup_location = weather_followup_location(lookup_message, previous_live_info)
    if not live_kind and followup_location and is_location_clarification(lookup_message):
        live_kind = "weather"
    if live_kind and followup_location:
        explicit_location = followup_location
    if event_mode and (
        is_uncertain
        or language_code not in {"en", "ar", "hi", "zh"}
        or (translation and translation.language_code not in {"en", "ar", "hi", "zh"})
        or any(intent.language_code not in {"en", "ar", "hi", "zh"} for intent in multi_translations)
    ):
        reply = event_supported_language_message(language_code)
        print(f"Assistant: {reply}")
        if speak:
            _speak(reply, language_code if language_code in {"ar", "hi", "zh"} else "en")
        log_turn(
            turn=turn, transcript=user_message, language=language_code,
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return
    if is_uncertain:
        reply = "Hello! Please ask me a question in the language you prefer."
        if speak:
            _speak(reply, language_code)
        print(f"Detected language: uncertain ({language_code})")
        print(f"Assistant: {reply}")
        return

    print(f"You said: {user_message}")
    print(f"Detected language: {language_name} ({language_code})")

    if not check_transcript(user_message):
        print("Transcript blocked by safety check.")
        reply = (
            unsafe_language_reply[1]
            if unsafe_language_reply
            else specific_safety_refusal(user_message, language_code)
            or fallback_message("blocked", language_code)
        )
        reply_language_code = unsafe_language_reply[0] if unsafe_language_reply else language_code
        print(f"Assistant: {reply}")
        if speak:
            _speak(reply, reply_language_code)
        log_turn(
            turn=turn, transcript=user_message, language=reply_language_code, transcript_flagged=True,
            reply=reply, reply_replaced=True, stt_unclear=False,
        )
        return

    language_policy_reply = event_language_policy_reply(user_message) if event_mode else None
    if language_policy_reply:
        reply_language_code, reply = language_policy_reply
        print(f"Assistant: {reply}")
        if speak:
            _speak(reply, reply_language_code)
        log_turn(
            turn=turn, transcript=user_message, language=reply_language_code,
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    if event_mode and arabic_hindi_time_arabic_weather_request(user_message):
        location = extract_explicit_location(user_message) or EVENT_CITY
        time_context = get_live_context(f"What time is it in {location}?")
        weather_context = get_live_context(f"What's the weather in {location}?")
        time_reply = (
            live_info_failure_reply("time", "hi", time_context, user_message)
            or live_info_direct_reply("time", "hi", time_context, user_message)
            or fallback_message("network", "hi")
        )
        weather_reply = (
            live_info_failure_reply("weather", "ar", weather_context, user_message)
            or live_info_direct_reply("weather", "ar", weather_context, user_message)
            or fallback_message("network", "ar")
        )
        time_first = arabic_request_time_first(user_message)
        ordered_replies = [time_reply, weather_reply] if time_first else [weather_reply, time_reply]
        ordered_codes = ["hi", "ar"] if time_first else ["ar", "hi"]
        reply = " ".join(ordered_replies)
        print(f"Assistant: {reply}")
        if speak:
            _speak(ordered_replies[0], ordered_codes[0])
            _speak(ordered_replies[1], ordered_codes[1])
        SESSION_STATE["last_language_code"] = language_code
        SESSION_STATE["last_live_info"] = {
            "kind": "weather" if time_first else "time",
            "location": location,
        }
        SESSION_STATE["history"] = [
            *SESSION_STATE["history"],
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ][-4:]
        log_turn(
            turn=turn, transcript=user_message, language="ar",
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    if event_mode and arabic_hindi_then_arabic_time_request(user_message):
        location = extract_explicit_location(user_message) or EVENT_CITY
        live_context = get_live_context(f"What time is it in {location}?")
        replies = [
            live_info_failure_reply("time", code, live_context, user_message)
            or live_info_direct_reply("time", code, live_context, user_message)
            or fallback_message("network", code)
            for code in ("hi", "ar")
        ]
        reply = " ".join(replies)
        print(f"Assistant: {reply}")
        if speak:
            _speak(replies[0], "hi")
            _speak(replies[1], "ar")
        SESSION_STATE["last_language_code"] = language_code
        SESSION_STATE["last_live_info"] = {"kind": "time", "location": location}
        SESSION_STATE["history"] = [
            *SESSION_STATE["history"],
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ][-4:]
        log_turn(
            turn=turn, transcript=user_message, language="ar",
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    mixed_live_request = event_mixed_live_request(user_message) if event_mode else None
    if mixed_live_request:
        first_location, first_request, second_location, second_request = mixed_live_request
        replies = []
        for location, (kind, reply_code) in (
            (first_location, first_request), (second_location, second_request)
        ):
            live_request = (
                f"What time is it in {location}?"
                if kind == "time"
                else f"What's the weather in {location}?"
            )
            live_context = get_live_context(live_request)
            reply = (
                live_info_failure_reply(kind, reply_code, live_context, user_message)
                or live_info_direct_reply(kind, reply_code, live_context, user_message)
                or fallback_message("network", reply_code)
            )
            replies.append(reply)
        reply = " ".join(replies)
        print(f"Assistant: {reply}")
        if speak:
            _speak(replies[0], first_request[1])
            _speak(replies[1], second_request[1])
        SESSION_STATE["last_language_code"] = language_code
        SESSION_STATE["last_live_info"] = {"kind": second_request[0], "location": second_location}
        SESSION_STATE["history"] = [
            *SESSION_STATE["history"],
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ][-4:]
        log_turn(
            turn=turn, transcript=user_message, language=second_request[1],
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    requested_language_code = event_requested_language_code(user_message) if event_mode else None
    if requested_language_code and requested_language_code not in {"en", "ar", "hi", "zh"}:
        reply = event_supported_language_message("en")
        print(f"Assistant: {reply}")
        if speak:
            _speak(reply, "en")
        log_turn(
            turn=turn, transcript=user_message, language="en", transcript_flagged=False,
            reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    if multi_translations:
        replies = []
        for intent in multi_translations:
            reply = local_event_translation(intent.phrase, intent.language_code)
            if not reply:
                try:
                    from llm import get_llm_reply

                    reply = get_llm_reply(
                        intent.phrase, language=intent.language_name, history=[],
                        use_web=False, translation_only=True,
                    )
                except RuntimeError:
                    reply = fallback_message("network", intent.language_code)
            replies.append(translation_only_reply(reply))
        reply = " ".join(replies)
        print(f"Assistant: {reply}")
        if speak:
            for intent, translated_reply in zip(multi_translations, replies):
                _speak(translated_reply, intent.language_code)
        log_turn(
            turn=turn, transcript=user_message, language=multi_translations[-1].language_code,
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    if unsafe_language_reply:
        reply_language_code, reply = unsafe_language_reply
        print(f"Assistant: {reply}")
        if speak:
            _speak(reply, reply_language_code)
        log_turn(
            turn=turn, transcript=user_message, language=reply_language_code,
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    capability_reply = event_language_capability_reply(user_message) if event_mode else None
    if capability_reply:
        reply_language_code, reply = capability_reply
        print(f"Assistant: {reply}")
        if speak:
            _speak(reply, reply_language_code)
        log_turn(
            turn=turn, transcript=user_message, language=reply_language_code,
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    generic_language_reply = event_generic_language_reply(user_message) if event_mode else None
    if generic_language_reply:
        reply_language_code, reply = generic_language_reply
        print(f"Assistant: {reply}")
        if speak:
            _speak(reply, reply_language_code)
        log_turn(
            turn=turn, transcript=user_message, language=reply_language_code,
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    requested_reply_language = (
        event_requested_reply_language(user_message) if event_mode else None
    )
    reply_language_code, reply_language_name = requested_reply_language or language_choice

    physical_reply = physical_action_unavailable_reply(user_message, reply_language_code)
    if physical_reply:
        print(f"Assistant: {physical_reply}")
        if speak:
            _speak(physical_reply, reply_language_code)
        SESSION_STATE["last_language_code"] = language_code
        SESSION_STATE["history"] = [
            *SESSION_STATE["history"],
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": physical_reply},
        ][-4:]
        log_turn(
            turn=turn, transcript=user_message, language=reply_language_code,
            transcript_flagged=False, reply=physical_reply, reply_replaced=False, stt_unclear=False,
        )
        return

    if not RAG_ENABLED and is_company_fact_request(user_message):
        reply = company_facts_unavailable(language_code)
        print("Company facts unavailable; refusing to guess.")
        print(f"Assistant: {reply}")
        if speak:
            _speak(reply, language_code)
        SESSION_STATE["last_language_code"] = language_code
        SESSION_STATE["history"] = [
            *SESSION_STATE["history"],
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ][-4:]
        log_turn(
            turn=turn, transcript=user_message, language=language_code,
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    if translation:
        try:
            from llm import get_llm_reply

            llm_started_at = time.perf_counter()
            reply = get_llm_reply(
                translation.phrase,
                language=translation.language_name,
                history=[],
                use_web=False,
                translation_only=True,
            )
            _debug_timing("llm", llm_started_at)
        except RuntimeError as error:
            print(f"LLM unavailable: {error}")
            reply = fallback_message("network", translation.language_code)
        safe_reply = check_reply(reply, translation.language_code)
        if safe_reply == fallback_message("safe", translation.language_code):
            safe_reply = local_event_translation(
                translation.phrase, translation.language_code
            ) or safe_reply
        safe_reply = translation_only_reply(safe_reply)
        print(f"Assistant: {safe_reply}")
        if speak:
            _speak(safe_reply, translation.language_code)
        SESSION_STATE["history"] = [
            *SESSION_STATE["history"],
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": safe_reply},
        ][-4:]
        log_turn(
            turn=turn, transcript=user_message, language=translation.language_code,
            transcript_flagged=False, reply=safe_reply,
            reply_replaced=safe_reply != reply, stt_unclear=False,
        )
        return

    if is_current_residence_request(user_message):
        reply = current_residence_refusal(language_code)
        print(f"Assistant: {reply}")
        if speak:
            _speak(reply, language_code)
        SESSION_STATE["last_language_code"] = language_code
        SESSION_STATE["history"] = [
            *SESSION_STATE["history"],
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ][-4:]
        log_turn(
            turn=turn, transcript=user_message, language=language_code,
            transcript_flagged=False, reply=reply, reply_replaced=False, stt_unclear=False,
        )
        return

    needs_location_clarification = (
        (live_kind is not None and has_location_reference(lookup_message) and not followup_location)
        or (is_location_clarification(lookup_message) and not followup_location)
    )
    if needs_location_clarification:
        location = extract_explicit_location(lookup_message)
        reply = (
            f"Are you asking for the weather in {location}?"
            if location
            else "Which city or place do you mean?"
        )
        safe_reply = check_reply(reply, "en")
        print(f"Assistant: {safe_reply}")
        if speak:
            _speak(safe_reply, "en")
        SESSION_STATE["last_language_code"] = "en"
        SESSION_STATE["history"] = [
            *SESSION_STATE["history"],
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": safe_reply},
        ][-4:]
        log_turn(
            turn=turn, transcript=user_message, language="en", transcript_flagged=False,
            reply=safe_reply, reply_replaced=safe_reply != reply, stt_unclear=False,
        )
        return

    context_parts = []
    rag_context = ""
    live_request = lookup_message
    if followup_location:
        followup_kind = live_kind or "weather"
        live_request = (
            f"What's the weather like right now in {followup_location}?"
            if followup_kind == "weather"
            else f"What time is it in {followup_location}?"
        )
    live_started_at = time.perf_counter()
    live_context = get_live_context(live_request, followup_location)
    _debug_timing("live_info", live_started_at)
    if live_context:
        context_parts.append(live_context)
        print(
            "Live information: unavailable"
            if "unavailable" in live_context or "lookup failed" in live_context
            else "Live information: found"
        )
    live_failure = live_info_failure_reply(
        live_kind, reply_language_code, live_context, user_message
    )
    if live_failure:
        print(f"Assistant: {live_failure}")
        if speak:
            _speak(live_failure, reply_language_code)
        SESSION_STATE["last_language_code"] = language_code
        SESSION_STATE["history"] = [
            *SESSION_STATE["history"],
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": live_failure},
        ][-4:]
        log_turn(
            turn=turn, transcript=user_message, language=reply_language_code,
            transcript_flagged=False, reply=live_failure, reply_replaced=False, stt_unclear=False,
        )
        return
    live_reply = live_info_direct_reply(
        live_kind, reply_language_code, live_context, user_message
    )
    if live_reply:
        print(f"Assistant: {live_reply}")
        if speak:
            _speak(live_reply, reply_language_code)
        SESSION_STATE["last_language_code"] = language_code
        SESSION_STATE["history"] = [
            *SESSION_STATE["history"],
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": live_reply},
        ][-4:]
        if live_kind:
            SESSION_STATE["last_live_info"] = {
                "kind": live_kind,
                "location": explicit_location or EVENT_CITY,
            }
        log_turn(
            turn=turn, transcript=user_message, language=reply_language_code,
            transcript_flagged=False, reply=live_reply, reply_replaced=False, stt_unclear=False,
        )
        return
    if RAG_ENABLED:
        rag_context = get_context(user_message)
        if rag_context:
            context_parts.append(rag_context)
        print("RAG context: found" if rag_context else "RAG context: not found")
    else:
        print("RAG context: disabled")
    context = "\n\n".join(context_parts)

    if is_company_fact_request(user_message) and not rag_context:
        print("Company facts unavailable; refusing to guess.")
        reply = company_facts_unavailable(language_code)
    else:
        try:
            from llm import get_llm_reply

            llm_started_at = time.perf_counter()
            reply = get_llm_reply(
                live_request,
                context=context,
                language=reply_language_name,
                history=SESSION_STATE["history"],
            )
            _debug_timing("llm", llm_started_at)
        except RuntimeError as error:
            print(f"LLM unavailable: {error}")
            reply = fallback_message("network", language_code)

    safe_reply = check_reply(reply, reply_language_code)
    if safe_reply == fallback_message("safe", reply_language_code):
        safe_reply = public_event_joke_reply(user_message, reply_language_code) or safe_reply
    reply_replaced = safe_reply != reply
    print(f"Assistant: {safe_reply}")
    if speak:
        _speak(safe_reply, reply_language_code)
    SESSION_STATE["last_language_code"] = language_code
    SESSION_STATE["history"] = [
        *SESSION_STATE["history"],
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": safe_reply},
    ][-4:]
    if live_kind:
        remembered_location = explicit_location or EVENT_CITY
        if not (live_kind == "time" and is_ambiguous_time_location(remembered_location)):
            SESSION_STATE["last_live_info"] = {
                "kind": live_kind,
                "location": remembered_location,
            }
    log_turn(
        turn=turn, transcript=user_message, language=reply_language_code, transcript_flagged=False,
        reply=safe_reply, reply_replaced=reply_replaced, stt_unclear=False,
    )


def _transcribe(audio_path: str) -> tuple[str, str | None] | None:
    from stt import transcribe_audio

    try:
        started_at = time.perf_counter()
        result = transcribe_audio(
            audio_path, model_name=WHISPER_MODEL, language=WHISPER_LANGUAGE,
            return_language=True,
        )
        _debug_timing("stt", started_at)
        return result
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
                _reset_session()
                print("Session reset.")
                continue
            try:
                capture_started_at = time.perf_counter()
                audio_path = record_from_mic()
                _debug_timing("capture", capture_started_at)
            except RuntimeError as error:
                print(f"Microphone error: {error}")
                continue

            if audio_path is None:
                if os.getenv("MIC_DEBUG") == "1":
                    print("MIC_DEBUG: no recording was saved; STT and LLM were skipped.")
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


def _warm_up(include_stt: bool = True) -> None:
    print("Warming up...")
    actions = []
    if include_stt:
        from stt import warm_up_stt

        actions.append(("Whisper", lambda: warm_up_stt(WHISPER_MODEL)))
    from llm import warm_up_llm
    from safety import warm_up_moderation

    actions.extend((
        ("moderation", warm_up_moderation),
        ("LLM", warm_up_llm),
    ))
    for label, action in actions:
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
    elif arguments == ["--calibrate-mic"]:
        from mic import calibrate_microphone

        try:
            calibrate_microphone()
        except RuntimeError as error:
            print(f"Microphone calibration error: {error}")
    elif arguments[0] == "--text":
        if len(arguments) != 2:
            print("Usage: python3 main.py --text \"your question\"")
            raise SystemExit(1)
        _warm_up(include_stt=False)
        run_text_mode(arguments[1])
    elif len(arguments) == 1 and not arguments[0].startswith("-"):
        _warm_up()
        run_file_mode(arguments[0])
    else:
        print(
            "Usage: python3 main.py [audio-or-video-file] | --text \"your question\" "
            "| --calibrate-mic"
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
