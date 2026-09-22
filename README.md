# Robot Voice Assistant

This is a local public-demo prototype for a Linux mini-PC with an external
microphone and speaker. It supports both a saved audio/video file and a live,
press-to-record microphone conversation.

## Flow

`audio file or mic -> faster-whisper -> language choice -> safety check -> OpenAI -> safety check -> ElevenLabs -> speaker`

`main.py` coordinates the flow. `stt.py` handles transcription, `mic.py`
records speech using voice activity detection, `llm.py` calls OpenAI, `tts.py`
creates and plays an ElevenLabs MP3, `safety.py` moderates input and spoken
output, and `rag.py` remains optional document lookup.

## Setup

Linux needs FFmpeg and a working audio backend for the connected microphone and
speaker. On Debian/Ubuntu, install them with:

```bash
sudo apt update
sudo apt install ffmpeg portaudio19-dev libsndfile1
```

Then create a virtual environment and install the Python packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your API keys and ElevenLabs voice ID to `.env`. Never commit `.env`.

```env
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o-mini
WEB_SEARCH_ENABLED=false
WEB_SEARCH_PROVIDER=openai
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_DEFAULT=your_elevenlabs_voice_id
WHISPER_MODEL=small
INPUT_DEVICE_NAME=
OUTPUT_DEVICE_NAME=
```

## Optional web search

Set `WEB_SEARCH_ENABLED=true` to allow current public-information lookups.
The default provider, `openai`, uses the existing OpenAI web-search tool.
To try Firecrawl's page-based search instead, create a Firecrawl API key and add
the following to your private `.env` file:

```env
WEB_SEARCH_ENABLED=true
WEB_SEARCH_PROVIDER=firecrawl
FIRECRAWL_API_KEY=your_firecrawl_key
```

Firecrawl sends up to three source pages to the LLM and tells it not to invent
facts missing from those pages. This reduces, but cannot completely eliminate,
wrong or outdated web information. Greetings, robot small talk, and the built-in
Dubai time/weather lookup do not use a Firecrawl search.

## Choose audio devices

Run this command to list devices before configuring them:

```bash
python3 -c "from mic import audio_device_summary; print('\\n'.join(audio_device_summary()))"
```

Copy a distinctive part of the microphone or speaker name into `INPUT_DEVICE_NAME`
or `OUTPUT_DEVICE_NAME`. Leave either setting blank to use the Linux system
default. A configured name that cannot be found stops mic mode with a clear
message instead of silently using the wrong device.

## Run

Test the existing file workflow:

```bash
python3 main.py sample.mp4
```

Start live mic mode:

```bash
python3 main.py
```

Press Enter to start listening. The recorder waits for speech, keeps 300 ms of
pre-roll, and stops after about 900 ms of silence (or a 30-second cap). Press
`Q` then Enter to reset the saved language for the session. Press Ctrl+C to exit.

If the microphone hears only noise, too little speech, or a clearly unusable
transcript, the LLM is skipped and the robot asks the person to repeat it.

## Safety and logging

The transcript is moderated before it reaches the LLM. If that moderation service
is temporarily unavailable, input is allowed so the demo can continue. The final
reply is moderated before TTS; if that service is unavailable, the robot speaks a
safe network fallback instead. `logs/session_YYYY-MM-DD.jsonl` records turns for
troubleshooting and is ignored by Git.

TTS sets a shared `MIC_BLOCKED` flag during playback, so a new recording waits
until the robot finishes speaking.

## Optional RAG

RAG stays off unless `RAG_ENABLED=true`. Build a local index only after placing
`.txt`, `.md`, or `.pdf` files in `knowledge_base/`:

```bash
python3 -c "from rag import build_or_update_knowledge_base; print(build_or_update_knowledge_base())"
```

No index is not an error: the assistant simply runs without document context.
