import base64
import json

import pytest

from agentwatch_api.alerts import SnsPublisher
from agentwatch_api.handlers import api
from agentwatch_api.rules import to_json, GuardrailConfig
from agentwatch_api.service import NullPublisher
from agentwatch_api.store import InMemoryStore

H = "a" * 64
HEADERS = {"X-Agentwatch-Owner": "tejaswi", "X-Agentwatch-Key-Hash": H}
TS = "2026-10-08T10:00:00.000Z"
CFG = {"dailySpendCapUsd": 1.0, "blockedPaths": [".env"]}


@pytest.fixture
def store(monkeypatch):
    s = InMemoryStore()
    monkeypatch.setattr(api, "_deps", api.Deps(store=s, publisher=NullPublisher()))
    return s


def http_event(route, body=None, agent_id=None, headers=HEADERS, raw_body=None, b64=False):
    ev = {
        "version": "2.0",
        "routeKey": route,
        "headers": {k.lower(): v for k, v in headers.items()},
        "requestContext": {"requestId": "req-1", "http": {"method": (route.split() or ["GET"])[0]}},
        "isBase64Encoded": b64,
    }
    if agent_id is not None:
        ev["pathParameters"] = {"agentId": agent_id}
    if raw_body is not None:
        ev["body"] = raw_body
    elif body is not None:
        text = json.dumps(body)
        ev["body"] = base64.b64encode(text.encode()).decode() if b64 else text
    return ev


def call(ev):
    resp = api.lambda_handler(ev, None)
    assert resp["headers"]["content-type"] == "application/json"
    return resp["statusCode"], json.loads(resp["body"])


def event_body(eid="0" * 32):
    return {"agentId": "bot", "ownerId": "tejaswi", "ts": TS, "eventId": eid,
            "type": "tool_call", "tool": "read_file", "target": "x"}


def test_post_events_reaches_ingest(store):
    status, body = call(http_event("POST /events", event_body()))
    assert status == 200 and body == {"eventId": "0" * 32, "costUsd": 0.0, "duplicate": False}
    assert store.get_agent("bot") is not None


def test_post_events_base64_body(store):
    status, _ = call(http_event("POST /events", event_body(), b64=True))
    assert status == 200


def test_put_then_get_config(store):
    status, body = call(http_event("PUT /agents/{agentId}/config", CFG, agent_id="bot"))
    # A v1 body (no blockedCommands) is accepted; the response always carries the key (Req 28.3).
    assert status == 200 and body == {"guardrails": {**CFG, "blockedCommands": []}}
    status, body = call(http_event("GET /agents/{agentId}/config", agent_id="bot"))
    assert status == 200 and body["guardrails"] == {**CFG, "blockedCommands": []} and "models" in body["pricing"]


def test_get_config_missing_agent(store):
    status, body = call(http_event("GET /agents/{agentId}/config", agent_id="ghost"))
    assert status == 200 and body["guardrails"] == {"dailySpendCapUsd": None, "blockedPaths": [], "blockedCommands": []}
    assert store.items == {}


def test_get_spend_route(store):
    call(http_event("POST /events", event_body()))
    status, body = call(http_event("GET /agents/{agentId}/spend", agent_id="bot"))
    assert status == 200
    assert body["agentId"] == "bot" and body["rollingSpendUsd"] == 0.0
    assert set(body) == {"agentId", "rollingSpendUsd", "windowStart", "windowEnd"}


def test_get_spend_missing_agent_creates_nothing(store):
    status, body = call(http_event("GET /agents/{agentId}/spend", agent_id="ghost"))
    assert status == 200 and body["rollingSpendUsd"] == 0.0
    assert store.items == {}


@pytest.mark.parametrize("raw", ["{not json", "", "[1,", "{" * 100000 + "}" * 100000])
@pytest.mark.parametrize("route,agent_id", [("POST /events", None), ("PUT /agents/{agentId}/config", "bot")])
def test_invalid_json_400(store, raw, route, agent_id):
    status, body = call(http_event(route, raw_body=raw, agent_id=agent_id))
    assert status == 400 and "JSON" in body["error"]
    assert store.items == {}


def test_missing_body_400(store):
    status, body = call(http_event("POST /events"))
    assert status == 400


def test_bad_base64_400(store):
    status, _ = call(http_event("POST /events", raw_body="%%%not-b64", b64=True))
    assert status == 400


def test_missing_path_param_400(store):
    status, body = call(http_event("GET /agents/{agentId}/config"))
    assert status == 400 and "agentId" in body["error"]


@pytest.mark.parametrize("route", ["GET /nope", "DELETE /agents/{agentId}/config", "$default", ""])
def test_unknown_route_404(store, route):
    ev = http_event(route, agent_id="bot")
    status, body = call(ev)
    assert status == 404 and body == {"error": "not found"}


def test_unexpected_exception_500(monkeypatch):
    class Boom(InMemoryStore):
        def get_agent(self, agent_id):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(api, "_deps", api.Deps(store=Boom(), publisher=NullPublisher()))
    status, body = call(http_event("GET /agents/{agentId}/config", agent_id="bot"))
    assert status == 500 and body == {"error": "internal"}


def test_deps_built_lazily_once_from_env(monkeypatch):
    built = []

    class FakeDynamo(InMemoryStore):
        def __init__(self, table_name):
            super().__init__()
            built.append(table_name)

    monkeypatch.setattr(api, "_deps", None)
    monkeypatch.setattr(api, "DynamoStore", FakeDynamo)
    monkeypatch.setenv("TABLE_NAME", "agentwatch-table")
    monkeypatch.setenv("TOPIC_ARN", "arn:aws:sns:us-west-2:123456789012:alerts")
    call(http_event("GET /agents/{agentId}/config", agent_id="bot"))
    call(http_event("GET /agents/{agentId}/config", agent_id="bot"))
    assert built == ["agentwatch-table"]
    assert isinstance(api._deps.publisher, SnsPublisher)
    assert api._deps.publisher.topic_arn == "arn:aws:sns:us-west-2:123456789012:alerts"


WEBHOOK = "https://discord.com/api/webhooks/1/SECRETTOKEN"  # synthetic


def _build_deps(monkeypatch, webhook):
    monkeypatch.setattr(api, "_deps", None)
    monkeypatch.setattr(api, "DynamoStore", lambda name: InMemoryStore())
    monkeypatch.setenv("TABLE_NAME", "t")
    monkeypatch.setenv("TOPIC_ARN", "arn:aws:sns:us-west-2:123456789012:alerts")
    if webhook is None:
        monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    else:
        monkeypatch.setenv("ALERT_WEBHOOK_URL", webhook)
    return api._get_deps()


def test_deps_with_webhook_fan_out_to_sns_and_webhook(monkeypatch):
    from agentwatch_api.alerts import MultiPublisher, WebhookPublisher
    d = _build_deps(monkeypatch, WEBHOOK)
    assert isinstance(d.publisher, MultiPublisher)
    sns, wh = d.publisher.publishers
    assert isinstance(sns, SnsPublisher) and sns.topic_arn.endswith(":alerts")
    assert isinstance(wh, WebhookPublisher)


@pytest.mark.parametrize("webhook", [None, "", "   "])
def test_deps_without_webhook_sns_only(monkeypatch, webhook):
    d = _build_deps(monkeypatch, webhook)
    assert isinstance(d.publisher, SnsPublisher)


def test_webhook_url_never_logged_by_handler(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    _build_deps(monkeypatch, WEBHOOK)
    call(http_event("GET /agents/{agentId}/config", agent_id="bot"))
    assert "SECRETTOKEN" not in caplog.text


def test_existing_config_returned_through_handler(store):
    from agentwatch_api.service import new_record
    from agentwatch_api.auth import Credentials

    cfg = GuardrailConfig(None, ("~/.ssh",))
    store.create_agent_if_absent(new_record("bot", Credentials("tejaswi", H), cfg))
    status, body = call(http_event("GET /agents/{agentId}/config", agent_id="bot"))
    assert status == 200 and body["guardrails"] == to_json(cfg)


# ---- 2.7 401 gate and secret-safe logging ----

import logging  # noqa: E402

ROUTES = [
    ("POST /events", None),
    ("GET /agents/{agentId}/config", "bot"),
    ("PUT /agents/{agentId}/config", "bot"),
]
BAD_HEADERS = [
    {},
    {"X-Agentwatch-Owner": "tejaswi"},
    {"X-Agentwatch-Key-Hash": H},
    {"X-Agentwatch-Owner": "has space", "X-Agentwatch-Key-Hash": H},
    {"X-Agentwatch-Owner": "tejaswi", "X-Agentwatch-Key-Hash": H.upper()},
    {"X-Agentwatch-Owner": "tejaswi", "X-Agentwatch-Key-Hash": "a" * 63},
]


@pytest.mark.parametrize("headers", BAD_HEADERS)
@pytest.mark.parametrize("route,agent_id", ROUTES)
def test_missing_or_malformed_credentials_401_before_any_work(store, route, agent_id, headers):
    # Even an invalid body must not be parsed before the 401.
    ev = http_event(route, raw_body="{not json", agent_id=agent_id, headers=headers)
    status, body = call(ev)
    assert status == 401 and body == {"error": "unauthorized"}
    assert store.items == {}


def test_no_headers_key_at_all_401(store):
    ev = http_event("POST /events", event_body())
    del ev["headers"]
    assert call(ev) == (401, {"error": "unauthorized"})


def test_forbidden_through_handler(store):
    call(http_event("PUT /agents/{agentId}/config", CFG, agent_id="bot"))
    snap = store.snapshot()
    other = {"X-Agentwatch-Owner": "tejaswi", "X-Agentwatch-Key-Hash": "b" * 64}
    for route, agent_id in ROUTES:
        body = event_body() if route == "POST /events" else CFG
        assert call(http_event(route, body, agent_id=agent_id, headers=other)) == (403, {"error": "forbidden"})
    assert store.snapshot() == snap


def test_logs_route_agent_status_request_id_only(store, caplog):
    caplog.set_level(logging.DEBUG)
    call(http_event("PUT /agents/{agentId}/config", CFG, agent_id="bot"))
    recs = [r for r in caplog.records if r.name == "agentwatch_api"]
    assert len(recs) == 1
    r = recs[0]
    assert (r.route, r.agent_id, r.status, r.request_id) == ("PUT /agents/{agentId}/config", "bot", 200, "req-1")
    text = caplog.text
    assert H not in text and "x-agentwatch" not in text.lower()


def test_post_events_logs_agent_id_from_body(store, caplog):
    caplog.set_level(logging.INFO)
    call(http_event("POST /events", event_body()))
    (r,) = [r for r in caplog.records if r.name == "agentwatch_api"]
    assert r.agent_id == "bot" and r.status == 200


def test_500_log_has_no_secrets(monkeypatch, caplog):
    class Boom(InMemoryStore):
        def get_agent(self, agent_id):
            raise RuntimeError(f"kaboom with {H}")  # hostile: a secret inside the exception

    monkeypatch.setattr(api, "_deps", api.Deps(store=Boom(), publisher=NullPublisher()))
    caplog.set_level(logging.DEBUG)
    status, _ = call(http_event("GET /agents/{agentId}/config", agent_id="bot"))
    assert status == 500
    assert H not in caplog.text


# ---- group 2 review fixes ----


def test_agentwatch_logger_level_is_info():
    assert logging.getLogger("agentwatch_api").level == logging.INFO


class NoBodyEvent(dict):
    """An API Gateway event whose body must never be touched."""

    def get(self, key, default=None):
        assert key != "body", "body read on a 401"
        return super().get(key, default)

    def __getitem__(self, key):
        assert key != "body", "body read on a 401"
        return super().__getitem__(key)


@pytest.mark.parametrize("route,agent_id", ROUTES)
def test_401_never_reads_body(store, route, agent_id):
    ev = NoBodyEvent(http_event(route, event_body(), agent_id=agent_id, headers={}))
    assert call(ev) == (401, {"error": "unauthorized"})


def test_401_logs_no_agent_id(store, caplog):
    caplog.set_level(logging.INFO)
    call(http_event("POST /events", event_body(), headers={}))
    (r,) = [r for r in caplog.records if r.name == "agentwatch_api"]
    assert r.status == 401 and r.agent_id is None


def test_post_body_parsed_once(store, monkeypatch):
    calls = []
    real = api._json_body

    def counting(ev):
        calls.append(1)
        return real(ev)

    monkeypatch.setattr(api, "_json_body", counting)
    status, _ = call(http_event("POST /events", event_body()))
    assert status == 200 and len(calls) == 1


# ---- v2 8.2: status routes ----

STATUS_ROUTES = [("GET /agents/{agentId}/status", None), ("PUT /agents/{agentId}/status", {"paused": True})]


def test_route_table_has_exactly_eight_entries():
    assert set(api.ROUTES) == {
        "POST /events", "GET /agents", "GET /agents/{agentId}/events",
        "GET /agents/{agentId}/config", "PUT /agents/{agentId}/config",
        "GET /agents/{agentId}/spend",
        "GET /agents/{agentId}/status", "PUT /agents/{agentId}/status",
    }
    assert len(api.ROUTES) == 8


def test_get_status_missing_agent_creates_nothing(store):
    status, body = call(http_event("GET /agents/{agentId}/status", agent_id="ghost"))
    assert (status, body) == (200, {"agentId": "ghost", "paused": False, "pausedAt": None})
    assert store.items == {}


def test_put_then_get_status(store):
    status, body = call(http_event("PUT /agents/{agentId}/status", {"paused": True}, agent_id="bot"))
    assert status == 200 and body["paused"] is True and body["agentId"] == "bot"
    assert isinstance(body["pausedAt"], str) and body["pausedAt"].endswith("Z")
    assert call(http_event("GET /agents/{agentId}/status", agent_id="bot")) == (200, body)
    status, body = call(http_event("PUT /agents/{agentId}/status", {"paused": False}, agent_id="bot"))
    assert (status, body) == (200, {"agentId": "bot", "paused": False, "pausedAt": None})


def test_put_status_routes_to_service_with_utc_now(store, monkeypatch):
    seen = {}

    def fake_put_status(st, creds, agent_id, body, now):
        seen.update(agent_id=agent_id, body=body, now=now, owner=creds.owner_id)
        return api.Result(200, {"ok": True})

    monkeypatch.setattr(api.service, "put_status", fake_put_status)
    assert call(http_event("PUT /agents/{agentId}/status", {"paused": True}, agent_id="bot")) == (200, {"ok": True})
    assert seen["agent_id"] == "bot" and seen["body"] == {"paused": True} and seen["owner"] == "tejaswi"
    assert seen["now"].tzinfo is not None and seen["now"].utcoffset().total_seconds() == 0


def test_get_status_routes_to_service(store, monkeypatch):
    seen = []
    monkeypatch.setattr(api.service, "get_status",
                        lambda st, creds, agent_id: seen.append(agent_id) or api.Result(200, {"x": 1}))
    assert call(http_event("GET /agents/{agentId}/status", agent_id="bot")) == (200, {"x": 1})
    assert seen == ["bot"]


@pytest.mark.parametrize("headers", BAD_HEADERS)
@pytest.mark.parametrize("route,body", STATUS_ROUTES)
def test_status_routes_401_without_credentials(store, route, body, headers):
    ev = NoBodyEvent(http_event(route, body, agent_id="bot", headers=headers))
    assert call(ev) == (401, {"error": "unauthorized"})
    assert store.items == {}


@pytest.mark.parametrize("bad", [{}, {"paused": "yes"}, {"paused": 1}, {"paused": True, "x": 1}, [True]])
def test_put_status_bad_body_400(store, bad):
    status, body = call(http_event("PUT /agents/{agentId}/status", bad, agent_id="bot"))
    assert status == 400 and "paused" in body["error"]
    assert store.items == {}


def test_put_status_invalid_json_400(store):
    status, body = call(http_event("PUT /agents/{agentId}/status", raw_body="{nope", agent_id="bot"))
    assert status == 400 and "JSON" in body["error"]
    assert store.items == {}


def test_status_forbidden_through_handler(store):
    call(http_event("PUT /agents/{agentId}/config", CFG, agent_id="bot"))
    snap = store.snapshot()
    other = {"X-Agentwatch-Owner": "tejaswi", "X-Agentwatch-Key-Hash": "b" * 64}
    for route, body in STATUS_ROUTES:
        assert call(http_event(route, body, agent_id="bot", headers=other)) == (403, {"error": "forbidden"})
    assert store.snapshot() == snap


# ---- audit fix (PR A): ALERT_AGENTS ----


def _deps_with_agents(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ALERT_AGENTS", raising=False)
    else:
        monkeypatch.setenv("ALERT_AGENTS", value)
    return _build_deps(monkeypatch, None)


@pytest.mark.parametrize("value,expected", [
    (None, frozenset()),
    ("", frozenset()),
    ("  ,  ", frozenset()),
    ("tejaswi/bad-bot", frozenset({"tejaswi/bad-bot"})),
    (" tejaswi/bad-bot , tejaswi/demo-bot ,", frozenset({"tejaswi/bad-bot", "tejaswi/demo-bot"})),
])
def test_alert_agents_parsed_from_env(monkeypatch, value, expected):
    assert _deps_with_agents(monkeypatch, value).alert_agents == expected


def test_old_owner_only_env_var_is_ignored(monkeypatch):
    monkeypatch.setenv("ALERT_OWNER_IDS", "tejaswi")
    assert _deps_with_agents(monkeypatch, None).alert_agents == frozenset()
    assert not hasattr(api.Deps, "alert_owner_ids")


def test_handler_passes_allowlist_to_ingest(monkeypatch):
    calls = []

    class Rec:
        def publish(self, subject, body):
            calls.append(subject)

    s = InMemoryStore()
    # Right owner, wrong agent: the owner alone is not enough.
    monkeypatch.setattr(api, "_deps", api.Deps(store=s, publisher=Rec(), alert_agents=frozenset({"tejaswi/other-bot"})))
    blocked = {**event_body(), "type": "blocked", "violationType": "blocked_path", "attemptedPath": ".env"}
    status, _ = call(http_event("POST /events", blocked))
    assert status == 200 and calls == []
    monkeypatch.setattr(api, "_deps", api.Deps(store=s, publisher=Rec(), alert_agents=frozenset({"tejaswi/bot"})))
    status, _ = call(http_event("POST /events", {**blocked, "eventId": "1" * 32}))
    assert status == 200 and len(calls) == 1
