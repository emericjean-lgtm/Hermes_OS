"""Loads/saves workflow definitions as YAML files under WORKFLOWS_DIR
(cahier des charges §15: "défini en YAML"). Mirrors config.py's loader
pattern but for user-editable files meant to be created/imported/saved at
runtime (via POST /workflows), not just read once at app startup.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from backend.core.config import get_settings
from backend.workflows.schema import WorkflowDefinition


def _workflows_dir() -> Path:
    path = Path(get_settings().workflows_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path_for(workflow_id: str) -> Path:
    return _workflows_dir() / f"{workflow_id}.yaml"


def save_workflow(workflow: WorkflowDefinition) -> None:
    with _path_for(workflow.id).open("w", encoding="utf-8") as f:
        yaml.safe_dump(workflow.to_dict(), f, sort_keys=False)


def load_workflow(workflow_id: str) -> WorkflowDefinition:
    path = _path_for(workflow_id)
    if not path.exists():
        raise FileNotFoundError(f"No workflow {workflow_id!r} at {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return WorkflowDefinition.from_dict(data)


def list_workflow_ids() -> list[str]:
    return sorted(p.stem for p in _workflows_dir().glob("*.yaml"))


def list_workflows(*, project_id: str | None = None) -> list[WorkflowDefinition]:
    workflows = [load_workflow(workflow_id) for workflow_id in list_workflow_ids()]
    if project_id is not None:
        workflows = [w for w in workflows if w.project_id == project_id]
    return workflows


def delete_workflow(workflow_id: str) -> bool:
    path = _path_for(workflow_id)
    if not path.exists():
        return False
    path.unlink()
    return True
