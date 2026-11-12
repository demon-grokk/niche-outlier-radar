# 📡 Niche Outlier Radar

> YouTube-Native AI/Tech Discovery Platform & Viral Outlier Intelligence Engine.

Niche Outlier Radar tracks curated high-signal YouTube channels across AI Agents, Automations, AI News, Developer Tools, and AGI Research. It detects breakout videos ("outliers") that outperform a channel's rolling median, generates actionable creator blueprints, and extracts full video transcripts.

---

## ⚡ Key Capabilities

- **3-Layer Resilient Ingestion**:
  1. *Primary Feed Layer*: Sub-second Channel XML RSS feeds for zero-block updates and live view counts.
  2. *Session Persistence & Innertube Headers*: Fallback client headers for restricted metadata.
  3. *Fail-Safe Audio Fallback*: `yt-dlp` audio slice + Groq Whisper (`whisper-large-v3`) fallback guaranteeing 100% transcript availability.
- **Outlier Engine**:
  - Calculates channel-specific rolling 90-day medians.
  - Automatically identifies breakout videos (`multiplier = video.views / median`) with dynamic outlier badges (e.g. `🔥 4.2× Outlier`).
- **Creator Blueprint Intelligence**:
  - Powered by Groq LLMs (`qwen/qwen3.8-27b`, `openai/gpt-oss-20b`).
  - Produces 3-bullet technical takeaways, tools mentioned, and viral reproduction angles.
- **YouTube-Native Dark UI**:
  - Exact desktop dark-mode aesthetic (`#0f0f0f`), category chip filter bar, 3-4 column video grid, blueprint modal, and raw data inspector.

---

## 🛠️ Project Structure

```text
niche-outlier-radar/
├── app/                  # FastAPI web application, API routes, templates, and static assets
│   ├── main.py           # FastAPI entrypoint and REST endpoints
│   ├── static/           # CSS and vanilla JS frontend
│   └── templates/        # YouTube-native HTML template
├── radar/                # Core domain engine
│   ├── config.py         # App configuration and environment loading
│   ├── db.py             # SQLite WAL-mode database interface
│   ├── fetcher.py        # RSS and Innertube video feed fetcher
│   ├── outlier_engine.py # Median calculation and outlier multiplier logic
│   ├── transcript.py     # Transcripts via API + Groq Whisper audio fallback
│   ├── analyzer.py       # Creator blueprint generation via Groq
│   ├── seed_channels.py  # Curated high-signal channel catalog
│   ├── discovery.py      # Channel recommendation & crawler
│   ├── collab.py         # Guest/collaboration detector
│   └── scheduler.py      # Background sync loop
├── scripts/              # Platform verification and utility scripts
├── tests/                # Pytest test suite with isolated DB fixtures
├── data/                 # SQLite database storage (excluded from git)
├── run.py                # Server launcher and CLI runner
├── RADAR_RULES.md        # Channel hunting, eligibility & feed quality rules
└── requirements.txt      # Python dependencies
```

---

## 🚀 Getting Started

### 1. Installation

```bash
git clone https://github.com/demon-grokk/niche-outlier-radar.git
cd niche-outlier-radar

# Using uv (recommended)
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Or using standard pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Configuration (Optional)

Create a `.env` file in the project root:

```bash
GROQ_API_KEY=your_groq_api_key_here
OUTLIER_MULTIPLIER=1.8
RECENCY_DAYS=15
FEED_LIMIT=50
```

### 3. Launching

```bash
# Run server with background sync on launch
python run.py --sync

# Access dashboard
# Open http://localhost:8000
```

---

## 🧪 Testing

```bash
PYTHONPATH=. pytest
```

---

## 📜 Editorial & Quality Rules

For channel eligibility standards, blacklist filters, and two-tier feed specifications, refer to [RADAR_RULES.md](RADAR_RULES.md).
