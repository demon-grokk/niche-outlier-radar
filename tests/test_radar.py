from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient
from app.main import app
from radar.db import (
    init_db,
    upsert_channel,
    upsert_video,
    upsert_outlier,
    get_all_channels,
    get_channel_videos,
    get_outliers
)
from radar.outlier_engine import calculate_channel_median, detect_outliers_for_channel

TEST_CHANNEL_ID = "UC_TEST_MOCK_123"
OUTLIER_VIDEO_ID = "vid_outlier_breakout"


def _days_ago(days: int) -> str:
    """Returns an ISO-8601 UTC timestamp `days` days before now.

    Outlier queries filter on recency (`days_back`, default 15), so hardcoded
    dates silently rot: a fixture that is fresh today falls out of the window
    weeks later. Relative dates keep these tests deterministic forever.
    """
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest.fixture
def seeded_breakout_channel(isolated_test_db):
    """Seeds a channel with 5 baseline videos and one recent breakout video.

    Baseline views: 8000..12000 -> median 10500.
    Breakout views: 45000 -> 45000 / 10500 = 4.29x outlier.
    """
    upsert_channel(
        channel_id=TEST_CHANNEL_ID,
        name="Test AI Channel",
        url="https://youtube.com/@testaichannel",
        handle="@testaichannel",
        category="AI Agents",
        country="US"
    )

    baseline_views = [8000, 9000, 10000, 11000, 12000]
    for idx, views in enumerate(baseline_views):
        upsert_video(
            video_id=f"vid_test_{idx}",
            channel_id=TEST_CHANNEL_ID,
            title=f"Standard Video {idx}",
            url=f"https://youtube.com/watch?v=vid_test_{idx}",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at=_days_ago(20 + idx),
            view_count=views,
            duration_seconds=600,
            is_short=False
        )

    # Recent 4.29x outlier video (45,000 views)
    upsert_video(
        video_id=OUTLIER_VIDEO_ID,
        channel_id=TEST_CHANNEL_ID,
        title="Breakout AI Agent Workflow Revealed",
        url=f"https://youtube.com/watch?v={OUTLIER_VIDEO_ID}",
        thumbnail_url="https://example.com/thumb.jpg",
        published_at=_days_ago(2),
        view_count=45000,
        duration_seconds=900,
        is_short=False
    )

    return TEST_CHANNEL_ID


def setup_module(module):
    init_db()


def test_channel_and_video_flow(seeded_breakout_channel):
    test_ch_id = seeded_breakout_channel

    channels = get_all_channels()
    ch_map = {c["channel_id"]: c for c in channels}
    assert test_ch_id in ch_map
    assert ch_map[test_ch_id]["name"] == "Test AI Channel"

    videos = get_channel_videos(test_ch_id)
    assert len(videos) == 6

    median = calculate_channel_median(test_ch_id)
    assert median == 10500

    outliers = detect_outliers_for_channel(test_ch_id, min_multiplier=2.5, days_back=30)
    assert len(outliers) == 1
    assert outliers[0]["video_id"] == OUTLIER_VIDEO_ID
    assert outliers[0]["multiplier"] == 4.29


def test_outlier_query_filtering(seeded_breakout_channel):
    outliers = get_outliers(min_multiplier=2.0)
    assert any(o["video_id"] == OUTLIER_VIDEO_ID for o in outliers)

    # High threshold filtering
    high_outliers = get_outliers(min_multiplier=10.0)
    assert not any(o["video_id"] == OUTLIER_VIDEO_ID for o in high_outliers)


def test_fastapi_endpoints():
    client = TestClient(app)

    # Check HTML dashboard
    r_dash = client.get("/")
    assert r_dash.status_code == 200
    assert "Outlier Radar" in r_dash.text

    # Check /api/channels
    r_chan = client.get("/api/channels")
    assert r_chan.status_code == 200
    data_chan = r_chan.json()
    assert data_chan["count"] > 0

    # Check /api/outliers
    r_out = client.get("/api/outliers?min_multiplier=2.0")
    assert r_out.status_code == 200
    data_out = r_out.json()
    assert "outliers" in data_out
