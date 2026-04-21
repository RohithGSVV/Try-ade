"""
Robinhood options chain feed (replaces Tradier).

Uses the unofficial robin_stocks library to pull live options data
from your existing Robinhood account — no extra signup or API key needed.

Requires:
  pip install robin_stocks
  RH_USERNAME and RH_PASSWORD in .env

First run: Robinhood will send an MFA code to your email/SMS. Enter it
interactively. After that, the session token is stored in
~/.tokens/robinhood.pickle and re-used automatically — no MFA again.

Public functions (identical interface to the Tradier feed it replaces):
  get_expiry_dates(ticker)                          → list[str]
  get_options_chain(ticker, expiry)                 → list[dict]
  get_entry_price(ticker, strike, expiry, opt_type) → float | None

Option dict shape (matches what context_builder.py expects):
    {
        "symbol":        "AAPL250516C00220000",
        "type":          "call" | "put",
        "strike":        220.0,
        "expiry":        "2025-05-16",
        "dte":           28,
        "bid":           3.10,
        "ask":           3.30,
        "mid":           3.20,
        "delta":         0.42,
        "theta":        -0.06,
        "iv":            0.31,
        "ivr":           None,   # computed by context_builder
        "open_interest": 14200,
        "volume":        3810,
    }
"""

import logging
from datetime import date, datetime
from typing import Optional

from config.settings import RH_USERNAME, RH_PASSWORD

log = logging.getLogger(__name__)

# Session state — login once per process
_logged_in = False


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def get_expiry_dates(ticker: str) -> list[str]:
    """
    Return available expiry dates for ticker, sorted nearest → furthest.
    Filters to future dates only (today + 1 day onwards).
    """
    rh = _get_rh()
    if rh is None:
        return []

    try:
        chain_data = rh.options.get_chains(ticker)
        if not chain_data:
            log.warning("No chain data returned for %s", ticker)
            return []

        raw_dates = chain_data.get("expiration_dates") or []
        today = date.today()
        return sorted(
            d for d in raw_dates
            if _parse_date(d) and _parse_date(d) > today
        )
    except Exception as exc:
        log.error("Robinhood expiry dates failed for %s: %s", ticker, exc)
        return []


def get_options_chain(ticker: str, expiry: str) -> list[dict]:
    """
    Fetch full options chain (calls + puts) for ticker on a specific expiry.
    expiry format: "YYYY-MM-DD"
    Returns list of option dicts (see module docstring).
    """
    rh = _get_rh()
    if rh is None:
        return []

    try:
        # Fetch calls and puts in two requests (Robinhood API requires type filter)
        calls = rh.options.find_options_for_stock(
            ticker, expirationDate=expiry, optionType="call"
        ) or []
        puts = rh.options.find_options_for_stock(
            ticker, expirationDate=expiry, optionType="put"
        ) or []
    except Exception as exc:
        log.error("Robinhood chain fetch failed for %s %s: %s", ticker, expiry, exc)
        return []

    today = date.today()
    results = []
    for opt in calls + puts:
        try:
            results.append(_normalize(opt, today))
        except Exception as exc:
            log.debug("Skipping malformed option: %s", exc)

    return results


def get_entry_price(
    ticker: str, strike: float, expiry: str, option_type: str
) -> Optional[float]:
    """
    Return the current ask price for a specific contract.
    Used as the paper trade entry price.
    Returns None if contract cannot be found or market is closed.
    """
    chain = get_options_chain(ticker, expiry)
    for opt in chain:
        if opt["type"] == option_type and opt["strike"] == strike:
            return opt["ask"]
    log.warning(
        "Entry price not found: %s $%s %s %s", ticker, strike, option_type, expiry
    )
    return None


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #

def _get_rh():
    """
    Return the robin_stocks robinhood module after ensuring login.
    Returns None if credentials are missing or login fails.
    """
    global _logged_in

    try:
        import robin_stocks.robinhood as rh
    except ImportError:
        log.error(
            "robin_stocks not installed — run: pip install robin_stocks"
        )
        return None

    if _logged_in:
        return rh

    if not RH_USERNAME or not RH_PASSWORD:
        log.error(
            "RH_USERNAME or RH_PASSWORD not set in .env — "
            "Robinhood feed disabled"
        )
        return None

    try:
        rh.login(
            username=RH_USERNAME,
            password=RH_PASSWORD,
            store_session=True,   # saves token to disk — no MFA next time
            mfa_code=None,        # prompts interactively if needed on first run
        )
        _logged_in = True
        log.info("Robinhood login successful")
        return rh
    except Exception as exc:
        log.error("Robinhood login failed: %s", exc)
        return None


def _normalize(opt: dict, today: date) -> dict:
    """
    Convert a raw robin_stocks option dict to the standard shape.
    All values from Robinhood are strings — must be cast to float/int.
    """
    exp_str = opt.get("expiration_date", "")
    exp_date = _parse_date(exp_str)
    dte = (exp_date - today).days if exp_date else None

    bid   = _f(opt.get("bid_price"))
    ask   = _f(opt.get("ask_price"))
    mark  = _f(opt.get("adjusted_mark_price"))

    # Robinhood puts delta as positive for calls, negative for puts
    delta = _f(opt.get("delta"))
    theta = _f(opt.get("theta"))
    iv    = _f(opt.get("implied_volatility"))

    # Build OCC-style symbol (best effort — Robinhood gives chain_symbol separately)
    symbol = opt.get("chain_symbol", "") or opt.get("symbol", "")

    return {
        "symbol":        symbol,
        "type":          opt.get("type", "").lower(),   # "call" | "put"
        "strike":        _f(opt.get("strike_price")),
        "expiry":        exp_str,
        "dte":           dte,
        "bid":           bid,
        "ask":           ask,
        "mid":           round((bid + ask) / 2, 2) if bid is not None and ask is not None else mark,
        "delta":         delta,
        "theta":         theta,
        "iv":            iv,
        "ivr":           None,   # computed by context_builder using historical IV
        "open_interest": _i(opt.get("open_interest")),
        "volume":        _i(opt.get("volume")),
    }


def _f(val) -> Optional[float]:
    """Safe string → float cast."""
    try:
        return round(float(val), 4) if val is not None else None
    except (TypeError, ValueError):
        return None


def _i(val) -> Optional[int]:
    """Safe string → int cast."""
    try:
        return int(float(val)) if val is not None else None
    except (TypeError, ValueError):
        return None


def _parse_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
