import os

import pytest

from agentwatch.guardrails import blocked_entry_for


def _link(src, dst):
    try:
        os.symlink(src, dst)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted")


def test_symlink_named_env_pointing_elsewhere_is_blocked(tmp_path):
    (tmp_path / "secrets.txt").write_text("x")
    _link(tmp_path / "secrets.txt", tmp_path / ".env")
    assert blocked_entry_for(str(tmp_path / ".env"), [".env"]) == ".env"


def test_innocent_alias_into_blocked_directory_is_blocked(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "key.pem").write_text("x")
    _link(vault / "key.pem", tmp_path / "notes.txt")
    assert blocked_entry_for(str(tmp_path / "notes.txt"), [str(vault)]) == str(vault)


def test_directory_alias_into_blocked_directory_is_blocked(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _link(vault, tmp_path / "docs")
    assert blocked_entry_for(str(tmp_path / "docs" / "anything"), [str(vault)]) == str(vault)


def test_alias_to_env_file_is_blocked_by_name(tmp_path):
    (tmp_path / ".env").write_text("x")
    _link(tmp_path / ".env", tmp_path / "config.txt")
    assert blocked_entry_for(str(tmp_path / "config.txt"), [".env"]) == ".env"


def test_blocked_entry_given_through_a_symlink_still_blocks_real_path(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _link(vault, tmp_path / "v")
    assert blocked_entry_for(str(vault / "f"), [str(tmp_path / "v")]) == str(tmp_path / "v")
