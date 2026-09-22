"""Small display-only settings for a cleaner event terminal."""

import os
import warnings


os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
# webrtcvad currently emits this dependency warning on every import.
warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API")
