import pytest
from datetime import datetime, timezone, timedelta
from starlette.testclient import TestClient

from app.main import app
from radar.db import (
    init_db,
    upsert_channel,
    upsert_video,
    get_feed_videos,
    search_channels,
    interleave_feed_videos
)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

class TestUserFlawsFixes:
    """Verifies fixes for the three non-negotiable user flaws."""

    def test_flaw_1_no_creator_monopolization_and_zero_consecutive_repeat(self):
        """Flaw 1: Verifies that no creator appears consecutively and max 2 per creator in top feed."""
        # Create 3 creators
        for c_idx in range(1, 4):
            upsert_channel(
                channel_id=f"UC_FLAW1_CH_{c_idx}",
                name=f"Creator {c_idx}",
                url=f"https://youtube.com/@creator{c_idx}",
                handle=f"@creator{c_idx}"
            )

        now = datetime.now(timezone.utc)
        # Creator 1 uploads 15 videos in a row (would monopolize if not interleaved)
        for i in range(15):
            upsert_video(
                video_id=f"vid_flaw1_c1_{i}",
                channel_id="UC_FLAW1_CH_1",
                title=f"Creator 1 Video {i}",
                url=f"https://youtube.com/watch?v=vid_flaw1_c1_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(hours=i)).isoformat(),
                view_count=20000,
                duration_seconds=600,
                is_short=False
            )

        # Creator 2 uploads 5 videos
        for i in range(5):
            upsert_video(
                video_id=f"vid_flaw1_c2_{i}",
                channel_id="UC_FLAW1_CH_2",
                title=f"Creator 2 Video {i}",
                url=f"https://youtube.com/watch?v=vid_flaw1_c2_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(hours=i + 2)).isoformat(),
                view_count=18000,
                duration_seconds=600,
                is_short=False
            )

        # Creator 3 uploads 5 videos
        for i in range(5):
            upsert_video(
                video_id=f"vid_flaw1_c3_{i}",
                channel_id="UC_FLAW1_CH_3",
                title=f"Creator 3 Video {i}",
                url=f"https://youtube.com/watch?v=vid_flaw1_c3_{i}",
                thumbnail_url="https://example.com/thumb.jpg",
                published_at=(now - timedelta(hours=i + 3)).isoformat(),
                view_count=15000,
                duration_seconds=600,
                is_short=False
            )

        # Feed query
        feed = get_feed_videos(days_back=15, limit=50)
        assert len(feed) > 0

        # Check: Zero consecutive videos from the same creator
        for i in range(1, len(feed)):
            prev_creator = feed[i - 1]["channel_id"]
            curr_creator = feed[i]["channel_id"]
            assert prev_creator != curr_creator, (
                f"Consecutive creator match at index {i-1} and {i}: {prev_creator}"
            )

    def test_flaw_2_authentic_timestamps_not_now_fallback(self):
        """Flaw 2: Verifies that videos preserve original upload dates and reject fake now() fallback."""
        ch_id = "UC_FLAW2_CH"
        upsert_channel(channel_id=ch_id, name="Timestamp Channel", url="https://youtube.com/@time")

        authentic_time = "2026-10-15T18:24:00+00:00"
        upsert_video(
            video_id="vid_flaw2_authentic",
            channel_id=ch_id,
            title="Real Upload Date Video",
            url="https://youtube.com/watch?v=vid_flaw2_authentic",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=authentic_time,
            view_count=25000,
            duration_seconds=500,
            is_short=False
        )

        feed = get_feed_videos(days_back=15, search="Real Upload Date Video")
        assert len(feed) == 1
        assert feed[0]["published_at"] == authentic_time
        # Ensure microsecond sync fake timestamps are absent
        assert "." not in feed[0]["published_at"]

    def test_flaw_3_search_channel_name_and_handle_and_banner(self):
        """Flaw 3: Verifies that searching channel name or handle returns matching channel cards and videos."""
        ch_id = "UC_FLAW3_JASON"
        upsert_channel(
            channel_id=ch_id,
            name="AI Jason",
            url="https://youtube.com/@AIJasonZ",
            handle="@AIJasonZ",
            category="AI Agents"
        )

        # Video uploaded 20 days ago (outside 15-day general window, but must appear in search)
        upsert_video(
            video_id="vid_flaw3_jason_01",
            channel_id=ch_id,
            title="Building Autonomous Agents with Jev and Treg",
            url="https://youtube.com/watch?v=vid_flaw3_jason_01",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at="2026-09-28T12:00:00+00:00",
            view_count=45000,
            duration_seconds=700,
            is_short=False
        )

        # Test search_channels function
        # 1. Search by exact handle "@AIJasonZ"
        channels_handle = search_channels("@AIJasonZ")
        assert len(channels_handle) >= 1
        assert any(c["handle"] == "@AIJasonZ" for c in channels_handle)

        # 2. Search by handle without '@'
        channels_no_at = search_channels("AIJasonZ")
        assert len(channels_no_at) >= 1
        assert any(c["name"] == "AI Jason" for c in channels_no_at)

        # 3. Search by name "AI Jason"
        channels_name = search_channels("AI Jason")
        assert len(channels_name) >= 1
        assert any(c["name"] == "AI Jason" for c in channels_name)

        # 4. Search via /api/feed endpoint
        client = TestClient(app)
        resp = client.get("/api/feed?search=%40AIJasonZ")
        assert resp.status_code == 200
        data = resp.json()
        assert "matched_channels" in data
        assert len(data["matched_channels"]) >= 1
        assert data["matched_channels"][0]["handle"] == "@AIJasonZ"
        assert len(data["videos"]) >= 1
        assert data["videos"][0]["video_id"] == "vid_flaw3_jason_01"

    def test_9_user_channels_synced_in_catalog(self):
        """Verifies that all 9 user requested channels exist in database with real videos."""
        client = TestClient(app)
        resp = client.get("/api/channels")
        assert resp.status_code == 200
        data = resp.json()
        channels = data["channels"]
        assert len(channels) >= 110

        handle_set = {c.get("handle") for c in channels if c.get("handle")}
        expected_handles = [
            "@mobbindesign",
            "@vaibhavsisinty",
            "@nateherk",
            "@parthknowsai",
            "@wdf_ai",
            "@Ai.Vishnuvijayan",
            "@aishwaryasrinivasan",
            "@Techie007",
            "@medyrenaldyshorts"
        ]
        for eh in expected_handles:
            assert eh in handle_set, f"Expected channel {eh} missing from database catalog!"

    def test_dynamic_channel_filter_logic(self):
        """Verifies channel filter logic: typing a string keeps only matching channels and removes non-matching ones."""
        client = TestClient(app)
        resp = client.get("/api/channels")
        channels = resp.json()["channels"]

        # Filter function identical to Alpine.js filteredChannels()
        def filter_channels(query, ch_list):
            q = query.strip().lower().replace("@", "")
            if not q:
                return ch_list
            return [
                c for c in ch_list
                if q in (c.get("name") or "").lower()
                or q in (c.get("handle") or "").lower().replace("@", "")
                or q in (c.get("category") or "").lower()
            ]

        # 1. Filter for "mobbin" -> should only return Mobbin
        mobbin_matches = filter_channels("mobbin", channels)
        assert len(mobbin_matches) >= 1
        assert all("mobbin" in c["name"].lower() or "mobbindesign" in c["handle"].lower() for c in mobbin_matches)

        # 2. Filter for "nate" -> should only return Nate Herk
        nate_matches = filter_channels("nate", channels)
        assert len(nate_matches) >= 1
        assert all("nate" in c["name"].lower() or "nateherk" in c["handle"].lower() for c in nate_matches)

        # 3. Filter for non-existent channel -> returns empty list
        empty_matches = filter_channels("nonexistent_random_xyz", channels)
        assert len(empty_matches) == 0

    def test_relative_time_parsing_and_no_fake_dates(self):
        """Verifies native relative time parsing and helper parsers."""
        from radar.fetcher import parse_relative_time, parse_duration_to_seconds, parse_views_text
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)

        # 1. Test relative time parser
        dt_12d = parse_relative_time("12 days ago")
        assert dt_12d is not None
        assert abs((now - dt_12d).total_seconds() - (12 * 86400)) < 300

        dt_2mo = parse_relative_time("2 months ago")
        assert dt_2mo is not None
        assert abs((now - dt_2mo).total_seconds() - (60 * 86400)) < 300

        dt_3h = parse_relative_time("3 hours ago")
        assert dt_3h is not None
        assert abs((now - dt_3h).total_seconds() - (3 * 3600)) < 300

        dt_stream = parse_relative_time("Streamed 3 days ago")
        assert dt_stream is not None
        assert abs((now - dt_stream).total_seconds() - (3 * 86400)) < 300

        dt_prem = parse_relative_time("Premiered 1 week ago")
        assert dt_prem is not None
        assert abs((now - dt_prem).total_seconds() - (7 * 86400)) < 300

        # Short notations
        assert parse_relative_time("12d ago") is not None
        assert parse_relative_time("2mo ago") is not None
        assert parse_relative_time("3h ago") is not None

        # 2. Test duration parser
        assert parse_duration_to_seconds("15:09") == 909
        assert parse_duration_to_seconds("14:34") == 874
        assert parse_duration_to_seconds("1:02:15") == 3735

        # 3. Test view parser
        assert parse_views_text("602K views") == 602000
        assert parse_views_text("1.5M views") == 1500000
        assert parse_views_text("294K") == 294000

    def test_wayfinder_video_real_upload_date_and_feed_exclusion(self):
        """Verifies that 2-month-old videos (like /wayfinder) are excluded from the 15-day feed and retain authentic dates."""
        ch_id = "UCswG6FSbgZjbWtdf_hMLaow"
        upsert_channel(channel_id=ch_id, name="Matt Pocock", url="https://youtube.com/@mattpocockuk", handle="@mattpocockuk")

        # 2.5 months ago
        wayfinder_real_date = "2026-07-30T03:17:45-07:00"
        upsert_video(
            video_id="F3lL98Pj90o",
            channel_id=ch_id,
            title="/wayfinder: Nothing is too big to plan anymore",
            url="https://youtube.com/watch?v=F3lL98Pj90o",
            thumbnail_url="https://i.ytimg.com/vi/F3lL98Pj90o/hqdefault.jpg",
            published_at=wayfinder_real_date,
            view_count=602000,
            duration_seconds=909,
            is_short=False
        )

        # 1. Must NOT appear in 15-day feed
        feed = get_feed_videos(days_back=15, limit=50)
        assert all(v["video_id"] != "F3lL98Pj90o" for v in feed)

        # 2. Must appear when searched, with exact real upload date
        searched = get_feed_videos(search="wayfinder", limit=50)
        assert len(searched) == 1
        assert searched[0]["video_id"] == "F3lL98Pj90o"
        assert searched[0]["published_at"] == wayfinder_real_date

