"""Cost math over the server-provided Pricing_Table. No price constants live here (Req 3.8).

The formula must match backend/src/agentwatch_api/pricing.py exactly (Property 1).
"""

from __future__ import annotations

TOKENS_PER_MTOK = 1_000_000


def cost_from_table(table: dict, model: str, in_tok: int, out_tok: int) -> float:
    """USD cost for one call. Unknown model or empty table -> 0.0."""
    p = (table or {}).get("models", {}).get(model)
    if p is None:
        return 0.0
    return round((in_tok * p["inputPerMTokUsd"] + out_tok * p["outputPerMTokUsd"]) / TOKENS_PER_MTOK, 6)
