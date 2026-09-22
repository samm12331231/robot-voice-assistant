"""Generate a local MP3 reply with ElevenLabs and play it back."""

import os
from pathlib import Path
from uuid import uuid4

from audio_state import MIC_BLOCKED
from dotenv import load_dotenv


load_dotenv()


def _voice_id_for(language: str) -> str:
    """Choose a language-specific voice, with a default fallback."""
    code = language.lower()[:2]
    voice_id = os.getenv(f"ELEVENLABS_VOICE_{code.upper()}")
    voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_DEFAULT")
    if not voice_id:
        raise RuntimeError(
            "No ElevenLabs voice is configured. Set ELEVENLABS_VOICE_DEFAULT in .env."
        )
    return voice_id


def _play_audio(path: Path) -> None:
    """Play audio while preventing the microphone from hearing the speaker."""
    try:
        import pygame
    except ImportError as error:
        raise RuntimeError(
            "pygame is not installed. Run: pip install -r requirements.txt"
        ) from error

    try:
        output_device = os.getenv("OUTPUT_DEVICE_NAME") or None
        pygame.mixer.init(devicename=output_device)
        MIC_BLOCKED.set()
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
    except Exception as error:
        raise RuntimeError(f"Could not play audio through pygame: {error}") from error
    finally:
        MIC_BLOCKED.clear()
        try:
            pygame.mixer.quit()
        except Exception:
            pass


def speak_text(
    text: str,
    language: str = "en",
    unique_filename: bool = False,
    play_audio: bool = True,
) -> str:
    """Create an MP3 file from text, optionally play it, and return its path.

    ``language`` should be a short language code such as ``en`` or ``ar``.
    Set ``play_audio=False`` to save the file without playing it.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is missing. Add it to your .env file before running."
        )

    try:
        from elevenlabs.client import ElevenLabs
    except ImportError as error:
        raise RuntimeError(
            "ElevenLabs is not installed. Run: pip install -r requirements.txt"
        ) from error

    output_path = Path(os.getenv("TTS_OUTPUT_PATH", "output/reply.mp3"))
    if unique_filename:
        suffix = output_path.suffix or ".mp3"
        output_path = output_path.with_name(f"{output_path.stem}_{uuid4().hex[:8]}{suffix}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        client = ElevenLabs(api_key=api_key, timeout=8)
        audio = client.text_to_speech.convert(
            voice_id=_voice_id_for(language),
            model_id=os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
            output_format="mp3_44100_128",
            text=text,
        )
        with output_path.open("wb") as output_file:
            for chunk in audio:
                if chunk:
                    output_file.write(chunk)
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(f"ElevenLabs could not create speech: {error}") from error

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("ElevenLabs returned no audio data.")

    if play_audio:
        _play_audio(output_path)

    return str(output_path)
