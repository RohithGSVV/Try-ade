# Symbol Profiles — Trading Bot Knowledge

> Per-symbol notes the LLM must factor into every trade decision.
> Each symbol behaves differently — what works on SPY may not work on TSLA.

---

## SPY — SPDR S&P 500 ETF

**Role in this system:** Macro direction gauge. Trades here represent market-wide sentiment.

**Behavior:**
- Extremely liquid — tightest bid/ask spreads of any options market
- Massive options volume daily — filtering for unusual flow requires higher premium threshold
- Large put flow on SPY is almost always a hedge, NOT a directional short
- SPY moves are driven by macro: Fed decisions, CPI, jobs data, geopolitical events

**Flow rules:**
- Minimum premium for SPY flow to be meaningful: $500k+ (standard $100k is noise here)
- Only treat SPY put flow as bearish if: market tide is already bearish AND premium is $2M+
- Call sweeps on SPY during bearish market tide sessions are worth flagging — contrarian signal

**Options behavior:**
- IV spikes before macro events (FOMC, CPI) — avoid buying options day before these
- After macro events, IV drops sharply — if direction was right, hold through IV crush only if DTE > 14
- Weekly SPY options (0–5 DTE) see enormous volume — do NOT treat this as unusual

**Suggested expiry range:** 21–45 DTE for cleaner signals

---

## QQQ — Invesco Nasdaq-100 ETF

**Role in this system:** Tech sector direction. Correlated with NVDA, AAPL, MSFT, META, AMZN, GOOGL.

**Behavior:**
- Highly correlated to Mag7 — when QQQ is bearish, most Mag7 names will also be weak
- Use QQQ market tide to confirm or deny individual Mag7 trade ideas
- If QQQ flow is bearish, do not enter bullish plays on NVDA or AAPL — wait for alignment

**Flow rules:**
- Same hedge caveat as SPY: large put flows are often institutional hedges
- Call sweeps on QQQ are more directional than SPY calls — Nasdaq is more speculative
- Minimum meaningful premium: $300k+

**Correlation rule:**
- Do not hold both a QQQ trade AND a trade on a Mag7 stock simultaneously
- They move together — it doubles your effective exposure to one thesis

---

## AAPL — Apple Inc.

**Behavior:**
- One of the most liquid single-stock options in the world
- Moves slowly relative to other Mag7 — requires meaningful catalyst for 3%+ days
- Earnings are in Jan, Apr, Jul, Oct — enforce 5-day earnings block strictly
- Sensitive to: iPhone cycle news, China sales data, Fed rate decisions (cash-heavy company)

**Flow rules:**
- $200k+ for notable, $500k+ for actionable on AAPL
- AAPL flows are very commonly hedges by institutions long the stock — confirm with dark pool
- Call stacking (2+ sweeps) is particularly meaningful here due to normally quiet flow profile

**Options behavior:**
- IV is typically low (AAPL doesn't move much) — options are cheap most of the time
- IV rank below 30 is common — buying options is relatively cheap vs other names
- When IV spikes above 50 on AAPL, something is happening — check news immediately

---

## NVDA — NVIDIA Corporation

**Behavior:**
- Highest beta Mag7 stock — moves 5–10% on catalyst regularly
- Largest single-stock options flow by premium in the market on many days
- Driven by: AI narrative, data center earnings, chip export rules, competitor announcements
- Earnings are Feb, May, Aug, Nov — extremely volatile earnings events

**Flow rules:**
- $500k+ for meaningful on NVDA — it has enormous daily flow, need high threshold
- Call sweeps are common here from retail AND institutions — require dark pool or stacking to confirm
- The highest-quality NVDA signals are: large block (not sweep) + dark pool confirm

**Options behavior:**
- IV is high by default (40–60 IVR baseline) — options are expensive
- Do not enter NVDA options when IV rank is above 70 — overpaying
- Preferred: 30–45 DTE with 0.35–0.50 delta strikes

**Special caution:** NVDA moves fast. A 5% gap overnight is possible. Paper trade stops (50% loss) will trigger frequently — this is by design.

---

## MSFT — Microsoft Corporation

**Behavior:**
- Defensive growth stock — moves less violently than NVDA or TSLA
- Steady uptrend bias historically — bearish flow on MSFT is often hedging
- Sensitive to: Azure cloud metrics, AI partnership news (OpenAI), enterprise spending
- Earnings: Jan, Apr, Jul, Oct

**Flow rules:**
- $200k+ for notable, $400k+ for actionable
- Bullish flow on MSFT during tech sector strength is the cleanest signal here
- Put sweeps on MSFT are almost always hedges given its institutional ownership

**Options behavior:**
- Low IV baseline — options are cheap
- Good entry point for bullish trades: call sweep + low IV rank (<30) + uptrend

---

## META — Meta Platforms

**Behavior:**
- High beta, momentum-driven, moves 5–8% on earnings or guidance changes
- Strong correlation to ad spending and broader consumer economy
- Can swing violently in both directions — both call and put flows are meaningful here
- Earnings: Jan, Apr, Jul, Oct

**Flow rules:**
- $300k+ for meaningful, $600k+ for actionable
- Meta call sweeps during social/ad spending momentum cycles are high quality
- Meta put sweeps before macro data (consumer confidence, retail sales) can be directional
- Unlike SPY/QQQ, put sweeps on META are often actually directional, not just hedging

**Options behavior:**
- IV moderate to high — check IV rank before entering
- Premium can be expensive around macro events — respect IV rank < 50 rule

---

## TSLA — Tesla Inc.

**Behavior:**
- Most volatile Mag7 stock. 5–10% daily swings are common. 15%+ on catalyst is not rare.
- Retail-driven with institutional layering — flow signals are noisier than other names
- Sensitive to: delivery numbers, Elon Musk news, energy division, macro/rate environment
- Earnings: Jan, Apr, Jul, Oct

**Flow rules:**
- Require $1M+ premium for TSLA flow to be actionable — noise threshold is very high
- Stacking is essential — single sweep on TSLA is insufficient given volume
- Dark pool confirmation is especially important here — retail sweeps too many contracts to ignore without it

**Options behavior:**
- IV is chronically high — TSLA options are expensive
- Do NOT enter when IV rank > 65 — premium is too expensive
- Use wider DTE (30–60 days) to absorb volatility

**Special caution:** TSLA is the most likely symbol to trigger false alerts. Apply an extra layer of skepticism. Require dark pool OR stacking — not just a single sweep.

---

## AMZN — Amazon.com

**Behavior:**
- Driven by: AWS growth, e-commerce volumes, advertising revenue, macro/consumer spending
- Large cap with less explosive daily moves vs NVDA/TSLA but meaningful 3–6% catalyst moves
- Options flow here is often institutional, making it higher quality than TSLA
- Earnings: Jan, Apr, Jul, Oct

**Flow rules:**
- $300k+ for notable, $500k+ for actionable
- AMZN call flow during AWS-positive narratives (cloud spending cycles) is high quality
- Clean flows — AMZN options flow is less noisy than TSLA, treat sweeps with more weight

**Options behavior:**
- IV moderate — reasonable premium costs most of the time
- Good signal-to-noise ratio compared to other high-beta names

---

## GOOGL — Alphabet Inc.

**Behavior:**
- Driven by: search advertising revenue, Google Cloud, AI developments, YouTube
- Steady compounder — moves 4–8% on earnings, otherwise slow-moving
- Institutional ownership is very high — flow signals here are often clean and meaningful
- Earnings: Jan, Apr, Jul, Oct

**Flow rules:**
- $300k+ for notable, $500k+ for actionable
- GOOGL flow has excellent signal quality — institutions dominate the order flow
- Dark pool prints on GOOGL are particularly meaningful given institutional ownership

**Options behavior:**
- IV moderate to low — affordable options outside of earnings
- Good entry conditions: sweep + IV rank < 40 + price momentum aligned

---

## Cross-Symbol Rules

### Correlation groups — max 1 open trade per group

| Group | Symbols |
|---|---|
| Broad market | SPY, QQQ |
| Big tech / cloud | AAPL, MSFT, GOOGL, AMZN |
| AI / semiconductors | NVDA |
| High beta / consumer | TSLA, META |

Do not hold two open trades in the same group simultaneously. They move together — it doubles effective exposure on the same thesis.

### Market tide overrides by symbol

| Market tide | Action |
|---|---|
| Strong bullish (>65) | Prioritize call flow on all symbols. Treat put flow as hedges unless $2M+. |
| Neutral (35–65) | Equal weight on calls and puts. Require higher confidence threshold (0.77+). |
| Strong bearish (<35) | Prioritize put flow. Do not enter call trades — fighting the tape. |
