"""Watcher, API client, and background sender.

Secrets: the plaintext API_Key is hashed on entry and never stored. The Key_Hash is kept
only in private fields that are excluded from repr, and is never passed to the logger.
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

REQUEST_TIMEOUT_S = 2.0
_log = logging.getLogger("agentwatch")


def key_hash(api_key: str) -> str:
    """Key_Hash = lowercase hex SHA-256 of the UTF-8 API_Key. The server only ever sees this."""
    if not isinstance(api_key, str) or not api_key:
        raise ValueError("api_key must be a non-empty string")
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


class GuardrailBlocked(Exception):
    """Raised before a blocked action runs. `violation_type` is "spend_cap" or "blocked_path"."""

    def __init__(self, violation_type: str, detail: str) -> None:
        super().__init__(f"agentwatch blocked ({violation_type}): {detail}")
        self.violation_type = violation_type
        self.detail = detail


class SpendCapExceeded(GuardrailBlocked):
    def __init__(self, detail: str) -> None:
        super().__init__("spend_cap", detail)


class PathBlocked(GuardrailBlocked):
    def __init__(self, detail: str) -> None:
        super().__init__("blocked_path", detail)


@dataclass(frozen=True)
class Credentials:
    """ownerId plus Key_Hash. The plaintext key is never kept; repr hides the hash."""

    owner_id: str
    key_hash: str = field(repr=False)

    @classmethod
    def from_api_key(cls, owner_id: str, api_key: str) -> "Credentials":
        return cls(owner_id, key_hash(api_key))


# ---- HTTP transport and ApiClient (task 3.3) ----


class TransportError(Exception):
    """Network-level failure: connection error or timeout. Carries no request data."""


@dataclass(frozen=True)
class Response:
    status: int
    body: Any  # parsed JSON, or None if the body was not JSON


class Transport(Protocol):
    def request(self, method: str, url: str, *, headers: dict, json: Any = None, timeout: float) -> Response: ...


class RequestsTransport:
    """Default transport over a requests.Session (connection reuse across events)."""

    def __init__(self, session=None) -> None:
        if session is None:
            import requests

            session = requests.Session()
        self.session = session

    def request(self, method, url, *, headers, json=None, timeout):
        import requests

        try:
            r = self.session.request(method, url, headers=headers, json=json, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            # Type name only: requests' messages can include the full URL and headers.
            raise TransportError(type(e).__name__) from None
        try:
            body = _json.loads(r.text) if r.text else None
        except ValueError:
            body = None
        return Response(r.status_code, body)


class ApiClient:
    """Thin HTTP client for the Ingestion_API. Every request carries the credential headers."""

    def __init__(self, endpoint: str, owner_id: str, key_hash: str, transport: Transport | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.owner_id = owner_id
        self._key_hash = key_hash
        self.transport = transport if transport is not None else RequestsTransport()

    def __repr__(self) -> str:
        return f"ApiClient(endpoint={self.endpoint!r}, owner_id={self.owner_id!r})"

    def _headers(self) -> dict:
        return {"X-Agentwatch-Owner": self.owner_id, "X-Agentwatch-Key-Hash": self._key_hash}

    def _call(self, method: str, path: str, body=None) -> Response:
        return self.transport.request(method, self.endpoint + path, headers=self._headers(),
                                      json=body, timeout=REQUEST_TIMEOUT_S)

    def post_event(self, event: dict) -> Response:
        return self._call("POST", "/events", event)

    def get_config(self, agent_id: str) -> Response:
        return self._call("GET", f"/agents/{agent_id}/config")

    def get_spend(self, agent_id: str) -> Response:
        return self._call("GET", f"/agents/{agent_id}/spend")


# ---- retry policy (task 3.4) ----

BACKOFF_S = (0.5, 1, 2)  # 3 retries after the first attempt
AUTH_FAILED_MSG = "agentwatch: authorization failed (check owner_id/api_key)"
_auth_warned = False  # per process: a wrong key would otherwise log on every event


def _retryable(resp: Response) -> bool:
    return resp.status == 429 or resp.status >= 500


def send_with_retries(api, event: dict, sleep: Callable[[float], None]) -> bool:
    """POST one event. True on 2xx. Never raises; the agent always continues (Req 2.3, 2.6)."""
    global _auth_warned
    event_id = event.get("eventId")
    for attempt in range(len(BACKOFF_S) + 1):
        if attempt:
            sleep(BACKOFF_S[attempt - 1])
        try:
            resp = api.post_event(event)
        except TransportError:
            continue
        except Exception as e:  # a bug in a transport must not crash the agent
            _log.warning("agentwatch: unexpected send error %s for event %s", type(e).__name__, event_id)
            return False
        if 200 <= resp.status < 300:
            return True
        if resp.status in (401, 403):
            if not _auth_warned:
                _auth_warned = True
                _log.warning(AUTH_FAILED_MSG)
            return False
        if resp.status == 400:
            msg = resp.body.get("error") if isinstance(resp.body, dict) else None
            _log.warning("agentwatch: event %s rejected: %s", event_id, msg)
            return False
        if not _retryable(resp):  # other 4xx (404, 413...): retrying will not help
            _log.warning("agentwatch: event %s rejected with status %s", event_id, resp.status)
            return False
    _log.warning("agentwatch: giving up on event %s after %d attempts", event_id, len(BACKOFF_S) + 1)
    return False
