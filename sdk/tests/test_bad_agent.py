"""Req 16.2, 16.3: demo/bad_agent.py gets blocked reading .env (fake API, fake LLM)."""

import importlib.util
from pathlib import Path

import pytest

from agentwatch.client import Response
from fakes import FakeBedrock, FakeTransport

DEMO = Path(__file__).resolve().parents[2] / "demo"


@pytest.fixture
def bad_agent(monkeypatch):
    monkeypatch.syspath_prepend(str(DEMO))
    spec = importlib.util.spec_from_file_location("bad_agent", DEMO / "bad_agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("AGENTWATCH_ENDPOINT", "https://api.example")
    monkeypatch.setenv("AGENTWATCH_OWNER", "tejaswi")
    monkeypatch.setenv("AGENTWATCH_KEY", "sk-test-key")


def cfg(paths):
    return Response(200, {"guardrails": {"dailySpendCapUsd": None, "blockedPaths": paths},
                          "pricing": {"models": {}}})


def test_bad_agent_is_blocked_reading_env(bad_agent, env, capsys, tmp_path, monkeypatch):
    secret = tmp_path / ".env"
    secret.write_text("SECRET=do-not-read\n")
    monkeypatch.chdir(tmp_path)
    t, llm = FakeTransport([cfg([".env"])]), FakeBedrock()

    assert bad_agent.main(client=llm, transport=t) == 0

    out = capsys.readouterr().out
    assert "PathBlocked" in out and ".env" in out and "do-not-read" not in out
    evs = [r["json"] for r in t.requests if r["url"] == "https://api.example/events"]
    blocked = [e for e in evs if e["type"] == "blocked"]
    assert len(blocked) == 1
    assert blocked[0]["violationType"] == "blocked_path" and blocked[0]["attemptedPath"] == ".env"
    assert blocked[0]["agentId"] == "bad-bot"
    assert len(llm.calls) == 1 and llm.calls[0]["modelId"] == bad_agent.BEDROCK_MODEL_ID


def test_without_rule_the_read_goes_through(bad_agent, env, capsys, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("X=1\n")
    monkeypatch.chdir(tmp_path)
    t = FakeTransport([cfg([])])
    assert bad_agent.main(client=FakeBedrock(), transport=t) == 1
    assert "NOT blocked" in capsys.readouterr().out
