"""Creator collaboration and guest detection engine.

Detects collaborator and guest creators featured in video titles and descriptions
(e.g. 'Matt Pocock: The Most Valuable Skill to Learn in the Age of AI' or 'Interview with Harrison Chase'),
cross-references with tracked channels, and provides 1-click channel tracking.
"""
import re
from typing import Optional, Dict, Any, List
from radar.db import get_db

# Common non-person prefixes before colons in tech video titles
IGNORED_TITLE_PREFIXES = {
    "tutorial", "guide", "review", "update", "warning", "breaking", "news",
    "part", "ep", "episode", "vol", "volume", "how to", "why", "what",
    "live", "qa", "q&a", "ama", "interview", "deep dive", "discussion",
    "lesson", "course", "crash course", "masterclass", "demo", "overview",
    "case study", "vlog", "shorts", "recap", "summary", "analysis", "show",
    "daily", "weekly", "special", "edition", "podcast", "stream", "rant"
}

def clean_guest_name(name: str) -> str:
    """Cleans punctuation, quotes, and extraneous text from extracted guest names."""
    if not name:
        return ""
    # Strip quotes, brackets, emojis, extra spaces
    cleaned = re.sub(r'[\'\"“”‘’`()\[\]{}|#]', '', name).strip()
    # Strip trailing punctuation
    cleaned = re.sub(r'[!?,.:;]+$', '', cleaned).strip()
    return cleaned

def extract_guest_candidate(title: str, description: str = "", host_name: str = "") -> Optional[str]:
    """
    Extracts potential collaborator or guest name from title and description.
    Handles colon prefix, 'with', 'ft.', 'feat.', 'x', and '@handle'.
    """
    if not title:
        return None

    cleaned_title = title.strip()

    # 1. Check for @handle mentions in title (e.g. "Talking with @mattpocockuk")
    handle_match = re.search(r'@([a-zA-Z0-9_.-]{3,30})', cleaned_title)
    if handle_match:
        handle = f"@{handle_match.group(1)}"
        if host_name.lower() not in handle.lower():
            return handle

    # 2. Check for Prefix format: "{Guest}: {Topic}"
    # e.g., "Matt Pocock: The Most Valuable Skill to Learn in the Age of AI"
    if ":" in cleaned_title:
        parts = cleaned_title.split(":", 1)
        prefix = clean_guest_name(parts[0])
        # Check if prefix looks like a person's name (1 to 3 words, each capitalized or camelCase)
        words = prefix.split()
        if 1 <= len(words) <= 3 and prefix.lower() not in IGNORED_TITLE_PREFIXES:
            # Check not starting with generic indicators
            is_valid_name = True
            for w in words:
                if not (w[0].isupper() or w.startswith("@")):
                    is_valid_name = False
                    break
            if is_valid_name and (not host_name or prefix.lower() not in host_name.lower()):
                return prefix

    # 3. Check for "with / ft. / feat. / featuring / x / Collab with" patterns
    collab_patterns = [
        r'(?:collab\s+with|interview\s+with|talking\s+with|chat\s+with)\s+([A-Z][a-zA-Z0-9_.-]+(?:\s+[A-Z][a-zA-Z0-9_.-]+){0,2})',
        r'(?:\s+ft\.|\s+feat\.|\s+featuring|\s+w\/|\s+with)\s+([A-Z][a-zA-Z0-9_.-]+(?:\s+[A-Z][a-zA-Z0-9_.-]+){0,2})',
        r'(?:^|\s)([A-Z][a-zA-Z0-9_.-]+(?:\s+[A-Z][a-zA-Z0-9_.-]+){0,1})\s+x\s+([A-Z][a-zA-Z0-9_.-]+(?:\s+[A-Z][a-zA-Z0-9_.-]+){0,1})',
    ]

    for pat in collab_patterns:
        m = re.search(pat, cleaned_title, re.IGNORECASE)
        if m:
            matched_name = clean_guest_name(m.group(1))
            # Avoid matching host name
            if matched_name and (not host_name or matched_name.lower() not in host_name.lower()):
                words = matched_name.split()
                if words and words[0].lower() not in IGNORED_TITLE_PREFIXES:
                    return matched_name

    # 4. Check description for @handle if title had none
    if description:
        desc_handle_match = re.search(r'@([a-zA-Z0-9_.-]{3,30})', description[:500])
        if desc_handle_match:
            handle = f"@{desc_handle_match.group(1)}"
            if host_name.lower() not in handle.lower():
                return handle

    return None

def find_tracked_channel(guest_name: str) -> Optional[Dict[str, Any]]:
    """Looks up whether the guest is already tracked in our channels table."""
    if not guest_name:
        return None

    clean_term = guest_name.strip().lstrip("@")
    term = f"%{clean_term}%"

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT channel_id, name, handle, url, avatar_url, category, median_views
            FROM channels
            WHERE name LIKE ?
               OR handle LIKE ?
               OR REPLACE(handle, '@', '') LIKE ?
            LIMIT 1
        """, (term, term, term))
        row = cursor.fetchone()
        return dict(row) if row else None

def detect_collab_for_video(title: str, description: str = "", host_name: str = "") -> Optional[Dict[str, Any]]:
    """
    Detects if a video is a collaboration or guest feature, and checks tracking status.
    Returns structured collab metadata or None.
    """
    guest_candidate = extract_guest_candidate(title, description, host_name)
    if not guest_candidate:
        return None

    tracked = find_tracked_channel(guest_candidate)
    if tracked:
        return {
            "guest_name": tracked["name"],
            "guest_handle": tracked["handle"],
            "channel_id": tracked["channel_id"],
            "is_tracked": True,
            "channel_url": tracked["url"],
            "avatar_url": tracked.get("avatar_url", "")
        }
    else:
        # Candidate not tracked yet - provide actionable tracking recommendation
        clean_handle = f"@{guest_candidate.lstrip('@').lower().replace(' ', '')}"
        return {
            "guest_name": guest_candidate,
            "guest_handle": clean_handle if guest_candidate.startswith("@") else f"@{guest_candidate.replace(' ', '')}",
            "channel_id": None,
            "is_tracked": False,
            "channel_url": f"https://www.youtube.com/results?search_query={guest_candidate}",
            "avatar_url": ""
        }

def annotate_feed_with_collabs(videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Annotates each video dictionary in the feed with `collab` metadata."""
    for v in videos:
        title = v.get("title", "")
        host_name = v.get("channel_name", "")
        v["collab"] = detect_collab_for_video(title=title, host_name=host_name)
    return videos
