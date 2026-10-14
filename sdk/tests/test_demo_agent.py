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


# ---- 6.5: --loop N trips the spend cap ----

def capped_transport(demo, cap):
    # Output-only pricing keeps the math exact: each ask (maxTokens 200) is estimated at
    # 200 * 10 / 1e6 = 0.002 and FakeBedrock's 50 output tokens actually cost 0.0005.
    pricing = {"models": {demo.BEDROCK_MODEL_ID: {"inputPerMTokUsd": 0.0, "outputPerMTokUsd": 10.0}}}
    return FakeTransport([Response(200, {"guardrails": {"dailySpendCapUsd": cap, "blockedPaths": []},
                                         "pricing": pricing})])


def test_loop_stops_cleanly_on_spend_cap(demo, tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.write_text("study plan")
    # call 1: 0 + .002 ok; call 2: .0005 + .002 ok; call 3: .001 + .002 = .003 > .0027 blocked.
    t, br = capped_transport(demo, 0.0027), FakeBedrock(in_tok=100, out_tok=50)
    assert demo.main(client=br, transport=t, notes_path=str(notes), loop=3) == 0
    out = capsys.readouterr().out
    assert len(br.calls) == 2
    assert "SpendCapExceeded" in out and "run 3/3" in out
    blocked = [e for e in events(t) if e["type"] == "blocked"]
    assert [b["violationType"] for b in blocked] == ["spend_cap"]


def test_loop_without_cap_runs_n_times(demo, tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.write_text("study plan")
    t, br = capped_transport(demo, None), FakeBedrock()
    assert demo.main(client=br, transport=t, notes_path=str(notes), loop=4) == 0
    assert len(br.calls) == 4
    assert "SpendCapExceeded" not in capsys.readouterr().out
    assert [e["type"] for e in events(t)].count("tool_call") == 1  # notes are read once


@pytest.mark.parametrize("argv,want", [([], 1), (["--loop", "5"], 5)])
def test_parse_args_loop(demo, argv, want):
    assert demo.parse_args(argv).loop == want


@pytest.mark.parametrize("bad", ["0", "-2", "x"])
def test_parse_args_rejects_non_positive_loop(demo, bad):
    with pytest.raises(SystemExit):
        demo.parse_args(["--loop", bad])


# ---- 8.6: --sleep and generic guardrail handling ----

@pytest.mark.parametrize("argv,want", [([], 0.0), (["--sleep", "2"], 2.0), (["--sleep", "0.5"], 0.5),
                                       (["--sleep", "0"], 0.0)])
def test_parse_args_sleep(demo, argv, want):
    assert demo.parse_args(argv).sleep == want


@pytest.mark.parametrize("bad", ["-1", "-0.1", "x", "nan", "inf"])
def test_parse_args_rejects_bad_sleep(demo, bad):
    with pytest.raises(SystemExit):
        demo.parse_args(["--sleep", bad])


def test_loop_sleeps_between_runs_not_after_last(demo, tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("study plan")
    slept = []
    assert demo.main(client=FakeBedrock(), transport=capped_transport(demo, None), notes_path=str(notes),
                     loop=3, sleep_s=2.0, sleep=slept.append) == 0
    assert slept == [2.0, 2.0]


def test_loop_without_sleep_never_sleeps(demo, tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("study plan")
    slept = []
    demo.main(client=FakeBedrock(), transport=capped_transport(demo, None), notes_path=str(notes),
              loop=3, sleep=slept.append)
    assert slept == []


def test_loop_stops_cleanly_on_agent_paused(demo, tmp_path, capsys, monkeypatch):
    import agentwatch
    from agentwatch.client import CONTROL_INTERVAL_S
    from fakes import status_body

    notes = tmp_path / "notes.txt"
    notes.write_text("study plan")
    t = capped_transport(demo, None)
    # init: not paused. The injected sleep advances a fake clock past the control interval,
    # so the poll before run 2 sees paused: run 1 succeeds, run 2 raises AgentPaused.
    t.status_outcomes = [Response(200, status_body(False)), Response(200, status_body(True))]
    br = FakeBedrock()
    clock = {"t": 0.0}
    real_init = agentwatch.init
    monkeypatch.setattr(agentwatch, "init", lambda **kw: real_init(**kw, clock=lambda: clock["t"]))

    def sleep(s):
        clock["t"] += CONTROL_INTERVAL_S

    assert demo.main(client=br, transport=t, notes_path=str(notes), loop=5, sleep_s=1.0, sleep=sleep) == 0
    out = capsys.readouterr().out
    assert len(br.calls) == 1
    assert "run 2/5: AgentPaused: agent demo-bot is paused" in out
    assert "run 3/5" not in out
    blocked = [e for e in events(t) if e["type"] == "blocked"]
    assert [b["violationType"] for b in blocked] == ["paused"]


def test_spend_cap_message_unchanged(demo, tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.write_text("study plan")
    demo.main(client=FakeBedrock(), transport=capped_transport(demo, 0.0027), notes_path=str(notes), loop=3)
    out = capsys.readouterr().out
    assert "run 3/3: SpendCapExceeded: " in out
    assert "(Agent Watch stopped the call before it ran; an alert is on its way)" in out
