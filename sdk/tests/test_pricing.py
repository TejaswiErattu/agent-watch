import ast
from pathlib import Path

from agentwatch.pricing import cost_from_table

TABLE = {"models": {"m": {"inputPerMTokUsd": 3.0, "outputPerMTokUsd": 15.0}}}


def test_known_model_cost():
    # 1000 * 3 + 500 * 15 = 10500 per million tokens
    assert cost_from_table(TABLE, "m", 1000, 500) == 0.0105


def test_unknown_model_and_empty_table_cost_zero():
    assert cost_from_table(TABLE, "other", 1000, 500) == 0.0
    assert cost_from_table({}, "m", 1000, 500) == 0.0
    assert cost_from_table({"models": {}}, "m", 1000, 500) == 0.0


def test_zero_tokens_cost_zero():
    assert cost_from_table(TABLE, "m", 0, 0) == 0.0


def test_no_numeric_price_literals_in_sdk_pricing():
    src = (Path(__file__).resolve().parent.parent / "agentwatch" / "pricing.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for v in node.values:
                assert not (isinstance(v, ast.Constant) and isinstance(v.value, float)), "price literal in dict"
        if isinstance(node, ast.Constant) and isinstance(node.value, float) and node.value != 0.0:
            raise AssertionError(f"float literal {node.value!r} in sdk pricing.py")
