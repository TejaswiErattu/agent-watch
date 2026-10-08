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
