"""Watcher, API client, and background sender.

Secrets: the plaintext API_Key is hashed on entry and never stored. The Key_Hash is kept
only in private fields that are excluded from repr, and is never passed to the logger.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


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
