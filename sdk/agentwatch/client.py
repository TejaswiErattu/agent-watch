"""Watcher, API client, and background sender.

Secrets: the plaintext API_Key is hashed on entry and never stored. The Key_Hash is kept
only in private fields that are excluded from repr, and is never passed to the logger.
"""

from __future__ import annotations

import hashlib
import json as _json
from dataclasses import dataclass, field
from typing import Any, Protocol

REQUEST_TIMEOUT_S = 2.0


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
