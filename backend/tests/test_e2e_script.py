"""Static checks on scripts/e2e.sh: the API key comes only from ~/.agentwatch_key and is never exposed."""

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "e2e.sh"
KEY_READ = 'AGENTWATCH_KEY="$(cat ~/.agentwatch_key)"'


def _code_lines() -> list[str]:
    """Script lines with full-line comments dropped."""
    return [line for line in SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#")]


def test_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111


def test_key_is_assigned_only_from_the_key_file():
    assignments = [line.strip() for line in _code_lines() if re.search(r"\bAGENTWATCH_KEY=", line)]
    assert assignments == [KEY_READ]
    # The key file is the only file read with cat.
    assert re.findall(r"\$\(cat ([^)]+)\)", SCRIPT.read_text()) == ["~/.agentwatch_key"]


def test_no_literal_key_or_hash():
    text = SCRIPT.read_text()
    assert not re.search(r"\b[0-9a-f]{64}\b", text)            # no Key_Hash
    assert not re.search(r"(?i)x-agentwatch-key-hash:\s*[0-9a-f]", text)


def test_key_is_never_echoed_logged_or_written():
    for line in _code_lines():
        uses_key = re.search(r"\$\{?AGENTWATCH_KEY\b|\$\{?key_hash\b", line)
        if uses_key:
            # Only allowed uses: export, and the emptiness check.
            assert re.match(r"\s*(export AGENTWATCH_KEY$|\[\[ -n \"\$AGENTWATCH_KEY\" \]\])", line), line
    text = SCRIPT.read_text()
    assert not re.search(r"^\s*set\s+-[a-z]*x", text, re.MULTILINE)  # no xtrace
    assert "~/.agentwatch_key" not in "".join(l for l in _code_lines() if re.search(r">\s*~/", l))
    assert "print(key_hash" not in text and "print(os.environ" not in text


# ---- 9.6: shell-command step (Req 28.16, 37.4) ----

def test_cfg_edit_supports_command_ops():
    text = SCRIPT.read_text()
    assert '"add-command"' in text and '"remove-command"' in text
    assert 'g.setdefault("blockedCommands", [])' in text


def test_shell_step_adds_pipe_to_shell_and_expects_both_blocks():
    text = SCRIPT.read_text()
    # The pattern comes from the presets file, never retyped in the script.
    assert "commandPresets.json" in text and '"pipe_to_shell"' in text
    assert re.search(r"cfg_edit bad-bot add-command \"\$PIPE_TO_SHELL\"", text)
    assert '"bad-bot: CommandBlocked" "CommandBlocked"' in text
    assert re.search(r"new_blocked bad-bot blocked_command", text)


def test_exit_trap_removes_the_command():
    body = SCRIPT.read_text().split("on_exit() {", 1)[1].split("\n}", 1)[0]
    assert 'cfg_edit bad-bot remove-command "$PIPE_TO_SHELL"' in body
