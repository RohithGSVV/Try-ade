"""
Unusual Whales REST feed.

Three public functions used by flow_verifier.py and market_tide.py:
  get_flow_alerts(ticker, limit)   → recent options flow prints for one ticker
  get_darkpool(ticker, hours)      → recent dark pool prints for one ticker
  get_market_tide()                → current market tide score (0–100)

Flow alert dict shape:
    {
        "ticker":      "AAPL",
        "ts":          1713430800.0,      # unix epoch
        "time_str":    "11:14am",
        "premium":     1_200_000,         # total premium in dollars
        "strike":      220.0,
        "expiry":      "2025-05-16",
        "dte":         28,
        "option_type": "call" | "put",
        "trade_type":  "sweep" | "block" | "split",
        "side":        "ask" | "bid" | "mid",
        "direction":   "bullish" | "bearish" | "neutral",
    }

Dark pool print dict shape:
    {
        "ticker":   "AAPL",
        "ts":       1713430800.0,
        "shares":   280_000,
        "price":    216.80,
        "direction": "bullish" | "bearish" | "neutral",
    }
"""

import logging
from datetime import date, datetime

import requests

from config.settings import UW_API_KEY, UW_BASE_URL, WATCHLIST

log = logging.getLogger(__name__)

_HEADERS = {
    "Authorization": f"Bearer {UW_API_KEY}",
    "Accept": "application/json",
}


def get_flow_alerts(ticker: str, limit: int = 50) -> list[dict]:
    """
    Fetch recent unusual options flow for ticker from UW.
    Returns most recent `limit` prints, newest first.
    Returns [] silently if UW_API_KEY is not set.
    """
    if not UW_API_KEY:
        return []

    url = f"{UW_BASE_URL}/api/option-trades/flow"
    params = {"ticker": ticker, "limit": limit, "order": "desc"}

    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        log.error("UW flow fetch failed for %s: %s", ticker, exc)
        return []

    prints = raw.get("data") or []
    results = []
    today = date.today()

    for p in prints:
        try:
            ts = _parse_ts(p.get("created_at") or p.get("date"))
            exp_str = p.get("expiry") or p.get("expiration_date", "")
            dte = None
            if exp_str:
                try:
                    exp_date = datetime.strptime(exp_str[:10], "%Y-%m-%d").date()
                    dte = (exp_date - today).days
                except ValueError:
                    pass

            side = _normalize_side(p.get("put_call_side") or p.get("side") or "")
            option_type = (p.get("put_call") or "").lower()
            direction = _infer_direction(option_type, side)

            results.append({
                "ticker":      ticker,
                "ts":          ts,
                "time_str":    _fmt_time(ts),
                "premium":     _to_int(p.get("premium") or p.get("total_premium")),
                "strike":      _to_float(p.get("strike")),
                "expiry":      exp_str[:10] if exp_str else None,
                "dte":         dte,
                "option_type": option_type,
                "trade_type":  _normalize_trade_type(p.get("type") or p.get("trade_type") or ""),
                "side":        side,
                "direction":   direction,
            })
        except Exception:
            log.debug("Skipped malformed UW flow record: %s", p)
            continue

    return results


def get_darkpool(ticker: str, hours: int = 2) -> list[dict]:
    """
    Fetch recent dark pool prints for ticker.
    Returns [] silently if UW_API_KEY is not set.
    """
    if not UW_API_KEY:
        return []

    url = f"{UW_BASE_URL}/api/darkpool/{ticker}"
    params = {"limit": 20}

    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        log.error("UW dark pool fetch failed for %s: %s", ticker, exc)
        return []

    prints = raw.get("data") or []
    results = []

    for p in prints:
        try:
            ts = _parse_ts(p.get("date") or p.get("created_at"))
            direction = (p.get("bullish_bearish") or "neutral").lower()
            results.append({
                "ticker":    ticker,
                "ts":        ts,
                "shares":    _to_int(p.get("size") or p.get("shares")),
                "price":     _to_float(p.get("price")),
                "direction": direction if direction in ("bullish", "bearish") else "neutral",
            })
        except Exception:
            log.debug("Skipped malformed UW dark pool record: %s", p)
            continue

    return results


def get_market_tide() -> dict:
    """
    Fetch the current UW Market Tide score.
    Returns {"score": 50, "direction": "neutral"} silently if UW_API_KEY is not set.
    """
    if not UW_API_KEY:
        return {"score": 50, "direction": "neutral"}

    url = f"{UW_BASE_URL}/api/market/market-tide"

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        log.error("UW market tide fetch failed: %s", exc)
        return {"score": 50, "direction": "neutral"}

    data = raw.get("data") or {}
    score = _to_float(data.get("score") or data.get("tide_score")) or 50.0

    if score > 65:
        direction = "bullish"
    elif score < 35:
        direction = "bearish"
    else:
        direction = "neutral"

    return {"score": round(score), "direction": direction}


# ------------------------------------------------------------------ #

def _parse_ts(value) -> float:
    """Parse ISO string or epoch int/float → unix timestamp float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        # could be ms or seconds
        return value / 1000 if value > 1e12 else float(value)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        return 0.0


def _fmt_time(ts: float) -> str:
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts)
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d}{'am' if dt.hour < 12 else 'pm'}"


def _normalize_side(raw: str) -> str:
    raw = raw.lower()
    if "ask" in raw or "above" in raw:
        return "ask"
    if "bid" in raw or "below" in raw:
        return "bid"
    return "mid"


def _normalize_trade_type(raw: str) -> str:
    raw = raw.lower()
    if "sweep" in raw:
        return "sweep"
    if "block" in raw:
        return "block"
    if "split" in raw:
        return "split"
    return "block"


def _infer_direction(option_type: str, side: str) -> str:
    """
    call + ask → bullish directional
    put  + ask → bearish directional
    anything on bid → closing (neutral for signal purposes)
    """
    if side == "bid":
        return "neutral"
    if option_type == "call":
        return "bullish"
    if option_type == "put":
        return "bearish"
    return "neutral"


def _to_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _to_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
