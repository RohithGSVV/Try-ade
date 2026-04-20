"""
Market tide watcher — fetches UW market tide score and caches it.

The market tide is a macro sentiment indicator (0–100) published by
Unusual Whales. It refreshes every few minutes on their end; we fetch
it every 5 minutes to avoid burning API quota on stale data.

Public API:
    get_tide()  → {"score": 71, "direction": "bullish", "label": "bullish (71/100)"}

Direction thresholds (from analysis_prompt.md):
    > 65  → bullish
    35–65 → neutral
    < 35  → bearish
"""

import logging
import time

from feeds.uw_feed import get_market_tide

log = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 5 * 60  # 5 minutes

_cache: dict = {"tide": None, "fetched_at": 0.0}


def get_tide() -> dict:
    """
    Return current market tide, refreshing from UW at most every 5 minutes.
    Always returns a valid dict — falls back to neutral on API failure.
    """
    now = time.time()
    if now - _cache["fetched_at"] > REFRESH_INTERVAL_SECONDS or _cache["tide"] is None:
        _refresh(now)
    return _cache["tide"]


def is_aligned(tide: dict, flow_direction: str) -> bool:
    """
    Return True if the market tide direction matches the flow direction.
    Used by flow_verifier to award the +1 market tide bonus.
    """
    tide_dir = tide.get("direction", "neutral")
    if tide_dir == "neutral":
        return False
    return tide_dir == flow_direction


def tide_label(score: int) -> str:
    if score > 65:
        return "bullish"
    if score < 35:
        return "bearish"
    return "neutral"


# ------------------------------------------------------------------ #

def _refresh(now: float) -> None:
    try:
        raw = get_market_tide()
        score = raw.get("score", 50)
        direction = raw.get("direction", "neutral")
        _cache["tide"] = {
            "score":     score,
            "direction": direction,
            "label":     f"{direction} ({score}/100)",
        }
        _cache["fetched_at"] = now
        log.debug("Market tide refreshed: %s", _cache["tide"])
    except Exception as exc:
        log.warning("Market tide refresh failed: %s — using neutral", exc)
        if _cache["tide"] is None:
            _cache["tide"] = {"score": 50, "direction": "neutral", "label": "neutral (50/100)"}
