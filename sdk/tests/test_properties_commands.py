import re

from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch.guardrails import command_strings, compile_patterns, first_blocked_command

# Patterns: literal words, \s+, \b, alternations, classes, plus a few hostile ones that don't compile.
atom = st.one_of(
    st.sampled_from(["rm", "sudo", "curl", "sh", "git", "push", "dd", "if=", "-rf", "--force"]),
    st.sampled_from([r"\s+", r"\b", r"[0-9]", r"(ba)?sh", r"(rm|del)", r"[|]", r".*"]),
)
good_pattern = st.lists(atom, min_size=1, max_size=4).map("".join)
hostile = st.sampled_from(["(", "[a-", "*x", "(?P<"])
patterns = st.lists(st.one_of(good_pattern, good_pattern, hostile), max_size=5)

word = st.sampled_from(["rm", "RM", "-rf", "/tmp", "sudo", "Sudo", "curl", "x", "|", "sh", "git",
                        "push", "--force", "ls", "dd", "if=/dev/zero", ""])
ws = st.sampled_from([" ", "  ", "\t", "\n", " \t "])
cmd_str = st.lists(st.tuples(word, ws), max_size=5).map(lambda xs: "".join(w + s for w, s in xs))
value = st.one_of(
    cmd_str,
    st.lists(word, max_size=4),
    st.lists(word, max_size=4).map(tuple),
    st.lists(st.one_of(word, st.integers()), max_size=3),  # mixed: skipped unless all str
    st.integers(), st.none(), st.binary(max_size=5), st.floats(allow_nan=False),
)


def _reference(named, args, kwargs, pats):
    """Independent restatement of Req 28.5/28.6: first candidate (named first) matched by any valid pattern."""
    def to_s(v):
        if isinstance(v, str):
            return " ".join(v.split())
        if isinstance(v, (list, tuple)) and all(isinstance(i, str) for i in v):
            return " ".join(" ".join(v).split())
        return None

    cands = []
    for v in (*named, *args, *kwargs.values()):
        s = to_s(v)
        if s and s not in cands:
            cands.append(s)
    valid = []
    for p in pats:
        try:
            valid.append((p, re.compile(p, re.IGNORECASE)))
        except re.error:
            pass
    for s in cands:
        for p, rx in valid:
            if rx.search(s):
                return s, p
    return None


# Feature: agent-watch-v2, Property 33: Blocked-command decision matches the reference rule (pure half)
@settings(max_examples=200)
@given(pats=patterns, named=st.lists(value, max_size=2), args=st.lists(value, max_size=4),
       kwargs=st.dictionaries(st.sampled_from(["a", "b", "command", "cmd"]), value, max_size=3))
def test_property_33_pure_decision_matches_reference(pats, named, args, kwargs):
    got = first_blocked_command(command_strings(named, tuple(args), kwargs), compile_patterns(pats))
    assert got == _reference(named, tuple(args), kwargs, pats)
