"""Service layer: one function per route. Takes (store, creds, ..., now), returns Result.

No AWS and no HTTP here; handlers/api.py translates API Gateway events to these calls.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from . import auth
from .alerts import publish_alert
from .auth import Credentials
from .pricing import estimate_cost, pricing_table
from .rules import EMPTY_CONFIG, GuardrailConfig, parse_config, to_json
from .store import AgentRecord, Store, round_cost
from .validation import Event, ValidationError, validate_agent_id, validate_event

FORBIDDEN = {"error": "forbidden"}


@dataclass(frozen=True)
class Result:
    status: int
    body: dict


@runtime_checkable
class Publisher(Protocol):
    def publish(self, subject: str, body: str) -> None: ...


class NullPublisher:
    """No-op publisher, for tests and local runs without SNS."""

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


def authorize_or_register(
    store: Store, agent_id: str, creds: Credentials, cfg: GuardrailConfig
) -> AgentRecord | Literal["forbidden", "created"]:
    """Authorize; if no record exists, create one bound to creds with `cfg`.

    Returns "created" when this call created the record. If the create loses a race,
    the winner's record is re-read and authorized like any other.
    """
    found = authorize(store, agent_id, creds)
    if found is not None:
        return found
    if store.create_agent_if_absent(new_record(agent_id, creds, cfg)):
        return "created"
    again = authorize(store, agent_id, creds)
    if again is None:  # created then deleted between calls; never expected
        raise RuntimeError(f"agent record for {agent_id!r} vanished after a lost create race")
    return again


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

    # 2. authorize / register (a lost create race re-reads and authorizes again)
    if authorize_or_register(store, event.agent_id, creds, EMPTY_CONFIG) == "forbidden":
        return Result(403, FORBIDDEN)

    # 3-4. server-side cost, transactional write
    cost = event_cost(event)
    outcome = store.record_event(event, cost, auth.key_verifier(creds.key_hash))

    # 5. verifier changed mid-flight: nothing was written
    if outcome == "forbidden":
        return Result(403, FORBIDDEN)

    # A duplicate reports what was stored the first time, not the resubmitted body's cost.
    if outcome == "duplicate":
        stored = store.get_event_cost(event.agent_id, event.sk)
        cost = cost if stored is None else stored

    # 6. lastSeen keeps the later ts (a no-op for duplicates)
    store.bump_last_seen(event.agent_id, event.ts)

    # 7. alert only for a newly stored blocked event; a publish failure never fails the request
    if event.type == "blocked" and outcome == "stored" and publisher is not None:
        publish_alert(publisher, event)

    # 8. respond
    return Result(200, {"eventId": event.event_id, "costUsd": cost, "duplicate": outcome == "duplicate"})


def _inventory_item(rec: AgentRecord) -> dict:
    """InventoryItem view: public fields only, never the keyVerifier (Req 5.6)."""
    return {
        "agentId": rec.agent_id,
        "ownerId": rec.owner_id,
        "model": rec.model,
        "firstSeen": rec.first_seen,
        "lastSeen": rec.last_seen,
        "totalSpendUsd": rec.total_spend_usd,
    }


def list_inventory(store: Store, creds: Credentials) -> Result:
    """GET /agents. Every record for this owner whose key also matches; empty list if none."""
    agents = [_inventory_item(rec) for rec in store.list_by_owner(creds.owner_id) if auth.matches(rec, creds)]
    return Result(200, {"agents": agents})


TIMELINE_FIELDS = (
    "ts", "eventId", "type", "model", "tool", "target", "inputTokens",
    "outputTokens", "costUsd", "violationType", "attemptedCostUsd", "attemptedPath", "meta",
)
EVENT_SK_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z#[0-9a-f]{32}"
)


def encode_cursor(sk: str) -> str:
    """base64url JSON of the LastEvaluatedKey sk (Req 20.5)."""
    return base64.urlsafe_b64encode(json.dumps({"sk": sk}).encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> str | None:
    """Return the event SK a cursor points at, or None if it is undecodable or not an event SK."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        sk = json.loads(raw)["sk"]
    except (binascii.Error, ValueError, KeyError, TypeError):
        return None
    if not isinstance(sk, str) or not EVENT_SK_RE.fullmatch(sk):
        return None
    return sk


def _parse_timeline_query(query: dict) -> tuple[dict, None] | tuple[None, Result]:
    """Validate order/limit/type/cursor. Return (parsed, None) or (None, 400 Result)."""
    order = query.get("order", "asc")
    if order not in ("asc", "desc"):
        return None, _bad(ValidationError("order", "must be asc or desc"))

    raw_limit = query.get("limit", "50")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return None, _bad(ValidationError("limit", "must be an integer 1..100"))
    if not 1 <= limit <= 100:
        return None, _bad(ValidationError("limit", "must be an integer 1..100"))

    type_filter = query.get("type")
    if type_filter is not None and type_filter not in ("llm_call", "tool_call", "blocked"):
        return None, _bad(ValidationError("type", "must be llm_call, tool_call, or blocked"))

    start_after = None
    if (cursor := query.get("cursor")) is not None:
        start_after = _decode_cursor(cursor)
        if start_after is None:
            return None, _bad(ValidationError("cursor", "is not a valid timeline cursor"))

    return {"ascending": order == "asc", "limit": limit,
            "type_filter": type_filter, "start_after": start_after}, None


def _timeline_item(stored: dict) -> dict:
    """Project a stored event to a TimelineItem; absent fields become null."""
    return {name: stored.get(name) for name in TIMELINE_FIELDS}


def get_timeline(store: Store, creds: Credentials, agent_id: str, query: dict) -> Result:
    """GET /agents/{agentId}/events. Missing agent returns an empty list and creates nothing."""
    if (e := validate_agent_id(agent_id)) is not None:
        return _bad(e)
    parsed, err = _parse_timeline_query(query)
    if err is not None:
        return err

    found = authorize(store, agent_id, creds)
    if found == "forbidden":
        return Result(403, FORBIDDEN)
    if found is None:
        return Result(200, {"events": [], "nextCursor": None})

    items, last_sk = store.query_events(
        agent_id,
        ascending=parsed["ascending"],
        limit=parsed["limit"],
        type_filter=parsed["type_filter"],
        start_after=parsed["start_after"],
    )
    events = [_timeline_item(i) for i in items]
    next_cursor = encode_cursor(last_sk) if last_sk is not None else None
    return Result(200, {"events": events, "nextCursor": next_cursor})


def get_config(store: Store, creds: Credentials, agent_id: str) -> Result:
    """GET /agents/{agentId}/config. A missing record returns the empty config and creates nothing."""
    if (e := validate_agent_id(agent_id)) is not None:
        return _bad(e)
    found = authorize(store, agent_id, creds)
    if found == "forbidden":
        return Result(403, FORBIDDEN)
    cfg = EMPTY_CONFIG if found is None else found.guardrails
    return Result(200, {"guardrails": to_json(cfg), "pricing": pricing_table()})


def put_config(store: Store, creds: Credentials, agent_id: str, body) -> Result:
    """PUT /agents/{agentId}/config. Full replace; registers the agent if it has no record."""
    if (e := validate_agent_id(agent_id)) is not None:
        return _bad(e)
    cfg = parse_config(body)
    if isinstance(cfg, ValidationError):
        return _bad(cfg)
    found = authorize_or_register(store, agent_id, creds, cfg)
    if found == "forbidden":
        return Result(403, FORBIDDEN)
    # On "created" the record already holds cfg; otherwise write it under keyVerifier = :kv.
    if found != "created" and not store.put_config(agent_id, cfg, auth.key_verifier(creds.key_hash)):
        return Result(403, FORBIDDEN)  # verifier replaced mid-flight
    return Result(200, {"guardrails": to_json(cfg)})
