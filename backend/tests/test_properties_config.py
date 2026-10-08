from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.auth import Credentials
from agentwatch_api.pricing import pricing_table
from agentwatch_api.rules import EMPTY_CONFIG, to_json
from agentwatch_api.service import get_config
from agentwatch_api.store import InMemoryStore

agent_ids = st.from_regex(r"[A-Za-z0-9._-]{1,128}", fullmatch=True)
creds_s = st.builds(
    Credentials,
    st.from_regex(r"[A-Za-z0-9._-]{1,64}", fullmatch=True),
    st.from_regex(r"[0-9a-f]{64}", fullmatch=True),
)


# Feature: agent-watch, Property 6: Read routes never create records
@settings(max_examples=100)
@given(agent_id=agent_ids, creds=creds_s)
def test_get_config_never_creates_records(agent_id, creds):
    s = InMemoryStore()
    r = get_config(s, creds, agent_id)
    assert r.status == 200
    assert r.body == {"guardrails": to_json(EMPTY_CONFIG), "pricing": pricing_table()}
    assert s.items == {}
