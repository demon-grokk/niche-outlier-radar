# 📡 Niche Outlier Radar

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.140%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/Database-Embedded%20SQLite%20(Zero--Config)-003B57.svg)](https://sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **YouTube-Native AI/Tech Discovery Platform & Outlier Intelligence Engine.**  
> Track curated channels, calculate rolling 90-day medians, surface breakout viral videos, and generate creator blueprints — with zero external database dependencies.

---

## 🌟 Highlights

- **Embedded Zero-Config Database**: Powered by SQLite (WAL mode). Requires **zero** database servers (no Postgres, no MySQL, no Docker) — tables and channel catalogs are created automatically on launch.
- **Resilient 3-Layer Ingestion**:
  1. *Sub-Second RSS*: Instant video discovery and view-count tracking via YouTube Channel XML feeds with zero rate-limit blocks.
  2. *Session & Innertube Headers*: Fallback client headers for restricted metadata.
  3. *Audio Transcript Fallback*: `yt-dlp` stream extraction + `ffmpeg` slice + Groq Whisper (`whisper-large-v3`) fallback on missing captions.
- **Statistical Outlier Detection**: Computes rolling 90-day baseline medians for channels and tags breakout videos (`multiplier = video.views / median`, e.g. `🔥 4.2× Outlier`).
- **YouTube-Native Dark Dashboard**: Custom dark UI (`#0f0f0f`), responsive grid, category chip filters, and creator blueprint modals.
- **Cross-Platform Ready**: Runs seamlessly out of the box on **macOS**, **Linux**, and **Windows**.

---

## 💾 How Database Setup Works

Niche Outlier Radar uses an **embedded SQLite database** (`data/radar.db`).

You **do not need** to install, configure, or run an external database server:
1. **Automatic Initialization**: The moment you run `python run.py`, the system verifies and creates the `data/` directory, initializes all SQLite tables (`channels`, `videos`, `outliers`, `sync_logs`, `transcripts`), and applies required performance indexes.
2. **Channel Catalog Seeding**: Default high-signal AI/Tech channels (AI Agents, Automations, AI News, Developer Tools, AGI Research) are automatically seeded on first launch.
3. **Data Sync**:
   - To sync videos and calculate outliers on startup, pass `--sync`:
     ```bash
     python run.py --sync
     ```
   - Alternatively, open the web dashboard (`http://localhost:8000`) and click **"⚡ Sync Now"** to trigger a sync at any time.
4. **Headless / CI Initialization**:
   If you want to initialize the database schema and channel catalog without keeping the web server running:
   ```bash
   python run.py --init-only
   ```

---

## 📋 System Requirements

| Requirement | Supported Versions | Notes |
| :--- | :--- | :--- |
| **Python** | `3.10` – `3.13` | Core runtime |
| **Operating System** | macOS, Linux, Windows | Fully cross-platform |
| **ffmpeg** *(Optional)* | Any recent release | Only needed if transcribing videos that lack YouTube captions via Whisper audio fallback |

### Installing ffmpeg (Optional)

- **macOS** (Homebrew):
  ```bash
  brew install ffmpeg
  ```
- **Linux** (Debian/Ubuntu):
  ```bash
  sudo apt update && sudo apt install -y ffmpeg
  ```
- **Windows** (winget / Chocolatey):
  ```powershell
  winget install Gyan.FFmpeg
  # or: choco install ffmpeg
  ```

---

## 🚀 Quick Start Guide

### Step 1: Clone Repository

```bash
git clone https://github.com/demon-grokk/niche-outlier-radar.git
cd niche-outlier-radar
```

---

### Step 2: Set Up Virtual Environment

You can use either [uv](https://github.com/astral-sh/uv) (recommended for blazing speed) or standard Python `venv`.

#### Option A: Using `uv` (Recommended)

##### macOS / Linux
```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

##### Windows (PowerShell)
```powershell
uv venv .venv
.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

---

#### Option B: Using Standard Python `venv`

##### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

##### Windows (Command Prompt / PowerShell)
```powershell
python -m venv .venv
# PowerShell:
.venv\Scripts\Activate.ps1
# Or Command Prompt:
# .venv\Scripts\activate.bat
pip install -r requirements.txt
```

---

### Step 3: Environment Configuration (Optional)

The core application (RSS ingestion, channel directory, rolling median calculations, outlier multiplier engine, and dashboard) **works completely offline without any API keys**.

If you wish to enable **AI Creator Card summaries** (Groq LLM) or **Whisper audio transcription**, copy the template and provide your free Groq API key:

```bash
# macOS / Linux
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env
```

Edit `.env`:
```ini
# Free key from https://console.groq.com/keys
GROQ_API_KEY=your_actual_groq_api_key_here
```

> [!NOTE]
> `.env` and `data/*.db` are excluded from Git in `.gitignore` to prevent secret or local data leakage.

---

### Step 4: Run the Platform

```bash
# Initialize DB and start server with background sync
python run.py --sync
```

Once started, open your browser:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## ⚙️ CLI Reference

```text
usage: run.py [-h] [--port PORT] [--host HOST] [--sync] [--init-only]

options:
  -h, --help   show this help message and exit
  --port PORT  Server port (default: 8000)
  --host HOST  Host address (default: 0.0.0.0)
  --sync       Trigger background RSS sync and outlier detection on launch
  --init-only  Initialize database, seed channel catalog, and exit
```

---

## 🗂️ Project Architecture

```text
niche-outlier-radar/
├── app/                  # FastAPI web application, API routes, templates, and static assets
│   ├── main.py           # FastAPI entrypoint and REST endpoints
│   ├── static/           # CSS and vanilla JS frontend
│   └── templates/        # YouTube-native HTML template
├── radar/                # Core domain engine
│   ├── config.py         # Configuration and environment resolver
│   ├── db.py             # SQLite WAL-mode database interface
│   ├── fetcher.py        # RSS and Innertube video feed fetcher
│   ├── outlier_engine.py # Rolling median & multiplier calculations
│   ├── transcript.py     # Transcripts via API + Groq Whisper audio fallback
│   ├── analyzer.py       # Creator blueprint generation via Groq
│   ├── seed_channels.py  # Curated high-signal channel catalog
│   ├── discovery.py      # Channel recommendation & crawler
│   ├── collab.py         # Guest/collaboration detector
│   └── scheduler.py      # Background sync loop
├── scripts/              # Verification and utility scripts
├── tests/                # Pytest test suite with isolated DB fixtures
├── data/                 # SQLite database storage (radar.db is git-ignored)
├── run.py                # Server launcher and CLI runner
├── .env.example          # Environment variable template
├── RADAR_RULES.md        # Channel hunting, eligibility & feed quality rules
└── requirements.txt      # Python dependencies
```

---

## 🧪 Running Tests

Tests use isolated temporary databases so your production data is never modified:

```bash
# macOS / Linux
PYTHONPATH=. pytest

# Windows (PowerShell)
$env:PYTHONPATH="."
pytest
```

---

## 📜 Editorial & Quality Rules

For channel eligibility standards, blacklist filters, and two-tier feed specifications, refer to [RADAR_RULES.md](RADAR_RULES.md).

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
