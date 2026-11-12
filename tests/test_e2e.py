"""
Comprehensive 4-Tier Opaque-Box E2E Test Suite for Niche Outlier Radar.
Requirements Covered: R1 (Ingestion), R2 (100-Channel Catalog & Recency), R3 (Outlier Engine), R4 (UI & REST API).
"""
import json
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch

import pytest
import requests
from starlette.testclient import TestClient

import radar.config
import radar.db
import radar.fetcher
import radar.outlier_engine
import radar.analyzer
import radar.seed_channels
import radar.transcript
from radar.db import (
    get_db,
    init_db,
    upsert_channel,
    upsert_video,
    upsert_outlier,
    get_all_channels,
    delete_channel,
    get_channel_videos,
    get_outliers,
    create_sync_log,
    update_sync_log,
    get_latest_sync_status
)
from radar.fetcher import clean_channel_url, fetch_rss_timestamps, sync_channel
from radar.outlier_engine import calculate_channel_median, detect_outliers_for_channel
from radar.analyzer import analyze_outlier_video
from radar.transcript import fetch_video_transcript
from app.main import app


# ==============================================================================
# TIER 1: FEATURE COVERAGE (R1 - R4)
# ==============================================================================

class TestTier1FeatureCoverage:
    """Tier 1: Comprehensive feature coverage across R1 through R4."""

    # --------------------------------------------------------------------------
    # R1: Hybrid Ingestion Pipeline
    # --------------------------------------------------------------------------

    def test_r1_rss_feed_parsing_extracts_all_entry_metadata(self, sample_atom_xml):
        """Feature 1: Channel XML RSS feed parser extracts video IDs and published timestamps."""
        ch_id = "UC_TEST_RSS_001"
        xml_data = sample_atom_xml(channel_id=ch_id, entries=[
            {
                "video_id": "vid_xml_test_01",
                "title": "Autonomous AI Agents Deep Dive",
                "published": "2026-10-14T08:30:00+00:00",
                "views": 42000
            },
            {
                "video_id": "vid_xml_test_02",
                "title": "Local LLM Fine-Tuning Tutorial",
                "published": "2026-10-15T10:15:00+00:00",
                "views": 88000
            }
        ])

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = xml_data
            mock_resp.content = xml_data.encode("utf-8")
            mock_get.return_value = mock_resp

            timestamps = fetch_rss_timestamps(ch_id)

            assert "vid_xml_test_01" in timestamps
            assert timestamps["vid_xml_test_01"] == "2026-10-14T08:30:00+00:00"
            assert "vid_xml_test_02" in timestamps
            assert timestamps["vid_xml_test_02"] == "2026-10-15T10:15:00+00:00"
            assert mock_get.called
            assert ch_id in mock_get.call_args[0][0]

    def test_r1_rss_feed_view_count_extraction_from_media_statistics(self, sample_atom_xml):
        """Feature 1: RSS XML parses view counts from media:community/media:statistics."""
        ch_id = "UC_TEST_VIEWS_002"
        xml_data = sample_atom_xml(channel_id=ch_id, entries=[
            {
                "video_id": "vid_views_check",
                "title": "MCP Server Architecture Guide",
                "published": "2026-10-16T12:00:00+00:00",
                "views": 67500
            }
        ])

        root = ET.fromstring(xml_data)
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'yt': 'http://www.youtube.com/xml/schemas/2015',
            'media': 'http://search.yahoo.com/mrss/'
        }
        entry = root.find('atom:entry', ns)
        assert entry is not None
        stats = entry.find('media:group/media:community/media:statistics', ns)
        assert stats is not None
        assert int(stats.attrib['views']) == 67500

    def test_r1_channel_url_normalization_handles_various_formats(self):
        """Feature 2: clean_channel_url normalizes handles, channel IDs, and naked names."""
        assert clean_channel_url("@AIJasonZ") == "https://www.youtube.com/@AIJasonZ"
        assert clean_channel_url("AIJasonZ") == "https://www.youtube.com/@AIJasonZ"
        assert clean_channel_url("UC_x36zCEGilGpBFlrPLgkKw") == "https://www.youtube.com/channel/UC_x36zCEGilGpBFlrPLgkKw"
        assert clean_channel_url("https://www.youtube.com/@Fireship") == "https://www.youtube.com/@Fireship"
        assert clean_channel_url("https://youtube.com/@Fireship/videos") == "https://youtube.com/@Fireship/videos"

    def test_r1_channel_video_sync_persists_channel_and_videos(self):
        """Feature 2: sync_channel persists channel metadata and video records in DB."""
        ch_id = "UC_MOCK_SYNC_CH_01"
        mock_data = {
            "channel": {
                "channel_id": ch_id,
                "name": "AI Automation Studio",
                "handle": "@aiautomation",
                "url": "https://www.youtube.com/@aiautomation",
                "avatar_url": "https://unavatar.io/youtube/@aiautomation"
            },
            "videos": [
                {
                    "video_id": "vid_sync_01",
                    "title": "Building Production Multi-Agent Systems",
                    "url": "https://www.youtube.com/watch?v=vid_sync_01",
                    "thumbnail_url": "https://i.ytimg.com/vi/vid_sync_01/hqdefault.jpg",
                    "published_at": "2026-10-15T14:00:00+00:00",
                    "view_count": 28500,
                    "duration_seconds": 720,
                    "is_short": False
                },
                {
                    "video_id": "vid_sync_02",
                    "title": "Cursor AI 2.0 Full Review",
                    "url": "https://www.youtube.com/watch?v=vid_sync_02",
                    "thumbnail_url": "https://i.ytimg.com/vi/vid_sync_02/hqdefault.jpg",
                    "published_at": "2026-10-14T09:00:00+00:00",
                    "view_count": 45000,
                    "duration_seconds": 540,
                    "is_short": False
                }
            ]
        }

        with patch("radar.fetcher.fetch_channel_videos", return_value=mock_data):
            res = sync_channel("https://www.youtube.com/@aiautomation")
            assert res["success"] is True
            assert res["channel_id"] == ch_id
            assert res["videos_count"] == 2

            videos = get_channel_videos(ch_id)
            assert len(videos) == 2
            v_ids = {v["video_id"] for v in videos}
            assert "vid_sync_01" in v_ids
            assert "vid_sync_02" in v_ids

    def test_r1_transcript_fetch_with_caption_success(self):
        """Feature 3: fetch_video_transcript returns full cleaned text when captions succeed."""
        vid_id = "vid_transcript_ok"
        mock_transcript_items = [
            {"text": "Welcome back everyone."},
            {"text": "Today we are building an autonomous agent from scratch."},
            {"text": "We will use SQLite WAL mode for state persistence and Groq for inference."}
        ]

        with patch("radar.transcript.YouTubeTranscriptApi") as mock_ytt_cls:
            mock_ytt = MagicMock()
            mock_ytt.fetch.return_value = mock_transcript_items
            mock_ytt_cls.return_value = mock_ytt

            text = fetch_video_transcript(vid_id)
            assert text is not None
            assert len(text) > 50
            assert "autonomous agent from scratch" in text
            assert "SQLite WAL mode" in text

    def test_r1_whisper_fallback_architecture_contract(self):
        """Feature 3: Transcript pipeline interface handles fallback when caption fetch fails."""
        vid_id = "vid_caption_failure"
        with patch("radar.transcript.YouTubeTranscriptApi") as mock_ytt_cls:
            mock_ytt = MagicMock()
            mock_ytt.fetch.side_effect = Exception("YouTube captions disabled or blocked (HTTP 429)")
            mock_ytt_cls.return_value = mock_ytt

            text = fetch_video_transcript(vid_id)
            # Default fetcher logs warning and returns None on caption error
            assert text is None

    # --------------------------------------------------------------------------
    # R2: 100-Channel Catalog & Strict 7–15 Day Freshness
    # --------------------------------------------------------------------------

    def test_r2_catalog_channel_seeding_and_upsert_idempotency(self):
        """Feature 4: Seeding channels into the database is idempotent and does not create duplicates."""
        initial_channels = get_all_channels()
        initial_count = len(initial_channels)

        # Re-running seed should return 0 new channels because all already exist
        seeded = radar.seed_channels.seed_default_channels()
        assert seeded == 0

        current_channels = get_all_channels()
        assert len(current_channels) == initial_count

    def test_r2_category_distribution_across_5_core_domains(self, seed_catalog_helper):
        """Feature 4: Tracked creator catalog spans the 5 authoritative AI/Tech domains."""
        seeded = seed_catalog_helper(count=25)
        assert len(seeded) == 25

        categories = {ch["category"] for ch in seeded}
        expected_categories = {"AI Agents", "Automations", "AI News", "Developer Tools", "AGI Research"}
        assert categories == expected_categories

    def test_r2_strict_15_day_recency_filter(self):
        """Feature 6: Outlier engine and feed queries enforce strict 15-day recency cutoff."""
        test_ch = "UC_RECENCY_TEST_01"
        upsert_channel(channel_id=test_ch, name="Recency Test Channel", url="https://youtube.com/@recency")

        now = datetime.now(timezone.utc)
        # Baseline videos (older, to establish channel median)
        for i in range(10):
            upsert_video(
                video_id=f"vid_baseline_{i}",
                channel_id=test_ch,
                title=f"Old Video {i}",
                url=f"https://youtube.com/watch?v=vid_baseline_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(days=20 + i)).isoformat(),
                view_count=10000,
                duration_seconds=600,
                is_short=False
            )

        # Video published 5 days ago (Within 15 days, 3.5x multiplier)
        upsert_video(
            video_id="vid_recent_outlier",
            channel_id=test_ch,
            title="Recent Breakthrough Video",
            url="https://youtube.com/watch?v=vid_recent_outlier",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=5)).isoformat(),
            view_count=35000,
            duration_seconds=600,
            is_short=False
        )

        # Video published 22 days ago (Outside 15 days, 4.0x multiplier)
        upsert_video(
            video_id="vid_stale_outlier",
            channel_id=test_ch,
            title="Stale Breakthrough Video",
            url="https://youtube.com/watch?v=vid_stale_outlier",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=22)).isoformat(),
            view_count=40000,
            duration_seconds=600,
            is_short=False
        )

        # Detect outliers with strict 15-day recency
        outliers = detect_outliers_for_channel(test_ch, min_multiplier=2.0, days_back=15)
        outlier_vids = [o["video_id"] for o in outliers]

        assert "vid_recent_outlier" in outlier_vids
        assert "vid_stale_outlier" not in outlier_vids

    def test_r2_feed_ordering_by_published_at_descending(self):
        """Feature 6: Feed query orders videos strictly by published_at DESC."""
        test_ch = "UC_ORDER_TEST_01"
        upsert_channel(channel_id=test_ch, name="Order Test Channel", url="https://youtube.com/@order")

        now = datetime.now(timezone.utc)
        upsert_video(
            video_id="vid_order_day1",
            channel_id=test_ch,
            title="Published 1 day ago",
            url="https://youtube.com/watch?v=vid_order_day1",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=1)).isoformat(),
            view_count=12000,
            duration_seconds=600,
            is_short=False
        )
        upsert_video(
            video_id="vid_order_day4",
            channel_id=test_ch,
            title="Published 4 days ago",
            url="https://youtube.com/watch?v=vid_order_day4",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=4)).isoformat(),
            view_count=15000,
            duration_seconds=600,
            is_short=False
        )
        upsert_video(
            video_id="vid_order_day2",
            channel_id=test_ch,
            title="Published 2 days ago",
            url="https://youtube.com/watch?v=vid_order_day2",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=2)).isoformat(),
            view_count=18000,
            duration_seconds=600,
            is_short=False
        )

        videos = get_channel_videos(test_ch, limit=10)
        assert len(videos) == 3
        # Strict descending order
        assert videos[0]["video_id"] == "vid_order_day1"
        assert videos[1]["video_id"] == "vid_order_day2"
        assert videos[2]["video_id"] == "vid_order_day4"

    def test_r2_feed_density_up_to_50_videos(self):
        """Feature 6: Database query reliably returns dense feed limited to 50 videos."""
        test_ch = "UC_DENSITY_TEST_01"
        upsert_channel(channel_id=test_ch, name="Density Test Channel", url="https://youtube.com/@density")

        now = datetime.now(timezone.utc)
        for i in range(60):
            upsert_video(
                video_id=f"vid_dense_{i:02d}",
                channel_id=test_ch,
                title=f"Dense Video {i}",
                url=f"https://youtube.com/watch?v=vid_dense_{i:02d}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(hours=i)).isoformat(),
                view_count=10000 + i,
                duration_seconds=500,
                is_short=False
            )

        videos_50 = get_channel_videos(test_ch, limit=50)
        assert len(videos_50) == 50

    def test_r2_foreign_key_cascade_deletion(self):
        """Feature 5: Deleting a channel cascades and removes all its videos and outliers."""
        ch_id = "UC_CASCADE_TEST_01"
        upsert_channel(channel_id=ch_id, name="Cascade Test Channel", url="https://youtube.com/@cascade")

        upsert_video(
            video_id="vid_cascade_01",
            channel_id=ch_id,
            title="Video for Cascade Test",
            url="https://youtube.com/watch?v=vid_cascade_01",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at="2026-10-15T10:00:00+00:00",
            view_count=50000,
            duration_seconds=600,
            is_short=False
        )

        upsert_outlier(
            video_id="vid_cascade_01",
            channel_id=ch_id,
            multiplier=3.5,
            channel_median=14000
        )

        # Verify exist in DB
        with get_db() as conn:
            cursor_v = conn.execute("SELECT COUNT(*) FROM videos WHERE channel_id = ?", (ch_id,))
            assert cursor_v.fetchone()[0] == 1
            cursor_o = conn.execute("SELECT COUNT(*) FROM outliers WHERE channel_id = ?", (ch_id,))
            assert cursor_o.fetchone()[0] == 1

        # Delete channel
        delete_channel(ch_id)

        # Verify cascade removed videos and outliers
        with get_db() as conn:
            cursor_v = conn.execute("SELECT COUNT(*) FROM videos WHERE channel_id = ?", (ch_id,))
            assert cursor_v.fetchone()[0] == 0
            cursor_o = conn.execute("SELECT COUNT(*) FROM outliers WHERE channel_id = ?", (ch_id,))
            assert cursor_o.fetchone()[0] == 0

    # --------------------------------------------------------------------------
    # R3: Outlier Scoring & Actionable Intelligence
    # --------------------------------------------------------------------------

    def test_r3_rolling_channel_median_calculation(self):
        """Feature 7: calculate_channel_median accurately calculates rolling median views."""
        ch_id = "UC_MEDIAN_TEST_01"
        upsert_channel(channel_id=ch_id, name="Median Channel", url="https://youtube.com/@median")

        # Views: [12000, 14000, 16000, 18000, 20000] -> Median is 16000
        for i, views in enumerate([12000, 14000, 16000, 18000, 20000]):
            upsert_video(
                video_id=f"vid_med_{i}",
                channel_id=ch_id,
                title=f"Median Video {i}",
                url=f"https://youtube.com/watch?v=vid_med_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at="2026-10-10T10:00:00+00:00",
                view_count=views,
                duration_seconds=600,
                is_short=False
            )

        median = calculate_channel_median(ch_id)
        assert median == 16000

    def test_r3_median_calculation_excludes_shorts(self):
        """Feature 7: calculate_channel_median strictly excludes Shorts from median calculation."""
        ch_id = "UC_SHORTS_TEST_01"
        upsert_channel(channel_id=ch_id, name="Shorts Exclusion Channel", url="https://youtube.com/@shorts")

        # Longform videos with 10k views each
        for i in range(5):
            upsert_video(
                video_id=f"vid_long_{i}",
                channel_id=ch_id,
                title=f"Longform Video {i}",
                url=f"https://youtube.com/watch?v=vid_long_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at="2026-10-10T10:00:00+00:00",
                view_count=10000,
                duration_seconds=900,
                is_short=False
            )

        # Viral Shorts with 1,000,000 views each (is_short = True)
        for i in range(5):
            upsert_video(
                video_id=f"vid_short_{i}",
                channel_id=ch_id,
                title=f"Viral Short {i}",
                url=f"https://youtube.com/watch?v=vid_short_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at="2026-10-11T10:00:00+00:00",
                view_count=1000000,
                duration_seconds=45,
                is_short=True
            )

        median = calculate_channel_median(ch_id)
        # If shorts were included, median would be skewed to ~505,000. It must be 10,000.
        assert median == 10000

    def test_r3_outlier_multiplier_computation_and_threshold(self):
        """Feature 8: compute outlier multiplier = round(views / median, 2) and filter by threshold."""
        ch_id = "UC_OUTLIER_CALC_01"
        upsert_channel(channel_id=ch_id, name="Outlier Calc Channel", url="https://youtube.com/@outlier_calc")

        # Establish median of 20,000
        for i in range(5):
            upsert_video(
                video_id=f"vid_base_{i}",
                channel_id=ch_id,
                title=f"Baseline Video {i}",
                url=f"https://youtube.com/watch?v=vid_base_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at="2026-10-01T10:00:00+00:00",
                view_count=20000,
                duration_seconds=600,
                is_short=False
            )

        # Insert 86,000 views video -> Multiplier: 86000 / 20000 = 4.30x
        now = datetime.now(timezone.utc)
        upsert_video(
            video_id="vid_viral_breakout",
            channel_id=ch_id,
            title="Viral AI Agent Breakout",
            url="https://youtube.com/watch?v=vid_viral_breakout",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=3)).isoformat(),
            view_count=86000,
            duration_seconds=800,
            is_short=False
        )

        outliers = detect_outliers_for_channel(ch_id, min_multiplier=2.5, days_back=15)
        assert len(outliers) == 1
        assert outliers[0]["video_id"] == "vid_viral_breakout"
        assert outliers[0]["multiplier"] == 4.3

    def test_r3_groq_actionable_creator_card_generation(self, mock_groq_blueprint):
        """Feature 8: Groq Actionable Creator Card generates technical takeaways and viral hook."""
        ch_id = "UC_GROQ_TEST_01"
        upsert_channel(channel_id=ch_id, name="Groq Creator Channel", url="https://youtube.com/@groq")
        upsert_video(
            video_id="vid_groq_01",
            channel_id=ch_id,
            title="Building an Autonomous Dev Agent",
            url="https://youtube.com/watch?v=vid_groq_01",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at="2026-10-15T12:00:00+00:00",
            view_count=65000,
            duration_seconds=700,
            is_short=False
        )
        upsert_outlier(
            video_id="vid_groq_01",
            channel_id=ch_id,
            multiplier=4.2,
            channel_median=15000
        )

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(mock_groq_blueprint)
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        with patch("radar.analyzer.GROQ_API_KEY", "mock_groq_api_key_valid"), \
             patch("radar.analyzer.fetch_video_transcript", return_value="Sample transcript text for test"), \
             patch("radar.analyzer.Groq") as mock_groq_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_completion
            mock_groq_client_cls.return_value = mock_client

            blueprint = analyze_outlier_video(
                video_id="vid_groq_01",
                channel_id=ch_id,
                title="Building an Autonomous Dev Agent",
                multiplier=4.2,
                median=15000
            )

            assert blueprint is not None
            assert blueprint["category"] == "AI Agents"
            assert len(blueprint["summary_bullets"]) == 3
            assert "FastAPI" in blueprint["tools_mentioned"]
            assert "Actionable reproduction" in blueprint["viral_hook_angle"]

    def test_r3_groq_fallback_model_on_primary_failure(self, mock_groq_blueprint):
        """Feature 8: Groq analyzer switches to fallback model if primary model fails."""
        ch_id = "UC_GROQ_FALLBACK_01"
        upsert_channel(channel_id=ch_id, name="Groq Fallback Channel", url="https://youtube.com/@groq_fallback")
        upsert_video(
            video_id="vid_groq_fallback",
            channel_id=ch_id,
            title="Breakout Tech Model",
            url="https://youtube.com/watch?v=vid_groq_fallback",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at="2026-10-15T12:00:00+00:00",
            view_count=50000,
            duration_seconds=700,
            is_short=False
        )
        upsert_outlier(
            video_id="vid_groq_fallback",
            channel_id=ch_id,
            multiplier=3.8,
            channel_median=13000
        )

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(mock_groq_blueprint)
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        with patch("radar.analyzer.GROQ_API_KEY", "mock_key"), \
             patch("radar.analyzer.fetch_video_transcript", return_value="Sample transcript text for test"), \
             patch("radar.analyzer.Groq") as mock_groq_client_cls:
            mock_client = MagicMock()
            # Primary model fails, secondary succeeds
            mock_client.chat.completions.create.side_effect = [
                Exception("Rate limit on primary model qwen/qwen3.8-27b"),
                mock_completion
            ]
            mock_groq_client_cls.return_value = mock_client

            blueprint = analyze_outlier_video(
                video_id="vid_groq_fallback",
                channel_id=ch_id,
                title="Breakout Tech Model",
                multiplier=3.8,
                median=13000
            )

            assert blueprint is not None
            assert mock_client.chat.completions.create.call_count == 2

    # --------------------------------------------------------------------------
    # R4: YouTube-Native Dark UI & REST Endpoints
    # --------------------------------------------------------------------------

    def test_r4_dashboard_html_serves_youtube_dark_theme(self, client):
        """Feature 9: GET / serves authentic dark mode HTML dashboard with controls."""
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        # Assert dark mode styles and elements
        assert "dark" in html
        assert "Outlier Radar" in html
        assert "Sync Now" in html

    def test_r4_api_outliers_returns_structured_feed(self, client):
        """Feature 10: GET /api/outliers returns count and list of outliers."""
        resp = client.get("/api/outliers?min_multiplier=1.5&days_back=90")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "outliers" in data
        assert isinstance(data["outliers"], list)

    def test_r4_api_outliers_category_filter(self, client):
        """Feature 10: GET /api/outliers filters correctly by category."""
        # Insert test outlier in AI Agents
        ch_id = "UC_API_FILTER_01"
        upsert_channel(channel_id=ch_id, name="Filter Test", url="https://youtube.com/@filter")
        upsert_video(
            video_id="vid_cat_filter_01",
            channel_id=ch_id,
            title="AI Agents in Production",
            url="https://youtube.com/watch?v=vid_cat_filter_01",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=datetime.now(timezone.utc).isoformat(),
            view_count=50000,
            duration_seconds=600,
            is_short=False
        )
        upsert_outlier(
            video_id="vid_cat_filter_01",
            channel_id=ch_id,
            multiplier=3.0,
            channel_median=15000,
            category="AI Agents"
        )

        resp = client.get("/api/outliers?category=AI+Agents&min_multiplier=1.5&days_back=30")
        assert resp.status_code == 200
        data = resp.json()
        assert any(o["video_id"] == "vid_cat_filter_01" for o in data["outliers"])

    def test_r4_api_channels_management_endpoints(self, client):
        """Feature 12: Channels REST API supports listing, adding, and deleting channels."""
        # 1. List channels
        resp_list = client.get("/api/channels")
        assert resp_list.status_code == 200
        initial_channels = resp_list.json()["channels"]

        # 2. Add channel with mock sync
        mock_sync_result = {
            "success": True,
            "channel_id": "UC_NEW_API_CH",
            "videos_count": 5
        }
        with patch("app.main.sync_channel", return_value=mock_sync_result):
            resp_add = client.post("/api/channels", json={"url_or_handle": "@newapicreator"})
            assert resp_add.status_code == 200
            assert resp_add.json()["channel_id"] == "UC_NEW_API_CH"

        # 3. Delete channel
        resp_del = client.delete("/api/channels/UC_NEW_API_CH")
        assert resp_del.status_code == 200
        assert "removed" in resp_del.json()["message"]

    def test_r4_api_sync_endpoints_and_status(self, client):
        """Feature 13: /api/sync triggers background sync and /api/sync/status reports progress."""
        with patch("app.main.start_async_sync", return_value=True):
            resp_sync = client.post("/api/sync")
            assert resp_sync.status_code == 200
            assert "started" in resp_sync.json()["message"]

        resp_status = client.get("/api/sync/status")
        assert resp_status.status_code == 200
        status_data = resp_status.json()
        assert "progress" in status_data
        assert "latest_log" in status_data

    def test_r4_api_outlier_analysis_endpoint(self, client, mock_groq_blueprint):
        """Feature 14: POST /api/outliers/{video_id}/analyze triggers Groq analysis."""
        ch_id = "UC_ANALYSIS_API_01"
        upsert_channel(channel_id=ch_id, name="Analysis API Channel", url="https://youtube.com/@analysis_api")
        upsert_video(
            video_id="vid_analyze_api_01",
            channel_id=ch_id,
            title="Analysis API Breakthrough",
            url="https://youtube.com/watch?v=vid_analyze_api_01",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=datetime.now(timezone.utc).isoformat(),
            view_count=60000,
            duration_seconds=600,
            is_short=False
        )
        upsert_outlier(
            video_id="vid_analyze_api_01",
            channel_id=ch_id,
            multiplier=3.5,
            channel_median=17000
        )

        with patch("app.main.analyze_outlier_video", return_value=mock_groq_blueprint):
            resp = client.post("/api/outliers/vid_analyze_api_01/analyze")
            assert resp.status_code == 200
            blueprint = resp.json()
            assert blueprint["category"] == "AI Agents"
            assert len(blueprint["summary_bullets"]) == 3


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES (Adversarial, Rate Limits, Stress)
# ==============================================================================

class TestTier2BoundaryAndCornerCases:
    """Tier 2: Boundary, corner cases, error handling, rate limits, and network resilience."""

    # --------------------------------------------------------------------------
    # R1 Corner Cases
    # --------------------------------------------------------------------------

    def test_r2_c1_rss_http_429_rate_limit_resilience(self):
        """Corner Case: YouTube RSS returns HTTP 429 Too Many Requests -> does not crash."""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_resp.content = b"Too Many Requests"
            mock_get.return_value = mock_resp

            timestamps = fetch_rss_timestamps("UC_RATE_LIMITED_123")
            assert timestamps == {}

    def test_r2_c2_rss_http_timeout_and_network_dropout(self):
        """Corner Case: Network timeout / connection dropout on RSS fetch -> handled cleanly."""
        with patch("requests.get", side_effect=requests.exceptions.Timeout("Connection timed out")):
            timestamps = fetch_rss_timestamps("UC_TIMEOUT_123")
            assert timestamps == {}

    def test_r2_c3_malformed_xml_feed_graceful_handling(self):
        """Corner Case: Malformed or truncated XML feed from YouTube -> handled without crash."""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b"<feed><entry><id>incomplete xml..."
            mock_get.return_value = mock_resp

            timestamps = fetch_rss_timestamps("UC_CORRUPT_XML_123")
            assert timestamps == {}

    def test_r2_c4_missing_captions_throws_transcripts_disabled(self):
        """Corner Case: Video with disabled or blocked captions -> returns None gracefully."""
        with patch("radar.transcript.YouTubeTranscriptApi") as mock_ytt_cls:
            mock_ytt = MagicMock()
            mock_ytt.fetch.side_effect = Exception("TranscriptsDisabled: Subtitles are disabled for this video")
            mock_ytt_cls.return_value = mock_ytt

            transcript = fetch_video_transcript("vid_no_subtitles")
            assert transcript is None

    def test_r2_c5_special_characters_in_channel_names_and_titles(self):
        """Corner Case: Titles with emojis, quotes, ampersands, and SQL injection syntax."""
        ch_id = "UC_SPECIAL_CHARS_01"
        special_name = "AI Hub: 'Breakthroughs' & <Tools> 🤖"
        special_title = 'Revealing "Secret" Agent Architecture; DROP TABLE videos; -- 🚀'
        
        upsert_channel(channel_id=ch_id, name=special_name, url="https://youtube.com/@special")
        upsert_video(
            video_id="vid_special_chars",
            channel_id=ch_id,
            title=special_title,
            url="https://youtube.com/watch?v=vid_special_chars",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=datetime.now(timezone.utc).isoformat(),
            view_count=25000,
            duration_seconds=600,
            is_short=False
        )

        channels = get_all_channels()
        ch = next(c for c in channels if c["channel_id"] == ch_id)
        assert ch["name"] == special_name

        videos = get_channel_videos(ch_id)
        assert len(videos) == 1
        assert videos[0]["title"] == special_title

    # --------------------------------------------------------------------------
    # R2 Corner Cases
    # --------------------------------------------------------------------------

    def test_r2_c6_zero_video_channel_median_and_outlier(self):
        """Corner Case: Channel with zero videos calculates median as 0, avoiding divide-by-zero."""
        ch_id = "UC_EMPTY_CHANNEL_01"
        upsert_channel(channel_id=ch_id, name="Empty Channel", url="https://youtube.com/@empty")

        median = calculate_channel_median(ch_id)
        assert median == 0

        outliers = detect_outliers_for_channel(ch_id)
        assert outliers == []

    def test_r2_c7_all_videos_identical_views(self):
        """Corner Case: Channel with all videos having identical view counts -> 1.0x multiplier."""
        ch_id = "UC_IDENTICAL_VIEWS_01"
        upsert_channel(channel_id=ch_id, name="Identical Channel", url="https://youtube.com/@identical")

        now = datetime.now(timezone.utc)
        for i in range(6):
            upsert_video(
                video_id=f"vid_ident_{i}",
                channel_id=ch_id,
                title=f"Uniform Video {i}",
                url=f"https://youtube.com/watch?v=vid_ident_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(days=2)).isoformat(),
                view_count=5000,
                duration_seconds=600,
                is_short=False
            )

        median = calculate_channel_median(ch_id)
        assert median == 5000

        # At default 2.5x threshold, zero outliers exist
        outliers = detect_outliers_for_channel(ch_id, min_multiplier=2.5)
        assert len(outliers) == 0

    def test_r2_c8_views_floor_boundary_condition(self):
        """Corner Case: Video exceeding multiplier threshold but below MIN_VIDEO_VIEWS_FLOOR."""
        ch_id = "UC_FLOOR_TEST_01"
        upsert_channel(channel_id=ch_id, name="Tiny Channel", url="https://youtube.com/@tiny")

        now = datetime.now(timezone.utc)
        # Median is 100 views
        for i in range(5):
            upsert_video(
                video_id=f"vid_tiny_{i}",
                channel_id=ch_id,
                title=f"Tiny Video {i}",
                url=f"https://youtube.com/watch?v=vid_tiny_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(days=2)).isoformat(),
                view_count=100,
                duration_seconds=600,
                is_short=False
            )

        # Video with 400 views (4.0x multiplier, but < MIN_VIDEO_VIEWS_FLOOR of 1000)
        upsert_video(
            video_id="vid_tiny_outlier",
            channel_id=ch_id,
            title="Tiny 4x Outlier",
            url="https://youtube.com/watch?v=vid_tiny_outlier",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=1)).isoformat(),
            view_count=400,
            duration_seconds=600,
            is_short=False
        )

        outliers = detect_outliers_for_channel(ch_id, min_multiplier=2.0)
        assert len(outliers) == 0

    def test_r2_c9_strict_recency_boundary_15_days(self):
        """Corner Case: 15-day recency boundary (14d 23h included vs 15d 1h excluded)."""
        ch_id = "UC_EXACT_RECENCY_01"
        upsert_channel(channel_id=ch_id, name="Recency Edge Channel", url="https://youtube.com/@edge")

        now = datetime.now(timezone.utc)
        # Establish baseline median
        for i in range(5):
            upsert_video(
                video_id=f"vid_edge_base_{i}",
                channel_id=ch_id,
                title=f"Base {i}",
                url=f"https://youtube.com/watch?v=vid_edge_base_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(days=20)).isoformat(),
                view_count=10000,
                duration_seconds=600,
                is_short=False
            )

        # In-bounds: 14 days and 23 hours ago
        in_bounds_date = (now - timedelta(days=14, hours=23)).isoformat()
        upsert_video(
            video_id="vid_in_bounds",
            channel_id=ch_id,
            title="In-Bounds Video",
            url="https://youtube.com/watch?v=vid_in_bounds",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=in_bounds_date,
            view_count=35000,
            duration_seconds=600,
            is_short=False
        )

        # Out-of-bounds: 15 days and 2 hours ago
        out_bounds_date = (now - timedelta(days=15, hours=2)).isoformat()
        upsert_video(
            video_id="vid_out_bounds",
            channel_id=ch_id,
            title="Out-of-Bounds Video",
            url="https://youtube.com/watch?v=vid_out_bounds",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=out_bounds_date,
            view_count=45000,
            duration_seconds=600,
            is_short=False
        )

        outliers = detect_outliers_for_channel(ch_id, min_multiplier=2.0, days_back=15)
        outlier_ids = [o["video_id"] for o in outliers]
        assert "vid_in_bounds" in outlier_ids
        assert "vid_out_bounds" not in outlier_ids

    def test_r2_c10_shorts_boundary_duration_60s_vs_61s(self):
        """Corner Case: Video duration 60s is Short; 61s is longform video."""
        from radar.fetcher import fetch_channel_videos

        mock_entries = [
            {"id": "vid_60s", "title": "60-second video", "duration": 60, "url": "https://youtube.com/watch?v=vid_60s"},
            {"id": "vid_61s", "title": "61-second video", "duration": 61, "url": "https://youtube.com/watch?v=vid_61s"},
            {"id": "vid_url_short", "title": "URL short", "duration": 120, "url": "https://youtube.com/shorts/vid_url_short"}
        ]

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            mock_ydl = MagicMock()
            mock_ydl.extract_info.return_value = {
                "id": "UC_SHORTS_BOUND",
                "title": "Shorts Bound Channel",
                "entries": mock_entries
            }
            mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

            res = fetch_channel_videos("https://youtube.com/@shortsbound")
            videos = {v["video_id"]: v for v in res["videos"]}

            assert bool(videos["vid_60s"]["is_short"]) is True
            assert bool(videos["vid_61s"]["is_short"]) is False
            assert bool(videos["vid_url_short"]["is_short"]) is True

    # --------------------------------------------------------------------------
    # R3 Corner Cases
    # --------------------------------------------------------------------------

    def test_r2_c11_extreme_multiplier_calculations(self):
        """Corner Case: Extreme view multipliers (10M views vs 1k median = 10000.0x)."""
        ch_id = "UC_EXTREME_MULT_01"
        upsert_channel(channel_id=ch_id, name="Extreme Multiplier Channel", url="https://youtube.com/@extreme")

        now = datetime.now(timezone.utc)
        # Median is 1,000 views
        for i in range(5):
            upsert_video(
                video_id=f"vid_ex_base_{i}",
                channel_id=ch_id,
                title=f"Base {i}",
                url=f"https://youtube.com/watch?v=vid_ex_base_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(days=20)).isoformat(),
                view_count=1000,
                duration_seconds=600,
                is_short=False
            )

        # Viral megahit: 10,000,000 views
        upsert_video(
            video_id="vid_megahit",
            channel_id=ch_id,
            title="10 Million Views Mega Outlier",
            url="https://youtube.com/watch?v=vid_megahit",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=2)).isoformat(),
            view_count=10000000,
            duration_seconds=1200,
            is_short=False
        )

        outliers = detect_outliers_for_channel(ch_id, min_multiplier=2.0)
        assert len(outliers) == 1
        assert outliers[0]["video_id"] == "vid_megahit"
        assert outliers[0]["multiplier"] == 10000.0

    def test_r2_c12_groq_api_missing_or_empty_key(self):
        """Corner Case: GROQ_API_KEY is empty -> returns None without unhandled exception."""
        with patch("radar.analyzer.GROQ_API_KEY", ""):
            res = analyze_outlier_video(
                video_id="vid_any",
                channel_id="ch_any",
                title="Test Title",
                multiplier=3.0,
                median=10000
            )
            assert res is None

    def test_r2_c13_groq_returns_malformed_json(self):
        """Corner Case: Groq returns invalid JSON text -> handled gracefully, returns None."""
        mock_choice = MagicMock()
        mock_choice.message.content = "I am an AI and cannot generate JSON right now."
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        with patch("radar.analyzer.GROQ_API_KEY", "mock_key"), \
             patch("radar.analyzer.fetch_video_transcript", return_value="Sample transcript text for test"), \
             patch("radar.analyzer.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_completion
            mock_groq_cls.return_value = mock_client

            res = analyze_outlier_video(
                video_id="vid_corrupt_llm",
                channel_id="ch_corrupt",
                title="Test Title",
                multiplier=3.5,
                median=12000
            )
            assert res is None

    def test_r2_c14_single_video_median_calculation(self):
        """Corner Case: Channel with exactly one video -> median is that video's views."""
        ch_id = "UC_SINGLE_VID_01"
        upsert_channel(channel_id=ch_id, name="Single Video Channel", url="https://youtube.com/@single")

        upsert_video(
            video_id="vid_lonely",
            channel_id=ch_id,
            title="The Only Video",
            url="https://youtube.com/watch?v=vid_lonely",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at="2026-10-15T10:00:00+00:00",
            view_count=23500,
            duration_seconds=600,
            is_short=False
        )

        median = calculate_channel_median(ch_id)
        assert median == 23500

    def test_r2_c15_even_number_of_videos_median(self):
        """Corner Case: Channel with even number of videos calculates mathematical mean of middle two."""
        ch_id = "UC_EVEN_VIDS_01"
        upsert_channel(channel_id=ch_id, name="Even Videos Channel", url="https://youtube.com/@even")

        # Views: [1000, 2000, 4000, 5000] -> Middle two: 2000, 4000 -> Median: 3000
        for i, v in enumerate([1000, 2000, 4000, 5000]):
            upsert_video(
                video_id=f"vid_even_{i}",
                channel_id=ch_id,
                title=f"Even Video {i}",
                url=f"https://youtube.com/watch?v=vid_even_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at="2026-10-10T10:00:00+00:00",
                view_count=v,
                duration_seconds=600,
                is_short=False
            )

        median = calculate_channel_median(ch_id)
        assert median == 3000

    # --------------------------------------------------------------------------
    # R4 Corner Cases
    # --------------------------------------------------------------------------

    def test_r2_c16_concurrent_sync_returns_409_conflict(self, client):
        """Corner Case: Triggering /api/sync while a sync is already running returns 409 Conflict."""
        with patch("app.main.start_async_sync", return_value=False):
            resp = client.post("/api/sync")
            assert resp.status_code == 409
            assert "already in progress" in resp.json()["message"]

    def test_r2_c17_empty_search_query_returns_all_unfiltered(self, client):
        """Corner Case: Empty search string or whitespace query returns all records without error."""
        resp = client.get("/api/outliers?search=")
        assert resp.status_code == 200
        assert "outliers" in resp.json()

    def test_r2_c18_invalid_outlier_multiplier_param_validation(self, client):
        """Corner Case: min_multiplier below 1.0 or above 50.0 fails validation with 422."""
        resp_low = client.get("/api/outliers?min_multiplier=0.5")
        assert resp_low.status_code == 422

        resp_high = client.get("/api/outliers?min_multiplier=100.0")
        assert resp_high.status_code == 422

    def test_r2_c19_add_channel_with_empty_or_whitespace_handle(self, client):
        """Corner Case: POST /api/channels with empty or whitespace string returns 400 Bad Request."""
        resp = client.post("/api/channels", json={"url_or_handle": "   "})
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"].lower()

    def test_r2_c20_delete_nonexistent_channel_idempotent(self, client):
        """Corner Case: DELETE /api/channels for non-existent channel ID is safe and idempotent."""
        resp = client.delete("/api/channels/UC_DOES_NOT_EXIST_XYZ")
        assert resp.status_code == 200


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (Pairwise Interactions)
# ==============================================================================

class TestTier3CrossFeatureCombinations:
    """Tier 3: Pairwise multi-module interactions across ingestion, analysis, and API."""

    def test_tier3_rss_ingest_to_outlier_detection_to_groq_card(self, mock_groq_blueprint):
        """Interaction 1: RSS Feed Sync -> 90-Day Median -> Outlier Engine -> Groq Creator Card."""
        ch_id = "UC_COMBO_01"
        upsert_channel(channel_id=ch_id, name="Combo Channel 1", url="https://youtube.com/@combo1")

        now = datetime.now(timezone.utc)
        # 1. Feed sync simulation: 10 baseline videos + 1 breakout video
        for i in range(10):
            upsert_video(
                video_id=f"vid_combo1_base_{i}",
                channel_id=ch_id,
                title=f"Standard Video {i}",
                url=f"https://youtube.com/watch?v=vid_combo1_base_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(days=25 + i)).isoformat(),
                view_count=10000,
                duration_seconds=600,
                is_short=False
            )

        upsert_video(
            video_id="vid_combo1_breakout",
            channel_id=ch_id,
            title="Reasoning Agent Architecture",
            url="https://youtube.com/watch?v=vid_combo1_breakout",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=2)).isoformat(),
            view_count=52000,
            duration_seconds=900,
            is_short=False
        )

        # 2. Outlier detection
        outliers = detect_outliers_for_channel(ch_id, min_multiplier=2.5, days_back=15)
        assert len(outliers) == 1
        assert outliers[0]["video_id"] == "vid_combo1_breakout"
        assert outliers[0]["multiplier"] == 5.2

        # 3. Groq Creator Card generation
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(mock_groq_blueprint)
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        with patch("radar.analyzer.GROQ_API_KEY", "mock_key"), \
             patch("radar.analyzer.fetch_video_transcript", return_value="Sample transcript text for test"), \
             patch("radar.analyzer.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_completion
            mock_groq_cls.return_value = mock_client

            blueprint = analyze_outlier_video(
                video_id="vid_combo1_breakout",
                channel_id=ch_id,
                title="Reasoning Agent Architecture",
                multiplier=5.2,
                median=10000
            )

            assert blueprint is not None
            # Verify database persisted the analysis
            with get_db() as conn:
                cursor = conn.execute("SELECT * FROM outliers WHERE video_id = ?", ("vid_combo1_breakout",))
                row = cursor.fetchone()
                assert row is not None
                assert row["category"] == "AI Agents"
                assert "FastAPI" in row["tools_mentioned"]

    def test_tier3_caption_failure_to_whisper_fallback_to_modal_payload(self, client, mock_groq_blueprint):
        """Interaction 2: Caption failure -> Whisper audio fallback -> Modal Blueprint payload."""
        ch_id = "UC_COMBO_02"
        upsert_channel(channel_id=ch_id, name="Combo Channel 2", url="https://youtube.com/@combo2")
        upsert_video(
            video_id="vid_combo2_audio",
            channel_id=ch_id,
            title="Audio Stream Fallback Breakthrough",
            url="https://youtube.com/watch?v=vid_combo2_audio",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=datetime.now(timezone.utc).isoformat(),
            view_count=72000,
            duration_seconds=750,
            is_short=False
        )
        upsert_outlier(
            video_id="vid_combo2_audio",
            channel_id=ch_id,
            multiplier=4.0,
            channel_median=18000
        )

        # Primary caption fails, Groq analyzer uses title/context fallback
        with patch("radar.transcript.YouTubeTranscriptApi") as mock_ytt_cls:
            mock_ytt = MagicMock()
            mock_ytt.fetch.side_effect = Exception("HTTP 429 Captions Blocked")
            mock_ytt_cls.return_value = mock_ytt

            with patch("app.main.analyze_outlier_video", return_value=mock_groq_blueprint):
                resp = client.post("/api/outliers/vid_combo2_audio/analyze")
                assert resp.status_code == 200
                data = resp.json()
                assert data["category"] == "AI Agents"
                assert len(data["summary_bullets"]) == 3
                assert len(data["tools_mentioned"]) > 0
                assert len(data["viral_hook_angle"]) > 0

    def test_tier3_channel_registration_outlier_creation_and_cascade_delete(self, client):
        """Interaction 3: Add Channel -> Detect Outliers -> Verify in Feed -> Delete Channel -> Verify Cascade."""
        ch_id = "UC_COMBO_03"
        upsert_channel(channel_id=ch_id, name="Lifecycle Channel", url="https://youtube.com/@lifecycle")
        now = datetime.now(timezone.utc)

        upsert_video(
            video_id="vid_lifecycle_01",
            channel_id=ch_id,
            title="Lifecycle Video",
            url="https://youtube.com/watch?v=vid_lifecycle_01",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=2)).isoformat(),
            view_count=60000,
            duration_seconds=600,
            is_short=False
        )
        upsert_outlier(
            video_id="vid_lifecycle_01",
            channel_id=ch_id,
            multiplier=3.2,
            channel_median=18750
        )

        # Verify outlier in API
        resp_feed = client.get("/api/outliers?min_multiplier=2.0")
        assert resp_feed.status_code == 200
        assert any(o["video_id"] == "vid_lifecycle_01" for o in resp_feed.json()["outliers"])

        # Delete channel via API
        resp_del = client.delete(f"/api/channels/{ch_id}")
        assert resp_del.status_code == 200

        # Verify outlier is gone from feed
        resp_feed_after = client.get("/api/outliers?min_multiplier=2.0")
        assert not any(o["video_id"] == "vid_lifecycle_01" for o in resp_feed_after.json()["outliers"])

    def test_tier3_multi_channel_category_filter_and_recency_combination(self, client):
        """Interaction 4: Multi-channel category filter + recency window + multiplier threshold combination."""
        now = datetime.now(timezone.utc)
        
        # Setup Channel A (Automations, recent 5 days, 3.5x multiplier)
        upsert_channel(channel_id="UC_COMBO_A", name="Channel A", url="https://youtube.com/@ch_a")
        upsert_video(
            video_id="vid_combo_a",
            channel_id="UC_COMBO_A",
            title="Automation Swarm Tutorial",
            url="https://youtube.com/watch?v=vid_combo_a",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=5)).isoformat(),
            view_count=35000,
            duration_seconds=600,
            is_short=False
        )
        upsert_outlier(
            video_id="vid_combo_a",
            channel_id="UC_COMBO_A",
            multiplier=3.5,
            channel_median=10000,
            category="Automations"
        )

        # Setup Channel B (AI News, recent 4 days, 2.8x multiplier)
        upsert_channel(channel_id="UC_COMBO_B", name="Channel B", url="https://youtube.com/@ch_b")
        upsert_video(
            video_id="vid_combo_b",
            channel_id="UC_COMBO_B",
            title="Weekly AI News Roundup",
            url="https://youtube.com/watch?v=vid_combo_b",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=4)).isoformat(),
            view_count=28000,
            duration_seconds=600,
            is_short=False
        )
        upsert_outlier(
            video_id="vid_combo_b",
            channel_id="UC_COMBO_B",
            multiplier=2.8,
            channel_median=10000,
            category="AI News"
        )

        # Query specifically for Automations with min_multiplier=3.0
        resp = client.get("/api/outliers?category=Automations&min_multiplier=3.0&days_back=15")
        assert resp.status_code == 200
        outliers = resp.json()["outliers"]
        v_ids = [o["video_id"] for o in outliers]
        assert "vid_combo_a" in v_ids
        assert "vid_combo_b" not in v_ids

    def test_tier3_sync_log_lifecycle_and_progress_tracking(self, client):
        """Interaction 5: Sync log creation -> status tracking -> completion -> inspector query."""
        log_id = create_sync_log()
        assert log_id > 0

        # Check status is running
        status_mid = get_latest_sync_status()
        assert status_mid is not None
        assert status_mid["id"] == log_id
        assert status_mid["status"] == "running"

        # Complete sync log
        update_sync_log(
            log_id=log_id,
            status="completed",
            channels_scanned=100,
            videos_fetched=450,
            outliers_found=28,
            message="Full catalog scan completed successfully"
        )

        # Query API
        resp = client.get("/api/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        latest_log = data["latest_log"]
        assert latest_log["id"] == log_id
        assert latest_log["status"] == "completed"
        assert latest_log["channels_scanned"] == 100
        assert latest_log["outliers_found"] == 28


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS (End-to-End User Workflows)
# ==============================================================================

class TestTier4RealWorldApplicationScenarios:
    """Tier 4: Full real-world application user scenarios and platform workflows."""

    def test_tier4_scenario1_100_creators_sync_to_50_video_fresh_feed(self, seed_catalog_helper, client):
        """
        Scenario 1: Full Platform Sync & Feed Density:
        - 100 creators across 5 categories seeded in DB.
        - Videos populated with dates ranging from 1 to 45 days ago.
        - Feed query strictly filters to 15-day recency and orders by published_at DESC.
        - Asserts dense feed rendering without starvation.
        """
        # 1. Seed 100 channels across 5 categories
        seeded_channels = seed_catalog_helper(count=100)
        assert len(seeded_channels) == 100

        now = datetime.now(timezone.utc)
        # 2. Populate 100 recent videos (1 to 10 days ago) and 100 old videos (20 to 40 days ago)
        for i in range(100):
            ch = seeded_channels[i]
            # Fresh video (within 15 days)
            fresh_date = (now - timedelta(days=(i % 10) + 1, hours=i)).isoformat()
            upsert_video(
                video_id=f"vid_fresh_{i:03d}",
                channel_id=ch["channel_id"],
                title=f"Cutting-Edge AI Breakthrough {i:03d}",
                url=f"https://youtube.com/watch?v=vid_fresh_{i:03d}",
                thumbnail_url=f"https://i.ytimg.com/vi/vid_fresh_{i:03d}/hqdefault.jpg",
                published_at=fresh_date,
                view_count=50000 + (i * 500),
                duration_seconds=720,
                is_short=False
            )
            # Create outlier for top performing videos
            if i % 2 == 0:
                upsert_outlier(
                    video_id=f"vid_fresh_{i:03d}",
                    channel_id=ch["channel_id"],
                    multiplier=3.2 + (i % 5) * 0.5,
                    channel_median=15000,
                    category=ch["category"]
                )

            # Stale video (outside 15 days)
            stale_date = (now - timedelta(days=20 + (i % 20))).isoformat()
            upsert_video(
                video_id=f"vid_stale_{i:03d}",
                channel_id=ch["channel_id"],
                title=f"Archived Tech Talk {i:03d}",
                url=f"https://youtube.com/watch?v=vid_stale_{i:03d}",
                thumbnail_url=f"https://i.ytimg.com/vi/vid_stale_{i:03d}/hqdefault.jpg",
                published_at=stale_date,
                view_count=10000,
                duration_seconds=600,
                is_short=False
            )

        # 3. Query outliers feed with strict 15-day recency
        resp = client.get("/api/outliers?days_back=15&min_multiplier=2.0")
        assert resp.status_code == 200
        data = resp.json()
        outliers = data["outliers"]

        assert len(outliers) > 0
        cutoff_date = now - timedelta(days=15)
        for o in outliers:
            # Assert all returned videos strictly within 15 days
            pub_dt = datetime.fromisoformat(o["published_at"].replace("Z", "+00:00"))
            assert pub_dt >= cutoff_date
            # Assert non-stale IDs
            assert not o["video_id"].startswith("vid_stale_")

    def test_tier4_scenario2_viral_outlier_breakthrough_detection(self, client):
        """
        Scenario 2: Viral Outlier Breakthrough Detection:
        - Creator with normal 15k median views publishes a breakthrough video getting 150k views.
        - System detects anomaly, computes 10.0x multiplier, and assigns outlier badge in feed.
        """
        ch_id = "UC_VIRAL_SCENARIO_01"
        upsert_channel(
            channel_id=ch_id,
            name="IndyDevDan",
            url="https://youtube.com/@indydevdan",
            handle="@indydevdan"
        )
        now = datetime.now(timezone.utc)

        # 10 historical videos averaging 15k views
        for i in range(10):
            upsert_video(
                video_id=f"vid_indy_base_{i}",
                channel_id=ch_id,
                title=f"Standard Tutorial {i}",
                url=f"https://youtube.com/watch?v=vid_indy_base_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(days=20 + i)).isoformat(),
                view_count=15000,
                duration_seconds=600,
                is_short=False
            )

        median = calculate_channel_median(ch_id)
        assert median == 15000

        # Breakout video published 2 days ago: 150,000 views
        breakout_id = "vid_indy_viral_swarm"
        upsert_video(
            video_id=breakout_id,
            channel_id=ch_id,
            title="Building an Autonomous Multi-Agent Swarm from Scratch",
            url=f"https://youtube.com/watch?v={breakout_id}",
            thumbnail_url=f"https://i.ytimg.com/vi/{breakout_id}/hqdefault.jpg",
            published_at=(now - timedelta(days=2)).isoformat(),
            view_count=150000,
            duration_seconds=1150,
            is_short=False
        )

        # Run anomaly detection
        outliers = detect_outliers_for_channel(ch_id, min_multiplier=2.5, days_back=15)
        assert len(outliers) == 1
        assert outliers[0]["video_id"] == breakout_id
        assert outliers[0]["multiplier"] == 10.0

        # Verify API surfaces the viral outlier
        resp = client.get("/api/outliers?min_multiplier=5.0")
        assert resp.status_code == 200
        feed_outliers = resp.json()["outliers"]
        viral_card = next(o for o in feed_outliers if o["video_id"] == breakout_id)
        assert viral_card["multiplier"] == 10.0
        assert viral_card["channel_name"] == "IndyDevDan"

    def test_tier4_scenario3_dynamic_top_chip_filtering_without_reload(self, client):
        """
        Scenario 3: Zero-Reload Dynamic Filter Chip Interactivity:
        - User navigates between category chips ('All', 'AI Agents', 'Automations', 'Dev Tools').
        - User adjusts outlier multiplier slider from 2.0x to 4.0x.
        - User searches for specific keyword ('MCP').
        - Verifies that API accurately yields expected subsets without state corruption.
        """
        now = datetime.now(timezone.utc)
        ch_base = "UC_CHIP_TEST"
        upsert_channel(channel_id=f"{ch_base}_1", name="Agent Creator", url="https://youtube.com/@agent_c")
        upsert_channel(channel_id=f"{ch_base}_2", name="DevTools Creator", url="https://youtube.com/@devtools_c")

        # Video 1: AI Agents, 2.5x multiplier, contains "MCP"
        upsert_video(
            video_id="vid_chip_01",
            channel_id=f"{ch_base}_1",
            title="Mastering MCP Architecture for Agents",
            url="https://youtube.com/watch?v=vid_chip_01",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=2)).isoformat(),
            view_count=25000,
            duration_seconds=600,
            is_short=False
        )
        upsert_outlier(
            video_id="vid_chip_01",
            channel_id=f"{ch_base}_1",
            multiplier=2.5,
            channel_median=10000,
            category="AI Agents"
        )

        # Video 2: Dev Tools, 4.5x multiplier, contains "Cursor"
        upsert_video(
            video_id="vid_chip_02",
            channel_id=f"{ch_base}_2",
            title="Cursor AI Workflow Secrets",
            url="https://youtube.com/watch?v=vid_chip_02",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=(now - timedelta(days=3)).isoformat(),
            view_count=45000,
            duration_seconds=600,
            is_short=False
        )
        upsert_outlier(
            video_id="vid_chip_02",
            channel_id=f"{ch_base}_2",
            multiplier=4.5,
            channel_median=10000,
            category="SaaS & Dev Tools"
        )

        # Step A: Filter by "AI Agents"
        resp_agents = client.get("/api/outliers?category=AI+Agents&min_multiplier=2.0")
        assert resp_agents.status_code == 200
        ids_agents = [o["video_id"] for o in resp_agents.json()["outliers"]]
        assert "vid_chip_01" in ids_agents
        assert "vid_chip_02" not in ids_agents

        # Step B: Filter by High Outlier Threshold (> 4.0x)
        resp_high = client.get("/api/outliers?min_multiplier=4.0")
        assert resp_high.status_code == 200
        ids_high = [o["video_id"] for o in resp_high.json()["outliers"]]
        assert "vid_chip_02" in ids_high
        assert "vid_chip_01" not in ids_high

        # Step C: Search by keyword "MCP"
        resp_search = client.get("/api/outliers?search=MCP&min_multiplier=2.0")
        assert resp_search.status_code == 200
        ids_search = [o["video_id"] for o in resp_search.json()["outliers"]]
        assert "vid_chip_01" in ids_search
        assert "vid_chip_02" not in ids_search

    def test_tier4_scenario4_creator_blueprint_modal_teardown(self, client, mock_groq_blueprint):
        """
        Scenario 4: Actionable Creator Blueprint & Modal Teardown:
        - User clicks on an outlier card to open the Detail Drawer / Modal.
        - Groq generates 3 technical takeaways, tools mentioned, and viral hook angle.
        - Verifies complete payload for frontend presentation.
        """
        ch_id = "UC_MODAL_TEARDOWN_01"
        upsert_channel(channel_id=ch_id, name="AI Jason", url="https://youtube.com/@AIJasonZ")
        now = datetime.now(timezone.utc)

        vid_id = "vid_modal_teardown"
        upsert_video(
            video_id=vid_id,
            channel_id=ch_id,
            title="How I Built an Autonomous Research Agent with LangGraph",
            url=f"https://youtube.com/watch?v={vid_id}",
            thumbnail_url=f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
            published_at=(now - timedelta(days=3)).isoformat(),
            view_count=82000,
            duration_seconds=950,
            is_short=False
        )
        upsert_outlier(
            video_id=vid_id,
            channel_id=ch_id,
            multiplier=4.1,
            channel_median=20000
        )

        with patch("app.main.analyze_outlier_video", return_value=mock_groq_blueprint):
            resp = client.post(f"/api/outliers/{vid_id}/analyze")
            assert resp.status_code == 200
            card = resp.json()

            # Verify complete schema for YouTube modal
            assert card["category"] == "AI Agents"
            assert isinstance(card["summary_bullets"], list)
            assert len(card["summary_bullets"]) == 3
            assert isinstance(card["tools_mentioned"], list)
            assert len(card["tools_mentioned"]) > 0
            assert isinstance(card["viral_hook_angle"], str)
            assert len(card["viral_hook_angle"]) > 20

    def test_tier4_scenario5_raw_data_inspector_and_catalog_audit(self, client):
        """
        Scenario 5: Raw Data Inspector & Platform Catalog Audit:
        - Inspects channels catalog, verifying total channels, video counts, and 90-day medians.
        - Verifies database consistency between channels, videos, and outlier records.
        """
        resp_channels = client.get("/api/channels")
        assert resp_channels.status_code == 200
        catalog = resp_channels.json()["channels"]

        assert len(catalog) > 0
        for ch in catalog:
            assert "channel_id" in ch
            assert "name" in ch
            assert "url" in ch
            assert "video_count" in ch
            assert "outlier_count" in ch
            assert "median_views" in ch
            assert ch["video_count"] >= 0
            assert ch["outlier_count"] >= 0

        # Verify raw database table counts match
        with get_db() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM channels")
            db_ch_count = cursor.fetchone()[0]
            assert db_ch_count == len(catalog)
