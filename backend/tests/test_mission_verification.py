"""Mission verification against the filesystem (HOS-092).

Written from five real false positives. Making Hermes Agent the mission
brain surfaced five distinct defects — the HOS tool loop overriding the
agent, emptied CLI toolsets, the objective lost in decomposition, a 4k
served context, a 180s timeout — and every one of them produced a mission
that reported success over an untouched workspace. "Completed" meant "every
node returned some text", and text is what a model produces when it cannot
do the work.

These tests pin the one check that would have caught all five.
"""
from __future__ import annotations

import time

from backend.mission.verification import diff, snapshot, verify


def _snap(path):
    return snapshot(str(path))


def test_created_file_is_detected(tmp_path):
    before = _snap(tmp_path)
    (tmp_path / "report.md").write_text("alpha")

    changes = diff(before, _snap(tmp_path))

    assert changes.created == ("report.md",)
    assert changes.touched_anything


def test_rewrite_of_identical_length_is_detected(tmp_path):
    """Size and mtime alone would miss this, and it is exactly the case
    that matters: the agent rewrote the file with different content."""
    target = tmp_path / "config.txt"
    target.write_text("aaaa")
    before = _snap(tmp_path)
    target.write_text("bbbb")

    assert diff(before, _snap(tmp_path)).modified == ("config.txt",)


def test_deletion_is_detected(tmp_path):
    (tmp_path / "old.txt").write_text("x")
    before = _snap(tmp_path)
    (tmp_path / "old.txt").unlink()

    assert diff(before, _snap(tmp_path)).deleted == ("old.txt",)


def test_untouched_workspace_reports_nothing(tmp_path):
    (tmp_path / "stable.txt").write_text("unchanged")
    before = _snap(tmp_path)
    time.sleep(0.01)

    changes = diff(before, _snap(tmp_path))

    assert not changes.touched_anything
    assert changes.summary() == "no file was created, modified or deleted"


def test_noise_directories_are_ignored(tmp_path):
    """A mission in a git repo or Python project must not look productive
    because a cache directory moved."""
    (tmp_path / "src").mkdir()
    before = _snap(tmp_path)
    for noisy in (".git", "__pycache__", "node_modules"):
        (tmp_path / noisy).mkdir()
        (tmp_path / noisy / "junk").write_text("noise")

    assert not diff(before, _snap(tmp_path)).touched_anything


def test_success_without_any_change_is_contradicted(tmp_path):
    """The five false positives, in one assertion."""
    before = _snap(tmp_path)

    result = verify("m-1", True, str(tmp_path), before, _snap(tmp_path))

    assert result.contradicted
    assert not result.verified


def test_success_with_a_real_artifact_is_verified(tmp_path):
    before = _snap(tmp_path)
    (tmp_path / "HERMES_OS_FINAL_INTEGRATION_TEST.md").write_text("alpha\nbeta\ngamma\n")

    result = verify("m-2", True, str(tmp_path), before, _snap(tmp_path))

    assert result.verified
    assert not result.contradicted
    assert "HERMES_OS_FINAL_INTEGRATION_TEST.md" in result.as_dict()["created"]


def test_failed_mission_is_not_retroactively_passed(tmp_path):
    """A mission that failed while still writing files is reported as it
    happened, not rescued by the diff."""
    before = _snap(tmp_path)
    (tmp_path / "partial.txt").write_text("half done")

    result = verify("m-3", False, str(tmp_path), before, _snap(tmp_path))

    assert not result.verified
    assert not result.contradicted


def test_mission_without_a_workspace_is_left_alone(tmp_path):
    """Nothing to confront: an unbound mission must not be failed for
    lacking evidence it was never in a position to produce."""
    result = verify("m-4", True, None, None, None)

    assert not result.contradicted
    assert not result.verified


def test_snapshot_of_a_missing_directory_is_empty_not_fatal(tmp_path):
    """This runs around a real mission; a snapshot failure must never be
    able to fail the mission itself."""
    missing = tmp_path / "does-not-exist"

    result = snapshot(str(missing))

    assert result.file_count == 0
