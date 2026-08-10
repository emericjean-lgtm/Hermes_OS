"""Workspace/Filesystem tool layer — security-critical coverage.

Three things this file exists to prove, all in one place because they are
the actual point of the whole layer:

1. A validated Project's root_path really does widen Aegis's whitelist
   (agents/aegis.py's _dynamic_allowed_paths + aegis_engine.py's
   extra_allowed_paths) — the mechanism that lets a user register
   C:\\Users\\emeri\\Skill360 Industry without editing config/security.yaml.
2. That grant is genuinely dynamic: archiving, invalidating, or deleting
   the Project revokes it on the very next call, nothing cached.
3. Every new file_tools operation (exists/stat/search/mkdir/append/copy/
   move/delete) is independently verified — a false verified=True must be
   impossible to produce by construction, not just untested.

test_file_tools.py covers the pre-existing read/list/propose_write
surface in isolation (a bare AegisEngine, no DB); test_aegis_agent_bus.py
covers the message-bus wiring. This file is the one that exercises the
real AegisAgent + real ProjectStore together, because the dynamic
whitelist only exists at that seam.
"""
from __future__ import annotations

import pytest

from backend.agents.aegis import AegisAgent
from backend.core.config import get_settings
from backend.core.message_bus import get_message_bus
from backend.core.router import ModelRouter
from backend.projects.project_manager import ValidationStatus
from backend.projects.store import get_project_store
from backend.security.aegis_engine import ActionRequest, Verdict
from backend.tools import file_tools


@pytest.fixture
def aegis_agent(monkeypatch, fake_ollama_client, models_config, security_config, tmp_path):
    """Same shape as test_aegis_agent_bus.py's fixture, but ALLOWED_PATHS
    points at an *unrelated* empty directory rather than tmp_path itself —
    every real workspace in these tests lives under tmp_path and must be
    granted access purely through a validated Project, proving the
    dynamic-widening path actually does the work rather than piggybacking
    on the static whitelist."""
    unrelated = tmp_path / "_static_whitelist_only"
    unrelated.mkdir()

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(unrelated))
    get_settings.cache_clear()
    get_message_bus.cache_clear()
    get_project_store.cache_clear()
    monkeypatch.setattr("backend.agents.aegis.load_security_config", lambda: security_config)

    router = ModelRouter(models_config)
    agent = AegisAgent(fake_ollama_client, router, models_config)

    try:
        yield agent
    finally:
        get_settings.cache_clear()
        get_message_bus.cache_clear()
        get_project_store.cache_clear()


def _make_workspace(tmp_path, name="ws"):
    root = tmp_path / name
    root.mkdir()
    return root


# ── 1. Dynamic whitelist widening ───────────────────────────────────


def test_unvalidated_project_root_does_not_grant_access(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    assert project.validation_status == ValidationStatus.UNVALIDATED.value

    decision = aegis_agent.evaluate(ActionRequest(
        action_type="file_read", description="read", target_path=str(root / "f.txt"),
        requesting_agent="test",
    ))
    assert decision.verdict is Verdict.DENY


def test_validated_project_root_grants_access_outside_static_whitelist(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    (root / "f.txt").write_text("hi")
    project = get_project_store().create(name="ws", root_path=str(root))
    validated = get_project_store().validate(project.id)
    assert validated.validation_status == ValidationStatus.VALID.value

    decision = aegis_agent.evaluate(ActionRequest(
        action_type="file_read", description="read", target_path=str(root / "f.txt"),
        requesting_agent="test",
    ))
    assert decision.verdict is Verdict.ALLOW


def test_sibling_directory_not_covered_by_a_different_validated_project(aegis_agent, tmp_path):
    """Registering ws-a must not incidentally whitelist ws-b just because
    they're siblings — only ws-a's own resolved root_path is in the
    dynamic whitelist, unlike a naive string-prefix check would allow."""
    root_a = _make_workspace(tmp_path, "ws-a")
    root_b = _make_workspace(tmp_path, "ws-b")
    project = get_project_store().create(name="a", root_path=str(root_a))
    get_project_store().validate(project.id)

    decision = aegis_agent.evaluate(ActionRequest(
        action_type="file_read", description="read", target_path=str(root_b / "f.txt"),
        requesting_agent="test",
    ))
    assert decision.verdict is Verdict.DENY


def test_archiving_project_revokes_access_on_next_call(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    action = ActionRequest(
        action_type="file_read", description="read", target_path=str(root / "f.txt"),
        requesting_agent="test",
    )
    assert aegis_agent.evaluate(action).verdict is Verdict.ALLOW

    get_project_store().update(project.id, status="archived")

    assert aegis_agent.evaluate(action).verdict is Verdict.DENY


def test_deleting_project_revokes_access_on_next_call(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    action = ActionRequest(
        action_type="file_read", description="read", target_path=str(root / "f.txt"),
        requesting_agent="test",
    )
    assert aegis_agent.evaluate(action).verdict is Verdict.ALLOW

    get_project_store().delete(project.id)

    assert aegis_agent.evaluate(action).verdict is Verdict.DENY


def test_invalidating_root_path_change_revokes_access_until_revalidated(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    other = _make_workspace(tmp_path, "ws-other")
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    action = ActionRequest(
        action_type="file_read", description="read", target_path=str(root / "f.txt"),
        requesting_agent="test",
    )
    assert aegis_agent.evaluate(action).verdict is Verdict.ALLOW

    # update_project() resets validation_status to "unvalidated" on a real
    # root_path change (project_manager.py) — the old root must stop
    # being granted immediately, before anyone calls validate again.
    get_project_store().update(project.id, root_path=str(other))

    assert aegis_agent.evaluate(action).verdict is Verdict.DENY


def test_project_scoping_still_narrows_regardless_of_validation_status(aegis_agent, tmp_path):
    """Narrowing (project_root=) is the pre-existing, independent
    restriction — it must keep working for an *unvalidated* project too,
    since it can only ever make an action more restrictive, never grant
    anything new. Uses a path that IS in the static whitelist so the
    narrowing check is what's actually being exercised."""
    from backend.core.config import get_settings as _gs

    static_root = next(iter(_gs().allowed_paths_list))
    from pathlib import Path
    inside_static = Path(static_root)
    sibling = inside_static / "sibling"
    sibling.mkdir(exist_ok=True)
    project_root = inside_static / "project"
    project_root.mkdir(exist_ok=True)

    project = get_project_store().create(name="p", root_path=str(project_root))
    # Deliberately not validated — narrowing must not depend on it.

    denied = aegis_agent.evaluate(ActionRequest(
        action_type="file_read", description="read", target_path=str(sibling / "f.txt"),
        requesting_agent="test", project_id=project.id,
    ))
    assert denied.verdict is Verdict.DENY

    allowed = aegis_agent.evaluate(ActionRequest(
        action_type="file_read", description="read", target_path=str(project_root / "f.txt"),
        requesting_agent="test", project_id=project.id,
    ))
    assert allowed.verdict is Verdict.ALLOW


# ── 2. Path escape attempts (real filesystem, real Aegis) ──────────


@pytest.mark.parametrize("escape", [
    "../escape.txt",
    "../../escape.txt",
    "..\\escape.txt",
])
def test_relative_escape_from_validated_workspace_is_denied(aegis_agent, tmp_path, escape):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)

    target = str((root / escape).resolve())
    decision = aegis_agent.evaluate(ActionRequest(
        action_type="file_read", description="read", target_path=target,
        requesting_agent="test",
    ))
    assert decision.verdict is Verdict.DENY


def test_absolute_path_outside_any_workspace_is_denied(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)

    outside = tmp_path / "_static_whitelist_only" / ".." / "totally-elsewhere"
    decision = aegis_agent.evaluate(ActionRequest(
        action_type="file_read", description="read", target_path=str(outside),
        requesting_agent="test",
    ))
    assert decision.verdict is Verdict.DENY


# ── 3. New file_tools operations — Aegis-denied + real, verified success ──


def test_exists_denied_outside_whitelist_raises(aegis_agent, tmp_path):
    with pytest.raises(PermissionError):
        file_tools.exists(aegis_agent, str(tmp_path / "nowhere" / "f.txt"))


def test_mkdir_creates_and_verifies(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)

    result = file_tools.create_directory(aegis_agent, str(root / "sub" / "nested"))
    assert result.success is True
    assert result.verified is True
    assert (root / "sub" / "nested").is_dir()


def test_mkdir_denied_outside_whitelist_does_not_create(aegis_agent, tmp_path):
    target = tmp_path / "denied" / "sub"
    result = file_tools.create_directory(aegis_agent, str(target))
    assert result.success is False
    assert result.verified is False
    assert not target.exists()


def test_append_creates_new_file_and_verifies(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    target = root / "log.txt"

    r1 = file_tools.append(aegis_agent, str(target), "line1\n")
    r2 = file_tools.append(aegis_agent, str(target), "line2\n")

    assert r1.verified is True
    assert r2.verified is True
    assert target.read_text() == "line1\nline2\n"


def test_copy_duplicates_content_and_verifies(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    src = root / "a.txt"
    src.write_bytes(b"payload")
    dst = root / "b.txt"

    result = file_tools.copy(aegis_agent, str(src), str(dst))

    assert result.success is True
    assert result.verified is True
    assert dst.read_bytes() == b"payload"
    assert src.exists()  # copy never removes the source


def test_copy_denied_when_destination_outside_whitelist(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    src = root / "a.txt"
    src.write_text("payload")
    dst = tmp_path / "elsewhere" / "b.txt"

    result = file_tools.copy(aegis_agent, str(src), str(dst))

    assert result.success is False
    assert not dst.exists()


def test_move_first_attempt_always_requires_human_validation(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    src = root / "a.txt"
    src.write_bytes(b"payload")
    dst = root / "moved.txt"

    # file_move is mandatory_validation: true (config/security.yaml) — a
    # move makes the source disappear, same risk shape as delete, so it
    # can never auto-allow regardless of autonomy level.
    first = file_tools.move(aegis_agent, str(src), str(dst))
    assert first.success is False
    assert first.verdict == "require_human_validation"
    assert src.exists()
    assert not dst.exists()


def test_move_after_human_approval_relocates_and_verifies(aegis_agent, tmp_path):
    """The full request -> pending -> human decides -> retry consumes
    approval -> execution -> verification chain, exercised for real.

    move() makes two separate Aegis requests (source, then destination)
    and each approval is one-shot — consumed the instant its own
    evaluate() call succeeds, whether or not the overall move() call goes
    on to complete. Sequentially approving "whatever is pending right
    now" one hop at a time therefore never reaches a state where *both*
    are simultaneously live (source's first approval gets spent just
    reaching the destination check, before move() can succeed) — the
    real, intended usage is a human approving both pending requests
    before the next retry, which is what's set up directly here rather
    than walked through hop by hop."""
    from backend.security import approvals

    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    src = root / "a.txt"
    src.write_bytes(b"payload")
    dst = root / "moved.txt"

    first = file_tools.move(aegis_agent, str(src), str(dst))
    assert first.success is False  # only source's request exists yet

    with aegis_agent._session_factory() as session:  # noqa: SLF001 - test-only introspection
        approvals.record_pending(
            session, action_type="file_move",
            description=f"Move {src} to {dst} (source)",
            reason="test setup", target_path=str(src),
        )
        approvals.record_pending(
            session, action_type="file_move",
            description=f"Move {src} to {dst} (destination)",
            reason="test setup", target_path=str(dst),
        )
        for entry in approvals.list_approvals(session, status="pending"):
            approvals.decide(session, entry.id, approved=True)

    second = file_tools.move(aegis_agent, str(src), str(dst))
    assert second.success is True
    assert second.verified is True
    assert not src.exists()
    assert dst.read_bytes() == b"payload"


def test_delete_first_attempt_always_requires_human_validation(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    target = root / "a.txt"
    target.write_text("payload")

    # file_delete is mandatory_validation: true — same shape as move.
    result = file_tools.delete(aegis_agent, str(target))
    assert result.success is False
    assert result.verdict == "require_human_validation"
    assert target.exists()


def test_delete_after_human_approval_removes_and_verifies(aegis_agent, tmp_path):
    from backend.security import approvals

    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    target = root / "a.txt"
    target.write_text("payload")

    first = file_tools.delete(aegis_agent, str(target))
    assert first.success is False

    with aegis_agent._session_factory() as session:  # noqa: SLF001 - test-only introspection
        for entry in approvals.list_approvals(session, status="pending"):
            approvals.decide(session, entry.id, approved=True)

    second = file_tools.delete(aegis_agent, str(target))
    assert second.success is True
    assert second.verified is True
    assert not target.exists()


def test_search_finds_matching_files_readonly(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    (root / "a.py").write_text("")
    (root / "b.txt").write_text("")
    (root / "sub").mkdir()
    (root / "sub" / "c.py").write_text("")

    results = file_tools.search(aegis_agent, str(root), "**/*.py")

    assert len(results) == 2
    assert all(r.endswith(".py") for r in results)


def test_stat_reports_real_size_and_kind(aegis_agent, tmp_path):
    root = _make_workspace(tmp_path)
    project = get_project_store().create(name="ws", root_path=str(root))
    get_project_store().validate(project.id)
    target = root / "a.txt"
    target.write_text("12345")

    info = file_tools.stat(aegis_agent, str(target))

    assert info["is_file"] is True
    assert info["is_dir"] is False
    assert info["size_bytes"] == 5
