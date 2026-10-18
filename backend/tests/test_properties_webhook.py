import json
from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

from agentwatch_api.alerts import WebhookPublisher, format_alert
from agentwatch_api.validation import Event, validate_event

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
ALLOWED = {"discord.com": "content", "discordapp.com": "content", "hooks.slack.com": "text"}
NEAR = ["discord.com.evil.com", "evil.com", "xdiscord.com", "hooks.slack.com.x", "slack.com",
        "DISCORD.COM.evil", "api.discord.com", "localhost", "127.0.0.1"]


class FakeResp:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self):
        self.calls = []

    def __call__(self, req, timeout=None):
        self.calls.append((req.data, timeout))
        return FakeResp()


@st.composite
def urls(draw):
    scheme = draw(st.sampled_from(["https", "http", "ftp"]))
    host = draw(st.sampled_from(sorted(ALLOWED) + NEAR))
    path = draw(st.text("abcdefghijklmnopqrstuvwxyz0123456789/_-", max_size=40))
    userinfo = draw(st.sampled_from(["", "", "", "u@", "discord.com@"]))
    url = f"{scheme}://{userinfo}{host}/{path}"
    ok = scheme == "https" and host in ALLOWED and userinfo == ""
    return url, (ALLOWED[host] if ok else None)


@st.composite
def blocked_events(draw):
    b = {"agentId": draw(st.text("abcdefghij-_.0123", min_size=1, max_size=128)), "ownerId": "o",
         "ts": "2026-10-17T10:00:00.000Z", "eventId": "ab" * 16, "type": "blocked"}
    printable = st.text(st.characters().filter(str.isprintable), min_size=1, max_size=1024)
    b |= draw(st.one_of(
        printable.map(lambda p: {"violationType": "blocked_path", "attemptedPath": p}),
        printable.map(lambda c: {"violationType": "blocked_command", "attemptedCommand": c}),
    ))
    e = validate_event(b, NOW)
    assert isinstance(e, Event), e
    return e


# Feature: agent-watch-v2, Property 37: Webhook payload and host allowlist
@settings(max_examples=100)
@given(urls(), blocked_events())
def test_webhook_payload_and_allowlist(url_kind, event):
    url, key = url_kind
    o = FakeOpener()
    subject, body = format_alert(event)
    WebhookPublisher(url, opener=o).publish(subject, body)
    if key is None:
        assert o.calls == []
        return
    assert len(o.calls) == 1
    data, timeout = o.calls[0]
    assert timeout == 3.0
    payload = json.loads(data)
    assert set(payload) == {key}
    text = payload[key]
    assert len(text) <= 1900
    full = f"{subject}\n{body}"
    if len(full) <= 1900:
        assert subject in text and all(line in text for line in body.splitlines())
    else:
        assert text == full[:1900]
