"""Alert email formatting and a publish call that never raises (Req 10.3, 10.5, 10.8)."""

from __future__ import annotations

import json
import logging

from .validation import Event

log = logging.getLogger("agentwatch_api.alerts")

SUBJECT_MAX = 100  # SNS email Subject: ASCII, no newlines, <= 100 chars


def _clean(s: str) -> str:
    """Escape control chars so an attacker-chosen path can't forge lines in the email."""
    return "".join(c if c.isprintable() else repr(c)[1:-1] for c in s)


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
    if violation == "spend_cap":
        lines.append(f"attemptedCostUsd: {item['attemptedCostUsd']!r}")
    else:
        lines.append(f"attemptedPath: {_clean(item['attemptedPath'])}")
    meta = item.get("meta") or {}
    for key in ("tool", "entry"):
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
