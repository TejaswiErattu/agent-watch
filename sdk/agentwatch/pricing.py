"""Cost math over the server-provided Pricing_Table. No price constants live here (Req 3.8).

The formula must match backend/src/agentwatch_api/pricing.py exactly (Property 1).
"""

from __future__ import annotations

import logging

TOKENS_PER_MTOK = 1_000_000

# Models already warned about. Module-level: "once per model per process" (Req 3.10).
_warned: set[str] = set()
_log = logging.getLogger("agentwatch")


def cost_from_table(table: dict, model: str, in_tok: int, out_tok: int) -> float:
    """USD cost for one call. Unknown model or empty table -> 0.0."""
    p = (table or {}).get("models", {}).get(model)
    if p is None:
        return 0.0
    return round((in_tok * p["inputPerMTokUsd"] + out_tok * p["outputPerMTokUsd"]) / TOKENS_PER_MTOK, 6)


def warn_unknown_model(table: dict, model: str) -> None:
    """Log one warning per unknown model per process. Caller decides whether the table is trustworthy."""
    if model in (table or {}).get("models", {}) or model in _warned:
        return
    _warned.add(model)
    _log.warning("agentwatch: no price for model %r; cost recorded as 0.0", model)
