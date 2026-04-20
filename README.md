# LLM Trading Bot

An automated **options flow analysis bot** that monitors institutional order flow on 9 US stocks/ETFs, uses two AI models in parallel to build a thesis-first trade decision, and paper trades with full P&L tracking.

> **Status:** End-to-end runnable. Paper trading only — no real money, no brokerage connection.

---

## What it does right now

Every 10 minutes during market hours (10am–3:30pm ET), for each of 9 symbols:

1. **Checks hard blocks** — session time, VIX level, max open positions, correlation groups, 24hr re-entry cooldown. Blocked tickers are skipped instantly (no API call wasted).
2. **Scores options flow** — fetches the last 60 min of Unusual Whales flow for the ticker, scores it by size/type/stacking/dark pool. Score < 4 = skip.
3. **Calls both LLMs in parallel** — DeepSeek R1 + GPT-OSS 120B each get the full context: price structure, moving averages, VWAP, market tide, earnings date, open positions, and scored flow prints.
4. **Consensus check** — both models must agree on direction (bullish/bearish) and both must say ENTER. Any disagreement = no trade.
5. **Logs paper trade** — fetches real ask price from Tradier, writes to `paper_trades.csv`.
6. **Sends Discord alert** — shows both models' confidence scores and thesis.
7. **Auto-manages positions** — checks every open trade each cycle. Closes at -50% loss, +100% gain, or ≤5 DTE remaining. Sends close alert to Discord.

---

## Watchlist

```
SPY  QQQ  AAPL  NVDA  MSFT  META  TSLA  AMZN  GOOGL
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Needed for `zoneinfo` and `X \| Y` type hints |
| OpenRouter account ×2 | Free — one for DeepSeek R1, one for GPT-OSS 120B |
| Finnhub account | Free — real-time WebSocket prices |
| Unusual Whales API | $50/mo — options flow, dark pool, market tide |
| Tradier account | Free sandbox — options chains + entry prices |
| Discord webhook | Free — paste a channel webhook URL, no bot needed |

---

## Step-by-step setup

### 1. Clone and install

```bash
git clone <your-repo-url>
cd trading-bot
pip install -r requirements.txt
```

### 2. Get your API keys

| Key | Where |
|---|---|
| `OPENROUTER_API_KEY_DEEPSEEK` | [openrouter.ai](https://openrouter.ai) → Dashboard → API Keys (Account 1) |
| `OPENROUTER_API_KEY_GPT` | [openrouter.ai](https://openrouter.ai) → Dashboard → API Keys (Account 2, different email) |
| `FINNHUB_API_KEY` | [finnhub.io](https://finnhub.io) → shown on dashboard after login |
| `UW_API_KEY` | unusualwhales.com → Account → API ($50/mo required) |
| `TRADIER_API_KEY` | [developer.tradier.com](https://developer.tradier.com) → Create App → copy Access Token |
| `DISCORD_WEBHOOK_URL` | Discord channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL |

### 3. Fill in `.env`

```env
OPENROUTER_API_KEY_DEEPSEEK=sk-or-v1-...
OPENROUTER_API_KEY_GPT=sk-or-v1-...
FINNHUB_API_KEY=your_20_char_key
UW_API_KEY=your_uw_key
TRADIER_API_KEY=your_tradier_token
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

> ⚠️ Never commit `.env` — it is gitignored. Never share these keys in chat or screenshots.

### 4. Verify feeds work

```bash
python -m feeds.test
```

Expected output:
```
── Finnhub WebSocket ──────────────────────────────
  AAPL    47 ticks  last=$218.40
  NVDA    52 ticks  last=$890.10
  ...
  PASS — 9/9 symbols ticked

── Tradier Options Chain ──────────────────────────
  AAPL 2025-05-16: 45 calls, 45 puts
  PASS — options chain returned 90 contracts

── Unusual Whales REST ────────────────────────────
  Flow [11:14am] $1,200,000  call sweep ask  → BULLISH
  PASS — 5 flow alert(s) returned for AAPL
  ...
```

### 5. Run the bot

```bash
python main.py
```

The bot will:
- Start the Finnhub price stream
- Wait up to 30s for price ticks
- Run the first scan immediately
- Schedule a scan every 10 minutes
- Log everything to console + `bot.log`

**Stop it:** `Ctrl+C` — shuts down cleanly.

---

## What you will see

### Console / bot.log during a scan
```
10:14:22 INFO    scan — ─── Scan cycle starting (9 symbols) ───
10:14:23 INFO    scan —   SPY    BLOCKED  — session opening block (first 30 min — high noise)
10:14:24 INFO    scan —   QQQ    BLOCKED  — session opening block (first 30 min — high noise)
10:14:25 INFO    scan —   AAPL   ANALYZING — flow score=8
10:14:35 INFO    scan —   AAPL   ALERT [CONSENSUS] BULLISH | DS=0.81 GPT=0.78
10:14:36 INFO    scan —   NVDA   LOW FLOW — score=2 (threshold 4)
10:14:37 INFO    scan —   MSFT   SKIP — below threshold (DS=0.68 GPT=0.71)
10:14:38 INFO    scan — ─── Cycle done in 16.2s | scanned=9 blocked=2 low_flow=3 llm_calls=4 alerts=1 trades=1 ───
```

### Discord alert on entry
```
🟢 CONSENSUS ALERT — AAPL BULLISH CALL $220 2025-05-16
────────────────────────────────────────────────────────
DeepSeek R1   | conf: 0.81 | confirming
GPT-OSS 120B  | conf: 0.78 | confirming
────────────────────────────────────────────────────────
Thesis : Uptrend intact, support bounce, stacked call sweeps $1.2M+
Flow   : confirming
Entry  : $3.20 ask  |  DTE: 28
Signals: call sweep stack, low IVR, support bounce, bullish tide
Risks  : approaching resistance at $222, VIX ticking up
```

### Discord alert on close
```
🔴 STOPPED OUT — NVDA BULLISH CALL $900 2025-05-02
Reason : Stop loss hit
Entry  : $8.50  →  Exit: $4.25
P&L    : -50.0%
```

### paper_trades.csv
```
id,date_entered,ticker,direction,type,strike,expiry,entry_price,contracts,...
1,2025-04-20 11:14,AAPL,bullish,call,220,2025-05-16,3.20,6,...
```

---

## Do I need to keep it running all day?

**During the session: yes.** The bot only does work during 10am–3:30pm ET (2:30pm–9:30pm IST). Before and after those hours, scan cycles are skipped automatically.

**Options for running it:**

| Option | Best for |
|---|---|
| Your laptop (keep it open) | Testing — first 1-2 weeks |
| Google Colab notebook | Running without tying up your machine (free) |
| Cheap VPS — Hetzner/Vultr ~$4/mo | Production — reliable, always on |

For testing, just run it on your laptop during the session. Move to a VPS once you're happy with the results.

---

## Do the AI models need training on historical data?

**No.** DeepSeek R1 and GPT-OSS 120B are pre-trained large language models — they already understand options trading, technical analysis, and market structure from their training. You are not training them; you are sending them prompts.

yfinance (historical data) is used **at runtime** to compute:
- 21-day EMA, 50-day SMA
- Intraday VWAP
- 52-week high/low
- Support/resistance levels
- Earnings dates

This happens automatically every scan cycle. No setup required.

---

## What's not built yet

| Feature | Phase | Impact |
|---|---|---|
| Terminal UI (Rich live table) | Phase 5 | Nice to have — logs cover it for now |
| Trade journal (SQLite audit log) | Phase 5 | `bot.log` covers it for now |
| Backtesting (replay UW history) | Phase 6 | Needed to validate before scaling |

---

## File structure

```
trading-bot/
├── main.py                  ← entry point — python main.py
├── scan.py                  ← one scan cycle across all 9 symbols
├── config/
│   └── settings.py          ← all thresholds, keys, constants
├── feeds/
│   ├── finnhub_feed.py      ← real-time price WebSocket
│   ├── tradier_feed.py      ← options chain, Greeks, entry price
│   ├── uw_feed.py           ← flow alerts, dark pool, market tide
│   ├── historical_feed.py   ← yfinance: EMA/SMA/VWAP/earnings
│   └── test.py              ← python -m feeds.test
├── signals/
│   ├── flow_verifier.py     ← score + filter UW prints (pre-LLM)
│   ├── market_tide.py       ← UW tide refresh every 5 min
│   └── event_filters.py     ← code-side hard blocks
├── core/
│   ├── data_bus.py          ← real-time price store (Finnhub → here)
│   ├── context_builder.py   ← fills analysis prompt with live data
│   └── llm_engine.py        ← dual model calls + consensus + Discord
├── trading/
│   ├── paper_trader.py      ← log trades to paper_trades.csv
│   └── position_tracker.py  ← P&L updates, auto-close
├── knowledge/               ← LLM reads all 5 files before every analysis
├── prompts/                 ← system prompt + analysis template
├── paper_trades.csv         ← created on first trade
├── bot.log                  ← created on first run
└── .env                     ← your API keys (never commit this)
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `No ticks received` after startup | Bad Finnhub key | Check `FINNHUB_API_KEY` — must be exactly 20 chars |
| All tickers `LOW FLOW` | UW key missing | Fill `UW_API_KEY` — flow data requires the paid plan |
| LLM returns invalid JSON | Model rate limit | Wait a few minutes; fallback model will kick in |
| Tradier returns empty chain | Wrong base URL | Check `TRADIER_BASE_URL` in settings.py (sandbox vs live) |
| Discord alert not sending | Bad webhook URL | Re-copy the full webhook URL from Discord channel settings |
