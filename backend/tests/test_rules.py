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
    assert to_json(EMPTY_CONFIG) == {"dailySpendCapUsd": None, "blockedPaths": [], "blockedCommands": []}
    assert EMPTY_CONFIG == GuardrailConfig(None, ())


def test_config_is_frozen():
    with pytest.raises(Exception):
        EMPTY_CONFIG.blocked_paths = ("x",)


def test_to_json_shape():
    cfg = GuardrailConfig(1.25, (".env",))
    assert to_json(cfg) == {"dailySpendCapUsd": 1.25, "blockedPaths": [".env"], "blockedCommands": []}


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


# ---- v2 9.1: blockedCommands ----

from agentwatch_api.rules import MAX_COMMAND_LEN, MAX_COMMANDS  # noqa: E402
from agentwatch_api.store import item_to_record  # noqa: E402

V1 = {"dailySpendCapUsd": 0.5, "blockedPaths": [".env"]}


def test_v1_body_defaults_blocked_commands_to_empty():
    assert ok(dict(V1)).blocked_commands == ()


def test_blocked_commands_parse_and_keep_order():
    cfg = ok({**V1, "blockedCommands": [r"\brm\s+-rf\b", "sudo", "sudo"]})
    assert cfg.blocked_commands == (r"\brm\s+-rf\b", "sudo", "sudo")


def test_to_json_always_emits_blocked_commands():
    assert to_json(EMPTY_CONFIG)["blockedCommands"] == []
    assert to_json(GuardrailConfig(None, (), ("sudo",)))["blockedCommands"] == ["sudo"]


def test_positional_v1_constructor_still_works():
    assert GuardrailConfig(1.0, (".env",)).blocked_commands == ()


@pytest.mark.parametrize("cmds", ["sudo", None, {"a": 1}, 3])
def test_blocked_commands_not_a_list(cmds):
    bad({**V1, "blockedCommands": cmds}, "blockedCommands")


@pytest.mark.parametrize("cmds", [[""], ["sudo", ""], [1], ["sudo", None]])
def test_blocked_commands_bad_entries(cmds):
    bad({**V1, "blockedCommands": cmds}, "blockedCommands")


def test_blocked_commands_limits():
    assert MAX_COMMANDS == 100 and MAX_COMMAND_LEN == 256
    bad({**V1, "blockedCommands": ["x"] * 101}, "blockedCommands")
    ok({**V1, "blockedCommands": ["x"] * 100})
    bad({**V1, "blockedCommands": ["a" * 257]}, "blockedCommands")
    ok({**V1, "blockedCommands": ["a" * 256]})


@pytest.mark.parametrize("pattern", ["(", "[a-", "*x", "(?P<"])
def test_blocked_commands_must_compile_and_error_is_not_echoed(pattern):
    import re

    e = parse_config({**V1, "blockedCommands": ["sudo", pattern]})
    assert isinstance(e, ValidationError) and e.field == "blockedCommands"
    assert "entry 1" in e.reason
    try:
        re.compile(pattern, re.IGNORECASE)
    except re.error as err:
        assert str(err) not in e.reason  # no re.error text echoed back
        assert err.msg not in e.reason


def test_blocked_commands_compiled_case_insensitive_accepts_flags_free_patterns():
    ok({**V1, "blockedCommands": [r"curl[^|]*\|\s*(ba)?sh", r"(?:^|\s)sudo\b"]})


def test_stored_v1_guardrails_round_trip_through_item_to_record():
    item = {
        "agentId": "bot", "sk": "META", "ownerId": "o", "gsiOwnerId": "o",
        "keyVerifier": "v" * 64, "guardrails": dict(V1), "totalSpendUsd": 0,
    }
    rec = item_to_record(item)
    assert rec.guardrails.blocked_commands == ()
    assert rec.paused is False


# ---- audit fix (PR A): repeat counts that overflow re's limits are a 400, not a 500 ----


@pytest.mark.parametrize("pattern", ["a{4294967296}", "a{99999999999999999999}", "x{1,4294967296}"])
def test_blocked_commands_overflowing_repeat_is_validation_error(pattern):
    r = parse_config({**V1, "blockedCommands": ["sudo", pattern]})
    assert isinstance(r, ValidationError)
    assert r.field == "blockedCommands" and "entry 1" in r.reason
