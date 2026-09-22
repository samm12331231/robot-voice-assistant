"""File-based speech-to-text using Whisper."""

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _load_whisper_model(model_name: str):
    """Load one Whisper model and reuse it for later transcriptions."""
    try:
        import whisper
    except ImportError as error:
        raise RuntimeError(
            "Whisper is not installed. Run: pip install -r requirements.txt"
        ) from error

    try:
        return whisper.load_model(model_name)
    except Exception as error:
        raise RuntimeError(
            f"Could not load Whisper model '{model_name}'. Check your internet "
            "connection for the first download."
        ) from error


def transcribe_audio(
    audio_path: str,
    model_name: str = "small",
    language: str | None = None,
    return_language: bool = False,
) -> str | tuple[str, str | None]:
    """Transcribe a local audio file and optionally return Whisper's language.

    The model is cached after its first load. Future microphone code can save
    audio to a file and call this same function.

    Raises:
        FileNotFoundError: If ``audio_path`` does not exist or is not a file.
        RuntimeError: If Whisper is unavailable or transcription fails.
    """
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        model = _load_whisper_model(model_name)
        options = {"language": language} if language else {}
        result = model.transcribe(str(path), **options)
        text = result.get("text", "").strip()
        detected_language = result.get("language")
    except Exception as error:
        if isinstance(error, RuntimeError):
            raise
        raise RuntimeError(
            "Could not transcribe the audio file. Check that it is a supported "
            "audio format and that FFmpeg is installed."
        ) from error

    if not text:
        raise RuntimeError("Whisper finished, but no speech was detected in the audio file.")

    if return_language:
        return text, detected_language
    return text
