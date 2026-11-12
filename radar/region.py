"""Region and Country Classification Engine.

Enforces geographic diversity standards across the creator catalog:
- Caps Indian creators at <= 10% in the feed (quality-only).
- Balances and promotes creators from the US, Canada, UK, Europe, Japan, China,
  and expanding tech hubs worldwide (Singapore, Australia, Israel, Nordics).
"""
import re
from typing import Dict, Any, Optional

# Canonical Region Codes
# US: United States
# CA: Canada
# UK: United Kingdom
# EU: Continental Europe (Germany, France, Switzerland, Netherlands, Poland, Nordics, etc.)
# APAC: Asia-Pacific (Australia, Singapore, South Korea, etc.)
# JP: Japan
# CN: China & East Asia
# IN: India (Capped at <= 10% in feed)
# GLOBAL: International tech hubs (Israel, New Zealand, etc.)

CREATOR_REGION_MAP: Dict[str, str] = {
    # --- India (IN) - Capped at <= 10% in feed ---
    "@vaibhavsisinty": "IN",
    "@codewithharry": "IN",
    "@piyushgargdev": "IN",
    "@codebasics": "IN",
    "@aishwaryasrinivasan": "IN",
    "@tech.mayankagg": "IN",
    "@genaiunplugged": "IN",
    "@ailearnersbyabhijeet": "IN",
    "@parthknowsai": "IN",
    "@ai.vishnuvijayan": "IN",
    "@techie007": "IN",
    "@ai-with-rajpalsinh": "IN",
    "@iamnamangupta22": "IN",
    "@wdf_ai": "IN",
    "@roadsidecoder": "IN",
    "@ai_lavishka": "IN",
    "@hiteshchoudharydotcom": "IN",
    "@codingwithctobhaiya": "IN",
    "@vivekmishrayt": "IN",

    # --- United States (US) ---
    "@gregisenberg": "US",
    "@fireship": "US",
    "@andrejkarpathy": "US",
    "@karpathy": "US",
    "@t3dotgg": "US",
    "@theprimetimeagen": "US",
    "@theprimeagen": "US",
    "@matthew_berman": "US",
    "@wesroth": "US",
    "@davidondrej": "US",
    "@colemedin": "US",
    "@indydevdan": "US",
    "@webdevsimplified": "US",
    "@jherr": "US",
    "@syntaxfm": "US",
    "@davegrayteachescode": "US",
    "@alexziskind": "US",
    "@webdevcody": "US",
    "@sonnysangha": "US",
    "@freecodecamp": "US",
    "@traversymedia": "US",
    "@networkchuck": "US",
    "@lexfridman": "US",
    "@dwarkeshpatel": "US",
    "@maboris": "US",
    "@theaibreakdown": "US",
    "@aijasonz": "US",
    "@promptengineering": "US",
    "@worldofai": "US",
    "@allaboutai": "US",
    "@langchain": "US",
    "@crewai": "US",
    "@sentdex": "US",
    "@3blue1brown": "US",
    "@openai": "US",
    "@anthropic-ai": "US",
    "@anthropic": "US",
    "@cursor_ai": "US",
    "@rileybrownai": "US",
    "@aicodeking": "US",
    "@nateherk": "US",
    "@mikeynocode": "US",
    "@codesistency": "US",
    "@hnasr": "US",
    "@aidotengineer": "US",
    "@designcourse": "US",
    "@edhillai": "US",
    "@devforgehq": "US",
    "@deeplearningai": "US",
    "@bytebytego": "US",

    # --- Canada (CA) ---
    "@techwithtim": "CA",
    "@kevinpowell": "CA",

    # --- United Kingdom (UK) ---
    "@mattpocockuk": "UK",
    "@computerphile": "UK",
    "@standupmaths": "UK",
    "@googledeepmind": "UK",
    "@aiexplained-official": "UK",
    "@charlimarietv": "UK",
    "@jamesbriggs": "UK",

    # --- Continental Europe (EU) ---
    "@yannickilcher": "EU",
    "@codewithantonio": "EU",
    "@arjancodes": "EU",
    "@developedbyed": "EU",
    "@techworldwithnana": "EU",
    "@twominutepapers": "EU",
    "@malewiczhype": "EU",
    "@mistralai": "EU",
    "@sebastianraschka": "EU",

    # --- Asia-Pacific & Expanding Tech Hubs (APAC / JP / CN / GLOBAL) ---
    "@techwithlucy": "APAC",
    "@samwitteveen": "APAC",
    "@mathologer": "APAC",
    "@mobbindesign": "GLOBAL",
    "@fluxacademy": "GLOBAL",
    "@liamottley": "GLOBAL",
    "@deepseek_ai": "CN",
}

INDIAN_KEYWORDS = [
    "india", "hindi", "bhaiya", "tamil", "telugu", "guruji", "choudhary", "sharma"
]

# Personal drama / apology / clickbait titles to strictly suppress
DRAMA_TITLE_PATTERNS = [
    r"\bi\s+am\s+sorry\b",
    r"\bpersonal\s+update\b",
    r"\bquitting\s+youtube\b",
    r"\bexposed\b",
    r"\bcontroversy\b",
    r"\bemotional\s+update\b",
]

def get_channel_region(handle: Optional[str] = "", name: Optional[str] = "") -> str:
    """Resolves the canonical region code for a creator from handle and name."""
    h_clean = (handle or "").lower().strip()
    if h_clean and not h_clean.startswith("@"):
        h_clean = f"@{h_clean}"

    if h_clean in CREATOR_REGION_MAP:
        return CREATOR_REGION_MAP[h_clean]

    n_clean = (name or "").lower().strip()
    combined = f"{h_clean} {n_clean}"

    if any(k in combined for k in INDIAN_KEYWORDS):
        return "IN"

    return "US"

def is_indian_creator(handle: Optional[str] = "", name: Optional[str] = "", country: Optional[str] = "") -> bool:
    """Returns True if the creator is identified as an Indian creator."""
    if (country or "").upper() == "IN":
        return True
    return get_channel_region(handle=handle, name=name) == "IN"

def is_drama_or_low_quality_title(title: str) -> bool:
    """Detects personal drama, apology vlogs, or non-technical emotional updates."""
    if not title:
        return False
    t_clean = title.lower().strip()
    return any(re.search(pat, t_clean) for pat in DRAMA_TITLE_PATTERNS)
