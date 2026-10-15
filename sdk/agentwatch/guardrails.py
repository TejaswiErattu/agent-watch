"""Pure guardrail decisions: blocked-path matching (Req 8) and, later, the spend decision.

Two forms of every path are compared, both folded (NFC + casefold):
- Absolute_Path (lexical, keeps symlinks): catches a symlink *named* like a blocked entry.
- Normalized_Path (realpath, resolves symlinks): catches an alias that *points into* a blocked place.
Adding forms only adds candidate matches, so a second form can never turn a block into an allow.
An existing Directory_Entry also matches by (st_dev, st_ino) against the path and its parents,
which catches aliases no string form sees (macOS firmlinks, bind mounts). That too only adds blocks.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata


def _seps() -> set[str]:
    return {"/", os.sep} | ({os.altsep} if os.altsep else set())


def absolute_path(p: str) -> str:
    """Absolute_Path: ~ expanded, made absolute, . and .. removed lexically. Symlinks kept."""
    return os.path.normpath(os.path.abspath(os.path.expanduser(p)))


def normalize_path(p: str) -> str:
    """Normalized_Path: ~ expanded and every symlink resolved."""
    return os.path.realpath(os.path.expanduser(p))


def fold(s: str) -> str:
    """Case_Fold: NFC first, so an NFD name (common on macOS) equals its NFC spelling."""
    return unicodedata.normalize("NFC", s).casefold()


def path_forms(p: str) -> set[str]:
    """Path_Forms, already folded (Req 8.5, 8.6, 8.12)."""
    return {fold(absolute_path(p)), fold(normalize_path(p))}


def _file_id(p: str):
    try:
        st = os.stat(p)  # follows symlinks, so an alias reports its target's identity
    except (OSError, ValueError):
        return None
    return (st.st_dev, st.st_ino)


def _ancestor_ids(p: str) -> set:
    """(st_dev, st_ino) of p and every existing parent. Catches firmlinks and bind mounts (Req 8.15)."""
    ids, cur = set(), absolute_path(p)
    while True:
        fid = _file_id(cur)
        if fid is not None:
            ids.add(fid)
        parent = os.path.dirname(cur)
        if parent == cur:
            return ids
        cur = parent


def _components(form: str) -> list[str]:
    parts = [form]
    for s in _seps():
        parts = [x for part in parts for x in part.split(s)]
    return [x for x in parts if x]


def is_directory_entry(entry: str) -> bool:
    """An entry containing a separator names a place; otherwise it is a file name, anywhere."""
    return any(s in entry for s in _seps())


def _under(a: str, e: str) -> bool:
    """a is e or inside e. The separator boundary keeps /a/bc out of /a/b; "/" blocks everything."""
    prefix = e if e.endswith(os.sep) else e + os.sep
    return a == e or a.startswith(prefix)


class _Attempt:
    """An attempted path's forms, computed once and shared across entries. Inode ids are lazy."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.forms = path_forms(path)  # may raise (e.g. NUL byte); the caller fails closed
        self._ids = None

    @property
    def ids(self) -> set:
        if self._ids is None:
            self._ids = _ancestor_ids(self.path)
        return self._ids


def _matches(att: _Attempt, entry: str) -> bool:
    if is_directory_entry(entry):
        if any(_under(a, e) for a in att.forms for e in path_forms(entry)):
            return True
        eid = _file_id(os.path.expanduser(entry))  # only an existing entry has an identity
        return eid is not None and eid in att.ids
    name = fold(entry)  # Name_Entry: any component, any directory (".git" blocks ".git/config")
    return any(name in _components(a) for a in att.forms)


def path_matches(attempted: str, entry: str) -> bool:
    return _matches(_Attempt(attempted), entry)


def blocked_entry_for(path: str, blocked_paths) -> str | None:
    """The first Blocked_Path that matches `path`, or None if the access is allowed."""
    att = _Attempt(path)
    for entry in blocked_paths:
        if _matches(att, entry):
            return entry
    return None


def spend_decision(local_total: float, est_cost: float, cap: float) -> str:
    """"block" iff local_total + est_cost > cap; exactly reaching the cap is allowed (Req 7.6, 7.7)."""
    return "block" if local_total + est_cost > cap else "allow"


# ---- Blocked_Command matching (Req 28.5, 28.6, 28.8) ----

COMMAND_ARG_NAMES = ("command", "cmd", "args", "argv", "cmdline", "script", "shell_command")

_log = logging.getLogger("agentwatch")
# Patterns already warned about. Module-level: "once per pattern per process" (Req 28.8).
_warned_patterns: set[str] = set()


def _command_string(v) -> str | None:
    """A str, or an all-str list/tuple joined by spaces, with whitespace collapsed. Anything else: None."""
    if isinstance(v, str):
        s = v
    elif isinstance(v, (list, tuple)) and all(isinstance(i, str) for i in v):
        s = " ".join(v)
    else:
        return None
    return " ".join(s.split())


def command_strings(named, args, kwargs) -> list[str]:
    """Command_Strings in candidate order: named command args first, then every positional and
    keyword value. Empty strings and duplicates are dropped (Req 28.5)."""
    out: list[str] = []
    for v in (*named, *args, *kwargs.values()):
        s = _command_string(v)
        if s and s not in out:
            out.append(s)
    return out


def compile_patterns(patterns) -> tuple:
    """((pattern, compiled), ...) in order. A pattern that doesn't compile is skipped and warned once."""
    out = []
    for p in patterns:
        try:
            out.append((p, re.compile(p, re.IGNORECASE)))
        except (re.error, TypeError):
            if p not in _warned_patterns:
                _warned_patterns.add(p)
                _log.warning("agentwatch: skipping blocked command pattern %r (does not compile)", p)
    return tuple(out)


def first_blocked_command(strings, compiled) -> tuple[str, str] | None:
    """(string, pattern) for the first string (in order) that any pattern matches, else None."""
    for s in strings:
        for p, rx in compiled:
            if rx.search(s):
                return s, p
    return None
