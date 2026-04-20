# Options Basics — Trading Bot Knowledge

> This document is loaded into the LLM context before every analysis.
> It defines core options concepts the bot must understand to reason correctly.

---

## What an Option Is

An option is a contract giving the buyer the right — but not the obligation — to buy or sell 100 shares of a stock at a specific price (the strike) before a specific date (the expiry). One contract = 100 shares.

- **Call option** — right to BUY shares at the strike. Profits when stock goes UP.
- **Put option** — right to SELL shares at the strike. Profits when stock goes DOWN.

The buyer pays a **premium** (the option price × 100). This is the maximum they can lose.

---

## Key Terms

### Strike Price
The price at which the option gives the right to buy (call) or sell (put). If AAPL is at $210 and you buy a $220 call, the stock needs to rise above $220 before expiry to be profitable at expiry.

### Expiry Date
The date the option contract expires. After this date it is worthless if not in the money. Always look at:
- **Days to Expiry (DTE):** how many calendar days remain
- Never recommend options with less than 14 DTE — time decay is brutal

### In the Money (ITM) / Out of the Money (OTM) / At the Money (ATM)
- **ITM call:** strike is below current stock price (e.g. $200 call when stock is $210)
- **OTM call:** strike is above current stock price (e.g. $220 call when stock is $210)
- **ATM:** strike equals current stock price
- OTM options are cheaper and have higher leverage but lower probability of profit
- Most unusual flow targets OTM options — they're cheaper to move big premium with

### Premium
The price of one option contract divided by 100. If an option costs $3.50, the buyer pays $350 per contract. Total flow premium = contracts × price × 100.

---

## The Greeks — What They Mean for Trade Selection

### Delta (Δ)
- Measures how much the option price moves per $1 move in the stock
- Call delta: 0 to 1.0 | Put delta: -1.0 to 0
- ATM options have ~0.50 delta. Deep ITM can be ~0.90+.
- **Rule:** Prefer options with delta between 0.30–0.60 for balanced leverage and probability

### Theta (Θ)
- Time decay — how much value the option loses per day, all else equal
- Always negative for buyers. Accelerates in the last 2–3 weeks before expiry.
- **Rule:** Never enter options with less than 14 DTE — theta decay is too aggressive

### Gamma (Γ)
- Rate of change of delta. High gamma = delta moves quickly with stock price.
- ATM options have highest gamma. High gamma = explosive potential, both ways.
- High gamma near expiry = dangerous. Small stock move = huge option swing.

### Vega (V)
- Sensitivity to implied volatility (IV) changes
- High vega = option price rises/falls significantly with IV changes
- Buying before earnings = buying high vega. After earnings IV collapses (IV crush).
- **Rule:** Never buy options into earnings. IV will crush the premium even if direction is right.

### IV Rank (IVR) and IV Percentile
- **IV Rank:** where current IV sits relative to its 52-week range (0–100)
- IVR above 50 = options are expensive relative to recent history
- IVR below 30 = options are relatively cheap
- **Rule:** Prefer buying options when IVR < 50. High IVR means overpaying for premium.

---

## Options Strategies (Context for Flow Interpretation)

### Long Call
- Buy a call, profit if stock rises above strike + premium paid
- Used in bullish flow: sweep on the ask = someone expects stock to rise

### Long Put
- Buy a put, profit if stock falls below strike - premium paid
- Used in bearish flow: sweep on the bid = someone expects stock to fall

### Call Spread / Put Spread
- Buying one strike and selling another to reduce cost
- Limits upside but also limits cost — seen in large hedged institutional flows
- If flow is a spread (multi-leg), weight it lower as a directional signal

### Covered Call / Protective Put
- Often used as hedges, not directional bets
- Large put flows on SPY/QQQ from institutions are often portfolio hedges, NOT bearish bets
- Context: if market tide is bullish and you see large SPY put flow, it's likely a hedge — do not interpret as bearish signal

---

## Option Pricing: What Drives Premium

1. **Intrinsic value** — how far ITM the option is (zero if OTM)
2. **Time value** — more time = more premium
3. **Implied Volatility** — higher IV = higher premium
4. **Distance from strike** — further OTM = cheaper but requires bigger move

Understanding this means:
- A $1M sweep on a $0.50 option = 20,000 contracts — massive position
- A $1M sweep on a $5.00 option = 2,000 contracts — still large but more conservative
- Both are significant. The cheaper option suggests higher conviction on a big fast move.

---

## Common Mistakes to Avoid in Trade Selection

- **Buying high IV options** — overpaying for premium that IV crush will destroy
- **Buying near expiry** — theta eats value daily even if direction is right
- **Ignoring market tide** — buying calls in a strong bear trend fights the tape
- **Treating all put flow as bearish** — large put flow on indexes is often hedging
- **Chasing already-moved options** — if AAPL already moved 3% on news and options are up 200%, the move is priced in
- **Overweighting one signal** — flow alone is not enough; confirm with price action and market tide

---

## Quick Reference: Signal Strength

| Scenario | Interpretation |
|---|---|
| Call sweep on ask, OTM, >$500k premium | Strong bullish signal |
| Put sweep on bid, OTM, >$500k premium | Strong bearish signal |
| Large put on SPY/QQQ during bull market tide | Likely hedge — lower weight |
| Repeat sweeps same ticker within 60 min | Very strong conviction — weight higher |
| Dark pool print + same-direction sweep | Institutional confirmation — weight highest |
| Sweep on bid for calls / ask for puts | Closing position, not opening — ignore |
| IV rank > 60 on the flagged contract | Premium expensive — only enter if flow is extreme |
| Earnings within 5 days | Hard block — do not enter |
