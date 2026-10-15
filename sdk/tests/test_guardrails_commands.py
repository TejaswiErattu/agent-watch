import logging
import re

import pytest

from agentwatch import guardrails
from agentwatch.guardrails import (
    COMMAND_ARG_NAMES,
    command_strings,
    compile_patterns,
    first_blocked_command,
)


@pytest.fixture(autouse=True)
def _clear_warned():
    guardrails._warned_patterns.clear()
    yield
    guardrails._warned_patterns.clear()


def test_command_arg_names():
    assert COMMAND_ARG_NAMES == ("command", "cmd", "args", "argv", "cmdline", "script", "shell_command")


def test_collapses_whitespace():
    assert command_strings([], ("  rm \t -rf\n /tmp  ",), {}) == ["rm -rf /tmp"]


def test_joins_all_str_lists_and_tuples():
    assert command_strings([], (["rm", "-rf", "/tmp/x"],), {"c": ("git", "push", "--force")}) == [
        "rm -rf /tmp/x", "git push --force"]


def test_skips_non_str_and_mixed_lists():
    assert command_strings([], (1, None, b"rm -rf /", ["rm", 1], {"a": "rm"}, 2.5), {"x": ["ok", None]}) == []


def test_drops_empties_and_duplicates():
    assert command_strings([], ("", "   ", [], "ls", " ls "), {"k": ["ls"]}) == ["ls"]


def test_named_command_args_come_first():
    out = command_strings(["sudo  reboot"], ("echo hi",), {"command": "sudo reboot", "z": "pwd"})
    assert out == ["sudo reboot", "echo hi", "pwd"]


def test_first_blocked_command_returns_string_and_pattern():
    compiled = compile_patterns([r"\bsudo\b", r"rm\s+-rf"])
    assert first_blocked_command(["echo hi", "rm -rf /", "sudo ls"], compiled) == ("rm -rf /", r"rm\s+-rf")


def test_first_blocked_command_none_when_nothing_matches():
    assert first_blocked_command(["ls -la", "echo hi"], compile_patterns([r"\bsudo\b"])) is None
    assert first_blocked_command([], compile_patterns([r"."])) is None
    assert first_blocked_command(["anything"], ()) is None


def test_first_string_wins_over_first_pattern():
    compiled = compile_patterns(["b", "a"])
    assert first_blocked_command(["xa", "xb"], compiled) == ("xa", "a")


def test_matching_is_case_insensitive():
    assert first_blocked_command(["SUDO Reboot"], compile_patterns([r"\bsudo\b"])) == ("SUDO Reboot", r"\bsudo\b")


def test_compile_patterns_keeps_order_and_ignorecase():
    compiled = compile_patterns(["b", "a"])
    assert [p for p, _ in compiled] == ["b", "a"]
    assert all(rx.flags & re.IGNORECASE for _, rx in compiled)


def test_bad_pattern_skipped_with_one_warning_per_pattern(caplog):
    caplog.set_level(logging.WARNING, logger="agentwatch")
    for _ in range(3):
        compiled = compile_patterns(["(", r"\bsudo\b", "[a-"])
        assert [p for p, _ in compiled] == [r"\bsudo\b"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert any("'('" in w for w in warnings) and any("'[a-'" in w for w in warnings)
    assert first_blocked_command(["sudo ls"], compiled) == ("sudo ls", r"\bsudo\b")
