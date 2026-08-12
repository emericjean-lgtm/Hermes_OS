"""Did the mission actually change anything? (HOS-092)

Every defect found while making Hermes Agent the mission brain produced a
*successful* mission: the tool loop bypass, the emptied CLI toolsets, the
objective lost in decomposition, the 4k served context, the 180s timeout.
Five distinct causes, five green reports, and in each case an empty
workspace. The common failure was not any of the five — it was that
"completed" meant "every node returned some text", and text is exactly what
a language model produces when it cannot do the work.

This module answers a different question, and answers it without asking the
agent: compare the workspace before and after. A filesystem diff is ground
truth. It needs no cooperation from the model, cannot be talked out of its
answer, and would have caught all five.

Deliberately *not* a pass/fail judge of the objective. Deciding whether
"alpha/beta/gamma" is the right content for a given goal is a semantic
question this layer has no business answering, and pretending otherwise
would just move the fabrication one level up. It reports what physically
changed; whether that satisfies the objective stays with the operator and
the mission's own validation.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes_os.mission.verification")

#: Files bigger than this are compared by size and mtime rather than hash.
#: Hashing a multi-gigabyte artifact to answer "did anything change" would
#: cost more than the answer is worth.
_HASH_LIMIT_BYTES = 8 * 1024 * 1024

#: Directories whose churn says nothing about whether the mission did its
#: work. Without this, any mission in a git repo or a Python project looks
#: productive because a cache directory moved.
_IGNORED_DIRS = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".next", "dist", "build", ".idea", ".vscode",
})


@dataclass(frozen=True)
class WorkspaceSnapshot:
    """What the workspace looked like at one instant."""

    root: str
    entries: dict[str, str] = field(default_factory=dict)

    @property
    def file_count(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class WorkspaceDiff:
    """What physically changed between two snapshots."""

    created: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()

    @property
    def touched_anything(self) -> bool:
        return bool(self.created or self.modified or self.deleted)

    def summary(self) -> str:
        if not self.touched_anything:
            return "no file was created, modified or deleted"
        parts = []
        for label, items in (("created", self.created), ("modified", self.modified),
                             ("deleted", self.deleted)):
            if items:
                shown = ", ".join(sorted(items)[:5])
                more = f" (+{len(items) - 5} more)" if len(items) > 5 else ""
                parts.append(f"{len(items)} {label}: {shown}{more}")
        return "; ".join(parts)


def _fingerprint(path: Path) -> str:
    """Cheap, collision-resistant enough to answer "did this change".

    Size and mtime alone miss a same-length rewrite within the filesystem's
    timestamp granularity — precisely the "agent rewrote the file with
    different content" case this exists to catch — so small files are
    hashed.
    """
    try:
        stat = path.stat()
    except OSError:
        return "unreadable"
    if stat.st_size > _HASH_LIMIT_BYTES:
        return f"size:{stat.st_size}:mtime:{int(stat.st_mtime)}"
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return f"size:{stat.st_size}:mtime:{int(stat.st_mtime)}"


def snapshot(root: str) -> WorkspaceSnapshot:
    """Fingerprint every file under ``root``.

    Never raises: this runs around a mission, and a snapshot that fails must
    not be able to fail the mission itself. An unreadable tree yields an
    empty snapshot, which shows up as "nothing changed" rather than as a
    crash — visible, and honest about having learned nothing.
    """
    base = Path(root)
    entries: dict[str, str] = {}
    try:
        if not base.is_dir():
            return WorkspaceSnapshot(root=root)
        for path in base.rglob("*"):
            if any(part in _IGNORED_DIRS for part in path.parts):
                continue
            if not path.is_file():
                continue
            try:
                relative = str(path.relative_to(base))
            except ValueError:  # pragma: no cover - symlink escaping the root
                continue
            entries[relative] = _fingerprint(path)
    except OSError:
        logger.debug("snapshot of %r failed", root, exc_info=True)
    return WorkspaceSnapshot(root=root, entries=entries)


def diff(before: WorkspaceSnapshot, after: WorkspaceSnapshot) -> WorkspaceDiff:
    """What changed between two snapshots of the same workspace."""
    before_keys, after_keys = set(before.entries), set(after.entries)
    return WorkspaceDiff(
        created=tuple(sorted(after_keys - before_keys)),
        deleted=tuple(sorted(before_keys - after_keys)),
        modified=tuple(sorted(
            k for k in before_keys & after_keys
            if before.entries[k] != after.entries[k]
        )),
    )


@dataclass(frozen=True)
class MissionVerification:
    """Whether a mission's claimed success is backed by a real change."""

    mission_id: str
    reported_success: bool
    workspace: Optional[str]
    changes: WorkspaceDiff
    #: False when there was nothing to compare — no bound workspace, or a
    #: snapshot that could not be taken. Absence of measurement is not
    #: evidence of absence of work, and conflating the two would flag every
    #: workspace-less mission as a false success.
    measured: bool = True

    @property
    def verified(self) -> bool:
        """A successful mission that touched nothing is not verified.

        The inverse is not asserted: a mission that failed while still
        writing files is reported as it happened, not retroactively passed.
        """
        return self.measured and self.reported_success and self.changes.touched_anything

    @property
    def contradicted(self) -> bool:
        """Reported success, changed nothing — the exact false positive that
        hid five separate defects. Only ever claimed when we actually
        looked."""
        return (self.measured and self.reported_success
                and not self.changes.touched_anything)

    def as_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "reported_success": self.reported_success,
            "measured": self.measured,
            "verified": self.verified,
            "contradicted": self.contradicted,
            "workspace": self.workspace,
            "created": list(self.changes.created),
            "modified": list(self.changes.modified),
            "deleted": list(self.changes.deleted),
            "summary": self.changes.summary(),
        }


def verify(
    mission_id: str,
    reported_success: bool,
    workspace: Optional[str],
    before: Optional[WorkspaceSnapshot],
    after: Optional[WorkspaceSnapshot],
) -> MissionVerification:
    """Confront a mission's own verdict with the filesystem's.

    A mission bound to no workspace has nothing to confront, so its reported
    result stands unchallenged rather than being failed for lacking evidence
    it was never in a position to produce.
    """
    if workspace is None or before is None or after is None:
        return MissionVerification(
            mission_id=mission_id, reported_success=reported_success,
            workspace=workspace, changes=WorkspaceDiff(), measured=False,
        )
    result = MissionVerification(
        mission_id=mission_id, reported_success=reported_success,
        workspace=workspace, changes=diff(before, after),
    )
    if result.contradicted:
        logger.warning(
            "mission %s reported success but %s in %r — the result is the "
            "model's account of the work, not evidence of it",
            mission_id, result.changes.summary(), workspace,
        )
    return result
