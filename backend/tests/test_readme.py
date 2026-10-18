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
