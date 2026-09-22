# Robot Voice Assistant

This local prototype accepts an audio or video file, transcribes speech with
Whisper, detects the transcript language, asks an OpenRouter model for a short
reply, and saves an ElevenLabs spoken reply as an MP3 file. Local document
search is optional.

## Project structure

- `main.py`: coordinates the full file-to-speech flow.
- `stt.py`: transcribes local media files with Whisper.
- `language_utils.py`: detects a language code and readable label.
- `llm.py`: sends text and optional context to OpenRouter.
- `rag.py`: optionally indexes and searches local documents with ChromaDB.
- `tts.py`: saves an ElevenLabs MP3 response.

## Setup

FFmpeg must be installed for Whisper to read common audio and video formats.

```bash
pip install -r requirements.txt
```

Create or update `.env` with the following values:

```env
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=openrouter/free

ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_DEFAULT=your_elevenlabs_voice_id
ELEVENLABS_MODEL=eleven_multilingual_v2
TTS_OUTPUT_PATH=output/reply.mp3

RAG_ENABLED=false
RAG_DOCUMENTS_DIR=knowledge_base
RAG_PERSIST_DIRECTORY=chroma_db

# The multilingual Whisper model. For English-only use: small.en and en.
WHISPER_MODEL=small
WHISPER_LANGUAGE=
```

Optional language-specific ElevenLabs voices can be added to `.env`:

```env
ELEVENLABS_VOICE_EN=your_english_voice_id
ELEVENLABS_VOICE_AR=your_arabic_voice_id
ELEVENLABS_VOICE_HI=your_hindi_voice_id
ELEVENLABS_VOICE_RU=your_russian_voice_id
```

## Test each stage

Transcription only:

```bash
python3 -c "from stt import transcribe_audio; print(transcribe_audio('sample.mp4'))"
```

LLM only:

```bash
python3 -c "from llm import get_llm_reply; print(get_llm_reply('Hello', language='English'))"
```

TTS only:

```bash
python3 -c "from tts import speak_text; print(speak_text('Hello from the robot assistant', language='en'))"
```

Build and test RAG:

```bash
mkdir -p knowledge_base
printf 'The robot assistant can answer questions from recorded audio files.' > knowledge_base/example.txt
python3 -c "from rag import build_or_update_knowledge_base; print(build_or_update_knowledge_base())"
python3 -c "from rag import get_context; print(get_context('What can the robot assistant do?'))"
```

Full pipeline without RAG:

```bash
python3 main.py sample.mp4
```

Full pipeline with RAG after building the index:

```bash
RAG_ENABLED=true python3 main.py sample.mp4
```

Microphone input, live conversations, and continuous memory are not built yet.
RAG is optional: if `chroma_db` does not exist, the assistant continues without
document context.
