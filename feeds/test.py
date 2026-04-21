"""
Feed integration test.

Run: python -m feeds.test

Checks all three feeds are returning live data:
  1. Finnhub WebSocket  — streams prices for 9 symbols (waits 15s for ticks)
  2. Robinhood REST     — expiry dates, options chain, Greeks for AAPL
  3. UW REST            — flow alerts, dark pool, and market tide for AAPL

Prints a clear PASS/FAIL for each check.

Note on Robinhood:
  First run will prompt for MFA (email/SMS code from Robinhood).
  After that the session token is saved to ~/.tokens/robinhood.pickle
  and you won't be asked again.
"""

import logging
import time
from collections import defaultdict
from datetime import date, datetime

from config.settings import WATCHLIST
from feeds.finnhub_feed import FinnhubFeed
from feeds.robinhood_feed import get_entry_price, get_expiry_dates, get_options_chain
from feeds.uw_feed import get_darkpool, get_flow_alerts, get_market_tide

logging.basicConfig(level=logging.WARNING)  # suppress debug noise during test

WAIT_SECONDS = 15


# ------------------------------------------------------------------ #
# Test 1 — Finnhub WebSocket
# ------------------------------------------------------------------ #

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
        print(f"  WARN: No ticks for: {missing}")
    if received:
        print(f"  PASS — {len(received)}/{len(WATCHLIST)} symbols ticked")
    else:
        print("  FAIL — no ticks received (check FINNHUB_API_KEY)")
    return bool(received)


# ------------------------------------------------------------------ #
# Test 2 — Robinhood options chain
# ------------------------------------------------------------------ #

def test_robinhood():
    print("\n── Robinhood Options Chain ────────────────────────")
    print("  (First run: you may be prompted for your Robinhood MFA code)")
    ticker = "AAPL"

    # Step 1 — expiry dates
    expiries = get_expiry_dates(ticker)
    if not expiries:
        print(f"  FAIL — could not fetch expiry dates for {ticker}")
        print("         Check RH_USERNAME and RH_PASSWORD in .env")
        return False

    print(f"  Expiry dates: {expiries[:5]} ...")

    # Step 2 — pick first expiry with DTE >= 14
    today = date.today()
    target = None
    for exp in expiries:
        try:
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
            if dte >= 14:
                target = exp
                break
        except ValueError:
            continue

    if not target:
        print("  FAIL — no expiry with DTE >= 14 found")
        return False

    # Step 3 — options chain
    chain = get_options_chain(ticker, target)
    calls = [o for o in chain if o["type"] == "call"]
    puts  = [o for o in chain if o["type"] == "put"]
    print(f"  {ticker} {target}: {len(calls)} calls, {len(puts)} puts")

    if not chain:
        print("  FAIL — empty chain (market may be closed — Greeks are None outside hours)")
        return False

    # Step 4 — show a sample contract with Greeks
    sample = None
    for c in calls:
        if c.get("delta") is not None:
            sample = c
            break
    if sample is None and calls:
        sample = calls[len(calls) // 2]  # ATM-ish fallback

    if sample:
        print(
            f"  Sample call: strike=${sample['strike']}  "
            f"ask=${sample['ask']}  delta={sample['delta']}  "
            f"iv={sample['iv']}  OI={sample['open_interest']}"
        )

    print(f"  PASS — chain returned {len(chain)} contracts")
    return True


# ------------------------------------------------------------------ #
# Test 3 — Unusual Whales
# ------------------------------------------------------------------ #

def test_uw():
    print("\n── Unusual Whales REST ────────────────────────────")
    ticker = "AAPL"

    flow = get_flow_alerts(ticker, limit=5)
    if flow:
        f = flow[0]
        print(f"  Flow   [{f['time_str']}] ${f['premium']:,}  {f['option_type']} "
              f"{f['trade_type']} {f['side']}  → {f['direction']}")
        print(f"  PASS — {len(flow)} flow alert(s) returned")
    else:
        print(f"  WARN — no flow alerts (market may be closed, or check UW_API_KEY)")

    dp = get_darkpool(ticker, hours=2)
    if dp:
        d = dp[0]
        print(f"  Dark pool  {d['shares']:,} shares @ ${d['price']}  {d['direction']}")
        print(f"  PASS — {len(dp)} dark pool print(s) returned")
    else:
        print(f"  WARN — no dark pool prints")

    tide = get_market_tide()
    print(f"  Market tide: {tide['score']}/100 ({tide['direction']})")
    if tide["score"] != 50 or tide["direction"] != "neutral":
        print("  PASS — market tide returned a real value")
    else:
        print("  WARN — default value returned (check UW_API_KEY)")

    return bool(flow or dp)


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    print("=" * 52)
    print("  Feed integration test")
    print("=" * 52)

    r1 = test_finnhub()
    r2 = test_robinhood()
    r3 = test_uw()

    print("\n── Summary ────────────────────────────────────────")
    print(f"  Finnhub   : {'PASS' if r1 else 'FAIL'}")
    print(f"  Robinhood : {'PASS' if r2 else 'FAIL'}")
    print(f"  UW        : {'PASS' if r3 else 'FAIL/WARN'}")

    if r1 and r2:
        print("\n  Core feeds operational — bot can run.")
        if not r3:
            print("  Add UW_API_KEY when ready for real flow data.")
    else:
        print("\n  Fix failing feeds before running the bot.")
