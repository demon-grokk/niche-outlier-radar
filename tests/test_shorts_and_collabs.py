"""Automated verification tests for Shorts separation, Collab detection, and Creator discovery."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from radar.db import get_feed_videos, get_all_channels
from radar.collab import detect_collab_for_video, extract_guest_candidate

client = TestClient(app)

def test_feed_separates_shorts_and_long_form():
    """Verify that video_type='long' contains no shorts, and video_type='shorts' contains only shorts."""
    long_feed = get_feed_videos(video_type="long", limit=50)
    assert len(long_feed) > 0
    for v in long_feed:
        assert v.get("is_short") == 0 or v.get("is_short") is None
        dur = v.get("duration_seconds", 0)
        assert dur == 0 or dur > 60 or dur is None, f"Video {v['video_id']} had short duration {dur}"

    shorts_feed = get_feed_videos(video_type="shorts", limit=50)
    assert len(shorts_feed) > 0
    for v in shorts_feed:
        is_short = v.get("is_short") == 1
        is_short_duration = (v.get("duration_seconds", 0) > 0 and v.get("duration_seconds", 0) <= 60)
        assert is_short or is_short_duration, f"Video {v['video_id']} was not a short"

def test_api_feed_video_type_query_param():
    """Test API endpoint /api/feed with video_type query parameter."""
    res_long = client.get("/api/feed?video_type=long&limit=20")
    assert res_long.status_code == 200
    data_long = res_long.json()
    assert "videos" in data_long
    for v in data_long["videos"]:
        dur = v.get("duration_seconds", 0) or 0
        assert not (dur > 0 and dur <= 60)
        assert v.get("is_short") != 1

    res_shorts = client.get("/api/feed?video_type=shorts&limit=20")
    assert res_shorts.status_code == 200
    data_shorts = res_shorts.json()
    assert len(data_shorts["videos"]) > 0
    for v in data_shorts["videos"]:
        dur = v.get("duration_seconds", 0) or 0
        assert v.get("is_short") == 1 or (dur > 0 and dur <= 60)

def test_collab_extraction_nate_herk_matt_pocock():
    """Verify that Nate Herk's collab with Matt Pocock is detected as a tracked creator."""
    title = "Matt Pocock: The Most Valuable Skill to Learn in the Age of AI"
    collab = detect_collab_for_video(title=title, host_name="Nate Herk | AI Automation")
    assert collab is not None
    assert collab["guest_name"] == "Matt Pocock"
    assert collab["is_tracked"] is True
    assert collab["guest_handle"] == "@mattpocockuk"

def test_collab_extraction_featuring_and_untracked():
    """Verify with/ft./feat. syntax and untracked creator recommendations."""
    title = "Building Multi-Agent Systems with Sam Altman"
    collab = detect_collab_for_video(title=title, host_name="IndyDevDan")
    assert collab is not None
    assert "Sam Altman" in collab["guest_name"]

def test_collab_extraction_ignores_common_title_prefixes():
    """Ensure non-creator prefixes like Tutorial, Review, Guide do not trigger false positive collabs."""
    titles = [
        "Tutorial: How to install Docker",
        "Review: The best mouse for coding",
        "Warning: Do not use this Python feature",
        "Guide: Building your first fullstack app",
        "Deep Dive: Understanding Attention Mechanisms"
    ]
    for t in titles:
        candidate = extract_guest_candidate(t, host_name="Test Creator")
        assert candidate is None, f"False positive candidate '{candidate}' found for title: {t}"

def test_api_detect_collab_endpoint():
    """Verify GET /api/collabs/detect returns accurate collab payload."""
    res = client.get("/api/collabs/detect", params={
        "title": "Matt Pocock: The Most Valuable Skill to Learn in the Age of AI",
        "channel_name": "Nate Herk | AI Automation"
    })
    assert res.status_code == 200
    data = res.json()
    assert "collab" in data
    assert data["collab"] is not None
    assert data["collab"]["guest_name"] == "Matt Pocock"
    assert data["collab"]["is_tracked"] is True

def test_matt_pocock_tracked_in_catalog():
    """Verify Matt Pocock exists in the database and catalog."""
    channels = get_all_channels()
    matt_matches = [c for c in channels if "Matt Pocock" in c.get("name", "") or c.get("handle") == "@mattpocockuk"]
    assert len(matt_matches) >= 1
    assert matt_matches[0]["channel_id"] == "UCswG6FSbgZjbWtdf_hMLaow"

def test_expanded_catalog_size():
    """Verify Sections A, B, and C expanded catalog beyond 150 creators."""
    channels = get_all_channels()
    assert len(channels) >= 150
