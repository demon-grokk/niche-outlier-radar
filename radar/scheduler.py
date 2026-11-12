"""Scheduler and job runner for scanning channels and updating outliers."""
import time
import logging
import threading
from typing import Dict, Any, Optional

from radar.db import (
    get_all_channels,
    create_sync_log,
    update_sync_log,
    get_latest_sync_status
)
from radar.fetcher import sync_channel
from radar.outlier_engine import detect_outliers_for_channel
from radar.analyzer import process_pending_outliers

logger = logging.getLogger(__name__)

_SYNC_LOCK = threading.Lock()
_CURRENT_PROGRESS = {
    "is_running": False,
    "current_channel": "",
    "channels_completed": 0,
    "total_channels": 0,
    "outliers_found": 0,
    "started_at": 0
}

def get_current_sync_progress() -> Dict[str, Any]:
    return dict(_CURRENT_PROGRESS)

def execute_full_sync(max_channels: Optional[int] = None) -> Dict[str, Any]:
    """Runs a complete sync cycle across channels with polite pacing."""
    global _CURRENT_PROGRESS

    if not _SYNC_LOCK.acquire(blocking=False):
        return {"status": "already_running", "message": "A sync is already in progress."}

    log_id = create_sync_log()
    channels = get_all_channels()
    if max_channels:
        channels = channels[:max_channels]

    total = len(channels)
    _CURRENT_PROGRESS = {
        "is_running": True,
        "current_channel": "Initializing...",
        "channels_completed": 0,
        "total_channels": total,
        "outliers_found": 0,
        "started_at": time.time()
    }

    scanned_channels = 0
    total_videos = 0
    total_outliers = 0

    try:
        for idx, ch in enumerate(channels):
            ch_name = ch["name"]
            ch_url = ch["url"]
            _CURRENT_PROGRESS["current_channel"] = ch_name
            logger.info(f"[{idx+1}/{total}] Syncing channel: {ch_name}")

            res = sync_channel(ch_url)
            if res["success"]:
                scanned_channels += 1
                total_videos += res["videos_count"]

                # Detect outliers for this channel
                outliers = detect_outliers_for_channel(res["channel_id"])
                total_outliers += len(outliers)
                _CURRENT_PROGRESS["outliers_found"] = total_outliers

            _CURRENT_PROGRESS["channels_completed"] = idx + 1
            # Polite pause to avoid rate limiting
            time.sleep(1.0)

        # Process any pending LLM transcript analyses
        _CURRENT_PROGRESS["current_channel"] = "Generating AI Creator Cards..."
        analyzed_count = process_pending_outliers(limit=15)

        update_sync_log(
            log_id=log_id,
            status="completed",
            channels_scanned=scanned_channels,
            videos_fetched=total_videos,
            outliers_found=total_outliers,
            message=f"Sync finished. Analyzed {analyzed_count} outliers with Groq."
        )

        return {
            "status": "completed",
            "channels_scanned": scanned_channels,
            "videos_fetched": total_videos,
            "outliers_found": total_outliers,
            "analyzed_count": analyzed_count
        }

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        update_sync_log(log_id=log_id, status="failed", message=str(e))
        return {"status": "failed", "error": str(e)}

    finally:
        _CURRENT_PROGRESS["is_running"] = False
        _CURRENT_PROGRESS["current_channel"] = ""
        _SYNC_LOCK.release()

def start_async_sync(max_channels: Optional[int] = None) -> bool:
    """Spawns sync execution in a background thread."""
    if _SYNC_LOCK.locked():
        return False
    t = threading.Thread(target=execute_full_sync, args=(max_channels,), daemon=True)
    t.start()
    return True
