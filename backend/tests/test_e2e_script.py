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


# ---- 9.7: post-deploy verify script ----

VERIFY = SCRIPT.parent / "verify_deploy.sh"


def test_verify_script_reads_key_only_from_file_and_never_prints_it():
    assert VERIFY.is_file() and VERIFY.stat().st_mode & 0o111
    text = VERIFY.read_text()
    assert re.findall(r"\$\(cat ([^)]+)\)", text) == ["~/.agentwatch_key"]
    assert not re.search(r"\b[0-9a-f]{64}\b", text)
    assert not re.search(r"^\s*set\s+-[a-z]*x", text, re.MULTILINE)
    assert "print(key_hash" not in text and "print(os.environ" not in text
    assert '"blockedCommands" in keys' in text


# ---- v2 17.3: pause/resume step, rate limit excluded (Req 37.4) ----
# The pause runs on demo-bot: its loop catches every GuardrailBlocked, so a mid-run pause
# shows up as one "run N/20: AgentPaused" line. bad_agent.py has no loop to interrupt.

import subprocess


def _text() -> str:
    return SCRIPT.read_text()


def _on_exit() -> str:
    return _text().split("on_exit() {", 1)[1].split("\n}", 1)[0]


def test_script_parses_under_bash():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode == 0


def test_pause_step_is_a_real_mid_run_pause():
    text = _text()
    start = text.index('"$PYBIN" -u demo/demo_agent.py --loop 20 --sleep 2')   # -u: unbuffered, so lines appear live
    assert "&" in text[start:text.index("\n", start)]                            # runs in the background
    running = text.index('wait_for "$LOOP_LOG" "run 2/20 agent:"', start)       # loop is really running
    pause = text.index("set_paused demo-bot true", running)
    stopped = text.index('wait_for "$LOOP_LOG" "AgentPaused" "$PAUSE_MAX_S"', pause)
    stored = text.index('new_blocked demo-bot paused "$SINCE_PAUSE"', stopped)
    resume = text.index("set_paused demo-bot false", stored)
    again = text.index('run_agent "demo-bot: runs again after resume" "^agent:"', resume)
    cap = text.index('cfg_edit demo-bot cap "$CAP"')
    assert again < cap                                    # pause before the cap step, so the cap can't win


def test_pause_starts_from_a_clean_state():
    text = _text()
    start = text.index('"$PYBIN" -u demo/demo_agent.py --loop 20')
    before = text[:start]
    assert "cfg_edit demo-bot cap null" in before and "set_paused demo-bot false" in before


def test_pause_limit_covers_poll_sleep_and_one_call():
    sdk = (SCRIPT.parents[1] / "sdk" / "agentwatch" / "client.py").read_text()
    poll = float(re.search(r"^CONTROL_INTERVAL_S = ([0-9.]+)", sdk, re.MULTILINE).group(1))
    limit = int(re.search(r"^PAUSE_MAX_S=(\d+)$", _text(), re.MULTILINE).group(1))
    assert poll + 2 < limit <= 30                         # poll + --sleep 2, plus room for one LLM call


def test_set_paused_uses_the_status_route():
    text = _text()
    assert re.search(r'set_paused\(\) \{\n\s*aw_api PUT "/agents/\$1/status" "\{\\"paused\\": \$2\}"', text)


def test_exit_trap_stops_the_loop_and_resumes():
    body = _on_exit()
    kill, resume = body.index('kill "$LOOP_PID"'), body.index("set_paused demo-bot false")
    assert kill < resume                                  # stop the loop before resuming, or it keeps calling
    assert 'rm -f "$LOOP_LOG"' in body
    assert re.search(r'^LOOP_PID=""$', _text(), re.MULTILINE) and re.search(r'^LOOP_LOG=""$', _text(), re.MULTILINE)


def test_rate_limit_recorded_as_excluded():
    text = _text()
    header = text.split("\nset -uo pipefail", 1)[0]
    assert "Rate limit (group 12) is not covered" in header and "cut" in header
    for s in ("maxLlmCallsPerMinute", "RateLimitExceeded", '"rate"'):
        assert s not in text.replace(header, ""), s


def test_header_counts_four_alerts():
    header = _text().split("\nset -uo pipefail", 1)[0]
    assert "4 alerts" in header
