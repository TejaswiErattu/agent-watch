"""Shared fakes for SDK tests. No network."""

from __future__ import annotations

from agentwatch.client import Response, TransportError


def spend_body(usd=0.0):
    return {"agentId": "bot", "rollingSpendUsd": usd,
            "windowStart": "2026-10-08T12:00:00.000Z", "windowEnd": "2026-10-09T12:00:00.000Z"}


class FakeTransport:
    """Records every request. `outcomes` is a queue of Response or Exception; default 200 {}.

    GET .../spend requests made by a Watcher are routed separately: they pop from
    `spend_outcomes` (default 200 with 0.0 spend) and are recorded in `spend_requests`, not
    `requests`. That keeps the config/event queues and request counts of tests that predate
    spend sync unchanged. Pass `route_spend=False` for raw ApiClient tests that want one queue.
    """

    def __init__(self, outcomes=None, default=None, spend_outcomes=None, spend_default=None,
                 route_spend=True):
        self.route_spend = route_spend
        self.requests: list[dict] = []
        self.outcomes = list(outcomes or [])
        self.default = default or Response(200, {})
        self.spend_requests: list[dict] = []
        self.spend_outcomes = list(spend_outcomes or [])
        self.spend_default = spend_default or Response(200, spend_body())

    def request(self, method, url, *, headers, json=None, timeout):
        rec = {"method": method, "url": url, "headers": dict(headers), "json": json, "timeout": timeout}
        if self.route_spend and url.endswith("/spend"):
            self.spend_requests.append(rec)
            out = self.spend_outcomes.pop(0) if self.spend_outcomes else self.spend_default
        else:
            self.requests.append(rec)
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
