"""Req 28.13, 28.14: the dashboard's Command_Presets are valid Python patterns.

The SDK matches with Python `re`, so every preset the dashboard offers must compile
here, stay within MAX_COMMAND_LEN, match its example, and miss its safe example.
"""
import json
import re
from pathlib import Path

import pytest

from agentwatch_api.rules import MAX_COMMAND_LEN, parse_config

PRESETS_PATH = Path(__file__).resolve().parents[2] / "dashboard" / "lib" / "commandPresets.json"
FIELDS = {"id", "label", "pattern", "example", "safeExample"}
REQUIRED_IDS = {
    "rm_recursive", "pipe_to_shell", "ssh_dir", "sudo", "chmod_777",
    "disk_destroy", "write_block_device", "git_force_push", "env_file",
}


def load_presets():
    return json.loads(PRESETS_PATH.read_text(encoding="utf-8"))


PRESETS = load_presets()


def test_presets_cover_required_ids_once():
    ids = [p["id"] for p in PRESETS]
    assert len(ids) == len(set(ids))
    assert REQUIRED_IDS <= set(ids)


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p["id"])
def test_preset_compiles_and_matches_examples(preset):
    assert set(preset) == FIELDS
    pattern = preset["pattern"]
    assert 1 <= len(pattern) <= MAX_COMMAND_LEN
    rx = re.compile(pattern, re.IGNORECASE)
    assert rx.search(preset["example"]), preset["example"]
    assert not rx.search(preset["safeExample"]), preset["safeExample"]


def test_all_presets_pass_backend_config_validation():
    body = {
        "dailySpendCapUsd": None,
        "blockedPaths": [],
        "blockedCommands": [p["pattern"] for p in PRESETS],
    }
    cfg = parse_config(body)
    assert tuple(cfg.blocked_commands) == tuple(body["blockedCommands"])


def test_env_file_preset_blocks_cat_env():
    """PROGRESS 9.4 finding: blockedPaths misses run_shell("cat .env"); this preset covers it."""
    env = next(p for p in PRESETS if p["id"] == "env_file")
    rx = re.compile(env["pattern"], re.IGNORECASE)
    assert rx.search("cat .env")
    assert rx.search("cat ./.env")
    assert not rx.search("cat environment.yml")
