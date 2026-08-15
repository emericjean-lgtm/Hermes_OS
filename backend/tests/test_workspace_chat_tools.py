"""backend/tools/workspace_chat_tools.py — the single real path-resolution
+ tool-schema + file_tools-adapter implementation shared by the Assistant
chat (conversation/routes.py) and Mission/Autonomous task execution
(execution/task_executor.py). Testing it once here, rather than per
consumer, is the point of extracting it."""
from __future__ import annotations

import pytest

from backend.tools import workspace_chat_tools as wct


# ── resolve_in_project ──────────────────────────────────────────


def test_resolve_relative_path_joins_against_root(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    resolved = wct.resolve_in_project(str(root), "AGENTS.md")
    assert resolved == str((root / "AGENTS.md").resolve())


def test_resolve_relative_path_with_subdirectory(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    resolved = wct.resolve_in_project(str(root), "src/main.py")
    assert resolved == str((root / "src" / "main.py").resolve())


def test_resolve_absolute_path_inside_root_is_normalized(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    target = root / "f.txt"
    resolved = wct.resolve_in_project(str(root), str(target))
    assert resolved == str(target.resolve())


def test_resolve_absolute_path_outside_root_passes_through_unchanged(tmp_path):
    """A convenience, never the security boundary — an absolute path
    outside root is handed back as-is so Aegis's real whitelist check
    rejects it explicitly, rather than this function silently
    reinterpreting a model/task-supplied absolute path as relative."""
    root = tmp_path / "ws"
    root.mkdir()
    outside = str(tmp_path / "elsewhere" / "f.txt")
    assert wct.resolve_in_project(str(root), outside) == outside


def test_resolve_relative_escape_collapses_within_join(tmp_path):
    """Path.resolve() on (root / "../../x") collapses the ".." the normal
    way — the result may land outside root, and that is fine: it is
    Aegis's whitelist check, not this resolver, that must reject it."""
    root = tmp_path / "ws" / "nested"
    root.mkdir(parents=True)
    resolved = wct.resolve_in_project(str(root), "../../escape.txt")
    assert resolved == str((tmp_path / "escape.txt").resolve())


# ── workspace_tool_schemas ───────────────────────────────────────


def test_workspace_tool_schemas_covers_every_file_operation():
    """Les douze opérations de `file_tools`, plus seulement quatre (HOS-115).

    Ce test épinglait l'ensemble « découverte progressive » — list /
    exists / read / write — et il avait raison de le faire : c'était une
    décision, écrite dans le docstring du module. Elle a changé sur
    demande, pour une raison mesurable : le serveur MCP exposait déjà les
    douze opérations à l'agent, si bien que renommer un fichier depuis le
    chat était impossible alors que `file_tools.move` existait, marchait,
    et passait déjà par une validation humaine.

    L'assertion reste une **égalité** et non une inclusion : ce qui compte
    n'est pas qu'il y ait « au moins » ces outils, mais que la liste offerte
    au modèle soit exactement celle qu'on a décidé de lui donner. Un outil
    qui s'y ajouterait sans passer par ici ne serait vu de personne.
    """
    names = {t["function"]["name"] for t in wct.workspace_tool_schemas()}
    assert names == {
        "workspace_list", "workspace_exists", "workspace_read", "workspace_write",
        "workspace_search", "workspace_stat", "workspace_mkdir", "workspace_append",
        "workspace_copy", "workspace_move", "workspace_delete",
    }


# ── execute_workspace_tool: thin adapter, no duplicated logic ───


@pytest.mark.asyncio
async def test_execute_workspace_tool_read_denied_outside_project():
    """No project bound (project_root="") — the adapter must not invent
    access; it reports the real Aegis refusal, same as file_tools itself
    would raise."""
    result = await wct.execute_workspace_tool(
        "workspace_read", {"path": "f.txt"}, project_id="", project_root="",
    )
    assert "Refusé par Aegis" in result or "refusée" in result.lower()


@pytest.mark.asyncio
async def test_execute_workspace_tool_unknown_name_reports_unknown():
    result = await wct.execute_workspace_tool(
        "workspace_delete_everything", {}, project_id="", project_root="",
    )
    assert "Unknown tool" in result
