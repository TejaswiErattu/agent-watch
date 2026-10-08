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

log = logging.getLogger("agentwatch_api")
JSON_HEADERS = {"content-type": "application/json"}


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


def lambda_handler(event, context):
    route = event.get("routeKey", "")
    handler = ROUTES.get(route)
    if handler is None:
        return _response(Result(404, {"error": "not found"}))
    try:
        creds = parse_credentials(event.get("headers"))
        result = handler(_get_deps(), creds, event)
    except BadRequest as e:
        result = Result(400, {"error": str(e)})
    except Exception:
        log.exception("unhandled error route=%s", route)
        result = Result(500, {"error": "internal"})
    return _response(result)
