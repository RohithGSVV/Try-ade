"""
Tradier options chain feed.

Provides two public functions:
  get_options_chain(ticker, expiry)  → list of option dicts with Greeks
  get_entry_price(ticker, strike, expiry, option_type)  → ask price (float)

Tradier free sandbox: https://sandbox.tradier.com/v1
Switch TRADIER_BASE_URL to https://api.tradier.com/v1 for a live brokerage account.

Option dict shape:
    {
        "symbol":      "AAPL250516C00220000",
        "type":        "call" | "put",
        "strike":      220.0,
        "expiry":      "2025-05-16",
        "dte":         28,
        "bid":         3.10,
        "ask":         3.30,
        "mid":         3.20,
        "delta":       0.42,
        "theta":       -0.06,
        "iv":          0.31,
        "ivr":         None,   # calculated separately via historical IV
        "open_interest": 14200,
        "volume":      3810,
    }
"""

import logging
from datetime import date, datetime

import requests

from config.settings import TRADIER_API_KEY, TRADIER_BASE_URL

log = logging.getLogger(__name__)

_HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_KEY}",
    "Accept": "application/json",
}


def get_options_chain(ticker: str, expiry: str) -> list[dict]:
    """
    Fetch full options chain for ticker on a specific expiry date.
    expiry format: "YYYY-MM-DD"
    Returns list of option dicts (see module docstring).
    """
    url = f"{TRADIER_BASE_URL}/markets/options/chains"
    params = {"symbol": ticker, "expiration": expiry, "greeks": "true"}

    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.error("Tradier chain fetch failed for %s %s: %s", ticker, expiry, exc)
        return []

    options = data.get("options", {}) or {}
    raw_list = options.get("option") or []
    if isinstance(raw_list, dict):
        raw_list = [raw_list]  # single result comes back as dict

    today = date.today()
    results = []
    for opt in raw_list:
        greeks = opt.get("greeks") or {}
        try:
            exp_date = datetime.strptime(opt["expiration_date"], "%Y-%m-%d").date()
            dte = (exp_date - today).days
        except (KeyError, ValueError):
            dte = None

        results.append({
            "symbol":        opt.get("symbol"),
            "type":          opt.get("option_type"),
            "strike":        opt.get("strike"),
            "expiry":        opt.get("expiration_date"),
            "dte":           dte,
            "bid":           opt.get("bid"),
            "ask":           opt.get("ask"),
            "mid":           _mid(opt.get("bid"), opt.get("ask")),
            "delta":         greeks.get("delta"),
            "theta":         greeks.get("theta"),
            "iv":            greeks.get("mid_iv"),
            "ivr":           None,  # computed by context_builder using historical IV
            "open_interest": opt.get("open_interest"),
            "volume":        opt.get("volume"),
        })

    return results


def get_entry_price(ticker: str, strike: float, expiry: str, option_type: str) -> float | None:
    """
    Return the current ask price for a specific contract — used as paper trade entry price.
    option_type: "call" or "put"
    Returns None if the contract cannot be found.
    """
    chain = get_options_chain(ticker, expiry)
    for opt in chain:
        if opt["type"] == option_type and opt["strike"] == strike:
            return opt["ask"]
    log.warning("Entry price not found: %s %s%s %s", ticker, strike, option_type[0].upper(), expiry)
    return None


def get_expiry_dates(ticker: str) -> list[str]:
    """
    Return available expiry dates for ticker (nearest to furthest).
    Useful for picking the right expiry when building the suggested contract.
    """
    url = f"{TRADIER_BASE_URL}/markets/options/expirations"
    params = {"symbol": ticker, "includeAllRoots": "true", "strikes": "false"}

    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.error("Tradier expirations fetch failed for %s: %s", ticker, exc)
        return []

    dates = data.get("expirations", {}) or {}
    raw = dates.get("date") or []
    if isinstance(raw, str):
        raw = [raw]
    return raw


# ------------------------------------------------------------------ #

def _mid(bid, ask) -> float | None:
    if bid is not None and ask is not None:
        return round((bid + ask) / 2, 2)
    return None
