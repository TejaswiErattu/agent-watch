"""The single source of model prices (Req 3). Never hardcode prices elsewhere.

Prices are USD per million tokens, standard on-demand tier, checked 2026-10-08:
- Anthropic API: https://www.anthropic.com/news/claude-haiku-4-5 ($1 in / $5 out)
- Bedrock IDs: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html
  Bedrock price assumed equal to Anthropic list price; confirm on https://aws.amazon.com/bedrock/pricing/
Lookup is exact-match on the model ID; unknown models cost 0.0.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok_usd: float
    output_per_mtok_usd: float


_HAIKU_4_5 = ModelPrice(input_per_mtok_usd=1.0, output_per_mtok_usd=5.0)

PRICING: dict[str, ModelPrice] = {
    # Bedrock base model ID (not invokable on-demand for this model, but may appear in logs)
    "anthropic.claude-haiku-4-5-20251001-v1:0": _HAIKU_4_5,
    # Bedrock US geo cross-Region inference profile (demo BEDROCK_MODEL_ID)
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": _HAIKU_4_5,
    # Anthropic API (demo ANTHROPIC_MODEL_ID) and its alias
    "claude-haiku-4-5-20251001": _HAIKU_4_5,
    "claude-haiku-4-5": _HAIKU_4_5,
}


def pricing_table() -> dict:
    """The Pricing_Table JSON sent to the SDK in Config_Response. Returns a fresh copy."""
    return {
        "models": {
            mid: {"inputPerMTokUsd": p.input_per_mtok_usd, "outputPerMTokUsd": p.output_per_mtok_usd}
            for mid, p in PRICING.items()
        }
    }


def cost_from_table(table: dict, model: str, in_tok: int, out_tok: int) -> float:
    """Same formula as sdk/agentwatch/pricing.py (Property 1)."""
    p = table.get("models", {}).get(model)
    if p is None:
        return 0.0
    return round((in_tok * p["inputPerMTokUsd"] + out_tok * p["outputPerMTokUsd"]) / 1_000_000, 6)


def estimate_cost(model: str, in_tok: int, out_tok: int) -> float:
    return cost_from_table(pricing_table(), model, in_tok, out_tok)


def format_cost(x: float) -> str:
    return f"{x:.6f}"


def parse_cost(s: str) -> float:
    return float(s)
