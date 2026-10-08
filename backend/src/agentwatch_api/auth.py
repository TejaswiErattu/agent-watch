"""Credential parsing and constant-time matching (Req 14.8, 14.9, 25.1).

Key_Hash     = sha256(api_key)      sent by the SDK/dashboard as a header
Key_Verifier = sha256(Key_Hash)     the only thing ever stored
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

OWNER_HEADER = "x-agentwatch-owner"
KEY_HASH_HEADER = "x-agentwatch-key-hash"
OWNER_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
KEY_HASH_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class Credentials:
    owner_id: str
    key_hash: str = field(repr=False)  # never shown in repr/logs


def parse_credentials(headers: Mapping[str, Any] | None) -> Credentials | None:
    """Read the two credential headers case-insensitively. None if missing or malformed."""
    if not headers:
        return None
    lower = {str(k).lower(): v for k, v in headers.items()}
    owner = lower.get(OWNER_HEADER)
    key_hash = lower.get(KEY_HASH_HEADER)
    if not isinstance(owner, str) or not OWNER_RE.fullmatch(owner):
        return None
    if not isinstance(key_hash, str) or not KEY_HASH_RE.fullmatch(key_hash):
        return None
    return Credentials(owner_id=owner, key_hash=key_hash)


def key_verifier(key_hash: str) -> str:
    return hashlib.sha256(key_hash.encode("ascii")).hexdigest()


def matches(record: Any, creds: Credentials) -> bool:
    """True iff ownerId and Key_Verifier both match. The only compare_digest call site."""
    owner_ok = record.owner_id == creds.owner_id
    kv_ok = hmac.compare_digest(record.key_verifier, key_verifier(creds.key_hash))
    return owner_ok and kv_ok
