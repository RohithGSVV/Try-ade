"""
Paper trader — logs new trades to paper_trades.csv when an alert fires.

CSV columns (from plan.md):
  id | date_entered | ticker | direction | type | strike | expiry |
  entry_price | contracts | notional | confidence | ds_confidence |
  gpt_confidence | status | current_price | pnl_pct |
  exit_price | outcome | thesis_summary

Public API:
  log_trade(ticker, result, live_data)  → trade dict or None
  get_open_positions()                  → list[dict] of open trades
  get_stopout_log()                     → list[dict] of recent stop-outs
  CSV_PATH                              → path to paper_trades.csv
"""

import csv
import logging
import math
import os
import time
from datetime import datetime

from feeds.robinhood_feed import get_entry_price
from config.settings import (
    BASE_NOTIONAL,
    HIGH_CONF_NOTIONAL,
    HIGH_CONF_THRESHOLD,
    STOPOUT_COOLDOWN_HOURS,
)
from core.llm_engine import AnalysisResult

log = logging.getLogger(__name__)

CSV_PATH = "paper_trades.csv"

COLUMNS = [
    "id", "date_entered", "ticker", "direction", "type", "strike", "expiry",
    "entry_price", "contracts", "notional", "confidence", "ds_confidence",
    "gpt_confidence", "status", "current_price", "pnl_pct",
    "exit_price", "outcome", "thesis_summary",
]


# ------------------------------------------------------------------ #
# Log a new trade

def log_trade(
    ticker: str,
    result: AnalysisResult,
    live_data: dict,
) -> dict | None:
    """
    Called when consensus alert fires. Fetches live ask price from Tradier,
    calculates contract count, and appends a row to paper_trades.csv.

    Returns the trade dict on success, None if entry price can't be fetched.
    """
    primary_raw = _primary_raw(result)
    if not primary_raw:
        log.error("log_trade called but no valid LLM result for %s", ticker)
        return None

    strike     = primary_raw.get("strike")
    expiry     = primary_raw.get("expiry")
    opt_type   = primary_raw.get("trade_type", "call").lower()
    confidence = primary_raw.get("confidence", 0.0)
    direction  = primary_raw.get("direction", "")
    thesis     = primary_raw.get("thesis_summary", "")

    # Fetch real ask price from Tradier at entry moment
    entry_price = get_entry_price(ticker, strike, expiry, opt_type)
    if entry_price is None:
        log.warning("Could not fetch entry price for %s %s%s %s — trade not logged", ticker, strike, opt_type[0].upper(), expiry)
        return None

    # Position sizing
    notional  = HIGH_CONF_NOTIONAL if confidence >= HIGH_CONF_THRESHOLD else BASE_NOTIONAL
    contracts = max(1, math.floor(notional / (entry_price * 100)))

    # Per-model confidences
    ds_conf  = result.deepseek.confidence if result.deepseek and result.deepseek.ok else ""
    gpt_conf = result.gpt.confidence      if result.gpt      and result.gpt.ok      else ""

    trade = {
        "id":            _next_id(),
        "date_entered":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ticker":        ticker,
        "direction":     direction,
        "type":          opt_type,
        "strike":        strike,
        "expiry":        expiry,
        "entry_price":   entry_price,
        "contracts":     contracts,
        "notional":      notional,
        "confidence":    round(confidence, 3),
        "ds_confidence": round(ds_conf, 3) if ds_conf != "" else "",
        "gpt_confidence":round(gpt_conf, 3) if gpt_conf != "" else "",
        "status":        "open",
        "current_price": entry_price,
        "pnl_pct":       0.0,
        "exit_price":    "",
        "outcome":       "",
        "thesis_summary":thesis,
    }

    _append_row(trade)
    log.info(
        "Trade logged: %s %s %s $%s %s | entry=$%.2f | %d contracts | conf=%.2f",
        ticker, direction.upper(), opt_type.upper(), strike, expiry,
        entry_price, contracts, confidence,
    )
    return trade


# ------------------------------------------------------------------ #
# Read positions

def get_open_positions() -> list[dict]:
    """Return all rows where status == 'open'."""
    return [r for r in _read_all() if r.get("status") == "open"]


def get_stopout_log() -> list[dict]:
    """
    Return trades closed as 'stop_loss' within the last STOPOUT_COOLDOWN_HOURS.
    Used by event_filters.py to enforce the 24-hour re-entry cooldown.
    """
    cutoff = time.time() - STOPOUT_COOLDOWN_HOURS * 3600
    result = []
    for row in _read_all():
        if row.get("outcome") != "stop_loss":
            continue
        closed_ts = _parse_date_ts(row.get("date_entered", ""))
        if closed_ts and closed_ts >= cutoff:
            result.append({
                "ticker":    row["ticker"],
                "closed_at": closed_ts,
            })
    return result


# ------------------------------------------------------------------ #
# CSV helpers

def _read_all() -> list[dict]:
    if not os.path.exists(CSV_PATH):
        return []
    try:
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception as exc:
        log.error("Failed to read %s: %s", CSV_PATH, exc)
        return []


def _append_row(trade: dict) -> None:
    exists = os.path.exists(CSV_PATH)
    try:
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            if not exists:
                writer.writeheader()
            writer.writerow({col: trade.get(col, "") for col in COLUMNS})
    except Exception as exc:
        log.error("Failed to write trade to %s: %s", CSV_PATH, exc)


def update_row(trade_id: str, updates: dict) -> None:
    """
    Overwrite fields on the row with matching id.
    Called by position_tracker when updating P&L or closing a trade.
    """
    rows = _read_all()
    changed = False
    for row in rows:
        if row.get("id") == str(trade_id):
            row.update(updates)
            changed = True
            break

    if not changed:
        log.warning("update_row: id %s not found", trade_id)
        return

    try:
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except Exception as exc:
        log.error("Failed to rewrite %s: %s", CSV_PATH, exc)


# ------------------------------------------------------------------ #
# Utilities

def _next_id() -> str:
    rows = _read_all()
    if not rows:
        return "1"
    try:
        return str(max(int(r.get("id", 0)) for r in rows) + 1)
    except (ValueError, TypeError):
        return str(len(rows) + 1)


def _primary_raw(result: AnalysisResult) -> dict | None:
    if result.deepseek and result.deepseek.ok:
        return result.deepseek.raw
    if result.gpt and result.gpt.ok:
        return result.gpt.raw
    return None


def _parse_date_ts(date_str: str) -> float | None:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).timestamp()
        except ValueError:
            continue
    return None
