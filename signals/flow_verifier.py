"""
Flow verifier — pre-LLM filter for Unusual Whales options flow.

Takes raw prints from uw_feed.get_flow_alerts() and dark pool prints from
uw_feed.get_darkpool(), applies the scoring model from flow_interpretation.md,
and returns a structured dict the context_builder passes to the analysis prompt.

Output dict shape:
    {
        "recent_prints":  [...],       # cleaned prints from last 60 min (ask-side, above threshold)
        "net_premium":    1_980_000,   # positive = net bullish, negative = net bearish
        "spread_detected": False,      # True if a spread trap was found
        "status":         "confirming",# confirming | neutral | contradicting | complex | none
        "direction":      "bullish",   # dominant direction of qualifying prints
        "score":          8,           # integer score (< 4 = skip LLM, 4-5 = medium, 6+ = high)
        "stacking":       True,        # 2+ sweeps same direction within 60 min
        "darkpool_confirmed": False,   # dark pool print in same direction within 60 min
        "darkpool_summary": "none",    # human-readable string for analysis prompt
    }

Scoring rules (from knowledge/flow_interpretation.md):
    Sweep on ask $100k–$500k    → +1
    Sweep on ask $500k–$1M      → +2
    Sweep on ask $1M+           → +3
    Block trade (not sweep)     → +1
    Stacking (2+ sweeps, 60min) → +2 additional
    Dark pool confirms          → +3 additional
    Price action confirms       → +1 additional  (caller provides, default 0)
    Market tide aligned         → +1 additional  (caller provides, default 0)
    OTM sweep, 14–45 DTE        → +1 additional
    IV rank < 50                → +1 additional  (caller provides, default 0)

Thresholds (from config/settings.py):
    score < 4  → filter out, do not call LLM
    score 4–5  → medium priority, call LLM
    score >= 6 → high priority, call LLM
"""

import logging
import time

from config.settings import (
    FLOW_MAX_AGE_MINUTES,
    FLOW_SCORE_SEND_THRESHOLD,
    DARKPOOL_MATCH_WINDOW_MIN,
    MIN_FLOW_PREMIUM,
)

log = logging.getLogger(__name__)

# Spread trap detection: if two prints on the same expiry in opposite directions
# arrive within this many seconds, treat the whole set as complex (spread).
SPREAD_WINDOW_SECONDS = 30


def verify_flow(
    ticker: str,
    prints: list[dict],
    darkpool: list[dict],
    current_price: float | None = None,
    market_tide_aligned: bool = False,
    ivr: float | None = None,
) -> dict:
    """
    Main entry point. Call once per ticker per scan cycle.

    Args:
        ticker:               symbol being analyzed
        prints:               raw list from uw_feed.get_flow_alerts(ticker)
        darkpool:             raw list from uw_feed.get_darkpool(ticker)
        current_price:        live price for OTM/ITM classification
        market_tide_aligned:  True if market tide direction matches dominant flow
        ivr:                  IV rank of suggested contract (0–100), or None
    """
    now = time.time()
    max_age = FLOW_MAX_AGE_MINUTES * 60
    min_premium = MIN_FLOW_PREMIUM.get(ticker, 200_000)

    # ── Step 1: filter to qualifying prints ──────────────────────────
    qualifying = []
    for p in prints:
        age = now - (p.get("ts") or 0)
        if age > max_age:
            continue
        if (p.get("premium") or 0) < min_premium:
            continue
        if p.get("side") == "bid":          # closing trades, not directional
            continue
        if p.get("direction") == "neutral":
            continue
        qualifying.append(p)

    if not qualifying:
        return _no_flow_result()

    # ── Step 2: spread trap detection ────────────────────────────────
    spread_detected = _detect_spread(qualifying)

    # ── Step 3: score prints ─────────────────────────────────────────
    bullish_prints = [p for p in qualifying if p.get("direction") == "bullish"]
    bearish_prints = [p for p in qualifying if p.get("direction") == "bearish"]

    dominant_dir = "bullish" if len(bullish_prints) >= len(bearish_prints) else "bearish"
    dominant_prints = bullish_prints if dominant_dir == "bullish" else bearish_prints
    contra_prints   = bearish_prints if dominant_dir == "bullish" else bullish_prints

    score = 0
    for p in dominant_prints:
        score += _score_print(p, current_price)

    # Stacking bonus: 2+ sweeps same direction within 60 min
    sweeps = [p for p in dominant_prints if p.get("trade_type") == "sweep"]
    stacking = len(sweeps) >= 2
    if stacking:
        score += 2

    # Dark pool bonus
    dp_window = DARKPOOL_MATCH_WINDOW_MIN * 60
    dp_matching = [
        d for d in darkpool
        if (now - (d.get("ts") or 0)) <= dp_window
        and d.get("direction") == dominant_dir
    ]
    darkpool_confirmed = bool(dp_matching)
    if darkpool_confirmed:
        score += 3

    # Market tide bonus (caller provides)
    if market_tide_aligned:
        score += 1

    # IV rank bonus (< 50 = not overpaying)
    if ivr is not None and ivr < 50:
        score += 1

    # ── Step 4: net premium ──────────────────────────────────────────
    bull_premium = sum(p.get("premium") or 0 for p in bullish_prints)
    bear_premium = sum(p.get("premium") or 0 for p in bearish_prints)
    net_premium  = bull_premium - bear_premium

    # ── Step 5: status classification ────────────────────────────────
    if spread_detected:
        status = "complex"
    elif not dominant_prints:
        status = "none"
    elif contra_prints and _contra_is_significant(contra_prints, dominant_prints):
        status = "contradicting"
    elif dominant_prints:
        status = "confirming"
    else:
        status = "neutral"

    # ── Step 6: format recent prints for prompt ───────────────────────
    formatted = _format_prints(qualifying)

    # Dark pool summary string
    dp_summary = _format_darkpool(dp_matching) if dp_matching else "none"

    log.debug(
        "%s flow: score=%d status=%s stacking=%s dp=%s prints=%d",
        ticker, score, status, stacking, darkpool_confirmed, len(qualifying),
    )

    return {
        "recent_prints":       qualifying,
        "net_premium":         net_premium,
        "spread_detected":     spread_detected,
        "status":              status,
        "direction":           dominant_dir,
        "score":               score,
        "stacking":            stacking,
        "darkpool_confirmed":  darkpool_confirmed,
        "darkpool_summary":    dp_summary,
        "formatted_prints":    formatted,    # ready for {flow_prints_block} placeholder
    }


def should_call_llm(flow_result: dict) -> bool:
    """
    Return True if this flow result is worth sending to the LLM.
    Filters out noise before burning an API call.
    """
    return flow_result["score"] >= FLOW_SCORE_SEND_THRESHOLD


# ------------------------------------------------------------------ #
# Scoring helpers

def _score_print(p: dict, current_price: float | None) -> int:
    premium     = p.get("premium") or 0
    trade_type  = p.get("trade_type", "block")
    dte         = p.get("dte")
    strike      = p.get("strike")
    option_type = p.get("option_type", "")

    if trade_type == "sweep":
        if premium >= 1_000_000:
            pts = 3
        elif premium >= 500_000:
            pts = 2
        else:
            pts = 1
    else:
        pts = 1  # block or split

    # OTM + clean DTE bonus
    if dte and 14 <= dte <= 45 and current_price and strike:
        pct_otm = abs(strike - current_price) / current_price
        if 0.01 < pct_otm < 0.10:   # 1–10% OTM = clean directional
            pts += 1

    return pts


def _detect_spread(prints: list[dict]) -> bool:
    """
    Spread trap: opposite-side prints on the same expiry within 30 seconds.
    e.g. $1.5M calls bought then $1.4M calls sold 28s later = debit spread.
    """
    for i, p1 in enumerate(prints):
        for p2 in prints[i+1:]:
            same_expiry = p1.get("expiry") == p2.get("expiry") and p1.get("expiry")
            opposite    = p1.get("direction") != p2.get("direction")
            close_ts    = abs((p1.get("ts") or 0) - (p2.get("ts") or 0)) <= SPREAD_WINDOW_SECONDS
            if same_expiry and opposite and close_ts:
                log.debug("Spread trap detected: %s vs %s", p1, p2)
                return True
    return False


def _contra_is_significant(contra: list[dict], dominant: list[dict]) -> bool:
    """
    Contradicting flow is significant if its premium is > 40% of dominant premium.
    Small contra prints are noise; large contra prints are a real warning.
    """
    contra_premium   = sum(p.get("premium") or 0 for p in contra)
    dominant_premium = sum(p.get("premium") or 0 for p in dominant)
    if not dominant_premium:
        return False
    return (contra_premium / dominant_premium) > 0.40


# ------------------------------------------------------------------ #
# Formatting helpers

def _format_prints(prints: list[dict]) -> str:
    """
    Format qualifying prints for the {flow_prints_block} prompt placeholder.
    Example output:
        • 10:32am | $1.2M | May16 $220C | SWEEP | at ask | BULLISH
    """
    if not prints:
        return "No unusual flow detected in the last 60 minutes."

    lines = []
    for p in sorted(prints, key=lambda x: x.get("ts") or 0):
        premium    = p.get("premium") or 0
        strike     = p.get("strike")
        expiry     = p.get("expiry", "")
        opt_type   = (p.get("option_type") or "").upper()[0] if p.get("option_type") else "?"
        trade_type = (p.get("trade_type") or "block").upper()
        direction  = (p.get("direction") or "").upper()
        time_str   = p.get("time_str", "")

        expiry_short = _short_expiry(expiry)
        premium_str  = _fmt_premium(premium)
        contract     = f"{expiry_short} ${strike}{opt_type}" if strike else "?"

        lines.append(f"  • {time_str} | {premium_str} | {contract} | {trade_type} | at ask | {direction}")

    return "\n".join(lines)


def _format_darkpool(prints: list[dict]) -> str:
    if not prints:
        return "none"
    p = prints[0]  # show most recent
    shares    = p.get("shares") or 0
    price     = p.get("price") or 0
    direction = p.get("direction", "")
    ts        = p.get("ts") or 0
    time_str  = _ts_to_time(ts)
    return f"{shares:,} shares @ ${price:.2f} at {time_str} — {direction} direction"


def _short_expiry(expiry: str) -> str:
    """'2025-05-16' → 'May16'"""
    try:
        from datetime import datetime
        dt = datetime.strptime(expiry, "%Y-%m-%d")
        return dt.strftime("%b%-d") if hasattr(dt, "strftime") else expiry
    except Exception:
        return expiry


def _fmt_premium(p: int) -> str:
    if p >= 1_000_000:
        return f"${p/1_000_000:.1f}M"
    if p >= 1_000:
        return f"${p//1_000}k"
    return f"${p}"


def _ts_to_time(ts: float) -> str:
    from datetime import datetime
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts)
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d}{'am' if dt.hour < 12 else 'pm'}"


def _no_flow_result() -> dict:
    return {
        "recent_prints":      [],
        "net_premium":        0,
        "spread_detected":    False,
        "status":             "none",
        "direction":          "neutral",
        "score":              0,
        "stacking":           False,
        "darkpool_confirmed": False,
        "darkpool_summary":   "none",
        "formatted_prints":   "No unusual flow detected in the last 60 minutes.",
    }
