"""Event_Store: one DynamoDB table, PK agentId, SK sk.

Items:
- Agent_Record: sk == "META", carries ownerId, gsiOwnerId (sparse GSI key), keyVerifier, guardrails,
  firstSeen?, lastSeen?, model?, totalSpendUsd.
- Event: sk == f"{ts}#{eventId}". No keyVerifier, no gsiOwnerId (Req 4.6, 14.3).

InMemoryStore mirrors DynamoStore's conditional semantics and is used by every service test.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from .rules import GuardrailConfig, parse_config, to_json

META_SK = "META"
RecordResult = Literal["stored", "duplicate", "forbidden"]


def event_sk(ts: str, event_id: str) -> str:
    return f"{ts}#{event_id}"


@dataclass
class AgentRecord:
    agent_id: str
    owner_id: str
    key_verifier: str
    guardrails: GuardrailConfig
    first_seen: str | None = None
    last_seen: str | None = None
    model: str | None = None
    total_spend_usd: float = 0.0


def record_to_item(r: AgentRecord) -> dict:
    item = {
        "agentId": r.agent_id,
        "sk": META_SK,
        "ownerId": r.owner_id,
        "gsiOwnerId": r.owner_id,
        "keyVerifier": r.key_verifier,
        "guardrails": to_json(r.guardrails),
        "totalSpendUsd": r.total_spend_usd,
    }
    # Absent attribute means null (Unreported_Agent).
    for attr, val in (("firstSeen", r.first_seen), ("lastSeen", r.last_seen), ("model", r.model)):
        if val is not None:
            item[attr] = val
    return item


def item_to_record(item: dict) -> AgentRecord:
    cfg = parse_config(item["guardrails"])
    if not isinstance(cfg, GuardrailConfig):  # stored data is always valid; fail loudly if not
        raise ValueError(f"corrupt guardrails on {item['agentId']}: {cfg}")
    return AgentRecord(
        agent_id=item["agentId"],
        owner_id=item["ownerId"],
        key_verifier=item["keyVerifier"],
        guardrails=cfg,
        first_seen=item.get("firstSeen"),
        last_seen=item.get("lastSeen"),
        model=item.get("model"),
        total_spend_usd=float(item.get("totalSpendUsd", 0.0)),
    )


@runtime_checkable
class Store(Protocol):
    def get_agent(self, agent_id: str) -> AgentRecord | None: ...

    def create_agent_if_absent(self, record: AgentRecord) -> bool: ...

    def put_config(self, agent_id: str, cfg: GuardrailConfig, key_verifier: str) -> bool: ...

    def record_event(self, event, cost: float, key_verifier: str) -> RecordResult: ...

    def bump_last_seen(self, agent_id: str, ts: str) -> None: ...

    def query_events(
        self,
        agent_id: str,
        *,
        ascending: bool = True,
        limit: int = 50,
        type_filter: str | None = None,
        start_after: str | None = None,
    ) -> tuple[list[dict], str | None]: ...

    def list_by_owner(self, owner_id: str) -> list[AgentRecord]: ...

    def sum_spend(self, agent_id: str, start_sk: str, end_sk: str) -> float: ...


class InMemoryStore:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    # ---- agent records ----

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        item = self.items.get((agent_id, META_SK))
        return item_to_record(item) if item is not None else None

    def create_agent_if_absent(self, record: AgentRecord) -> bool:
        key = (record.agent_id, META_SK)
        if key in self.items:  # attribute_not_exists(sk)
            return False
        self.items[key] = record_to_item(record)
        return True

    def put_config(self, agent_id: str, cfg: GuardrailConfig, key_verifier: str) -> bool:
        item = self.items.get((agent_id, META_SK))
        if item is None or item["keyVerifier"] != key_verifier:  # keyVerifier = :kv
            return False
        item["guardrails"] = to_json(cfg)
        return True

    # ---- events and queries (tasks 1.9, 1.10) ----

    def record_event(self, event, cost: float, key_verifier: str) -> RecordResult:
        raise NotImplementedError

    def bump_last_seen(self, agent_id: str, ts: str) -> None:
        raise NotImplementedError

    def query_events(self, agent_id, *, ascending=True, limit=50, type_filter=None, start_after=None):
        raise NotImplementedError

    def list_by_owner(self, owner_id: str) -> list[AgentRecord]:
        raise NotImplementedError

    def sum_spend(self, agent_id: str, start_sk: str, end_sk: str) -> float:
        raise NotImplementedError

    def snapshot(self) -> dict:
        """Deep copy of all items, for 'store unchanged' assertions in tests."""
        return copy.deepcopy(self.items)
