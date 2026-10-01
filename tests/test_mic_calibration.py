"""Deterministic, no-device checks for microphone calibration metrics."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

import main
import mic


class MicrophoneCalibrationTests(unittest.TestCase):
    def test_calibration_metrics_report_quantiles_vad_runs_and_candidate_counts(self):
        metrics = mic.calibration_metrics(
            [0.001, 0.003, 0.005, 0.007, 0.009],
            [False, True, True, False, True],
            np,
        )

        self.assertEqual(metrics["frames"], 5)
        self.assertEqual(metrics["rms_min"], 0.001)
        self.assertAlmostEqual(metrics["rms_median"], 0.005)
        self.assertEqual(metrics["vad_positive_frames"], 3)
        self.assertEqual(metrics["longest_vad_run"], 2)
        self.assertEqual(metrics["floor_pass_frames"], {
            0.002: 4, 0.004: 3, 0.006: 2, 0.008: 1,
        })

    def test_recommendation_uses_measurement_separation_without_applying_it(self):
        ambient = mic.calibration_metrics([0.001] * 10, [False] * 10, np)
        speaking = mic.calibration_metrics([0.005] * 10, [True] * 10, np)

        recommendation = mic.calibration_recommendation(ambient, speaking)

        self.assertIn("0.004", recommendation)
        self.assertIn("Review", recommendation)
        self.assertEqual(mic.LOW_ENERGY_RMS, 0.004)

    def test_recommendation_accepts_real_airhug_clean_separation_at_008(self):
        ambient = {
            "frames": 134,
            "rms_p95": 0.0031,
            "floor_pass_frames": {0.002: 0, 0.004: 0, 0.006: 0, 0.008: 0},
        }
        speaking = {
            "frames": 133,
            "rms_median": 0.0940,
            "floor_pass_frames": {0.002: 133, 0.004: 120, 0.006: 100, 0.008: 83},
        }

        recommendation = mic.calibration_recommendation(ambient, speaking)

        self.assertIn("0.008", recommendation)

    def test_calibration_command_does_not_warm_up_or_call_any_service(self):
        calibrate = Mock()
        with (
            patch.dict(sys.modules, {"mic": SimpleNamespace(calibrate_microphone=calibrate)}),
            patch.object(main, "_warm_up") as warm_up,
            patch.object(sys, "argv", ["main.py", "--calibrate-mic"]),
            redirect_stdout(io.StringIO()),
        ):
            main.main()

        calibrate.assert_called_once_with()
        warm_up.assert_not_called()


if __name__ == "__main__":
    unittest.main()
