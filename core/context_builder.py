"""
Context builder — assembles all live data and fills the analysis prompt.

Two public functions:

  build_messages(ticker, open_positions, stopout_log)
      → {"messages": [...], "blocked": bool, "block_reason": str|None,
         "flow_score": int, "should_call_llm": bool}

      Full pipeline:
        1. Hard block check (event_filters) — skip LLM if blocked
        2. Fetch technicals, earnings, VIX, SPY/QQQ context (historical_feed)
        3. Fetch flow + dark pool (uw_feed)
        4. Score flow (flow_verifier) — skip LLM if score < threshold
        5. Fetch market tide (market_tide)
        6. Pick suggested options contract (robinhood_feed)
        7. Fill analysis_prompt.md template
        8. Build system message with knowledge files prepended

  build_system_message()
      → the static system string (knowledge files + system_prompt.md)
      Cached after first call — knowledge files don't change at runtime.
"""

import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from feeds.historical_feed import get_technicals, get_earnings_date, get_vix
from feeds.robinhood_feed import get_expiry_dates, get_options_chain
from feeds.uw_feed import get_flow_alerts, get_darkpool
from signals.event_filters import check_all, get_session_status
from signals.flow_verifier import verify_flow, should_call_llm
from signals.market_tide import get_tide, is_aligned
from core import data_bus
from config.settings import CORRELATION_GROUPS, MIN_EXPIRY_DAYS, BYPASS_FLOW_FILTER

log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Cache the static system message — it never changes between scans
_system_message_cache: str | None = None

# Knowledge files loaded in this order (never reorder — playbook must be first)
KNOWLEDGE_FILES = [
    "knowledge/playbook.md",
    "knowledge/risk_rules.md",
    "knowledge/flow_interpretation.md",
    "knowledge/options_basics.md",
    "knowledge/symbol_profiles.md",
]
SYSTEM_PROMPT_FILE = "prompts/system_prompt.md"
ANALYSIS_PROMPT_FILE = "prompts/analysis_prompt.md"


# ------------------------------------------------------------------ #
# Main entry point

def build_messages(
    ticker: str,
    open_positions: list[dict],
    stopout_log: list[dict],
) -> dict:
    """
    Full pipeline for one ticker. Returns a result dict the scan loop uses.

    Result keys:
      messages       → list[dict] ready for OpenRouter API (system + user)
      blocked        → True if a hard block fired before LLM
      block_reason   → human-readable block reason or None
      flow_score     → integer flow score (0 if no flow)
      should_call_llm→ False if flow score below threshold (save the API call)
      live_data      → the assembled data dict (useful for logging/debugging)
    """

    # ── 1. Hard block check ──────────────────────────────────────────
    blocked, block_reason = check_all(ticker, open_positions, stopout_log)
    if blocked:
        return _blocked_result(block_reason)

    # ── 2. Technical data ────────────────────────────────────────────
    tech      = get_technicals(ticker)
    spy_tech  = get_technicals("SPY")
    qqq_tech  = get_technicals("QQQ")
    vix       = get_vix()
    earn_date, earn_days = get_earnings_date(ticker)

    # Override yfinance's delayed current price with Finnhub real-time tick
    rt_price = data_bus.get_price(ticker)
    if rt_price:
        tech["current_price"] = rt_price

    # ── 3. Flow + dark pool ──────────────────────────────────────────
    prints   = get_flow_alerts(ticker, limit=50)
    darkpool = get_darkpool(ticker, hours=2)

    # ── 4. Market tide ───────────────────────────────────────────────
    tide = get_tide()

    # ── 5. Score flow ────────────────────────────────────────────────
    current_price = tech.get("current_price")
    tide_aligned  = is_aligned(tide, _guess_direction(tech, tide))

    flow = verify_flow(
        ticker=ticker,
        prints=prints,
        darkpool=darkpool,
        current_price=current_price,
        market_tide_aligned=tide_aligned,
    )

    if not should_call_llm(flow) and not BYPASS_FLOW_FILTER:
        return {
            "messages":       [],
            "blocked":        False,
            "block_reason":   None,
            "flow_score":     flow["score"],
            "should_call_llm": False,
            "live_data":      {},
        }

    # ── 6. Options contract ──────────────────────────────────────────
    contract = _pick_contract(ticker, flow["direction"], current_price)

    # ── 7. Assemble live_data dict ───────────────────────────────────
    live_data = _assemble(
        ticker, tech, spy_tech, qqq_tech, vix,
        earn_date, earn_days, tide, flow, contract,
        open_positions, stopout_log,
    )

    # ── 8. Fill prompt template ──────────────────────────────────────
    user_message   = _fill_analysis_prompt(ticker, live_data)
    system_message = build_system_message()

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user",   "content": user_message},
    ]

    return {
        "messages":        messages,
        "blocked":         False,
        "block_reason":    None,
        "flow_score":      flow["score"],
        "should_call_llm": True,
        "live_data":       live_data,
    }


# ------------------------------------------------------------------ #
# System message (cached)

def build_system_message() -> str:
    global _system_message_cache
    if _system_message_cache:
        return _system_message_cache

    parts = []
    for path in KNOWLEDGE_FILES:
        try:
            with open(path, "r", encoding="utf-8") as f:
                parts.append(f.read())
        except FileNotFoundError:
            log.warning("Knowledge file not found: %s", path)

    try:
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
            raw = f.read()
        # extract the prompt block between the first pair of ``` markers
        system_prompt = raw.split("```")[1].strip()
    except (FileNotFoundError, IndexError) as exc:
        log.error("Could not load system prompt: %s", exc)
        system_prompt = ""

    _system_message_cache = "\n\n---\n\n".join(parts) + "\n\n---\n\n" + system_prompt
    return _system_message_cache


# ------------------------------------------------------------------ #
# Data assembly

def _assemble(
    ticker, tech, spy_tech, qqq_tech, vix,
    earn_date, earn_days, tide, flow, contract,
    open_positions, stopout_log,
) -> dict:

    open_trades = [p for p in open_positions if p.get("status") == "open"]
    group = CORRELATION_GROUPS.get(ticker, "none")
    group_occupied = any(
        CORRELATION_GROUPS.get(p.get("ticker")) == group and p.get("ticker") != ticker
        for p in open_trades
    )

    return {
        # Time
        "scan_time":       _scan_time(),
        "session_status":  get_session_status(),

        # Price & structure
        "price":           tech.get("current_price", "N/A"),
        "change_pct":      tech.get("price_change_pct", "N/A"),
        "change_direction":tech.get("price_change_direction", "N/A"),
        "volume_ratio":    tech.get("volume_ratio", "N/A"),
        "volume_label":    tech.get("volume_label", "N/A"),
        "ema_21":          tech.get("ema_21", "N/A"),
        "price_vs_ema21":  tech.get("price_vs_ema21", "N/A"),
        "sma_50":          tech.get("sma_50", "N/A"),
        "price_vs_sma50":  tech.get("price_vs_sma50", "N/A"),
        "vwap":            tech.get("vwap", "N/A"),
        "price_vs_vwap":   tech.get("price_vs_vwap", "N/A"),
        "resistance":      tech.get("resistance", "N/A"),
        "resistance_dist": tech.get("resistance_dist", "N/A"),
        "support":         tech.get("support", "N/A"),
        "support_dist":    tech.get("support_dist", "N/A"),
        "high_52w":        tech.get("high_52w", "N/A"),
        "low_52w":         tech.get("low_52w", "N/A"),
        "trend_structure": tech.get("trend_structure", "N/A"),

        # Macro context
        "spy_change":      spy_tech.get("price_change_pct", "N/A"),
        "spy_vs_vwap":     _vs_vwap_str(spy_tech),
        "qqq_change":      qqq_tech.get("price_change_pct", "N/A"),
        "qqq_vs_vwap":     _vs_vwap_str(qqq_tech),
        "vix":             round(vix, 1),
        "vix_label":       _vix_label(vix),
        "market_tide_score":     tide.get("score", 50),
        "market_tide_direction": tide.get("direction", "neutral"),

        # Options contract
        "strike":       contract.get("strike", "N/A"),
        "option_type":  contract.get("option_type", "call"),
        "expiry":       contract.get("expiry", "N/A"),
        "dte":          contract.get("dte", "N/A"),
        "ivr":          contract.get("ivr", "N/A"),
        "ivr_label":    _ivr_label(contract.get("ivr")),
        "open_interest":contract.get("open_interest", "N/A"),
        "spread":       contract.get("spread", "N/A"),
        "delta":        contract.get("delta", "N/A"),
        "theta":        contract.get("theta", "N/A"),

        # Earnings
        "earnings_date":   earn_date or "N/A",
        "earnings_days":   earn_days if earn_days is not None else "N/A",
        "earnings_status": _earnings_status(earn_days),

        # Flow
        "flow_status":     flow.get("status", "none"),
        "flow_prints":     flow.get("formatted_prints", "No unusual flow detected."),
        "spread_detected": flow.get("spread_detected", False),
        "net_premium":     f"{flow.get('net_premium', 0):,}",
        "darkpool":        flow.get("darkpool_summary", "none"),

        # Positions
        "open_count":      len(open_trades),
        "open_positions":  _format_positions(open_trades),
        "corr_group":      f"{group} [{', '.join(_group_members(group))}]",
        "group_occupied":  group_occupied,
        "recent_stopouts": _format_stopouts(stopout_log),
    }


# ------------------------------------------------------------------ #
# Contract selection

def _pick_contract(ticker: str, flow_direction: str, current_price: float | None) -> dict:
    """
    Pick the best options contract to suggest:
    - expiry: first one with 21–45 DTE (sweet spot)
    - type: call for bullish flow, put for bearish
    - strike: closest to 0.40 delta (slightly OTM)
    Falls back gracefully if Tradier returns nothing.
    """
    opt_type = "call" if flow_direction == "bullish" else "put"

    expiries = get_expiry_dates(ticker)
    target_expiry = _pick_expiry(expiries, min_dte=21, max_dte=45)
    if not target_expiry:
        target_expiry = _pick_expiry(expiries, min_dte=MIN_EXPIRY_DAYS, max_dte=60)
    if not target_expiry:
        return {}

    chain = get_options_chain(ticker, target_expiry)
    contracts = [c for c in chain if c["type"] == opt_type]
    if not contracts:
        return {}

    best = _closest_to_delta(contracts, target_delta=0.40)
    if not best:
        return {}

    # Estimate IVR from current IV vs historical volatility range
    ivr = _estimate_ivr(ticker, best.get("iv"))

    return {
        "strike":       best.get("strike"),
        "option_type":  opt_type,
        "expiry":       best.get("expiry"),
        "dte":          best.get("dte"),
        "ivr":          ivr,
        "open_interest":best.get("open_interest"),
        "spread":       round((best.get("ask", 0) or 0) - (best.get("bid", 0) or 0), 2),
        "delta":        best.get("delta"),
        "theta":        best.get("theta"),
        "ask":          best.get("ask"),
    }


def _pick_expiry(expiries: list[str], min_dte: int, max_dte: int) -> str | None:
    from datetime import date, datetime
    today = date.today()
    for exp in expiries:
        try:
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
            if min_dte <= dte <= max_dte:
                return exp
        except ValueError:
            continue
    return None


def _closest_to_delta(contracts: list[dict], target_delta: float) -> dict | None:
    valid = [c for c in contracts if c.get("delta") is not None]
    if not valid:
        # fall back to roughly ATM by strike proximity
        return contracts[len(contracts) // 2] if contracts else None
    return min(valid, key=lambda c: abs(abs(c["delta"]) - target_delta))


def _estimate_ivr(ticker: str, current_iv: float | None) -> int | None:
    """
    Approximate IVR using 60-day historical volatility as a proxy.
    True IVR needs historical IV data; this is a reasonable v1 estimate.
    """
    if current_iv is None:
        return None
    try:
        from feeds.historical_feed import get_ohlcv
        import numpy as np
        df = get_ohlcv(ticker, days=252)
        if df.empty or len(df) < 30:
            return None
        log_returns = np.log(df["Close"] / df["Close"].shift(1)).dropna()
        hv_30  = float(log_returns.tail(30).std()  * np.sqrt(252))
        hv_252 = float(log_returns.std() * np.sqrt(252))
        hv_min = log_returns.rolling(30).std().min() * np.sqrt(252)
        hv_max = log_returns.rolling(30).std().max() * np.sqrt(252)
        if hv_max == hv_min:
            return None
        # Use current IV vs HV range as IVR proxy
        ivr = int(round((current_iv - float(hv_min)) / (float(hv_max) - float(hv_min)) * 100))
        return max(0, min(100, ivr))
    except Exception:
        return None


# ------------------------------------------------------------------ #
# Formatting helpers

def _fill_analysis_prompt(ticker: str, live_data: dict) -> str:
    try:
        with open(ANALYSIS_PROMPT_FILE, "r", encoding="utf-8") as f:
            raw = f.read()
        # extract the first ``` block (the prompt template itself)
        prompt = raw.split("```")[1].strip()
    except (FileNotFoundError, IndexError) as exc:
        log.error("Could not load analysis prompt: %s", exc)
        return f"Analyze {ticker} for a potential options trade."

    try:
        return prompt.format(
            ticker=ticker,
            scan_time=live_data["scan_time"],
            session_status=live_data["session_status"],
            current_price=live_data["price"],
            price_change_pct=live_data["change_pct"],
            price_change_direction=live_data["change_direction"],
            volume_ratio=live_data["volume_ratio"],
            volume_label=live_data["volume_label"],
            ema_21=live_data["ema_21"],
            price_vs_ema21=live_data["price_vs_ema21"],
            sma_50=live_data["sma_50"],
            price_vs_sma50=live_data["price_vs_sma50"],
            vwap=live_data["vwap"],
            price_vs_vwap=live_data["price_vs_vwap"],
            resistance_level=live_data["resistance"],
            resistance_distance=live_data["resistance_dist"],
            support_level=live_data["support"],
            support_distance=live_data["support_dist"],
            high_52w=live_data["high_52w"],
            low_52w=live_data["low_52w"],
            trend_structure=live_data["trend_structure"],
            spy_change_pct=live_data["spy_change"],
            spy_vs_vwap=live_data["spy_vs_vwap"],
            qqq_change_pct=live_data["qqq_change"],
            qqq_vs_vwap=live_data["qqq_vs_vwap"],
            vix_level=live_data["vix"],
            vix_label=live_data["vix_label"],
            market_tide_score=live_data["market_tide_score"],
            market_tide_direction=live_data["market_tide_direction"],
            suggested_strike=live_data["strike"],
            option_type=live_data["option_type"],
            suggested_expiry=live_data["expiry"],
            dte=live_data["dte"],
            ivr=live_data["ivr"],
            ivr_label=live_data["ivr_label"],
            open_interest=live_data["open_interest"],
            bid_ask_spread=live_data["spread"],
            delta=live_data["delta"],
            theta_daily=live_data["theta"],
            earnings_date=live_data["earnings_date"],
            earnings_days_away=live_data["earnings_days"],
            earnings_buffer_status=live_data["earnings_status"],
            flow_status=live_data["flow_status"],
            flow_prints_block=live_data["flow_prints"],
            spread_detected=live_data["spread_detected"],
            net_flow_premium=live_data["net_premium"],
            darkpool_summary=live_data["darkpool"],
            open_positions_count=live_data["open_count"],
            open_positions_block=live_data["open_positions"],
            correlation_group=live_data["corr_group"],
            group_occupied=live_data["group_occupied"],
            recent_stopouts=live_data["recent_stopouts"],
        )
    except KeyError as exc:
        log.error("Missing live_data key when filling prompt: %s", exc)
        return f"Analyze {ticker} for a potential options trade. (Data assembly error: {exc})"


def _format_positions(open_trades: list[dict]) -> str:
    if not open_trades:
        return "No open positions."
    lines = []
    for p in open_trades:
        pnl = p.get("pnl_pct")
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else "N/A"
        lines.append(
            f"  • {p.get('ticker')} {p.get('direction','').upper()} "
            f"{p.get('type','').upper()} ${p.get('strike')} {p.get('expiry')} "
            f"— entered ${p.get('entry_price')}, currently {pnl_str}"
        )
    return "\n".join(lines)


def _format_stopouts(stopout_log: list[dict]) -> str:
    import time
    now = time.time()
    from config.settings import STOPOUT_COOLDOWN_HOURS
    active = []
    for s in stopout_log:
        age_hrs = (now - (s.get("closed_at") or 0)) / 3600
        if age_hrs < STOPOUT_COOLDOWN_HOURS:
            remaining = STOPOUT_COOLDOWN_HOURS - age_hrs
            closed_str = _ts_to_timestr(s.get("closed_at"))
            active.append(
                f"{s.get('ticker')} stopped out at {closed_str} "
                f"— no re-entry for {remaining:.1f}h"
            )
    return "\n".join(f"  • {s}" for s in active) if active else "none"


def _group_members(group: str) -> list[str]:
    return [t for t, g in CORRELATION_GROUPS.items() if g == group]


def _guess_direction(tech: dict, tide: dict) -> str:
    """Rough direction hint for market tide alignment check — not used for LLM."""
    tide_dir = tide.get("direction", "neutral")
    if tide_dir != "neutral":
        return tide_dir
    trend = tech.get("trend_structure", "")
    if "uptrend" in trend:
        return "bullish"
    if "downtrend" in trend:
        return "bearish"
    return "neutral"


def _vs_vwap_str(tech: dict) -> str:
    direction = tech.get("price_vs_vwap", "unknown")
    return f"{direction} VWAP"


def _scan_time() -> str:
    now = datetime.now(ET)
    hour = now.hour % 12 or 12
    return f"{hour}:{now.minute:02d}{'am' if now.hour < 12 else 'pm'}"


def _vix_label(vix: float) -> str:
    if vix < 15:
        return "very low — very favorable for long premium"
    if vix < 20:
        return "low — favorable for long premium"
    if vix < 25:
        return "moderate"
    if vix < 30:
        return "elevated — options getting expensive"
    return "high — hard block territory"


def _ivr_label(ivr: int | None) -> str:
    if ivr is None:
        return "unknown"
    if ivr < 30:
        return "cheap"
    if ivr < 50:
        return "normal"
    if ivr < 70:
        return "elevated"
    return "expensive"


def _earnings_status(days_away: int | None) -> str:
    if days_away is None:
        return "UNKNOWN"
    if days_away < 5:
        return "HARD BLOCK"
    if days_away <= 10:
        return "WARNING"
    return "CLEAR"


def _ts_to_timestr(ts: float | None) -> str:
    if not ts:
        return "unknown"
    from datetime import datetime
    dt = datetime.fromtimestamp(ts, tz=ET)
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d}{'am' if dt.hour < 12 else 'pm'}"


def _blocked_result(reason: str) -> dict:
    return {
        "messages":        [],
        "blocked":         True,
        "block_reason":    reason,
        "flow_score":      0,
        "should_call_llm": False,
        "live_data":       {},
    }
