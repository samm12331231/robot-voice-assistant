"""Generate a local MP3 reply with ElevenLabs and play it back."""

import os
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

from audio_state import MIC_BLOCKED
from dotenv import load_dotenv


load_dotenv()


def _debug_timing(stage: str, started_at: float) -> None:
    """Print opt-in timing details without changing playback behavior."""
    if os.getenv("MIC_DEBUG") == "1":
        print(f"MIC_DEBUG: {stage}_duration={time.perf_counter() - started_at:.3f}s")


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

    output_device = os.getenv("OUTPUT_DEVICE_NAME") or None
    MIC_BLOCKED.set()
    started_at = time.perf_counter()
    try:
        attempts = [output_device] if output_device else []
        attempts.append(None)
        last_error = None
        for device_name in attempts:
            try:
                pygame.mixer.quit()
                if device_name:
                    pygame.mixer.init(devicename=device_name)
                else:
                    pygame.mixer.init()
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(100)
                return
            except Exception as error:
                last_error = error
        raise RuntimeError(f"Audio playback failed on configured and default speakers: {last_error}")
    except Exception as error:
        raise RuntimeError(f"Could not play audio: {error}") from error
    finally:
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        # Release capture only after the playback device has been torn down.
        MIC_BLOCKED.clear()
        _debug_timing("tts_playback", started_at)


def _stream_audio_to_default_speaker(audio, output_path: Path) -> None:
    """Save streamed MP3 chunks while ffplay begins default-speaker playback early."""
    try:
        process = subprocess.Popen(
            ["ffplay", "-autoexit", "-nodisp", "-loglevel", "error", "-i", "pipe:0"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise RuntimeError(f"Could not start streamed audio playback: {error}") from error

    MIC_BLOCKED.set()
    started_at = time.perf_counter()
    try:
        with output_path.open("wb") as output_file:
            for chunk in audio:
                if not chunk:
                    continue
                output_file.write(chunk)
                process.stdin.write(chunk)
                process.stdin.flush()
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Streamed audio playback failed.")
    except Exception as error:
        if process.poll() is None:
            process.kill()
        raise RuntimeError(f"Could not stream audio playback: {error}") from error
    finally:
        # Do not unblock the microphone while ffplay may still be exiting.
        if process.poll() is None:
            process.kill()
        process.wait()
        MIC_BLOCKED.clear()
        _debug_timing("tts_stream_generation_playback", started_at)


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
        generation_started_at = time.perf_counter()
        client = ElevenLabs(api_key=api_key, timeout=8)
        model_id = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
        stream_to_default_speaker = (
            play_audio
            and not os.getenv("OUTPUT_DEVICE_NAME")
            and shutil.which("ffplay") is not None
        )
        create_audio = (
            client.text_to_speech.convert_as_stream
            if stream_to_default_speaker
            else client.text_to_speech.convert
        )
        audio = create_audio(
            voice_id=_voice_id_for(language),
            model_id=model_id,
            output_format="mp3_22050_32",
            optimize_streaming_latency=3,
            text=text,
        )
        if stream_to_default_speaker:
            _stream_audio_to_default_speaker(audio, output_path)
        else:
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

    if not stream_to_default_speaker:
        _debug_timing("tts_generation", generation_started_at)

    if play_audio and not stream_to_default_speaker:
        _play_audio(output_path)

    return str(output_path)
