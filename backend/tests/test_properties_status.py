"""Property 31 (agent-watch-v2): status round trip, no-create reads, and inventory mirror."""

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.auth import Credentials
from agentwatch_api.rules import GuardrailConfig
from agentwatch_api.service import get_status, list_inventory, new_record, put_status
from agentwatch_api.store import InMemoryStore

agent_ids = st.from_regex(r"[A-Za-z0-9._-]{1,128}", fullmatch=True)
creds_s = st.builds(
    Credentials,
    st.from_regex(r"[A-Za-z0-9._-]{1,64}", fullmatch=True),
    st.from_regex(r"[0-9a-f]{64}", fullmatch=True),
)
configs = st.builds(
    GuardrailConfig,
    st.one_of(st.none(), st.floats(0, 1000, allow_nan=False, allow_infinity=False)),
    st.lists(st.text(min_size=1, max_size=20), max_size=5).map(tuple),
)
BASE = datetime(2026, 10, 14, tzinfo=timezone.utc)
times = st.integers(0, 10**10).map(lambda us: BASE + timedelta(microseconds=us))
json_values = st.one_of(st.none(), st.integers(), st.floats(allow_nan=False), st.text(max_size=5),
                        st.lists(st.integers(), max_size=2))
bad_bodies = st.one_of(
    json_values,  # not an object
    st.just({}),
    st.fixed_dictionaries({"paused": json_values}),  # non-bool value (bool is not in json_values)
    st.fixed_dictionaries({"paused": st.booleans()}).flatmap(  # an extra key
        lambda d: st.dictionaries(st.text(min_size=1, max_size=5).filter(lambda k: k != "paused"),
                                  json_values, min_size=1, max_size=2).map(lambda extra: {**d, **extra})
    ),
)


def _other(creds):
    return Credentials(creds.owner_id, "0" * 64 if creds.key_hash != "0" * 64 else "1" * 64)


# Feature: agent-watch-v2, Property 31: Status round trip, no-create reads, and inventory mirror
@settings(max_examples=100)
@given(agent_id=agent_ids, creds=creds_s, cfg=st.one_of(st.none(), configs),
       puts=st.lists(st.tuples(st.booleans(), times), max_size=6), bad=bad_bodies)
def test_status_round_trip_no_create_and_inventory_mirror(agent_id, creds, cfg, puts, bad):
    s = InMemoryStore()
    # No record: GET is not paused and creates nothing.
    g = get_status(s, creds, agent_id)
    assert g.status == 200 and g.body == {"agentId": agent_id, "paused": False, "pausedAt": None}
    assert s.items == {}

    if cfg is not None:
        s.create_agent_if_absent(new_record(agent_id, creds, cfg))

    for paused, now in puts:
        before = s.get_agent(agent_id)
        r = put_status(s, creds, agent_id, {"paused": paused}, now)
        assert r.status == 200
        g = get_status(s, creds, agent_id)
        assert g.body == r.body
        assert g.body["paused"] is paused
        assert (g.body["pausedAt"] is not None) == paused
        rec = s.get_agent(agent_id)
        if before is not None:  # status PUTs never touch guardrails
            assert rec.guardrails == before.guardrails
        (item,) = [a for a in list_inventory(s, creds).body["agents"] if a["agentId"] == agent_id]
        assert item["paused"] is paused

    # Non-matching credentials and bad bodies change nothing.
    snap = s.snapshot()
    if s.get_agent(agent_id) is not None:
        assert put_status(s, _other(creds), agent_id, {"paused": True}, BASE).status == 403
        assert s.snapshot() == snap
    r = put_status(s, creds, agent_id, bad, BASE)
    assert r.status == 400 and "paused" in r.body["error"]
    assert s.snapshot() == snap
