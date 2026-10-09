"""Unit tests for list_inventory (service layer, no AWS)."""

from agentwatch_api.auth import Credentials
from agentwatch_api.rules import EMPTY_CONFIG
from agentwatch_api.service import list_inventory, new_record
from agentwatch_api.store import InMemoryStore

INVENTORY_FIELDS = {"agentId", "ownerId", "model", "firstSeen", "lastSeen", "totalSpendUsd"}

CREDS_A = Credentials(owner_id="alice", key_hash="a" * 64)
CREDS_B = Credentials(owner_id="alice", key_hash="b" * 64)  # same owner, different key


def test_no_matching_records_returns_empty_list():
    s = InMemoryStore()
    r = list_inventory(s, CREDS_A)
    assert r.status == 200
    assert r.body == {"agents": []}


def test_two_owners_sharing_owner_id_see_only_their_own():
    s = InMemoryStore()
    s.create_agent_if_absent(new_record("bot-a", CREDS_A, EMPTY_CONFIG))
    s.create_agent_if_absent(new_record("bot-b", CREDS_B, EMPTY_CONFIG))

    ra = list_inventory(s, CREDS_A)
    assert {a["agentId"] for a in ra.body["agents"]} == {"bot-a"}

    rb = list_inventory(s, CREDS_B)
    assert {a["agentId"] for a in rb.body["agents"]} == {"bot-b"}


def test_unreported_agent_shows_nulls_and_zero_spend():
    s = InMemoryStore()
    s.create_agent_if_absent(new_record("fresh", CREDS_A, EMPTY_CONFIG))
    (item,) = list_inventory(s, CREDS_A).body["agents"]
    assert item["model"] is None
    assert item["firstSeen"] is None
    assert item["lastSeen"] is None
    assert item["totalSpendUsd"] == 0.0


def test_items_have_all_fields_and_no_key_verifier():
    s = InMemoryStore()
    s.create_agent_if_absent(new_record("bot-a", CREDS_A, EMPTY_CONFIG))
    (item,) = list_inventory(s, CREDS_A).body["agents"]
    assert set(item) == INVENTORY_FIELDS
    assert "keyVerifier" not in item
