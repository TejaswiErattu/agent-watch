"""Cost math over the server-provided Pricing_Table. No price constants live here (Req 3.8).

The formula must match backend/src/agentwatch_api/pricing.py exactly (Property 1).
"""

from __future__ import annotations

import json
import logging
import math

TOKENS_PER_MTOK = 1_000_000
# Bedrock converse may omit inferenceConfig.maxTokens; assume a conservative output budget (design).
DEFAULT_MAX_TOKENS = 4096
CHARS_PER_TOKEN = 4

# Models already warned about. Module-level: "once per model per process" (Req 3.10).
_warned: set[str] = set()
_log = logging.getLogger("agentwatch")


def cost_from_table(table: dict, model: str, in_tok: int, out_tok: int) -> float:
    """USD cost for one call. Unknown model or empty table -> 0.0."""
    p = (table or {}).get("models", {}).get(model)
    if p is None:
        return 0.0
    return round((in_tok * p["inputPerMTokUsd"] + out_tok * p["outputPerMTokUsd"]) / TOKENS_PER_MTOK, 6)


def estimate_input_tokens(request: dict) -> int:
    """ceil(len(json.dumps(messages + system)) / 4). Rough, no tokenizer dependency (Req 7.5)."""
    messages = list(request.get("messages") or [])
    system = request.get("system") or []
    parts = messages + (list(system) if isinstance(system, (list, tuple)) else [system])
    return math.ceil(len(json.dumps(parts, default=str)) / CHARS_PER_TOKEN)


def max_output_tokens(request: dict) -> int:
    """Anthropic `max_tokens` or Bedrock `inferenceConfig.maxTokens`, else DEFAULT_MAX_TOKENS."""
    v = request.get("max_tokens")
    if v is None:
        v = (request.get("inferenceConfig") or {}).get("maxTokens")
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        return DEFAULT_MAX_TOKENS
    return v


def estimate_pending_cost(table: dict, model: str, request: dict, max_tokens: int) -> float:
    """Worst-case cost of a call before it runs: estimated input plus the full output budget."""
    return cost_from_table(table, model, estimate_input_tokens(request), max_tokens)


def warn_unknown_model(table: dict, model: str) -> None:
    """Log one warning per unknown model per process. Caller decides whether the table is trustworthy."""
    if model in (table or {}).get("models", {}) or model in _warned:
        return
    _warned.add(model)
    _log.warning("agentwatch: no price for model %r; cost recorded as 0.0", model)
