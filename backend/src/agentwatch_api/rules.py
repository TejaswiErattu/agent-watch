"""Guardrail_Config parsing and serialization (Req 21.6, 22.4)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .validation import ValidationError

MAX_PATHS = 100
MAX_PATH_LEN = 1024
KEYS = ("dailySpendCapUsd", "blockedPaths")


@dataclass(frozen=True)
class GuardrailConfig:
    daily_spend_cap_usd: float | None
    blocked_paths: tuple[str, ...]


EMPTY_CONFIG = GuardrailConfig(daily_spend_cap_usd=None, blocked_paths=())


def parse_config(obj: Any) -> GuardrailConfig | ValidationError:
    """Parse a full Guardrail_Config JSON object. Both keys are required; unknown keys are rejected."""
    if not isinstance(obj, dict):
        return ValidationError("body", "must be a JSON object")
    for k in sorted(obj.keys() - set(KEYS), key=str):
        return ValidationError(str(k), "unknown field")
    for k in KEYS:
        if k not in obj:
            return ValidationError(k, "is required")

    cap = obj["dailySpendCapUsd"]
    if cap is not None and (
        isinstance(cap, bool) or not isinstance(cap, (int, float)) or not math.isfinite(cap) or cap < 0
    ):
        return ValidationError("dailySpendCapUsd", "must be null or a finite number >= 0")

    paths = obj["blockedPaths"]
    if not isinstance(paths, list):
        return ValidationError("blockedPaths", "must be a list of strings")
    if len(paths) > MAX_PATHS:
        return ValidationError("blockedPaths", f"must have at most {MAX_PATHS} entries")
    for p in paths:
        if not isinstance(p, str) or p == "":
            return ValidationError("blockedPaths", "entries must be non-empty strings")
        if len(p) > MAX_PATH_LEN:
            return ValidationError("blockedPaths", f"entries must be at most {MAX_PATH_LEN} chars")

    return GuardrailConfig(daily_spend_cap_usd=cap, blocked_paths=tuple(paths))


def to_json(cfg: GuardrailConfig) -> dict:
    return {"dailySpendCapUsd": cfg.daily_spend_cap_usd, "blockedPaths": list(cfg.blocked_paths)}
