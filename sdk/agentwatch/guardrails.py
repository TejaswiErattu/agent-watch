"""Pure guardrail decisions: blocked-path matching (Req 8) and, later, the spend decision.

Two forms of every path are compared, both casefolded:
- Absolute_Path (lexical, keeps symlinks): catches a symlink *named* like a blocked entry.
- Normalized_Path (realpath, resolves symlinks): catches an alias that *points into* a blocked place.
Adding forms only adds candidate matches, so a second form can never turn a block into an allow.
"""

from __future__ import annotations

import os


def _seps() -> set[str]:
    return {"/", os.sep} | ({os.altsep} if os.altsep else set())


def absolute_path(p: str) -> str:
    """Absolute_Path: ~ expanded, made absolute, . and .. removed lexically. Symlinks kept."""
    return os.path.normpath(os.path.abspath(os.path.expanduser(p)))


def normalize_path(p: str) -> str:
    """Normalized_Path: ~ expanded and every symlink resolved."""
    return os.path.realpath(os.path.expanduser(p))


def path_forms(p: str) -> set[str]:
    """Path_Forms, already casefolded (Req 8.5, 8.6, 8.12)."""
    return {absolute_path(p).casefold(), normalize_path(p).casefold()}


def is_directory_entry(entry: str) -> bool:
    """An entry containing a separator names a place; otherwise it is a file name, anywhere."""
    return any(s in entry for s in _seps())
