"""
Event filters — code-side hard block enforcement.

These checks run BEFORE the LLM is called. If any returns True, the scan
cycle skips that ticker entirely and saves the API call.

Hard blocks owned by code (from the plan's responsibility split):
  - Session time: 9:30–10:00am and 3:30–4:00pm ET → block
  - VIX > 30 → block
  - Max 3 open positions → block
  - Correlation group already occupied → block
  - 24hr re-entry cooldown after stop-loss → block

Hard blocks owned by LLM (checked in the prompt, not here):
  - DTE < 14 (depends on which contract LLM suggests)
  - IVR > 70 (depends on chosen contract)
  - Earnings < 5 days (code provides the date, LLM verifies)
  - Bid-side flow (filtered by flow_verifier before reaching here)

Public API:
  check_all(ticker, open_positions, stopout_log) → (blocked: bool, reason: str | None)
  is_market_hours() → bool
  get_session_status() → "ACTIVE" | "PRE_MARKET" | "POST_MARKET" | "OPENING_BLOCK" | "CLOSING_BLOCK"
"""

import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from feeds.historical_feed import get_vix
from config.settings import (
    VIX_MAX,
    MAX_OPEN_POSITIONS,
    NO_TRADE_OPEN_MIN,
    NO_TRADE_CLOSE_MIN,
    STOPOUT_COOLDOWN_HOURS,
    CORRELATION_GROUPS,
)

log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Market open/close in ET
MARKET_OPEN  = (9, 30)   # 9:30am
MARKET_CLOSE = (16, 0)   # 4:00pm


def check_all(
    ticker: str,
    open_positions: list[dict],
    stopout_log: list[dict],
) -> tuple[bool, str | None]:
    """
    Run all code-side hard block checks for a ticker.

    Args:
        ticker:          symbol being evaluated
        open_positions:  list of open paper trade dicts (from position_tracker)
                         each must have keys: "ticker", "status"
        stopout_log:     list of recent stop-out dicts: {"ticker", "closed_at" (epoch float)}

    Returns:
        (True, "reason string")  if blocked
        (False, None)            if clear to proceed
    """
    checks = [
        _check_session,
        _check_vix,
        lambda t, op, sl: _check_max_positions(op),
        lambda t, op, sl: _check_correlation(t, op),
        lambda t, op, sl: _check_stopout_cooldown(t, sl),
    ]

    for check in checks:
        blocked, reason = check(ticker, open_positions, stopout_log)
        if blocked:
            log.info("Hard block on %s: %s", ticker, reason)
            return True, reason

    return False, None


def is_market_hours() -> bool:
    """True only during regular session (9:30am–4:00pm ET)."""
    now = _now_et()
    open_mins  = MARKET_OPEN[0]  * 60 + MARKET_OPEN[1]
    close_mins = MARKET_CLOSE[0] * 60 + MARKET_CLOSE[1]
    current_mins = now.hour * 60 + now.minute
    return open_mins <= current_mins < close_mins


def get_session_status() -> str:
    """
    Return a human-readable session status for the {session_status} prompt placeholder.
    """
    now = _now_et()
    hm  = now.hour * 60 + now.minute

    open_mins  = MARKET_OPEN[0]  * 60 + MARKET_OPEN[1]
    close_mins = MARKET_CLOSE[0] * 60 + MARKET_CLOSE[1]
    block_open_end   = open_mins  + NO_TRADE_OPEN_MIN
    block_close_start = close_mins - NO_TRADE_CLOSE_MIN

    if hm < open_mins:
        return "PRE_MARKET"
    if hm >= close_mins:
        return "POST_MARKET"
    if open_mins <= hm < block_open_end:
        return "OPENING_BLOCK"     # hard block
    if block_close_start <= hm < close_mins:
        return "CLOSING_BLOCK"     # hard block
    return "ACTIVE"


# ------------------------------------------------------------------ #
# Individual checks

def _check_session(ticker, open_positions, stopout_log) -> tuple[bool, str | None]:
    status = get_session_status()
    if status == "OPENING_BLOCK":
        return True, f"session opening block (first {NO_TRADE_OPEN_MIN} min — high noise)"
    if status == "CLOSING_BLOCK":
        return True, f"session closing block (last {NO_TRADE_CLOSE_MIN} min — MOC flow)"
    if status in ("PRE_MARKET", "POST_MARKET"):
        return True, f"market closed ({status})"
    return False, None


def _check_vix(ticker, open_positions, stopout_log) -> tuple[bool, str | None]:
    vix = get_vix()
    if vix > VIX_MAX:
        return True, f"VIX {vix:.1f} > {VIX_MAX} — options too expensive"
    return False, None


def _check_max_positions(open_positions: list[dict]) -> tuple[bool, str | None]:
    open_count = sum(1 for p in open_positions if p.get("status") == "open")
    if open_count >= MAX_OPEN_POSITIONS:
        return True, f"max open positions reached ({open_count}/{MAX_OPEN_POSITIONS})"
    return False, None


def _check_correlation(ticker: str, open_positions: list[dict]) -> tuple[bool, str | None]:
    my_group = CORRELATION_GROUPS.get(ticker)
    if not my_group:
        return False, None

    for pos in open_positions:
        if pos.get("status") != "open":
            continue
        other_ticker = pos.get("ticker", "")
        other_group  = CORRELATION_GROUPS.get(other_ticker)
        if other_group == my_group and other_ticker != ticker:
            return True, (
                f"correlation group '{my_group}' already occupied by {other_ticker}"
            )
    return False, None


def _check_stopout_cooldown(ticker: str, stopout_log: list[dict]) -> tuple[bool, str | None]:
    import time
    now = time.time()
    cooldown_secs = STOPOUT_COOLDOWN_HOURS * 3600

    for entry in stopout_log:
        if entry.get("ticker") != ticker:
            continue
        closed_at = entry.get("closed_at") or 0
        age_secs  = now - closed_at
        if age_secs < cooldown_secs:
            remaining_hrs = (cooldown_secs - age_secs) / 3600
            return True, (
                f"{ticker} stopped out {age_secs/3600:.1f}h ago — "
                f"{remaining_hrs:.1f}h cooldown remaining"
            )
    return False, None


# ------------------------------------------------------------------ #

def _now_et() -> datetime:
    return datetime.now(ET)
