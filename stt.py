"""Speech-to-text with faster-whisper for files and microphone recordings."""

from functools import lru_cache
import os
from pathlib import Path
import re
from threading import Lock, Thread

from dotenv import load_dotenv


load_dotenv()

_background_warmup_lock = Lock()
_background_warmup_started = False


@lru_cache(maxsize=4)
def _load_whisper_model(model_name: str):
    """Load a CPU-friendly model once, then reuse it for later turns."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install -r requirements.txt"
        ) from error

    try:
        return WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception as error:
        raise RuntimeError(
            f"Could not load Whisper model '{model_name}'. It may need to download "
            "on first use."
        ) from error


def warm_up_stt(model_name: str = "small") -> None:
    """Warm local Whisper now or in the background for fast cloud fallback."""
    if os.getenv("STT_PROVIDER", "local").lower() == "local":
        _load_whisper_model(model_name)
        return

    global _background_warmup_started
    with _background_warmup_lock:
        if _background_warmup_started:
            return
        _background_warmup_started = True

    def load_fallback() -> None:
        try:
            _load_whisper_model(model_name)
        except RuntimeError as error:
            print(f"STT: local fallback warmup failed: {error}")

    Thread(target=load_fallback, name="whisper-fallback-warmup", daemon=True).start()


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

    if os.getenv("STT_PROVIDER", "local").lower() == "openai":
        try:
            text, detected_language = _transcribe_openai(path, language)
        except RuntimeError:
            print("STT: cloud failed, using local Whisper fallback")
            text, detected_language = _transcribe_local(path, model_name, language)
    else:
        text, detected_language = _transcribe_local(path, model_name, language)

    if return_language:
        return text, detected_language
    return text


def is_transcript_unclear(transcript: str) -> bool:
    """Return True for empty, very short, noisy, or obviously repeated text."""
    text = transcript.strip()
    compact_script = bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", text))
    if not text or (len(text) < 3 and not compact_script):
        return True

    alphanumeric = sum(character.isalnum() for character in text)
    if alphanumeric < 2 and not compact_script:
        return True
    if (len(text) - alphanumeric - text.count(" ")) / max(len(text), 1) > 0.70:
        return True

    words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    if not words:
        return True
    if len(words) >= 3 and max(words.count(word) for word in set(words)) / len(words) > 0.70:
        return True

    fillers = {"uh", "um", "erm", "hmm", "ah", "noise"}
    return len(words) <= 2 and all(word in fillers for word in words)
