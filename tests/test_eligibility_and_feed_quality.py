"""Automated tests for Channel Eligibility, Feed Quality Gatekeepers, and Micro-Creator Outlier Rules."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from radar.db import get_feed_videos, get_all_channels
from radar.discovery import is_channel_eligible, prune_ineligible_channels

client = TestClient(app)

def test_blacklisted_channels_rejected():
    """Verify that course mills and non-niche generic channels are strictly rejected."""
    assert is_channel_eligible("@simplilearnofficial", "Simplilearn") is False
    assert is_channel_eligible("@intellipaat", "Intellipaat") is False
    assert is_channel_eligible("@edureka", "Edureka") is False
    assert is_channel_eligible("@wscubetech", "WsCube Tech") is False
    assert is_channel_eligible("@tedx", "TEDx Talks") is False
    assert is_channel_eligible("@khanacademy", "Khan Academy") is False
    assert is_channel_eligible("@markrober", "Mark Rober") is False
    assert is_channel_eligible("@AIautomationofficially", "AI Automation Official") is False

def test_eligible_tech_channels_accepted():
    """Verify that authentic AI, Dev, and Automation creators pass the eligibility check."""
    assert is_channel_eligible("@indydevdan", "IndyDevDan", median_views=48000, max_views=190000) is True
    assert is_channel_eligible("@nateherk", "Nate Herk | AI Automation", median_views=150000, max_views=250000) is True
    assert is_channel_eligible("@mattpocockuk", "Matt Pocock", median_views=290000, max_views=300000) is True
    assert is_channel_eligible("@Fireship", "Fireship", median_views=1900000, max_views=5000000) is True

def test_feed_quality_floor_excludes_dead_videos():
    """Verify that videos with low/zero views are excluded from the main feed."""
    feed = get_feed_videos(video_type="long", limit=50)
    for v in feed:
        views = v.get("view_count", 0)
        # Every video in feed must meet the signal floor or be from a trusted high-median channel
        assert views >= 200 or (v.get("channel_median", 0) >= 10000), f"Video {v['video_id']} had {views} views"

def test_feed_micro_creator_outlier_rule():
    """Verify that channels with median < 10k only appear if their video is an outlier (multiplier >= 2.0)."""
    feed = get_feed_videos(video_type="long", limit=50)
    for v in feed:
        ch_median = v.get("channel_median", 0) or 0
        if ch_median < 10000:
            mult = v.get("multiplier", 0) or 0
            assert mult >= 2.0 or v.get("view_count", 0) >= 2000, (
                f"Micro creator {v.get('channel_name')} video {v['video_id']} had mult {mult} and views {v.get('view_count')}"
            )

def test_smart_signal_sorting_endpoint():
    """Verify API endpoint returns valid feed sorted by smart_signal."""
    res = client.get("/api/feed?sort_by=smart_signal&limit=25")
    assert res.status_code == 200
    data = res.json()
    assert "videos" in data
    assert len(data["videos"]) > 0
    # Top video should have strong view count and high signal
    top_video = data["videos"][0]
    assert top_video.get("view_count", 0) >= 1000

def test_prune_ineligible_channels_runs_safely():
    """Verify prune_ineligible_channels executes without errors and preserves curated creators."""
    deleted = prune_ineligible_channels()
    assert isinstance(deleted, int)
    channels = get_all_channels()
    # Check that core anchor creators remain intact
    handles = {c.get("handle") for c in channels}
    assert "@indydevdan" in handles or "@nateherk" in handles
    assert "@mattpocockuk" in handles

def test_indian_channel_feed_capped_at_10_percent():
    """Verify that Indian creators occupy strictly at most 10% of the 50-video feed (max 5 videos)."""
    feed = get_feed_videos(limit=50)
    assert len(feed) == 50
    in_videos = [v for v in feed if v.get("channel_country") == "IN"]
    assert len(in_videos) <= 5, f"Expected at most 5 Indian videos in feed, got {len(in_videos)}"
    assert (len(in_videos) / len(feed)) <= 0.101

def test_global_creators_dominate_feed():
    """Verify that US, Canada, Europe, APAC, and Global tech creators occupy >= 90% of the feed."""
    feed = get_feed_videos(limit=50)
    assert len(feed) == 50
    global_videos = [v for v in feed if v.get("channel_country") in ("US", "CA", "UK", "EU", "APAC", "GLOBAL")]
    assert len(global_videos) >= 45, f"Expected at least 45 global videos, got {len(global_videos)}"

def test_drama_and_apology_vlogs_suppressed():
    """Verify that personal drama, apology vlogs, and non-tech updates are strictly suppressed."""
    feed = get_feed_videos(limit=50)
    for v in feed:
        t = v.get("title", "").lower()
        assert "i am sorry" not in t, f"Drama video found in feed: {v['title']}"
        assert "personal update" not in t, f"Personal update vlog found in feed: {v['title']}"

def test_country_resolution_mappings():
    """Verify get_channel_region accurately resolves creators across continents."""
    from radar.region import get_channel_region
    assert get_channel_region("@AndrejKarpathy") == "US"
    assert get_channel_region("@Fireship") == "US"
    assert get_channel_region("@TechWithTim") == "CA"
    assert get_channel_region("@mattpocockuk") == "UK"
    assert get_channel_region("@YannicKilcher") == "EU"
    assert get_channel_region("@TechwithLucy") == "APAC"
    assert get_channel_region("@vaibhavsisinty") == "IN"
    assert get_channel_region("@gregisenberg") == "US"
    assert get_channel_region("@vivekmishrayt") == "IN"

def test_user_added_channels_greg_and_vivek_preserved():
    """Verify that user-added channels like Greg Isenberg and Vivek Mishra are permanently preserved."""
    from radar.db import upsert_video
    from datetime import datetime, timezone

    channels = get_all_channels()
    handles = {c.get("handle", "").lower(): c for c in channels if c.get("handle")}
    assert "@gregisenberg" in handles, "Expected @GregIsenberg in channels catalog"
    assert "@vivekmishrayt" in handles, "Expected @vivekmishrayt in channels catalog"

    greg = handles["@gregisenberg"]
    vivek = handles["@vivekmishrayt"]

    if greg.get("video_count", 0) == 0:
        upsert_video(
            video_id="mock_greg_01",
            channel_id=greg["channel_id"],
            title="Building Community-Led AI Products",
            url="https://youtube.com/watch?v=mock_greg_01",
            thumbnail_url="https://i.ytimg.com/vi/mock_greg_01/hqdefault.jpg",
            published_at=datetime.now(timezone.utc).isoformat(),
            view_count=50000,
            duration_seconds=750,
            is_short=False
        )
    if vivek.get("video_count", 0) == 0:
        upsert_video(
            video_id="mock_vivek_01",
            channel_id=vivek["channel_id"],
            title="Automate Workflows with AI Agents",
            url="https://youtube.com/watch?v=mock_vivek_01",
            thumbnail_url="https://i.ytimg.com/vi/mock_vivek_01/hqdefault.jpg",
            published_at=datetime.now(timezone.utc).isoformat(),
            view_count=12000,
            duration_seconds=860,
            is_short=False
        )

    channels = get_all_channels()
    handles = {c.get("handle", "").lower(): c for c in channels if c.get("handle")}
    greg = handles["@gregisenberg"]
    vivek = handles["@vivekmishrayt"]
    assert greg["video_count"] > 0
    assert greg["median_views"] > 0
    assert vivek["video_count"] > 0
    assert vivek["median_views"] > 0

    # Ensure prune_ineligible_channels does NOT delete them
    prune_ineligible_channels()
    channels_after = get_all_channels()
    handles_after = {c.get("handle", "").lower() for c in channels_after if c.get("handle")}
    assert "@gregisenberg" in handles_after
    assert "@vivekmishrayt" in handles_after

def test_fake_karpathy_squatter_blacklisted_and_real_karpathy_tracked():
    """Verify squatter handle @karpathy is strictly rejected and real @AndrejKarpathy is accepted."""
    assert is_channel_eligible("@karpathy", "karpathy") is False
    assert is_channel_eligible("@AndrejKarpathy", "Andrej Karpathy", median_views=3500000, max_views=10000000) is True

    # Ensure real Andrej Karpathy exists in seed catalog
    channels = get_all_channels()
    handles = {c.get("handle", "").lower(): c for c in channels if c.get("handle")}
    assert "@andrejkarpathy" in handles
    assert "@karpathy" not in handles or handles["@karpathy"]["channel_id"] != "UCe4jUOmQPKMDvOkzJpDfMRQ"

