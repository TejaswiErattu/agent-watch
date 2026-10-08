"""Event schema validation (Req 13, 20.1). Pure functions, no AWS."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

AGENT_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")
OWNER_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
EVENT_ID_RE = re.compile(r"[0-9a-f]{32}")
# [0-9], not \d: \d also matches non-ASCII digits (e.g. Arabic-Indic), which would sort above "META".
TS_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z")
TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

EVENT_TYPES = ("llm_call", "tool_call", "blocked")
REQUIRED = ("agentId", "ownerId", "ts", "eventId", "type")
OPTIONAL = (
    "model", "tool", "target", "inputTokens", "outputTokens", "costUsd",
    "violationType", "attemptedCostUsd", "attemptedPath", "meta",
)
KNOWN_FIELDS = frozenset(REQUIRED + OPTIONAL)
META_MAX_BYTES = 4096
META_MAX_DEPTH = 32  # meta itself is depth 1; lists and objects both count

# Fields kept per type (plus REQUIRED and meta). Anything else known is dropped, not validated.
TYPE_FIELDS = {
    "llm_call": ("model", "inputTokens", "outputTokens"),
    "tool_call": ("tool", "target"),
    ("blocked", "spend_cap"): ("violationType", "attemptedCostUsd"),
    ("blocked", "blocked_path"): ("violationType", "attemptedPath"),
}


class ValidationError(Exception):
    """A 400-worthy problem with one named field."""

    def __init__(self, field: str, reason: str):
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason

    def __eq__(self, other):
        return isinstance(other, ValidationError) and (self.field, self.reason) == (other.field, other.reason)

    def __hash__(self):
        return hash((self.field, self.reason))


@dataclass(frozen=True)
class Event:
    """A validated event. `item` holds the fields to store (no costUsd; the server sets it)."""

    agent_id: str
    owner_id: str
    ts: str
    event_id: str
    type: str
    item: dict = field(default_factory=dict)

    @property
    def sk(self) -> str:
        return f"{self.ts}#{self.event_id}"


def validate_agent_id(s: Any) -> ValidationError | None:
    if not isinstance(s, str) or not AGENT_ID_RE.fullmatch(s):
        return ValidationError("agentId", "must be 1-128 chars of [A-Za-z0-9._-]")
    return None


def _check_ts(ts: str) -> ValidationError | None:
    if not TS_RE.fullmatch(ts):
        return ValidationError("ts", "must be YYYY-MM-DDTHH:MM:SS.mmmZ (UTC)")
    try:
        datetime.strptime(ts, TS_FORMAT)
    except ValueError:
        return ValidationError("ts", "not a real date/time")
    return None


def _scan(value: Any, max_depth: int | None) -> str | None:
    """Iteratively walk a JSON value. Return "nonfinite", "depth", or None.

    Iterative so a hostile, deeply nested body can't raise RecursionError.
    """
    stack = [(value, 1)]
    while stack:
        v, depth = stack.pop()
        if isinstance(v, float) and not math.isfinite(v):
            return "nonfinite"
        if isinstance(v, (dict, list)):
            if max_depth is not None and depth > max_depth:
                return "depth"
            children = v.values() if isinstance(v, dict) else v
            stack.extend((c, depth + 1) for c in children)
    return None


def _validate_common(body: dict) -> ValidationError | None:
    for name in REQUIRED:
        if name not in body:
            return ValidationError(name, "is required")
        if not isinstance(body[name], str):
            return ValidationError(name, "must be a string")

    for name in sorted(body.keys() - KNOWN_FIELDS, key=str):
        return ValidationError(str(name), "unknown field")

    if (e := validate_agent_id(body["agentId"])) is not None:
        return e
    if not OWNER_ID_RE.fullmatch(body["ownerId"]):
        return ValidationError("ownerId", "must be 1-64 chars of [A-Za-z0-9._-]")
    if (e := _check_ts(body["ts"])) is not None:
        return e
    if not EVENT_ID_RE.fullmatch(body["eventId"]):
        return ValidationError("eventId", "must be 32 lowercase hex chars")
    if body["type"] not in EVENT_TYPES:
        return ValidationError("type", f"must be one of {', '.join(EVENT_TYPES)}")

    # NaN/Infinity can't be stored as DynamoDB numbers; reject them in any field, even dropped ones.
    for name in sorted(body, key=str):
        problem = _scan(body[name], META_MAX_DEPTH if name == "meta" else None)
        if problem == "nonfinite":
            return ValidationError(name, "must not contain NaN or Infinity")
        if problem == "depth":
            return ValidationError(name, f"must be nested at most {META_MAX_DEPTH} levels deep")

    meta = body.get("meta", {})
    if not isinstance(meta, dict):
        return ValidationError("meta", "must be an object")
    try:
        size = len(json.dumps(meta, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError):
        return ValidationError("meta", "must be JSON-serializable")
    if size > META_MAX_BYTES:
        return ValidationError("meta", f"must serialize to at most {META_MAX_BYTES} bytes")
    return None


STR_MAX = 1024
VIOLATION_TYPES = ("spend_cap", "blocked_path")


def _req_str(body: dict, name: str, *, allow_empty: bool = False) -> ValidationError | None:
    if name not in body:
        return ValidationError(name, "is required")
    v = body[name]
    if not isinstance(v, str):
        return ValidationError(name, "must be a string")
    if not allow_empty and v == "":
        return ValidationError(name, "must be non-empty")
    if len(v) > STR_MAX:
        return ValidationError(name, f"must be at most {STR_MAX} chars")
    return None


def _req_count(body: dict, name: str) -> ValidationError | None:
    if name not in body:
        return ValidationError(name, "is required")
    v = body[name]
    # bool is a subclass of int; reject it explicitly.
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        return ValidationError(name, "must be an integer >= 0")
    return None


def _own_fields(body: dict) -> dict:
    """Keep REQUIRED, meta, and the fields that belong to this event's type; drop the rest."""
    t = body["type"]
    key = (t, body.get("violationType")) if t == "blocked" else t
    keep = set(REQUIRED) | {"meta"} | set(TYPE_FIELDS.get(key, ("violationType",)))
    return {k: v for k, v in body.items() if k in keep}


def _validate_type_specific(body: dict) -> ValidationError | None:
    """Validate a body already reduced by _own_fields. _req_str enforces the 1024-char cap."""
    t = body["type"]
    if t == "llm_call":
        return _req_str(body, "model") or _req_count(body, "inputTokens") or _req_count(body, "outputTokens")
    if t == "tool_call":
        return _req_str(body, "tool") or _req_str(body, "target", allow_empty=True)
    # blocked
    vt = body.get("violationType")
    if vt not in VIOLATION_TYPES:
        reason = "is required" if "violationType" not in body else f"must be one of {', '.join(VIOLATION_TYPES)}"
        return ValidationError("violationType", reason)
    if vt == "spend_cap":
        if "attemptedCostUsd" not in body:
            return ValidationError("attemptedCostUsd", "is required")
        c = body["attemptedCostUsd"]
        if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or c < 0:
            return ValidationError("attemptedCostUsd", "must be a finite number >= 0")
        return None
    return _req_str(body, "attemptedPath")


def validate_event(body: Any, now: datetime) -> Event | ValidationError:
    """Return an Event, or a ValidationError naming the first bad field.

    `now` is accepted for future clock-skew checks; it is not used yet.
    """
    if not isinstance(body, dict):
        return ValidationError("body", "must be a JSON object")
    if (e := _validate_common(body)) is not None:
        return e
    # Drops client costUsd and any field that belongs to another type before type checks.
    item = _own_fields(body)
    if (e := _validate_type_specific(item)) is not None:
        return e

    item.setdefault("meta", {})
    return Event(
        agent_id=body["agentId"],
        owner_id=body["ownerId"],
        ts=body["ts"],
        event_id=body["eventId"],
        type=body["type"],
        item=item,
    )
