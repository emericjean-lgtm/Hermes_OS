"""Graph Serializer for the Mission Graph Engine (HOS-041).

Import/export missions as JSON and YAML with versioning.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from backend.mission.mission_models import (
    Mission,
    MissionContext,
    MissionEdge,
    MissionNode,
    MissionPriority,
    MissionStatus,
    MissionType,
    NodeStatus,
)


class GraphSerializer:
    """Serializes and deserializes missions."""

    SCHEMA_VERSION = "1.0.0"

    # ── JSON ────────────────────────────────────────────────

    def to_json(self, mission: Mission, indent: int = 2) -> str:
        """Serialize a mission to JSON string."""
        data = self._mission_to_dict(mission)
        return json.dumps(data, indent=indent, default=str)

    def from_json(self, json_str: str) -> Mission:
        """Deserialize a mission from JSON string."""
        data = json.loads(json_str)
        return self._dict_to_mission(data)

    def export_to_file(self, mission: Mission, path: str) -> None:
        with open(path, "w") as f:
            f.write(self.to_json(mission))

    def import_from_file(self, path: str) -> Mission:
        with open(path, "r") as f:
            return self.from_json(f.read())

    # ── YAML ────────────────────────────────────────────────

    def to_yaml(self, mission: Mission) -> str:
        """Serialize a mission to YAML string."""
        try:
            import yaml
            data = self._mission_to_dict(mission)
            return yaml.dump(data, default_flow_style=False, allow_unicode=True)
        except ImportError:
            return self.to_json(mission)

    def from_yaml(self, yaml_str: str) -> Mission:
        try:
            import yaml
            data = yaml.safe_load(yaml_str)
            return self._dict_to_mission(data)
        except ImportError:
            return self.from_json(yaml_str)

    # ── Internal ────────────────────────────────────────────

    def _mission_to_dict(self, mission: Mission) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "mission_id": mission.mission_id,
            "title": mission.title,
            "description": mission.description,
            "objective": mission.objective,
            "type": mission.type.value,
            "priority": mission.priority.value,
            "status": mission.status.value,
            "context": {
                "project_id": mission.context.project_id,
                "user_id": mission.context.user_id,
                "repository": mission.context.repository,
                "branch": mission.context.branch,
                "tags": mission.context.tags,
                "metadata": mission.context.metadata,
            },
            "nodes": [
                {
                    "node_id": n.node_id,
                    "title": n.title,
                    "description": n.description,
                    "type": n.type,
                    "priority": n.priority.value,
                    "status": n.status.value,
                    "preferred_agent": n.preferred_agent,
                    "preferred_runtime": n.preferred_runtime,
                    "benchmark_profile": n.benchmark_profile,
                    "required_skills": n.required_skills,
                    "estimated_resources": n.estimated_resources,
                    "estimated_duration_ms": n.estimated_duration_ms,
                    "depends_on": n.depends_on,
                    "validation_criteria": n.validation_criteria,
                    "expected_outputs": n.expected_outputs,
                }
                for n in mission.nodes
            ],
            "edges": [
                {"edge_id": e.edge_id, "source_id": e.source_id, "target_id": e.target_id}
                for e in mission.edges
            ],
            "metadata": mission.metadata,
            "created_at": mission.created_at.isoformat(),
            "updated_at": mission.updated_at.isoformat() if mission.updated_at else None,
        }

    def _dict_to_mission(self, data: dict) -> Mission:
        mission = Mission(
            mission_id=data.get("mission_id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            objective=data.get("objective", ""),
            type=MissionType(data.get("type", "custom")),
            priority=MissionPriority(data.get("priority", "normal")),
            status=MissionStatus(data.get("status", "created")),
            metadata=data.get("metadata", {}),
        )

        ctx = data.get("context", {})
        mission.context = MissionContext(
            project_id=ctx.get("project_id", ""),
            user_id=ctx.get("user_id", ""),
            repository=ctx.get("repository", ""),
            branch=ctx.get("branch", ""),
            tags=ctx.get("tags", []),
            metadata=ctx.get("metadata", {}),
        )

        mission.nodes = [
            MissionNode(
                node_id=n.get("node_id", ""),
                title=n.get("title", ""),
                description=n.get("description", ""),
                type=n.get("type", "task"),
                priority=MissionPriority(n.get("priority", "normal")),
                status=NodeStatus(n.get("status", "pending")),
                preferred_agent=n.get("preferred_agent", ""),
                preferred_runtime=n.get("preferred_runtime", ""),
                benchmark_profile=n.get("benchmark_profile", ""),
                required_skills=n.get("required_skills", []),
                estimated_resources=n.get("estimated_resources", {}),
                estimated_duration_ms=n.get("estimated_duration_ms", 0.0),
                depends_on=n.get("depends_on", []),
                validation_criteria=n.get("validation_criteria", []),
                expected_outputs=n.get("expected_outputs", []),
            )
            for n in data.get("nodes", [])
        ]

        mission.edges = [
            MissionEdge(
                edge_id=e.get("edge_id", ""),
                source_id=e.get("source_id", ""),
                target_id=e.get("target_id", ""),
            )
            for e in data.get("edges", [])
        ]

        return mission
