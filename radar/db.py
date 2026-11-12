"""Database management and SQLite schemas for Niche Outlier Radar."""
import sqlite3
import json
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
from datetime import datetime
from radar.config import DB_PATH
from radar.region import get_channel_region, is_indian_creator, is_drama_or_low_quality_title

@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Initializes tables and indexes."""
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            handle TEXT,
            url TEXT NOT NULL,
            avatar_url TEXT,
            category TEXT,
            subscriber_count INTEGER DEFAULT 0,
            median_views INTEGER DEFAULT 0,
            last_synced_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            channel_id TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            thumbnail_url TEXT,
            published_at TIMESTAMP,
            view_count INTEGER DEFAULT 0,
            duration_seconds INTEGER DEFAULT 0,
            is_short BOOLEAN DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (channel_id) REFERENCES channels (channel_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS outliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            channel_id TEXT NOT NULL,
            multiplier REAL NOT NULL,
            channel_median_at_time INTEGER NOT NULL,
            category TEXT,
            summary_bullets TEXT,
            tools_mentioned TEXT,
            viral_hook_angle TEXT,
            analyzed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos (video_id) ON DELETE CASCADE,
            FOREIGN KEY (channel_id) REFERENCES channels (channel_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            channels_scanned INTEGER DEFAULT 0,
            videos_fetched INTEGER DEFAULT 0,
            outliers_found INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            message TEXT
        );

        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            transcript_text TEXT NOT NULL,
            source TEXT DEFAULT 'captions',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_videos_channel_published ON videos(channel_id, published_at);
        CREATE INDEX IF NOT EXISTS idx_outliers_multiplier ON outliers(multiplier DESC);
        CREATE INDEX IF NOT EXISTS idx_outliers_category ON outliers(category);
        """)

        # Migration checks
        cursor = conn.execute("PRAGMA table_info(channels)")
        cols = [r["name"] if isinstance(r, sqlite3.Row) else r[1] for r in cursor.fetchall()]
        if "category" not in cols:
            conn.execute("ALTER TABLE channels ADD COLUMN category TEXT")
        if "country" not in cols:
            conn.execute("ALTER TABLE channels ADD COLUMN country TEXT DEFAULT 'US'")

        cursor_t = conn.execute("PRAGMA table_info(transcripts)")
        t_cols = [r["name"] if isinstance(r, sqlite3.Row) else r[1] for r in cursor_t.fetchall()]
        if "created_at" not in t_cols:
            conn.execute("ALTER TABLE transcripts ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

# Channel Helpers
def upsert_channel(channel_id: str, name: str, url: str, handle: str = "", avatar_url: str = "", category: str = "", subscriber_count: int = 0, country: Optional[str] = None) -> None:
    resolved_country = country or get_channel_region(handle=handle, name=name)
    with get_db() as conn:
        conn.execute("""
            INSERT INTO channels (channel_id, name, handle, url, avatar_url, category, subscriber_count, country)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                name = excluded.name,
                handle = COALESCE(NULLIF(excluded.handle, ''), channels.handle),
                avatar_url = COALESCE(NULLIF(excluded.avatar_url, ''), channels.avatar_url),
                category = COALESCE(NULLIF(excluded.category, ''), channels.category),
                subscriber_count = CASE WHEN excluded.subscriber_count > 0 THEN excluded.subscriber_count ELSE channels.subscriber_count END,
                country = COALESCE(NULLIF(excluded.country, ''), channels.country)
        """, (channel_id, name, handle, url, avatar_url, category, subscriber_count, resolved_country))

def update_channel_median(channel_id: str, median_views: int) -> None:
    with get_db() as conn:
        conn.execute("""
            UPDATE channels 
            SET median_views = ?, last_synced_at = CURRENT_TIMESTAMP
            WHERE channel_id = ?
        """, (median_views, channel_id))

def get_all_channels() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT c.*, COUNT(v.id) as video_count, COUNT(o.id) as outlier_count
            FROM channels c
            LEFT JOIN videos v ON c.channel_id = v.channel_id
            LEFT JOIN outliers o ON c.channel_id = o.channel_id
            GROUP BY c.channel_id
            ORDER BY c.name COLLATE NOCASE ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

def delete_channel(channel_id: str) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))

# Video Helpers
def upsert_video(video_id: str, channel_id: str, title: str, url: str, thumbnail_url: str, published_at: Optional[str], view_count: int, duration_seconds: int, is_short: bool) -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO videos (video_id, channel_id, title, url, thumbnail_url, published_at, view_count, duration_seconds, is_short, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(video_id) DO UPDATE SET
                title = excluded.title,
                view_count = excluded.view_count,
                duration_seconds = excluded.duration_seconds,
                thumbnail_url = excluded.thumbnail_url,
                published_at = COALESCE(NULLIF(excluded.published_at, ''), videos.published_at),
                updated_at = CURRENT_TIMESTAMP
        """, (video_id, channel_id, title, url, thumbnail_url, published_at, view_count, duration_seconds, 1 if is_short else 0))

def get_channel_videos(channel_id: str, limit: int = 50, exclude_shorts: bool = True) -> List[Dict[str, Any]]:
    with get_db() as conn:
        query = "SELECT * FROM videos WHERE channel_id = ?"
        if exclude_shorts:
            query += " AND (is_short = 0 OR is_short IS NULL) AND (duration_seconds = 0 OR duration_seconds > 60 OR duration_seconds IS NULL)"
        query += " ORDER BY published_at DESC LIMIT ?"
        cursor = conn.execute(query, (channel_id, limit))
        return [dict(row) for row in cursor.fetchall()]

# Outlier Helpers
def upsert_outlier(video_id: str, channel_id: str, multiplier: float, channel_median: int, category: str = "", summary_bullets: List[str] = None, tools_mentioned: List[str] = None, viral_hook_angle: str = "") -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO outliers (video_id, channel_id, multiplier, channel_median_at_time, category, summary_bullets, tools_mentioned, viral_hook_angle, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(video_id) DO UPDATE SET
                multiplier = excluded.multiplier,
                channel_median_at_time = excluded.channel_median_at_time,
                category = COALESCE(NULLIF(excluded.category, ''), outliers.category),
                summary_bullets = COALESCE(NULLIF(excluded.summary_bullets, ''), outliers.summary_bullets),
                tools_mentioned = COALESCE(NULLIF(excluded.tools_mentioned, ''), outliers.tools_mentioned),
                viral_hook_angle = COALESCE(NULLIF(excluded.viral_hook_angle, ''), outliers.viral_hook_angle),
                analyzed_at = CURRENT_TIMESTAMP
        """, (
            video_id,
            channel_id,
            multiplier,
            channel_median,
            category,
            json.dumps(summary_bullets or []),
            json.dumps(tools_mentioned or []),
            viral_hook_angle
        ))

def interleave_feed_videos(
    videos: List[Dict[str, Any]],
    max_per_creator: int = 2,
    max_consecutive: int = 1,
    target_count: int = 50,
    max_in_ratio: float = 0.10
) -> List[Dict[str, Any]]:
    """
    Enforces creator diversity, geographic balance, and quality standards:
    1. Caps any single creator at max_per_creator (default: 2).
    2. Strictly guarantees 0 consecutive videos from the same creator.
    3. Caps Indian creators at <= 10% of the feed (max 5 out of 50 videos).
    4. Suppresses personal drama/apology vlogs from entering the feed.
    """
    if not videos:
        return []

    result: List[Dict[str, Any]] = []
    creator_counts: Dict[str, int] = {}
    deferred: List[Dict[str, Any]] = []

    # Maximum Indian videos allowed in feed (strictly <= 10%)
    max_in_count = max(1, int(target_count * max_in_ratio))
    in_creator_count = 0

    def get_cid(v: Dict[str, Any]) -> str:
        return str(v.get("channel_id") or v.get("channel_name") or "")

    def is_in(v: Dict[str, Any]) -> bool:
        return is_indian_creator(
            handle=v.get("channel_handle") or v.get("handle") or "",
            name=v.get("channel_name") or v.get("name") or "",
            country=v.get("channel_country") or v.get("country") or ""
        )

    # Pass 1: Select up to max_per_creator with regional cap and no consecutive repeats
    for v in videos:
        # Strictly suppress personal drama or apology vlogs
        if is_drama_or_low_quality_title(v.get("title", "")):
            continue

        cid = get_cid(v)
        if creator_counts.get(cid, 0) >= max_per_creator:
            deferred.append(v)
            continue

        # Regional quota: Indian creators capped at <= 10%
        if is_in(v) and in_creator_count >= max_in_count:
            deferred.append(v)
            continue

        if result and get_cid(result[-1]) == cid:
            deferred.append(v)
            continue

        result.append(v)
        creator_counts[cid] = creator_counts.get(cid, 0) + 1
        if is_in(v):
            in_creator_count += 1

        if len(result) >= target_count:
            return result

    # Pass 2: If we haven't reached target_count, pull from deferred (honoring regional quota where possible)
    while deferred and len(result) < target_count:
        placed = False
        last_cid = get_cid(result[-1]) if result else None
        for i, v in enumerate(deferred):
            if is_drama_or_low_quality_title(v.get("title", "")):
                continue

            cid = get_cid(v)
            if cid != last_cid:
                if is_in(v) and in_creator_count >= max_in_count:
                    has_other_candidates = any(not is_in(cand) for cand in deferred)
                    if has_other_candidates:
                        continue

                result.append(deferred.pop(i))
                creator_counts[cid] = creator_counts.get(cid, 0) + 1
                if is_in(v):
                    in_creator_count += 1
                placed = True
                break

        if not placed:
            for i, v in enumerate(deferred):
                if is_drama_or_low_quality_title(v.get("title", "")):
                    continue
                cid = get_cid(v)
                if is_in(v) and in_creator_count >= max_in_count:
                    has_other_candidates = any(not is_in(cand) for cand in deferred)
                    if has_other_candidates:
                        continue

                inserted = False
                for pos in range(len(result) - 1, 0, -1):
                    prev_cid = get_cid(result[pos - 1])
                    next_cid = get_cid(result[pos])
                    if cid != prev_cid and cid != next_cid:
                        result.insert(pos, deferred.pop(i))
                        creator_counts[cid] = creator_counts.get(cid, 0) + 1
                        if is_in(v):
                            in_creator_count += 1
                        inserted = True
                        break
                if inserted:
                    placed = True
                    break

            if not placed:
                break

    return result[:target_count]

def search_channels(search_term: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Searches channels by name, handle, or category and returns matching creator cards."""
    if not search_term or not search_term.strip():
        return []
    clean_term = search_term.strip().lstrip("@")
    term = f"%{clean_term}%"
    raw_term = f"%{search_term.strip()}%"
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT 
                c.channel_id, c.name, c.handle, c.url, c.avatar_url, 
                c.category, COALESCE(c.country, 'US') as country, c.subscriber_count, c.median_views,
                (SELECT count(*) FROM videos v WHERE v.channel_id = c.channel_id) as video_count
            FROM channels c
            WHERE c.name LIKE ? 
               OR c.handle LIKE ? 
               OR REPLACE(c.handle, '@', '') LIKE ?
               OR c.category LIKE ?
            ORDER BY video_count DESC, c.median_views DESC
            LIMIT ?
        """, (term, raw_term, term, term, limit))
        return [dict(row) for row in cursor.fetchall()]

def get_feed_videos(
    days_back: int = 15,
    min_multiplier: Optional[float] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "date_desc",
    limit: int = 50,
    video_type: str = "long"
) -> List[Dict[str, Any]]:
    """Returns top 50 videos strictly filtered within days_back (max 15), sorted by published_at DESC or outlier score.
    video_type can be 'long' (default, non-shorts only), 'shorts' (shorts only), or 'all' (all videos)."""
    with get_db() as conn:
        effective_days = 365 if search else days_back

        query = """
            SELECT 
                v.video_id, v.title, v.url as video_url, v.thumbnail_url, 
                v.published_at, v.view_count, v.duration_seconds, v.is_short,
                c.channel_id, c.name as channel_name, c.handle as channel_handle, 
                c.avatar_url as channel_avatar, COALESCE(c.category, 'Tech Discovery') as channel_category,
                COALESCE(c.country, 'US') as channel_country,
                c.median_views as channel_median,
                o.multiplier, o.category as outlier_category, 
                o.summary_bullets, o.tools_mentioned, o.viral_hook_angle
            FROM videos v
            JOIN channels c ON v.channel_id = c.channel_id
            LEFT JOIN outliers o ON v.video_id = o.video_id
            WHERE (datetime(v.published_at) >= datetime('now', '-' || ? || ' days') OR (? = 365 AND v.published_at IS NOT NULL))
        """
        params: List[Any] = [effective_days, effective_days]

        if video_type == "long":
            query += " AND (v.is_short = 0 OR v.is_short IS NULL) AND (v.duration_seconds = 0 OR v.duration_seconds > 60 OR v.duration_seconds IS NULL)"
        elif video_type == "shorts":
            query += " AND (v.is_short = 1 OR (v.duration_seconds > 0 AND v.duration_seconds <= 60))"

        if min_multiplier is not None and min_multiplier > 0:
            query += " AND o.multiplier >= ?"
            params.append(min_multiplier)

        if category and category.lower() != 'all':
            query += " AND (LOWER(c.category) = LOWER(?) OR LOWER(o.category) = LOWER(?))"
            params.extend([category, category])

        if search:
            clean_term = search.strip().lstrip("@")
            term = f"%{clean_term}%"
            raw_term = f"%{search.strip()}%"
            query += """ AND (
                v.title LIKE ? 
                OR c.name LIKE ? 
                OR c.handle LIKE ? 
                OR REPLACE(c.handle, '@', '') LIKE ? 
                OR c.category LIKE ? 
                OR o.viral_hook_angle LIKE ?
                OR o.tools_mentioned LIKE ?
            )"""
            params.extend([term, term, raw_term, term, term, term, term])

        if not search:
            # 1. Base signal floor: strictly eliminate zero-view/dead uploads (>= 200 views)
            query += " AND v.view_count >= 200"
            
            # 2. Strict Micro-Creator Rule (<10k median channels must be verified outliers >= 2.0x and views >= 1,000)
            query += """ AND (
                c.median_views >= 10000 
                OR (COALESCE(o.multiplier, CAST(v.view_count AS REAL) / MAX(c.median_views, 1)) >= 2.0 AND v.view_count >= 1000)
            )"""

        if sort_by == "outlier_desc":
            query += " ORDER BY COALESCE(o.multiplier, CAST(v.view_count AS REAL) / MAX(c.median_views, 1)) DESC, v.published_at DESC"
        elif sort_by == "smart_signal":
            # Trending velocity: view count decayed by publish age, multiplied by outlier factor
            query += """ ORDER BY (
                COALESCE(o.multiplier, 1.0) * (CAST(v.view_count AS REAL) / (MAX((strftime('%s', 'now') - strftime('%s', v.published_at)) / 3600.0, 1.0) + 2.0))
            ) DESC, v.published_at DESC"""
        else:
            query += " ORDER BY v.published_at DESC"

        # Fetch extra candidates for interleaving
        fetch_limit = max(limit * 4, 150)
        query += " LIMIT ?"
        params.append(fetch_limit)

        cursor = conn.execute(query, params)
        rows = [dict(row) for row in cursor.fetchall()]
        for r in rows:
            if r["multiplier"] is None:
                median = r["channel_median"] or 15000
                r["multiplier"] = round(r["view_count"] / max(median, 1), 2)
            try:
                r["summary_bullets"] = json.loads(r["summary_bullets"]) if r["summary_bullets"] else []
            except Exception:
                r["summary_bullets"] = []
            try:
                r["tools_mentioned"] = json.loads(r["tools_mentioned"]) if r["tools_mentioned"] else []
            except Exception:
                r["tools_mentioned"] = []
            r["is_micro_outlier"] = bool((r.get("channel_median") or 0) < 10000 and (r.get("multiplier") or 0) >= 2.0)

        max_per_creator = 50 if search else 2
        max_in_ratio = 1.0 if search else 0.10
        interleaved = interleave_feed_videos(
            rows,
            max_per_creator=max_per_creator,
            max_consecutive=1,
            target_count=limit,
            max_in_ratio=max_in_ratio
        )
        return interleaved

def get_outliers(min_multiplier: float = 2.0, category: str = None, days_back: int = 15, search: str = None, video_type: str = "long") -> List[Dict[str, Any]]:
    return get_feed_videos(days_back=days_back, min_multiplier=min_multiplier, category=category, search=search, sort_by="outlier_desc", limit=50, video_type=video_type)

def get_pending_analysis_outliers(limit: int = 10) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT o.id, o.video_id, o.channel_id, o.multiplier, v.title, v.url, c.name as channel_name
            FROM outliers o
            JOIN videos v ON o.video_id = v.video_id
            JOIN channels c ON o.channel_id = c.channel_id
            WHERE o.category IS NULL OR o.category = '' OR o.summary_bullets IS NULL OR o.summary_bullets = '[]'
            ORDER BY o.multiplier DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

# Sync Logs
def create_sync_log() -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO sync_logs (status) VALUES ('running')")
        return cursor.lastrowid

def update_sync_log(log_id: int, status: str, channels_scanned: int = 0, videos_fetched: int = 0, outliers_found: int = 0, message: str = "") -> None:
    with get_db() as conn:
        conn.execute("""
            UPDATE sync_logs
            SET finished_at = CURRENT_TIMESTAMP,
                status = ?,
                channels_scanned = ?,
                videos_fetched = ?,
                outliers_found = ?,
                message = ?
            WHERE id = ?
        """, (status, channels_scanned, videos_fetched, outliers_found, message, log_id))

def get_latest_sync_status() -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM sync_logs ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return dict(row) if row else None
