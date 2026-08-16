"""Shared workspace-tool schemas + executor for anything that lets a
model call filesystem tools mid-completion (Assistant chat,
conversation/routes.py; Mission/Autonomous task execution,
execution/task_executor.py). A single real implementation — both
callers are thin: they resolve which Project (if any) the current
turn/task is scoped to and hand this module (project_id, project_root);
none of them re-implement path resolution, tool schemas, or the
file_tools dispatch themselves.

## Pourquoi l'ensemble s'est élargi (HOS-115)

La version précédente s'en tenait à quatre opérations — list / exists /
read / write — au motif d'offrir « les outils qui correspondent à la façon
dont un modèle explore vraiment un workspace ». L'intention était juste,
la conséquence l'était moins : le serveur MCP exposait **douze**
opérations fichier à l'agent, toutes filtrées par Aegis et testées, et
l'Assistant n'en voyait que quatre. Renommer un fichier depuis le chat
était impossible alors que `file_tools.move` existait, marchait, et était
déjà soumis à validation humaine.

Les huit autres ne sont donc pas une nouvelle surface : c'est la même,
rendue joignable depuis le second appelant. La barrière reste où elle a
toujours été — `_check()` et le verdict d'Aegis, que ce module ne fait que
relayer honnêtement.

Ce qui *n'entre pas* ici : l'exécution de commandes. `verification_run`
lui répond avec des runners épinglés (config/verification.yaml), et
`system_command` reste l'échappatoire à validation obligatoire. Un shell
libre offert au chat contredirait les deux règles que ce dépôt s'est
données — pas d'argument fourni par l'appelant, pas d'interpréteur sur du
texte fourni par l'appelant.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.tools import syntaxe

if TYPE_CHECKING:  # pragma: no cover - annotation seulement
    from backend.tools.file_tools import FileOpResult


def resolve_in_project(project_root: str, raw_path: str) -> str:
    """Resolve a model-supplied path against the active workspace's root —
    a real relative-path join, not string concatenation, so ".."
    components collapse the normal way. This is a convenience for the
    common case (the model names a file relative to the workspace it was
    told about), never the security boundary: whatever this returns still
    goes through file_tools' Aegis gate exactly like any other path, and
    an absolute path outside root is passed through unchanged rather than
    silently reinterpreted, so Aegis's whitelist explicitly rejects it
    (see security/aegis_engine.py) rather than this function guessing."""
    root = Path(project_root).resolve()
    candidate = Path(raw_path)
    if candidate.is_absolute():
        try:
            resolved = candidate.resolve()
        except OSError:
            return raw_path
        # Already inside root: normalize. Outside root: pass through
        # unchanged rather than reinterpreting as relative — Aegis's real
        # whitelist check rejects it explicitly (see module docstring).
        return str(resolved) if resolved.is_relative_to(root) else raw_path
    return str((root / _sans_prefixe_redondant(candidate, root)).resolve())


def _sans_prefixe_redondant(candidate: Path, root: Path) -> Path:
    """Retirer le nom du workspace quand le modèle l'a préfixé lui-même.

    Mesuré le 2026-08-15 : un cahier des charges de trois livrables a
    produit **six fichiers**. Chacun existait deux fois — à la racine, et
    dans un sous-dossier répétant le nom du workspace :

        ./calculatrice.py        ./cahier_zkfzqhqu/calculatrice.py

    Le modèle connaît le chemin de son workspace et le préfixe parfois, ce
    qui est un réflexe raisonnable ; le join le rejoignait alors à la racine
    et créait un dossier fantôme. Résultat : on ne sait plus lequel des deux
    fichiers fait foi, et une relecture de vérification peut tomber sur le
    mauvais.

    Le retrait ne s'applique qu'au **premier** segment et seulement s'il
    égale exactement le nom du dossier racine. Un projet contenant
    légitimement un sous-dossier de même nom (`src/src/…` reste possible)
    n'est pas affecté, puisqu'il ne serait pas en tête.

    Ce n'est pas une frontière de sécurité — `file_tools` repasse par Aegis
    quoi qu'il arrive. C'est une correction d'ergonomie, du même ordre que
    le join lui-même.
    """
    parties = candidate.parts
    if len(parties) < 2:
        return candidate

    # HOS-123 : le préfixe n'est pas toujours d'un seul segment. Mesuré sur
    # deux missions consécutives, le modèle a écrit
    #
    #     Users/emeri/AppData/Local/Temp/memoire_X/identity_model.py
    #
    # — le chemin absolu de son workspace **amputé de sa lettre de
    # lecteur**. `Path.is_absolute()` rend `False` là-dessus sous Windows
    # (il n'y a pas de drive), donc la branche des chemins absolus ne le
    # voyait pas, et l'ancienne règle « un segment » ne reconnaissait pas
    # `Users`. Le join a recréé six niveaux de dossiers **à l'intérieur du
    # workspace**, avec un double de chaque livrable dedans.
    #
    # On retire donc le plus long préfixe du candidat qui reproduit la fin
    # du chemin de la racine. Le cas d'origine (un seul segment) en est
    # l'instance k=1 : rien ne change pour lui.
    # `normcase` et pas `==` : mesuré le 2026-08-16, la comparaison stricte
    # laissait passer `users/emeri/appdata/local/temp/<racine>/b.py` — la
    # même chose en minuscules. Sous Windows les chemins ne sont pas
    # sensibles à la casse ; les comparer comme des chaînes recréait
    # l'arbre fantôme pour toute variante de casse produite par le modèle.
    # `normcase` est l'identité sous POSIX, où la casse compte vraiment.
    def _norm(parties_: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(os.path.normcase(p) for p in parties_)

    racine_parties = root.parts
    normalisees, racine_normalisee = _norm(parties), _norm(racine_parties)
    for k in range(min(len(parties) - 1, len(racine_parties)), 0, -1):
        if normalisees[:k] == racine_normalisee[-k:]:
            return Path(*parties[k:])
    return candidate


def _outil(nom: str, description: str, parametres: dict[str, str]) -> dict[str, Any]:
    """Une déclaration d'outil, forme Ollama/OpenAI.

    Les quatre premières sont écrites à la main plus bas, chacune avec sa
    propre justification ; les huit suivantes partagent exactement la même
    forme et la répéter douze fois ferait diverger un schéma sur douze sans
    que personne le remarque. Tous les paramètres sont requis : un
    `workspace_move` sans destination n'a pas de sens à moitié.
    """
    return {
        "type": "function",
        "function": {
            "name": nom,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    nom_param: {"type": "string", "description": desc}
                    for nom_param, desc in parametres.items()
                },
                "required": list(parametres),
            },
        },
    }


def workspace_tool_schemas() -> list[dict[str, Any]]:
    """Ollama/OpenAI-shaped declarations, same format as
    connectors.web_search's web_search_tool_schema()."""
    return [
        {
            "type": "function",
            "function": {
                "name": "workspace_list",
                "description": (
                    "List the files and subdirectories directly inside a directory "
                    "of the active workspace. Use this to discover what exists "
                    "before reading a file whose exact path you don't already know."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path, relative to the workspace root. Use \".\" for the root itself.",
                        },
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "workspace_exists",
                "description": "Check whether a file or directory exists in the active workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path relative to the workspace root."},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "workspace_read",
                "description": "Read a text file's full contents from the active workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path relative to the workspace root."},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "workspace_write",
                "description": (
                    "Create a new file, or overwrite an existing one, in the active "
                    "workspace. A backup of any existing file is taken first. The "
                    "result tells you whether the write was independently verified "
                    "by re-reading the file — never assume it worked just because "
                    "you called this."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path relative to the workspace root."},
                        "content": {"type": "string", "description": "The full new content of the file."},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        _outil(
            "workspace_search",
            "Find files matching a glob pattern under a directory of the active "
            "workspace. Use this when you know roughly what a file is called but "
            "not where it is. Read-only.",
            {"path": "Directory to search under, relative to the workspace root.",
             "pattern": "Glob pattern, e.g. \"*.md\" or \"**/test_*.py\"."},
        ),
        _outil(
            "workspace_stat",
            "Size, type and modification time of a file or directory. Read-only — "
            "use it instead of reading a file whole when you only need to know how "
            "big it is or when it changed.",
            {"path": "Path relative to the workspace root."},
        ),
        _outil(
            "workspace_mkdir",
            "Create a directory (and any missing parents) in the active workspace.",
            {"path": "Directory path relative to the workspace root."},
        ),
        _outil(
            "workspace_append",
            "Append text to the end of an existing file without rewriting it. "
            "Prefer this over read-then-write when you are adding to a log, a "
            "changelog or a list — it cannot lose what is already there.",
            {"path": "Path relative to the workspace root.",
             "content": "Text to append. Include your own leading newline if you need one."},
        ),
        _outil(
            "workspace_copy",
            "Copy a file to another path inside the active workspace.",
            {"source": "Existing path, relative to the workspace root.",
             "destination": "New path, relative to the workspace root."},
        ),
        _outil(
            "workspace_move",
            "Move or rename a file inside the active workspace. This is how you "
            "rename something — there is no separate rename tool. Requires human "
            "validation before it takes effect.",
            {"source": "Existing path, relative to the workspace root.",
             "destination": "New path, relative to the workspace root."},
        ),
        _outil(
            "workspace_delete",
            "Delete a file from the active workspace. Requires human validation "
            "before it takes effect, and it is not undone by anything you can "
            "call — say what you are about to delete before calling this.",
            {"path": "Path relative to the workspace root."},
        ),
    ]


def _aegis():
    from backend.core.agent_registry import get_agent_registry
    return get_agent_registry().get("aegis")


async def execute_workspace_tool(
    name: str, arguments: dict[str, Any], *, project_id: str, project_root: str
) -> str:
    """Thin adapter over backend/tools/file_tools.py — no filesystem or
    security logic lives here, matching MCP's own adapters
    (mcp_server/server.py). Every result is reported back to the model
    honestly: a denial states the real Aegis reason, a write states
    whether it was actually verified."""
    from backend.tools import file_tools

    path_arg = str(arguments.get("path", "")).strip()
    resolved = resolve_in_project(project_root, path_arg) if path_arg else project_root
    aegis = _aegis()

    try:
        if name == "workspace_list":
            entries = file_tools.list_directory(aegis, resolved, project_id=project_id)
            return "\n".join(entries) if entries else "(dossier vide)"
        if name == "workspace_exists":
            found = file_tools.exists(aegis, resolved, project_id=project_id)
            return "true" if found else "false"
        if name == "workspace_read":
            return file_tools.read_file(aegis, resolved, project_id=project_id)
        if name == "workspace_write":
            content = str(arguments.get("content", ""))
            result = file_tools.propose_write(aegis, resolved, content, project_id=project_id)
            if not result.applied:
                return f"Écriture refusée ({result.verdict}) : {result.reason}"
            if not result.verified:
                return (
                    "L'écriture a été tentée mais n'a PAS pu être vérifiée par une "
                    "relecture du fichier — ne considère pas cette opération comme "
                    "réussie."
                )
            # HOS-121 : « écrit et vérifié » ne dit que « les octets sont
            # sur le disque ». Sur l'essai Skills360, un fichier écrit et
            # vérifié ne compilait pas, et personne ne l'a su pendant
            # trente minutes. L'analyse est gratuite, ne s'arme pas sur un
            # niveau d'autonomie, et rend l'erreur au tour suivant.
            return (f"Fichier écrit et vérifié : {resolved}"
                    + syntaxe.message(resolved, content))

        if name == "workspace_search":
            motif = str(arguments.get("pattern", "")).strip()
            if not motif:
                return "Aucun motif fourni — rien de cherché."
            trouves = file_tools.search(aegis, resolved, motif, project_id=project_id)
            return "\n".join(trouves) if trouves else "(aucune correspondance)"

        if name == "workspace_stat":
            infos = file_tools.stat(aegis, resolved, project_id=project_id)
            return "\n".join(f"{cle} : {valeur}" for cle, valeur in infos.items())

        if name == "workspace_mkdir":
            return _rendre(file_tools.create_directory(
                aegis, resolved, project_id=project_id), f"Dossier créé : {resolved}")

        if name == "workspace_append":
            contenu = str(arguments.get("content", ""))
            resultat = file_tools.append(
                aegis, resolved, contenu, project_id=project_id)
            rendu = _rendre(resultat, f"Ajouté à la fin de {resolved}")
            if resultat.success and resultat.verified:
                # C'est le fichier **entier** qu'il faut analyser : un
                # fragment ajouté peut être valide isolément et casser le
                # fichier qui le reçoit (une parenthèse, une indentation).
                try:
                    entier = file_tools.read_file(
                        aegis, resolved, project_id=project_id)
                except Exception:  # noqa: BLE001 - une analyse ratée ne casse rien
                    entier = ""
                if entier:
                    rendu += syntaxe.message(resolved, entier)
            return rendu

        if name in ("workspace_copy", "workspace_move"):
            source_arg = str(arguments.get("source", "")).strip()
            dest_arg = str(arguments.get("destination", "")).strip()
            if not source_arg or not dest_arg:
                return "Il faut une source *et* une destination — rien n'a été fait."
            source = resolve_in_project(project_root, source_arg)
            destination = resolve_in_project(project_root, dest_arg)
            operation = file_tools.copy if name == "workspace_copy" else file_tools.move
            verbe = "Copié" if name == "workspace_copy" else "Déplacé"
            return _rendre(operation(aegis, source, destination, project_id=project_id),
                           f"{verbe} : {source} -> {destination}")

        if name == "workspace_delete":
            return _rendre(file_tools.delete(
                aegis, resolved, project_id=project_id), f"Supprimé : {resolved}")

        return f"Unknown tool {name!r} — nothing executed."
    except PermissionError as exc:
        return f"Refusé par Aegis : {exc}"
    except FileNotFoundError as exc:
        return f"Introuvable : {exc}"


def _rendre(result: "FileOpResult", succes: str) -> str:
    """Traduire un `FileOpResult` pour le modèle, sans jamais l'embellir.

    Trois issues, et elles ne se confondent pas :

    * **refusée** — Aegis a dit non, et sa raison est rendue telle quelle.
      Une mise en attente de validation humaine passe par ici : l'opération
      n'a pas eu lieu, et le modèle doit le dire au lieu d'annoncer un
      succès qui viendra peut-être.
    * **exécutée mais non vérifiée** — le contraire d'un succès. C'est la
      règle centrale de ce dépôt : `success` est ce que le code croit avoir
      fait, `verified` est ce qu'une relecture a constaté.
    * **exécutée et vérifiée** — la seule qui s'annonce comme réussie.

    Les champs sont lus directement, sans `getattr` de repli. La première
    version en utilisait un, sur `applied` — le champ de `propose_write`,
    pas celui de `FileOpResult`, qui s'appelle `success`. Chaque création
    de dossier, chaque copie, chaque suppression aurait été rapportée
    « refusée » sans que rien ne signale l'erreur. Un nom de champ faux
    doit lever, pas se déguiser en verdict de sécurité.
    """
    if not result.success:
        return f"Refusé ({result.verdict}) : {result.reason}"
    if not result.verified:
        return ("L'opération a été tentée mais n'a PAS pu être vérifiée — "
                "ne la considère pas comme réussie.")
    return succes
