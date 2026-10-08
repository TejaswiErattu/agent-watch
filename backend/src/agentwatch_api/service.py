"""Service layer: one function per route. Takes (store, creds, ..., now), returns Result.

No AWS and no HTTP here; handlers/api.py translates API Gateway events to these calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from . import auth
from .auth import Credentials
from .rules import GuardrailConfig
from .store import AgentRecord, Store

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
