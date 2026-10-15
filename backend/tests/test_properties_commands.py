import re

from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.auth import Credentials
from agentwatch_api.rules import EMPTY_CONFIG, GuardrailConfig, to_json
from agentwatch_api.service import get_config, new_record, put_config
from agentwatch_api.store import InMemoryStore

creds_s = st.builds(
    Credentials,
    st.from_regex(r"[A-Za-z0-9._-]{1,20}", fullmatch=True),
    st.from_regex(r"[0-9a-f]{64}", fullmatch=True),
)


def _compiles(p: str) -> bool:
    try:
        re.compile(p, re.IGNORECASE)
        return True
    except re.error:
        return False


# Grammar of valid patterns: words, \s+, \b, alternations, classes.
atom = st.one_of(
    st.from_regex(r"[a-z]{1,8}", fullmatch=True),
    st.sampled_from([r"\s+", r"\b", r"[0-9]", r"(ba)?sh", r"(rm|del)", r"-r?f"]),
)
valid_pattern = st.lists(atom, min_size=1, max_size=6).map("".join).filter(lambda p: len(p) <= 256)
valid_lists = st.lists(valid_pattern, max_size=10)

bad_entry = st.one_of(
    st.just(""),
    st.just("a" * 257),
    st.sampled_from(["(", "[a-", "*x", "(?P<", "a{2,1}", "\\"]),
    st.integers(),
    st.none(),
)


@st.composite
def bad_command_values(draw):
    kind = draw(st.sampled_from(["not_list", "too_many", "bad_entry"]))
    if kind == "not_list":
        return draw(st.one_of(st.text(max_size=5), st.none(), st.integers(), st.dictionaries(st.text(max_size=3), st.integers(), max_size=2)))
    if kind == "too_many":
        return ["x"] * draw(st.integers(101, 150))
    good = draw(st.lists(valid_pattern, max_size=5))
    i = draw(st.integers(0, len(good)))
    return good[:i] + [draw(bad_entry)] + good[i:]


# Feature: agent-watch-v2, Property 34: Invalid command patterns are rejected without side effects
@settings(max_examples=100)
@given(cmds=bad_command_values(), existing=st.booleans(), creds=creds_s)
def test_property_34_invalid_patterns_rejected_without_side_effects(cmds, existing, creds):
    s = InMemoryStore()
    if existing:
        s.create_agent_if_absent(new_record("bot", creds, GuardrailConfig(None, (".env",), ("sudo",))))
    before = s.snapshot()
    body = {"dailySpendCapUsd": None, "blockedPaths": [], "blockedCommands": cmds}
    r = put_config(s, creds, "bot", body)
    assert r.status == 400 and "blockedCommands" in r.body["error"]
    assert s.snapshot() == before


# Feature: agent-watch-v2, Property 34: valid pattern lists round-trip through PUT then GET
@settings(max_examples=100)
@given(cmds=valid_lists, creds=creds_s, preexisting=st.booleans())
def test_property_34_valid_patterns_round_trip(cmds, creds, preexisting):
    assert all(_compiles(p) for p in cmds)
    s = InMemoryStore()
    if preexisting:
        s.create_agent_if_absent(new_record("bot", creds, EMPTY_CONFIG))
    body = {"dailySpendCapUsd": None, "blockedPaths": [], "blockedCommands": cmds}
    r = put_config(s, creds, "bot", body)
    assert r.status == 200 and r.body["guardrails"]["blockedCommands"] == cmds
    g = get_config(s, creds, "bot")
    assert g.body["guardrails"]["blockedCommands"] == cmds
    assert g.body["guardrails"] == to_json(GuardrailConfig(None, (), tuple(cmds)))
