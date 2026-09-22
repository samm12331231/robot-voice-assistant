"""Speech-to-text with faster-whisper for files and microphone recordings."""

from functools import lru_cache
from pathlib import Path
import re


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
    """Load the configured model during startup so the first turn is faster."""
    _load_whisper_model(model_name)


def transcribe_audio(
    audio_path: str,
    model_name: str = "small",
    language: str | None = None,
    return_language: bool = False,
) -> str | tuple[str, str | None]:
    """Transcribe a local media file and optionally return Whisper's language code."""
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        model = _load_whisper_model(model_name)
        segments, info = model.transcribe(
            str(path), language=language, beam_size=5, vad_filter=False
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        text = re.sub(r"\s+", " ", text).strip()
        detected_language = getattr(info, "language", None)
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(
            "Could not transcribe the audio. Check the media file, FFmpeg, and Whisper model."
        ) from error

    if return_language:
        return text, detected_language
    return text


def is_transcript_unclear(transcript: str) -> bool:
    """Return True for empty, very short, noisy, or obviously repeated text."""
    text = transcript.strip()
    if not text or len(text) < 3:
        return True

    alphanumeric = sum(character.isalnum() for character in text)
    if alphanumeric < 2:
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
