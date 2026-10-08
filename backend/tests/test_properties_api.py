import json
import logging

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agentwatch_api.auth import key_verifier
from agentwatch_api.handlers import api
from agentwatch_api.service import NullPublisher
from agentwatch_api.store import META_SK, InMemoryStore

owners = st.from_regex(r"[A-Za-z0-9._-]{1,64}", fullmatch=True)
hashes = st.from_regex(r"[0-9a-f]{64}", fullmatch=True)
agent_ids = st.sampled_from(["bot", "bot2", "other.agent"])


@st.composite
def operations(draw, key_hashes):
    kind = draw(st.sampled_from(["event", "get", "put", "bad_put"]))
    agent_id = draw(agent_ids)
    key_hash = draw(st.sampled_from(key_hashes))
    owner = draw(st.sampled_from(["tejaswi", "someone"]))
    headers = {"x-agentwatch-owner": owner, "x-agentwatch-key-hash": key_hash}
    if kind == "event":
        i = draw(st.integers(0, 20))
        body = {"agentId": agent_id, "ownerId": owner, "ts": f"2026-10-08T10:00:{i:02d}.000Z",
                "eventId": f"{i:032x}", "type": "llm_call", "model": "claude-haiku-4-5",
                "inputTokens": i, "outputTokens": i, "meta": {"note": draw(st.text(max_size=10))}}
        return {"routeKey": "POST /events", "headers": headers, "body": json.dumps(body)}
    route = "GET /agents/{agentId}/config" if kind == "get" else "PUT /agents/{agentId}/config"
    ev = {"routeKey": route, "headers": headers, "pathParameters": {"agentId": agent_id}}
    if kind == "put":
        ev["body"] = json.dumps({"dailySpendCapUsd": None, "blockedPaths": [".env"]})
    elif kind == "bad_put":
        ev["body"] = json.dumps({"dailySpendCapUsd": -1, "blockedPaths": []})
    return ev


@st.composite
def scenarios(draw):
    key_hashes = draw(st.lists(hashes, min_size=1, max_size=3, unique=True))
    ops = draw(st.lists(operations(key_hashes), min_size=1, max_size=10))
    return key_hashes, ops


@pytest.fixture
def capture():
    handler = _ListHandler()
    logger = logging.getLogger("agentwatch_api")
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(old_level)


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(self.format(record) + " " + json.dumps(record.__dict__, default=str))


# Feature: agent-watch, Property 15: Secret hygiene in the API
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios())
def test_secret_hygiene(scenario, capture, monkeypatch):
    key_hashes, ops = scenario
    capture.lines.clear()
    store = InMemoryStore()
    monkeypatch.setattr(api, "_deps", api.Deps(store=store, publisher=NullPublisher()))
    secrets = set(key_hashes) | {key_verifier(h) for h in key_hashes}
    responses = [api.lambda_handler(ev, None)["body"] for ev in ops]

    for (_, sk), item in store.items.items():
        if sk != META_SK:
            assert "keyVerifier" not in item
        dumped = json.dumps(item, default=str)
        for h in key_hashes:
            assert h not in dumped  # the Key_Hash itself is never stored
    for text in responses + capture.lines:
        for s in secrets:
            assert s not in text
