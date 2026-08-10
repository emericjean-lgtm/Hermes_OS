"""Shared workspace-tool schemas + executor for anything that lets a
model call filesystem tools mid-completion (Assistant chat,
conversation/routes.py; Mission/Autonomous task execution,
execution/task_executor.py). A single real implementation — both
callers are thin: they resolve which Project (if any) the current
turn/task is scoped to and hand this module (project_id, project_root);
none of them re-implement path resolution, tool schemas, or the
file_tools dispatch themselves.

Deliberately a small, progressive-discovery tool set (list/exists/read/
write) rather than every file_tools operation — copy/move/delete stay
MCP-only for now (mcp_server/server.py), matching "offer the tools that
match how a model actually explores a workspace" rather than the full
surface at once.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


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
    return str((root / candidate).resolve())


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
            return f"Fichier écrit et vérifié : {resolved}"
        return f"Unknown tool {name!r} — nothing executed."
    except PermissionError as exc:
        return f"Refusé par Aegis : {exc}"
    except FileNotFoundError as exc:
        return f"Introuvable : {exc}"
