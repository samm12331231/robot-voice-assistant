"""VAD-based microphone recording for a Linux mini-PC and external microphone."""

from collections import deque
import os
from pathlib import Path
import time

from audio_state import MIC_BLOCKED


SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
PRE_ROLL_FRAMES = 10  # 300 ms
END_SILENCE_FRAMES = 67  # About 2 seconds of silence before ending a turn.
MIN_SPEECH_FRAMES = 14  # 420 ms
MAX_RECORD_SECONDS = 30
DEFAULT_OUTPUT_PATH = Path("output/mic_input.wav")


def _audio_modules():
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
        import webrtcvad
    except ImportError as error:
        raise RuntimeError(
            "Microphone dependencies are missing. Run: pip install -r requirements.txt"
        ) from error
    return np, sd, sf, webrtcvad


def list_audio_devices() -> list[dict]:
    """Return the system audio devices as plain dictionaries."""
    _, sd, _, _ = _audio_modules()
    try:
        return [dict(device) for device in sd.query_devices()]
    except Exception as error:
        raise RuntimeError(f"Could not list audio devices: {error}") from error


def audio_device_summary() -> list[str]:
    """Return readable input/output device names for startup output."""
    lines = []
    for index, device in enumerate(list_audio_devices()):
        roles = []
        if device.get("max_input_channels", 0) > 0:
            roles.append("input")
        if device.get("max_output_channels", 0) > 0:
            roles.append("output")
        if roles:
            lines.append(f"  [{index}] {device['name']} ({', '.join(roles)})")
    return lines


def resolve_audio_device(name: str | None, direction: str) -> int | None:
    """Resolve a configured device-name substring, or use the system default."""
    if not name:
        return None
    channel_key = "max_input_channels" if direction == "input" else "max_output_channels"
    matches = [
        index
        for index, device in enumerate(list_audio_devices())
        if name.lower() in device["name"].lower() and device.get(channel_key, 0) > 0
    ]
    if not matches:
        raise RuntimeError(
            f"Configured {direction} device '{name}' was not found. "
            "Check INPUT_DEVICE_NAME or OUTPUT_DEVICE_NAME in .env."
        )
    return matches[0]


def validate_configured_devices() -> None:
    """Fail early if a selected input or output device cannot be found."""
    resolve_audio_device(os.getenv("INPUT_DEVICE_NAME"), "input")
    resolve_audio_device(os.getenv("OUTPUT_DEVICE_NAME"), "output")


def record_from_mic(duration: int = MAX_RECORD_SECONDS, samplerate: int = SAMPLE_RATE) -> str | None:
    """Wait for speech, record until a pause, and save 16-bit mono WAV audio."""
    np, sd, sf, webrtcvad = _audio_modules()
    if samplerate != SAMPLE_RATE:
        raise RuntimeError(f"VAD recording requires {SAMPLE_RATE} Hz audio.")

    while MIC_BLOCKED.is_set():
        time.sleep(0.05)

    input_device = resolve_audio_device(os.getenv("INPUT_DEVICE_NAME"), "input")
    try:
        sd.check_input_settings(
            device=input_device, samplerate=SAMPLE_RATE, channels=1, dtype="float32"
        )
    except Exception as error:
        print(f"Warning: 16 kHz pre-check failed; will try the microphone anyway: {error}")

    pre_roll: deque[bytes] = deque(maxlen=PRE_ROLL_FRAMES)
    frames: list[bytes] = []
    speech_frames = 0
    silence_frames = 0
    started = False
    max_frames = max(1, int(duration * 1000 / FRAME_MS))
    vad = webrtcvad.Vad(2)

    recording_rate = SAMPLE_RATE
    frame_samples = FRAME_SAMPLES

    def open_stream(rate: int, samples_per_frame: int):
        return sd.InputStream(
            samplerate=rate,
            channels=1,
            dtype="float32",
            blocksize=samples_per_frame,
            device=input_device,
        )

    print("Listening...")
    try:
        try:
            stream = open_stream(SAMPLE_RATE, FRAME_SAMPLES)
            stream.start()
        except Exception as first_error:
            try:
                stream.close()
            except Exception:
                pass
            try:
                device_info = sd.query_devices(input_device, kind="input")
                recording_rate = int(round(device_info["default_samplerate"]))
                frame_samples = int(recording_rate * FRAME_MS / 1000)
                if frame_samples <= 0:
                    raise RuntimeError("The microphone reported an invalid native sample rate.")
                stream = open_stream(recording_rate, frame_samples)
                stream.start()
                from scipy.signal import resample

                print(f"Using microphone native rate {recording_rate} Hz and resampling to 16 kHz.")
            except Exception as fallback_error:
                raise RuntimeError(
                    "Could not open the microphone at 16 kHz or its native sample rate. "
                    "Check the connected microphone and INPUT_DEVICE_NAME setting."
                ) from fallback_error

        try:
            for _ in range(max_frames):
                float_frame, _overflowed = stream.read(frame_samples)
                if recording_rate != SAMPLE_RATE:
                    float_frame = resample(float_frame[:, 0], FRAME_SAMPLES).reshape(-1, 1)
                pcm = (np.clip(float_frame[:, 0], -1.0, 1.0) * 32767).astype("<i2").tobytes()
                is_speech = vad.is_speech(pcm, SAMPLE_RATE)

                if not started:
                    pre_roll.append(pcm)
                    if not is_speech:
                        continue
                    started = True
                    frames.extend(pre_roll)
                    speech_frames += 1
                    print("Recording...")
                    continue

                frames.append(pcm)
                if is_speech:
                    speech_frames += 1
                    silence_frames = 0
                else:
                    silence_frames += 1
                    if silence_frames >= END_SILENCE_FRAMES:
                        break
        finally:
            stream.stop()
            stream.close()
    except Exception as error:
        raise RuntimeError(f"Microphone recording failed: {error}") from error

    if not started or speech_frames < MIN_SPEECH_FRAMES:
        print("Done.")
        return None

    output_path = DEFAULT_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        audio = np.frombuffer(b"".join(frames), dtype="<i2").reshape(-1, 1)
        sf.write(str(output_path), audio, SAMPLE_RATE, subtype="PCM_16")
    except Exception as error:
        raise RuntimeError(f"Could not save recording to {output_path}: {error}") from error

    print("Done.")
    return str(output_path)


if __name__ == "__main__":
    print("\n".join(audio_device_summary()))
