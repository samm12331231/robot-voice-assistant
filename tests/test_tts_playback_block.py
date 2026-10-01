"""Playback cleanup tests that do not start an audio device."""

from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

import tts


class PlaybackBlockTests(unittest.TestCase):
    def test_microphone_unblocks_only_after_mixer_teardown(self):
        order = []
        mixer = types.SimpleNamespace(
            quit=Mock(side_effect=lambda: order.append("mixer.quit")),
            init=Mock(),
            music=types.SimpleNamespace(
                load=Mock(),
                play=Mock(),
                get_busy=Mock(return_value=False),
            ),
        )
        pygame = types.SimpleNamespace(mixer=mixer, time=types.SimpleNamespace(wait=Mock()))
        blocked = types.SimpleNamespace(
            set=Mock(side_effect=lambda: order.append("blocked.set")),
            clear=Mock(side_effect=lambda: order.append("blocked.clear")),
        )

        with (
            patch.dict(sys.modules, {"pygame": pygame}),
            patch.object(tts, "MIC_BLOCKED", blocked),
            patch("tts.os.getenv", return_value=None),
        ):
            tts._play_audio(Path("mock-reply.mp3"))

        self.assertEqual(order[-2:], ["mixer.quit", "blocked.clear"])
        blocked.set.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
