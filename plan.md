# 🤖 LLM Trading Bot — Project Plan

> **Markets:** US Stocks & Options  
> **Stack:** Python  
> **LLM:** DeepSeek R1 via OpenRouter (free) → Claude later  
> **Flow:** Unusual Whales API ($50/mo)  
> **Watchlist:** Mag7 + SPY + QQQ (9 symbols)  
> **Paper trading:** CSV log + terminal UI  
> **Total cost:** ~$50/mo  

---

## 💰 Cost Summary

| Service | Cost | Notes |
|---|---|---|
| Unusual Whales API | $50/mo | Flow, dark pool, market tide |
| OpenRouter (DeepSeek R1) | Free | 200 req/day, chain-of-thought |
| Finnhub | Free | Real-time stock prices via WebSocket |
| Tradier | Free | Real-time options chains + Greeks (open free account) |
| yfinance | Free | Historical OHLCV for backtesting only |
| Telegram Bot | Free | Alerts |
| SQLite + CSV | Free | Storage + paper trade log |
| **Total** | **~$50/mo** | |

---

## 📊 Data Stack

| Source | Purpose | Delay | Cost |
|---|---|---|---|
| **Finnhub** | Real-time stock prices (WebSocket stream) | None | Free |
| **Tradier** | Real-time options chains + Greeks | None | Free w/ account |
| **Unusual Whales** | Flow alerts, dark pool, market tide, news | Seconds | $50/mo |
| **yfinance** | Historical OHLCV (backtesting only) | 15min (irrelevant for history) | Free |

### Why this combination
- Finnhub free tier gives real-time US stock prices via WebSocket at 60 calls/min — enough for 9 symbols with headroom
- Tradier gives real-time OPRA options chains with Greeks (Delta, Theta, IV) free with a brokerage account — critical for accurate paper trade entry prices
- yfinance is kept only for pulling historical candle data for backtesting — the 15-min delay doesn't matter for history
- Alpaca free tier was considered but rejected: it only covers the IEX exchange for stocks (small fraction of volume) and an indicative options feed — not reliable enough for entry price logging

---

## 🧠 LLM: DeepSeek R1 via OpenRouter

**Why R1 over Llama 3.3 70B or GPT-OSS 120B:**
- Reasoning model — thinks step by step, exposes chain-of-thought
- You can read exactly why it flagged a trade and debug bad calls
- Strongest on multi-signal analytical tasks

**Fallback:** `meta-llama/llama-3.3-70b-instruct:free` if R1 hits rate limits

```python
LLM_MODEL    = "deepseek/deepseek-r1:free"
LLM_FALLBACK = "meta-llama/llama-3.3-70b-instruct:free"
```

---

## 📋 Watchlist (9 symbols)

```python
WATCHLIST = [
    "SPY", "QQQ",                                             # Indexes
    "AAPL", "NVDA", "MSFT", "META", "TSLA", "AMZN", "GOOGL"  # Mag7
]
```

9 symbols × every 10 min × 6.5hr session = ~58 LLM calls/day. Well within the 200 free limit.

---

## ⚠️ Known Limitations & Rules

### Hard session rules
- No trades in first 30 min (9:30–10:00am ET) — opening noise
- No trades in last 30 min (3:30–4:00pm ET) — rebalancing noise

### Hard trade filters
- No new trade within 5 days of earnings — IV crush risk
- No trades when VIX > 30 — options too expensive, unpredictable
- Minimum expiry 14 days out — no weeklies
- Max 3 open paper trades at once — simulates capital constraints
- No two open trades in the same correlated group (e.g. AAPL + MSFT both open = blocked)

### Paper trade stops
- Auto-close at 50% loss
- Auto-close at 100% gain
- Auto-close at expiry

### Entry price accuracy
- Entry price logged using Tradier real-time options chain (not yfinance)
- Entry logged at the ask price, not mid — simulates realistic fill

---

## 📄 Paper Trading

Every alert that meets the confidence threshold:
1. Logs a row to `paper_trades.csv`
2. Fetches real entry price from Tradier at that moment
3. Updates terminal UI with open position
4. Tracks P&L every scan cycle
5. Auto-closes and logs outcome on stop/target/expiry

### paper_trades.csv columns
```
id | date_entered | symbol | direction | type | strike | expiry 
| entry_price | confidence | status | current_price | pnl_pct 
| exit_price | outcome | thesis_summary
```

### Terminal UI (Rich)
```
╔══════════════════════════════════════════════════════════════════╗
║  🤖 LLM TRADING BOT  |  11:42am  |  Next scan: 11:52am         ║
╠══════════════════════════════════════════════════════════════════╣
║  OPEN PAPER TRADES                                               ║
╠════════╦═══════╦══════╦════════╦══════════╦════════╦════════════╣
║ Symbol ║  Dir  ║ Type ║ Strike ║  Expiry  ║ Entry  ║ P&L        ║
╠════════╬═══════╬══════╬════════╬══════════╬════════╬════════════╣
║ AAPL   ║ BULL  ║ CALL ║ $220   ║ May 16   ║ $3.20  ║ +28.1% 🟢 ║
║ NVDA   ║ BEAR  ║ PUT  ║ $850   ║ May 02   ║ $6.40  ║  -7.8% 🔴 ║
╠════════╩═══════╩══════╩════════╩══════════╩════════╩════════════╣
║  RECENT ALERTS                                                   ║
║  11:34  MSFT  BULL  0.76 → ENTERED                              ║
║  11:21  QQQ   BEAR  0.68 → SKIPPED (below threshold)           ║
╠══════════════════════════════════════════════════════════════════╣
║  Today: 3 alerts | 2 trades | 30-day win rate: 64%             ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 🧠 Core Architecture Principle: Thesis First, Flow Second

This is the most important design decision in the entire system.

```
❌ WRONG:  Flow alert → Bot trades
✅ CORRECT: LLM builds thesis → Flow verifies → You decide
```

**The 4-step decision chain (enforced in every analysis cycle):**

```
Step 1 — BUILD BIAS FROM STRUCTURE
         Price vs 21 EMA / 50 SMA / VWAP
         Higher highs/lows? Key support or resistance nearby?
         Market Tide direction from UW
         SPY/QQQ macro context
         → If no clear bias can be formed: STOP. No trade.

Step 2 — CHECK OPTIONS VIABILITY
         IVR < 70? DTE ≥ 14? OI > 1000? Spread < $0.25?
         Hard blocks: earnings, VIX, session time
         → Any hard block triggered: alert = false. Always.

Step 3 — VERIFY WITH FLOW
         Does UW flow from the last 60 min align with the thesis?
         Confirming flow → +0.15 confidence
         No flow       →  0.00 (raise threshold to 0.85)
         Contradicting → -0.25 (usually skip)

Step 4 — SCORE AND DECIDE
         Confidence ≥ 0.72 → alert fires → paper trade logged
         Confidence < 0.72 → no alert
```

**Flow is a weight, not a trigger.** The bot never trades because "big money bought calls."
It only trades when a technical thesis would be valid even without flow — and flow then confirms it.

This principle is codified in `knowledge/playbook.md` which the LLM reads before every analysis.

---

## 🗂️ Project Phases

### Phase 1 — Data Layer (Week 1)
- [ ] Sign up Unusual Whales API → test `/api/option-trades/flow-alerts`
- [ ] Connect UW Kafka stream → log raw events to console
- [ ] Set up Finnhub WebSocket → stream real-time prices for all 9 symbols
- [ ] Set up Tradier sandbox account → pull live options chains + Greeks
- [ ] Set up yfinance → pull historical OHLCV for backtesting
- [ ] Build `DataBus` — normalize all feeds into unified event format
- [ ] Store to SQLite

**Deliverable:** `python feeds/test.py` → live flow + prices printing together.

---

### Phase 2 — Signal Processing (Week 1–2)
- [ ] `FlowVerifier` — pre-processes UW flow events before the LLM sees them. Output is a structured dict, NOT a score. The LLM does the scoring using `playbook.md` rules:
  ```python
  {
    "recent_prints": [...],     # raw print list for last 60 min
    "net_premium": 1_980_000,   # positive = net bullish, negative = net bearish
    "spread_detected": False,   # True if matching opposite leg found within 30s
    "status": "confirming"      # confirming | neutral | contradicting | complex
  }
  ```
- [ ] `MarketTideWatcher` — fetch UW market tide score, classify as bullish/neutral/bearish
- [ ] `GreeksContext` — pull Delta, Theta, IVR, OI, bid/ask from Tradier for suggested contract
- [ ] `TechnicalLevels` — calculate 21 EMA, 50 SMA, VWAP, support/resistance, trend structure
- [ ] `ContextBuilder` — assemble full live data dict, fill `analysis_prompt.md` template, prepend all knowledge files

---

### Phase 3 — LLM Engine (Week 2)
- [x] `prompts/system_prompt.md` — ✅ done. Forces thesis-first reasoning order + JSON contract
- [x] `prompts/analysis_prompt.md` — ✅ done. Live data template with all placeholders
- [ ] `LLMEngine` — call OpenRouter with system + filled analysis prompt:
  - Set `response_format={"type": "json_object"}` to force valid JSON
  - Log `reasoning_content` (R1's chain-of-thought) separately for auditing
  - Retry once on JSON parse failure with a clarification message
  - After 2 failures: log raw response, skip ticker for this cycle
  - Token budget: drop `symbol_profiles.md` first if >7k tokens, never drop `playbook.md` or `risk_rules.md`
- [ ] Validate reasoning manually on 20+ real outputs before going live

---

### Phase 4 — Paper Trading + UI (Week 2–3)
- [ ] `PaperTrader` — log trades to CSV on alert, fetch entry price from Tradier
- [ ] `PositionTracker` — update P&L each scan, auto-close on stop/target/expiry
- [ ] `TerminalUI` — Rich live table of open trades + recent alerts

---

### Phase 5 — Alert System (Week 3)
- [ ] Telegram bot via @BotFather
- [ ] Alert on paper trade entry with full trade details
- [ ] Confirmation logging (confirm / dismiss)

---

### Phase 6 — Backtesting (Week 4)
- [ ] Replay 3 months of UW flow tape through LLM
- [ ] Score win rate by signal type, symbol, confidence band
- [ ] Target: 60%+ accuracy before expanding watchlist

---

### Phase 7 — Feedback Loop (Ongoing)
- [ ] Log all outcomes (win/loss/expired)
- [ ] Weekly performance summary fed back to LLM context
- [ ] Tune system prompt and thresholds based on patterns

---

## 🏗️ File Structure

```
trading-bot/
│
├── config/
│   └── settings.py
│
├── knowledge/                   ← LLM reads ALL of these before every analysis
│   ├── playbook.md              # ✅ done — READ FIRST. Thesis-first framework + examples
│   ├── options_basics.md        # ✅ done — Greeks, premium, IV, strategy mechanics
│   ├── flow_interpretation.md   # ✅ done — How to read and weight UW flow data
│   ├── symbol_profiles.md       # ✅ done — Per-symbol rules for all 9 watchlist names
│   └── risk_rules.md            # ✅ done — Hard blocks, confidence modifiers, stops
│
├── feeds/
│   ├── uw_feed.py               # UW REST + Kafka
│   ├── finnhub_feed.py          # Real-time stock prices (WebSocket)
│   ├── tradier_feed.py          # Real-time options chains + Greeks
│   ├── historical_feed.py       # yfinance (backtesting only)
│   └── test.py
│
├── signals/
│   ├── flow_verifier.py      # was flow_scorer.py — outputs structured dict, not a score
│   ├── market_tide.py        # UW market tide fetch + classification
│   ├── technical_levels.py   # 21 EMA, 50 SMA, VWAP, S/R, trend structure
│   └── event_filters.py      # spread trap detection, staleness check
│
├── core/
│   ├── data_bus.py
│   ├── context_builder.py
│   └── llm_engine.py
│
├── trading/
│   ├── paper_trader.py
│   └── position_tracker.py
│
├── ui/
│   └── terminal_ui.py
│
├── alerts/
│   ├── telegram_bot.py
│   └── trade_journal.py
│
├── prompts/
│   ├── system_prompt.md      # ✅ done — LLM identity + reasoning order + JSON contract
│   └── analysis_prompt.md    # ✅ done — live data template, filled each scan by context_builder
│
├── paper_trades.csv
├── backtest.py
├── scan.py
├── analyze.py
├── main.py
└── requirements.txt
```

---

## 📦 requirements.txt

```txt
yfinance
requests
kafka-python
websocket-client       # Finnhub WebSocket
openai                 # OpenRouter-compatible
python-telegram-bot
sqlalchemy
schedule
python-dotenv
pydantic
rich
pandas
```

---

## ⚙️ config/settings.py

```python
# LLM
OPENROUTER_API_KEY = ""
LLM_MODEL          = "deepseek/deepseek-r1:free"
LLM_FALLBACK       = "meta-llama/llama-3.3-70b-instruct:free"

# Data feeds
UW_API_KEY         = ""
UW_BASE_URL        = "https://api.unusualwhales.com"
FINNHUB_API_KEY    = ""
TRADIER_API_KEY    = ""

# Alerts
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID   = ""

# Watchlist
WATCHLIST = ["SPY","QQQ","AAPL","NVDA","MSFT","META","TSLA","AMZN","GOOGL"]

# Thresholds
CONFIDENCE_THRESHOLD  = 0.72
MIN_FLOW_PREMIUM      = 100_000   # $100k+
SCAN_INTERVAL_MIN     = 10
VIX_MAX               = 30
MAX_OPEN_POSITIONS    = 3
MIN_EXPIRY_DAYS       = 14
NO_TRADE_OPEN_MIN     = 30        # Skip first 30min
NO_TRADE_CLOSE_MIN    = 30        # Skip last 30min
EARNINGS_BUFFER_DAYS  = 5

# Paper trade stops
STOP_LOSS_PCT         = 0.50
TAKE_PROFIT_PCT       = 1.00
```

---

## 🚦 Build Order

```
Week 1   feeds/ + data_bus.py + context_builder.py    data flows
Week 2   llm_engine.py + prompts/                     LLM reasons
Week 2   paper_trader.py + position_tracker.py        trades tracked
Week 3   terminal_ui.py + telegram_bot.py + main.py   bot runs live
Week 4   backtest.py                                   validate
Ongoing  feedback loop + threshold tuning
```

---

## 🔁 Upgrade Path

```
Now                                Later
─────────────────────────────────  ─────────────────────────────────
DeepSeek R1 (free)             →   Claude (UW MCP native tool calls)
Finnhub free WebSocket         →   Keep (it's good enough)
Tradier free options           →   Keep (it's good enough)
9 symbols                      →   Expand after 60%+ win rate
CSV + terminal UI              →   Streamlit dashboard
```