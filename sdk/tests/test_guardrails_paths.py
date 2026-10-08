import os

import pytest

from agentwatch.guardrails import absolute_path, is_directory_entry, normalize_path, path_forms


def _symlink_or_skip(src, dst):
    try:
        os.symlink(src, dst)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted")


def test_absolute_path_resolves_dot_and_dotdot_lexically(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert absolute_path("./x") == os.path.join(str(tmp_path), "x")
    assert absolute_path("a/../x") == os.path.join(str(tmp_path), "x")


def test_absolute_path_keeps_symlinks(tmp_path):
    (tmp_path / "real").mkdir()
    _symlink_or_skip(tmp_path / "real", tmp_path / "link")
    assert absolute_path(str(tmp_path / "link" / "f")) == str(tmp_path / "link" / "f")


def test_normalize_path_resolves_symlinks(tmp_path):
    (tmp_path / "real").mkdir()
    _symlink_or_skip(tmp_path / "real", tmp_path / "link")
    assert normalize_path(str(tmp_path / "link" / "f")) == os.path.realpath(tmp_path / "real" / "f")


def test_path_forms_are_casefolded(tmp_path):
    forms = path_forms(str(tmp_path / "MiXeD" / "Straße.ENV"))
    assert forms and all(f == f.casefold() for f in forms)
    assert any(f.endswith("strasse.env") for f in forms)


def test_tilde_expands(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert absolute_path("~/.ssh") == os.path.join(str(tmp_path), ".ssh")
    assert normalize_path("~/.ssh") == os.path.join(os.path.realpath(tmp_path), ".ssh")


@pytest.mark.parametrize("entry,expected", [
    ("~/.ssh", True), ("/a/b", True), ("a/b", True), ("/", True),
    (".env", False), ("id_rsa", False), ("secrets.txt", False),
])
def test_is_directory_entry(entry, expected):
    assert is_directory_entry(entry) is expected


# ---- 3.9 path_matches and blocked_entry_for ----

from agentwatch.guardrails import blocked_entry_for, path_matches  # noqa: E402


@pytest.mark.parametrize("attempt,expected", [
    ("/a/b", True), ("/A/B", True), ("/a/b/c", True), ("/a/b/", True),
    ("/a/bc", False), ("/a", False), ("/x/a/b", False),
])
def test_directory_entry_boundaries(attempt, expected):
    assert path_matches(attempt, "/a/b") is expected


@pytest.mark.parametrize("attempt", ["x/.env", ".ENV", "/deep/nested/dir/.Env", "./.env"])
def test_name_entry_matches_anywhere_any_case(attempt):
    assert path_matches(attempt, ".env") is True


@pytest.mark.parametrize("attempt", [".env.example", "env", "x/.env/../notes.md", "my.env"])
def test_name_entry_non_matches(attempt):
    assert path_matches(attempt, ".env") is False


def test_root_blocks_everything(tmp_path):
    assert path_matches(str(tmp_path / "anything"), "/") is True
    assert path_matches("relative.txt", "/") is True


def test_tilde_directory_entry(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert path_matches(str(tmp_path / ".ssh" / "id_rsa"), "~/.ssh") is True
    assert path_matches(str(tmp_path / ".sshx"), "~/.ssh") is False


def test_blocked_entry_for_returns_first_match_or_none():
    entries = ["/etc", ".env", "/a/b"]
    assert blocked_entry_for("/a/b/.env", entries) == ".env"
    assert blocked_entry_for("/a/b/notes", entries) == "/a/b"
    assert blocked_entry_for("/home/me/notes.md", entries) is None
    assert blocked_entry_for("/home/me/notes.md", []) is None
