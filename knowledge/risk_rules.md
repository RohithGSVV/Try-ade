# Risk Rules — Trading Bot Hard Rules

> These are NON-NEGOTIABLE rules. The LLM must apply every rule on this list
> before issuing any trade recommendation. If ANY hard block condition is met,
> the output must be: "alert": false, regardless of signal strength.

---

## Hard Blocks — Automatic Disqualifiers

If any of the following conditions are true, do NOT recommend a trade. Set `"alert": false`.

### 1. Earnings within 5 days
- Check the earnings date for the ticker
- If earnings are 0–5 calendar days away: **BLOCK**
- Exception: only override if total flow premium exceeds $3M AND stacking is confirmed
- Reason: IV crush after earnings destroys option value even when direction is correct

### 2. VIX above 30
- Check current VIX level (`^VIX`) before every analysis
- If VIX > 30: **BLOCK all new trades**
- Reason: high VIX = expensive options, unpredictable swings, stops trigger too easily
- Resume when VIX drops below 25

### 3. First 30 minutes of session (9:30–10:00am ET)
- Do not enter any new trade during the opening 30 minutes
- Opening flow is dominated by market-on-open orders, gap fills, and overnight positioning adjustments
- Flow signals in this window have much lower predictive value
- **BLOCK** from 9:30am to 10:00am ET

### 4. Last 30 minutes of session (3:30–4:00pm ET)
- Do not enter any new trade in the final 30 minutes
- Flow in this window is dominated by market-on-close orders, hedging, and delta hedging by dealers
- **BLOCK** from 3:30pm to 4:00pm ET

### 5. Expiry less than 14 days away
- Never recommend an option with fewer than 14 days to expiry
- Theta decay is too aggressive — even correct directional bets lose money from time alone
- **BLOCK** any contract with DTE < 14

### 6. Maximum 3 open positions
- If there are already 3 open paper trades, do not enter a new one
- **BLOCK** until a position closes

### 7. Correlation group already occupied
- Check open positions before recommending
- If a symbol from the same correlation group already has an open trade: **BLOCK**
- Groups: [SPY, QQQ] / [AAPL, MSFT, GOOGL, AMZN] / [NVDA] / [TSLA, META]

### 8. IV rank above 70
- If the IV rank on the suggested contract is above 70: **BLOCK**
- Reason: overpaying for premium that has limited upside from here and high downside on IV mean reversion
- Exception: if IV rank is elevated due to an ongoing news event (not upcoming earnings), may proceed only if confidence would be ≥ 0.80 after applying all other modifiers from playbook.md

### 9. Flow on bid side only
- If the trigger flow was executed on the bid (not the ask): **BLOCK**
- Bid-side flow = seller closing position, not a buyer opening
- This is not a directional signal

---

## Confidence Requirements

The minimum confidence score to set `"alert": true` is **0.72**.

All confidence modifiers are defined in `knowledge/playbook.md` (Step 4 — Score and Decide). That is the canonical table — do not maintain a separate modifier list here.

---

## Position Sizing Rules (Paper Trading)

All paper trades use a standardized base size to enable fair comparison of results.

- **Base notional per trade:** $2,000 (paper money)
- **High confidence (≥ 0.82):** $3,000
- **Standard (0.72–0.81):** $2,000
- Number of contracts = floor(notional / (option_price × 100))

This is tracked in paper_trades.csv. Do not change sizes mid-series.

---

## Trade Management Rules

### Stop Loss
- Auto-close paper trade if option loses **50%** of entry value
- This is non-negotiable — options can go to zero, protect the paper account

### Take Profit
- Auto-close paper trade if option gains **100%** (doubles)
- Lock in the win — do not get greedy, the bot is not built for swing trading

### Expiry
- Auto-close any position when DTE reaches 5, regardless of P&L
- Reason: last 5 days are pure theta decay — even winning positions deteriorate fast

### Re-entry
- After a stop loss on a ticker, do not re-enter the same ticker for 24 hours
- Reason: the trade thesis was wrong — let the situation settle before re-analyzing

---

## Do Not Trade Conditions (Soft Blocks)

These don't auto-block but require confidence threshold to be raised to 0.80:

- **Major macro event tomorrow** (FOMC, CPI, NFP) — IV elevated, direction unpredictable
- **Same ticker lost money in last 3 trades** — possible model blind spot on that name
- **Flow premium below $200k** — only meaningful on slow names (MSFT, GOOGL); on TSLA/NVDA this is noise
- **Gap up or down > 3% on open** — price already moved, catching a runner is low-quality entry

---

## What Good Looks Like vs What Bad Looks Like

### ✅ High Quality Setup
- AAPL, 11:15am, call sweep $800k on ask, 35 DTE
- Dark pool print 300k shares 20 min earlier
- Market tide bullish (71/100)
- IV rank 28%
- No earnings for 6 weeks
- Price action: up 0.8% on above-average volume

→ This scores 8+ on the flow scoring model. Confidence will be 0.80+. Alert should fire.

### ❌ Low Quality Setup (common false signals to avoid)

**False signal 1 — SPY put sweep during bull session**
- SPY put sweep $2M — looks huge
- But market tide is bullish (68/100)
- This is almost certainly a hedge by a long equity fund
- Correct response: ignore, do not alert

**False signal 2 — TSLA single sweep, no confirmation**
- TSLA call sweep $400k on ask
- No dark pool, no stacking
- IV rank 74%
- Correct response: below threshold, do not alert

**False signal 3 — Bid-side flow**
- NVDA put sweep $1.2M on the bid
- Sounds huge — but bid-side = seller, not buyer
- This is someone closing their existing put position (possibly a bullish signal actually)
- Correct response: ignore

**False signal 4 — Stale flow**
- MSFT call sweep came in at 10:45am
- It is now 12:30pm and MSFT is already up 2.1%
- The move is priced in — entering now is chasing
- Correct response: do not alert on flow older than 30 minutes if price has already moved significantly

---

## Logging Requirements

Every LLM analysis cycle must log to SQLite:

```json
{
  "timestamp": "2025-04-18T10:42:00",
  "ticker": "AAPL",
  "flow_events_seen": 3,
  "flow_score": 8,
  "hard_blocks_checked": ["earnings", "vix", "session_time", "expiry", "positions"],
  "hard_block_triggered": false,
  "confidence": 0.81,
  "alert_fired": true,
  "reasoning_summary": "..."
}
```

This log is used to audit the bot, tune thresholds, and build the feedback loop.
