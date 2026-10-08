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
