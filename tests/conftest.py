"""Pytest test configuration and isolated fixtures for Niche Outlier Radar."""
import os
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

import radar.config
import radar.db
import radar.seed_channels
from app.main import app

# Authoritative categories per ORIGINAL_REQUEST.md & PROJECT.md
AUTHORITATIVE_CATEGORIES = [
    "AI Agents",
    "Automations",
    "AI News",
    "Developer Tools",
    "AGI Research"
]

@pytest.fixture(scope="session", autouse=True)
def isolated_test_db_session(tmp_path_factory):
    """
    Session-level database isolation fixture:
    Redirects radar.config.DB_PATH and radar.db.DB_PATH to an isolated SQLite database.
    Guarantees that production `data/radar.db` is NEVER touched or corrupted by tests.
    """
    temp_dir = tmp_path_factory.mktemp("radar_test_data")
    test_db_path = temp_dir / "test_radar.db"

    # Set both references to ensure all database calls route to isolated DB
    radar.config.DB_PATH = test_db_path
    radar.db.DB_PATH = test_db_path

    # Initialize tables
    radar.db.init_db()

    # Ensure schema enhancements (category in channels, transcripts table)
    with radar.db.get_db() as conn:
        cursor = conn.execute("PRAGMA table_info(channels)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "category" not in columns:
            try:
                conn.execute("ALTER TABLE channels ADD COLUMN category TEXT")
            except sqlite3.OperationalError:
                pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE NOT NULL,
                transcript TEXT NOT NULL,
                source TEXT DEFAULT 'api',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos (video_id) ON DELETE CASCADE
            );
        """)

    # Seed default channels so API endpoints have baseline data
    radar.seed_channels.seed_default_channels()

    yield test_db_path

@pytest.fixture
def isolated_test_db(isolated_test_db_session):
    """Function-level alias pointing to the isolated test database."""
    return isolated_test_db_session

@pytest.fixture
def client(isolated_test_db):
    """FastAPI TestClient fixture bound to the isolated test database."""
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture
def sample_atom_xml():
    """Generates a standard valid YouTube Atom RSS feed XML string."""
    def _generate(channel_id="UC_SAMPLE_123", channel_name="Sample AI Channel", entries=None):
        if entries is None:
            entries = [
                {
                    "video_id": "vid_xml_01",
                    "title": "Build Autonomous Agents with LangGraph & MCP",
                    "published": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                    "views": 48200
                },
                {
                    "video_id": "vid_xml_02",
                    "title": "State of AI 2026: Reasoning Models Teardown",
                    "published": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
                    "views": 95000
                }
            ]

        entries_xml = ""
        for e in entries:
            entries_xml += f"""
    <entry>
        <id>yt:video:{e['video_id']}</id>
        <yt:videoId>{e['video_id']}</yt:videoId>
        <yt:channelId>{channel_id}</yt:channelId>
        <title>{e['title']}</title>
        <link rel="alternate" href="https://www.youtube.com/watch?v={e['video_id']}"/>
        <published>{e['published']}</published>
        <updated>{e['published']}</updated>
        <media:group>
            <media:title>{e['title']}</media:title>
            <media:thumbnail url="https://i.ytimg.com/vi/{e['video_id']}/hqdefault.jpg" width="480" height="360"/>
            <media:community>
                <media:statistics views="{e['views']}"/>
            </media:community>
        </media:group>
    </entry>
            """

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
    <link rel="self" href="https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"/>
    <id>yt:channel:{channel_id}</id>
    <yt:channelId>{channel_id}</yt:channelId>
    <title>{channel_name}</title>
    <author>
        <name>{channel_name}</name>
        <uri>https://www.youtube.com/channel/{channel_id}</uri>
    </author>
    {entries_xml}
</feed>"""
        return xml_content

    return _generate

@pytest.fixture
def mock_groq_blueprint():
    """Returns a deterministic structured Actionable Creator Card mock payload."""
    return {
        "category": "AI Agents",
        "summary_bullets": [
            "Introduced distributed multi-agent state machines using SQLite WAL persistence.",
            "Demonstrated sub-200ms tool dispatch across local MCP servers.",
            "Benchmarked latency reduction of 42% against traditional REST loops."
        ],
        "tools_mentioned": ["FastAPI", "Groq Whisper", "Model Context Protocol", "SQLite"],
        "viral_hook_angle": "Focuses on solving developer frustration with agent timeouts by replacing polling with reactive wakeups. Actionable reproduction: build a 3-step live demo showing zero-lag tool chaining."
    }

@pytest.fixture
def seed_catalog_helper():
    """Helper to seed arbitrary numbers of channels across the 5 categories."""
    def _seed(count=100):
        channels_created = []
        for i in range(count):
            cat = AUTHORITATIVE_CATEGORIES[i % len(AUTHORITATIVE_CATEGORIES)]
            ch_id = f"UC_SEEDED_CHANNEL_{i:03d}"
            name = f"Creator {i:03d} - {cat}"
            handle = f"@creator_{i:03d}"
            url = f"https://www.youtube.com/{handle}"
            
            radar.db.upsert_channel(
                channel_id=ch_id,
                name=name,
                url=url,
                handle=handle,
                avatar_url=f"https://unavatar.io/youtube/{handle}",
                subscriber_count=(i + 1) * 10000
            )

            # Update category
            with radar.db.get_db() as conn:
                conn.execute("UPDATE channels SET category = ? WHERE channel_id = ?", (cat, ch_id))

            channels_created.append({
                "channel_id": ch_id,
                "name": name,
                "handle": handle,
                "category": cat,
                "url": url
            })
        return channels_created

    return _seed
