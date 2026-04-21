"""
Real-time stock price feed via Finnhub WebSocket.

Connects once, subscribes to all WATCHLIST symbols, and calls on_price(event)
for every trade tick received. Reconnects automatically on disconnect.

Event shape passed to on_price:
    {"ticker": "AAPL", "price": 218.40, "volume": 120, "ts": 1713430800.0}

Usage:
    feed = FinnhubFeed(on_price=my_callback)
    feed.start()          # non-blocking, runs in background thread
    feed.stop()
"""

import json
import logging
import threading
import time

import websocket

from config.settings import FINNHUB_API_KEY, WATCHLIST

log = logging.getLogger(__name__)

WS_URL = f"wss://ws.finnhub.io?token={FINNHUB_API_KEY}"
RECONNECT_DELAY = 5  # seconds between reconnect attempts


class FinnhubFeed:
    def __init__(self, on_price):
        self._on_price = on_price
        self._ws = None
        self._thread = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._ws:
            self._ws.close()

    # ------------------------------------------------------------------ #

    def _run_forever(self):
        while self._running:
            try:
                self._connect()
            except Exception as exc:
                log.warning("Finnhub WS error: %s — reconnecting in %ds", exc, RECONNECT_DELAY)
            if self._running:
                time.sleep(RECONNECT_DELAY)

    def _connect(self):
        self._ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws.run_forever()

    def _on_open(self, ws):
        log.info("Finnhub WS connected — subscribing to %d symbols", len(WATCHLIST))
        for ticker in WATCHLIST:
            ws.send(json.dumps({"type": "subscribe", "symbol": ticker}))

    def _on_message(self, ws, raw):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        if msg.get("type") != "trade":
            return

        for tick in msg.get("data", []):
            event = {
                "ticker":  tick.get("s"),
                "price":   tick.get("p"),
                "volume":  tick.get("v"),
                "ts":      tick.get("t", 0) / 1000,  # ms → seconds
            }
            if event["ticker"] and event["price"]:
                try:
                    self._on_price(event)
                except Exception:
                    log.exception("on_price callback raised")

    def _on_error(self, ws, error):
        log.warning("Finnhub WS error: %s", error)

    def _on_close(self, ws, code, msg):
        log.info("Finnhub WS closed (code=%s)", code)
