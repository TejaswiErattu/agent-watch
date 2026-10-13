"""Property 38 (v2). One clause per Violation_Type; later groups add a clause to CLAUSES.

A clause is (draw extra body fields, expected detail lines). The v1 Property 17 test stays untouched.
"""

from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

from agentwatch_api.alerts import _clean, format_alert
from agentwatch_api.validation import Event, validate_event

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

agent_ids = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-",
                    min_size=1, max_size=128)
ts = st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2026, 10, 8, 11)).map(
    lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z")
# Any text, control chars included: the body must escape them.
texts = st.text(min_size=1, max_size=200)
scalars = st.one_of(texts, st.integers(-10**6, 10**6),
                    st.floats(allow_nan=False, allow_infinity=False, width=32))
non_scalars = st.one_of(st.none(), st.booleans(), st.lists(st.integers(), max_size=3),
                        st.dictionaries(st.text(max_size=5), st.integers(), max_size=3))


def _meta_line(key, value):
    """Expected line for a printable meta value, or None when the value must be skipped."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    return f"{key}: {_clean(str(value))}"


# ---- clauses ----

@st.composite
def _blocked_path(draw):
    path = draw(texts.filter(lambda s: s != ""))
    meta = {"tool": draw(texts), "entry": draw(texts)}
    lines = [f"attemptedPath: {_clean(path)}", f"tool: {_clean(meta['tool'])}", f"entry: {_clean(meta['entry'])}"]
    return {"attemptedPath": path, "meta": meta}, lines


@st.composite
def _spend_cap(draw):
    cost = draw(st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False))
    return {"attemptedCostUsd": cost}, [f"attemptedCostUsd: {cost!r}"]


@st.composite
def _paused(draw):
    action = draw(st.sampled_from(["llm_call", "tool_call"]))
    detail_key = "model" if action == "llm_call" else "tool"
    detail = draw(st.one_of(scalars, non_scalars))
    meta = {"action": action, detail_key: detail}
    lines = [f"action: {action}"]
    if (line := _meta_line(detail_key, detail)) is not None:
        lines.append(line)
    return {"meta": meta}, lines


CLAUSES = {
    "blocked_path": _blocked_path,
    "spend_cap": _spend_cap,
    "paused": _paused,
    # 9.2 blocked_command, 12.1 rate_limit, 14.2 secret_redacted, 15.1 blocked_domain
}


@st.composite
def cases(draw):
    vt = draw(st.sampled_from(sorted(CLAUSES)))
    extra, lines = draw(CLAUSES[vt]())
    b = {"agentId": draw(agent_ids), "ownerId": "o", "ts": draw(ts),
         "eventId": draw(st.text("0123456789abcdef", min_size=32, max_size=32)),
         "type": "blocked", "violationType": vt, **extra}
    e = validate_event(b, NOW)
    assert isinstance(e, Event), e
    return e, lines


# Feature: agent-watch-v2, Property 38: Alert content covers every Violation_Type
@settings(max_examples=100)
@given(cases())
def test_alert_content_covers_every_violation_type(case):
    e, expected_lines = case
    subject, body = format_alert(e)
    vt = e.item["violationType"]
    assert len(subject) <= 100 and subject.isascii() and "\n" not in subject
    assert vt in subject
    assert e.agent_id in subject or subject.endswith("...")
    lines = body.splitlines()
    assert f"agentId: {e.agent_id}" in lines
    assert f"violationType: {vt}" in lines
    assert f"ts: {e.ts}" in lines
    assert f"eventId: {e.event_id}" in lines
    for line in expected_lines:
        assert line in lines, (line, lines)
    assert all(line.isprintable() for line in lines)
