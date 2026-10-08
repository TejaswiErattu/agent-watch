import hashlib
from types import SimpleNamespace
from unittest import mock

import pytest

from agentwatch_api import auth
from agentwatch_api.auth import Credentials, key_verifier, matches, parse_credentials

KH = hashlib.sha256(b"my-api-key").hexdigest()


def test_parses_lowercase_headers():
    c = parse_credentials({"x-agentwatch-owner": "tejaswi", "x-agentwatch-key-hash": KH})
    assert c == Credentials(owner_id="tejaswi", key_hash=KH)


def test_parses_mixed_case_headers():
    c = parse_credentials({"X-Agentwatch-Owner": "tejaswi", "X-AgentWatch-Key-Hash": KH})
    assert c is not None and c.owner_id == "tejaswi"


def test_none_headers():
    assert parse_credentials(None) is None
    assert parse_credentials({}) is None


@pytest.mark.parametrize("owner", [None, "", "o" * 65, "has space", "semi;colon", 5])
def test_bad_owner(owner):
    h = {"x-agentwatch-key-hash": KH}
    if owner is not None:
        h["x-agentwatch-owner"] = owner
    assert parse_credentials(h) is None


@pytest.mark.parametrize("kh", [None, "", KH.upper(), KH[:-1], KH + "0", "z" * 64])
def test_bad_key_hash(kh):
    h = {"x-agentwatch-owner": "tejaswi"}
    if kh is not None:
        h["x-agentwatch-key-hash"] = kh
    assert parse_credentials(h) is None


def test_owner_boundaries_ok():
    for o in ["a", "o" * 64, "Tej.as_wi-1"]:
        assert parse_credentials({"x-agentwatch-owner": o, "x-agentwatch-key-hash": KH}) is not None


def test_key_verifier_known_vector():
    # sha256("abc") then sha256 of that hex string.
    kh = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert key_verifier(kh) == hashlib.sha256(kh.encode("ascii")).hexdigest()
    assert key_verifier(kh) != kh
    assert len(key_verifier(kh)) == 64


def _rec(owner, kv):
    return SimpleNamespace(owner_id=owner, key_verifier=kv)


def test_matches_true_and_false():
    c = Credentials("tejaswi", KH)
    assert matches(_rec("tejaswi", key_verifier(KH)), c)
    assert not matches(_rec("someone", key_verifier(KH)), c)
    assert not matches(_rec("tejaswi", key_verifier("0" * 64)), c)


def test_matches_uses_compare_digest():
    c = Credentials("tejaswi", KH)
    with mock.patch.object(auth.hmac, "compare_digest", wraps=auth.hmac.compare_digest) as spy:
        assert matches(_rec("tejaswi", key_verifier(KH)), c)
    spy.assert_called_once()


def test_repr_hides_key_hash():
    c = Credentials("tejaswi", KH)
    assert KH not in repr(c)
    assert KH not in str(c)
    assert "tejaswi" in repr(c)
