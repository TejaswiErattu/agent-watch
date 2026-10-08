import pytest

from agentwatch_api.rules import EMPTY_CONFIG, GuardrailConfig, parse_config, to_json
from agentwatch_api.validation import ValidationError


def ok(obj):
    cfg = parse_config(obj)
    assert isinstance(cfg, GuardrailConfig), cfg
    return cfg


def bad(obj, field):
    e = parse_config(obj)
    assert isinstance(e, ValidationError), e
    assert e.field == field
    assert field in str(e)


def test_valid_config_parses():
    cfg = ok({"dailySpendCapUsd": 0.5, "blockedPaths": [".env", "~/.ssh"]})
    assert cfg.daily_spend_cap_usd == 0.5
    assert cfg.blocked_paths == (".env", "~/.ssh")


def test_integer_cap_ok_and_zero_ok():
    assert ok({"dailySpendCapUsd": 2, "blockedPaths": []}).daily_spend_cap_usd == 2
    assert ok({"dailySpendCapUsd": 0, "blockedPaths": []}).daily_spend_cap_usd == 0


def test_null_cap_ok():
    assert ok({"dailySpendCapUsd": None, "blockedPaths": []}).daily_spend_cap_usd is None


def test_order_and_duplicates_kept():
    assert ok({"dailySpendCapUsd": None, "blockedPaths": ["b", "a", "b"]}).blocked_paths == ("b", "a", "b")


def test_empty_config():
    assert to_json(EMPTY_CONFIG) == {"dailySpendCapUsd": None, "blockedPaths": []}
    assert EMPTY_CONFIG == GuardrailConfig(None, ())


def test_config_is_frozen():
    with pytest.raises(Exception):
        EMPTY_CONFIG.blocked_paths = ("x",)


def test_to_json_shape():
    cfg = GuardrailConfig(1.25, (".env",))
    assert to_json(cfg) == {"dailySpendCapUsd": 1.25, "blockedPaths": [".env"]}


def test_not_an_object():
    bad([], "body")
    bad(None, "body")


@pytest.mark.parametrize("cap", [True, False, "0.5", -0.01, float("nan"), float("inf"), float("-inf"), [1]])
def test_bad_cap(cap):
    bad({"dailySpendCapUsd": cap, "blockedPaths": []}, "dailySpendCapUsd")


@pytest.mark.parametrize("paths", ["/a", None, {"a": 1}, 3])
def test_paths_not_a_list(paths):
    bad({"dailySpendCapUsd": None, "blockedPaths": paths}, "blockedPaths")


@pytest.mark.parametrize("paths", [[""], [".env", ""], [1], [".env", None]])
def test_paths_bad_entries(paths):
    bad({"dailySpendCapUsd": None, "blockedPaths": paths}, "blockedPaths")


def test_paths_over_100_entries():
    bad({"dailySpendCapUsd": None, "blockedPaths": ["x"] * 101}, "blockedPaths")
    ok({"dailySpendCapUsd": None, "blockedPaths": ["x"] * 100})


def test_path_entry_over_1024_chars():
    bad({"dailySpendCapUsd": None, "blockedPaths": ["p" * 1025]}, "blockedPaths")
    ok({"dailySpendCapUsd": None, "blockedPaths": ["p" * 1024]})


def test_unknown_key():
    bad({"dailySpendCapUsd": None, "blockedPaths": [], "extra": 1}, "extra")


@pytest.mark.parametrize("missing", ["dailySpendCapUsd", "blockedPaths"])
def test_missing_key(missing):
    obj = {"dailySpendCapUsd": None, "blockedPaths": []}
    del obj[missing]
    bad(obj, missing)
