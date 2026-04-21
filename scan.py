"""
Scan cycle — runs once every SCAN_INTERVAL_MIN minutes.

Steps per cycle:
  1. Update all open positions (P&L, auto-close)
  2. For each ticker in WATCHLIST:
       a. Build context (hard block check + flow score + prompt)
       b. If flow score too low → skip (save API call)
       c. Call both LLMs in parallel
       d. If consensus alert → log paper trade
  3. Return a summary of the cycle

Called by main.py on a schedule.
"""

import logging
import time
from dataclasses import dataclass, field

from config.settings import WATCHLIST
from core.context_builder import build_messages
from core.llm_engine import analyze, AnalysisResult
from trading.paper_trader import log_trade
from trading.position_tracker import update_all

log = logging.getLogger(__name__)


@dataclass
class CycleSummary:
    started_at:    float = field(default_factory=time.time)
    tickers_scanned: int = 0
    hard_blocked:  int   = 0
    low_flow:      int   = 0
    llm_calls:     int   = 0
    alerts_fired:  int   = 0
    trades_logged: int   = 0
    errors:        int   = 0
    duration_s:    float = 0.0


def run_scan_cycle() -> CycleSummary:
    summary = CycleSummary()
    log.info("─── Scan cycle starting (%d symbols) ───", len(WATCHLIST))

    # ── Step 1: refresh positions ────────────────────────────────────
    try:
        open_positions, stopout_log, closed = update_all()
        if closed:
            log.info("Auto-closed %d position(s) this cycle", len(closed))
    except Exception as exc:
        log.error("Position update failed: %s", exc)
        open_positions, stopout_log = [], []

    # ── Step 2: scan each ticker ─────────────────────────────────────
    for ticker in WATCHLIST:
        summary.tickers_scanned += 1
        try:
            _scan_ticker(ticker, open_positions, stopout_log, summary)
        except Exception as exc:
            log.error("Unhandled error scanning %s: %s", ticker, exc)
            summary.errors += 1

    summary.duration_s = round(time.time() - summary.started_at, 1)
    _log_summary(summary)
    return summary


# ------------------------------------------------------------------ #

def _scan_ticker(
    ticker: str,
    open_positions: list[dict],
    stopout_log: list[dict],
    summary: CycleSummary,
) -> None:

    # Build context + run hard block + flow score check
    ctx = build_messages(ticker, open_positions, stopout_log)

    if ctx["blocked"]:
        log.info("  %-6s BLOCKED  — %s", ticker, ctx["block_reason"])
        summary.hard_blocked += 1
        return

    if not ctx["should_call_llm"]:
        log.info("  %-6s LOW FLOW — score=%d (threshold %d)",
                 ticker, ctx["flow_score"], 4)
        summary.low_flow += 1
        return

    # Call both LLMs
    log.info("  %-6s ANALYZING — flow score=%d", ticker, ctx["flow_score"])
    summary.llm_calls += 1

    result: AnalysisResult = analyze(ticker, ctx["messages"], ctx["flow_score"])

    if result.alert:
        summary.alerts_fired += 1
        tag = "CONSENSUS" if result.consensus else "SINGLE"
        log.info(
            "  %-6s ALERT [%s] %s | DS=%.2f GPT=%.2f",
            ticker, tag, result.direction.upper(),
            result.deepseek.confidence if result.deepseek and result.deepseek.ok else 0,
            result.gpt.confidence if result.gpt and result.gpt.ok else 0,
        )
        trade = log_trade(ticker, result, ctx["live_data"])
        if trade:
            summary.trades_logged += 1
            # Refresh open_positions so correlation check is current for next ticker
            from trading.paper_trader import get_open_positions
            open_positions[:] = get_open_positions()
    else:
        _log_skip_reason(ticker, result)


def _log_skip_reason(ticker: str, result: AnalysisResult) -> None:
    ds  = result.deepseek
    gpt = result.gpt

    if ds and ds.ok and gpt and gpt.ok:
        if ds.direction != gpt.direction:
            log.info(
                "  %-6s SKIP — direction conflict (DS=%s GPT=%s)",
                ticker, ds.direction, gpt.direction,
            )
        else:
            log.info(
                "  %-6s SKIP — below threshold (DS=%.2f GPT=%.2f)",
                ticker,
                ds.confidence if ds.ok else 0,
                gpt.confidence if gpt.ok else 0,
            )
    elif ds and ds.ok:
        log.info("  %-6s SKIP — single model, conf=%.2f", ticker, ds.confidence)
    elif gpt and gpt.ok:
        log.info("  %-6s SKIP — single model, conf=%.2f", ticker, gpt.confidence)
    else:
        log.info("  %-6s SKIP — both models failed", ticker)


def _log_summary(s: CycleSummary) -> None:
    log.info(
        "─── Cycle done in %.1fs | scanned=%d blocked=%d low_flow=%d "
        "llm_calls=%d alerts=%d trades=%d errors=%d ───",
        s.duration_s, s.tickers_scanned, s.hard_blocked, s.low_flow,
        s.llm_calls, s.alerts_fired, s.trades_logged, s.errors,
    )
