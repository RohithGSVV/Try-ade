# Analysis Prompt Template

> This file is the per-scan prompt template. `context_builder.py` fills in
> every {placeholder} with live data before sending to DeepSeek R1.
> The system_prompt.md is sent as the `system` message.
> This filled template is sent as the `user` message.

---

## Prompt Template (context_builder.py fills this each scan)

```
Analyze {ticker} for a potential options trade. Apply your full 4-step framework.

---

SYMBOL: {ticker}
SCAN TIME: {scan_time} ET
SESSION STATUS: {session_status}

---

## PRICE & STRUCTURE

Current price:     ${current_price}
Change today:      {price_change_pct}% ({price_change_direction})
Volume vs avg:     {volume_ratio}x average ({volume_label})

Moving averages:
  21 EMA:          ${ema_21}  → price is {price_vs_ema21}
  50 SMA:          ${sma_50}  → price is {price_vs_sma50}
  VWAP (today):    ${vwap}    → price is {price_vs_vwap}

Key levels:
  Recent resistance: ${resistance_level} ({resistance_distance}% away)
  Recent support:    ${support_level} ({support_distance}% away)
  52-week high:      ${high_52w}
  52-week low:       ${low_52w}

Trend structure:   {trend_structure}
  (e.g. "higher highs and higher lows — uptrend intact"
        "lower highs and lower lows — downtrend"
        "choppy range between {low} and {high} — no clear trend")

---

## MACRO CONTEXT

SPY today:         {spy_change_pct}% | {spy_vs_vwap}
QQQ today:         {qqq_change_pct}% | {qqq_vs_vwap}
VIX:               {vix_level} ({vix_label})
Market Tide:       {market_tide_score}/100 ({market_tide_direction})
  (Scores: >65 = bullish, 35-65 = neutral, <35 = bearish)

---

## OPTIONS VIABILITY

Suggested contract: {suggested_strike}{option_type} expiring {suggested_expiry}
DTE:               {dte} days
IV Rank (IVR):     {ivr}% ({ivr_label})
  (IVR label: <30 = cheap, 30-50 = normal, 50-70 = elevated, >70 = expensive)
Open interest:     {open_interest} contracts
Bid/ask spread:    ${bid_ask_spread}
Delta:             {delta}
Theta (daily):     ${theta_daily}

Earnings date:     {earnings_date} ({earnings_days_away} days away)
Earnings buffer:   {earnings_buffer_status}
  (CLEAR = >5 days, WARNING = 5-10 days, HARD BLOCK = <5 days)

---

## FLOW VERIFICATION

Flow status:       {flow_status}
  (confirming | neutral | contradicting | complex | none)

Recent UW prints (last 60 min on {ticker}):
{flow_prints_block}

  Example format when prints exist:
  • 10:32am | $1.2M | May16 $220C | SWEEP | at ask | BULLISH
  • 10:45am | $400k | May16 $220C | SWEEP | at ask | BULLISH
  • 11:02am | $380k | May16 $220C | BLOCK | at ask | BULLISH
  
  When no prints: "No unusual flow detected on {ticker} in the last 60 minutes."

Spread detected:   {spread_detected}
  (true = matching opposite leg found within 30s — treat as complex, add no confidence)

Net flow premium:  ${net_flow_premium}
  (positive = net bullish flow, negative = net bearish flow)

Dark pool (last 2hr): {darkpool_summary}
  (e.g. "280k shares @ $212.80 at 10:45am — bullish direction" or "none")

---

## OPEN POSITIONS CHECK

Current open paper trades: {open_positions_count} / 3 max
{open_positions_block}

  Example format:
  • AAPL BULL CALL $220 May16 — entered $3.20, currently +18%
  
  When none: "No open positions."

Correlation group for {ticker}: {correlation_group}
Group already occupied: {group_occupied}
  (true = hard block on correlation — cannot open another trade in this group)

---

## YOUR TASK

Apply your 4-step framework now:

1. Build a directional thesis from PRICE & STRUCTURE and MACRO CONTEXT.
   Write your technical_basis BEFORE reading the flow section above.
   (Yes, you can see it — but pretend you haven't yet. The discipline matters.)

2. Check OPTIONS VIABILITY for hard blocks and contract quality.

3. Read FLOW VERIFICATION and apply the appropriate confidence modifier.

4. Output the JSON. Every field required. No text outside the JSON.

Remember:
- thesis before flow
- hard blocks override everything
- no flow + confidence < 0.85 = no trade
- contradicting flow = almost always skip
- spread detected = add zero confidence from that flow
```

---

## How context_builder.py Fills This Template

```python
def build_analysis_prompt(ticker: str, live_data: dict) -> str:
    """
    Loads analysis_prompt.md and fills all {placeholders} with live data.
    Called once per ticker per scan cycle.
    """
    with open("prompts/analysis_prompt.md", "r") as f:
        template = f.read()
        # Extract just the prompt block between ``` markers
        prompt = template.split("```")[1]  # get first code block

    return prompt.format(
        ticker=ticker,
        scan_time=live_data["scan_time"],
        session_status=live_data["session_status"],
        current_price=live_data["price"],
        price_change_pct=live_data["change_pct"],
        price_change_direction=live_data["change_direction"],
        volume_ratio=live_data["volume_ratio"],
        volume_label=live_data["volume_label"],
        ema_21=live_data["ema_21"],
        price_vs_ema21=live_data["price_vs_ema21"],
        sma_50=live_data["sma_50"],
        price_vs_sma50=live_data["price_vs_sma50"],
        vwap=live_data["vwap"],
        price_vs_vwap=live_data["price_vs_vwap"],
        resistance_level=live_data["resistance"],
        resistance_distance=live_data["resistance_dist"],
        support_level=live_data["support"],
        support_distance=live_data["support_dist"],
        high_52w=live_data["high_52w"],
        low_52w=live_data["low_52w"],
        trend_structure=live_data["trend_structure"],
        spy_change_pct=live_data["spy_change"],
        spy_vs_vwap=live_data["spy_vs_vwap"],
        qqq_change_pct=live_data["qqq_change"],
        qqq_vs_vwap=live_data["qqq_vs_vwap"],
        vix_level=live_data["vix"],
        vix_label=live_data["vix_label"],
        market_tide_score=live_data["market_tide_score"],
        market_tide_direction=live_data["market_tide_direction"],
        suggested_strike=live_data["strike"],
        option_type=live_data["option_type"],
        suggested_expiry=live_data["expiry"],
        dte=live_data["dte"],
        ivr=live_data["ivr"],
        ivr_label=live_data["ivr_label"],
        open_interest=live_data["open_interest"],
        bid_ask_spread=live_data["spread"],
        delta=live_data["delta"],
        theta_daily=live_data["theta"],
        earnings_date=live_data["earnings_date"],
        earnings_days_away=live_data["earnings_days"],
        earnings_buffer_status=live_data["earnings_status"],
        flow_status=live_data["flow_status"],
        flow_prints_block=live_data["flow_prints"],
        spread_detected=live_data["spread_detected"],
        net_flow_premium=live_data["net_premium"],
        darkpool_summary=live_data["darkpool"],
        open_positions_count=live_data["open_count"],
        open_positions_block=live_data["open_positions"],
        correlation_group=live_data["corr_group"],
        group_occupied=live_data["group_occupied"],
    )
```

---

## How the Full LLM Call Looks

```python
def build_messages(ticker: str, live_data: dict) -> list:
    """
    Assembles the full message list for the OpenRouter API call.
    system = fixed identity + reasoning rules
    user   = filled analysis template with live data
    """

    # Load system prompt (static, same every call)
    with open("prompts/system_prompt.md", "r") as f:
        raw = f.read()
        system_text = raw.split("```")[1]  # extract the prompt block

    # Load all knowledge files and prepend to system context
    knowledge_files = [
        "knowledge/playbook.md",          # READ FIRST
        "knowledge/risk_rules.md",        # hard blocks
        "knowledge/flow_interpretation.md",
        "knowledge/options_basics.md",
        "knowledge/symbol_profiles.md",   # drop first if token budget tight
    ]

    knowledge_context = ""
    for path in knowledge_files:
        with open(path, "r") as f:
            knowledge_context += f"\n\n---\n\n" + f.read()

    system_message = knowledge_context + "\n\n---\n\n" + system_text

    # Build the filled user prompt
    user_message = build_analysis_prompt(ticker, live_data)

    return [
        {"role": "system", "content": system_message},
        {"role": "user",   "content": user_message},
    ]
```

---

## Filled Example (what R1 actually receives for AAPL)

```
Analyze AAPL for a potential options trade. Apply your full 4-step framework.

SYMBOL: AAPL
SCAN TIME: 11:14am ET
SESSION STATUS: ACTIVE

PRICE & STRUCTURE
Current price:     $218.40
Change today:      +1.1% (bullish)
Volume vs avg:     1.4x average (elevated)

Moving averages:
  21 EMA: $214.20 → price is above
  50 SMA: $208.80 → price is above
  VWAP (today): $216.50 → price is above

Key levels:
  Recent resistance: $221.00 (1.2% away)
  Recent support:    $214.50 (1.8% away)
  52-week high:      $237.49
  52-week low:       $169.21

Trend structure: higher highs and higher lows — uptrend intact

MACRO CONTEXT
SPY today: +0.6% | above VWAP
QQQ today: +0.9% | above VWAP
VIX: 17.4 (low — favorable for long premium)
Market Tide: 71/100 (bullish)

OPTIONS VIABILITY
Suggested contract: $220C expiring 2025-05-16
DTE: 28 days
IV Rank (IVR): 38% (normal)
Open interest: 14,200 contracts
Bid/ask spread: $0.08
Delta: 0.42
Theta (daily): -$0.06

Earnings date: 2025-05-01 (13 days away)
Earnings buffer: WARNING — 13 days, elevated IV into event

FLOW VERIFICATION
Flow status: confirming

Recent UW prints (last 60 min on AAPL):
• 11:14am | $1.2M | May16 $220C | SWEEP | at ask | BULLISH
• 11:18am | $400k | May16 $220C | SWEEP | at ask | BULLISH
• 11:22am | $380k | May16 $220C | SWEEP | at ask | BULLISH

Spread detected: false
Net flow premium: $1,980,000
Dark pool (last 2hr): 280k shares @ $216.80 at 10:45am — bullish direction

OPEN POSITIONS CHECK
Current open paper trades: 1 / 3 max
• NVDA BULL CALL $900 May02 — entered $8.50, currently -12%

Correlation group for AAPL: Big tech / cloud [AAPL, MSFT, GOOGL, AMZN]
Group already occupied: false

YOUR TASK
Apply your 4-step framework now...
```