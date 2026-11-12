"""Configuration settings for Niche Outlier Radar."""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)

DB_PATH = DATA_DIR / "radar.db"

# Outlier & Feed parameters (Strict 7-15 days freshness, 50 videos limit)
DEFAULT_OUTLIER_MULTIPLIER = float(os.getenv("OUTLIER_MULTIPLIER", "1.8"))
RECENCY_DAYS = int(os.getenv("RECENCY_DAYS", "15"))
FEED_LIMIT = int(os.getenv("FEED_LIMIT", "50"))
MEDIAN_BASELINE_COUNT = int(os.getenv("MEDIAN_BASELINE_COUNT", "50"))
MIN_VIDEO_VIEWS_FLOOR = int(os.getenv("MIN_VIDEO_VIEWS_FLOOR", "1000"))

# Sync settings
SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "6"))

# Session Persistence & Innertube Headers
DEFAULT_USER_AGENT = os.getenv(
    "DEFAULT_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)
YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", str(DATA_DIR / "youtube_cookies.txt"))

# Whisper Audio Fallback Settings
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")
WHISPER_AUDIO_DURATION_SECONDS = int(os.getenv("WHISPER_AUDIO_DURATION_SECONDS", "120"))

def resolve_groq_api_key() -> str:
    """Attempts to find Groq API key from env, .env, or Handy settings."""
    key = os.getenv("GROQ_API_KEY", "").strip()
    if key:
        return key

    handy_settings = Path.home() / ".local/share/com.pais.handy/settings_store.json"
    if handy_settings.exists():
        try:
            with open(handy_settings, "r", encoding="utf-8") as f:
                data = json.load(f)
                settings = data.get("settings", {})
                api_keys = settings.get("post_process_api_keys", {})
                if "groq" in api_keys and api_keys["groq"]:
                    return api_keys["groq"].strip()
        except Exception:
            pass

    return ""

GROQ_API_KEY = resolve_groq_api_key()
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")
