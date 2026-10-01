# Deepgram Nova-3 WAV benchmark

Set `STT_PROVIDER=deepgram` and use a recorded WAV through the normal robot flow.
For Arabic, Urdu, and Bengali runs, set `DEEPGRAM_LANGUAGE` explicitly to `ar`,
`ur`, or `bn`; this benchmark does not assume automatic multilingual recognition
covers those languages.

| Phrase | Provider | Transcript | Detected language | STT duration | Pass/fail |
|---|---|---|---|---|---|
| Hello, can you hear me clearly? |  |  |  |  |  |
| Can I join NASA? |  |  |  |  |  |
| Say good morning in Hindi. |  |  |  |  |  |
| السلام عليكم كيف حالك |  |  |  |  |  |
| آپ کیسے ہیں؟ |  |  |  |  |  |
| আপনি কেমন আছেন? |  |  |  |  |  |
| What is Ibtikar Robotics? |  |  |  |  |  |
| What exactly does Aptech Robotics do? |  |  |  |  |  |

Use `MIC_DEBUG=1` to capture `deepgram_stt_duration` and the overall `stt_duration`.
Record the provider value as `openai` or `deepgram`; do not record API keys.
