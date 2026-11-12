"""Outlier calculation and anomaly detection engine."""
import logging
import statistics
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from radar.config import (
    DEFAULT_OUTLIER_MULTIPLIER,
    RECENCY_DAYS,
    MEDIAN_BASELINE_COUNT,
    MIN_VIDEO_VIEWS_FLOOR
)
from radar.db import (
    get_all_channels,
    get_channel_videos,
    update_channel_median,
    upsert_outlier
)

logger = logging.getLogger(__name__)

def calculate_channel_median(channel_id: str, baseline_limit: int = MEDIAN_BASELINE_COUNT) -> int:
    """Calculates rolling median view count for non-Shorts videos (with fallback for shorts-only channels)."""
    videos = get_channel_videos(channel_id, limit=baseline_limit, exclude_shorts=True)
    if not videos:
        videos = get_channel_videos(channel_id, limit=baseline_limit, exclude_shorts=False)
    if not videos:
        return 0
    view_counts = [v["view_count"] for v in videos if v["view_count"] > 0]
    if not view_counts:
        return 0
    median_val = int(statistics.median(view_counts))
    update_channel_median(channel_id, median_val)
    return median_val

def detect_outliers_for_channel(channel_id: str, min_multiplier: float = DEFAULT_OUTLIER_MULTIPLIER, days_back: int = RECENCY_DAYS) -> List[Dict[str, Any]]:
    """
    Detects outlier videos for a channel whose views exceed `min_multiplier * median`.
    Only considers videos published within `days_back`.
    """
    median_views = calculate_channel_median(channel_id)
    if median_views <= 0:
        return []

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    videos = get_channel_videos(channel_id, limit=40, exclude_shorts=True)
    
    outliers = []
    for v in videos:
        # Check views floor
        if v["view_count"] < MIN_VIDEO_VIEWS_FLOOR:
            continue

        # Check recency
        if v["published_at"]:
            try:
                # Handle various ISO string formats
                pub_str = v["published_at"].replace("Z", "+00:00")
                pub_dt = datetime.fromisoformat(pub_str)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff_date:
                    continue
            except Exception:
                pass

        multiplier = round(v["view_count"] / median_views, 2)
        if multiplier >= min_multiplier:
            upsert_outlier(
                video_id=v["video_id"],
                channel_id=channel_id,
                multiplier=multiplier,
                channel_median=median_views
            )
            outliers.append({
                "video_id": v["video_id"],
                "channel_id": channel_id,
                "title": v["title"],
                "views": v["view_count"],
                "median": median_views,
                "multiplier": multiplier
            })

    return outliers

def scan_all_channels_for_outliers(min_multiplier: float = DEFAULT_OUTLIER_MULTIPLIER) -> List[Dict[str, Any]]:
    """Scans all registered channels and detects outliers."""
    channels = get_all_channels()
    all_outliers = []
    for ch in channels:
        found = detect_outliers_for_channel(ch["channel_id"], min_multiplier=min_multiplier)
        all_outliers.extend(found)
    return all_outliers
