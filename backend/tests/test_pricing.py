import pytest

from agentwatch_api import pricing
from agentwatch_api.pricing import (
    PRICING,
    cost_from_table,
    estimate_cost,
    format_cost,
    parse_cost,
    pricing_table,
)


def test_table_has_bedrock_crossregion_and_anthropic_ids():
    models = pricing_table()["models"]
    assert any(m.startswith("anthropic.claude-") for m in models)
    assert any(m.startswith("us.anthropic.claude-") for m in models)
    assert any(m.startswith("claude-") for m in models)


def test_table_shape_matches_pricing():
    models = pricing_table()["models"]
    assert set(models) == set(PRICING)
    for mid, entry in models.items():
        assert set(entry) == {"inputPerMTokUsd", "outputPerMTokUsd"}
        assert entry["inputPerMTokUsd"] == PRICING[mid].input_per_mtok_usd
        assert entry["outputPerMTokUsd"] == PRICING[mid].output_per_mtok_usd


def test_pricing_table_is_a_copy():
    t = pricing_table()
    t["models"].clear()
    assert pricing_table()["models"]


def test_unknown_model_costs_zero():
    assert estimate_cost("not-a-model", 1000, 1000) == 0.0


def test_zero_tokens_cost_zero():
    for model in PRICING:
        assert estimate_cost(model, 0, 0) == 0.0


def test_hand_computed_example():
    table = {"models": {"m": {"inputPerMTokUsd": 1.0, "outputPerMTokUsd": 5.0}}}
    # 1200 * 1 / 1e6 + 300 * 5 / 1e6 = 0.0012 + 0.0015 = 0.0027
    assert cost_from_table(table, "m", 1200, 300) == pytest.approx(0.0027)


def test_estimate_cost_matches_table_math():
    model = next(iter(PRICING))
    p = PRICING[model]
    expected = round((1000 * p.input_per_mtok_usd + 500 * p.output_per_mtok_usd) / 1_000_000, 6)
    assert estimate_cost(model, 1000, 500) == expected


def test_cost_from_table_empty_table():
    assert cost_from_table({}, "anything", 10, 10) == 0.0


def test_format_and_parse_cost():
    assert format_cost(0.0027) == "0.002700"
    assert parse_cost("0.002700") == pytest.approx(0.0027)


def test_module_exposes_model_price():
    mp = pricing.ModelPrice(input_per_mtok_usd=1.0, output_per_mtok_usd=2.0)
    assert mp.input_per_mtok_usd == 1.0
