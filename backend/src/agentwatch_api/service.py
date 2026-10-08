"""Service layer: one function per route. Takes (store, creds, ..., now), returns Result.

No AWS and no HTTP here; handlers/api.py translates API Gateway events to these calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from . import auth
from .auth import Credentials
from .pricing import estimate_cost
from .rules import EMPTY_CONFIG, GuardrailConfig
from .store import AgentRecord, Store, round_cost
from .validation import Event, ValidationError, validate_event

FORBIDDEN = {"error": "forbidden"}


@dataclass(frozen=True)
class Result:
    status: int
    body: dict


@runtime_checkable
class Publisher(Protocol):
    def publish(self, subject: str, body: str) -> None: ...


class NullPublisher:
    """No-op publisher until SNS alerts are wired in (task 4.2)."""

    def publish(self, subject: str, body: str) -> None:
        return None


def new_record(agent_id: str, creds: Credentials, cfg: GuardrailConfig) -> AgentRecord:
    """A fresh Agent_Record bound to these Credentials. Stores the verifier, never the Key_Hash."""
    return AgentRecord(
        agent_id=agent_id,
        owner_id=creds.owner_id,
        key_verifier=auth.key_verifier(creds.key_hash),
        guardrails=cfg,
    )


def authorize(store: Store, agent_id: str, creds: Credentials) -> AgentRecord | None | Literal["forbidden"]:
    """None if no record; the record if Credentials match; "forbidden" otherwise."""
    rec = store.get_agent(agent_id)
    if rec is None:
        return None
    return rec if auth.matches(rec, creds) else "forbidden"


def _bad(e: ValidationError) -> Result:
    return Result(400, {"error": str(e)})


def event_cost(event: Event) -> float:
    """Server-side cost. Only llm_call events cost anything; client costUsd is never used."""
    if event.type != "llm_call":
        return 0.0
    return round_cost(estimate_cost(event.item["model"], event.item["inputTokens"], event.item["outputTokens"]))


def ingest_event(store: Store, creds: Credentials, body, now: datetime, publisher: Publisher | None = None) -> Result:
    """POST /events. Steps follow the design's ingest_event list."""
    # 1. validate
    event = validate_event(body, now)
    if isinstance(event, ValidationError):
        return _bad(event)
    if event.owner_id != creds.owner_id:
        return _bad(ValidationError("ownerId", "must match the credentials ownerId"))

    # 2. authorize / register
    if authorize(store, event.agent_id, creds) is None:
        store.create_agent_if_absent(new_record(event.agent_id, creds, EMPTY_CONFIG))

    # 3-4. server-side cost, transactional write
    cost = event_cost(event)
    store.record_event(event, cost, auth.key_verifier(creds.key_hash))

    # 6. lastSeen keeps the later ts
    store.bump_last_seen(event.agent_id, event.ts)

    # 8. respond
    return Result(200, {"eventId": event.event_id, "costUsd": cost, "duplicate": False})
