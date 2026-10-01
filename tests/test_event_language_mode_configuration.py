"""Configuration coverage for the event-language turn handler."""

import os
import unittest
from unittest.mock import patch

import main


class EventLanguageModeConfigurationTests(unittest.TestCase):
    def test_exact_event_mode_value_is_enabled_after_normalization(self):
        with patch.dict(
            os.environ,
            {"LANGUAGE_MODE": "  EVENT_EN_AR_HI_ZH  "},
            clear=False,
        ):
            self.assertTrue(main._event_language_mode_enabled())

    def test_absent_event_mode_is_disabled_at_turn_time(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(main._event_language_mode_enabled())


if __name__ == "__main__":
    unittest.main()
