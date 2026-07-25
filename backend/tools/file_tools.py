"""File tools available to agents (primarily Atlas) — cahier des charges §14.1.

Every operation, reads included, is gated by Aegis before touching disk:
the whitelist (ALLOWED_PATHS) applies to file_read just as much as to
file_write (§17.1 — "séparation claire entre lecture et écriture" does
not mean reads are unrestricted, it means they're gated differently).
Writes additionally: always compute a diff against the current content,
take a timestamped backup before overwriting anything that already
exists, and only touch disk when Aegis's verdict is ALLOW.
"""
from __future__ import annotations

import difflib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.agents.aegis import AegisAgent
from backend.security.aegis_engine import ActionRequest, Verdict


@dataclass(frozen=True)
class FileWriteResult:
    applied: bool
    verdict: str
    reason: str
    diff: str
    backup_path: str | None = None


def _check(
    aegis: AegisAgent,
    action_type: str,
    path: str,
    description: str,
    *,
    project_id: str | None = None,
) -> None:
    decision = aegis.evaluate(
        ActionRequest(
            action_type=action_type,
            description=description,
            target_path=path,
            requesting_agent="atlas",
            project_id=project_id,
        )
    )
    if decision.verdict is not Verdict.ALLOW:
        raise PermissionError(decision.reason)


def read_file(aegis: AegisAgent, path: str, *, project_id: str | None = None) -> str:
    _check(aegis, "file_read", path, f"Read {path}", project_id=project_id)
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"No such file: {path}")
    return target.read_text(encoding="utf-8")


def read_bytes(aegis: AegisAgent, path: str, *, project_id: str | None = None) -> bytes:
    """Same `file_read` gate as read_file, but returns raw bytes.

    Needed by document ingestion (§13): PDF and DOCX are binary, so
    read_file's read_text() would raise UnicodeDecodeError on them. This
    is a second reader, not a second *gate* — the Aegis check below is the
    identical call read_file makes, so ALLOWED_PATHS and the autonomy
    level apply exactly the same way.
    """
    _check(aegis, "file_read", path, f"Read {path} (binary)", project_id=project_id)
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"No such file: {path}")
    return target.read_bytes()


def list_directory(aegis: AegisAgent, path: str, *, project_id: str | None = None) -> list[str]:
    _check(aegis, "file_read", path, f"List {path}", project_id=project_id)
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"No such directory: {path}")
    return sorted(p.name for p in target.iterdir())


def compute_diff(before: str, after: str, path: str) -> str:
    """Pure text diff, no I/O, no Aegis check needed — used both to
    preview a write and as part of propose_write's result."""
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def read_existing_or_empty(
    aegis: AegisAgent, path: str, *, project_id: str | None = None
) -> str:
    """Like read_file, but returns "" for a not-yet-existing path instead
    of raising — used to preview a diff for a brand-new file. The Aegis
    check (and therefore the whitelist boundary) still applies."""
    _check(aegis, "file_read", path, f"Read {path} for diff preview", project_id=project_id)
    target = Path(path)
    return target.read_text(encoding="utf-8") if target.exists() else ""


def propose_write(
    aegis: AegisAgent,
    path: str,
    new_content: str,
    *,
    backup_dir: str = "./data/snapshots",
    project_id: str | None = None,
) -> FileWriteResult:
    target = Path(path)
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    diff = compute_diff(before, new_content, path)

    decision = aegis.evaluate(
        ActionRequest(
            action_type="file_write",
            description=f"Write to {path}",
            target_path=path,
            requesting_agent="atlas",
            project_id=project_id,
        )
    )

    if decision.verdict is not Verdict.ALLOW:
        return FileWriteResult(
            applied=False, verdict=decision.verdict.value, reason=decision.reason, diff=diff
        )

    backup_path: str | None = None
    if target.exists():
        backup_root = Path(backup_dir)
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = str(backup_root / f"{target.name}.{stamp}.bak")
        shutil.copy2(target, backup_path)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_content, encoding="utf-8")

    return FileWriteResult(
        applied=True,
        verdict=decision.verdict.value,
        reason=decision.reason,
        diff=diff,
        backup_path=backup_path,
    )
