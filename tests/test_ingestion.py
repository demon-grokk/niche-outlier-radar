"""Comprehensive unit and integration tests for Ingestion Pipeline and Whisper Fallback."""
import subprocess
import pytest
from unittest.mock import patch, MagicMock

import radar.config as config
import radar.db as db
from radar.fetcher import (
    parse_feed_xml,
    fetch_channel_feed,
    fetch_channel_videos,
    fetch_channel_metadata,
    get_browser_headers,
    get_innertube_headers,
    get_ydl_options,
    extract_channel_id,
    clean_channel_url,
    sync_channel,
)
from radar.transcript import (
    get_video_transcript,
    fetch_video_transcript,
    fetch_captions,
    stream_audio_and_transcribe_whisper,
    get_cached_transcript,
    save_cached_transcript,
    ensure_transcripts_table,
)

SAMPLE_XML_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <link rel="self" href="http://www.youtube.com/feeds/videos.xml?channel_id=UCsBjURrPoezykLs9EqgamOA"/>
  <id>yt:channel:UCsBjURrPoezykLs9EqgamOA</id>
  <yt:channelId>UCsBjURrPoezykLs9EqgamOA</yt:channelId>
  <title>Fireship</title>
  <link rel="alternate" href="https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA"/>
  <author>
    <name>Fireship</name>
    <uri>https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA</uri>
  </author>
  <published>2020-04-29T17:15:35+00:00</published>
  <entry>
    <id>yt:video:vid_standard_001</id>
    <yt:videoId>vid_standard_001</yt:videoId>
    <yt:channelId>UCsBjURrPoezykLs9EqgamOA</yt:channelId>
    <title>The runtime wars are over... and Node won</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=vid_standard_001"/>
    <author>
      <name>Fireship</name>
      <uri>https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA</uri>
    </author>
    <published>2026-10-15T17:35:15+00:00</published>
    <updated>2026-10-16T08:37:25+00:00</updated>
    <media:group>
      <media:title>The runtime wars are over... and Node won</media:title>
      <media:thumbnail url="https://i1.ytimg.com/vi/vid_standard_001/hqdefault.jpg" width="480" height="360"/>
      <media:description>Full overview of JS runtime ecosystem.</media:description>
      <media:community>
        <media:starRating count="19702" average="5.00" min="1" max="5"/>
        <media:statistics views="352918"/>
      </media:community>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:vid_short_002</id>
    <yt:videoId>vid_short_002</yt:videoId>
    <yt:channelId>UCsBjURrPoezykLs9EqgamOA</yt:channelId>
    <title>10 CSS tricks in 60 seconds #shorts</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=vid_short_002"/>
    <author>
      <name>Fireship</name>
      <uri>https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA</uri>
    </author>
    <published>2026-10-14T12:00:00+00:00</published>
    <updated>2026-10-14T12:00:00+00:00</updated>
    <media:group>
      <media:title>10 CSS tricks in 60 seconds #shorts</media:title>
      <media:thumbnail url="https://i1.ytimg.com/vi/vid_short_002/hqdefault.jpg" width="480" height="360"/>
      <media:community>
        <media:statistics views="89200"/>
      </media:community>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:vid_no_stats_003</id>
    <yt:videoId>vid_no_stats_003</yt:videoId>
    <yt:channelId>UCsBjURrPoezykLs9EqgamOA</yt:channelId>
    <title>Brand New Tech Video</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=vid_no_stats_003"/>
    <published>2026-10-16T10:00:00+00:00</published>
    <media:group>
      <media:title>Brand New Tech Video</media:title>
      <media:thumbnail url="https://i1.ytimg.com/vi/vid_no_stats_003/hqdefault.jpg"/>
    </media:group>
  </entry>
</feed>
"""


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Isolates tests with a clean temporary SQLite database."""
    test_db_path = tmp_path / "test_radar.db"
    monkeypatch.setattr(config, "DB_PATH", test_db_path)
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    db.init_db()
    with db.get_db() as conn:
        ensure_transcripts_table(conn)
    return test_db_path


# ==========================================
# 1. XML RSS Parsing & View Extraction Tests
# ==========================================

def test_parse_feed_xml_fields():
    """Validates XML parsing extracts video_id, channel_id, title, published_at, thumbnail_url, and views."""
    videos = parse_feed_xml(SAMPLE_XML_FEED)
    assert len(videos) == 3

    v1 = videos[0]
    assert v1["video_id"] == "vid_standard_001"
    assert v1["channel_id"] == "UCsBjURrPoezykLs9EqgamOA"
    assert v1["title"] == "The runtime wars are over... and Node won"
    assert v1["published_at"] == "2026-10-15T17:35:15+00:00"
    assert v1["thumbnail_url"] == "https://i1.ytimg.com/vi/vid_standard_001/hqdefault.jpg"
    assert v1["views"] == 352918
    assert v1["view_count"] == 352918
    assert v1["url"] == "https://www.youtube.com/watch?v=vid_standard_001"
    assert v1["is_short"] is False


def test_parse_feed_xml_views_extraction():
    """Confirms views from media:statistics are accurately cast to int and default to 0 if missing."""
    videos = parse_feed_xml(SAMPLE_XML_FEED)
    assert videos[0]["views"] == 352918
    assert videos[1]["views"] == 89200
    # Third entry has no media:statistics, must default to 0
    assert videos[2]["views"] == 0
    assert videos[2]["view_count"] == 0


def test_parse_feed_xml_shorts_flagging():
    """Confirms #shorts in the title flags is_short = True."""
    videos = parse_feed_xml(SAMPLE_XML_FEED)
    assert videos[0]["is_short"] is False
    assert videos[1]["is_short"] is True


def test_fetch_channel_feed_success():
    """Tests fetch_channel_feed fetches and parses YouTube RSS XML."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_XML_FEED

    with patch("requests.get", return_value=mock_resp) as mock_get:
        videos = fetch_channel_feed("UCsBjURrPoezykLs9EqgamOA")
        assert len(videos) == 3
        assert videos[0]["video_id"] == "vid_standard_001"
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "channel_id=UCsBjURrPoezykLs9EqgamOA" in call_url


def test_fetch_channel_feed_invalid_channel():
    """Tests fetch_channel_feed returns empty list for non-UC IDs."""
    assert fetch_channel_feed("") == []
    assert fetch_channel_feed("invalid_handle") == []


def test_fetch_channel_feed_network_error():
    """Tests graceful fallback on HTTP error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("requests.get", return_value=mock_resp):
        videos = fetch_channel_feed("UCsBjURrPoezykLs9EqgamOA")
        assert videos == []


# ==========================================
# 2. Session Persistence & Inverted Fetching
# ==========================================

def test_session_persistence_headers():
    """Verifies browser session headers and Innertube client headers are structured properly."""
    browser_headers = get_browser_headers()
    assert "User-Agent" in browser_headers
    assert "Mozilla" in browser_headers["User-Agent"]

    innertube_headers = get_innertube_headers()
    assert "X-YouTube-Client-Name" in innertube_headers
    assert "X-YouTube-Client-Version" in innertube_headers
    assert innertube_headers["X-YouTube-Client-Name"] == "1"


def test_ydl_options_configuration():
    """Verifies yt-dlp options include Innertube headers and client parameters."""
    opts = get_ydl_options(max_videos=25)
    assert opts["extract_flat"] is True
    assert opts["playlistend"] == 25
    assert "http_headers" in opts
    assert opts["http_headers"]["X-YouTube-Client-Name"] == "1"
    assert "extractor_args" in opts
    assert "youtube" in opts["extractor_args"]


def test_fetch_channel_videos_xml_priority():
    """Confirms XML RSS is used as the primary layer without invoking yt-dlp when XML succeeds."""
    mock_videos = [
        {
            "video_id": "vid_primary_01",
            "channel_id": "UCsBjURrPoezykLs9EqgamOA",
            "title": "Primary XML Discovery",
            "published_at": "2026-10-16T12:00:00+00:00",
            "thumbnail_url": "https://example.com/thumb.jpg",
            "views": 42000,
            "view_count": 42000,
            "url": "https://www.youtube.com/watch?v=vid_primary_01",
            "duration_seconds": 0,
            "is_short": 0,
        }
    ]

    mock_metadata = {
        "channel_id": "UCsBjURrPoezykLs9EqgamOA",
        "name": "Fireship",
        "url": "https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA",
        "handle": "@Fireship",
        "avatar_url": "https://unavatar.io/youtube/@Fireship",
        "subscriber_count": 0,
    }

    with patch("radar.fetcher.fetch_channel_feed", return_value=mock_videos) as mock_feed:
        with patch("radar.fetcher.fetch_channel_metadata", return_value=mock_metadata):
            with patch("yt_dlp.YoutubeDL") as mock_ydl:
                data = fetch_channel_videos("https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA")
                # Verify primary feed was called
                mock_feed.assert_called_once_with("UCsBjURrPoezykLs9EqgamOA")
                # Verify yt-dlp was NOT called
                mock_ydl.assert_not_called()
                assert len(data["videos"]) == 1
                assert data["videos"][0]["video_id"] == "vid_primary_01"


def test_clean_channel_url_and_extraction():
    """Tests URL normalization and UC channel ID extraction."""
    assert clean_channel_url("@Fireship") == "https://www.youtube.com/@Fireship"
    assert clean_channel_url("UCsBjURrPoezykLs9EqgamOA") == "https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA"
    assert extract_channel_id("https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA") == "UCsBjURrPoezykLs9EqgamOA"


# ==========================================
# 3. Fail-Safe Groq Whisper Fallback Tests
# ==========================================

def test_transcript_db_cache_hit():
    """Verifies that cached transcripts in DB are returned immediately without calling external APIs."""
    test_vid = "vid_cached_123"
    expected_text = "This is a pre-cached transcript stored directly in the SQLite database."
    save_cached_transcript(test_vid, expected_text, source="captions")

    with patch("radar.transcript.YouTubeTranscriptApi") as mock_ytt:
        with patch("radar.transcript.stream_audio_and_transcribe_whisper") as mock_whisper:
            transcript = get_video_transcript(test_vid)
            assert transcript == expected_text
            # No external API should have been called
            mock_ytt.assert_not_called()
            mock_whisper.assert_not_called()


def test_transcript_caption_success():
    """Verifies YouTubeTranscriptApi success path caches and returns text."""
    test_vid = "vid_captions_success_456"

    mock_snippet = MagicMock()
    mock_snippet.text = "Hello world from authentic YouTube captions!"
    mock_instance = MagicMock()
    mock_instance.fetch.return_value = [mock_snippet] * 5

    with patch("radar.transcript.YouTubeTranscriptApi", return_value=mock_instance):
        with patch("radar.transcript.stream_audio_and_transcribe_whisper") as mock_whisper:
            transcript = get_video_transcript(test_vid)
            assert "Hello world from authentic YouTube captions!" in transcript
            mock_whisper.assert_not_called()

            # Verify it was saved to DB
            cached = get_cached_transcript(test_vid)
            assert cached == transcript


def test_whisper_audio_fallback_when_captions_fail(monkeypatch):
    """
    Simulates YouTube caption failure (e.g. TranscriptsDisabled or IpBlocked)
    and asserts complete fallback to yt-dlp audio stream + ffmpeg + Groq Whisper.
    """
    # radar/transcript.py binds GROQ_API_KEY at import time, so the consumer
    # module must be patched (same pattern as the radar.analyzer tests).
    monkeypatch.setattr("radar.transcript.GROQ_API_KEY", "gsk_test_key_mock_1234567890")
    test_vid = "vid_blocked_captions_789"
    expected_whisper_text = "Welcome to this episode. Today we build autonomous AI agents using graphs and models."

    # 1. YouTube caption raises exception
    mock_caption_instance = MagicMock()
    mock_caption_instance.fetch.side_effect = Exception("TranscriptsDisabled: Subtitles are disabled for this video")

    # 2. yt-dlp returns direct audio stream URL
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.return_value = {
        "url": "https://rr3---sn-mock.googlevideo.com/videoplayback?audio_stream"
    }

    # 3. ffmpeg slices audio into MP3 bytes
    fake_mp3_bytes = b"ID3\x03\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x44" * 1000
    mock_subprocess_res = MagicMock()
    mock_subprocess_res.returncode = 0
    mock_subprocess_res.stdout = fake_mp3_bytes

    # 4. Groq Whisper client returns transcription
    mock_transcription_res = MagicMock()
    mock_transcription_res.text = expected_whisper_text
    mock_groq_client = MagicMock()
    mock_groq_client.audio.transcriptions.create.return_value = mock_transcription_res

    with patch("radar.transcript.YouTubeTranscriptApi", return_value=mock_caption_instance):
        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
            with patch("subprocess.run", return_value=mock_subprocess_res) as mock_ffmpeg:
                with patch("radar.transcript.Groq", return_value=mock_groq_client) as mock_groq_cls:
                    transcript = get_video_transcript(test_vid)

                    # Assert returned text matches Whisper output
                    assert transcript == expected_whisper_text

                    # Verify ffmpeg called with -ss 0 and -t 120 and libmp3lame
                    mock_ffmpeg.assert_called_once()
                    cmd = mock_ffmpeg.call_args[0][0]
                    assert "ffmpeg" in cmd
                    assert "-acodec" in cmd
                    assert "libmp3lame" in cmd

                    # Verify Groq Whisper was called with whisper-large-v3
                    mock_groq_client.audio.transcriptions.create.assert_called_once()
                    call_kwargs = mock_groq_client.audio.transcriptions.create.call_args[1]
                    assert call_kwargs["model"] == "whisper-large-v3"

                    # Verify cached in DB with source='whisper'
                    cached = get_cached_transcript(test_vid)
                    assert cached == expected_whisper_text

                    with db.get_db() as conn:
                        row = conn.execute("SELECT source FROM transcripts WHERE video_id = ?", (test_vid,)).fetchone()
                        assert row["source"] == "whisper"


def test_fetch_video_transcript_wrapper():
    """Tests the backward-compatible fetch_video_transcript wrapper."""
    test_vid = "vid_wrapper_test"
    with patch("radar.transcript.get_video_transcript", return_value="A valid transcript over 20 chars long"):
        res = fetch_video_transcript(test_vid)
        assert res == "A valid transcript over 20 chars long"

    with patch("radar.transcript.get_video_transcript", return_value=""):
        res = fetch_video_transcript(test_vid)
        assert res is None


# ==========================================
# 4. End-to-End Channel Sync Test with RSS
# ==========================================

def test_sync_channel_with_rss():
    """Tests sync_channel populates both channels and videos tables using XML RSS data."""
    mock_videos = [
        {
            "video_id": "vid_synced_01",
            "channel_id": "UCsBjURrPoezykLs9EqgamOA",
            "title": "Synced Video via XML",
            "published_at": "2026-10-15T10:00:00+00:00",
            "thumbnail_url": "https://example.com/thumb.jpg",
            "views": 150000,
            "view_count": 150000,
            "url": "https://www.youtube.com/watch?v=vid_synced_01",
            "duration_seconds": 300,
            "is_short": 0,
        }
    ]

    mock_metadata = {
        "channel_id": "UCsBjURrPoezykLs9EqgamOA",
        "name": "Fireship",
        "url": "https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA",
        "handle": "@Fireship",
        "avatar_url": "https://unavatar.io/youtube/@Fireship",
        "subscriber_count": 0,
    }

    with patch("radar.fetcher.fetch_channel_feed", return_value=mock_videos):
        with patch("radar.fetcher.fetch_channel_metadata", return_value=mock_metadata):
            res = sync_channel("https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA")
            assert res["success"] is True
            assert res["videos_count"] == 1

        channels = db.get_all_channels()
        assert len(channels) == 1
        assert channels[0]["channel_id"] == "UCsBjURrPoezykLs9EqgamOA"

        vids = db.get_channel_videos("UCsBjURrPoezykLs9EqgamOA")
        assert len(vids) == 1
        assert vids[0]["video_id"] == "vid_synced_01"
        assert vids[0]["view_count"] == 150000
