import hashlib

import pytest

import agentwatch
from agentwatch.client import (
    Credentials,
    GuardrailBlocked,
    PathBlocked,
    SpendCapExceeded,
    key_hash,
)

# sha256(b"abc"), the FIPS 180-2 test vector
ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_key_hash_known_vector():
    assert key_hash("abc") == ABC


def test_key_hash_is_lowercase_hex_of_utf8():
    assert key_hash("ключ") == hashlib.sha256("ключ".encode("utf-8")).hexdigest()


@pytest.mark.parametrize("bad", ["", None, 123])
def test_key_hash_rejects_empty_or_non_string(bad):
    with pytest.raises(ValueError):
        key_hash(bad)


def test_guardrail_blocked_carries_type_and_detail():
    e = GuardrailBlocked("blocked_path", ".env")
    assert e.violation_type == "blocked_path" and e.detail == ".env"
    assert isinstance(e, Exception)


@pytest.mark.parametrize("cls,vt", [(SpendCapExceeded, "spend_cap"), (PathBlocked, "blocked_path")])
def test_subclasses_set_violation_type(cls, vt):
    e = cls("detail")
    assert isinstance(e, GuardrailBlocked)
    assert e.violation_type == vt and e.detail == "detail"


def test_exceptions_exported_from_package():
    assert agentwatch.GuardrailBlocked is GuardrailBlocked
    assert agentwatch.SpendCapExceeded is SpendCapExceeded
    assert agentwatch.PathBlocked is PathBlocked


def test_credentials_hash_the_key_and_drop_it():
    c = Credentials.from_api_key("tejaswi", "sk-secret-key")
    assert c.owner_id == "tejaswi"
    assert c.key_hash == key_hash("sk-secret-key")
    assert "sk-secret-key" not in vars(c).values()


def test_credentials_repr_hides_key_and_hash():
    key = "sk-secret-key"
    c = Credentials.from_api_key("tejaswi", key)
    for text in (repr(c), str(c)):
        assert key not in text
        assert c.key_hash not in text
        assert "tejaswi" in text
