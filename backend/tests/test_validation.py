from datetime import datetime, timezone

import pytest

from agentwatch_api.validation import Event, ValidationError, validate_agent_id, validate_event

NOW = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
EID = "0123456789abcdef0123456789abcdef"


def base(**over):
    body = {
        "agentId": "study-bot",
        "ownerId": "tejaswi",
        "ts": "2026-10-08T11:59:59.123Z",
        "eventId": EID,
        "type": "tool_call",
        "tool": "read_file",
        "target": "notes.md",
        "meta": {},
    }
    body.update(over)
    return body


def err(result):
    assert isinstance(result, ValidationError), result
    return result


def test_valid_event_returns_event():
    ev = validate_event(base(), NOW)
    assert isinstance(ev, Event)
    assert ev.agent_id == "study-bot"
    assert ev.owner_id == "tejaswi"
    assert ev.ts == "2026-10-08T11:59:59.123Z"
    assert ev.event_id == EID
    assert ev.type == "tool_call"
    assert ev.sk == f"2026-10-08T11:59:59.123Z#{EID}"


def test_body_not_a_dict():
    assert err(validate_event(["nope"], NOW)).field == "body"


@pytest.mark.parametrize("field", ["agentId", "ownerId", "ts", "eventId", "type"])
def test_missing_required_field_named(field):
    body = base()
    del body[field]
    e = err(validate_event(body, NOW))
    assert e.field == field
    assert field in str(e)


@pytest.mark.parametrize("field", ["agentId", "ownerId", "ts", "eventId", "type"])
def test_required_field_must_be_string(field):
    assert err(validate_event(base(**{field: 123}), NOW)).field == field


@pytest.mark.parametrize(
    "ts",
    [
        "2026-10-08T11:59:59Z",  # no millis
        "2026-10-08T11:59:59.1234Z",  # too many digits
        "2026-10-08 11:59:59.123Z",  # space
        "2026-10-08T11:59:59.123",  # no Z
        "2026-10-08T11:59:59.123+00:00",
        "2026-13-08T11:59:59.123Z",  # month 13
        "2026-02-30T11:59:59.123Z",  # not a real date
        "",
    ],
)
def test_bad_ts(ts):
    assert err(validate_event(base(ts=ts), NOW)).field == "ts"


@pytest.mark.parametrize(
    "eid",
    [EID.upper(), EID[:-1], EID + "0", "g" * 32, "0123456789abcdef-123456789abcdef", ""],
)
def test_bad_event_id(eid):
    assert err(validate_event(base(eventId=eid), NOW)).field == "eventId"


@pytest.mark.parametrize("aid", ["", "a" * 129, "has space", "slash/no", "ünï"])
def test_bad_agent_id(aid):
    assert err(validate_event(base(agentId=aid), NOW)).field == "agentId"
    assert isinstance(validate_agent_id(aid), ValidationError)


@pytest.mark.parametrize("aid", ["a", "a" * 128, "Bad-Bot_1.v2"])
def test_good_agent_id(aid):
    assert validate_agent_id(aid) is None


@pytest.mark.parametrize("oid", ["", "o" * 65, "has space"])
def test_bad_owner_id(oid):
    assert err(validate_event(base(ownerId=oid), NOW)).field == "ownerId"


def test_unknown_type():
    assert err(validate_event(base(type="file_read"), NOW)).field == "type"


def test_unknown_top_level_field():
    e = err(validate_event(base(surprise=1), NOW))
    assert e.field == "surprise"


def test_meta_must_be_object():
    assert err(validate_event(base(meta="x"), NOW)).field == "meta"


def test_meta_over_4kb():
    assert err(validate_event(base(meta={"x": "a" * 4096}), NOW)).field == "meta"


def test_meta_just_under_4kb_ok():
    assert isinstance(validate_event(base(meta={"x": "a" * 4000}), NOW), Event)


def test_meta_optional():
    body = base()
    del body["meta"]
    ev = validate_event(body, NOW)
    assert isinstance(ev, Event)
    assert ev.item["meta"] == {}


# ---- 1.5 type-specific validation ----


def llm(**over):
    body = base(type="llm_call", model="claude-haiku-4-5", inputTokens=10, outputTokens=5)
    del body["tool"], body["target"]
    body.update(over)
    return body


def blocked(vt="blocked_path", **over):
    body = base(type="blocked", violationType=vt)
    del body["tool"], body["target"]
    if vt == "blocked_path":
        body["attemptedPath"] = ".env"
    elif vt == "spend_cap":
        body["attemptedCostUsd"] = 0.01
    body.update(over)
    return body


def drop(body, key):
    body = dict(body)
    del body[key]
    return body


def test_valid_llm_call():
    assert isinstance(validate_event(llm(), NOW), Event)


@pytest.mark.parametrize("field", ["model", "inputTokens", "outputTokens"])
def test_llm_call_missing_field(field):
    assert err(validate_event(drop(llm(), field), NOW)).field == field


@pytest.mark.parametrize("bad", [-1, 1.5, "10", True, None])
@pytest.mark.parametrize("field", ["inputTokens", "outputTokens"])
def test_llm_call_bad_token_count(field, bad):
    assert err(validate_event(llm(**{field: bad}), NOW)).field == field


def test_llm_call_zero_tokens_ok():
    assert isinstance(validate_event(llm(inputTokens=0, outputTokens=0), NOW), Event)


def test_llm_call_model_must_be_nonempty_string():
    assert err(validate_event(llm(model=""), NOW)).field == "model"
    assert err(validate_event(llm(model=5), NOW)).field == "model"


@pytest.mark.parametrize("field", ["tool", "target"])
def test_tool_call_missing_field(field):
    assert err(validate_event(drop(base(), field), NOW)).field == field


def test_tool_call_tool_nonempty():
    assert err(validate_event(base(tool=""), NOW)).field == "tool"


def test_tool_call_empty_target_ok():
    # A tool with no args reports an empty target.
    assert isinstance(validate_event(base(target=""), NOW), Event)


def test_valid_blocked_path():
    assert isinstance(validate_event(blocked("blocked_path"), NOW), Event)


def test_valid_spend_cap():
    assert isinstance(validate_event(blocked("spend_cap"), NOW), Event)


def test_spend_cap_zero_cost_ok():
    assert isinstance(validate_event(blocked("spend_cap", attemptedCostUsd=0), NOW), Event)


def test_blocked_missing_violation_type():
    assert err(validate_event(drop(blocked(), "violationType"), NOW)).field == "violationType"


def test_blocked_bad_violation_type():
    assert err(validate_event(blocked(violationType="nope"), NOW)).field == "violationType"


def test_spend_cap_missing_cost():
    body = drop(blocked("spend_cap"), "attemptedCostUsd")
    assert err(validate_event(body, NOW)).field == "attemptedCostUsd"


@pytest.mark.parametrize("bad", [-0.01, True, False, "0.1", None, float("nan"), float("inf")])
def test_spend_cap_bad_cost(bad):
    e = err(validate_event(blocked("spend_cap", attemptedCostUsd=bad), NOW))
    assert e.field == "attemptedCostUsd"


def test_blocked_path_missing_path():
    body = drop(blocked("blocked_path"), "attemptedPath")
    assert err(validate_event(body, NOW)).field == "attemptedPath"


@pytest.mark.parametrize("bad", ["", 5, None])
def test_blocked_path_bad_path(bad):
    e = err(validate_event(blocked("blocked_path", attemptedPath=bad), NOW))
    assert e.field == "attemptedPath"


@pytest.mark.parametrize(
    "make,field",
    [
        (lambda: base(tool="t" * 1025), "tool"),
        (lambda: base(target="t" * 1025), "target"),
        (lambda: llm(model="m" * 1025), "model"),
        (lambda: blocked("blocked_path", attemptedPath="p" * 1025), "attemptedPath"),
    ],
)
def test_string_fields_capped_at_1024(make, field):
    assert err(validate_event(make(), NOW)).field == field


def test_string_fields_at_1024_ok():
    assert isinstance(validate_event(base(tool="t" * 1024, target="x" * 1024), NOW), Event)


@pytest.mark.parametrize("make", [base, llm, lambda: blocked("spend_cap")])
def test_client_cost_is_dropped(make):
    ev = validate_event(make() | {"costUsd": 999.0}, NOW)
    assert isinstance(ev, Event)
    assert "costUsd" not in ev.item


def test_client_cost_dropped_even_if_garbage():
    ev = validate_event(base(costUsd="free!"), NOW)
    assert isinstance(ev, Event)
    assert "costUsd" not in ev.item
