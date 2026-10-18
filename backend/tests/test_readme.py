"""Repo docs checks (Req 26). Wording is reviewed by hand; these pin the must-say facts."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"


def _section(text: str, heading: str) -> str:
    """Body of the markdown section whose heading matches, up to the next heading of the same or higher level."""
    m = re.search(rf"^(#+)\s*{re.escape(heading)}\s*$", text, re.MULTILINE | re.IGNORECASE)
    assert m, f"missing heading: {heading}"
    level = len(m.group(1))
    rest = text[m.end():]
    nxt = re.search(rf"^#{{1,{level}}}\s", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def test_readme_known_limitations():
    body = _section(README.read_text(), "Known limitations").lower()
    assert "open()" in body                      # 26.2: direct open() not covered
    assert "shell command" in body               # 26.2: shell commands not covered
    for name in ("path", "file_path", "filepath", "filename", "file",
                 "src", "dst", "source", "destination", "target_path"):
        assert f"`{name}`" in body, name         # 26.2: recognized path arguments
    assert "under-count" in body and "queued" in body   # 26.3
    assert "case-insensitive" in body            # over-blocking note
    assert "hardlink" in body and "toctou" in body
    assert "first-come" in body


def test_readme_core_sections():
    text = README.read_text()
    assert "aw = agentwatch.init(" in text and "aw.wrap(client)" in text and "aw.tools(TOOLS)" in text
    assert "sam deploy" in text
    assert "amplify" in text.lower()
    assert "bad_agent.py" in text and "demo_agent.py" in text
    assert "npx vitest --run" in text and "pytest" in text


DOCS = ROOT / "docs"


def test_submission_docs_exist_with_title():
    for name in ("ARCHITECTURE.md", "DEMO_SCRIPT.md", "SUBMISSION.md"):
        text = (DOCS / name).read_text()
        assert re.search(r"^# \S", text, re.MULTILINE), name


def test_demo_script_covers_both_demo_moments():
    text = (DOCS / "DEMO_SCRIPT.md").read_text()
    assert "bad_agent.py" in text and ".env" in text
    assert "demo_agent.py --loop" in text and "SpendCapExceeded" in text


def test_submission_lists_next_steps():
    body = _section((DOCS / "SUBMISSION.md").read_text(), "Next steps").lower()
    for item in ("multi-framework", "auth", "mobile", "anomaly detection", "risk scoring"):
        assert item in body, item


KEY_FROM_FILE = 'AGENTWATCH_KEY="$(cat ~/.agentwatch_key)"'


def test_demo_script_prep_reads_key_from_file():
    text = (DOCS / "DEMO_SCRIPT.md").read_text()
    prep = _section(text, "Before recording (about 5 min, off camera)")
    step1 = next(line for line in prep.splitlines() if line.startswith("1."))
    assert KEY_FROM_FILE in step1
    assert "<your-key>" not in text


def test_demo_script_inventory_lists_real_columns():
    # Must match the <TableHead> labels in dashboard/components/InventoryTable.tsx.
    on_camera = _section((DOCS / "DEMO_SCRIPT.md").read_text(), "On camera")
    step3 = next(line for line in on_camera.splitlines() if line.startswith("3."))
    for col in ("Agent", "Model", "Last activity", "Total spend"):
        assert f"**{col}**" in step3, col
    assert "first and last seen" not in step3


def test_docs_contain_no_live_secrets():
    # The demo key lives outside the repo; docs use placeholders or read it from ~/.agentwatch_key.
    for path in [README, *DOCS.glob("*.md")]:
        text = path.read_text().replace(KEY_FROM_FILE, "AGENTWATCH_KEY=<from-file>")
        assert not re.search(r"AGENTWATCH_KEY=(?!<)[^\s`]+", text), path.name
        assert not re.search(r"\b[0-9a-f]{64}\b", text), path.name


# ---- v2 11.2: webhook alerts (Req 30.8, 30.9) ----

WEBHOOK_URL_RE = re.compile(r"https://(discord(app)?\.com/api/webhooks|hooks\.slack\.com/services)/[^\s<`]*[0-9A-Za-z_-]{20,}")


def test_readme_webhook_section():
    body = _section(README.read_text(), "Webhook alerts")
    for s in ("Discord", "Slack", "AlertWebhookUrl", "UsePreviousValue", "DISCORD_WEBHOOK_URL"):
        assert s in body, s


def test_webhook_url_never_in_repo_config_or_docs():
    samconfig = (ROOT / "backend" / "samconfig.toml").read_text()
    assert "AlertWebhookUrl" not in samconfig and "webhook" not in samconfig.lower()
    for path in [README, *DOCS.glob("*.md"), ROOT / "PROGRESS.md"]:
        assert not WEBHOOK_URL_RE.search(path.read_text()), path.name


# ---- v2 17.1: README, ARCHITECTURE, SUBMISSION (Req 37.1, 37.2, 37.5) ----
# Groups 12 (rate limit) and 13 (CLI) were cut, so their features must appear only as
# excluded, never as shipped. The exception list is the one the SDK actually exports.

SHIPPED_EXCEPTIONS = ("PathBlocked", "SpendCapExceeded", "AgentPaused", "CommandBlocked", "GuardrailBlocked")
CUT_FEATURES = ("maxLlmCallsPerMinute", "RateLimitExceeded", "agentwatch init", "agentwatch doctor")


def test_readme_documents_shipped_v2_features():
    text = README.read_text()
    for s in ("blockedCommands", "Pause agent", "Confirm pause", "Resume agent", "Add presets",
              "Webhook alerts", "Discord", "SNS"):
        assert s in text, s
    for name in SHIPPED_EXCEPTIONS:
        assert f"`agentwatch.{name}`" in text or f"`{name}`" in text, name


def test_readme_exports_match_the_sdk():
    init = (ROOT / "sdk" / "agentwatch" / "__init__.py").read_text()
    for name in SHIPPED_EXCEPTIONS:
        assert f'"{name}"' in init, name           # the README never names an exception the SDK lacks
    assert "RateLimitExceeded" not in init


def test_readme_names_cut_features_only_as_excluded():
    text = README.read_text()
    excluded = _section(text, "Not in this release")
    for s in ("maxLlmCallsPerMinute", "agentwatch init"):
        assert s in excluded, s
    assert "not implemented" in excluded.lower()
    outside = text.replace(excluded, "")
    for s in CUT_FEATURES:
        assert s not in outside, f"{s} appears outside 'Not in this release'"


def test_readme_known_limitations_v2():
    body = _section(README.read_text(), "Known limitations").lower()
    assert "over-block" in body and "blockedcommands" in body       # 37.1: regex over-blocking
    assert "pause" in body and "5 s" in body                        # 37.1: pause propagation
    assert "env_file" in body                                       # blockedPaths does not cover shell strings
    assert "plaintext" in body and "lambda" in body                 # NoEcho does not hide the env value


def test_readme_webhook_secret_never_on_the_command_line():
    body = _section(README.read_text(), "Webhook alerts")
    assert 'AlertWebhookUrl="$' not in body and "ParameterValue=\"$" not in body   # argv is visible to ps
    assert "never into a file" not in body
    assert "file://" in body and "0600" in body and "rm " in body   # restricted temp parameters file, deleted


def test_readme_documents_verification_scripts():
    body = _section(README.read_text(), "Verify a deployment")
    assert "scripts/verify_deploy.sh" in body and "scripts/e2e.sh" in body
    assert "alert" in body.lower()                                  # e2e sends real alerts


def test_architecture_covers_v2():
    text = (DOCS / "ARCHITECTURE.md").read_text()
    assert "GET /agents/{agentId}/status" in text and "PUT /agents/{agentId}/status" in text
    assert "control plane" in text.lower() and "rules plane" in text.lower()
    assert "MultiPublisher" in text and "WebhookPublisher" in text


def test_submission_v2_moments_and_next_steps():
    text = (DOCS / "SUBMISSION.md").read_text()
    what = _section(text, "What it does")
    for s in ("Pause", "CommandBlocked", "spend chart", "Discord"):
        assert s.lower() in what.lower(), s
    nxt = _section(text, "Next steps").lower()
    for shipped in ("kill switch", "shell-command guard", "webhook alerts", "discord"):
        assert shipped not in nxt, shipped                          # Next steps drops what shipped
    for cut in ("rate limit", "cli"):
        assert cut in nxt, cut                                      # cut features stay future work


def _bash_blocks(body: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", body, re.DOTALL)


def test_readme_change_set_is_reviewed_approved_then_executed():
    body = _section(README.read_text(), "Webhook alerts")
    assert "only if nothing is replaced" not in body                 # Modify without replacement can still be unsafe
    review = body.index("Review the complete change set")
    approve = body.index("Get approval for this change set")
    execute = body.index("execute-change-set")
    assert review < approve < execute                               # prepare, review, approve, then execute
    assert "approved for this deployment" in body                   # compared against an explicit list
    for s in ("Action", "Replacement", "Scope", "Details"):
        assert s in body, s                                         # the review query shows the full change rows
    assert "--include-property-values" in body                      # warned against: it can print the URL
    assert "one-time exception" in body and "not a standing authorization" in body
    prepare = _bash_blocks(body[:review])
    assert prepare and not any("execute-change-set" in b for b in prepare)   # preparing never executes


def test_readme_webhook_temp_file_cleaned_on_failure():
    body = _section(README.read_text(), "Webhook alerts")
    prepare = next(b for b in _bash_blocks(body) if "mktemp" in b)
    assert "trap 'rm -f \"$PARAMS\"' EXIT" in prepare               # removed if interrupted
    assert "set -e" not in prepare                                  # zsh skips the EXIT trap when set -e ends a subshell
    cleanup = prepare.index('rm -f "$PARAMS"                     #')
    assert prepare.index("create-change-set") < cleanup              # removed right after the call, success or failure


# ---- 17.1 review: run the README's "Prepare the change set" block offline ----
# The exact block is extracted from README.md and run with stubbed sam, aws, and mktemp in a
# temp directory. No AWS call, no real secret, nothing outside tmp_path is touched.

import os
import shutil
import subprocess
import sys

import pytest

DUMMY = "DUMMYWEBHOOKVALUEFORTESTONLY"

HARNESS = r'''
LOG="$TESTDIR/calls.log"; : > "$LOG"; : > "$TESTDIR/paramsfile"
sam() {
  printf 'sam %s\n' "$*" >> "$LOG"
  case "$1" in
    build) [ "$MODE" = build_fail ] && return 1 ;;
    package) [ "$MODE" = package_fail ] && return 1
             mkdir -p .aws-sam && echo FRESH > .aws-sam/packaged.yaml ;;
  esac
  return 0
}
mktemp() { p="$(command mktemp "$@")"; echo "$p" > "$TESTDIR/paramsfile"; echo "$p"; }
aws() {
  all="$*"; printf 'aws %s\n' "$all" >> "$LOG"
  case "$all" in
    *create-change-set*)
      f="${all##*file://}"; f="${f%% *}"
      python3 -c 'import os,sys; print("mode", oct(os.stat(sys.argv[1]).st_mode & 0o777))' "$f" >> "$LOG"
      echo "template $(cat .aws-sam/packaged.yaml)" >> "$LOG"
      [ "$MODE" = aws_fail ] && return 255
      [ "$MODE" = signal ] && { sh -c 'kill -TERM $PPID'; sleep 1; } ;;
  esac
  return 0
}
. "$TESTDIR/block.sh"
'''


def _prepare_block() -> str:
    body = _section(README.read_text(), "Webhook alerts")
    block = next(b for b in _bash_blocks(body) if "mktemp" in b)
    # The README indents the block under a list item; the rendered copy has no indent.
    return "\n".join(line[3:] if line.startswith("   ") else line for line in block.splitlines()) + "\n"


SHELLS = [s for s in ("bash", "zsh") if shutil.which(s)]


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("mode", ["ok", "build_fail", "package_fail", "aws_fail", "signal"])
def test_readme_prepare_block_offline(tmp_path, shell, mode):
    (tmp_path / "block.sh").write_text(_prepare_block())
    (tmp_path / "harness.sh").write_text(HARNESS)
    work = tmp_path / "backend"
    (work / ".aws-sam").mkdir(parents=True)
    (work / ".aws-sam" / "packaged.yaml").write_text("STALE")      # an older package must never be used
    env = {**os.environ, "TESTDIR": str(tmp_path), "MODE": mode, "DISCORD_WEBHOOK_URL": f"https://discord.com/api/webhooks/1/{DUMMY}",
           "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")}
    rc = subprocess.run([shell, str(tmp_path / "harness.sh")], cwd=work, env=env, capture_output=True, text=True, timeout=30).returncode
    log = (tmp_path / "calls.log").read_text()
    params = (tmp_path / "paramsfile").read_text().strip()

    assert DUMMY not in log                                          # the value never reaches any command's arguments
    assert "STALE" not in log                                        # never packaged from an older template
    if mode in ("build_fail", "package_fail"):
        assert rc != 0
        assert "aws " not in log and params == ""                    # stopped before the secret file or any AWS call
        assert not (work / ".aws-sam" / "packaged.yaml").exists()    # the stale package was removed, not reused
        return
    assert "template FRESH" in log and "mode 0o600" in log
    assert params and not os.path.exists(params)                     # temp file gone: success, failure, or signal
    if mode == "ok":
        assert rc == 0 and "change-set-create-complete" in log
    else:
        assert rc != 0 and "change-set-create-complete" not in log   # no wait after a failed create


# ---- v2 17.2: DEMO_SCRIPT v2 (Req 37.3) ----
# Labels must match the dashboard: PauseButton.tsx, RulesEditor.tsx, SpendChart.tsx.

def _demo() -> str:
    return (DOCS / "DEMO_SCRIPT.md").read_text()


def test_demo_script_v2_moments():
    on_camera = _section(_demo(), "On camera")
    for s in ("--loop 20 --sleep 2", "**Pause agent**", "**Confirm pause**", "**Resume agent**",
              "CommandBlocked", "AgentPaused", "**Add presets**", "pipe_to_shell", "chart", "Discord"):
        assert s in on_camera, s


def test_demo_script_v2_on_camera_order():
    on_camera = _section(_demo(), "On camera")
    marks = ["bad_agent.py", "PathBlocked", "CommandBlocked", "Confirm pause", "SpendCapExceeded", "How it's built"]
    idx = [on_camera.index(m) for m in marks]
    assert idx == sorted(idx), list(zip(marks, idx))   # path, shell, pause, cap, then architecture


def test_demo_script_v2_prep_resets_state():
    prep = _section(_demo(), "Before recording (about 5 min, off camera)")
    assert "resume" in prep.lower() and "bad-bot" in prep and "demo-bot" in prep   # both agents resumed
    assert "aws login" in prep                                                     # fresh credentials right before
    assert "Discord" in prep                                                       # channel open on screen


def test_demo_script_v2_troubleshooting():
    body = _section(_demo(), "If something goes wrong").lower()
    assert "paused" in body                         # a stale pause from a rehearsal
    assert "over-block" in body                     # a pattern that blocks too much
    assert "discord" in body or "channel" in body   # no channel message


def test_demo_script_names_no_cut_features():
    text = _demo()
    for s in CUT_FEATURES:
        assert s not in text, s


def test_demo_script_ui_labels_exist_in_the_dashboard():
    # Every **bold** label must be visible text in a dashboard component or page.
    src = "\n".join(p.read_text() for p in (ROOT / "dashboard").glob("[ac]*/**/*.tsx")
                    if ".test." not in p.name)
    labels = set(re.findall(r"\*\*([^*]+)\*\*", _demo()))
    scene_titles = {l for l in labels if l.endswith(".")}             # "**Path block (60 s).**"
    for label in sorted(labels - scene_titles):
        assert label in src, label


EXPECTED_LINES = {
    "demo/bad_agent.py": ("PathBlocked:", "Agent Watch stopped the read", "CommandBlocked:",
                          "Agent Watch stopped the command"),
    "demo/demo_agent.py": ("Agent Watch stopped the call before it ran",),
}


def test_demo_script_expected_lines_match_the_code():
    text = _demo()
    for rel, lines in EXPECTED_LINES.items():
        code = (ROOT / rel).read_text()
        for line in lines:
            assert line in code, f"{rel}: {line}"                   # the code still prints it
            assert line in text, line                               # and the script promises it
    assert "Agent Watch: blocked_path blocked for bad-bot" in text   # format_alert subjects
    assert "Agent Watch: blocked_command blocked for bad-bot" in text
    assert "Agent Watch: paused blocked for demo-bot" in text
    assert "Agent Watch: spend_cap blocked for demo-bot" in text

