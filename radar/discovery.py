"""Aggressive Channel Growth Engine (Sections A, B, C).

Provides three layers of creator discovery:
- Section A: Curated batch of 50+ tier-1 creators (Vibe Coding, AI Agents, Automations, AGI Research, UI/UX).
- Section B: Creator Graph Crawler (featured channels & community network expansion).
- Section C: Emerging Topic & Keyword Ingestion (discovers breakout creators from viral search queries).
"""
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Set, Optional
from radar.db import get_db, upsert_channel, get_all_channels
from radar.fetcher import sync_channel, extract_channel_id

# Section A: 50+ Curated Top Creators Across Core AI & Tech Verticals
CURATED_DISCOVERY_CHANNELS: List[Dict[str, str]] = [
    # --- 1. Vibe Coding & Fullstack AI Builders ---
    {"handle": "@AlexZiskind", "name": "Alex Ziskind", "category": "Developer Tools"},
    {"handle": "@WebDevCody", "name": "Web Dev Cody", "category": "Developer Tools"},
    {"handle": "@SonnySangha", "name": "Sonny Sangha", "category": "Developer Tools"},
    {"handle": "@CodeWithAntonio", "name": "Code With Antonio", "category": "Developer Tools"},
    {"handle": "@HiteshChoudharydotcom", "name": "Hitesh Choudhary", "category": "Developer Tools"},
    {"handle": "@PiyushGargdev", "name": "Piyush Garg", "category": "Developer Tools"},
    {"handle": "@developedbyed", "name": "Dev Ed", "category": "Developer Tools"},
    {"handle": "@freecodecamp", "name": "freeCodeCamp", "category": "Developer Tools"},
    {"handle": "@TraversyMedia", "name": "Traversy Media", "category": "Developer Tools"},
    {"handle": "@NetworkChuck", "name": "NetworkChuck", "category": "Developer Tools"},
    {"handle": "@jherr", "name": "Jack Herrington", "category": "Developer Tools"},
    {"handle": "@SyntaxFM", "name": "Syntax", "category": "Developer Tools"},
    {"handle": "@DaveGrayTeachesCode", "name": "Dave Gray", "category": "Developer Tools"},
    {"handle": "@hnasr", "name": "Hussein Nasser", "category": "Developer Tools"},
    {"handle": "@ArjanCodes", "name": "ArjanCodes", "category": "Developer Tools"},
    {"handle": "@ThePrimeTimeagen", "name": "ThePrimeagen", "category": "Developer Tools"},
    {"handle": "@t3dotgg", "name": "Theo - t3.gg", "category": "Developer Tools"},
    {"handle": "@Fireship", "name": "Fireship", "category": "Developer Tools"},
    {"handle": "@mattpocockuk", "name": "Matt Pocock", "category": "Developer Tools"},

    # --- 2. AI Agents & Autonomous Systems ---
    {"handle": "@indydevdan", "name": "IndyDevDan", "category": "AI Agents"},
    {"handle": "@AIJasonZ", "name": "AI Jason", "category": "AI Agents"},
    {"handle": "@davidondrej", "name": "David Ondrej", "category": "AI Agents"},
    {"handle": "@ColeMedin", "name": "Cole Medin", "category": "AI Agents"},
    {"handle": "@PromptEngineering", "name": "Prompt Engineering", "category": "AI Agents"},
    {"handle": "@worldofai", "name": "WorldofAI", "category": "AI Agents"},
    {"handle": "@parthknowsai", "name": "Parthknowsai", "category": "AI Agents"},
    {"handle": "@Ai.Vishnuvijayan", "name": "Vishnu Vijayan", "category": "AI Agents"},
    {"handle": "@LeonvanZyl", "name": "Leon van Zyl", "category": "AI Agents"},
    {"handle": "@AllAboutAI", "name": "All About AI", "category": "AI Agents"},
    {"handle": "@SamWitteveen", "name": "Sam Witteveen", "category": "AI Agents"},
    {"handle": "@jamesbriggs", "name": "James Briggs", "category": "AI Agents"},
    {"handle": "@LangChain", "name": "LangChain Official", "category": "AI Agents"},
    {"handle": "@CrewAI", "name": "CrewAI Tutorials", "category": "AI Agents"},

    # --- 3. Automations & Workflows ---
    {"handle": "@LiamOttley", "name": "Liam Ottley", "category": "Automations"},
    {"handle": "@vaibhavsisinty", "name": "Vaibhav Sisinty", "category": "Automations"},
    {"handle": "@nateherk", "name": "Nate Herk | AI Automation", "category": "Automations"},
    {"handle": "@JulianGoldieSEO", "name": "Julian Goldie", "category": "Automations"},
    {"handle": "@echoknowledge", "name": "echoknowledge", "category": "Automations"},
    {"handle": "@flowiseai", "name": "Flowise AI", "category": "Automations"},
    {"handle": "@dify_ai", "name": "Dify AI", "category": "Automations"},
    {"handle": "@botpress", "name": "Botpress Studio", "category": "Automations"},
    {"handle": "@voiceflow", "name": "Voiceflow Masterclass", "category": "Automations"},

    # --- 4. AI News & Emerging Breakthroughs ---
    {"handle": "@matthew_berman", "name": "Matthew Berman", "category": "AI News"},
    {"handle": "@WesRoth", "name": "Wes Roth", "category": "AI News"},
    {"handle": "@wdf_ai", "name": "Sumit Paul", "category": "AI News"},
    {"handle": "@therundownai", "name": "The Rundown AI", "category": "AI News"},
    {"handle": "@maboris", "name": "Matt Wolfe", "category": "AI News"},
    {"handle": "@theaibreakdown", "name": "The AI Breakdown", "category": "AI News"},

    # --- 5. AGI Research & Deep Theory ---
    {"handle": "@TwoMinutePapers", "name": "Two Minute Papers", "category": "AGI Research"},
    {"handle": "@aiexplained-official", "name": "AI Explained", "category": "AGI Research"},
    {"handle": "@YannicKilcher", "name": "Yannic Kilcher", "category": "AGI Research"},
    {"handle": "@AndrejKarpathy", "name": "Andrej Karpathy", "category": "AGI Research"},
    {"handle": "@DwarkeshPatel", "name": "Dwarkesh Patel", "category": "AGI Research"},
    {"handle": "@lexfridman", "name": "Lex Fridman Podcast", "category": "AGI Research"},
    {"handle": "@3blue1brown", "name": "3Blue1Brown", "category": "AGI Research"},
    {"handle": "@sentdex", "name": "sentdex", "category": "AGI Research"},
    {"handle": "@aishwaryasrinivasan", "name": "Aishwarya Srinivasan", "category": "AGI Research"},

    # --- 6. UI/UX & Design Systems ---
    {"handle": "@mobbindesign", "name": "Mobbin", "category": "Developer Tools"},
    {"handle": "@FluxAcademy", "name": "Flux Academy", "category": "Developer Tools"},
    {"handle": "@MalewiczHype", "name": "Michal Malewicz", "category": "Developer Tools"},
    {"handle": "@DesignCourse", "name": "DesignCourse", "category": "Developer Tools"},
    {"handle": "@CharliMarieTV", "name": "Charli Marie TV", "category": "Developer Tools"},
    {"handle": "@HowardPinsky", "name": "Howard Pinsky", "category": "Developer Tools"},
]

# Non-negotiable Blacklist: Corporate Course Mills, Burner Scrapers & Generic Non-Tech
BLACKLISTED_HANDLES: Set[str] = {
    "@simplilearnofficial", "@intellipaat", "@edureka", "@wscubetech",
    "@tedx", "@khanacademy", "@markrober", "@geeksforgeeks",
    "@greatlearning", "@codingninjas", "@aiautomationofficially",
    "@rivntech", "@codeimprove", "@codingwithctobhaiya",
    "@karpathy"  # Squatter account with 126 subs, real is @AndrejKarpathy
}

BLACKLISTED_NAME_KEYWORDS: List[str] = [
    "simplilearn", "intellipaat", "edureka", "wscube", "tedx",
    "khan academy", "mark rober", "geeksforgeeks", "great learning",
    "coding ninjas", "ai automation official", "passive income", "make money",
    "bhaiya"
]

from radar.seed_channels import SEED_CHANNELS

# Curated & Seed Handles Whitelist
CURATED_HANDLES_SET: Set[str] = {
    (c.get("handle") or "").lower().strip() for c in SEED_CHANNELS if c.get("handle")
} | {
    (c.get("handle") or "").lower().strip() for c in CURATED_DISCOVERY_CHANNELS if c.get("handle")
} | {
    "@mobbindesign", "@vaibhavsisinty", "@nateherk", "@parthknowsai",
    "@wdf_ai", "@ai.vishnuvijayan", "@aishwaryasrinivasan", "@techie007",
    "@medyrenaldyshorts", "@mattpocockuk", "@fireship", "@t3dotgg",
    "@theprimetimeagen", "@theprimeagen", "@andrejkarpathy", "@lexfridman",
    "@3blue1brown", "@sentdex", "@yannickilcher", "@dwarkeshpatel",
    "@twominutepapers", "@aiexplained-official", "@gregisenberg", "@vivekmishrayt"
}

APPROVED_CATEGORIES: Set[str] = {
    "AI Agents", "Automations", "AI News", "Developer Tools", "AGI Research"
}

APPROVED_NICHE_KEYWORDS: List[str] = [
    "ai", "agent", "llm", "code", "dev", "cursor", "vibe", "langchain",
    "crewai", "n8n", "automation", "python", "frontend", "backend", "deepseek",
    "gpt", "claude", "design", "ui", "ux", "framer", "software", "tech",
    "math", "paper", "research", "robot", "workflow", "model", "typescript",
    "javascript", "react", "tutorial", "build", "prompt", "engineer",
    "machine learning", "neural", "data", "cloud", "developer", "science",
    "startup", "product", "business", "growth", "founder", "saas"
]

def is_channel_eligible(
    handle: str,
    name: str,
    category: Optional[str] = None,
    median_views: int = 0,
    max_views: int = 0
) -> bool:
    """
    Evaluates whether a channel candidate qualifies for catalog inclusion.
    Enforces quality > volume: zero slop, zero course mills, zero dead accounts.
    """
    h_clean = (handle or "").lower().strip()
    if h_clean and not h_clean.startswith("@"):
        h_clean = f"@{h_clean}"
    n_clean = (name or "").lower().strip()

    # 1. Hard Blacklist Check (Zero-tolerance for course mills & generic entertainment)
    if h_clean in BLACKLISTED_HANDLES:
        return False
    if any(term in n_clean for term in BLACKLISTED_NAME_KEYWORDS):
        return False

    # 2. Known Curated & Seed Creators Check
    if h_clean in CURATED_HANDLES_SET:
        return True

    # 3. Approved Pillar Category
    if category and category in APPROVED_CATEGORIES:
        return True

    # 4. Niche alignment keyword check
    combined = f"{h_clean} {n_clean}"
    if any(k in combined for k in APPROVED_NICHE_KEYWORDS):
        # Micro-channel validation hurdle
        # If channel has video history, must demonstrate >= 1,000 views on at least one video
        if max_views > 0 and max_views < 1000:
            return False
        return True

    # 5. Established tech creator with proven viewership (> 10,000 median views or > 20,000 max views)
    if median_views >= 10000 or max_views >= 20000:
        return True

    # 6. Active creator with proven view traction
    if max_views >= 1000 or median_views > 0:
        return True

    return False

def prune_ineligible_channels() -> int:
    """Prunes blacklisted course mills, scrapers, and dead accounts from the catalog.
    Never prunes curated, seed, or user-added creators."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT channel_id, name, handle, category, median_views,
                   (SELECT MAX(view_count) FROM videos WHERE videos.channel_id = channels.channel_id) as max_views,
                   (SELECT COUNT(*) FROM videos WHERE videos.channel_id = channels.channel_id) as vcount
            FROM channels
        """)
        rows = cursor.fetchall()
        deleted = 0
        for r in rows:
            cid = r["channel_id"]
            name = r["name"]
            handle = r["handle"]
            category = r["category"]
            med = r["median_views"]
            max_v = r["max_views"]
            vcount = r["vcount"]

            h_clean = (handle or "").lower().strip()
            if h_clean and not h_clean.startswith("@"):
                h_clean = f"@{h_clean}"
            n_clean = (name or "").lower().strip()

            # NEVER delete curated, user-added, or seed channels
            if h_clean in CURATED_HANDLES_SET:
                continue

            # Check if explicitly blacklisted (course mills, scraper channels)
            is_blacklisted = (
                h_clean in BLACKLISTED_HANDLES
                or any(term in n_clean for term in BLACKLISTED_NAME_KEYWORDS)
            )
            # Check if dead bot scraper with zero views
            is_dead_scraper = (vcount >= 5 and (max_v or 0) < 50)

            if is_blacklisted or is_dead_scraper:
                conn.execute("DELETE FROM videos WHERE channel_id = ?", (cid,))
                conn.execute("DELETE FROM outliers WHERE channel_id = ?", (cid,))
                conn.execute("DELETE FROM channels WHERE channel_id = ?", (cid,))
                deleted += 1
        return deleted

# Section C: High-Signal Search Keywords
HIGH_SIGNAL_KEYWORDS = [
    "Cursor AI tutorial",
    "vibe coding workflow",
    "n8n AI agent tutorial",
    "Claude 3.7 Sonnet agent",
    "LangGraph multi-agent build",
    "open source AI agent 2026",
    "local LLM agent tutorial"
]

def import_curated_section_a(sync_videos: bool = False) -> Dict[str, Any]:
    """Imports Section A curated creators into channels table. Optionally syncs recent videos."""
    existing_channels = get_all_channels()
    existing_handles = {c.get("handle", "").lower() for c in existing_channels if c.get("handle")}
    existing_ids = {c.get("channel_id", "") for c in existing_channels if c.get("channel_id")}

    added_channels: List[str] = []
    skipped_channels: List[str] = []

    for item in CURATED_DISCOVERY_CHANNELS:
        handle = item["handle"]
        if handle.lower() in existing_handles:
            skipped_channels.append(handle)
            continue

        cid = extract_channel_id(handle)
        if cid and cid not in existing_ids:
            url = f"https://www.youtube.com/{handle}"
            avatar = f"https://unavatar.io/youtube/{handle}"
            upsert_channel(
                channel_id=cid,
                name=item["name"],
                url=url,
                handle=handle,
                avatar_url=avatar,
                category=item["category"],
                subscriber_count=50000
            )
            existing_handles.add(handle.lower())
            existing_ids.add(cid)
            added_channels.append(handle)

            if sync_videos:
                try:
                    sync_channel(cid)
                except Exception as e:
                    pass
        else:
            skipped_channels.append(handle)

    return {
        "section": "Section A (Curated Creators)",
        "added_count": len(added_channels),
        "skipped_count": len(skipped_channels),
        "added": added_channels
    }

def crawl_featured_channels_section_b(max_channels_to_crawl: int = 15) -> Dict[str, Any]:
    """Crawls featured channels and recommended channels from tracked creators' YouTube homepages."""
    existing_channels = get_all_channels()
    existing_handles = {c.get("handle", "").lower() for c in existing_channels if c.get("handle")}
    existing_ids = {c.get("channel_id", "") for c in existing_channels if c.get("channel_id")}

    discovered_handles: Set[str] = set()

    # Sample active channels with handles
    seed_pool = [c for c in existing_channels if c.get("handle") and not c["handle"].startswith("@_")][:max_channels_to_crawl]

    for ch in seed_pool:
        handle = ch["handle"]
        url = f"https://www.youtube.com/{handle}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                # Find featured channel handles in HTML
                matches = re.findall(r'\"canonicalBaseUrl\":\"\/@([a-zA-Z0-9_.-]{3,30})\"', html)
                for m in matches:
                    cand = f"@{m}"
                    if cand.lower() not in existing_handles and cand.lower() != handle.lower():
                        discovered_handles.add(cand)
        except Exception:
            continue

    # Upsert newly discovered channels that pass eligibility
    added_from_crawl: List[str] = []
    for cand in list(discovered_handles)[:25]:
        clean_name = cand.lstrip("@")
        if not is_channel_eligible(handle=cand, name=clean_name):
            continue
        cid = extract_channel_id(cand)
        if cid and cid not in existing_ids:
            upsert_channel(
                channel_id=cid,
                name=clean_name,
                url=f"https://www.youtube.com/{cand}",
                handle=cand,
                avatar_url=f"https://unavatar.io/youtube/{cand}",
                category="AI Agents",
                subscriber_count=20000
            )
            existing_handles.add(cand.lower())
            existing_ids.add(cid)
            added_from_crawl.append(cand)

    return {
        "section": "Section B (Creator Graph Crawl)",
        "discovered_handles_count": len(discovered_handles),
        "added_count": len(added_from_crawl),
        "added": added_from_crawl
    }

def discover_keyword_creators_section_c(keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """Discovers high-signal breakout creators from YouTube video search results on emerging topics."""
    target_keywords = keywords or HIGH_SIGNAL_KEYWORDS
    existing_channels = get_all_channels()
    existing_handles = {c.get("handle", "").lower() for c in existing_channels if c.get("handle")}
    existing_ids = {c.get("channel_id", "") for c in existing_channels if c.get("channel_id")}

    discovered_creators: Dict[str, Dict[str, str]] = {}

    for kw in target_keywords:
        encoded = urllib.parse.quote(kw)
        search_url = f"https://www.youtube.com/results?search_query={encoded}&sp=CAI%253D"  # Upload date sorted
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                # Extract creator handles from search result canonical links
                handle_matches = re.findall(r'\"canonicalBaseUrl\":\"\/@([a-zA-Z0-9_.-]{3,30})\"', html)
                for h in handle_matches:
                    cand = f"@{h}"
                    if cand.lower() not in existing_handles:
                        discovered_creators[cand] = {
                            "handle": cand,
                            "name": h,
                            "category": "Developer Tools" if "code" in kw.lower() or "cursor" in kw.lower() else "AI Agents"
                        }
        except Exception:
            continue

    added_from_keywords: List[str] = []
    for cand, info in list(discovered_creators.items())[:20]:
        if not is_channel_eligible(handle=cand, name=info["name"]):
            continue
        cid = extract_channel_id(cand)
        if cid and cid not in existing_ids:
            upsert_channel(
                channel_id=cid,
                name=info["name"],
                url=f"https://www.youtube.com/{cand}",
                handle=cand,
                avatar_url=f"https://unavatar.io/youtube/{cand}",
                category=info["category"],
                subscriber_count=25000
            )
            existing_handles.add(cand.lower())
            existing_ids.add(cid)
            added_from_keywords.append(info["name"])

    return {
        "section": "Section C (Topic & Keyword Discovery)",
        "added_count": len(added_from_keywords),
        "added": added_from_keywords
    }

def run_all_growth_sections(sync_curated: bool = True) -> Dict[str, Any]:
    """Runs Sections A, B, and C consecutively for aggressive creator catalog scaling."""
    res_a = import_curated_section_a(sync_videos=sync_curated)
    res_b = crawl_featured_channels_section_b()
    res_c = discover_keyword_creators_section_c()

    total_added = res_a["added_count"] + res_b["added_count"] + res_c["added_count"]
    total_in_db = len(get_all_channels())

    return {
        "status": "success",
        "total_newly_added": total_added,
        "total_catalog_size": total_in_db,
        "details": {
            "section_a": res_a,
            "section_b": res_b,
            "section_c": res_c
        }
    }

if __name__ == "__main__":
    import json
    result = run_all_growth_sections(sync_curated=False)
    print(json.dumps(result, indent=2))
