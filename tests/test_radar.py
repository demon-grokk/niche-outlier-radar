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

def setup_module(module):
    init_db()

def test_channel_and_video_flow():
    test_ch_id = "UC_TEST_MOCK_123"
    upsert_channel(
        channel_id=test_ch_id,
        name="Test AI Channel",
        url="https://youtube.com/@testaichannel",
        handle="@testaichannel"
    )
    
    channels = get_all_channels()
    ch_map = {c["channel_id"]: c for c in channels}
    assert test_ch_id in ch_map
    assert ch_map[test_ch_id]["name"] == "Test AI Channel"

    # Insert historical videos
    baseline_views = [8000, 9000, 10000, 11000, 12000]
    for idx, v in enumerate(baseline_views):
        upsert_video(
            video_id=f"vid_test_{idx}",
            channel_id=test_ch_id,
            title=f"Standard Video {idx}",
            url=f"https://youtube.com/watch?v=vid_test_{idx}",
            thumbnail_url="https://example.com/thumb.jpg",
            published_at="2026-10-10T10:00:00+00:00",
            view_count=v,
            duration_seconds=600,
            is_short=False
        )

    # Insert a 4.29x Outlier video (45,000 views)
    upsert_video(
        video_id="vid_outlier_breakout",
        channel_id=test_ch_id,
        title="Breakout AI Agent Workflow Revealed",
        url="https://youtube.com/watch?v=vid_outlier_breakout",
        thumbnail_url="https://example.com/thumb.jpg",
        published_at="2026-10-14T10:00:00+00:00",
        view_count=45000,
        duration_seconds=900,
        is_short=False
    )

    median = calculate_channel_median(test_ch_id)
    assert median == 10500

    outliers = detect_outliers_for_channel(test_ch_id, min_multiplier=2.5, days_back=30)
    assert len(outliers) == 1
    assert outliers[0]["video_id"] == "vid_outlier_breakout"
    assert outliers[0]["multiplier"] == 4.29

def test_outlier_query_filtering():
    outliers = get_outliers(min_multiplier=2.0)
    assert any(o["video_id"] == "vid_outlier_breakout" for o in outliers)

    # High threshold filtering
    high_outliers = get_outliers(min_multiplier=10.0)
    assert not any(o["video_id"] == "vid_outlier_breakout" for o in high_outliers)

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
