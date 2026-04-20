"""
Position tracker — updates P&L each scan and auto-closes on stop/target/expiry.

Called once per scan cycle by the main scan loop BEFORE context_builder runs,
so open_positions and stopout_log are fresh when the LLM checks hard blocks.

Auto-close rules (from risk_rules.md):
  Stop loss:    option loses 50% of entry value  → outcome = "stop_loss"
  Take profit:  option gains 100% (doubles)      → outcome = "take_profit"
  Expiry DTE:   DTE reaches 5                    → outcome = "expired_early"
  Actual expiry:position past expiry date         → outcome = "expired"

Public API:
  update_all()  → (open_positions, stopout_log, closed_this_cycle)
                  Call at the start of every scan cycle.
"""

import logging
import time
from datetime import date, datetime

from feeds.tradier_feed import get_entry_price
from trading.paper_trader import get_open_positions, get_stopout_log, update_row
from config.settings import STOP_LOSS_PCT, TAKE_PROFIT_PCT, CLOSE_AT_DTE

log = logging.getLogger(__name__)


def update_all() -> tuple[list[dict], list[dict], list[dict]]:
    """
    Fetch current prices for all open positions, update P&L, auto-close if needed.

    Returns:
        open_positions   — list of still-open trade dicts (after closures)
        stopout_log      — list of recent stop-outs (for 24hr cooldown)
        closed_this_cycle— list of trades closed during this update
    """
    positions = get_open_positions()
    closed_this_cycle = []

    for pos in positions:
        try:
            updated, closed = _refresh_position(pos)
            if closed:
                closed_this_cycle.append(updated)
        except Exception as exc:
            log.error("Error refreshing position %s (%s): %s", pos.get("id"), pos.get("ticker"), exc)

    # Re-read after potential closures
    open_positions = get_open_positions()
    stopout_log    = get_stopout_log()

    if closed_this_cycle:
        log.info(
            "Auto-closed %d position(s) this cycle: %s",
            len(closed_this_cycle),
            [f"{p['ticker']} ({p['outcome']})" for p in closed_this_cycle],
        )

    return open_positions, stopout_log, closed_this_cycle


# ------------------------------------------------------------------ #
# Per-position refresh

def _refresh_position(pos: dict) -> tuple[dict, bool]:
    """
    Fetch current price, compute P&L, check auto-close rules.
    Returns (updated_pos, was_closed).
    """
    ticker     = pos.get("ticker", "")
    strike     = _to_float(pos.get("strike"))
    expiry     = pos.get("expiry", "")
    opt_type   = pos.get("type", "call")
    entry_price= _to_float(pos.get("entry_price"))
    trade_id   = pos.get("id")

    if not all([ticker, strike, expiry, entry_price]):
        log.warning("Skipping position %s — missing required fields", trade_id)
        return pos, False

    # ── Check expiry ────────────────────────────────────────────────
    today = date.today()
    try:
        exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        dte      = (exp_date - today).days
    except ValueError:
        dte = None

    # Already past expiry
    if dte is not None and dte < 0:
        return _close(pos, exit_price=0.0, outcome="expired")

    # DTE reached close-early threshold
    if dte is not None and dte <= CLOSE_AT_DTE:
        current_price = _fetch_price(ticker, strike, expiry, opt_type)
        ep = current_price if current_price is not None else 0.0
        return _close(pos, exit_price=ep, outcome="expired_early")

    # ── Fetch current price ─────────────────────────────────────────
    current_price = _fetch_price(ticker, strike, expiry, opt_type)
    if current_price is None:
        log.warning("Could not fetch current price for %s %s — skipping update", ticker, trade_id)
        return pos, False

    # ── P&L ─────────────────────────────────────────────────────────
    pnl_pct = round((current_price - entry_price) / entry_price * 100, 1)

    # ── Auto-close checks ────────────────────────────────────────────
    if pnl_pct <= -(STOP_LOSS_PCT * 100):
        return _close(pos, exit_price=current_price, outcome="stop_loss")

    if pnl_pct >= (TAKE_PROFIT_PCT * 100):
        return _close(pos, exit_price=current_price, outcome="take_profit")

    # ── Update P&L only ─────────────────────────────────────────────
    updates = {"current_price": current_price, "pnl_pct": pnl_pct}
    update_row(trade_id, updates)
    pos.update(updates)

    log.debug(
        "%s pos %s: current=$%.2f pnl=%+.1f%% DTE=%s",
        ticker, trade_id, current_price, pnl_pct, dte,
    )
    return pos, False


def _close(pos: dict, exit_price: float, outcome: str) -> tuple[dict, bool]:
    entry_price = _to_float(pos.get("entry_price")) or 0
    pnl_pct = round((exit_price - entry_price) / entry_price * 100, 1) if entry_price else 0.0

    updates = {
        "status":        "closed",
        "current_price": exit_price,
        "exit_price":    exit_price,
        "pnl_pct":       pnl_pct,
        "outcome":       outcome,
    }
    update_row(pos.get("id"), updates)
    pos.update(updates)

    emoji = {"stop_loss": "🔴", "take_profit": "🟢", "expired_early": "⏱️", "expired": "⏱️"}.get(outcome, "⚪")
    log.info(
        "%s %s %s | %s %s | P&L: %+.1f%% | exit=$%.2f",
        emoji, pos.get("ticker"), pos.get("id"), outcome, pos.get("expiry"),
        pnl_pct, exit_price,
    )

    _send_close_alert(pos, exit_price, outcome, pnl_pct)
    return pos, True


# ------------------------------------------------------------------ #
# Discord close alert

def _send_close_alert(pos: dict, exit_price: float, outcome: str, pnl_pct: float) -> None:
    from config.settings import DISCORD_WEBHOOK_URL
    import requests

    if not DISCORD_WEBHOOK_URL:
        return

    labels = {
        "stop_loss":    ("🔴 STOPPED OUT",  "Stop loss hit"),
        "take_profit":  ("🟢 TAKE PROFIT",  "Target reached — doubled"),
        "expired_early":("⏱️ CLOSED EARLY", f"DTE ≤ {CLOSE_AT_DTE} — theta decay"),
        "expired":      ("⏱️ EXPIRED",       "Past expiry date"),
    }
    header, reason = labels.get(outcome, ("⚪ CLOSED", outcome))
    ticker    = pos.get("ticker", "")
    direction = pos.get("direction", "").upper()
    opt_type  = pos.get("type", "").upper()
    strike    = pos.get("strike", "")
    expiry    = pos.get("expiry", "")
    entry     = pos.get("entry_price", "")
    pnl_sign  = "+" if pnl_pct >= 0 else ""

    content = (
        f"{header} — **{ticker} {direction} {opt_type} ${strike} {expiry}**\n"
        f"```\n"
        f"Reason : {reason}\n"
        f"Entry  : ${entry}  →  Exit: ${exit_price:.2f}\n"
        f"P&L    : {pnl_sign}{pnl_pct:.1f}%\n"
        f"```"
    )

    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": content}, timeout=10)
    except Exception as exc:
        log.warning("Close alert Discord send failed: %s", exc)


# ------------------------------------------------------------------ #
# Helpers

def _fetch_price(ticker: str, strike: float, expiry: str, opt_type: str) -> float | None:
    return get_entry_price(ticker, strike, expiry, opt_type)


def _to_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
