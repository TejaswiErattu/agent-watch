import re

import pytest

import agentwatch
from agentwatch.client import Response
from fakes import FakeTransport

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
EID_RE = re.compile(r"^[0-9a-f]{32}$")


def cfg(paths=()):
    return Response(200, {"guardrails": {"dailySpendCapUsd": None, "blockedPaths": list(paths)},
                          "pricing": {"models": {}}})


def make(paths=(), outcomes=None):
    t = FakeTransport([cfg(paths)] + list(outcomes or []))
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint="https://x", transport=t,
                         clock=lambda: 0.0, sleep=lambda s: None)
    return aw, t


def events(aw, t):
    aw._sender.flush(5)
    return [r["json"] for r in t.requests if r["url"].endswith("/events")]


def read_file(path):
    return f"contents of {path}"


def search(query, limit=5):
    return [query] * limit


def test_tools_keeps_keys_and_wraps_each():
    aw, t = make()
    tools = aw.tools({"read_file": read_file, "search": search})
    assert set(tools) == {"read_file", "search"}
    assert tools["read_file"]("notes.md") == "contents of notes.md"
    assert tools["search"]("q", limit=2) == ["q", "q"]
    evs = events(aw, t)
    assert [e["tool"] for e in evs] == ["read_file", "search"]
    assert all(e["type"] == "tool_call" for e in evs)


def test_tool_decorator_with_name_and_path_arg():
    aw, t = make()

    @aw.tool(name="loader", path_arg="src")
    def load(src, mode="r"):
        return src

    assert load("data.csv") == "data.csv"
    (e,) = events(aw, t)
    assert e["tool"] == "loader" and e["target"] == "data.csv"


def test_bare_decorator_uses_function_name():
    aw, t = make()

    @aw.tool
    def fetch(url):
        return url

    fetch("https://example.com")
    (e,) = events(aw, t)
    assert e["tool"] == "fetch"


@pytest.mark.parametrize("argname", ["path", "file_path", "filepath", "filename", "file"])
def test_path_argument_found_by_conventional_name(argname):
    aw, t = make()
    ns = {}
    exec(f"def f(mode, {argname}=None):\n    return {argname}", ns)
    f = aw.tool(name="f")(ns["f"])
    f("rb", **{argname: "x.txt"})
    (e,) = events(aw, t)
    assert e["target"] == "x.txt"


def test_target_falls_back_to_repr_of_first_arg_truncated():
    aw, t = make()
    tools = aw.tools({"search": search})
    tools["search"]("q" * 500)
    (e,) = events(aw, t)
    assert e["target"] == repr("q" * 500)[:200]


def test_target_for_no_arguments():
    aw, t = make()
    tools = aw.tools({"now": lambda: 1})
    tools["now"]()
    (e,) = events(aw, t)
    assert isinstance(e["target"], str) and e["target"]


def test_meta_args_at_most_10_truncated_to_200():
    aw, t = make()
    tools = aw.tools({"many": lambda *a: len(a)})
    tools["many"](*(["z" * 300] * 15))
    (e,) = events(aw, t)
    assert len(e["meta"]["args"]) == 10
    assert all(len(a) <= 200 for a in e["meta"]["args"])


def test_raising_tool_still_reports_and_reraises():
    aw, t = make()

    def boom(path):
        raise FileNotFoundError(path)

    tools = aw.tools({"boom": boom})
    with pytest.raises(FileNotFoundError):
        tools["boom"]("missing.txt")
    (e,) = events(aw, t)
    assert e["meta"]["error"] == "FileNotFoundError" and e["target"] == "missing.txt"


def test_event_envelope_fields():
    aw, t = make()
    tools = aw.tools({"read_file": read_file})
    tools["read_file"]("a")
    tools["read_file"]("b")
    evs = events(aw, t)
    for e in evs:
        assert e["agentId"] == "bot" and e["ownerId"] == "tejaswi"
        assert TS_RE.match(e["ts"]) and len(e["ts"]) == 24
        assert EID_RE.match(e["eventId"])
        assert "costUsd" not in e
    assert evs[0]["eventId"] != evs[1]["eventId"]


def test_wrapped_function_keeps_name_and_doc():
    aw, _ = make()

    def documented(path):
        """Reads a file."""

    w = aw.tools({"d": documented})["d"]
    assert w.__name__ == "documented" and w.__doc__ == "Reads a file."


def test_meta_stays_under_server_4kb_limit_with_wide_unicode():
    import json

    aw, t = make()
    tools = aw.tools({"many": lambda *a: None})
    tools["many"](*(["😀" * 300] * 15))
    (e,) = events(aw, t)
    size = len(json.dumps(e["meta"], separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    assert size <= 4096
    assert e["meta"]["args"]  # still reports something


# ---- 3.12 blocklist enforcement ----

import threading  # noqa: E402

from agentwatch import PathBlocked  # noqa: E402
from agentwatch.client import TransportError  # noqa: E402


def test_blocked_path_raises_before_tool_runs_and_reports_sync():
    aw, t = make(paths=[".env"])
    called = []

    def read(path):
        called.append(path)

    tools = aw.tools({"read_file": read})
    with pytest.raises(PathBlocked) as ei:
        tools["read_file"](".env")
    assert called == []
    assert ei.value.violation_type == "blocked_path" and ei.value.detail == ".env"
    # The blocked event was sent BEFORE the raise: present without flushing the queue.
    blocked = [r["json"] for r in t.requests if r["url"].endswith("/events")]
    assert len(blocked) == 1
    b = blocked[0]
    assert b["type"] == "blocked" and b["violationType"] == "blocked_path" and b["attemptedPath"] == ".env"
    assert b["meta"] == {"tool": "read_file", "entry": ".env"}
    # No tool_call event for a blocked call.
    assert [e["type"] for e in events(aw, t)] == ["blocked"]


def test_blocked_event_sent_on_caller_thread():
    aw, t = make(paths=[".env"])
    seen = []
    orig = t.request

    def rec(*a, **kw):
        seen.append(threading.current_thread().name)
        return orig(*a, **kw)

    t.request = rec
    with pytest.raises(PathBlocked):
        aw.tools({"r": read_file})["r"](".env")
    assert seen[-1] == threading.current_thread().name


def test_tool_without_path_like_argument_skips_check():
    aw, t = make(paths=["/"])  # root blocks every path
    # Since 3.17 every str argument is a candidate path, so only non-string args skip the check.
    assert aw.tools({"add": lambda a, b=1: a + b})["add"](2, b=3) == 5
    assert [e["type"] for e in events(aw, t)] == ["tool_call"]


def test_non_matching_path_runs_tool():
    aw, t = make(paths=[".env"])
    assert aw.tools({"r": read_file})["r"]("notes.md") == "contents of notes.md"


def test_stale_config_is_refreshed_before_check():
    now = [0.0]
    t = FakeTransport([cfg([]), cfg([".env"])])
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint="https://x", transport=t,
                         clock=lambda: now[0], sleep=lambda s: None)
    r = aw.tools({"r": read_file})["r"]
    assert r(".env") == "contents of .env"  # first config had no rules
    now[0] = 60.0
    with pytest.raises(PathBlocked):
        r(".env")


def test_block_still_raises_when_reporting_fails():
    aw, t = make(paths=[".env"], outcomes=[TransportError("down")] * 4)
    with pytest.raises(PathBlocked):
        aw.tools({"r": read_file})["r"](".env")


def test_pathlike_and_bytes_paths_are_checked(tmp_path):
    aw, _ = make(paths=[".env"])
    r = aw.tools({"r": read_file})["r"]
    with pytest.raises(PathBlocked):
        r(tmp_path / ".env")
    with pytest.raises(PathBlocked):
        r(b".env")


# ---- 3.17 every path-like argument is checked ----


@pytest.mark.parametrize("name", ["src", "dst", "source", "destination", "target_path"])
def test_extra_named_path_args_are_checked(name):
    aw, t = make(paths=[".env"])
    ns = {}
    exec(f"def f(other, {name}):\n    return {name}", ns)
    tool = aw.tool(name="f")(ns["f"])
    with pytest.raises(PathBlocked):
        tool("ok.txt", **{name: ".env"})


def test_copy_blocks_on_second_named_path():
    aw, t = make(paths=[".env"])
    called = []

    def copy(src, dst):
        called.append((src, dst))

    with pytest.raises(PathBlocked) as ei:
        aw.tools({"copy": copy})["copy"](src="ok.txt", dst=".env")
    assert called == [] and ei.value.detail == ".env"
    sent = [r["json"] for r in t.requests if r["url"].endswith("/events")]
    assert len(sent) == 1 and sent[0]["attemptedPath"] == ".env"


def test_second_positional_arg_is_checked():
    aw, t = make(paths=[".env"])
    called = []

    def run(cmd, arg):
        called.append(arg)

    with pytest.raises(PathBlocked):
        aw.tools({"run": run})["run"]("cat", ".env")
    assert called == []


def test_varargs_and_varkwargs_are_checked():
    aw, _ = make(paths=[".env"])
    called = []

    def many(*a, **kw):
        called.append(1)

    tool = aw.tools({"many": many})["many"]
    with pytest.raises(PathBlocked):
        tool("a", "b", ".env")
    with pytest.raises(PathBlocked):
        tool(x="a", y=".env")
    assert called == []


@pytest.mark.parametrize("container", [list, tuple])
def test_paths_inside_list_or_tuple_are_checked(container):
    aw, _ = make(paths=[".env"])
    called = []

    def cat(files):
        called.append(files)

    with pytest.raises(PathBlocked):
        aw.tools({"cat": cat})["cat"](container(["ok.txt", ".env"]))
    assert called == []


def test_path_arg_list_checks_each_name():
    aw, _ = make(paths=[".env"])
    called = []

    @aw.tool(name="merge", path_arg=["left", "right"])
    def merge(left, right, mode=0):
        called.append(1)

    with pytest.raises(PathBlocked):
        merge("ok.txt", ".env")
    assert called == []
    assert merge("a.txt", "b.txt") is None and called == [1]


def test_path_that_fails_normalization_is_blocked():
    aw, t = make(paths=["/nonexistent/dir"])
    called = []

    def read(path):
        called.append(path)

    with pytest.raises(PathBlocked):
        aw.tools({"read": read})["read"]("bad\x00name")
    assert called == []
    sent = [r["json"] for r in t.requests if r["url"].endswith("/events")]
    assert len(sent) == 1 and sent[0]["violationType"] == "blocked_path"
    assert sent[0]["attemptedPath"] == "bad\x00name"


def test_unrelated_strings_still_allowed():
    aw, t = make(paths=[".env"])

    def copy(src, dst, note=""):
        return dst

    assert aw.tools({"copy": copy})["copy"]("a.txt", "b.txt", note="hello") == "b.txt"
    (e,) = events(aw, t)
    assert e["type"] == "tool_call" and e["target"] == "a.txt"
