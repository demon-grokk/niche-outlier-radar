"""FastAPI web server for Niche Outlier Radar."""
import os
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from radar.config import BASE_DIR, DB_PATH, DEFAULT_OUTLIER_MULTIPLIER, RECENCY_DAYS, FEED_LIMIT
from radar.db import (
    init_db,
    get_all_channels,
    get_outliers,
    get_feed_videos,
    search_channels,
    delete_channel,
    get_latest_sync_status
)
from radar.seed_channels import seed_default_channels
from radar.fetcher import sync_channel
from radar.outlier_engine import detect_outliers_for_channel
from radar.analyzer import analyze_outlier_video
from radar.collab import annotate_feed_with_collabs, detect_collab_for_video
from radar.discovery import run_all_growth_sections
from radar.scheduler import (
    start_async_sync,
    get_current_sync_progress,
    execute_full_sync
)

STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_default_channels()
    yield

app = FastAPI(title="Niche Outlier Radar", version="2.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "default_multiplier": DEFAULT_OUTLIER_MULTIPLIER,
            "recency_days": RECENCY_DAYS,
            "feed_limit": FEED_LIMIT
        }
    )

@app.get("/api/feed")
def api_get_feed(
    days_back: int = Query(15, ge=1, le=90),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    min_multiplier: Optional[float] = Query(None, ge=1.0, le=50.0),
    sort_by: str = Query("smart_signal", pattern="^(smart_signal|date_desc|outlier_desc)$"),
    limit: int = Query(50, ge=1, le=100),
    video_type: str = Query("long", pattern="^(long|shorts|all)$")
):
    """Returns top 50 videos strictly within recency days, sorted by publish date or outlier score.
    video_type: 'long' (default, non-shorts only), 'shorts' (shorts only), or 'all'."""
    videos = get_feed_videos(
        days_back=days_back,
        min_multiplier=min_multiplier,
        category=category,
        search=search,
        sort_by=sort_by,
        limit=limit,
        video_type=video_type
    )
    annotate_feed_with_collabs(videos)
    matched_channels = search_channels(search, limit=3) if search else []
    return {"count": len(videos), "videos": videos, "matched_channels": matched_channels}

@app.get("/api/collabs/detect")
def api_detect_collab(title: str = Query(..., min_length=1), channel_name: Optional[str] = Query(None)):
    """Detects collaborator or guest creator from title and channel context."""
    collab = detect_collab_for_video(title=title, host_name=channel_name or "")
    return {"collab": collab}

@app.post("/api/discovery/scan")
def api_discovery_scan(background_tasks: BackgroundTasks):
    """Triggers Sections A, B, and C aggressive creator catalog scaling in the background."""
    def run_scan():
        run_all_growth_sections(sync_curated=False)
    background_tasks.add_task(run_scan)
    return {"message": "Creator catalog discovery scan started in background."}

@app.get("/api/channels/search")
def api_search_channels(q: str = Query(..., min_length=1)):
    channels = search_channels(q)
    return {"count": len(channels), "channels": channels}

@app.get("/api/outliers")
def api_get_outliers(
    min_multiplier: float = Query(1.8, ge=1.0, le=50.0),
    category: Optional[str] = Query(None),
    days_back: int = Query(15, ge=1, le=180),
    search: Optional[str] = Query(None),
    video_type: str = Query("long", pattern="^(long|shorts|all)$")
):
    outliers = get_outliers(
        min_multiplier=min_multiplier,
        category=category,
        days_back=days_back,
        search=search,
        video_type=video_type
    )
    annotate_feed_with_collabs(outliers)
    return {"count": len(outliers), "outliers": outliers}

@app.get("/api/channels")
def api_get_channels():
    channels = get_all_channels()
    return {"count": len(channels), "channels": channels}

@app.get("/api/raw-channels")
def api_get_raw_channels():
    channels = get_all_channels()
    stats = {
        "total_channels": len(channels),
        "db_path": str(DB_PATH),
        "categories": list({c.get("category") or "Uncategorized" for c in channels})
    }
    return {"stats": stats, "channels": channels}

class ChannelCreateRequest(BaseModel):
    url_or_handle: str

@app.post("/api/channels")
def api_add_channel(payload: ChannelCreateRequest, background_tasks: BackgroundTasks):
    url = payload.url_or_handle.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Channel URL or handle is required.")
    
    res = sync_channel(url)
    if not res["success"]:
        raise HTTPException(status_code=400, detail="Could not resolve or fetch channel. Verify URL or handle.")

    def post_add_task():
        from radar.outlier_engine import calculate_channel_median
        calculate_channel_median(res["channel_id"])
        detect_outliers_for_channel(res["channel_id"])
    background_tasks.add_task(post_add_task)

    return {"message": "Channel added successfully", "channel_id": res["channel_id"], "videos_count": res["videos_count"]}

@app.delete("/api/channels/{channel_id}")
def api_delete_channel(channel_id: str):
    delete_channel(channel_id)
    return {"message": f"Channel {channel_id} removed"}

@app.post("/api/sync")
def api_trigger_sync():
    started = start_async_sync()
    if not started:
        return JSONResponse(status_code=409, content={"message": "A sync is already in progress."})
    return {"message": "Sync started in background."}

@app.get("/api/sync/status")
def api_sync_status():
    progress = get_current_sync_progress()
    latest_log = get_latest_sync_status()
    return {
        "progress": progress,
        "latest_log": latest_log
    }

@app.post("/api/outliers/{video_id}/analyze")
def api_analyze_outlier(video_id: str):
    from radar.db import get_db
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM outliers WHERE video_id = ?", (video_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Outlier not found")
        
        cursor_v = conn.execute("SELECT title FROM videos WHERE video_id = ?", (video_id,))
        v_row = cursor_v.fetchone()
        title = v_row["title"] if v_row else "Untitled"

    res = analyze_outlier_video(
        video_id=video_id,
        channel_id=row["channel_id"],
        title=title,
        multiplier=row["multiplier"],
        median=row["channel_median_at_time"]
    )
    if not res:
        raise HTTPException(status_code=500, detail="AI Analysis failed. Check Groq API configuration.")
    return res
