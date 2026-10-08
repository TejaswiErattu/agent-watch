from agentwatch_api.auth import Credentials, key_verifier
from agentwatch_api.rules import EMPTY_CONFIG, GuardrailConfig
from agentwatch_api.service import NullPublisher, Publisher, Result, authorize, new_record
from agentwatch_api.store import InMemoryStore

H = "a" * 64
CREDS = Credentials("tejaswi", H)


def seeded():
    s = InMemoryStore()
    s.create_agent_if_absent(new_record("bot", CREDS, EMPTY_CONFIG))
    return s


def test_new_record_stores_verifier_not_key_hash():
    cfg = GuardrailConfig(1.0, (".env",))
    r = new_record("bot", CREDS, cfg)
    assert r.agent_id == "bot" and r.owner_id == "tejaswi" and r.guardrails == cfg
    assert r.key_verifier == key_verifier(H) != H
    assert r.first_seen is None and r.last_seen is None and r.model is None
    assert r.total_spend_usd == 0.0


def test_authorize_missing_record_is_none():
    assert authorize(InMemoryStore(), "ghost", CREDS) is None


def test_authorize_matching_returns_record():
    r = authorize(seeded(), "bot", CREDS)
    assert r is not None and r != "forbidden" and r.agent_id == "bot"


def test_authorize_owner_mismatch_forbidden():
    assert authorize(seeded(), "bot", Credentials("someone", H)) == "forbidden"


def test_authorize_verifier_mismatch_forbidden():
    assert authorize(seeded(), "bot", Credentials("tejaswi", "b" * 64)) == "forbidden"


def test_result_equality():
    assert Result(200, {"a": 1}) == Result(200, {"a": 1})
    assert Result(200, {"a": 1}) != Result(400, {"a": 1})
    assert Result(200, {"a": 1}) != Result(200, {"a": 2})


def test_null_publisher_is_a_publisher_and_noop():
    p = NullPublisher()
    assert isinstance(p, Publisher)
    assert p.publish("subject", "body") is None
