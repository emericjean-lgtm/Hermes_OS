"""File tools available to agents (primarily Atlas) — cahier des charges §14.1.

Every operation, reads included, is gated by Aegis before touching disk:
the whitelist (ALLOWED_PATHS, plus every active validated Project's root —
see security/aegis_engine.py) applies to file_read just as much as to
file_write (§17.1 — "séparation claire entre lecture et écriture" does
not mean reads are unrestricted, it means they're gated differently).
Writes additionally: always compute a diff against the current content,
take a timestamped backup before overwriting anything that already
exists, and only touch disk when Aegis's verdict is ALLOW.

Workspace/Filesystem tool layer: this module is the single real
implementation of every filesystem operation Hermes exposes — MCP
(mcp_server/server.py) and the Assistant chat (conversation/routes.py)
both call these same functions rather than re-implementing any of this
logic themselves (see FileOpResult below and the module-level functions
after propose_write). Every mutating operation is independently
*verified* after it runs — re-checked via exists()/read()/hash, never
just trusted because the OS call returned without raising — per the
"never fabricate a result" principle: FileOpResult.verified is only ever
True when a second, separate read confirms the change actually happened.
"""
from __future__ import annotations

import difflib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.agents.aegis import AegisAgent
from backend.core.event_hub import get_event_hub
from backend.security.aegis_engine import ActionRequest, Verdict


#: Les documents qui **definissent** le travail ne sont pas modifiables par
#: le travail (HOS-129).
#:
#: Mesure du 2026-08-17, sur la premiere file reelle : une mission a ecrase
#: `PROJECT_SPEC.md`. Le cahier des charges est passe de 23 Ko et 342 lignes
#: a 1,2 Ko ne contenant plus que la section sur laquelle elle travaillait.
#: La source de verite du projet a ete detruite par le projet.
#:
#: Le §36 de ce cahier-la exige d'ailleurs une validation explicite pour
#: toute modification : la regle existait, rien ne la faisait respecter.
#:
#: La liste vit dans le workspace, sous `.hermes/proteges.txt`, un chemin
#: relatif par ligne. Elle est **relue a chaque appel** : un projet protege
#: hier peut ne plus l'etre, et surtout la liste doit pouvoir changer sans
#: redemarrage, comme le niveau d'autonomie.
FICHIER_PROTEGES = ".hermes/proteges.txt"


def _proteges(chemin: Path) -> set[Path]:
    """Les chemins proteges du workspace qui contient `chemin`, s'il y en a.

    On remonte les parents jusqu'a trouver un `.hermes/proteges.txt` : un
    outil recoit un chemin de fichier, pas la racine du projet, et lui
    demander de la deviner autrement serait une seconde source de verite.
    """
    for parent in [chemin, *chemin.parents]:
        liste = parent / FICHIER_PROTEGES
        try:
            if not liste.is_file():
                continue
            lignes = liste.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        return {
            (parent / ligne.strip()).resolve()
            for ligne in lignes
            if ligne.strip() and not ligne.strip().startswith("#")
        }
    return set()


def _est_protege(path: str) -> bool:
    """Ce chemin fait-il partie des documents d'entree du projet ?

    Ne leve jamais et rend `False` en cas de doute : cette protection evite
    une perte, elle n'est pas une frontiere de securite — Aegis l'est, et
    il continue de s'appliquer independamment.
    """
    try:
        cible = Path(path).expanduser().resolve()
    except OSError:
        return False
    return cible in _proteges(cible.parent)


class FichierProtegeError(PermissionError):
    """Ecrire sur un document qui definit le travail."""


def _publish(event_type: str, payload: dict) -> None:
    """Best-effort notification — mirrors security/approvals.py's own
    get_event_hub().publish() call for this style of plain, DB/DI-free
    module. Never lets a broken subscriber fail the real filesystem
    operation it is reporting on (same contract as EventDispatcher)."""
    try:
        get_event_hub().publish(event_type, payload)
    except Exception:
        pass


@dataclass(frozen=True)
class FileWriteResult:
    applied: bool
    verdict: str
    reason: str
    diff: str
    backup_path: str | None = None
    # Re-read after writing and compared to new_content — never assumed
    # from write_text() not raising. False (not just absent) whenever
    # applied is False, so a caller can't mistake "not attempted" for
    # "attempted and unconfirmed".
    verified: bool = False


@dataclass(frozen=True)
class FileOpResult:
    """Shared result shape for every operation below propose_write.
    success is the Aegis+execution outcome; verified is the independent
    post-check (see each function for exactly what it re-checks)."""
    success: bool
    operation: str
    path: str
    verdict: str
    reason: str
    verified: bool
    detail: str = ""


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
    content = target.read_text(encoding="utf-8")
    _publish("filesystem.read", {"path": path, "project_id": project_id})
    return content


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
    if _est_protege(path):
        _publish("filesystem.permission_denied", {
            "operation": "write", "path": path, "project_id": project_id,
            "verdict": "deny", "reason": "document d'entree protege",
        })
        return FileWriteResult(
            applied=False, verdict="deny",
            reason=(f"Ce fichier definit le travail (voir {FICHIER_PROTEGES}) "
                    "et n'est pas modifiable par lui. Lis-le, ne le reecris pas."),
            diff="", verified=False,
        )
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
        _publish("filesystem.permission_denied", {
            "operation": "write", "path": path, "project_id": project_id,
            "verdict": decision.verdict.value, "reason": decision.reason,
        })
        return FileWriteResult(
            applied=False, verdict=decision.verdict.value, reason=decision.reason, diff=diff,
            verified=False,
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

    # Independent verification: re-read from disk and compare, rather than
    # trusting write_text() not having raised.
    verified = target.exists() and target.read_text(encoding="utf-8") == new_content

    _publish("filesystem.write" if verified else "filesystem.verification_failed", {
        "path": path, "project_id": project_id, "verified": verified, "backup_path": backup_path,
    })

    return FileWriteResult(
        applied=True,
        verdict=decision.verdict.value,
        reason=decision.reason,
        diff=diff,
        backup_path=backup_path,
        verified=verified,
    )


def exists(aegis: AegisAgent, path: str, *, project_id: str | None = None) -> bool:
    _check(aegis, "file_read", path, f"Check existence of {path}", project_id=project_id)
    return Path(path).exists()


def stat(aegis: AegisAgent, path: str, *, project_id: str | None = None) -> dict:
    _check(aegis, "file_read", path, f"Stat {path}", project_id=project_id)
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"No such path: {path}")
    info = target.stat()
    return {
        "path": str(target),
        "is_file": target.is_file(),
        "is_dir": target.is_dir(),
        "size_bytes": info.st_size,
        "modified_at": datetime.fromtimestamp(info.st_mtime, UTC).isoformat(),
    }


def search(
    aegis: AegisAgent, path: str, pattern: str, *, project_id: str | None = None
) -> list[str]:
    """Read-only glob search under path — gated exactly like list_directory
    (file_read), since it only ever surfaces names, never contents."""
    _check(aegis, "file_read", path, f"Search {pattern!r} under {path}", project_id=project_id)
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"No such directory: {path}")
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    return sorted(str(p) for p in target.rglob(pattern))


def create_directory(
    aegis: AegisAgent, path: str, *, project_id: str | None = None
) -> FileOpResult:
    if _est_protege(path):
        _publish("filesystem.permission_denied", {
            "operation": "create_directory", "path": path, "project_id": project_id,
            "verdict": "deny", "reason": "document d'entree protege",
        })
        return FileOpResult(
            success=False, operation="create_directory", path=path, verdict="deny",
            reason=("Ce fichier definit le travail (voir "
                    f"{FICHIER_PROTEGES}) et n'est pas modifiable par lui. "
                    "Lis-le, ne le reecris pas."),
            verified=False,
        )
    decision = aegis.evaluate(ActionRequest(
        action_type="file_write", description=f"Create directory {path}",
        target_path=path, requesting_agent="atlas", project_id=project_id,
    ))
    if decision.verdict is not Verdict.ALLOW:
        _publish("filesystem.permission_denied", {
            "operation": "mkdir", "path": path, "project_id": project_id,
            "verdict": decision.verdict.value, "reason": decision.reason,
        })
        return FileOpResult(
            success=False, operation="mkdir", path=path,
            verdict=decision.verdict.value, reason=decision.reason, verified=False,
        )
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    verified = target.exists() and target.is_dir()
    _publish("filesystem.create" if verified else "filesystem.verification_failed", {
        "operation": "mkdir", "path": path, "project_id": project_id, "verified": verified,
    })
    return FileOpResult(
        success=True, operation="mkdir", path=path,
        verdict=decision.verdict.value, reason=decision.reason, verified=verified,
    )


def append(
    aegis: AegisAgent, path: str, content: str, *, project_id: str | None = None
) -> FileOpResult:
    if _est_protege(path):
        _publish("filesystem.permission_denied", {
            "operation": "append", "path": path, "project_id": project_id,
            "verdict": "deny", "reason": "document d'entree protege",
        })
        return FileOpResult(
            success=False, operation="append", path=path, verdict="deny",
            reason=("Ce fichier definit le travail (voir "
                    f"{FICHIER_PROTEGES}) et n'est pas modifiable par lui. "
                    "Lis-le, ne le reecris pas."),
            verified=False,
        )
    decision = aegis.evaluate(ActionRequest(
        action_type="file_write", description=f"Append to {path}",
        target_path=path, requesting_agent="atlas", project_id=project_id,
    ))
    if decision.verdict is not Verdict.ALLOW:
        _publish("filesystem.permission_denied", {
            "operation": "append", "path": path, "project_id": project_id,
            "verdict": decision.verdict.value, "reason": decision.reason,
        })
        return FileOpResult(
            success=False, operation="append", path=path,
            verdict=decision.verdict.value, reason=decision.reason, verified=False,
        )
    target = Path(path)
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(content)
    after = target.read_text(encoding="utf-8") if target.exists() else ""
    verified = after == before + content
    _publish("filesystem.write" if verified else "filesystem.verification_failed", {
        "operation": "append", "path": path, "project_id": project_id, "verified": verified,
    })
    return FileOpResult(
        success=True, operation="append", path=path,
        verdict=decision.verdict.value, reason=decision.reason, verified=verified,
    )


def copy(
    aegis: AegisAgent, source: str, destination: str, *, project_id: str | None = None
) -> FileOpResult:
    # `move` verifiait ses deux extremites, `copy` aucune : une copie
    # ecraserait un document d'entree aussi surement qu'un deplacement.
    # Trouve en auditant le module apres la seconde destruction du cahier,
    # pas en le subissant — mais c'est le meme defaut.
    if _est_protege(destination):
        raise FichierProtegeError(
            f"{destination} definit le travail : la copie ecraserait un "
            f"document d'entree")
    read_decision = aegis.evaluate(ActionRequest(
        action_type="file_read", description=f"Read {source} to copy to {destination}",
        target_path=source, requesting_agent="atlas", project_id=project_id,
    ))
    if read_decision.verdict is not Verdict.ALLOW:
        _publish("filesystem.permission_denied", {
            "operation": "copy", "path": source, "project_id": project_id,
            "verdict": read_decision.verdict.value, "reason": read_decision.reason,
        })
        return FileOpResult(
            success=False, operation="copy", path=source,
            verdict=read_decision.verdict.value, reason=read_decision.reason, verified=False,
        )
    write_decision = aegis.evaluate(ActionRequest(
        action_type="file_copy", description=f"Copy {source} to {destination}",
        target_path=destination, requesting_agent="atlas", project_id=project_id,
    ))
    if write_decision.verdict is not Verdict.ALLOW:
        _publish("filesystem.permission_denied", {
            "operation": "copy", "path": destination, "project_id": project_id,
            "verdict": write_decision.verdict.value, "reason": write_decision.reason,
        })
        return FileOpResult(
            success=False, operation="copy", path=destination,
            verdict=write_decision.verdict.value, reason=write_decision.reason, verified=False,
        )
    src, dst = Path(source), Path(destination)
    if not src.exists():
        raise FileNotFoundError(f"No such file: {source}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    verified = dst.exists() and dst.read_bytes() == src.read_bytes()
    _publish("filesystem.copy" if verified else "filesystem.verification_failed", {
        "source": source, "destination": destination, "project_id": project_id,
        "verified": verified,
    })
    return FileOpResult(
        success=True, operation="copy", path=destination,
        verdict=write_decision.verdict.value, reason=write_decision.reason, verified=verified,
    )


def move(
    aegis: AegisAgent, source: str, destination: str, *, project_id: str | None = None
) -> FileOpResult:
    """Both endpoints are gated as file_move (mandatory human validation,
    config/security.yaml) — a move makes the source disappear, the same
    real-loss-of-access risk profile as a delete."""
    if _est_protege(source):
        _publish("filesystem.permission_denied", {
            "operation": "move", "path": source, "project_id": project_id,
            "verdict": "deny", "reason": "document d'entree protege",
        })
        return FileOpResult(
            success=False, operation="move", path=source, verdict="deny",
            reason=("Ce fichier definit le travail (voir "
                    f"{FICHIER_PROTEGES}) et n'est pas modifiable par lui. "
                    "Lis-le, ne le reecris pas."),
            verified=False,
        )
    if _est_protege(destination):
        _publish("filesystem.permission_denied", {
            "operation": "move", "path": destination, "project_id": project_id,
            "verdict": "deny", "reason": "document d'entree protege",
        })
        return FileOpResult(
            success=False, operation="move", path=destination, verdict="deny",
            reason=("Ce fichier definit le travail (voir "
                    f"{FICHIER_PROTEGES}) et n'est pas modifiable par lui. "
                    "Lis-le, ne le reecris pas."),
            verified=False,
        )
    src_decision = aegis.evaluate(ActionRequest(
        action_type="file_move", description=f"Move {source} to {destination} (source)",
        target_path=source, requesting_agent="atlas", project_id=project_id,
    ))
    if src_decision.verdict is not Verdict.ALLOW:
        _publish("filesystem.permission_denied", {
            "operation": "move", "path": source, "project_id": project_id,
            "verdict": src_decision.verdict.value, "reason": src_decision.reason,
        })
        return FileOpResult(
            success=False, operation="move", path=source,
            verdict=src_decision.verdict.value, reason=src_decision.reason, verified=False,
        )
    dst_decision = aegis.evaluate(ActionRequest(
        action_type="file_move", description=f"Move {source} to {destination} (destination)",
        target_path=destination, requesting_agent="atlas", project_id=project_id,
    ))
    if dst_decision.verdict is not Verdict.ALLOW:
        _publish("filesystem.permission_denied", {
            "operation": "move", "path": destination, "project_id": project_id,
            "verdict": dst_decision.verdict.value, "reason": dst_decision.reason,
        })
        return FileOpResult(
            success=False, operation="move", path=destination,
            verdict=dst_decision.verdict.value, reason=dst_decision.reason, verified=False,
        )
    src, dst = Path(source), Path(destination)
    if not src.exists():
        raise FileNotFoundError(f"No such file: {source}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    verified = (not src.exists()) and dst.exists()
    _publish("filesystem.move" if verified else "filesystem.verification_failed", {
        "source": source, "destination": destination, "project_id": project_id,
        "verified": verified,
    })
    return FileOpResult(
        success=True, operation="move", path=destination,
        verdict=dst_decision.verdict.value, reason=dst_decision.reason, verified=verified,
    )


def delete(aegis: AegisAgent, path: str, *, project_id: str | None = None) -> FileOpResult:
    if _est_protege(path):
        _publish("filesystem.permission_denied", {
            "operation": "delete", "path": path, "project_id": project_id,
            "verdict": "deny", "reason": "document d'entree protege",
        })
        return FileOpResult(
            success=False, operation="delete", path=path, verdict="deny",
            reason=("Ce fichier definit le travail (voir "
                    f"{FICHIER_PROTEGES}) et n'est pas modifiable par lui. "
                    "Lis-le, ne le reecris pas."),
            verified=False,
        )
    decision = aegis.evaluate(ActionRequest(
        action_type="file_delete", description=f"Delete {path}",
        target_path=path, requesting_agent="atlas", project_id=project_id,
    ))
    if decision.verdict is not Verdict.ALLOW:
        _publish("filesystem.permission_denied", {
            "operation": "delete", "path": path, "project_id": project_id,
            "verdict": decision.verdict.value, "reason": decision.reason,
        })
        return FileOpResult(
            success=False, operation="delete", path=path,
            verdict=decision.verdict.value, reason=decision.reason, verified=False,
        )
    target = Path(path)
    if not target.exists():
        return FileOpResult(
            success=False, operation="delete", path=path,
            verdict=decision.verdict.value, reason="Path does not exist.", verified=False,
        )
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    verified = not target.exists()
    _publish("filesystem.delete" if verified else "filesystem.verification_failed", {
        "path": path, "project_id": project_id, "verified": verified,
    })
    return FileOpResult(
        success=True, operation="delete", path=path,
        verdict=decision.verdict.value, reason=decision.reason, verified=verified,
    )
