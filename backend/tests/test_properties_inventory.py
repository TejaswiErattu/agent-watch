"""Property 13: Inventory returns exactly the matching records."""

from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.auth import Credentials, matches
from agentwatch_api.rules import EMPTY_CONFIG
from agentwatch_api.service import list_inventory, new_record
from agentwatch_api.store import InMemoryStore

INVENTORY_FIELDS = {"agentId", "ownerId", "model", "firstSeen", "lastSeen", "totalSpendUsd"}

owner_ids = st.sampled_from(["alice", "bob", "carol"])
key_hashes = st.sampled_from([c * 64 for c in "0123"])
agent_ids = st.from_regex(r"[A-Za-z0-9._-]{1,16}", fullmatch=True)
creds_s = st.builds(Credentials, owner_ids, key_hashes)
population = st.lists(st.tuples(agent_ids, creds_s), max_size=12, unique_by=lambda t: t[0])


# Feature: agent-watch, Property 13: Inventory returns exactly the matching records
@settings(max_examples=200)
@given(records=population, who=creds_s)
def test_inventory_returns_exactly_matching_records(records, who):
    s = InMemoryStore()
    for agent_id, creds in records:
        s.create_agent_if_absent(new_record(agent_id, creds, EMPTY_CONFIG))

    expected = {agent_id for agent_id, creds in records if matches(new_record(agent_id, creds, EMPTY_CONFIG), who)}

    agents = list_inventory(s, who).body["agents"]
    assert {a["agentId"] for a in agents} == expected
    for a in agents:
        assert set(a) == INVENTORY_FIELDS
