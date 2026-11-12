# Niche Outlier Radar: Channel Hunting & Feed Quality Rules

This document outlines the non-negotiable standards, eligibility criteria, and mathematical filters governing video feed creation and channel discovery in Niche Outlier Radar.

---

## 1. Core Operating Philosophy: Quality > Volume

> "If only 1 quality channel is discovered in a day, that is completely fine. Even 0 channels is fine. We will never compromise the feed quality or channel directory for the sake of catalog size."

The purpose of this platform is **not** to build a phonebook of thousands of random YouTube channels. The platform exists solely for:
1. **Market Intelligence**: Discovering what topics, frameworks, and formats are genuinely resonating and working right now.
2. **Global AI Pulse**: Tracking real breakthroughs, frontier models, and autonomous workflow developments.
3. **Actionable Content Ideation**: Sourcing battle-tested ideas and angles from other creators to reproduce in our own style.
4. **High-Signal Reference Channels**: Maintaining a tight, trusted catalog of elite engineers, indie builders, and researchers.

---

## 2. Creator Classification & Two-Tier Feed Rules

We divide creators into two distinct tiers, with fundamentally different inclusion rules in the main feed:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER A: Established Anchor Creators (Channel Median >= 10,000 views)        │
├─────────────────────────────────────────────────────────────────────────────┤
│ • Examples: IndyDevDan, Theo, Fireship, Nate Herk, Karpathy, Wes Roth.      │
│ • Baseline Feed Inclusion: Recent videos (<= 15 days) with view count >= 500│
│ • Outlier Treatment: Highlighted with visible 🔥 Multiplier badges.         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER B: Emerging / Micro-Creators (Channel Median < 10,000 views)           │
├─────────────────────────────────────────────────────────────────────────────┤
│ • RULE: OUTLIERS ONLY (Zero baseline churn).                                │
│ • Baseline videos (ordinary 50-300 view uploads) are STRICTLY FILTERED OUT. │
│ • ONLY videos that are verified RECENT OUTLIERS enter the feed:             │
│     Condition: multiplier >= 2.0x AND view_count >= 1,000                   │
│ • Reason: We celebrate emerging breakout gems, but do not clutter the feed  │
│   with low-traction daily churn.                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Channel Hunting & Eligibility Gatekeeper

Before any channel is admitted into the radar catalog (via graph crawl, keyword discovery, or collaboration search), it must pass all 4 filters:

### Filter 1: Hard Blacklist (Zero Tolerance)
The channel must NOT belong to any of these banned archetypes:
- **Corporate Ed-Tech Course Mills**: Channels mass-uploading 10–40 hour generic beginner courses:
  - `Simplilearn`, `Intellipaat`, `Edureka`, `WsCube Tech`, `GeeksforGeeks`, `Great Learning`, `Coding Ninjas`.
- **Generic Institutional Repositories**: Non-specialized educational channels:
  - `TEDx`, `Khan Academy`, general physics/biology archives without AI or developer focus.
- **General Entertainment & Viral DIY**:
  - `Mark Rober`, generic prank/entertainment accounts.
- **Faceless Scrapers & AI Burner Accounts**:
  - Channels with zero median views re-uploading short n8n clips or scraping voiceovers (e.g. `AI Automation Official`).

### Filter 2: Niche Alignment
The creator must actively publish original work in one of our 5 pillars:
1. **AI Agents & Autonomous Systems**: Multi-agent swarms, CrewAI, LangGraph, AutoGPT, MCP, agent architecture.
2. **Vibe Coding & Fullstack Engineering**: Cursor AI, Claude 3.7, Next.js, FastAPI, local LLMs, fullstack SaaS.
3. **Automations & Workflows**: n8n, Make, Flowise, Dify, Voiceflow, enterprise automation engineering.
4. **AI News & Frontier Research**: DeepSeek, OpenAI, Anthropic, Google DeepMind, paper breakdowns.
5. **UI/UX & Design Engineering**: Mobbin, modern design systems, Framer, micro-interactions, Figma to code.

### Filter 3: Traction & Signal Verification
- For established channels: Verified median $\ge 10,000$ views.
- For micro-channels: Verified track record of at least one video exceeding $2.0\times$ median or $5,000$ views within the last 30 days.
- Hard Floor: Any channel whose all-time maximum views is $< 1,000$ is permanently excluded.

---

## 4. Feed Creation Engine & Ranking Standards

### Rule 1: Absolute Signal Floor
- **No 0-view or dead videos**: Every video entering the feed must have at least **200 views** (or come from an established channel with median $\ge 15,000$).
- 0-view placeholder uploads and bot scrapers are blocked at the SQL query layer.

### Rule 2: Strict Format Isolation
- **Long-Form Feed (`video_type="long"`)**:
  - Strictly non-Shorts: `is_short = 0` AND (`duration_seconds > 60` OR `duration_seconds = 0`).
  - 100% free of vertical 15-second noise.
- **Shorts Feed (`video_type="shorts"`)**:
  - Dedicated tab displaying strictly short-form breakout content.

### Rule 3: Anti-Spam Creator Throttling
- Maximum 2 videos per creator in the 50-video feed view.
- Strictly **0 consecutive videos** from the same creator in a row (enforced via interleaving algorithm).
- If a creator uploads 5 videos in 24 hours, only their single highest-traction video is promoted.

### Rule 4: Smart Velocity Ranking (`smart_signal`)
The default feed ranking combines recency, view velocity, and outlier breakout score:
$$\text{Rank Score} = \text{Multiplier Bonus} \times \frac{\text{View Count}}{\max(\text{Hours Since Published}, 1)^{0.65}}$$
This ensures the top of the feed is always buzzing with high-traction, high-signal, relevant discussions.

---

## 5. Geographic Balance & The 10% Indian Creator Quota

### Rule 5: Strict 10% Indian Creator Feed Cap
- In any 50-video feed view, **at most 10% (maximum 5 videos)** may come from Indian creators (`country == 'IN'`).
- The remaining **90%+ (45+ videos)** are strictly reserved for top creators from:
  - **North America**: United States (`US`), Canada (`CA`).
  - **Europe**: United Kingdom (`UK`), Germany, France, Switzerland, Netherlands, Nordics (`EU`).
  - **Asia-Pacific & East Asia**: Japan (`JP`), China (`CN`), Singapore, Australia (`APAC`).
  - **Global Tech Hubs**: Israel, South Korea, etc. (`GLOBAL`).

### Rule 6: "Quality Indian Content Only" Filter
- For the 5 slots allocated to Indian creators, only top-tier engineering, AI architecture, and breakout systems are permitted (e.g. Aishwarya Srinivasan Agentic RAG, Vaibhav Sisinty Meta Connect breakdown, Piyush Garg system design).
- **Zero Personal Drama or Apology Vlogs**: Titles containing personal drama, apology clickbait (*"I AM SORRY"*, *"A Personal Update"*, *"quitting youtube"*), or generic coaching are permanently suppressed from entering the feed.
