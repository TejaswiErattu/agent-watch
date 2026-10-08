"""Req 1.5: the exact 3-line integration from design.md works unchanged."""

import os

from agentwatch import client as client_mod
from agentwatch.client import Response
from fakes import FakeAnthropic, FakeTransport


def test_three_line_snippet_records_llm_and_tool_events(monkeypatch):
    fake = FakeTransport([Response(200, {"guardrails": {"dailySpendCapUsd": None, "blockedPaths": []},
                                         "pricing": {"models": {}}})])
    monkeypatch.setattr(client_mod, "RequestsTransport", lambda: fake)
    monkeypatch.setenv("AGENTWATCH_ENDPOINT", "https://api.example")
    monkeypatch.setenv("AGENTWATCH_KEY", "sk-test-key")

    client = FakeAnthropic(in_tok=11, out_tok=22)
    TOOLS = {"read_file": lambda path: f"contents of {path}"}

    # ---- the 3 lines, verbatim from design.md ----
    import agentwatch
    aw = agentwatch.init(agent_id="study-bot", owner_id="tejaswi", api_key=os.environ["AGENTWATCH_KEY"])
    client, TOOLS = aw.wrap(client), aw.tools(TOOLS)
    # ----------------------------------------------

    client.messages.create(model="claude-haiku-4-5", max_tokens=16,
                           messages=[{"role": "user", "content": "hi"}])
    assert TOOLS["read_file"]("notes.txt") == "contents of notes.txt"
    assert aw._sender.flush(5)

    evs = [r["json"] for r in fake.requests if r["url"] == "https://api.example/events"]
    assert [e["type"] for e in evs] == ["llm_call", "tool_call"]
    assert all(e["agentId"] == "study-bot" and e["ownerId"] == "tejaswi" for e in evs)
    assert evs[1]["tool"] == "read_file" and evs[1]["target"] == "notes.txt"
