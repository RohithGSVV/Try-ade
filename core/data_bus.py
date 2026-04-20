"""
Data bus — thread-safe real-time price store.

Finnhub WebSocket ticks are written here as they arrive.
context_builder.py reads the latest price to override yfinance's
15-minute delayed current price during market hours.

Usage:
    # In Finnhub callback:
    data_bus.on_price({"ticker": "AAPL", "price": 218.40, "ts": ...})

    # In context_builder:
    price = data_bus.get_price("AAPL")   # None if no tick received yet
"""

import threading
import time

_lock  = threading.Lock()
_store: dict[str, dict] = {}   # ticker → {price, ts}

MAX_TICK_AGE_SECONDS = 600     # treat tick as stale if older than 10 min


def on_price(event: dict) -> None:
    """Called by FinnhubFeed on every trade tick."""
    ticker = event.get("ticker")
    price  = event.get("price")
    if ticker and price:
        with _lock:
            _store[ticker] = {"price": float(price), "ts": event.get("ts", time.time())}


def get_price(ticker: str) -> float | None:
    """
    Return the latest real-time price for ticker, or None if:
    - no tick received yet, or
    - the last tick is older than MAX_TICK_AGE_SECONDS (market closed / feed down)
    """
    with _lock:
        entry = _store.get(ticker)
    if not entry:
        return None
    age = time.time() - entry.get("ts", 0)
    if age > MAX_TICK_AGE_SECONDS:
        return None
    return entry["price"]


def get_all() -> dict[str, float]:
    """Return snapshot of all latest prices {ticker: price}."""
    with _lock:
        return {t: e["price"] for t, e in _store.items()}


def tick_count() -> int:
    """Number of symbols with at least one tick received."""
    with _lock:
        return len(_store)
