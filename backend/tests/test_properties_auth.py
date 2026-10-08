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
