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
END_SILENCE_FRAMES = 73  # About 2.2 seconds of silence before ending a turn.
SPEECH_RESUME_FRAMES = 6  # Require 180 ms of continuous speech before resetting silence.
MIN_SPEECH_FRAMES = 3  # Short greetings are valid when supported by a brief consecutive run.
MIN_CONSECUTIVE_SPEECH_FRAMES = 3
INITIAL_SPEECH_FRAMES = 4  # Ignore short VAD-positive noise bursts before recording starts.
INPUT_SETTLE_FRAMES = 6  # Discard 180 ms of stale device or keyboard audio before listening.
DEFAULT_MAX_RECORD_SECONDS = 15


def _configured_max_record_seconds() -> float:
    """Read a defensive process-level recording cap without requiring a .env entry."""
    try:
        configured = float(os.getenv("MIC_MAX_RECORD_SECONDS", DEFAULT_MAX_RECORD_SECONDS))
    except (TypeError, ValueError):
        return float(DEFAULT_MAX_RECORD_SECONDS)
    return max(0.03, configured)


MAX_RECORD_SECONDS = _configured_max_record_seconds()
DEFAULT_OUTPUT_PATH = Path("output/mic_input.wav")
LOW_ENERGY_RMS = 0.004
CALIBRATION_RMS_FLOORS = (0.002, 0.004, 0.006, 0.008)


def _mic_debug_enabled() -> bool:
    """Enable temporary microphone diagnostics only when explicitly requested."""
    return os.getenv("MIC_DEBUG") == "1"


def _classify_vad_frame(samples, pcm: bytes, vad, np) -> tuple[bool, bool]:
    """Return voice classification and whether low energy bypassed the VAD call."""
    frame_rms = float(np.sqrt(np.mean(samples ** 2)))
    if frame_rms < LOW_ENERGY_RMS:
        return False, True
    return bool(vad.is_speech(pcm, SAMPLE_RATE)), False


def _longest_true_run(values) -> int:
    """Return the longest consecutive run of true values."""
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def calibration_metrics(rms_values, vad_positive, np) -> dict:
    """Summarize locally captured calibration frames without changing VAD policy."""
    if not rms_values:
        return {
            "frames": 0, "rms_min": 0.0, "rms_median": 0.0,
            "rms_p90": 0.0, "rms_p95": 0.0, "vad_positive_frames": 0,
            "longest_vad_run": 0, "floor_pass_frames": {
                floor: 0 for floor in CALIBRATION_RMS_FLOORS
            },
        }
    return {
        "frames": len(rms_values),
        "rms_min": float(min(rms_values)),
        "rms_median": float(np.percentile(rms_values, 50)),
        "rms_p90": float(np.percentile(rms_values, 90)),
        "rms_p95": float(np.percentile(rms_values, 95)),
        "vad_positive_frames": sum(vad_positive),
        "longest_vad_run": _longest_true_run(vad_positive),
        "floor_pass_frames": {
            floor: sum(rms >= floor for rms in rms_values)
            for floor in CALIBRATION_RMS_FLOORS
        },
    }


def calibration_recommendation(ambient: dict, speaking: dict) -> str:
    """Recommend a candidate floor from measurements only; never apply it."""
    if not ambient["frames"] or not speaking["frames"]:
        return "No recommendation: calibration did not capture both phases."
    candidates = [
        floor for floor in CALIBRATION_RMS_FLOORS
        if ambient["rms_p95"] < floor
        and speaking["rms_median"] >= floor
        and speaking["floor_pass_frames"][floor] >= max(3, speaking["frames"] // 2)
    ]
    if candidates:
        return (
            f"Measured candidate floor: {max(candidates):.3f}. "
            "Review the counts before changing any recording setting."
        )
    ratio = speaking["rms_median"] / max(ambient["rms_p95"], 0.000001)
    return (
        f"No tested floor cleanly separates speech from ambient audio (median/p95 ratio {ratio:.1f}). "
        "Check microphone placement, output feedback, and repeat calibration."
    )


def _print_calibration_metrics(label: str, metrics: dict) -> None:
    """Print compact local calibration measurements."""
    floor_counts = ", ".join(
        f"{floor:.3f}={metrics['floor_pass_frames'][floor]}"
        for floor in CALIBRATION_RMS_FLOORS
    )
    print(
        f"{label}: rms min/median/p90/p95="
        f"{metrics['rms_min']:.4f}/{metrics['rms_median']:.4f}/"
        f"{metrics['rms_p90']:.4f}/{metrics['rms_p95']:.4f}; "
        f"vad_positive_frames={metrics['vad_positive_frames']}; "
        f"longest_vad_positive_run={metrics['longest_vad_run']}; "
        f"floor_pass_frames[{floor_counts}]"
    )


def _advance_silence_state(
    is_speech: bool, silence_frames: int, speech_run_frames: int
) -> tuple[int, int, bool]:
    """Advance silence and confirm resumed speech only after consecutive VAD positives."""
    if is_speech:
        if silence_frames == 0:
            return 0, 0, False
        speech_run_frames += 1
        if speech_run_frames >= SPEECH_RESUME_FRAMES:
            return 0, 0, True
        return silence_frames + 1, speech_run_frames, False
    return silence_frames + 1, 0, False


def _silence_limit_reached(silence_frames: int) -> bool:
    return silence_frames >= END_SILENCE_FRAMES


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


def calibrate_microphone() -> None:
    """Measure ambient and normal speech locally on the configured input device."""
    np, sd, _sf, webrtcvad = _audio_modules()
    input_device = resolve_audio_device(os.getenv("INPUT_DEVICE_NAME"), "input")
    phase_frames = {
        "ambient silence": round(2_000 / FRAME_MS),
        "normal speech": round(4_000 / FRAME_MS),
        "final ambient silence": round(2_000 / FRAME_MS),
    }
    print("Microphone calibration uses local audio metrics only; it saves no WAV and calls no services.")
    print("1. Stay silent for 2 seconds.")
    print("2. Speak normally for 4 seconds: Hello, can you hear me clearly? I would like to ask a question.")
    print("3. Stay silent again for 2 seconds.")
    try:
        sd.check_input_settings(
            device=input_device, samplerate=SAMPLE_RATE, channels=1, dtype="float32"
        )
    except Exception as error:
        print(f"Warning: 16 kHz pre-check failed; will try the microphone anyway: {error}")

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=FRAME_SAMPLES,
        device=input_device,
    )
    phase_data = {name: ([], []) for name in phase_frames}
    vad = webrtcvad.Vad(3)
    try:
        stream.start()
        for phase, frame_count in phase_frames.items():
            input(f"Press Enter, then {phase} begins... ")
            rms_values, vad_positive = phase_data[phase]
            for _ in range(frame_count):
                float_frame, _overflowed = stream.read(FRAME_SAMPLES)
                samples = float_frame[:, 0]
                pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
                rms_values.append(float(np.sqrt(np.mean(samples ** 2))))
                vad_positive.append(bool(vad.is_speech(pcm, SAMPLE_RATE)))
    except Exception as error:
        raise RuntimeError(f"Microphone calibration failed: {error}") from error
    finally:
        try:
            stream.stop()
        finally:
            stream.close()

    initial_ambient = calibration_metrics(*phase_data["ambient silence"], np)
    final_ambient = calibration_metrics(*phase_data["final ambient silence"], np)
    ambient = calibration_metrics(
        phase_data["ambient silence"][0] + phase_data["final ambient silence"][0],
        phase_data["ambient silence"][1] + phase_data["final ambient silence"][1], np,
    )
    speaking = calibration_metrics(*phase_data["normal speech"], np)
    _print_calibration_metrics("Ambient silence (first)", initial_ambient)
    _print_calibration_metrics("Normal speech", speaking)
    _print_calibration_metrics("Ambient silence (final)", final_ambient)
    print(f"Recommendation: {calibration_recommendation(ambient, speaking)}")


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
    initial_speech_frames = 0
    consecutive_speech_frames = 0
    max_consecutive_speech_frames = 0
    silence_frames = 0
    speech_run_frames = 0
    speech_segments = 0
    silence_reset_events = 0
    rejected_noise_runs = 0
    rejected_noise_frames = 0
    max_silence_before_reset_frames = 0
    low_energy_ignored_frames = 0
    started = False
    capped_duration = min(max(float(duration), FRAME_MS / 1000), MAX_RECORD_SECONDS)
    max_frames = max(1, int(capped_duration * 1000 / FRAME_MS))
    vad = webrtcvad.Vad(3)

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
            for _ in range(INPUT_SETTLE_FRAMES):
                stream.read(frame_samples)
            print("Listening...")
            for _ in range(max_frames):
                float_frame, _overflowed = stream.read(frame_samples)
                if recording_rate != SAMPLE_RATE:
                    float_frame = resample(float_frame[:, 0], FRAME_SAMPLES).reshape(-1, 1)
                pcm = (np.clip(float_frame[:, 0], -1.0, 1.0) * 32767).astype("<i2").tobytes()
                is_speech, low_energy_ignored = _classify_vad_frame(
                    float_frame[:, 0], pcm, vad, np
                )
                if low_energy_ignored:
                    low_energy_ignored_frames += 1

                if not started:
                    pre_roll.append(pcm)
                    if not is_speech:
                        initial_speech_frames = 0
                        continue
                    initial_speech_frames += 1
                    if initial_speech_frames < INITIAL_SPEECH_FRAMES:
                        continue
                    started = True
                    frames.extend(pre_roll)
                    speech_frames = initial_speech_frames
                    consecutive_speech_frames = initial_speech_frames
                    max_consecutive_speech_frames = initial_speech_frames
                    speech_segments = 1
                    print("Recording...")
                    continue

                frames.append(pcm)
                if is_speech:
                    speech_frames += 1
                    consecutive_speech_frames += 1
                    max_consecutive_speech_frames = max(
                        max_consecutive_speech_frames, consecutive_speech_frames
                    )
                else:
                    consecutive_speech_frames = 0
                previous_silence_frames = silence_frames
                previous_speech_run_frames = speech_run_frames
                silence_frames, speech_run_frames, speech_resumed = _advance_silence_state(
                    is_speech, silence_frames, speech_run_frames
                )
                if not is_speech and previous_speech_run_frames:
                    rejected_noise_runs += 1
                    rejected_noise_frames += previous_speech_run_frames
                if speech_resumed and previous_silence_frames:
                    speech_segments += 1
                    silence_reset_events += 1
                    max_silence_before_reset_frames = max(
                        max_silence_before_reset_frames, previous_silence_frames
                    )
                if _silence_limit_reached(silence_frames) and speech_run_frames == 0:
                    break
        finally:
            stream.stop()
            stream.close()
    except Exception as error:
        raise RuntimeError(f"Microphone recording failed: {error}") from error

    recorded_seconds = len(frames) * FRAME_MS / 1000
    if _mic_debug_enabled():
        time_after_voice = f"{silence_frames * FRAME_MS / 1000:.1f}s" if started else "n/a"
        print(
            "MIC_DEBUG: "
            f"recorded={recorded_seconds:.1f}s, after_last_voice={time_after_voice}, "
            f"speech_frames={speech_frames}, low_energy_ignored_frames={low_energy_ignored_frames}, "
            f"max_consecutive_speech_frames={max_consecutive_speech_frames}, "
            f"speech_segments={speech_segments}, silence_resets={silence_reset_events}, "
            f"confirmed_resume_events={silence_reset_events}, "
            f"rejected_noise_runs={rejected_noise_runs}, "
            f"rejected_noise_frames={rejected_noise_frames}, "
            f"max_silence_before_reset="
            f"{max_silence_before_reset_frames * FRAME_MS / 1000:.1f}s"
        )
    if (
        not started
        or speech_frames < MIN_SPEECH_FRAMES
        or max_consecutive_speech_frames < MIN_CONSECUTIVE_SPEECH_FRAMES
    ):
        if _mic_debug_enabled():
            reason = "no voice-classified frames" if not started else "too little consecutive speech to save"
            print(f"MIC_DEBUG: {reason}; transcription and LLM skipped.")
        print("Done.")
        return None

    output_path = DEFAULT_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        audio = np.frombuffer(b"".join(frames), dtype="<i2").reshape(-1, 1)
        sf.write(str(output_path), audio, SAMPLE_RATE, subtype="PCM_16")
    except Exception as error:
        raise RuntimeError(f"Could not save recording to {output_path}: {error}") from error

    print(f"Recorded {recorded_seconds:.1f} seconds")
    print("Done.")
    return str(output_path)


if __name__ == "__main__":
    print("\n".join(audio_device_summary()))
