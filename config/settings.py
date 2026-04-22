import os
from dotenv import load_dotenv

load_dotenv()

# LLM — dual model setup (two OpenRouter accounts, one key each)
# Both models run per ticker per scan; alert fires only when both agree.
OPENROUTER_API_KEY_DEEPSEEK = os.getenv("OPENROUTER_API_KEY_DEEPSEEK", "")
OPENROUTER_API_KEY_GPT      = os.getenv("OPENROUTER_API_KEY_GPT", "")

LLM_DEEPSEEK = "deepseek/deepseek-r1:free"   # exposes reasoning_content (chain-of-thought)
LLM_GPT      = "openai/gpt-oss-120b:free"    # second opinion, no reasoning_content field
LLM_FALLBACK = "meta-llama/llama-3.3-70b-instruct:free"  # used if both primaries fail

# Consensus rule: both models must agree on direction for alert to fire.
# If they disagree → no trade. If one fails → fall back to single-model threshold (0.80).
LLM_REQUIRE_CONSENSUS = True

# Data feeds
UW_API_KEY      = os.getenv("UW_API_KEY", "")
UW_BASE_URL     = "https://api.unusualwhales.com"
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

# Robinhood — options chain, Greeks, entry prices (uses your existing account)
# robin_stocks stores the auth token after first login, so MFA is only asked once.
RH_USERNAME = os.getenv("RH_USERNAME", "")
RH_PASSWORD = os.getenv("RH_PASSWORD", "")

# Alerts — Discord webhook (simpler than Telegram: no bot, no library, one URL)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Watchlist
WATCHLIST = ["SPY", "QQQ", "AAPL", "NVDA", "MSFT", "META", "TSLA", "AMZN", "GOOGL"]

# Correlation groups — max 1 open trade per group
CORRELATION_GROUPS = {
    "SPY":   "broad_market",
    "QQQ":   "broad_market",
    "AAPL":  "big_tech",
    "MSFT":  "big_tech",
    "GOOGL": "big_tech",
    "AMZN":  "big_tech",
    "NVDA":  "semiconductors",
    "TSLA":  "high_beta",
    "META":  "high_beta",
}

# Per-symbol minimum flow premium to pass to LLM (below = noise, filter out).
# A global $100k misses TSLA/NVDA/SPY noise — use per-symbol thresholds.
MIN_FLOW_PREMIUM = {
    "SPY":   500_000,
    "QQQ":   300_000,
    "AAPL":  200_000,
    "NVDA":  500_000,
    "MSFT":  200_000,
    "META":  300_000,
    "TSLA":  1_000_000,
    "AMZN":  300_000,
    "GOOGL": 300_000,
}

# Scan settings
SCAN_INTERVAL_MIN = 10

# Hard block thresholds (code enforces before calling LLM)
VIX_MAX              = 30    # block all new trades above this
MAX_OPEN_POSITIONS   = 3     # block when 3 positions already open
EARNINGS_BUFFER_DAYS = 5     # both code and LLM check this
NO_TRADE_OPEN_MIN    = 30    # skip first 30 min of session (9:30–10:00 ET)
NO_TRADE_CLOSE_MIN   = 30    # skip last 30 min of session (3:30–4:00 ET)
STOPOUT_COOLDOWN_HOURS = 24  # no re-entry on same ticker for 24h after stop-loss

# Confidence thresholds
CONFIDENCE_THRESHOLD         = 0.72   # minimum to alert and log paper trade
CONFIDENCE_THRESHOLD_NO_FLOW = 0.85   # raised when no flow exists

# Paper trade position sizing
BASE_NOTIONAL       = 2_000   # $ per trade (paper money)
HIGH_CONF_NOTIONAL  = 3_000   # $ when confidence >= HIGH_CONF_THRESHOLD
HIGH_CONF_THRESHOLD = 0.82

# Paper trade auto-close rules
STOP_LOSS_PCT   = 0.50   # close at 50% loss
TAKE_PROFIT_PCT = 1.00   # close at 100% gain
CLOSE_AT_DTE    = 5      # force-close when 5 DTE remain

# Options contract selection (context_builder picks expiry in this window)
MIN_EXPIRY_DAYS = 14     # fallback minimum DTE when 21–45 window has nothing

# Flow scoring (flow_verifier.py pre-LLM filter)
FLOW_SCORE_SEND_THRESHOLD = 4    # score >= 4 gets sent to LLM
FLOW_SCORE_HIGH_PRIORITY  = 6    # score >= 6 = high priority flag
FLOW_MAX_AGE_MINUTES      = 60   # ignore flow older than 60 min
DARKPOOL_MATCH_WINDOW_MIN = 60   # dark pool ↔ sweep correlation window (minutes)

# Set to True to bypass the flow score gate and call the LLM on every ticker
# using technicals only. Useful for testing the full pipeline without a UW key.
# WARNING: calls both LLMs for all 9 symbols every 10 min — watch OpenRouter rate limits.
BYPASS_FLOW_FILTER = os.getenv("BYPASS_FLOW_FILTER", "false").lower() == "true"
