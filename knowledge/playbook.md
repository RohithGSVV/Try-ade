# LLM Trading Playbook

> Read this before every analysis cycle. This is your decision framework.
> You do NOT trade flow. You trade a thesis, and use flow to verify institutional intent.

---

## Core Principle: Thesis First, Flow Second

Flow is not the signal. Flow is the verification.

Your job is to build a technical thesis from price structure, moving averages, market tide,
and Greeks — and then ask: "Does institutional flow confirm what I'm already seeing?"

If the answer is yes → confidence rises → potentially alert.
If flow is absent → requires stronger technicals to compensate.
If flow contradicts → almost always skip.

**The question is never "what is flow doing?"**
**The question is always "does flow agree with my thesis?"**

---

## The 4-Step Decision Framework

### Step 1 — Build Bias from Structure
Before looking at any flow, form a directional bias from:

- **Price vs key moving averages:** Is price above or below the 21 EMA and 50 SMA?
- **Trend structure:** Higher highs and higher lows (bullish) or lower highs and lower lows (bearish)?
- **Key levels:** Is price near support (good entry), near resistance (bad entry), or just broke out (great entry)?
- **Market Tide:** What is the UW Market Tide score? Bullish tide = bias toward calls. Bearish = bias toward puts.
- **SPY/QQQ context:** Even on individual names, check SPY and QQQ direction. Don't fight the broad market.
- **VWAP:** Price above VWAP = intraday momentum bullish. Below VWAP = bearish intraday.

If you cannot form a clear directional bias from structure alone, **stop here. No trade.**

---

### Step 2 — Check Options Viability
Before looking at flow, verify the options themselves are tradeable:

| Check | Requirement | If failed |
|---|---|---|
| IV Rank | < 70 for long premium | Skip — overpaying |
| Expiry | ≥ 14 DTE | Skip — theta decay |
| Open Interest | > 1,000 on the contract | Skip — illiquid |
| Bid/Ask spread | < $0.25 | Skip — slippage too high |
| Earnings buffer | > 5 days | Hard block |
| VIX level | < 30 | Hard block |
| Session time | 10:00am–3:30pm ET | Hard block outside window |

If any hard block condition is met, output `"alert": false` regardless of everything else.

---

### Step 3 — Verify with Flow
Now check UW flow from the last 60 minutes on this ticker.

**Flow confirms your thesis when:**
- Direction matches (calls for bull thesis, puts for bear thesis)
- Premium ≥ $100k per print, OR 3+ prints ≥ $50k within 10 minutes
- Executed at the ask or above mid — aggressive buyer, not a seller
- No matching opposite-side print within 30 seconds (would indicate a spread, not directional)
- Price held or continued in thesis direction after the flow (flow was not faded)

**Flow is neutral (no relevant flow) when:**
- No unusual activity in the last 60 minutes on this ticker
- Flow exists but is too small (< $50k), too old (> 60 min), or at mid/bid
- In this case: flow contributes 0.00 to confidence. Require stronger technicals (0.85+ base).

**Flow contradicts your thesis when:**
- Large flow in the opposite direction in the last 30 minutes
- Calls being sold (opening short premium) while you want to buy calls
- Flow hit but price faded within 5 minutes — institutional buyer already wrong or hedging
- In this case: apply -0.25 confidence penalty. Usually skip.

---

### Step 4 — Score and Decide

Base your confidence from the technical thesis, then adjust with flow:

| Condition | Confidence adjustment |
|---|---|
| Confirming flow (meets all criteria above) | +0.15 |
| No relevant flow | 0.00 |
| Contradicting flow | -0.25 |
| Dark pool print confirms direction | +0.08 |
| Flow stacking (2+ sweeps, same direction, 60 min) | +0.06 |
| Price just broke above resistance (breakout) | +0.05 |
| Price bouncing off confirmed support | +0.03 |
| Price above 21 EMA and 50 SMA | +0.02 each |
| Price above VWAP | +0.02 |
| Market tide strongly aligned (>65 or <35) | +0.04 |
| IVR < 30 (cheap premium) | +0.02 |
| IVR 50–70 | -0.03 |
| VIX 20–28 | -0.02 |
| VIX > 28 | -0.10 |
| IVR > 75 | -0.15 |
| Earnings < 7 days | -0.30 |
| Bid/ask spread > $0.30 or OI < 500 | -0.20 |
| TSLA ticker (high noise baseline) | -0.04 |
| Price below 50 SMA with bullish thesis | -0.05 |
| Price within 0.5% of major resistance | -0.06 |

---

## Confidence Thresholds

| Score | Action |
|---|---|
| 0.85 – 1.00 | Strong thesis + confirming flow + clean Greeks → Alert + paper trade |
| 0.72 – 0.84 | Good thesis + confirming flow OR excellent thesis alone → Alert + paper trade |
| 0.60 – 0.71 | Thesis OK but flow missing or mixed → **DO NOT TRADE** — log as watched |
| < 0.60 | Skip entirely — do not log |

**Note:** If there is no flow at all, the minimum threshold to trade rises to 0.85. You need
exceptional technical structure to trade without institutional confirmation.

---

## Good Trade Examples

### Example 1: AAPL Bull Call — Thesis Confirmed by Flow

**Structure:**
AAPL closed above 21 EMA 3 days in a row. Pulled back to $218 support today, which was also
prior resistance (now flipped support). SPY Market Tide bullish at 71. VIX 18. IVR 42.

**Technical thesis (formed before looking at flow):**
Uptrend intact. Healthy pullback to a key level. Low IV means cheap premium. This is a clean
risk/reward — stop below $218 support, target the prior high.

**Flow check:**
11:14am — $1.2M sweep, May 16 $220C, at the ask.
11:18am — $400k sweep, May 16 $220C, at the ask.
11:22am — $380k sweep, May 16 $220C, at the ask.

Flow is stacking on the same strike in the same direction. No opposite-side prints. Price is
holding $218 after the flow. Full confirmation.

**LLM reasoning:**
"Uptrend intact, healthy pullback to support, low IV favors long premium, three stacked sweeps
show institutional accumulation not chasing. Dark pool would be ideal but not required here —
the stacking alone is strong confirmation."

```json
{
  "ticker": "AAPL",
  "direction": "bullish",
  "trade_type": "call",
  "strike": 220,
  "expiry": "2025-05-16",
  "confidence": 0.84,
  "thesis_summary": "Trend support bounce with low IV and stacked confirming call sweeps",
  "flow_verification": "confirming",
  "alert": true
}
```

---

### Example 2: QQQ Bear Put — Market Tide Triggers Thesis

**Structure:**
QQQ rejected the 50 SMA twice in the past 4 days. SPY is trading below VWAP. Market Tide
flipped bearish from +0.4 to -1.8 in the last 2 hours. VIX rising from 19 to 23 today.
Price is making lower highs.

**Technical thesis:**
Double top rejection at 50 SMA. Market tide has turned. Intraday momentum negative. This is
a bearish structure. Looking for put entry if price breaks below today's low.

**Flow check:**
1:42pm — $850k in QQQ May 2 $440P, mix of sweeps at mid to ask.

Flow is directionally aligned. Not a clean ask-only sweep, but $850k in puts during a bearish
tide flip is meaningful. Proceed with slightly reduced confidence vs a clean ask sweep.

```json
{
  "ticker": "QQQ",
  "direction": "bearish",
  "trade_type": "put",
  "strike": 440,
  "expiry": "2025-05-02",
  "confidence": 0.78,
  "thesis_summary": "Double top rejection at 50 SMA with market tide flip and put sweep confirmation",
  "flow_verification": "confirming",
  "alert": true
}
```

---

### Example 3: NVDA — Flow Ignored, No Trade

**Structure:**
NVDA chopping between $860 and $880 for 3 days. No clear trend. IVR at 78 (options expensive).
Earnings in 3 days. Below 21 EMA.

**Flow check:**
10:05am — $2.1M in calls.

Massive flow. But the thesis check fails at Step 1 (no trend) and Step 2 (IVR 78, earnings 3 days).
The hard block on earnings within 5 days triggers automatically.

**LLM reasoning:**
"Flow is large but the earnings buffer hard block applies. Even if direction is correct, IV crush
post-earnings will destroy option value. IVR is also at 78 — buying expensive premium into a
known binary event is not this system's edge."

```json
{
  "ticker": "NVDA",
  "direction": "bullish",
  "trade_type": "call",
  "strike": 900,
  "expiry": "2025-05-16",
  "confidence": 0.48,
  "thesis_summary": "Hard block: earnings in 3 days. IVR 78. No trade regardless of flow size.",
  "flow_verification": "ignored_due_to_hard_block",
  "alert": false
}
```

---

## Bad Trade Examples — Learn From These

### Bad Example 1: TSLA Chase — Flow Without Thesis

**What happened:**
TSLA in a clear downtrend below 50 SMA. Bounced 2% from random level (not support).
No technical thesis formed. Flow came in: $600k calls at 11:03am.
LLM traded the flow. Confidence was 0.71. Stopped out -50% by next day.

**The mistake:**
Flow was the trigger, not the verification. Price structure was bearish. The call buyers
could have been hedgers, gamblers, or wrong. Without a valid technical thesis, there was
nothing to verify.

**The lesson:**
If you can't write a thesis that would be valid even without flow, do not trade.
"Large call flow" is not a thesis. "Uptrend with pullback to support in low-IV environment" is.

---

### Bad Example 2: MSFT Spread Trap

**What happened:**
$1.5M in MSFT May $420 calls bought.
$1.4M in MSFT May $430 calls sold — 28 seconds later.

**The mistake:**
This is a call spread (debit spread) — a hedged, defined-risk institutional position.
It is not a directional bet on MSFT going up. The net premium at risk is tiny.
Adding confidence for the $1.5M call buy without seeing the $1.4M sell is a false signal.

**The rule:**
Always check for paired prints within 30 seconds on the same expiry.
If a matching opposite leg exists → classify as "complex/spread" → do NOT add to confidence.

---

### Bad Example 3: SPY Opening Noise

**What happened:**
9:42am. SPY gapped up on positive macro news. $3M in call sweeps immediately on open.
LLM flagged it as bullish.

**The mistake:**
The hard session rule blocks all trades before 10:00am ET. Opening flow is dominated by:
- Overnight gap fills
- Market-on-open orders
- Institutional hedge unwinds from previous close
- Dealers adjusting delta exposure

None of this is directional signal. It is mechanical positioning.

**The rule:**
Hard block 9:30–10:00am overrides all flow, no matter how large. Do not analyze.
Do not add to confidence. Ignore entirely.

---

### Bad Example 4: Contradicting Flow, Thesis Still Held

**What happened:**
AAPL technical thesis looked bullish — above 21 EMA, near support.
Then: $900k in AAPL put sweeps on the ask came in at 11:30am.
LLM proceeded anyway, confidence 0.73.

**The mistake:**
Contradicting flow is a -0.25 penalty. A 0.73 base confidence becomes 0.48 — well below threshold.
The institutional buyer of puts knew something (or was hedging something) the technical picture didn't show.
The trade stopped out -60% intraday.

**The lesson:**
When institutions are aggressively buying protection against your thesis direction,
respect it. Either wait for the contradiction to resolve or skip entirely.

---

## Quick Reference: Output Schema

Every analysis must output this exact JSON structure:

```json
{
  "ticker": "AAPL",
  "direction": "bullish | bearish",
  "trade_type": "call | put",
  "strike": 220,
  "expiry": "YYYY-MM-DD",
  "dte": 28,
  "entry_price_estimate": 3.20,
  "confidence": 0.82,
  "thesis_summary": "One sentence. Trend + key level + flow confirmation.",
  "technical_basis": "Price above 21EMA and 50SMA. Bounced off $218 support. Breaking resistance.",
  "flow_verification": "confirming | neutral | contradicting | ignored_due_to_hard_block",
  "flow_summary": "3x call sweeps at ask, $1.2M + $400k + $380k, May 16 $220C, 11:14-11:22am",
  "key_signals": ["call sweep stack", "low IVR", "support bounce", "bullish market tide"],
  "risk_factors": ["approaching resistance at $222", "VIX ticking up"],
  "hard_blocks_checked": ["earnings", "vix", "session_time", "dte", "positions", "correlation"],
  "hard_block_triggered": false,
  "alert": true
}
```

If `hard_block_triggered` is true, `alert` must be false. No exceptions.
