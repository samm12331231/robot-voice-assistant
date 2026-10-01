"""Speech-to-text with faster-whisper for files and microphone recordings."""

from functools import lru_cache
import os
from pathlib import Path
import re
from importlib.util import find_spec
from threading import Lock
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from dotenv import load_dotenv


load_dotenv()

_background_warmup_lock = Lock()
_background_warmup_started = False
_fallback_notice_printed = False


def _cached_whisper_model_path(model_name: str) -> Path | None:
    """Find an existing local model directory without contacting Hugging Face."""
    model_path = Path(model_name)
    if model_path.is_dir():
        return model_path
    cache_root = Path(
        os.getenv("HF_HUB_CACHE")
        or os.getenv("HUGGINGFACE_HUB_CACHE")
        or (Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub")
    )
    snapshots = cache_root / f"models--Systran--faster-whisper-{model_name}" / "snapshots"
    if not snapshots.is_dir():
        return None
    cached_models = [path for path in snapshots.iterdir() if path.is_dir()]
    if not cached_models:
        return None
    return max(cached_models, key=lambda path: path.stat().st_mtime)


@lru_cache(maxsize=4)
def _load_whisper_model(model_name: str):
    """Load a CPU-friendly model once, then reuse it for later turns."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError(
            "faster-whisper is not installed; offline transcription is unavailable."
        ) from error

    model_path = _cached_whisper_model_path(model_name)
    if model_path is None:
        raise RuntimeError(
            f"Offline Whisper model '{model_name}' is not cached; no model was downloaded."
        )

    try:
        return WhisperModel(str(model_path), device="cpu", compute_type="int8")
    except Exception as error:
        raise RuntimeError(
            f"Could not load cached Whisper model '{model_name}'."
        ) from error


def warm_up_stt(model_name: str = "small") -> None:
    """Report optional local fallback availability without downloading a model."""
    if os.getenv("STT_PROVIDER", "openai").lower() == "local":
        _load_whisper_model(model_name)
        return

    global _background_warmup_started, _fallback_notice_printed
    with _background_warmup_lock:
        if _background_warmup_started:
            return
        _background_warmup_started = True
        if (
            (find_spec("faster_whisper") is None or _cached_whisper_model_path(model_name) is None)
            and not _fallback_notice_printed
        ):
            print("Offline Whisper fallback unavailable; cloud STT remains active.")
            _fallback_notice_printed = True


def _transcribe_openai(path: Path, language: str | None) -> tuple[str, str | None]:
    """Transcribe one file with OpenAI's cloud STT service."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")

    try:
        from openai import OpenAI

        with path.open("rb") as audio_file:
            request = {
                "file": audio_file,
                "model": os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe"),
            }
            if language:
                request["language"] = language
            response = OpenAI(api_key=api_key, timeout=10).audio.transcriptions.create(**request)
        text = re.sub(r"\s+", " ", response.text).strip()
        return text, getattr(response, "language", None)
    except Exception as error:
        raise RuntimeError(f"Cloud transcription failed: {error}") from error


def _deepgram_timeout_seconds() -> float:
    """Return a bounded REST timeout without exposing configuration values."""
    try:
        return max(1.0, float(os.getenv("DEEPGRAM_TIMEOUT_SECONDS", "10")))
    except ValueError:
        return 10.0


def _deepgram_keyterms() -> list[str]:
    """Read optional approved keyterms from configuration, never source code."""
    return [term.strip() for term in os.getenv("DEEPGRAM_KEYTERMS", "").split(",") if term.strip()]


def _parse_deepgram_response(payload: dict, requested_language: str | None) -> tuple[str, str | None]:
    """Extract one transcript and language hint from a Deepgram REST response."""
    try:
        channel = payload["results"]["channels"][0]
        transcript = channel["alternatives"][0]["transcript"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Deepgram returned an unexpected transcription response.") from error
    text = re.sub(r"\s+", " ", str(transcript)).strip()
    if not text:
        raise RuntimeError("Deepgram returned an empty transcript.")
    detected_language = channel.get("detected_language") or payload.get("metadata", {}).get(
        "detected_language"
    ) or requested_language
    return text, detected_language


def _transcribe_deepgram(path: Path, language: str | None) -> tuple[str, str | None]:
    """Transcribe a recorded WAV with Deepgram Nova-3 over a bounded REST request."""
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY is missing")
    requested_language = language or os.getenv("DEEPGRAM_LANGUAGE") or None
    query = {
        "model": os.getenv("DEEPGRAM_MODEL", "nova-3"),
        "smart_format": "true",
    }
    if requested_language:
        query["language"] = requested_language
    keyterms = _deepgram_keyterms()
    query_items = list(query.items()) + [("keyterm", term) for term in keyterms]
    endpoint = f"https://api.deepgram.com/v1/listen?{urlencode(query_items)}"
    try:
        started_at = time.perf_counter()
        request = Request(
            endpoint,
            data=path.read_bytes(),
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "audio/wav",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=_deepgram_timeout_seconds()) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if os.getenv("MIC_DEBUG") == "1":
            print(f"MIC_DEBUG: deepgram_stt_duration={time.perf_counter() - started_at:.3f}s")
        return _parse_deepgram_response(payload, requested_language)
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(f"Deepgram transcription failed: {error}") from error


def _transcribe_local(
    path: Path, model_name: str, language: str | None
) -> tuple[str, str | None]:
    """Transcribe one file with the installed faster-whisper model."""
    try:
        model = _load_whisper_model(model_name)
        segments, info = model.transcribe(
            str(path), language=language, beam_size=5, vad_filter=False
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        return re.sub(r"\s+", " ", text).strip(), getattr(info, "language", None)
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(
            "Could not transcribe the audio. Check the media file, FFmpeg, and Whisper model."
        ) from error


def _transcribe_openai_with_local_fallback(
    path: Path, model_name: str, language: str | None
) -> tuple[str, str | None]:
    """Keep the established OpenAI then local-Whisper fallback behavior in one place."""
    try:
        return _transcribe_openai(path, language)
    except RuntimeError as cloud_error:
        try:
            return _transcribe_local(path, model_name, language)
        except RuntimeError as local_error:
            raise RuntimeError(
                f"Cloud transcription failed ({cloud_error}); offline Whisper fallback "
                f"is unavailable ({local_error})."
            ) from local_error


def transcribe_audio(
    audio_path: str,
    model_name: str = "small",
    language: str | None = None,
    return_language: bool = False,
) -> str | tuple[str, str | None]:
    """Transcribe media with the selected provider and local fallback when needed."""
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    provider = os.getenv("STT_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        text, detected_language = _transcribe_openai_with_local_fallback(path, model_name, language)
    elif provider == "deepgram":
        try:
            text, detected_language = _transcribe_deepgram(path, language)
        except RuntimeError as deepgram_error:
            print("Deepgram transcription failed; using the OpenAI fallback.")
            try:
                text, detected_language = _transcribe_openai_with_local_fallback(
                    path, model_name, language
                )
            except RuntimeError as fallback_error:
                raise RuntimeError(
                    f"Deepgram transcription failed ({deepgram_error}); OpenAI fallback "
                    f"failed ({fallback_error})."
                ) from fallback_error
    elif provider == "local":
        text, detected_language = _transcribe_local(path, model_name, language)
    else:
        raise RuntimeError("STT_PROVIDER must be 'openai', 'deepgram', or legacy 'local'.")

    if return_language:
        return text, detected_language
    return text


def is_transcript_unclear(transcript: str) -> bool:
    """Return True for empty, very short, noisy, or obviously repeated text."""
    text = transcript.strip()
    compact_script = bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", text))
    words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    short_greetings = {"hi", "hey", "hello", "hola", "halo"}
    if words and len(words) <= 2 and all(word in short_greetings for word in words):
        return False

    if not text or (len(text) < 3 and not compact_script):
        return True

    alphanumeric = sum(character.isalnum() for character in text)
    if alphanumeric < 2 and not compact_script:
        return True
    if (len(text) - alphanumeric - text.count(" ")) / max(len(text), 1) > 0.70:
        return True

    if not words:
        return True
    if len(words) >= 3 and max(words.count(word) for word in set(words)) / len(words) > 0.70:
        return True

    fillers = {"uh", "um", "erm", "hmm", "ah", "noise"}
    return len(words) <= 2 and all(word in fillers for word in words)
