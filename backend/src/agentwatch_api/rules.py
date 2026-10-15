"""Guardrail_Config parsing and serialization (Req 21.6, 22.4)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from .validation import ValidationError

MAX_PATHS = 100
MAX_PATH_LEN = 1024
MAX_COMMANDS = 100
MAX_COMMAND_LEN = 256
KEYS = ("dailySpendCapUsd", "blockedPaths", "blockedCommands")
REQUIRED_KEYS = ("dailySpendCapUsd", "blockedPaths")  # v1 bodies stay valid (Req 36.1)


@dataclass(frozen=True)
class GuardrailConfig:
    daily_spend_cap_usd: float | None
    blocked_paths: tuple[str, ...]
    blocked_commands: tuple[str, ...] = ()  # Req 28.1; default keeps positional v1 calls valid


EMPTY_CONFIG = GuardrailConfig(daily_spend_cap_usd=None, blocked_paths=())


def _parse_commands(cmds: Any) -> tuple[str, ...] | ValidationError:
    """Req 28.2. The re.error text is never echoed: it can quote the pattern back in odd ways."""
    if not isinstance(cmds, list):
        return ValidationError("blockedCommands", "must be a list of strings")
    if len(cmds) > MAX_COMMANDS:
        return ValidationError("blockedCommands", f"must have at most {MAX_COMMANDS} entries")
    for i, p in enumerate(cmds):
        if not isinstance(p, str) or p == "":
            return ValidationError("blockedCommands", "entries must be non-empty strings")
        if len(p) > MAX_COMMAND_LEN:
            return ValidationError("blockedCommands", f"entries must be at most {MAX_COMMAND_LEN} chars")
        try:
            re.compile(p, re.IGNORECASE)
        except re.error:
            return ValidationError("blockedCommands", f"entry {i} is not a valid regular expression")
    return tuple(cmds)


def parse_config(obj: Any) -> GuardrailConfig | ValidationError:
    """Parse a Guardrail_Config JSON object. v1 keys are required, new keys default; unknown keys are rejected."""
    if not isinstance(obj, dict):
        return ValidationError("body", "must be a JSON object")
    for k in sorted(obj.keys() - set(KEYS), key=str):
        return ValidationError(str(k), "unknown field")
    for k in REQUIRED_KEYS:
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

    commands = _parse_commands(obj.get("blockedCommands", []))
    if isinstance(commands, ValidationError):
        return commands

    return GuardrailConfig(daily_spend_cap_usd=cap, blocked_paths=tuple(paths), blocked_commands=commands)


def to_json(cfg: GuardrailConfig) -> dict:
    """Always emits every key (Req 28.3, 36.2)."""
    return {
        "dailySpendCapUsd": cfg.daily_spend_cap_usd,
        "blockedPaths": list(cfg.blocked_paths),
        "blockedCommands": list(cfg.blocked_commands),
    }
