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


def test_docs_contain_no_live_secrets():
    # The demo key lives outside the repo; docs must use placeholders only.
    for path in [README, *DOCS.glob("*.md")]:
        text = path.read_text()
        assert not re.search(r"AGENTWATCH_KEY=(?!<)[^\s`]+", text), path.name
        assert not re.search(r"\b[0-9a-f]{64}\b", text), path.name
