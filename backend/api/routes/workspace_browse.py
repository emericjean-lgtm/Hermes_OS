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

No Electron/Tauri needed for a real OS folder dialog, corrected 2026-09-12:
the original reasoning here assumed a native picker required bundling the
frontend as a desktop app. It doesn't, on this deployment specifically —
Hermes OS's backend already runs on the *same* Windows machine as the
browser showing the Cockpit (the whole point of the desktop launcher,
`scripts/launcher/`), so the backend can pop a real
`System.Windows.Forms.FolderBrowserDialog` on the local desktop exactly
like the launcher already pops a console window, and hand back the path
it returns. Signalé par l'opérateur : la liste de sous-dossiers ci-dessous
restait la seule option, illisible en pratique (texte clair sur le fond
blanc du popup natif d'un `<select>`, cas différent mais même famille de
défaut). `POST /filesystem/pick-folder` below is the real dialog; the
browse-by-list endpoint stays as a fallback for anyone accessing the
Cockpit from a different machine, where no local dialog is possible.
"""
from __future__ import annotations

import asyncio
import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

#: Le dialogue peut rester ouvert tant que l'operateur ne repond pas — un
#: delai court le fermerait sous ses yeux avant qu'il ait choisi. 10 min
#: est large sans etre infini : un delai absent laisserait un dialogue
#: oublie tenir la requete HTTP indefiniment.
_DELAI_DIALOGUE_S = 600.0

#: PowerShell, pas une dependance native (pywin32, etc.) : le meme choix
#: que le reste du paquet runtime (`vram_physique.py`) — deja present sur
#: la machine cible, jamais une nouvelle surface a installer pour un seul
#: dialogue. Rend le chemin choisi sur stdout, une chaine vide si annule.
_SCRIPT_DIALOGUE = """
Add-Type -AssemblyName System.Windows.Forms | Out-Null
$dialogue = New-Object System.Windows.Forms.FolderBrowserDialog
$dialogue.Description = "Choisir le dossier de travail"
$dialogue.ShowNewFolderButton = $false
if ($env:HERMES_START_DIR) { $dialogue.SelectedPath = $env:HERMES_START_DIR }
# Le dialogue natif n'a pas de fenetre parente ici (processus backend, pas
# une app de bureau) : $Host.UI... ne donne pas de handle exploitable, et
# TopMost force la fenetre au premier plan malgre l'absence de parent —
# sans lui, elle s'ouvre parfois derriere le navigateur.
$forme = New-Object System.Windows.Forms.Form
$forme.TopMost = $true
$resultat = $dialogue.ShowDialog($forme)
if ($resultat -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialogue.SelectedPath
}
"""


def _ouvrir_dialogue_natif(start_dir: str | None) -> str | None:
    """Bloque jusqu'a ce que l'operateur choisisse ou annule.

    Execute hors de la boucle asyncio par l'appelant (`asyncio.to_thread`) :
    un dialogue modal peut rester ouvert plusieurs minutes, et bloquer la
    boucle geleriat tout le reste du backend pendant ce temps.
    """
    import os

    env = dict(os.environ)
    if start_dir:
        env["HERMES_START_DIR"] = start_dir
    resultat = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", _SCRIPT_DIALOGUE],
        capture_output=True, text=True, timeout=_DELAI_DIALOGUE_S, env=env,
    )
    chemin = (resultat.stdout or "").strip()
    return chemin or None


@router.post("/filesystem/pick-folder")
async def pick_folder(payload: dict | None = None) -> dict:
    """Ouvre un vrai dialogue Windows de selection de dossier et rend le
    chemin choisi — corrige la liste illisible/peu fonctionnelle signalee
    par l'operateur. `None` (jamais une erreur) quand l'operateur annule :
    annuler un choix de dossier n'est pas un echec."""
    if platform.system() != "Windows":
        raise HTTPException(
            status_code=501,
            detail="Le dialogue natif n'existe que sur Windows ; utilisez /filesystem/browse.",
        )
    start_dir = (payload or {}).get("start_dir")
    try:
        chemin = await asyncio.to_thread(_ouvrir_dialogue_natif, start_dir)
    except subprocess.TimeoutExpired:
        return {"path": None, "cancelled": True}
    return {"path": chemin, "cancelled": chemin is None}

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
