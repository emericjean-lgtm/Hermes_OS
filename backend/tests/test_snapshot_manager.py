"""§19.3 — snapshots & rollback, and acceptance criterion T8.

Restoring overwrites live state, so most of what follows pins down the
*limits* of that: it never runs unvalidated, it never deletes work
created after the snapshot, and it refuses cleanly on a corrupt file
rather than half-applying it.
"""
from __future__ import annotations

import json
import time

import pytest

from backend.security.aegis_engine import Verdict


@pytest.fixture
def snapshots(tmp_path, monkeypatch):
    """Point the whole module at a throwaway database and directory."""
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "snap.db"))
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path))

    from backend.core.config import get_settings

    get_settings.cache_clear()

    from backend.core import snapshot_manager
    from backend.memory.db import init_db, make_engine

    init_db(make_engine(str(tmp_path / "snap.db")))
    yield snapshot_manager
    get_settings.cache_clear()


@pytest.fixture
def store(snapshots):
    """Direct access to the same database the module snapshots."""
    from backend.tasks import task_manager

    factory = snapshots._session_factory()

    def create(title, status="todo"):
        with factory() as session:
            task = task_manager.create_task(session, title=title)
            if status != "todo":
                task_manager.update_task(session, task.id, status=status)
            return task.id

    def statuses():
        from backend.tasks.task_manager import Task

        with factory() as session:
            return {t.id: t.status for t in session.query(Task).all()}

    create.statuses = statuses
    return create


class _Aegis:
    def __init__(self, verdict=Verdict.ALLOW, reason="test"):
        self._verdict, self._reason = verdict, reason
        self.seen: list[str] = []

    def evaluate(self, request):
        self.seen.append(request.action_type)
        outer = self

        class _Decision:
            verdict = outer._verdict
            reason = outer._reason

        return _Decision()


# ── capture ──────────────────────────────────────────────────────────
def test_snapshot_captures_current_tasks(snapshots, store):
    store("Première tâche")
    store("Seconde tâche")

    info = snapshots.create_snapshot(reason="avant refactor")

    assert info.task_count == 2
    assert info.reason == "avant refactor"
    assert info.id in {s.id for s in snapshots.list_snapshots()}


def test_snapshot_is_plain_readable_json(snapshots, store):
    """A snapshot must stay readable even if this module is broken —
    that is the situation it exists for."""
    store("Tâche")
    info = snapshots.create_snapshot()

    raw = json.loads((snapshots._snapshot_dir() / f"{info.id}.json").read_text(encoding="utf-8"))

    assert raw["version"] == snapshots.SNAPSHOT_VERSION
    assert raw["tasks"][0]["title"] == "Tâche"


def test_capture_changes_nothing(snapshots, store):
    task_id = store("Intacte")
    before = store.statuses()

    snapshots.create_snapshot()

    assert store.statuses() == before
    assert task_id in before


def test_context_is_free_form_and_preserved(snapshots):
    info = snapshots.create_snapshot(context={"session": "abc", "step": 7})

    assert snapshots.list_snapshots()[0].context == {"session": "abc", "step": 7}
    assert info.context["step"] == 7


def test_snapshots_are_listed_newest_first(snapshots):
    """La pause sépare les deux horodatages — l'horloge Windows avance par
    pas de ~15,6 ms, et deux instantanés créés coup sur coup seraient ex
    aequo (HOS-112)."""
    first = snapshots.create_snapshot(reason="un")
    time.sleep(0.02)
    second = snapshots.create_snapshot(reason="deux")

    listed = [s.id for s in snapshots.list_snapshots()]

    assert listed.index(second.id) < listed.index(first.id)


def test_a_corrupt_file_does_not_hide_the_healthy_ones(snapshots):
    """This list is what someone reaches for when things have already
    gone wrong; one bad file must not empty it."""
    good = snapshots.create_snapshot(reason="bon")
    (snapshots._snapshot_dir() / "casse.json").write_text("{ pas du json", encoding="utf-8")

    assert good.id in {s.id for s in snapshots.list_snapshots()}


def test_file_backups_sharing_the_directory_are_ignored(snapshots):
    """propose_write writes .bak files into the same directory."""
    snapshots.create_snapshot()
    (snapshots._snapshot_dir() / "a.txt.20260101T000000Z.bak").write_text("x", encoding="utf-8")
    (snapshots._snapshot_dir() / "autre.json").write_text('{"pas": "un snapshot"}', encoding="utf-8")

    assert len(snapshots.list_snapshots()) == 1


# ── preview ──────────────────────────────────────────────────────────
def test_preview_reports_what_would_change(snapshots, store):
    kept = store("Existante")
    info = snapshots.create_snapshot()
    later = store("Créée après le snapshot")

    preview = snapshots.preview_restore(info.id)

    assert preview.tasks_overwritten == [kept]
    assert preview.tasks_absent_from_snapshot == [later]
    assert preview.tasks_created == []


def test_preview_changes_nothing(snapshots, store):
    store("Tâche", status="done")
    info = snapshots.create_snapshot()
    before = store.statuses()

    snapshots.preview_restore(info.id)

    assert store.statuses() == before


# ── restore ──────────────────────────────────────────────────────────
def test_restore_rolls_a_task_back(snapshots, store):
    task_id = store("Tâche", status="todo")
    info = snapshots.create_snapshot()

    from backend.tasks import task_manager

    with snapshots._session_factory()() as session:
        task_manager.update_task(session, task_id, status="done")
    assert store.statuses()[task_id] == "done"

    result = snapshots.restore_snapshot(_Aegis(), info.id)

    assert result.restored is True
    assert store.statuses()[task_id] == "todo"


def test_restore_never_deletes_work_created_afterwards(snapshots, store):
    """Restoring must not *lose* data — that would be the opposite of
    what a recovery tool is for."""
    store("Avant")
    info = snapshots.create_snapshot()
    later = store("Après le snapshot")

    snapshots.restore_snapshot(_Aegis(), info.id)

    assert later in store.statuses()


def test_restore_is_gated_as_a_data_migration(snapshots, store):
    """§17.3 lists data migration as mandatory human validation."""
    store("Tâche")
    info = snapshots.create_snapshot()
    aegis = _Aegis(verdict=Verdict.REQUIRE_HUMAN_VALIDATION, reason="migration")

    result = snapshots.restore_snapshot(aegis, info.id)

    assert result.restored is False
    assert result.verdict == "require_human_validation"
    assert aegis.seen == ["data_migration"]


def test_a_refused_restore_changes_nothing(snapshots, store):
    task_id = store("Tâche", status="todo")
    info = snapshots.create_snapshot()

    from backend.tasks import task_manager

    with snapshots._session_factory()() as session:
        task_manager.update_task(session, task_id, status="done")

    snapshots.restore_snapshot(_Aegis(verdict=Verdict.DENY, reason="non"), info.id)

    assert store.statuses()[task_id] == "done"


def test_restore_recreates_a_deleted_task(snapshots, store):
    task_id = store("Supprimée par erreur")
    info = snapshots.create_snapshot()

    from backend.tasks import task_manager

    with snapshots._session_factory()() as session:
        task_manager.delete_task(session, task_id)
    assert task_id not in store.statuses()

    snapshots.restore_snapshot(_Aegis(), info.id)

    assert task_id in store.statuses()


def test_an_unknown_snapshot_raises_before_reaching_aegis(snapshots):
    aegis = _Aegis()

    with pytest.raises(snapshots.SnapshotError):
        snapshots.restore_snapshot(aegis, "jamais-cree")

    assert aegis.seen == []


def test_a_corrupt_snapshot_refuses_rather_than_half_applying(snapshots, store):
    store("Tâche")
    info = snapshots.create_snapshot()
    (snapshots._snapshot_dir() / f"{info.id}.json").write_text("{ casse", encoding="utf-8")

    with pytest.raises(snapshots.SnapshotError, match="corrupt"):
        snapshots.restore_snapshot(_Aegis(), info.id)


# ── pruning & the step counter ───────────────────────────────────────
def _cinq_instantanes_dates(snapshots) -> list[str]:
    """Cinq instantanés d'horodatages distincts.

    Sans la pause, les cinq tombent dans le même pas d'horloge (~15,6 ms
    sous Windows) : « garder les deux plus récents » n'a alors plus de
    sens, et le test désignait deux gagnants au hasard (HOS-112).
    """
    ids = []
    for index in range(5):
        ids.append(snapshots.create_snapshot(reason=str(index)).id)
        time.sleep(0.02)
    return ids


def test_pruning_keeps_the_most_recent(snapshots):
    ids = _cinq_instantanes_dates(snapshots)

    removed = snapshots.prune_snapshots(keep=2)

    remaining = {s.id for s in snapshots.list_snapshots()}
    assert len(remaining) == 2
    assert set(ids[-2:]) == remaining
    assert len(removed) == 3


def test_the_counter_snapshots_every_n_steps(snapshots):
    counter = snapshots.StepCounter(every=3)

    results = [counter.step() for _ in range(7)]

    assert [r is not None for r in results] == [False, False, True, False, False, True, False]


def test_a_zero_interval_disables_automatic_snapshots(snapshots):
    """The escape hatch for anyone wanting only manual snapshots."""
    counter = snapshots.StepCounter(every=0)

    assert all(counter.step() is None for _ in range(20))
    assert snapshots.list_snapshots() == []
