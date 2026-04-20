# Flow Interpretation — Trading Bot Knowledge

> This document teaches the bot how to read and weigh options flow data
> from Unusual Whales. Correct flow interpretation is the primary edge.

---

## What Is Options Flow?

Options flow is the real-time feed of every options trade executed in the market. Most retail traders buy small quantities of 1–10 contracts. Institutional traders — hedge funds, prop desks, banks — execute in sizes of hundreds to thousands of contracts, often using sweeps to fill quickly across multiple exchanges.

Unusual Whales surfaces the trades that are statistically unusual in size, speed, or premium. These are the trades worth paying attention to.

---

## Types of Flow Events

### Sweep
A sweep is an aggressive market order that hits multiple exchanges simultaneously to fill quickly. The trader is not trying to hide — they want to get filled NOW. This signals urgency and conviction.

- **Call sweep on the ask** → buyer is paying the ask to get filled fast → **BULLISH**
- **Put sweep on the bid** → buyer is paying the ask on puts → **BEARISH**
- **Sweep on the bid (calls)** → seller, not buyer → closing or hedging → **IGNORE**

Sweeps are the highest-conviction flow signal. Prioritize them.

### Block Trade
A single large trade filled at once, often on one exchange, sometimes negotiated off-market. Less urgent than a sweep but still meaningful at large sizes.

- Block on ask = buying aggression → same directional interpretation as sweep
- Block size matters: $100k+ = notable, $500k+ = strong, $1M+ = very strong

### Split
A large order broken into smaller pieces and executed over time across exchanges. Used to hide size. Less immediately actionable than a sweep but watching for accumulation is useful.

### Dark Pool Print
A trade executed off-exchange (dark pool) — typically institutional. Dark pool prints represent large share accumulation or distribution, often before a directional move.

- **Dark pool buy print + call sweep** = institutional accumulation confirmed by directional options bet → **Strongest possible bullish signal**
- **Dark pool sell print + put sweep** = institutional distribution + directional hedge → **Strongest possible bearish signal**
- Dark pool alone without flow confirmation = inconclusive, do not act

---

## Interpreting Flow: The Decision Tree

When a flow alert comes in, evaluate in this order:

### Step 1: Was it a buy or a sell?
- **On the ask** → buyer initiating → directional bet
- **On the bid** → seller initiating → likely closing a position, not opening
- **Mid-price** → negotiated, inconclusive
- **Rule:** Only act on ask-side flow (buyers paying up)

### Step 2: What is the size?
| Premium | Signal Weight |
|---|---|
| $50k – $100k | Low — notable but not unusual for Mag7 |
| $100k – $500k | Medium — pay attention |
| $500k – $1M | High — strong conviction |
| $1M+ | Very High — institutional scale |

Set `MIN_FLOW_PREMIUM = 100_000` — ignore anything below $100k.

### Step 3: Is this a sweep or block?
- Sweep = highest urgency → weight × 1.5 vs block
- Block = strong but less urgent → standard weight
- Split = accumulation over time → weight lower, watch for continuation

### Step 4: Is the flow stacking?
- Same ticker, same direction, 2+ sweeps within 60 minutes = **conviction stacking**
- Weight stacked flow 2× a single sweep
- Stacking across multiple expiries = even stronger (institutional layering)

### Step 5: Does dark pool confirm?
- Dark pool print same direction within 30–60 min of sweep = **institutional confirmation**
- This is the strongest setup in the entire system
- Weight: dark pool + sweep = maximum confidence input to LLM

### Step 6: What is the expiry?
- **0–7 DTE (weekly):** Speculative / lottery ticket. Very high risk. Do not act.
- **8–21 DTE:** Short-term directional. Valid if flow is very strong ($500k+).
- **21–60 DTE:** Standard directional bet. Best risk/reward for this bot.
- **60+ DTE:** Longer-term positioning. May not play out quickly enough to track.
- **Rule:** Only flag options with 14–60 DTE as actionable.

### Step 7: What is the strike relative to current price?
- **Deep OTM (>10% from price):** Lottery ticket or hedge. Lower weight.
- **OTM (2–10% from price):** Standard directional bet. Full weight.
- **ATM / slightly OTM (<2%):** High conviction, expects move soon. Full weight.
- **ITM:** Could be a stock replacement, not a directional bet. Lower weight.

---

## Specific Patterns and What They Mean

### The "Conviction Stack"
> Same ticker, 2+ sweeps on the ask, same direction, within 60 minutes, $500k+ total

This is the highest-probability setup. One sweep could be a hedge or noise. Two or more sweeps in the same direction on the same name in an hour is institutional accumulation in real time. Always flag this for LLM analysis.

### The "Dark Pool Confirm"
> Dark pool print on ticker → within 30 min, a call/put sweep in the same direction

The dark pool print shows shares being accumulated or distributed. The options sweep shows someone buying directional leverage on top. When both happen together, a fund is making a coordinated move — shares + options.

### The "SPY/QQQ Hedge"
> Large put flow on SPY or QQQ during a bullish market tide day

Do NOT interpret this as a bearish directional signal. Portfolio managers are required to hedge long equity exposure. Large put buys on indexes during bull sessions are almost always protective hedges. The correct interpretation is "smart money is protecting gains" not "smart money is going short."

Exception: If market tide has already turned bearish AND there is massive put flow on SPY/QQQ ($5M+), that may be a directional bet, not a hedge.

### The "Pre-Earnings Load"
> Unusual call or put flow on a stock 5–15 days before earnings

This is someone betting on the earnings direction. Do NOT follow this. You cannot know if they have information (illegal) or are just speculating. More importantly, IV crush after earnings will destroy option value even if direction is right. Hard rule: no trades within 5 days of earnings.

### The "Close Out" (False Signal)
> Large sweep on the bid for calls, or on the ask for puts

This is someone SELLING their existing position to close, not opening a new one. It looks like big volume but it's the opposite of a directional signal. The bid/ask side is the critical filter — always check it.

---

## Flow + Price Action Confirmation

Flow alone is not enough. Always check:

1. **Is price trending in the direction of the flow?**
   - Bullish flow + uptrending price = confirmation
   - Bullish flow + downtrending price = contrarian bet, lower confidence

2. **Is volume elevated today?**
   - Flow on high-volume day = real institutional interest
   - Flow on low-volume day = could be a single large trader, less meaningful

3. **Did price react after the flow?**
   - If a sweep came in 30 min ago and price is already up 2%, the move may be priced in
   - Prefer entering when flow is fresh (under 20 min) and price has not yet moved

---

## Flow Signal Scoring Summary

Use this to build the confidence input for the LLM:

| Signal | Score Contribution |
|---|---|
| Single sweep on ask, $100k–$500k | +1 |
| Single sweep on ask, $500k–$1M | +2 |
| Single sweep on ask, $1M+ | +3 |
| Stacking (2+ sweeps same direction, 60 min) | +2 additional |
| Dark pool print confirms direction | +3 additional |
| Price action confirms direction | +1 additional |
| Block trade (not sweep) | +1 (half weight of sweep) |
| Market tide aligned | +1 additional |
| Sweep is OTM with 14–45 DTE | +1 (clean directional bet) |
| IV rank < 50 | +1 (not overpaying for premium) |
| Earnings within 5 days | BLOCK — do not trade |
| VIX > 30 | BLOCK — do not trade |
| Flow on bid side (closing) | 0 — ignore |

Score ≥ 6 → flag for LLM analysis with high priority
Score 4–5 → flag for LLM analysis with medium priority
Score < 4 → filter out, do not send to LLM

---

## Unusual Whales Specific Endpoints

### `/api/option-trades/flow-alerts`
Primary flow feed. Contains: ticker, strike, expiry, call/put, premium, side (ask/bid/mid), sweep/block flag, timestamp.

### `/api/darkpool/recent` and `/api/darkpool/{ticker}`
Dark pool prints by ticker. Contains: shares, price, timestamp. Match against options flow within ±30 min window.

### `/api/market/market-tide`
Overall market sentiment score. Use as a multiplier:
- Bullish tide: only flag bullish flow (calls) at full weight; bearish flow at half weight
- Bearish tide: only flag bearish flow (puts) at full weight; bullish flow at half weight
- Neutral tide: treat all flow equally

### `/api/market/oi-change`
Open interest changes. Rising OI + same-direction flow = new positions being opened (bullish for signal). Falling OI + flow = positions closing (bearish for signal).

### `/api/insider/{ticker}/ticker-flow`
Insider buying is a medium-weight supplementary signal. Insider selling is noisy (could be any personal reason). Only use insider buy as a confirming signal, never as a primary one.

### `/api/congress/recent-trades`
Congressional trades are public disclosures, often 30–45 days delayed. Useful as a background signal for longer-dated options positioning, not for intraday decisions.
