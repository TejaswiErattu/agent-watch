import json
import logging

import pytest

from agentwatch_api.alerts import (
    WEBHOOK_TEXT_MAX,
    WEBHOOK_TIMEOUT_S,
    MultiPublisher,
    WebhookPublisher,
)

# Synthetic webhook-shaped URLs. Not real webhooks.
DISCORD = "https://discord.com/api/webhooks/1/tok"
DISCORDAPP = "https://discordapp.com/api/webhooks/1/tok"
SLACK = "https://hooks.slack.com/services/T/B/tok"


class FakeResp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, status=204, exc=None):
        self.calls, self.status, self.exc = [], status, exc

    def __call__(self, req, timeout=None):
        self.calls.append((req.full_url, req.data, dict(req.header_items()), timeout, req.get_method()))
        if self.exc:
            raise self.exc
        return FakeResp(self.status)


def test_discord_sends_content():
    o = FakeOpener()
    WebhookPublisher(DISCORD, opener=o).publish("S", "line1\nline2\n")
    assert len(o.calls) == 1
    url, data, headers, timeout, method = o.calls[0]
    assert url == DISCORD and method == "POST" and timeout == WEBHOOK_TIMEOUT_S == 3.0
    assert json.loads(data) == {"content": "S\nline1\nline2\n"}
    assert {k.lower(): v for k, v in headers.items()}["content-type"] == "application/json"


def test_discordapp_host_is_discord():
    o = FakeOpener()
    WebhookPublisher(DISCORDAPP, opener=o).publish("S", "B")
    assert set(json.loads(o.calls[0][1])) == {"content"}


def test_slack_sends_text():
    o = FakeOpener(status=200)
    WebhookPublisher(SLACK, opener=o).publish("S", "B")
    assert json.loads(o.calls[0][1]) == {"text": "S\nB"}


@pytest.mark.parametrize("url", [
    "http://discord.com/api/webhooks/1/tok",
    "https://example.com/hook",
    "https://discord.com.evil.com/api/webhooks/1/tok",
    "https://user@discord.com/api/webhooks/1/tok",
    "https://evil.com#@discord.com/x",
    "https://discord.com:8443/api/webhooks/1/tok",
    "ftp://discord.com/x",
    "not a url",
])
def test_rejected_urls_warn_once_without_url_and_never_send(url, caplog):
    o = FakeOpener()
    with caplog.at_level(logging.INFO, logger="agentwatch_api"):
        p = WebhookPublisher(url, opener=o)
        p.publish("S", "B")
        p.publish("S", "B")
    assert o.calls == []
    msgs = [r.getMessage() for r in caplog.records]
    assert sum("webhook_url_rejected" in m for m in msgs) == 1
    assert not any(url in m or "tok" in m for m in msgs)


def test_non_2xx_raises():
    with pytest.raises(RuntimeError):
        WebhookPublisher(DISCORD, opener=FakeOpener(status=500)).publish("S", "B")


def test_opener_http_error_propagates_without_url():
    # A real urlopen raises HTTPError for 4xx/5xx; the publisher must not swallow it.
    import urllib.error
    exc = urllib.error.HTTPError(DISCORD, 404, "nf", {}, None)
    with pytest.raises(urllib.error.HTTPError):
        WebhookPublisher(DISCORD, opener=FakeOpener(exc=exc)).publish("S", "B")


def test_text_capped():
    o = FakeOpener()
    WebhookPublisher(DISCORD, opener=o).publish("S", "x" * 5000)
    assert len(json.loads(o.calls[0][1])["content"]) == WEBHOOK_TEXT_MAX == 1900


def test_repr_does_not_leak_url():
    p = WebhookPublisher("https://discord.com/api/webhooks/1/SECRETTOKEN", opener=FakeOpener())
    assert "SECRETTOKEN" not in repr(p) and "webhooks" not in repr(p)


class Rec:
    def __init__(self, exc=None):
        self.calls, self.exc = [], exc

    def publish(self, subject, body):
        self.calls.append((subject, body))
        if self.exc:
            raise self.exc


def test_multi_calls_each_once_and_isolates_failures(caplog):
    a, b, c = Rec(), Rec(ValueError("secret body text")), Rec()
    with caplog.at_level(logging.INFO, logger="agentwatch_api"):
        MultiPublisher([a, b, c]).publish("S", "B")
    assert a.calls == b.calls == c.calls == [("S", "B")]
    rec = [r.getMessage() for r in caplog.records if "alert_publish_failed" in r.getMessage()]
    assert len(rec) == 1
    assert json.loads(rec[0]) == {"msg": "alert_publish_failed", "publisher": "Rec", "error": "ValueError"}


def test_multi_empty_is_noop():
    MultiPublisher([]).publish("S", "B")
