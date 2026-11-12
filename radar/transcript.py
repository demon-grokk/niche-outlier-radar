"""Transcript extraction utility with DB caching, YouTubeTranscriptApi, and Groq Whisper audio fallback."""
import logging
import subprocess
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
from groq import Groq

from radar.config import (
    GROQ_API_KEY,
    GROQ_WHISPER_MODEL,
    WHISPER_AUDIO_DURATION_SECONDS,
)
from radar.fetcher import get_ydl_options
from radar.db import get_db

logger = logging.getLogger(__name__)


def ensure_transcripts_table(conn) -> None:
    """Ensures the transcripts table exists in SQLite database."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            transcript_text TEXT NOT NULL,
            source TEXT DEFAULT 'captions',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)


def get_cached_transcript(video_id: str) -> Optional[str]:
    """Retrieves cached transcript text from SQLite DB if available."""
    try:
        with get_db() as conn:
            ensure_transcripts_table(conn)
            cursor = conn.execute(
                "SELECT transcript_text FROM transcripts WHERE video_id = ?",
                (video_id,)
            )
            row = cursor.fetchone()
            if row and row["transcript_text"]:
                return row["transcript_text"]
    except Exception as e:
        logger.debug(f"DB cache lookup skipped for {video_id}: {e}")
    return None


def save_cached_transcript(video_id: str, transcript_text: str, source: str = "captions") -> None:
    """Persists transcript into SQLite database transcripts table."""
    if not transcript_text:
        return
    try:
        with get_db() as conn:
            ensure_transcripts_table(conn)
            conn.execute("""
                INSERT INTO transcripts (video_id, transcript_text, source, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(video_id) DO UPDATE SET
                    transcript_text = excluded.transcript_text,
                    source = excluded.source,
                    created_at = CURRENT_TIMESTAMP
            """, (video_id, transcript_text, source))
    except Exception as e:
        logger.warning(f"Failed to cache transcript in DB for {video_id}: {e}")


def fetch_captions(video_id: str) -> Optional[str]:
    """
    Attempts to fetch captions using YouTubeTranscriptApi.
    Returns cleaned full text if captions exist and are longer than 50 chars, else None.
    """
    try:
        ytt = YouTubeTranscriptApi()
        fetched = ytt.fetch(video_id)
        snippets = []
        for item in fetched:
            text = getattr(item, "text", None)
            if text is None and isinstance(item, dict):
                text = item.get("text", "")
            if text:
                snippets.append(text.strip())

        full_text = " ".join(snippets).strip()
        return full_text if len(full_text) > 50 else None
    except Exception as e:
        logger.info(f"YouTubeTranscriptApi failed for {video_id}: {e}")
        return None


def stream_audio_and_transcribe_whisper(video_id: str, duration_seconds: Optional[int] = None) -> Optional[str]:
    """
    Fail-Safe Layer 3 Fallback:
    1. Extracts direct audio stream URL via yt-dlp ('bestaudio/best').
    2. Slices the first N seconds (default 120s) into an in-memory MP3 pipe using ffmpeg.
    3. Transcribes using Groq Whisper ('whisper-large-v3').
    """
    if not GROQ_API_KEY:
        logger.warning(f"Cannot perform Whisper audio fallback for {video_id}: GROQ_API_KEY is not configured.")
        return None

    duration = duration_seconds or WHISPER_AUDIO_DURATION_SECONDS or 120
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Step 1: Extract direct audio stream URL
    stream_url = None
    try:
        ydl_opts = get_ydl_options(
            max_videos=1,
            extra_opts={
                "format": "bestaudio/best",
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
            }
        )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            stream_url = info.get("url") if info else None
    except Exception as e:
        logger.error(f"yt-dlp audio stream extraction failed for {video_id}: {e}")
        return None

    if not stream_url:
        logger.error(f"No audio stream URL resolved for {video_id}")
        return None

    # Step 2: Slice audio using ffmpeg into MP3 pipe in memory
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", "0",
            "-i", stream_url,
            "-t", str(duration),
            "-vn",
            "-acodec", "libmp3lame",
            "-b:a", "64k",
            "-f", "mp3",
            "-"
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        audio_bytes = proc.stdout
        if not audio_bytes or len(audio_bytes) < 1000:
            logger.error(f"ffmpeg produced empty or invalid audio slice ({len(audio_bytes)} bytes) for {video_id}")
            return None
    except Exception as e:
        logger.error(f"ffmpeg audio slicing failed for {video_id}: {e}")
        return None

    # Step 3: Transcribe via Groq Whisper API
    try:
        client = Groq(api_key=GROQ_API_KEY)
        model = GROQ_WHISPER_MODEL or "whisper-large-v3"
        res = client.audio.transcriptions.create(
            file=("audio.mp3", audio_bytes),
            model=model
        )
        transcribed_text = res.text.strip() if res and res.text else ""
        if len(transcribed_text) > 10:
            logger.info(f"Successfully transcribed {video_id} via Groq Whisper ({len(transcribed_text)} chars)")
            return transcribed_text
    except Exception as e:
        logger.error(f"Groq Whisper transcription failed for {video_id}: {e}")

    return None


def get_video_transcript(video_id: str, title: str = "") -> str:
    """
    Multi-tier transcript acquisition pipeline:
    1. Check SQLite database cache (transcripts table).
    2. Try YouTube captions via YouTubeTranscriptApi.
    3. Fail-safe fallback: Stream direct audio via yt-dlp + ffmpeg slice + Groq Whisper.
    4. Cache result in DB transcripts table and return.
    """
    # 1. DB Cache Check
    cached = get_cached_transcript(video_id)
    if cached:
        return cached

    # 2. Try YouTube captions
    captions = fetch_captions(video_id)
    if captions:
        save_cached_transcript(video_id, captions, source="captions")
        return captions

    # 3. Audio Fallback via Groq Whisper
    logger.info(f"Captions missing or blocked for {video_id}; initiating Groq Whisper audio fallback.")
    whisper_text = stream_audio_and_transcribe_whisper(video_id)
    if whisper_text:
        save_cached_transcript(video_id, whisper_text, source="whisper")
        return whisper_text

    # 4. Graceful terminal fallback
    if title:
        return f"Transcript unavailable for '{title}' (video ID: {video_id})."
    return ""


def fetch_video_transcript(video_id: str) -> Optional[str]:
    """
    Backward-compatible wrapper for existing callers (e.g. radar/analyzer.py).
    Returns transcript text if available, or None.
    """
    text = get_video_transcript(video_id)
    return text if text and len(text) > 20 else None
