"""
Feed integration test.

Run: python -m feeds.test

Checks all three feeds are returning live data:
  1. Finnhub WebSocket — streams prices for 9 symbols (waits 15s for ticks)
  2. Tradier REST      — fetches nearest expiry chain for AAPL
  3. UW REST           — fetches flow alerts, dark pool, and market tide for AAPL

Prints a clear PASS/FAIL for each check so you know what's working before
moving on to signal processing.
"""

import logging
import time
from collections import defaultdict

from feeds.finnhub_feed import FinnhubFeed
from feeds.tradier_feed import get_entry_price, get_expiry_dates, get_options_chain
from feeds.uw_feed import get_darkpool, get_flow_alerts, get_market_tide
from config.settings import WATCHLIST

logging.basicConfig(level=logging.WARNING)  # suppress debug noise during test

WAIT_SECONDS = 15  # how long to listen for Finnhub ticks


def test_finnhub():
    print("\n── Finnhub WebSocket ──────────────────────────────")
    received: dict[str, list] = defaultdict(list)

    def on_price(event):
        received[event["ticker"]].append(event["price"])

    feed = FinnhubFeed(on_price=on_price)
    feed.start()
    print(f"  Listening for {WAIT_SECONDS}s...")
    time.sleep(WAIT_SECONDS)
    feed.stop()

    missing = [t for t in WATCHLIST if t not in received]
    for ticker, prices in sorted(received.items()):
        print(f"  {ticker:6s}  {len(prices):3d} ticks  last=${prices[-1]:.2f}")

    if missing:
        print(f"  WARN: No ticks received for: {missing}")
    if received:
        print(f"  PASS — {len(received)}/{len(WATCHLIST)} symbols ticked")
    else:
        print("  FAIL — no ticks received (check FINNHUB_API_KEY and network)")
    return bool(received)


def test_tradier():
    print("\n── Tradier Options Chain ──────────────────────────")
    ticker = "AAPL"
    expiries = get_expiry_dates(ticker)
    if not expiries:
        print(f"  FAIL — could not fetch expiry dates for {ticker}")
        print("         (check TRADIER_API_KEY and TRADIER_BASE_URL in settings)")
        return False

    print(f"  Available expiries: {expiries[:5]} ...")
    # pick first expiry with DTE >= 14
    from datetime import date, datetime
    today = date.today()
    target_expiry = None
    for exp in expiries:
        dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
        if dte >= 14:
            target_expiry = exp
            break

    if not target_expiry:
        print(f"  FAIL — no expiry with DTE >= 14 found")
        return False

    chain = get_options_chain(ticker, target_expiry)
    calls = [o for o in chain if o["type"] == "call"]
    puts  = [o for o in chain if o["type"] == "put"]
    print(f"  {ticker} {target_expiry}: {len(calls)} calls, {len(puts)} puts")

    if calls:
        c = calls[len(calls) // 2]  # roughly ATM
        print(f"  Sample call: strike=${c['strike']}  ask=${c['ask']}  delta={c['delta']}  OI={c['open_interest']}")

    if chain:
        print(f"  PASS — options chain returned {len(chain)} contracts")
    else:
        print("  FAIL — empty chain returned")
    return bool(chain)


def test_uw():
    print("\n── Unusual Whales REST ────────────────────────────")
    ticker = "AAPL"

    # Flow alerts
    flow = get_flow_alerts(ticker, limit=5)
    if flow:
        f = flow[0]
        print(f"  Flow   [{f['time_str']}] ${f['premium']:,}  {f['option_type']} {f['trade_type']} {f['side']}  → {f['direction']}")
        print(f"  PASS — {len(flow)} flow alert(s) returned for {ticker}")
    else:
        print(f"  WARN — no flow alerts for {ticker} (market may be closed, or check UW_API_KEY)")

    # Dark pool
    dp = get_darkpool(ticker, hours=2)
    if dp:
        d = dp[0]
        print(f"  Dark pool [{d['ts']:.0f}] {d['shares']:,} shares @ ${d['price']}  {d['direction']}")
        print(f"  PASS — {len(dp)} dark pool print(s) returned")
    else:
        print(f"  WARN — no dark pool prints for {ticker}")

    # Market tide
    tide = get_market_tide()
    print(f"  Market tide: {tide['score']}/100 ({tide['direction']})")
    if tide["score"] != 50 or tide["direction"] != "neutral":
        print("  PASS — market tide returned a real value")
    else:
        print("  WARN — market tide returned default (50/neutral) — may be an API error")

    return bool(flow or dp)


if __name__ == "__main__":
    print("=" * 52)
    print("  Feed integration test")
    print("=" * 52)

    r1 = test_finnhub()
    r2 = test_tradier()
    r3 = test_uw()

    print("\n── Summary ────────────────────────────────────────")
    print(f"  Finnhub  : {'PASS' if r1 else 'FAIL'}")
    print(f"  Tradier  : {'PASS' if r2 else 'FAIL'}")
    print(f"  UW       : {'PASS' if r3 else 'FAIL'}")

    if all([r1, r2, r3]):
        print("\n  All feeds operational. Ready for Phase 2 (signal processing).")
    else:
        print("\n  Fix failing feeds before moving on.")
