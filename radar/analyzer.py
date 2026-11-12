"""AI Content Analyzer using Groq to produce Actionable Creator Cards."""
import json
import logging
from typing import Dict, Any, Optional

from groq import Groq
from radar.config import GROQ_API_KEY, GROQ_MODEL, GROQ_FALLBACK_MODEL
from radar.db import upsert_outlier, get_pending_analysis_outliers
from radar.transcript import fetch_video_transcript

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an elite AI content strategist and tech analyst.
Analyze the provided YouTube video transcript and metadata.
Return a STRICT, VALID JSON object with the following schema:
{
  "category": "AI Agents" | "Automations" | "AI News & Breakthroughs" | "SaaS & Dev Tools" | "AGI & Research",
  "summary_bullets": [
    "First concrete technical takeaway or insight.",
    "Second key mechanism, architecture, or workflow explained.",
    "Third practical conclusion or benchmark result."
  ],
  "tools_mentioned": ["Tool1", "Tool2", "Model or Repo"],
  "viral_hook_angle": "Explain why this video broke out (the psychological hook or problem solved) and provide an actionable angle for how a creator can reproduce or cover this topic in their own style."
}
Be concise, technical, and high-signal. Avoid fluff and buzzwords.
"""

def analyze_outlier_video(video_id: str, channel_id: str, title: str, multiplier: float, median: int) -> Optional[Dict[str, Any]]:
    """Analyzes an outlier video using Groq and updates the database."""
    if not GROQ_API_KEY:
        logger.warning("No Groq API key configured; skipping LLM analysis.")
        return None

    transcript_text = fetch_video_transcript(video_id)
    if transcript_text:
        # Truncate to first ~12,000 characters to stay fast and within budget
        content_snippet = transcript_text[:12000]
    else:
        content_snippet = f"Transcript unavailable. Video Title: {title}. Analyze based on title and tech context."

    prompt = f"""Video Title: {title}
Multiplier: {multiplier}x channel median views
Transcript / Context:
{content_snippet}
"""

    client = Groq(api_key=GROQ_API_KEY)
    model_to_use = GROQ_MODEL

    try:
        try:
            resp = client.chat.completions.create(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )
        except Exception as e:
            logger.warning(f"Primary model {model_to_use} failed ({e}), trying fallback {GROQ_FALLBACK_MODEL}")
            resp = client.chat.completions.create(
                model=GROQ_FALLBACK_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )

        content = resp.choices[0].message.content
        data = json.loads(content)

        category = data.get("category", "SaaS & Dev Tools")
        bullets = data.get("summary_bullets", [])
        tools = data.get("tools_mentioned", [])
        hook = data.get("viral_hook_angle", "")

        upsert_outlier(
            video_id=video_id,
            channel_id=channel_id,
            multiplier=multiplier,
            channel_median=median,
            category=category,
            summary_bullets=bullets,
            tools_mentioned=tools,
            viral_hook_angle=hook
        )

        return data

    except Exception as e:
        logger.error(f"Failed to analyze video {video_id}: {e}")
        return None

def process_pending_outliers(limit: int = 5) -> int:
    """Processes unanalyzed outliers from the queue."""
    pending = get_pending_analysis_outliers(limit=limit)
    processed = 0
    for item in pending:
        logger.info(f"Analyzing outlier: {item['title']} ({item['multiplier']}x)")
        res = analyze_outlier_video(
            video_id=item["video_id"],
            channel_id=item["channel_id"],
            title=item["title"],
            multiplier=item["multiplier"],
            median=item.get("median_at_detection", 0)
        )
        if res:
            processed += 1
    return processed
