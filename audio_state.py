"""State shared by microphone capture and speech playback."""

from threading import Event


MIC_BLOCKED = Event()
