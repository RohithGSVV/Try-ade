"""
Main entry point — start the bot.

  python main.py

Startup sequence:
  1. Configure logging
  2. Start Finnhub WebSocket price feed (background thread)
  3. Wait for initial price ticks (up to 30s)
  4. Run first scan cycle immediately
  5. Schedule scan every SCAN_INTERVAL_MIN minutes
  6. Loop forever, Ctrl+C to stop

Logs go to both console and bot.log.
"""

import logging
import signal
import sys
import time

import schedule

from config.settings import SCAN_INTERVAL_MIN, WATCHLIST
from core.data_bus import on_price, tick_count
from feeds.finnhub_feed import FinnhubFeed
from scan import run_scan_cycle
from signals.event_filters import is_market_hours, get_session_status

# ------------------------------------------------------------------ #
# Logging setup

def _setup_logging() -> None:
    fmt = "%(asctime)s %(levelname)-7s %(name)s — %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("bot.log", encoding="utf-8"),
        ],
    )
    # Suppress noisy third-party loggers
    for noisy in ("urllib3", "websocket", "httpx", "openai", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


log = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Scheduled job

def _scheduled_scan() -> None:
    status = get_session_status()
    if status in ("PRE_MARKET", "POST_MARKET"):
        log.info("Market closed (%s) — skipping scan", status)
        return
    run_scan_cycle()


# ------------------------------------------------------------------ #
# Main

def main() -> None:
    _setup_logging()

    log.info("=" * 56)
    log.info("  LLM Trading Bot starting")
    log.info("  Watchlist: %s", ", ".join(WATCHLIST))
    log.info("  Scan interval: every %d minutes", SCAN_INTERVAL_MIN)
    log.info("=" * 56)

    # ── Start Finnhub price feed ─────────────────────────────────────
    feed = FinnhubFeed(on_price=on_price)
    feed.start()
    log.info("Finnhub WebSocket started — waiting for price ticks...")

    # Wait up to 30s for at least half the watchlist to report ticks
    deadline = time.time() + 30
    target   = len(WATCHLIST) // 2
    while time.time() < deadline and tick_count() < target:
        time.sleep(1)

    received = tick_count()
    if received == 0:
        log.warning(
            "No Finnhub ticks received after 30s — "
            "continuing with yfinance prices (check FINNHUB_API_KEY)"
        )
    else:
        log.info("Finnhub: %d/%d symbols ticking", received, len(WATCHLIST))

    # ── Graceful shutdown ────────────────────────────────────────────
    def _shutdown(sig, frame):
        log.info("Shutdown signal received — stopping bot")
        feed.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── Run first scan immediately, then schedule ────────────────────
    log.info("Running initial scan cycle...")
    _scheduled_scan()

    schedule.every(SCAN_INTERVAL_MIN).minutes.do(_scheduled_scan)
    log.info("Scheduler running — next scan in %d min", SCAN_INTERVAL_MIN)

    while True:
        schedule.run_pending()
        time.sleep(30)   # check scheduler twice per minute


if __name__ == "__main__":
    main()
