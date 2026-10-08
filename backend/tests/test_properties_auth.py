from types import SimpleNamespace

from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.auth import Credentials, key_verifier, matches

owners = st.from_regex(r"[A-Za-z0-9._-]{1,64}", fullmatch=True)
hashes = st.from_regex(r"[0-9a-f]{64}", fullmatch=True)


# Feature: agent-watch, Property 14: Authorization gate
@settings(max_examples=100)
@given(
    rec_owner=owners,
    rec_hash=hashes,
    cred_owner=st.one_of(owners, st.just(None)),
    cred_hash=st.one_of(hashes, st.just(None)),
)
def test_auth_matches_iff_owner_and_verifier_equal(rec_owner, rec_hash, cred_owner, cred_hash):
    # None means "reuse the record's value", so equal cases are well covered.
    cred_owner = rec_owner if cred_owner is None else cred_owner
    cred_hash = rec_hash if cred_hash is None else cred_hash
    rec = SimpleNamespace(owner_id=rec_owner, key_verifier=key_verifier(rec_hash))
    creds = Credentials(cred_owner, cred_hash)
    expected = rec_owner == cred_owner and key_verifier(rec_hash) == key_verifier(cred_hash)
    assert matches(rec, creds) is expected


# ---- 2.7: route clauses, driven through lambda_handler ----

import json  # noqa: E402

from agentwatch_api.handlers import api  # noqa: E402
from agentwatch_api.service import NullPublisher  # noqa: E402
from agentwatch_api.store import InMemoryStore  # noqa: E402

ROUTES = ["POST /events", "GET /agents/{agentId}/config", "PUT /agents/{agentId}/config"]
CFG_BODY = json.dumps({"dailySpendCapUsd": 1.0, "blockedPaths": [".env"]})


def _event(route, headers, owner_in_body):
    ev = {"routeKey": route, "headers": headers, "pathParameters": {"agentId": "bot"}}
    if route == "POST /events":
        ev["body"] = json.dumps({"agentId": "bot", "ownerId": owner_in_body, "ts": "2026-10-08T10:00:00.000Z",
                                 "eventId": "f" * 32, "type": "tool_call", "tool": "t", "target": "x"})
    elif route.startswith("PUT"):
        ev["body"] = CFG_BODY
    return ev


def _seeded_store(owner, key_hash):
    s = InMemoryStore()
    api._deps = api.Deps(store=s, publisher=NullPublisher())
    seed = _event("PUT /agents/{agentId}/config",
                  {"x-agentwatch-owner": owner, "x-agentwatch-key-hash": key_hash}, owner)
    assert api.lambda_handler(seed, None)["statusCode"] == 200
    return s


bad_owner_values = st.one_of(st.none(), st.just(""), st.text(max_size=70).filter(
    lambda s: not (1 <= len(s) <= 64 and all(c.isascii() and (c.isalnum() or c in "._-") for c in s))))
bad_hash_values = st.one_of(st.none(), st.text(max_size=70).filter(
    lambda s: not (len(s) == 64 and all(c in "0123456789abcdef" for c in s))))


# Feature: agent-watch, Property 14: Authorization gate
@settings(max_examples=100)
@given(route=st.sampled_from(ROUTES), owner=bad_owner_values, key_hash=bad_hash_values,
       which=st.sampled_from(["owner", "hash", "both"]))
def test_route_clause_401_for_missing_or_malformed(route, owner, key_hash, which):
    old = api._deps
    try:
        s = InMemoryStore()
        api._deps = api.Deps(store=s, publisher=NullPublisher())
        headers = {"x-agentwatch-owner": "tejaswi", "x-agentwatch-key-hash": "a" * 64}
        if which in ("owner", "both"):
            headers["x-agentwatch-owner"] = owner
        if which in ("hash", "both"):
            headers["x-agentwatch-key-hash"] = key_hash
        headers = {k: v for k, v in headers.items() if v is not None}
        resp = api.lambda_handler(_event(route, headers, "tejaswi"), None)
        assert resp["statusCode"] == 401
        assert json.loads(resp["body"]) == {"error": "unauthorized"}
        assert s.items == {}
    finally:
        api._deps = old


# Feature: agent-watch, Property 14: Authorization gate
@settings(max_examples=100)
@given(route=st.sampled_from(ROUTES), rec_owner=owners, rec_hash=hashes,
       cred_owner=st.one_of(owners, st.none()), cred_hash=st.one_of(hashes, st.none()))
def test_route_clause_403_for_mismatch(route, rec_owner, rec_hash, cred_owner, cred_hash):
    cred_owner = rec_owner if cred_owner is None else cred_owner
    cred_hash = rec_hash if cred_hash is None else cred_hash
    if cred_owner == rec_owner and cred_hash == rec_hash:
        return  # matching credentials are covered elsewhere
    old = api._deps
    try:
        s = _seeded_store(rec_owner, rec_hash)
        before = s.snapshot()
        headers = {"x-agentwatch-owner": cred_owner, "x-agentwatch-key-hash": cred_hash}
        resp = api.lambda_handler(_event(route, headers, cred_owner), None)
        assert resp["statusCode"] == 403
        assert json.loads(resp["body"]) == {"error": "forbidden"}
        assert s.snapshot() == before
    finally:
        api._deps = old
