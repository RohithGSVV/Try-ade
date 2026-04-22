"""
Historical data feed via yfinance. No API key required.

Used by context_builder.py every scan to compute technical levels:
  get_technicals(ticker)   → dict with EMA, SMA, VWAP, 52w high/low,
                              support/resistance, trend structure, volume ratio
  get_earnings_date(ticker)→ (date_str, days_away) or (None, None)
  get_ohlcv(ticker, days)  → DataFrame of daily OHLCV (backtesting / EMA seed data)

All results are cached per ticker for CACHE_TTL_MINUTES so repeated calls
within the same scan cycle don't hit Yahoo Finance multiple times.
"""

import logging
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# Simple in-process cache: recompute technicals at most once per scan cycle.
# key = (ticker, minute_bucket) so it refreshes every 10 min automatically.
_CACHE: dict = {}
CACHE_TTL_MINUTES = 10


def get_technicals(ticker: str) -> dict:
    """
    Return all technical indicators needed to fill the analysis prompt.

    Returned dict keys (all used as {placeholders} in analysis_prompt.md):
        current_price, price_change_pct, price_change_direction,
        volume_ratio, volume_label,
        ema_21, price_vs_ema21,
        sma_50, price_vs_sma50,
        vwap,  price_vs_vwap,
        resistance, resistance_dist,
        support,    support_dist,
        high_52w, low_52w,
        trend_structure,
        spy_change, spy_vs_vwap,   ← populated separately for SPY
        qqq_change, qqq_vs_vwap,   ← populated separately for QQQ
        vix                        ← fetched via get_vix()
    """
    bucket = _minute_bucket()
    cache_key = (ticker, bucket)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    result = _compute_technicals(ticker)
    _CACHE[cache_key] = result
    return result


def get_earnings_date(ticker: str) -> tuple[Optional[str], Optional[int]]:
    """
    Return (earnings_date_str "YYYY-MM-DD", days_away) or (None, None).
    Handles both old yfinance (DataFrame) and new yfinance (dict) calendar format.
    ETFs like SPY/QQQ have no earnings — returns (None, None) cleanly.
    """
    try:
        cal = yf.Ticker(ticker).calendar
        if not cal:
            return None, None

        # New yfinance (≥0.2.x) returns a dict: {'Earnings Date': [Timestamp, ...], ...}
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date") or []
            if not dates:
                return None, None
            earn_date = dates[0]
            if hasattr(earn_date, "date"):
                earn_date = earn_date.date()
            days_away = (earn_date - date.today()).days
            return str(earn_date), days_away

        # Old yfinance returned a DataFrame with dates as columns
        if hasattr(cal, "empty"):
            if cal.empty:
                return None, None
            earn_date = cal.columns[0]
            if hasattr(earn_date, "date"):
                earn_date = earn_date.date()
            days_away = (earn_date - date.today()).days
            return str(earn_date), days_away

        return None, None
    except Exception as exc:
        log.debug("Earnings date not available for %s: %s", ticker, exc)
        return None, None


def get_vix() -> float:
    """Fetch current VIX level. Returns 20.0 as a safe default on failure."""
    bucket = _minute_bucket()
    cache_key = ("^VIX", bucket)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    try:
        hist = yf.Ticker("^VIX").history(period="2d", interval="1d")
        vix = float(hist["Close"].iloc[-1])
    except Exception as exc:
        log.warning("VIX fetch failed: %s", exc)
        vix = 20.0

    _CACHE[cache_key] = vix
    return vix


def get_ohlcv(ticker: str, days: int = 90) -> pd.DataFrame:
    """
    Return daily OHLCV DataFrame for the last `days` calendar days.
    Used by backtesting and for seeding EMA/SMA with enough history.
    Columns: Open, High, Low, Close, Volume (index = date).
    """
    try:
        df = yf.Ticker(ticker).history(period=f"{days}d", interval="1d")
        df.index = df.index.date
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as exc:
        log.error("OHLCV fetch failed for %s: %s", ticker, exc)
        return pd.DataFrame()


# ------------------------------------------------------------------ #
# Internal computation

def _compute_technicals(ticker: str) -> dict:
    try:
        daily = yf.Ticker(ticker).history(period="60d", interval="1d")
        intraday = yf.Ticker(ticker).history(period="1d", interval="5m")
    except Exception as exc:
        log.error("yfinance fetch failed for %s: %s", ticker, exc)
        return _empty_technicals(ticker)

    if daily.empty or len(daily) < 2:
        return _empty_technicals(ticker)

    close   = daily["Close"]
    current = float(close.iloc[-1])
    prev    = float(close.iloc[-2])

    # Price change
    change_pct = round((current - prev) / prev * 100, 2)
    change_dir = "bullish" if change_pct >= 0 else "bearish"

    # Volume ratio (today vs 20-day avg)
    vol_today = float(daily["Volume"].iloc[-1])
    vol_avg   = float(daily["Volume"].iloc[-21:-1].mean()) if len(daily) >= 21 else vol_today
    vol_ratio = round(vol_today / vol_avg, 1) if vol_avg else 1.0
    vol_label = _volume_label(vol_ratio)

    # Moving averages
    ema_21 = _ema(close, 21)
    sma_50 = _sma(close, 50)

    # VWAP (intraday, today only)
    vwap = _calc_vwap(intraday)

    # 52-week high/low
    hist_52w = yf.Ticker(ticker).history(period="52wk", interval="1d")
    high_52w = round(float(hist_52w["High"].max()), 2) if not hist_52w.empty else current
    low_52w  = round(float(hist_52w["Low"].min()),  2) if not hist_52w.empty else current

    # Support / resistance (recent swing highs/lows over last 20 days)
    support, resistance = _find_levels(daily.tail(20), current)

    # Trend structure
    trend = _trend_structure(close)

    return {
        "current_price":        round(current, 2),
        "price_change_pct":     abs(change_pct),
        "price_change_direction": change_dir,
        "volume_ratio":         vol_ratio,
        "volume_label":         vol_label,
        "ema_21":               ema_21,
        "price_vs_ema21":       _above_below(current, ema_21),
        "sma_50":               sma_50,
        "price_vs_sma50":       _above_below(current, sma_50),
        "vwap":                 vwap,
        "price_vs_vwap":        _above_below(current, vwap),
        "resistance":           resistance,
        "resistance_dist":      round(abs(resistance - current) / current * 100, 1) if resistance else None,
        "support":              support,
        "support_dist":         round(abs(current - support) / current * 100, 1) if support else None,
        "high_52w":             high_52w,
        "low_52w":              low_52w,
        "trend_structure":      trend,
    }


def _ema(series: pd.Series, span: int) -> Optional[float]:
    if len(series) < span:
        return None
    return round(float(series.ewm(span=span, adjust=False).mean().iloc[-1]), 2)


def _sma(series: pd.Series, window: int) -> Optional[float]:
    if len(series) < window:
        return None
    return round(float(series.rolling(window).mean().iloc[-1]), 2)


def _calc_vwap(intraday: pd.DataFrame) -> Optional[float]:
    if intraday.empty:
        return None
    typical = (intraday["High"] + intraday["Low"] + intraday["Close"]) / 3
    vwap = (typical * intraday["Volume"]).cumsum() / intraday["Volume"].cumsum()
    return round(float(vwap.iloc[-1]), 2)


def _find_levels(df: pd.DataFrame, current: float) -> tuple[Optional[float], Optional[float]]:
    """
    Simple swing high/low: look for local highs above current price (resistance)
    and local lows below current price (support) using a 3-bar pivot.
    """
    highs = df["High"].values
    lows  = df["Low"].values

    resistances = []
    supports    = []

    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1] and highs[i] > current:
            resistances.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i+1] and lows[i] < current:
            supports.append(lows[i])

    resistance = round(float(min(resistances)), 2) if resistances else round(current * 1.02, 2)
    support    = round(float(max(supports)),    2) if supports    else round(current * 0.98, 2)
    return support, resistance


def _trend_structure(close: pd.Series) -> str:
    """
    Classify trend using last 10 closes:
    higher highs + higher lows → uptrend
    lower highs + lower lows   → downtrend
    otherwise                  → choppy range
    """
    if len(close) < 10:
        return "insufficient data"

    recent = close.iloc[-10:].values
    mid    = len(recent) // 2
    first_half  = recent[:mid]
    second_half = recent[mid:]

    hh = second_half.max() > first_half.max()
    hl = second_half.min() > first_half.min()
    lh = second_half.max() < first_half.max()
    ll = second_half.min() < first_half.min()

    low  = round(float(recent.min()), 2)
    high = round(float(recent.max()), 2)

    if hh and hl:
        return "higher highs and higher lows — uptrend intact"
    if lh and ll:
        return "lower highs and lower lows — downtrend"
    return f"choppy range between ${low} and ${high} — no clear trend"


def _above_below(price: Optional[float], level: Optional[float]) -> str:
    if price is None or level is None:
        return "unknown"
    return "above" if price >= level else "below"


def _volume_label(ratio: float) -> str:
    if ratio >= 2.0:
        return "very high"
    if ratio >= 1.3:
        return "elevated"
    if ratio >= 0.7:
        return "normal"
    return "low"


def _minute_bucket() -> int:
    """Returns current time floored to CACHE_TTL_MINUTES bucket."""
    now = datetime.now()
    return (now.hour * 60 + now.minute) // CACHE_TTL_MINUTES


def _empty_technicals(ticker: str) -> dict:
    log.warning("Returning empty technicals for %s", ticker)
    return {k: None for k in [
        "current_price", "price_change_pct", "price_change_direction",
        "volume_ratio", "volume_label",
        "ema_21", "price_vs_ema21", "sma_50", "price_vs_sma50",
        "vwap", "price_vs_vwap",
        "resistance", "resistance_dist", "support", "support_dist",
        "high_52w", "low_52w", "trend_structure",
    ]}
