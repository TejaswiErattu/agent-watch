"""Lambda entry point for the HTTP API (payload format 2.0). Thin: parse, route, serialize.

All logic lives in service.py. Deps are built once per container and can be replaced in tests.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from .. import service
from ..auth import parse_credentials
from ..service import NullPublisher, Publisher, Result
from ..store import DynamoStore, Store
from ..validation import validate_agent_id

log = logging.getLogger("agentwatch_api")
JSON_HEADERS = {"content-type": "application/json"}
UNAUTHORIZED = {"error": "unauthorized"}


@dataclass
class Deps:
    store: Store
    publisher: Publisher


_deps: Deps | None = None


def _get_deps() -> Deps:
    global _deps
    if _deps is None:
        _deps = Deps(store=DynamoStore(os.environ["TABLE_NAME"]), publisher=NullPublisher())
    return _deps


class BadRequest(Exception):
    pass


def _json_body(event: dict):
    raw = event.get("body")
    if raw is None:
        raise BadRequest("body must be valid JSON")
    try:
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        return json.loads(raw)
    except (ValueError, binascii.Error, UnicodeDecodeError, RecursionError):
        # json.JSONDecodeError is a ValueError; RecursionError covers pathological nesting.
        raise BadRequest("body must be valid JSON") from None


def _agent_id(event: dict) -> str:
    agent_id = (event.get("pathParameters") or {}).get("agentId")
    if not isinstance(agent_id, str):
        raise BadRequest("agentId: is required")
    return agent_id


def _post_events(deps, creds, event):
    now = datetime.now(timezone.utc)
    return service.ingest_event(deps.store, creds, _json_body(event), now, publisher=deps.publisher)


def _get_config(deps, creds, event):
    return service.get_config(deps.store, creds, _agent_id(event))


def _put_config(deps, creds, event):
    return service.put_config(deps.store, creds, _agent_id(event), _json_body(event))


ROUTES = {
    "POST /events": _post_events,
    "GET /agents/{agentId}/config": _get_config,
    "PUT /agents/{agentId}/config": _put_config,
}


def _response(result: Result) -> dict:
    return {"statusCode": result.status, "headers": dict(JSON_HEADERS), "body": json.dumps(result.body)}


def _log_agent_id(event: dict) -> str | None:
    """agentId for the access log: path param, else the event body's agentId if it is valid."""
    agent_id = (event.get("pathParameters") or {}).get("agentId")
    if agent_id is None and event.get("routeKey") == "POST /events":
        try:
            body = _json_body(event)
            agent_id = body.get("agentId") if isinstance(body, dict) else None
        except BadRequest:
            agent_id = None
    return agent_id if isinstance(agent_id, str) and validate_agent_id(agent_id) is None else None


def _request_id(event: dict) -> str | None:
    return (event.get("requestContext") or {}).get("requestId")


def lambda_handler(event, context):
    route = event.get("routeKey", "")
    handler = ROUTES.get(route)
    if handler is None:
        result = Result(404, {"error": "not found"})
    elif (creds := parse_credentials(event.get("headers"))) is None:
        # Gate before any route work: no body parsing, no store access.
        result = Result(401, UNAUTHORIZED)
    else:
        try:
            result = handler(_get_deps(), creds, event)
        except BadRequest as e:
            result = Result(400, {"error": str(e)})
        except Exception as e:
            # Exception text could echo inputs, so log only its type. Never log headers.
            log.error("unhandled error", extra={"route": route, "request_id": _request_id(event),
                                                 "error_type": type(e).__name__})
            result = Result(500, {"error": "internal"})
    log.info("request", extra={"route": route, "agent_id": _log_agent_id(event) if handler else None,
                               "status": result.status, "request_id": _request_id(event)})
    return _response(result)
