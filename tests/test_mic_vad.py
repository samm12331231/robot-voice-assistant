"""Deterministic tests for VAD silence and speech-resume timing."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import numpy as np

import mic
from mic import (
    END_SILENCE_FRAMES,
    INITIAL_SPEECH_FRAMES,
    INPUT_SETTLE_FRAMES,
    LOW_ENERGY_RMS,
    SAMPLE_RATE,
    SPEECH_RESUME_FRAMES,
    _advance_silence_state,
    _classify_vad_frame,
    _silence_limit_reached,
)


class VadFrameTests(unittest.TestCase):
    def test_isolated_positive_noise_frames_do_not_prevent_final_stop(self):
        silence = 0
        speech_run = 0
        reset_events = 0
        stopped = False
        frames = [False] * 70 + [True, False, True, False]
        for is_speech in frames:
            previous_silence = silence
            silence, speech_run, resumed = _advance_silence_state(
                is_speech, silence, speech_run
            )
            if resumed and previous_silence:
                reset_events += 1
            stopped = _silence_limit_reached(silence) and speech_run == 0
            if stopped:
                break

        self.assertTrue(stopped)
        self.assertEqual(reset_events, 0)
        self.assertEqual(silence, END_SILENCE_FRAMES + 1)

    def test_six_consecutive_speech_frames_resume_a_paused_turn(self):
        silence = 40
        speech_run = 0
        for _ in range(SPEECH_RESUME_FRAMES - 1):
            silence, speech_run, resumed = _advance_silence_state(
                True, silence, speech_run
            )
            self.assertFalse(resumed)
            self.assertGreater(silence, 0)

        silence, speech_run, resumed = _advance_silence_state(
            True, silence, speech_run
        )
        self.assertTrue(resumed)
        self.assertEqual(silence, 0)
        self.assertEqual(speech_run, 0)

    def test_initial_speech_does_not_use_resume_debounce(self):
        self.assertEqual(_advance_silence_state(True, 0, 0), (0, 0, False))

    def test_repeated_short_noise_bursts_do_not_keep_final_silence_open(self):
        silence = 0
        speech_run = 0
        reset_events = 0
        rejected_runs = 0
        stopped = False
        frames = [False] * 8 + [True] * 3 + [False] * 5 + [True] * 5 + [False] * 100
        for is_speech in frames:
            previous_silence = silence
            previous_run = speech_run
            silence, speech_run, resumed = _advance_silence_state(
                is_speech, silence, speech_run
            )
            if not is_speech and previous_run:
                rejected_runs += 1
            if resumed and previous_silence:
                reset_events += 1
            stopped = _silence_limit_reached(silence) and speech_run == 0
            if stopped:
                break

        self.assertTrue(stopped)
        self.assertEqual(reset_events, 0)
        self.assertEqual(rejected_runs, 2)

    def test_recording_duration_is_capped_even_if_caller_requests_longer(self):
        stream = Mock()
        stream.read.return_value = (np.zeros((480, 1), dtype=np.float32), False)
        sd = Mock()
        sd.InputStream.return_value = stream
        sf = Mock()
        vad = Mock()
        webrtcvad = Mock(Vad=Mock(return_value=vad))

        with (
            patch.object(mic, "_audio_modules", return_value=(np, sd, sf, webrtcvad)),
            patch.object(mic, "resolve_audio_device", return_value=None),
            patch.object(mic, "MIC_BLOCKED") as blocked,
            patch.object(mic, "MAX_RECORD_SECONDS", 0.3),
            patch.object(mic, "_mic_debug_enabled", return_value=False),
        ):
            blocked.is_set.return_value = False
            with redirect_stdout(io.StringIO()):
                result = mic.record_from_mic(duration=30)

        self.assertIsNone(result)  # Ten positives remain below minimum speech validation.
        self.assertEqual(stream.read.call_count, 10 + INPUT_SETTLE_FRAMES)
        sf.write.assert_not_called()

    def _record_frames(self, amplitudes, vad_results):
        stream = Mock()
        stream.read.side_effect = [
            (np.full((480, 1), amplitude, dtype=np.float32), False)
            for amplitude in ([0.0] * INPUT_SETTLE_FRAMES + amplitudes)
        ]
        sd = Mock()
        sd.InputStream.return_value = stream
        sf = Mock()
        vad = Mock()
        vad.is_speech.side_effect = vad_results
        webrtcvad = Mock(Vad=Mock(return_value=vad))
        with (
            patch.object(mic, "_audio_modules", return_value=(np, sd, sf, webrtcvad)),
            patch.object(mic, "resolve_audio_device", return_value=None),
            patch.object(mic, "MIC_BLOCKED") as blocked,
            patch.object(mic, "DEFAULT_OUTPUT_PATH", Path("mock-recording.wav")),
            patch.object(mic, "_mic_debug_enabled", return_value=False),
        ):
            blocked.is_set.return_value = False
            with redirect_stdout(io.StringIO()):
                result = mic.record_from_mic(duration=10)
        return result, sf, vad, stream

    def test_quiet_valid_speech_below_old_floor_reaches_vad_and_is_saved(self):
        voice_frames = 8
        amplitudes = [0.006] * voice_frames + [0.0] * END_SILENCE_FRAMES
        result, sf, vad, _stream = self._record_frames(
            amplitudes, [True] * voice_frames
        )

        self.assertEqual(LOW_ENERGY_RMS, 0.004)
        self.assertEqual(vad.is_speech.call_count, voice_frames)
        self.assertIsNotNone(result)
        sf.write.assert_called_once()

    def test_short_hello_speech_can_be_saved(self):
        voice_frames = 6
        amplitudes = [0.01] * voice_frames + [0.0] * END_SILENCE_FRAMES
        result, sf, _vad, _stream = self._record_frames(
            amplitudes, [True] * voice_frames
        )

        self.assertIsNotNone(result)
        sf.write.assert_called_once()

    def test_isolated_noise_bursts_do_not_save_a_recording(self):
        amplitudes = [0.01, 0.0, 0.01, 0.0, 0.01] + [0.0] * 328
        result, sf, _vad, _stream = self._record_frames(
            amplitudes, [True, True, True]
        )

        self.assertIsNone(result)
        sf.write.assert_not_called()

    def test_three_frame_initial_noise_burst_does_not_start_recording(self):
        amplitudes = [0.01] * (INITIAL_SPEECH_FRAMES - 1) + [0.0] * 330
        result, sf, _vad, _stream = self._record_frames(
            amplitudes, [True] * (INITIAL_SPEECH_FRAMES - 1)
        )

        self.assertIsNone(result)
        sf.write.assert_not_called()

    def test_natural_two_second_pause_then_resumed_speech_is_retained(self):
        silence = 0
        speech_run = 0
        captured_frames = 0
        for _ in range(67):  # 2.01 seconds at 30 ms per frame.
            silence, speech_run, resumed = _advance_silence_state(
                False, silence, speech_run
            )
            captured_frames += 1
            self.assertFalse(resumed)
            self.assertFalse(_silence_limit_reached(silence))

        for _ in range(SPEECH_RESUME_FRAMES):
            silence, speech_run, _resumed = _advance_silence_state(
                True, silence, speech_run
            )
            captured_frames += 1

        self.assertEqual(captured_frames, 67 + SPEECH_RESUME_FRAMES)
        self.assertEqual(silence, 0)
        self.assertEqual(speech_run, 0)
        self.assertFalse(_silence_limit_reached(silence))

    def test_final_silence_ends_at_about_2_2_seconds(self):
        self.assertEqual(END_SILENCE_FRAMES, 73)
        silence = 0
        speech_run = 0
        for _ in range(END_SILENCE_FRAMES - 1):
            silence, speech_run, _resumed = _advance_silence_state(
                False, silence, speech_run
            )
            self.assertFalse(_silence_limit_reached(silence))
        silence, speech_run, _resumed = _advance_silence_state(
            False, silence, speech_run
        )
        self.assertEqual(speech_run, 0)
        self.assertTrue(_silence_limit_reached(silence))
        self.assertAlmostEqual(silence * 30 / 1000, 2.2, places=1)

    def test_no_speech_returns_without_saving_a_recording(self):
        stream = Mock()
        stream.read.return_value = (np.zeros((480, 1), dtype=np.float32), False)
        sd = Mock()
        sd.InputStream.return_value = stream
        sf = Mock()
        vad = Mock()
        webrtcvad = Mock(Vad=Mock(return_value=vad))

        with (
            patch.object(mic, "_audio_modules", return_value=(np, sd, sf, webrtcvad)),
            patch.object(mic, "resolve_audio_device", return_value=None),
            patch.object(mic, "MIC_BLOCKED") as blocked,
            patch.object(mic, "_mic_debug_enabled", return_value=False),
        ):
            blocked.is_set.return_value = False
            output = io.StringIO()
            with redirect_stdout(output):
                result = mic.record_from_mic(duration=0.09)

        self.assertIsNone(result)
        sf.write.assert_not_called()
        stream.stop.assert_called_once()
        stream.close.assert_called_once()
        self.assertIn("Done.", output.getvalue())
        self.assertNotIn("Recorded", output.getvalue())

    def test_low_energy_noise_is_ignored_and_does_not_reset_silence_timer(self):
        vad = Mock()
        vad.is_speech.return_value = True
        samples = np.full(480, LOW_ENERGY_RMS / 2, dtype=np.float32)
        classified_speech, low_energy_ignored = _classify_vad_frame(
            samples, b"", vad, np
        )
        self.assertFalse(classified_speech)
        self.assertTrue(low_energy_ignored)
        vad.is_speech.assert_not_called()

    def test_louder_frame_uses_vad_classification(self):
        vad = Mock()
        vad.is_speech.return_value = True
        samples = np.full(480, LOW_ENERGY_RMS * 2, dtype=np.float32)
        classified_speech, low_energy_ignored = _classify_vad_frame(
            samples, b"", vad, np
        )
        self.assertTrue(classified_speech)
        self.assertFalse(low_energy_ignored)
        vad.is_speech.assert_called_once_with(b"", SAMPLE_RATE)


if __name__ == "__main__":
    unittest.main()
