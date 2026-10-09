"""Req 16.1, 16.5, 16.6: demo_agent.py prefers Bedrock and falls back to the Anthropic API."""

import importlib.util
from pathlib import Path

import pytest

from agentwatch.client import Response
from fakes import FakeAnthropic, FakeBedrock, FakeTransport

DEMO = Path(__file__).resolve().parents[2] / "demo"


def load(name):
    spec = importlib.util.spec_from_file_location(name, DEMO / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.syspath_prepend(str(DEMO))
    monkeypatch.setenv("AGENTWATCH_ENDPOINT", "https://api.example")
    monkeypatch.setenv("AGENTWATCH_OWNER", "tejaswi")
    monkeypatch.setenv("AGENTWATCH_KEY", "sk-test-key")
    return load("demo_agent")


def transport():
    return FakeTransport([Response(200, {"guardrails": {"dailySpendCapUsd": None, "blockedPaths": [".env"]},
                                         "pricing": {"models": {}}})])


def events(t):
    return [r["json"] for r in t.requests if r["url"] == "https://api.example/events"]


def raise_(exc):
    def factory():
        raise exc
    return factory


def access_denied():
    botocore = pytest.importorskip("botocore.exceptions")
    return botocore.ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Converse")


@pytest.mark.parametrize("bedrock_factory", [
    raise_(ImportError("No module named 'boto3'")),
    lambda: FakeBedrock(error=access_denied()),
    lambda: FakeBedrock(error=RuntimeError("converse failed")),
], ids=["no-boto3", "access-denied", "converse-fails"])
def test_falls_back_to_anthropic(demo, bedrock_factory, capsys):
    t, anth = transport(), FakeAnthropic()
    aw = demo.common.init("demo-bot", transport=t)
    client = demo.make_client(aw, bedrock_factory=bedrock_factory, anthropic_factory=lambda: anth)
    demo.common.ask(client, "hi")
    assert anth.calls and anth.calls[-1]["model"] == demo.ANTHROPIC_MODEL_ID
    assert "falling back to Anthropic API" in capsys.readouterr().out


def test_uses_bedrock_when_it_works(demo):
    t, br = transport(), FakeBedrock()
    aw = demo.common.init("demo-bot", transport=t)
    client = demo.make_client(aw, bedrock_factory=lambda: br,
                              anthropic_factory=raise_(AssertionError("must not fall back")))
    demo.common.ask(client, "hi")
    assert br.calls and all(c["modelId"] == demo.BEDROCK_MODEL_ID for c in br.calls)


def test_main_runs_harmless_read_file(demo, tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.write_text("study plan: week 3")
    t, br = transport(), FakeBedrock()
    assert demo.main(client=br, transport=t, notes_path=str(notes)) == 0
    out = capsys.readouterr().out
    assert "study plan: week 3" in out
    evs = events(t)
    assert [e["type"] for e in evs].count("tool_call") == 1
    assert not [e for e in evs if e["type"] == "blocked"]
    (tool,) = [e for e in evs if e["type"] == "tool_call"]
    assert tool["tool"] == "read_file" and tool["target"] == str(notes)


def test_default_notes_file_exists(demo):
    assert Path(demo.NOTES_PATH).is_file()
