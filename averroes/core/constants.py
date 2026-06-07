LANG_NAMES = {
    "es": "Spanish",
    "ja": "Japanese",
    "en": "English",
    "fr": "French",
    "pt": "Portuguese",
    "zh": "Mandarin Chinese",
    "de": "German",
    "it": "Italian",
    "ko": "Korean",
    "ar": "Arabic",
    "ru": "Russian",
    "hi": "Hindi",
}

# GPT-4o Realtime native audio format
SAMPLE_RATE = 24000       # 24kHz
CHANNELS = 1              # mono
SAMPLE_WIDTH = 2          # 16-bit PCM = 2 bytes per sample
CHUNK_MS = 100            # 100ms chunks
CHUNK_FRAMES = SAMPLE_RATE * CHUNK_MS // 1000          # 2400 frames
CHUNK_SIZE = CHUNK_FRAMES * CHANNELS * SAMPLE_WIDTH    # 4800 bytes

REALTIME_URL = "wss://api.openai.com/v1/realtime"
REALTIME_TRANSLATE_URL = "wss://api.openai.com/v1/realtime/translations"
