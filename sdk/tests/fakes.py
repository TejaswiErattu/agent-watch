"""Shared fakes for SDK tests. No network."""

from __future__ import annotations

from agentwatch.client import Response, TransportError


class FakeTransport:
    """Records every request. `outcomes` is a queue of Response or Exception; default 200 {}."""

    def __init__(self, outcomes=None, default=None):
        self.requests: list[dict] = []
        self.outcomes = list(outcomes or [])
        self.default = default or Response(200, {})

    def request(self, method, url, *, headers, json=None, timeout):
        self.requests.append({"method": method, "url": url, "headers": dict(headers),
                              "json": json, "timeout": timeout})
        out = self.outcomes.pop(0) if self.outcomes else self.default
        if isinstance(out, Exception):
            raise out
        return out


def net_error():
    return TransportError("connection refused")


# ---- fake LLM clients (shapes of boto3 bedrock-runtime and anthropic.Anthropic) ----


class FakeBedrock:
    """Has `converse`, like boto3.client("bedrock-runtime")."""

    region_name = "us-west-2"

    def __init__(self, in_tok=100, out_tok=50, stop="end_turn", error=None):
        self.calls = []
        self.in_tok, self.out_tok, self.stop, self.error = in_tok, out_tok, stop, error

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"output": {"message": {"role": "assistant", "content": [{"text": "hi"}]}},
                "stopReason": self.stop,
                "usage": {"inputTokens": self.in_tok, "outputTokens": self.out_tok,
                          "totalTokens": self.in_tok + self.out_tok}}


class _Usage:
    def __init__(self, i, o):
        self.input_tokens, self.output_tokens = i, o


class _Message:
    def __init__(self, i, o, stop):
        self.usage = _Usage(i, o)
        self.stop_reason = stop
        self.content = [{"type": "text", "text": "hi"}]


class _Messages:
    def __init__(self, parent):
        self.parent = parent

    def create(self, **kwargs):
        p = self.parent
        p.calls.append(kwargs)
        if p.error:
            raise p.error
        return _Message(p.in_tok, p.out_tok, p.stop)

    def count_tokens(self, **kwargs):
        return "passthrough"


class FakeAnthropic:
    """Has `messages.create`, like anthropic.Anthropic()."""

    api_key = "sk-ant-should-never-be-read"

    def __init__(self, in_tok=100, out_tok=50, stop="end_turn", error=None):
        self.calls = []
        self.in_tok, self.out_tok, self.stop, self.error = in_tok, out_tok, stop, error
        self.messages = _Messages(self)
