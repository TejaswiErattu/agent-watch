"""Filesystem properties for the path blocklist (24 to 27). Trees live under tmp_path."""

import os
import tempfile

from hypothesis import given, settings, strategies as st

from agentwatch.guardrails import blocked_entry_for, normalize_path

# Names with case-sensitive and non-ASCII letters; no separators, no "." / ".." names.
name_chars = st.sampled_from(list("abcxyzABCXYZ_-.") + ["ß", "É", "é", "ü", " "])
name = st.text(name_chars, min_size=1, max_size=8).filter(lambda s: s not in {".", ".."} and s.strip() == s)


def swap_case(s: str, mask: list[bool]) -> str:
    return "".join(c.swapcase() if (mask[i % len(mask)] if mask else False) else c for i, c in enumerate(s))


# Feature: agent-watch, Property 26: Sibling prefixes are not blocked
@settings(max_examples=100, deadline=None)
@given(parts=st.lists(name, min_size=1, max_size=3), suffix=name)
def test_property_26_sibling_prefixes_not_blocked(parts, suffix):
    with tempfile.TemporaryDirectory() as root:
        e = os.path.join(root, *parts)
        attempted = normalize_path(e) + suffix
        assert blocked_entry_for(attempted, [e]) is None


# Feature: agent-watch, Property 27: Case changes do not change the decision
@settings(max_examples=100, deadline=None)
@given(
    dirs=st.lists(name, min_size=1, max_size=3),
    leaf=name,
    entries=st.lists(st.one_of(name.map(lambda n: ("name", n)),
                               st.integers(0, 3).map(lambda k: ("dir", k))), max_size=4),
    mask_p=st.lists(st.booleans(), min_size=1, max_size=6),
    mask_e=st.lists(st.booleans(), min_size=1, max_size=6),
)
def test_property_27_case_changes_keep_decision(dirs, leaf, entries, mask_p, mask_e):
    with tempfile.TemporaryDirectory() as root:
        root = os.path.realpath(root)  # symlink-free base (macOS /var -> /private/var)
        p = os.path.join(root, *dirs, leaf)
        blocked = []
        for kind, v in entries:
            if kind == "name":
                blocked.append(v)
            else:  # a directory entry: some ancestor of p (or root itself)
                blocked.append(os.path.join(root, *dirs[: min(v, len(dirs))]))
        base = blocked_entry_for(p, blocked) is not None
        # Change case only below root, so the tmp root's own spelling is untouched.
        rel = os.path.relpath(p, root)
        p2 = os.path.join(root, swap_case(rel, mask_p))
        blocked2 = [swap_case(b, mask_e) if os.sep not in b else
                    os.path.join(root, swap_case(os.path.relpath(b, root), mask_e)) for b in blocked]
        assert (blocked_entry_for(p2, blocked2) is not None) == base
