"""YouTube channel video scraper using XML RSS as primary layer, with Innertube/yt-dlp fallback."""
import os
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
import yt_dlp

from radar.config import DEFAULT_USER_AGENT, YOUTUBE_COOKIES_FILE
from radar.db import upsert_video, upsert_channel

logger = logging.getLogger(__name__)

# XML Namespaces for YouTube RSS feeds
ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"
MEDIA_NS = "http://search.yahoo.com/mrss/"
NS = {
    "atom": ATOM_NS,
    "yt": YT_NS,
    "media": MEDIA_NS,
}

# Session persistence and Innertube client headers
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

INNERTUBE_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "X-YouTube-Client-Name": "1",
    "X-YouTube-Client-Version": "2.20241015.01.00",
    "Origin": "https://www.youtube.com",
    "Referer": "https://www.youtube.com/",
    "Accept-Language": "en-US,en;q=0.9",
}


def get_browser_headers() -> Dict[str, str]:
    """Returns standard browser headers for requests."""
    return dict(DEFAULT_HEADERS)


def get_innertube_headers() -> Dict[str, str]:
    """Returns Innertube client emulation headers."""
    return dict(INNERTUBE_HEADERS)


def get_cookies_path() -> Optional[str]:
    """Returns path to YouTube cookies file if present on host in Netscape text format."""
    if YOUTUBE_COOKIES_FILE and Path(YOUTUBE_COOKIES_FILE).exists():
        try:
            with open(YOUTUBE_COOKIES_FILE, "rb") as f:
                header = f.read(30)
                if b"SQLite" not in header:
                    return str(YOUTUBE_COOKIES_FILE)
        except Exception:
            pass

    return None


def get_ydl_options(max_videos: int = 40, extra_opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Builds resilient yt-dlp configuration with Innertube headers and cookies."""
    opts: Dict[str, Any] = {
        "extract_flat": True,
        "skip_download": True,
        "playlistend": max_videos,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "http_headers": get_innertube_headers(),
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "tv_downgraded"]
            }
        },
    }

    cookies_file = get_cookies_path()
    if cookies_file and Path(cookies_file).is_file():
        opts["cookiefile"] = cookies_file

    if extra_opts:
        opts.update(extra_opts)

    return opts


def clean_channel_url(url_or_handle: str) -> str:
    """Normalizes channel URL from handle, channel ID, or partial URL."""
    url = url_or_handle.strip()
    if url.startswith("@"):
        return f"https://www.youtube.com/{url}"
    if not url.startswith("http"):
        if url.startswith("UC"):
            return f"https://www.youtube.com/channel/{url}"
        return f"https://www.youtube.com/@{url}"
    return url


def extract_channel_id(channel_url_or_handle: str) -> Optional[str]:
    """
    Extracts a YouTube UC channel ID from an ID, handle, or URL.
    Attempts regex extraction first; if given a handle, queries the handle page.
    """
    s = channel_url_or_handle.strip()
    # Check if channel ID is already embedded in string
    match = re.search(r"(UC[a-zA-Z0-9_-]{22})", s)
    if match:
        return match.group(1)

    # If it is a handle or custom URL, fetch the HTML header to find browseId / channelId
    target_url = clean_channel_url(s)
    try:
        resp = requests.get(target_url, headers=DEFAULT_HEADERS, timeout=6)
        if resp.status_code == 200:
            m = re.search(r'itemprop="identifier"\s+content="(UC[a-zA-Z0-9_-]{22})"', resp.text)
            if not m:
                m = re.search(r'"browseId":"(UC[a-zA-Z0-9_-]{22})"', resp.text)
            if not m:
                m = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', resp.text)
            if m:
                return m.group(1)
    except Exception as e:
        logger.debug(f"HTML lookup failed for channel ID {s}: {e}")

    # Fallback to yt-dlp
    try:
        opts = get_ydl_options(max_videos=1)
        with yt_dlp.YoutubeDL(opts) as ydl:
            res = ydl.extract_info(target_url, download=False)
            if res and res.get("channel_id"):
                return res.get("channel_id")
    except Exception as e:
        logger.debug(f"yt-dlp channel ID resolution failed for {s}: {e}")

    return None


def parse_feed_xml(xml_content: Any) -> List[Dict[str, Any]]:
    """
    Parses YouTube Channel Atom XML feed content.
    Extracts video_id, channel_id, title, published_at, thumbnail_url, and views.
    """
    if isinstance(xml_content, (bytes, bytearray)):
        xml_content = xml_content.decode("utf-8", errors="replace")
    elif not isinstance(xml_content, str):
        xml_content = str(xml_content)

    videos = []
    root = ET.fromstring(xml_content)

    # Root feed channel ID fallback
    feed_channel_id_elem = root.find("yt:channelId", NS)
    feed_channel_id = feed_channel_id_elem.text if feed_channel_id_elem is not None else ""

    for entry in root.findall("atom:entry", NS):
        vid_elem = entry.find("yt:videoId", NS)
        video_id = vid_elem.text if vid_elem is not None and vid_elem.text else ""
        if not video_id:
            id_elem = entry.find("atom:id", NS)
            if id_elem is not None and id_elem.text:
                m = re.search(r"video:(.+)$", id_elem.text)
                if m:
                    video_id = m.group(1)
        if not video_id:
            continue

        ch_elem = entry.find("yt:channelId", NS)
        channel_id = ch_elem.text if ch_elem is not None and ch_elem.text else feed_channel_id

        title_elem = entry.find("atom:title", NS)
        title = title_elem.text if title_elem is not None and title_elem.text else "Untitled Video"

        pub_elem = entry.find("atom:published", NS)
        if pub_elem is not None and pub_elem.text:
            published_at = pub_elem.text
        else:
            upd_elem = entry.find("atom:updated", NS)
            published_at = upd_elem.text if upd_elem is not None and upd_elem.text else datetime.now(timezone.utc).isoformat()

        # Thumbnail URL
        thumb_elem = entry.find("media:group/media:thumbnail", NS)
        if thumb_elem is not None and thumb_elem.attrib.get("url"):
            thumbnail_url = thumb_elem.attrib["url"]
        else:
            thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        # View count from media:statistics/@views
        views = 0
        stat_elem = entry.find("media:group/media:community/media:statistics", NS)
        if stat_elem is not None and stat_elem.attrib.get("views"):
            try:
                views = int(stat_elem.attrib["views"])
            except (ValueError, TypeError):
                views = 0

        # Detect Shorts from title or link
        link_elem = entry.find("atom:link", NS)
        link_href = link_elem.attrib.get("href", "") if link_elem is not None else ""
        is_short = bool("#shorts" in title.lower() or "/shorts/" in link_href)

        videos.append({
            "video_id": video_id,
            "channel_id": channel_id,
            "title": title,
            "published_at": published_at,
            "thumbnail_url": thumbnail_url,
            "views": views,
            "view_count": views,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "duration_seconds": 0,
            "is_short": is_short,
        })

    return videos


def fetch_channel_feed(channel_id: str) -> List[Dict[str, Any]]:
    """
    Fetches and parses YouTube Channel XML RSS feed.
    Primary Layer 1 ingestion path: sub-second, zero-block video discovery.
    """
    if not channel_id or not channel_id.startswith("UC"):
        return []

    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        resp = requests.get(rss_url, headers=DEFAULT_HEADERS, timeout=8)
        if resp.status_code == 200:
            raw = getattr(resp, "content", None)
            if isinstance(raw, (bytes, bytearray)) and raw:
                return parse_feed_xml(raw)
            text = getattr(resp, "text", "")
            if isinstance(text, str):
                return parse_feed_xml(text)
            return parse_feed_xml(str(text))
        else:
            logger.warning(f"RSS feed returned status {resp.status_code} for channel {channel_id}")
    except Exception as e:
        logger.warning(f"Failed to fetch XML RSS for channel {channel_id}: {e}")

    return []


def fetch_channel_metadata(channel_id: str) -> Dict[str, Any]:
    """
    Returns channel metadata with session persistence / Innertube headers fallback.
    """
    channel_url = f"https://www.youtube.com/channel/{channel_id}"
    metadata = {
        "channel_id": channel_id,
        "name": "YouTube Creator",
        "url": channel_url,
        "handle": "",
        "avatar_url": "",
        "subscriber_count": 0,
    }

    # First attempt: Try RSS XML feed for channel title and author name
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        resp = requests.get(rss_url, headers=DEFAULT_HEADERS, timeout=6)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            title_elem = root.find("atom:title", NS)
            author_elem = root.find("atom:author/atom:name", NS)
            if title_elem is not None and title_elem.text:
                metadata["name"] = title_elem.text
            elif author_elem is not None and author_elem.text:
                metadata["name"] = author_elem.text
    except Exception as e:
        logger.debug(f"RSS metadata lookup error for {channel_id}: {e}")

    # Second attempt: Try HTML scrape with session headers for handle and avatar
    try:
        resp = requests.get(channel_url, headers=DEFAULT_HEADERS, timeout=6)
        if resp.status_code == 200:
            m_handle = re.search(r'"canonicalChannelUrl":"https://www\.youtube\.com/(@[^"]+)"', resp.text)
            if not m_handle:
                m_handle = re.search(r'"canonicalUrl":"https://www\.youtube\.com/(@[^"]+)"', resp.text)
            if m_handle:
                metadata["handle"] = m_handle.group(1)
                metadata["avatar_url"] = f"https://unavatar.io/youtube/{metadata['handle']}"
    except Exception as e:
        logger.debug(f"HTML metadata lookup error for {channel_id}: {e}")

    return metadata


def fetch_rss_timestamps(channel_id: str) -> Dict[str, str]:
    """
    Fetches exact ISO timestamps for the 15 most recent videos via channel RSS feed.
    Maintained for backward compatibility.
    """
    timestamps = {}
    videos = fetch_channel_feed(channel_id)
    for v in videos:
        timestamps[v["video_id"]] = v["published_at"]
    return timestamps


def parse_relative_time(text: str) -> Optional[datetime]:
    """Parses native YouTube relative time text (e.g. '12 days ago', '2 months ago', '3 hours ago') into a datetime."""
    if not text:
        return None
    now = datetime.now(timezone.utc)
    t = text.lower().strip()
    t = re.sub(r'^(streamed|premiered)\s+', '', t)

    m = re.search(r'(\d+)\s*(?:seconds?|secs?|s)\s*ago', t)
    if m:
        return now - timedelta(seconds=int(m.group(1)))
    m = re.search(r'(\d+)\s*(?:minutes?|mins?|m)\s*ago', t)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    m = re.search(r'(\d+)\s*(?:hours?|hrs?|h)\s*ago', t)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.search(r'(\d+)\s*(?:days?|d)\s*ago', t)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r'(\d+)\s*(?:weeks?|wks?|w)\s*ago', t)
    if m:
        return now - timedelta(weeks=int(m.group(1)))
    m = re.search(r'(\d+)\s*(?:months?|mos?|mo)\s*ago', t)
    if m:
        return now - timedelta(days=int(m.group(1)) * 30)
    m = re.search(r'(\d+)\s*(?:years?|yrs?|y)\s*ago', t)
    if m:
        return now - timedelta(days=int(m.group(1)) * 365)
    return None


def parse_duration_to_seconds(dur_str: str) -> int:
    """Parses a duration string like '14:34' or '1:02:15' into seconds."""
    if not dur_str:
        return 0
    parts = dur_str.split(':')
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:
            return int(parts[0])
    except ValueError:
        return 0
    return 0


def parse_views_text(v_str: str) -> int:
    """Parses view/subscriber text like '294K views' or '1.5M views' into an integer."""
    if not v_str:
        return 0
    v = v_str.lower().replace('views', '').replace('view', '').replace('subscribers', '').replace('subscriber', '').strip().replace(',', '')
    try:
        if 'm' in v:
            return int(float(v.replace('m', '').strip()) * 1_000_000)
        elif 'k' in v:
            return int(float(v.replace('k', '').strip()) * 1_000)
        return int(float(v))
    except ValueError:
        return 0


def fetch_exact_video_publish_date(video_id: str) -> Optional[str]:
    """Fetches exact ISO publish date for a single video via Innertube player endpoint."""
    try:
        payload = {
            'videoId': video_id,
            'context': {
                'client': {
                    'clientName': 'WEB',
                    'clientVersion': '2.20240410.01.00',
                    'hl': 'en',
                    'gl': 'US'
                }
            }
        }
        resp = requests.post('https://www.youtube.com/youtubei/v1/player', json=payload, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            micro = data.get('microformat', {}).get('playerMicroformatRenderer', {})
            return micro.get('publishDate') or micro.get('uploadDate')
    except Exception as e:
        logger.debug(f"Failed to fetch exact publish date for {video_id}: {e}")
    return None


def fetch_innertube_channel_videos(channel_id: str, max_videos: int = 40) -> Dict[str, Any]:
    """
    Fetches videos directly via YouTube's official Innertube browse endpoint.
    Retrieves authentic YouTube relative timestamps ('12 days ago', '2 months ago'),
    titles, durations, view counts, and channel metadata without date stripping.
    """
    if not channel_id or not channel_id.startswith("UC"):
        return {"channel": None, "videos": []}

    try:
        payload = {
            'context': {
                'client': {
                    'clientName': 'WEB',
                    'clientVersion': '2.20240410.01.00',
                    'hl': 'en',
                    'gl': 'US'
                }
            },
            'browseId': channel_id,
            'params': 'Egl2aWRlb3PyBgQKAjoA'
        }
        resp = requests.post('https://www.youtube.com/youtubei/v1/browse', json=payload, timeout=8)
        if resp.status_code != 200:
            return {"channel": None, "videos": []}
        data = resp.json()

        # Parse Channel Header
        header_strings = []
        def find_strings(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ('content', 'text') and isinstance(v, str):
                        header_strings.append(v)
                    else:
                        find_strings(v)
            elif isinstance(o, list):
                for item in o:
                    find_strings(item)
        find_strings(data.get('header', {}))

        channel_name = header_strings[0] if header_strings else "YouTube Creator"
        handle = next((s for s in header_strings if s.startswith('@')), "")
        sub_text = next((s for s in header_strings if 'subscriber' in s.lower()), "")

        # Parse Videos
        lockups = []
        def find_lockups(o):
            if isinstance(o, dict):
                if 'lockupViewModel' in o:
                    lockups.append(o['lockupViewModel'])
                for v in o.values():
                    find_lockups(v)
            elif isinstance(o, list):
                for item in o:
                    find_lockups(item)
        find_lockups(data)

        seen_vids = set()
        videos = []
        for l in lockups:
            vid = l.get('contentId')
            if not vid or vid in seen_vids:
                continue
            seen_vids.add(vid)

            texts = []
            def extract_vstrings(o):
                if isinstance(o, dict):
                    for k, v in o.items():
                        if k in ('content', 'text') and isinstance(v, str):
                            texts.append(v)
                        else:
                            extract_vstrings(o[k])
                elif isinstance(o, list):
                    for item in o:
                        extract_vstrings(item)
            extract_vstrings(l)

            duration_str, title, views_str, rel_date_str = '', '', '', ''
            for t in texts:
                if re.match(r'^\d+:\d+(?::\d+)?$', t):
                    duration_str = t
                elif 'view' in t.lower() and not views_str:
                    views_str = t
                elif 'ago' in t.lower() and not rel_date_str:
                    rel_date_str = t
                elif len(t) > len(title) and not any(k in t.lower() for k in ['queue', 'playlist', 'share', 'view', 'ago', 'badge']):
                    title = t

            dt = parse_relative_time(rel_date_str)
            published_at = dt.isoformat() if dt else None
            dur_secs = parse_duration_to_seconds(duration_str)
            views = parse_views_text(views_str)
            is_short = bool(dur_secs > 0 and dur_secs <= 60)

            videos.append({
                'video_id': vid,
                'channel_id': channel_id,
                'title': title or "Untitled Video",
                'url': f'https://www.youtube.com/watch?v={vid}',
                'thumbnail_url': f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg',
                'published_at': published_at,
                'views': views,
                'view_count': views,
                'duration_seconds': dur_secs,
                'is_short': is_short,
            })
            if len(videos) >= max_videos:
                break

        if not videos:
            return {"channel": None, "videos": []}

        channel_info = {
            "channel_id": channel_id,
            "name": channel_name,
            "handle": handle,
            "url": f"https://www.youtube.com/{handle}" if handle else f"https://www.youtube.com/channel/{channel_id}",
            "avatar_url": f"https://unavatar.io/youtube/{handle}" if handle else "",
            "subscriber_count": parse_views_text(sub_text),
        }
        return {"channel": channel_info, "videos": videos}
    except Exception as e:
        logger.warning(f"Innertube browse failed for {channel_id}: {e}")
        return {"channel": None, "videos": []}


def fetch_channel_videos(channel_url: str, max_videos: int = 40) -> Dict[str, Any]:
    """
    Multi-Layered Ingestion Engine:
    1. Primary Feed Layer: Uses YouTube Channel XML RSS for sub-second video discovery.
    2. Secondary Browse Layer: Uses YouTube Innertube Browse API for native video metadata,
       durations, view counts, and authentic relative timestamps without date stripping.
    3. Tertiary Fallback Layer: yt-dlp extraction with Innertube headers and session persistence.
    """
    target_url = clean_channel_url(channel_url)
    channel_id = extract_channel_id(target_url)

    # Primary Path: XML RSS Feed Layer
    if channel_id:
        feed_videos = fetch_channel_feed(channel_id)
        if feed_videos:
            channel_info = fetch_channel_metadata(channel_id)
            return {
                "channel": channel_info,
                "videos": feed_videos[:max_videos],
            }

        # Secondary Path: Innertube Browse API (fast, unblocked, authentic relative dates)
        innertube_data = fetch_innertube_channel_videos(channel_id, max_videos=max_videos)
        if innertube_data and innertube_data.get("videos"):
            return innertube_data

    # Tertiary Path: yt-dlp with Innertube headers and session persistence
    logger.info(f"Falling back to yt-dlp extraction for {channel_url}")
    if not target_url.endswith("/videos"):
        videos_tab_url = f"{target_url.rstrip('/')}/videos"
    else:
        videos_tab_url = target_url

    ydl_opts = get_ydl_options(max_videos=max_videos)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(videos_tab_url, download=False)
            if not res:
                return {"channel": None, "videos": []}

            resolved_channel_id = res.get("channel_id") or res.get("id") or channel_id or target_url
            channel_name = res.get("channel") or res.get("uploader") or res.get("title", "").replace(" - Videos", "")
            handle = res.get("uploader_id") or ""

            # Check RSS timestamps for exact published_at dates if channel_id is available
            rss_dates = fetch_rss_timestamps(resolved_channel_id) if resolved_channel_id.startswith("UC") else {}

            raw_entries = res.get("entries", []) or []
            processed_videos = []

            for entry in raw_entries:
                if not entry or not entry.get("id"):
                    continue
                vid = entry["id"]
                title = entry.get("title") or "Untitled Video"
                view_count = int(entry.get("view_count") or 0)
                duration = int(entry.get("duration") or 0)
                is_short = bool((duration > 0 and duration <= 60) or ("/shorts/" in entry.get("url", "")))

                thumbs = entry.get("thumbnails") or []
                thumbnail_url = thumbs[-1].get("url") if thumbs else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"

                published_at = rss_dates.get(vid)
                if not published_at and entry.get("timestamp"):
                    published_at = datetime.fromtimestamp(entry["timestamp"], tz=timezone.utc).isoformat()
                elif not published_at and entry.get("upload_date"):
                    try:
                        dt = datetime.strptime(str(entry["upload_date"]), "%Y%m%d").replace(tzinfo=timezone.utc)
                        published_at = dt.isoformat()
                    except Exception:
                        published_at = None

                # Fallback: Query exact publish date via Innertube player endpoint (no fake dates)
                if not published_at:
                    published_at = fetch_exact_video_publish_date(vid)

                processed_videos.append({
                    "video_id": vid,
                    "channel_id": resolved_channel_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "thumbnail_url": thumbnail_url,
                    "published_at": published_at,
                    "views": view_count,
                    "view_count": view_count,
                    "duration_seconds": duration,
                    "is_short": is_short,
                })

            channel_info = {
                "channel_id": resolved_channel_id,
                "name": channel_name or "YouTube Creator",
                "handle": handle,
                "url": target_url.replace("/videos", ""),
                "avatar_url": f"https://unavatar.io/youtube/{handle}" if handle else "",
                "subscriber_count": 0,
            }

            return {"channel": channel_info, "videos": processed_videos}

    except Exception as e:
        logger.error(f"Error fetching channel {channel_url}: {e}")
        return {"channel": None, "videos": []}


def sync_channel(channel_url: str) -> Dict[str, Any]:
    """Syncs a single channel and its videos into the SQLite database."""
    data = fetch_channel_videos(channel_url)
    channel = data.get("channel")
    videos = data.get("videos", [])

    if not channel:
        return {"success": False, "channel_id": None, "videos_count": 0}

    upsert_channel(
        channel_id=channel["channel_id"],
        name=channel["name"],
        url=channel["url"],
        handle=channel.get("handle", ""),
        avatar_url=channel.get("avatar_url", "")
    )

    saved_count = 0
    for v in videos:
        view_count = v.get("views", v.get("view_count", 0))
        upsert_video(
            video_id=v["video_id"],
            channel_id=channel["channel_id"],
            title=v["title"],
            url=v["url"],
            thumbnail_url=v["thumbnail_url"],
            published_at=v["published_at"],
            view_count=view_count,
            duration_seconds=v.get("duration_seconds", 0),
            is_short=bool(v.get("is_short", 0))
        )
        saved_count += 1

    return {"success": True, "channel_id": channel["channel_id"], "videos_count": saved_count}
