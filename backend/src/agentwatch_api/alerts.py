"""Alert email formatting and a publish call that never raises (Req 10.3, 10.5, 10.8)."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from .validation import Event

log = logging.getLogger("agentwatch_api.alerts")

SUBJECT_MAX = 100  # SNS email Subject: ASCII, no newlines, <= 100 chars


def _clean(s: str) -> str:
    """Escape control chars so an attacker-chosen path can't forge lines in the email."""
    return "".join(c if c.isprintable() else repr(c)[1:-1] for c in s)


def _meta_lines(meta: dict, keys: tuple[str, ...]) -> list[str]:
    """`key: value` for each key whose meta value is a str, int, or float (bools and containers skipped)."""
    out = []
    for key in keys:
        v = meta.get(key)
        if isinstance(v, (str, int, float)) and not isinstance(v, bool):
            out.append(f"{key}: {_clean(str(v))}")
    return out


def format_alert(event: Event) -> tuple[str, str]:
    """(subject, body) for a blocked event."""
    item = event.item
    violation = item["violationType"]
    subject = f"Agent Watch: {violation} blocked for {event.agent_id}"
    if len(subject) > SUBJECT_MAX:
        subject = subject[: SUBJECT_MAX - 3] + "..."

    lines = [
        f"agentId: {event.agent_id}",
        f"violationType: {violation}",
        f"ts: {event.ts}",
    ]
    meta = item.get("meta") or {}
    if violation == "spend_cap":
        lines.append(f"attemptedCostUsd: {item['attemptedCostUsd']!r}")
    elif violation == "paused":
        lines.extend(_meta_lines(meta, ("action", "model", "tool")))
    elif violation == "blocked_command":
        lines.append(f"attemptedCommand: {_clean(item['attemptedCommand'])}")
        lines.extend(_meta_lines(meta, ("tool", "pattern")))
    else:
        lines.append(f"attemptedPath: {_clean(item['attemptedPath'])}")
    if violation in ("spend_cap", "blocked_path"):
        for key in ("tool", "entry"):  # v1 lines, unchanged
            if isinstance(meta.get(key), str):
                lines.append(f"{key}: {_clean(meta[key])}")
    lines.append(f"eventId: {event.event_id}")
    return subject, "\n".join(lines) + "\n"


def publish_alert(publisher, event: Event) -> bool:
    """Publish; on any failure log `alert_publish_failed` (type only, never the message) and return False."""
    try:
        publisher.publish(*format_alert(event))
        return True
    except Exception as e:
        log.warning(json.dumps({"msg": "alert_publish_failed", "agentId": event.agent_id,
                                "eventId": event.event_id, "error": type(e).__name__}))
        return False


class SnsPublisher:
    """Publishes to one SNS topic. boto3 is imported lazily so tests never need it."""

    def __init__(self, topic_arn: str, client=None):
        self.topic_arn = topic_arn
        self._client = client

    def publish(self, subject: str, body: str) -> None:
        if self._client is None:
            import boto3
            self._client = boto3.client("sns")
        self._client.publish(TopicArn=self.topic_arn, Subject=subject, Message=body)


# ---- v2 group 11: webhooks and fan-out (Req 30) ----

WEBHOOK_HOSTS = {"discord.com": "discord", "discordapp.com": "discord", "hooks.slack.com": "slack"}
WEBHOOK_TIMEOUT_S = 3.0
WEBHOOK_TEXT_MAX = 1900  # Discord's content limit is 2000; leave headroom


def _classify(url: str) -> str | None:
    """'discord' / 'slack' for an https URL on an allowed host, else None. Rejects userinfo and ports."""
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or "@" in parts.netloc or port is not None:
        return None
    return WEBHOOK_HOSTS.get(parts.hostname or "")


class WebhookPublisher:
    """POSTs alert text to a Discord or Slack incoming webhook. The URL is a secret: never logged or repr'd."""

    def __init__(self, url: str, opener=None):
        self._kind = _classify(url)
        if self._kind is None:
            log.warning(json.dumps({"msg": "webhook_url_rejected"}))
        self._url = url
        self._opener = opener or urllib.request.urlopen

    def __repr__(self) -> str:
        return f"WebhookPublisher(kind={self._kind!r})"

    def publish(self, subject: str, body: str) -> None:
        if self._kind is None:
            return
        text = f"{subject}\n{body}"[:WEBHOOK_TEXT_MAX]
        payload = {"content": text} if self._kind == "discord" else {"text": text}
        req = urllib.request.Request(
            self._url, data=json.dumps(payload).encode(), method="POST",
            headers={"content-type": "application/json", "user-agent": "agentwatch"})
        with self._opener(req, timeout=WEBHOOK_TIMEOUT_S) as r:
            if not 200 <= r.status < 300:
                raise RuntimeError(f"webhook status {r.status}")


class MultiPublisher:
    """Calls every publisher once; one failing channel never stops the others (Req 30.6)."""

    def __init__(self, publishers):
        self._pubs = list(publishers)

    @property
    def publishers(self) -> list:
        return list(self._pubs)

    def publish(self, subject: str, body: str) -> None:
        for p in self._pubs:
            try:
                p.publish(subject, body)
            except Exception as e:
                log.warning(json.dumps({"msg": "alert_publish_failed", "publisher": type(p).__name__,
                                        "error": type(e).__name__}))

