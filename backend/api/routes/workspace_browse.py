"""Read-only local directory browsing, for the "add a workspace" folder
picker (Workspace/Filesystem tool layer, Phase 10).

Deliberately NOT behind Aegis: the whole point is to let a user browse
*before* any folder has been authorized as a Project — there is nothing
yet for Aegis's whitelist to check against. The safety boundary here is
narrower and different in kind: this endpoint can only ever return
directory *names* one level at a time, never file contents, and it
refuses to descend into a short list of well-known system directories a
user should not casually register as a workspace. It grants no write
access and no read access to file contents — selecting a result here
only pre-fills the "add workspace" form; the folder still has to be
registered (POST /projects) and validated (POST /projects/{id}/validate)
before anything in it is actually reachable by an agent or the chat.

No Electron/Tauri/native file dialog: this is a plain Next.js web app
(confirmed: no such dependency in frontend/package.json), so a real OS
folder picker isn't available without adding one of those. Browsing
server-side, through an endpoint the backend already trusts to run
locally, is the lighter-weight answer the mission's own Phase 10
explicitly asks for instead.
"""
from __future__ import annotations

import platform
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

# Matched case-insensitively against the resolved path's own parts, not
# just a string prefix — "C:\Windows" must not match "C:\WindowsStuff".
_BLOCKED_WINDOWS_DIRS = {
    "windows", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "recovery",
}
_BLOCKED_POSIX_DIRS = {
    "etc", "sys", "proc", "dev", "boot", "root", "private", "system",
}


def _is_blocked(resolved: Path) -> bool:
    parts = {p.lower() for p in resolved.parts}
    if platform.system() == "Windows":
        return bool(parts & _BLOCKED_WINDOWS_DIRS)
    return bool(parts & _BLOCKED_POSIX_DIRS)


def _default_roots() -> list[str]:
    """Starting points shown when no path is given: the user's home
    directory, plus every drive root on Windows (there is no single
    filesystem root to start from the way POSIX has "/")."""
    roots = [str(Path.home())]
    if platform.system() == "Windows":
        import string
        from ctypes import windll  # type: ignore[attr-defined]

        try:
            bitmask = windll.kernel32.GetLogicalDrives()
            for i, letter in enumerate(string.ascii_uppercase):
                if bitmask & (1 << i):
                    roots.append(f"{letter}:\\")
        except Exception:
            pass
    return roots


@router.get("/filesystem/browse")
async def browse(path: str | None = None) -> dict:
    """List the immediate subdirectories of path (or a set of sensible
    starting points when path is omitted). Directories only — never
    files, never file contents. Refuses to list a well-known system
    directory outright rather than silently filtering its contents."""
    if not path:
        roots = _default_roots()
        return {"path": None, "parent": None, "directories": sorted(roots)}

    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid path: {exc}") from exc

    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"{resolved} does not exist.")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"{resolved} is not a directory.")
    if _is_blocked(resolved):
        raise HTTPException(
            status_code=403,
            detail=f"{resolved} is a system directory and cannot be browsed or registered.",
        )

    try:
        directories = sorted(
            entry.name for entry in resolved.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )
    except OSError as exc:
        raise HTTPException(status_code=403, detail=f"Cannot list {resolved}: {exc}") from exc

    parent = resolved.parent
    return {
        "path": str(resolved),
        "parent": str(parent) if parent != resolved else None,
        "directories": directories,
    }
