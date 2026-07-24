from __future__ import annotations

from pathlib import Path

import pytest

from backend.security.aegis_engine import ActionRequest, AegisDecision, AegisEngine, Verdict
from backend.security.permission_matrix import PermissionMatrix
from backend.tools import file_tools


class _EngineAsAegis:
    """Duck-types AegisAgent.evaluate() without going through Settings/.env
    — file_tools only ever calls .evaluate(), so this is enough."""

    def __init__(self, engine: AegisEngine) -> None:
        self._engine = engine

    def evaluate(self, action: ActionRequest) -> AegisDecision:
        return self._engine.evaluate(action)


def _aegis(security_config: dict, allowed_paths: list[str], autonomy_level: str) -> _EngineAsAegis:
    config = dict(security_config)
    config["autonomy_level"] = autonomy_level
    return _EngineAsAegis(AegisEngine(PermissionMatrix(config), allowed_paths))


def test_read_file_outside_whitelist_raises_permission_error(security_config, tmp_path):
    aegis = _aegis(security_config, [str(tmp_path / "allowed")], "high")
    with pytest.raises(PermissionError):
        file_tools.read_file(aegis, str(tmp_path / "elsewhere" / "f.txt"))


def test_read_file_missing_inside_whitelist_raises_file_not_found(security_config, tmp_path):
    aegis = _aegis(security_config, [str(tmp_path)], "high")
    with pytest.raises(FileNotFoundError):
        file_tools.read_file(aegis, str(tmp_path / "nope.txt"))


def test_read_file_returns_content(security_config, tmp_path):
    aegis = _aegis(security_config, [str(tmp_path)], "high")
    f = tmp_path / "hello.txt"
    f.write_text("hi there")
    assert file_tools.read_file(aegis, str(f)) == "hi there"


def test_list_directory_returns_sorted_names(security_config, tmp_path):
    aegis = _aegis(security_config, [str(tmp_path)], "high")
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "a.txt").write_text("")
    assert file_tools.list_directory(aegis, str(tmp_path)) == ["a.txt", "b.txt"]


def test_compute_diff_shows_added_line():
    diff = file_tools.compute_diff("a\n", "a\nb\n", "f.txt")
    assert "+b" in diff


def test_propose_write_denied_outside_whitelist_does_not_write(security_config, tmp_path):
    aegis = _aegis(security_config, [str(tmp_path / "allowed")], "high")
    target = tmp_path / "elsewhere" / "f.txt"
    result = file_tools.propose_write(aegis, str(target), "content")
    assert result.applied is False
    assert result.verdict == "deny"
    assert not target.exists()


def test_propose_write_requires_validation_at_low_autonomy_does_not_write(security_config, tmp_path):
    aegis = _aegis(security_config, [str(tmp_path)], "low")
    target = tmp_path / "f.txt"
    result = file_tools.propose_write(aegis, str(target), "content")
    assert result.applied is False
    assert result.verdict == "require_human_validation"
    assert not target.exists()


def test_propose_write_applies_at_medium_autonomy_and_creates_backup(security_config, tmp_path):
    aegis = _aegis(security_config, [str(tmp_path)], "medium")
    target = tmp_path / "f.txt"
    target.write_text("old content")
    backup_dir = tmp_path / "snapshots"

    result = file_tools.propose_write(aegis, str(target), "new content", backup_dir=str(backup_dir))

    assert result.applied is True
    assert target.read_text() == "new content"
    assert result.backup_path is not None
    assert Path(result.backup_path).read_text() == "old content"


def test_propose_write_new_file_has_no_backup(security_config, tmp_path):
    aegis = _aegis(security_config, [str(tmp_path)], "medium")
    target = tmp_path / "new_file.txt"

    result = file_tools.propose_write(
        aegis, str(target), "brand new", backup_dir=str(tmp_path / "snapshots")
    )

    assert result.applied is True
    assert result.backup_path is None
    assert target.read_text() == "brand new"


def test_propose_write_diff_reflects_change(security_config, tmp_path):
    aegis = _aegis(security_config, [str(tmp_path)], "medium")
    target = tmp_path / "f.txt"
    target.write_text("line1\n")

    result = file_tools.propose_write(aegis, str(target), "line1\nline2\n")

    assert "+line2" in result.diff


class _RecordingAegis:
    """Captures the ActionRequest it was called with instead of deciding
    anything — used to verify project_id reaches Aegis, since AegisEngine
    itself doesn't resolve project_id (that's AegisAgent's job, see
    agents/aegis.py) and so can't demonstrate the wiring on its own."""

    def __init__(self) -> None:
        self.last_action: ActionRequest | None = None

    def evaluate(self, action: ActionRequest) -> AegisDecision:
        self.last_action = action
        return AegisDecision(verdict=Verdict.DENY, reason="recorded", action_type=action.action_type)


def test_project_id_reaches_action_request_for_every_file_tool(tmp_path):
    aegis = _RecordingAegis()
    target = tmp_path / "f.txt"
    target.write_text("hi")

    with pytest.raises(PermissionError):
        file_tools.read_file(aegis, str(target), project_id="proj-1")
    assert aegis.last_action.project_id == "proj-1"

    with pytest.raises(PermissionError):
        file_tools.list_directory(aegis, str(tmp_path), project_id="proj-1")
    assert aegis.last_action.project_id == "proj-1"

    with pytest.raises(PermissionError):
        file_tools.read_existing_or_empty(aegis, str(target), project_id="proj-1")
    assert aegis.last_action.project_id == "proj-1"

    file_tools.propose_write(aegis, str(target), "new", project_id="proj-1")
    assert aegis.last_action.project_id == "proj-1"
