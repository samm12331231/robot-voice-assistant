"""Regression coverage for test-local LANGUAGE_MODE isolation."""

import os
import unittest
from unittest.mock import patch


class LanguageModeIsolationRegressionTests(unittest.TestCase):
    def test_environment_patch_is_scoped_and_restored(self):
        original = os.environ.get("LANGUAGE_MODE")
        with patch.dict(os.environ, {"LANGUAGE_MODE": ""}, clear=False):
            self.assertEqual(os.environ["LANGUAGE_MODE"], "")
        self.assertEqual(os.environ.get("LANGUAGE_MODE"), original)

