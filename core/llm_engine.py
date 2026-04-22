"""
LLM engine — dual-model analysis with consensus gate and Discord alerts.

Flow per ticker:
  1. Call DeepSeek R1 and GPT-OSS 120B in parallel (separate threads)
  2. Parse both JSON responses
  3. Consensus check:
       Both ENTER + same direction → consensus alert
       Both SKIP                   → no alert (quiet agreement)
       One ENTER / one SKIP        → no alert (disagreement)
       One model fails             → single-model fallback (threshold raised to 0.80)
  4. If consensus alert → send Discord embed → return result

Public API:
  analyze(ticker, messages, flow_score) → AnalysisResult
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from config.settings import (
    OPENROUTER_API_KEY_DEEPSEEK,
    OPENROUTER_API_KEY_GPT,
    LLM_DEEPSEEK,
    LLM_GPT,
    LLM_FALLBACK,
    LLM_REQUIRE_CONSENSUS,
    CONFIDENCE_THRESHOLD,
    CONFIDENCE_THRESHOLD_NO_FLOW,
    DISCORD_WEBHOOK_URL,
)

log = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
REQUEST_TIMEOUT     = 60    # seconds per model call
SINGLE_MODEL_THRESHOLD = 0.80   # raised threshold when only one model responds


@dataclass
class ModelResult:
    model:      str
    raw:        dict         = field(default_factory=dict)
    reasoning:  str          = ""
    error:      str          = ""
    ok:         bool         = False

    @property
    def action(self) -> str:
        return self.raw.get("action", "SKIP")

    @property
    def direction(self) -> str:
        return self.raw.get("direction", "")

    @property
    def confidence(self) -> float:
        return float(self.raw.get("confidence", 0.0))

    @property
    def alert(self) -> bool:
        return bool(self.raw.get("alert", False))


@dataclass
class AnalysisResult:
    ticker:          str
    consensus:       bool      = False
    alert:           bool      = False
    direction:       str       = ""
    deepseek:        Optional[ModelResult] = None
    gpt:             Optional[ModelResult] = None
    block_reason:    str       = ""
    discord_sent:    bool      = False


# ------------------------------------------------------------------ #
# Main entry point

def analyze(ticker: str, messages: list[dict], flow_score: int) -> AnalysisResult:
    """
    Run both models in parallel and return an AnalysisResult.

    Args:
        ticker:     symbol being analyzed
        messages:   [system, user] message list from context_builder
        flow_score: integer flow score (used for logging context only)
    """
    result = AnalysisResult(ticker=ticker)

    # ── Parallel model calls ─────────────────────────────────────────
    ds_result: list[ModelResult] = [ModelResult(model=LLM_DEEPSEEK)]
    gpt_result: list[ModelResult] = [ModelResult(model=LLM_GPT)]

    def call_deepseek():
        ds_result[0] = _call_model(LLM_DEEPSEEK, OPENROUTER_API_KEY_DEEPSEEK, messages)

    def call_gpt():
        gpt_result[0] = _call_model(LLM_GPT, OPENROUTER_API_KEY_GPT, messages)

    t1 = threading.Thread(target=call_deepseek, daemon=True)
    t2 = threading.Thread(target=call_gpt, daemon=True)
    t1.start(); t2.start()
    t1.join(timeout=REQUEST_TIMEOUT + 5)
    t2.join(timeout=REQUEST_TIMEOUT + 5)

    result.deepseek = ds_result[0]
    result.gpt      = gpt_result[0]

    _log_results(ticker, result.deepseek, result.gpt, flow_score)

    # ── Consensus logic ──────────────────────────────────────────────
    both_ok = result.deepseek.ok and result.gpt.ok

    if both_ok and LLM_REQUIRE_CONSENSUS:
        result.consensus, result.alert, result.direction = _consensus(
            result.deepseek, result.gpt
        )
    elif not both_ok:
        # one model failed — try fallback for that slot, then single-model
        working = result.deepseek if result.deepseek.ok else result.gpt
        if working.ok:
            threshold = SINGLE_MODEL_THRESHOLD
            result.consensus = False
            result.alert     = working.alert and working.confidence >= threshold
            result.direction = working.direction
            if result.alert:
                log.info(
                    "%s single-model alert (%.2f ≥ %.2f) via %s",
                    ticker, working.confidence, threshold, working.model,
                )
    else:
        # LLM_REQUIRE_CONSENSUS is False — use DeepSeek as primary
        primary = result.deepseek if result.deepseek.ok else result.gpt
        result.alert     = primary.alert
        result.direction = primary.direction

    # ── Discord alert ────────────────────────────────────────────────
    if result.alert:
        result.discord_sent = _send_discord_alert(ticker, result)

    return result


# ------------------------------------------------------------------ #
# Single model call

def _call_model(model: str, api_key: str, messages: list[dict]) -> ModelResult:
    if not api_key:
        return ModelResult(model=model, error=f"No API key configured for {model}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://github.com/RohithGSVV/Try-ade",  # OpenRouter attribution
    }

    for attempt in range(2):
        body = {
            "model":    model,
            "messages": messages if attempt == 0 else messages + [{
                "role":    "user",
                "content": "Your last response was not valid JSON. "
                           "Return ONLY the JSON object with no other text.",
            }],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        try:
            resp = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=body,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            choice  = data["choices"][0]["message"]
            content = choice.get("content") or ""

            # DeepSeek R1 exposes chain-of-thought in reasoning_content; GPT-OSS does not
            reasoning = choice.get("reasoning_content") or ""

            parsed = _parse_json(content)
            if parsed is None:
                log.warning("%s attempt %d: JSON parse failed", model, attempt + 1)
                continue

            return ModelResult(
                model=model,
                raw=parsed,
                reasoning=reasoning,
                ok=True,
            )

        except Exception as exc:
            log.error("%s attempt %d error: %s", model, attempt + 1, exc)
            if attempt == 0:
                time.sleep(2)

    return ModelResult(model=model, error=f"{model} failed after 2 attempts")


def _parse_json(text: str) -> Optional[dict]:
    text = text.strip()
    # strip any accidental markdown fences
    if text.startswith("```"):
        text = text.split("```")[1].strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ------------------------------------------------------------------ #
# Consensus logic

def _consensus(ds: ModelResult, gpt: ModelResult) -> tuple[bool, bool, str]:
    """
    Returns (consensus_reached, alert_fires, direction).
    Both models must agree on direction AND both must say ENTER.
    """
    same_direction = (
        ds.direction and gpt.direction and ds.direction == gpt.direction
    )
    both_enter = ds.action == "ENTER" and gpt.action == "ENTER"
    both_alert = ds.alert and gpt.alert

    if same_direction and both_enter and both_alert:
        return True, True, ds.direction

    return False, False, ""


# ------------------------------------------------------------------ #
# Discord alert

def _send_discord_alert(ticker: str, result: AnalysisResult) -> bool:
    if not DISCORD_WEBHOOK_URL:
        log.warning("DISCORD_WEBHOOK_URL not set — alert not sent")
        return False

    ds  = result.deepseek
    gpt = result.gpt

    # Pick primary for contract details (prefer DeepSeek if available)
    primary = ds if (ds and ds.ok) else gpt
    if not primary:
        return False

    raw = primary.raw
    direction  = raw.get("direction", "").upper()
    trade_type = raw.get("trade_type", "").upper()
    strike     = raw.get("strike", "N/A")
    expiry     = raw.get("expiry", "N/A")
    entry_est  = raw.get("entry_price_estimate", "N/A")
    dte        = raw.get("dte", "N/A")
    thesis     = raw.get("thesis_summary", "")
    flow_ver   = raw.get("flow_verification", "")
    key_sigs   = raw.get("key_signals", [])
    risk_facs  = raw.get("risk_factors", [])

    emoji = "🟢" if direction == "BULLISH" else "🔴"
    tag   = "CONSENSUS" if result.consensus else "SINGLE MODEL"

    ds_line  = (
        f"DeepSeek R1   | conf: {ds.confidence:.2f} | {ds.raw.get('flow_verification','')}"
        if ds and ds.ok else "DeepSeek R1   | ❌ failed"
    )
    gpt_line = (
        f"GPT-OSS 120B  | conf: {gpt.confidence:.2f} | {gpt.raw.get('flow_verification','')}"
        if gpt and gpt.ok else "GPT-OSS 120B  | ❌ failed"
    )

    signals_str = ", ".join(key_sigs[:4]) if key_sigs else "—"
    risks_str   = ", ".join(risk_facs[:3]) if risk_facs else "—"

    content = (
        f"{emoji} **{tag} ALERT — {ticker} {direction} {trade_type} "
        f"${strike} {expiry}**\n"
        f"```\n"
        f"{ds_line}\n"
        f"{gpt_line}\n"
        f"{'─'*48}\n"
        f"Thesis : {thesis}\n"
        f"Flow   : {flow_ver}\n"
        f"Entry  : ${entry_est} ask  |  DTE: {dte}\n"
        f"Signals: {signals_str}\n"
        f"Risks  : {risks_str}\n"
        f"```"
    )

    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": content},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("Discord alert sent for %s", ticker)
        return True
    except Exception as exc:
        log.error("Discord alert failed: %s", exc)
        return False


# ------------------------------------------------------------------ #
# Logging

def _log_results(ticker: str, ds: ModelResult, gpt: ModelResult, flow_score: int):
    def _fmt(r: ModelResult) -> str:
        if not r.ok:
            return f"ERR({r.error[:40]})"
        return f"conf={r.confidence:.2f} action={r.action} dir={r.direction}"

    log.info(
        "%s | score=%d | DeepSeek[%s] | GPT[%s]",
        ticker, flow_score, _fmt(ds), _fmt(gpt),
    )

    # Log DeepSeek chain-of-thought if available (unique to R1)
    if ds.ok and ds.reasoning:
        log.debug("%s DeepSeek reasoning:\n%s", ticker, ds.reasoning[:800])
