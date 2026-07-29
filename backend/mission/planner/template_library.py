"""Template Library for the Intelligent Mission Planner (HOS-042).

Provides reusable mission templates for common project types.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.mission.planner.planner_models import (
    TaskBreakdown,
    TaskCategory,
)


@dataclass
class MissionTemplate:
    """A reusable mission template."""

    template_id: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    tasks: list[TaskBreakdown] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


# ── Template Registry ────────────────────────────────────────

class TemplateLibrary:
    """Registry of reusable mission templates."""

    def __init__(self) -> None:
        self._templates: dict[str, MissionTemplate] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in templates."""
        self._add_web_app_template()
        self._add_api_service_template()
        self._add_cli_tool_template()
        self._add_data_pipeline_template()
        self._add_microservice_template()
        self._add_refactoring_template()

    def _add_web_app_template(self) -> None:
        self._templates["web_app"] = MissionTemplate(
            template_id="web_app",
            name="Full-Stack Web Application",
            description="Complete web application with frontend, backend, database, auth, and deployment",
            category="development",
            tags=["web", "fullstack", "react", "api"],
            tasks=[
                TaskBreakdown(title="Requirements analysis", description="Define features, user stories, and technical constraints", category=TaskCategory.ANALYSIS, order=0),
                TaskBreakdown(title="Architecture design", description="Design system architecture, data model, and API contract", category=TaskCategory.DESIGN, order=1),
                TaskBreakdown(title="Database schema", description="Create database schema, migrations, and seed data", category=TaskCategory.IMPLEMENTATION, order=2),
                TaskBreakdown(title="Backend API", description="Implement REST/GraphQL API with validation", category=TaskCategory.IMPLEMENTATION, order=3),
                TaskBreakdown(title="Authentication", description="Implement authentication and authorization", category=TaskCategory.SECURITY, order=4),
                TaskBreakdown(title="Frontend UI", description="Implement UI components, routing, and state management", category=TaskCategory.IMPLEMENTATION, order=5),
                TaskBreakdown(title="Integration tests", description="Write integration tests for API and UI", category=TaskCategory.TESTING, order=6),
                TaskBreakdown(title="Documentation", description="API docs, README, deployment guide", category=TaskCategory.DOCUMENTATION, order=7),
                TaskBreakdown(title="Deployment setup", description="CI/CD pipeline and deployment configuration", category=TaskCategory.DEPLOYMENT, order=8),
                TaskBreakdown(title="Final review", description="Code review, security audit, performance check", category=TaskCategory.REVIEW, order=9),
            ],
        )

    def _add_api_service_template(self) -> None:
        self._templates["api_service"] = MissionTemplate(
            template_id="api_service",
            name="REST API Service",
            description="Standalone REST API service with database and documentation",
            category="development",
            tags=["api", "backend", "rest"],
            tasks=[
                TaskBreakdown(title="Analyze API requirements", description="Define endpoints, data flow, and constraints", category=TaskCategory.ANALYSIS, order=0),
                TaskBreakdown(title="Design API contract", description="OpenAPI spec, data models, error handling", category=TaskCategory.DESIGN, order=1),
                TaskBreakdown(title="Implement data layer", description="Database models, migrations, repositories", category=TaskCategory.IMPLEMENTATION, order=2),
                TaskBreakdown(title="Implement API routes", description="Controllers, middleware, validation", category=TaskCategory.IMPLEMENTATION, order=3),
                TaskBreakdown(title="Implement auth", description="API keys, JWT, or OAuth authentication", category=TaskCategory.SECURITY, order=4),
                TaskBreakdown(title="Write API tests", description="Unit and integration tests for all endpoints", category=TaskCategory.TESTING, order=5),
                TaskBreakdown(title="Write API documentation", description="OpenAPI docs, usage examples", category=TaskCategory.DOCUMENTATION, order=6),
                TaskBreakdown(title="Deploy and monitor", description="Deployment, monitoring, and alerting", category=TaskCategory.DEPLOYMENT, order=7),
            ],
        )

    def _add_cli_tool_template(self) -> None:
        self._templates["cli_tool"] = MissionTemplate(
            template_id="cli_tool",
            name="CLI Tool",
            description="Command-line tool with argument parsing, config, and tests",
            category="development",
            tags=["cli", "tool", "python"],
            tasks=[
                TaskBreakdown(title="Define CLI interface", description="Commands, flags, arguments specification", category=TaskCategory.DESIGN, order=0),
                TaskBreakdown(title="Implement core logic", description="Main functionality and business logic", category=TaskCategory.IMPLEMENTATION, order=1),
                TaskBreakdown(title="Add argument parsing", description="CLI argument parsing and validation", category=TaskCategory.IMPLEMENTATION, order=2),
                TaskBreakdown(title="Add configuration", description="Config file parsing and env var support", category=TaskCategory.IMPLEMENTATION, order=3),
                TaskBreakdown(title="Write tests", description="Unit, integration, and CLI tests", category=TaskCategory.TESTING, order=4),
                TaskBreakdown(title="Write documentation", description="Usage docs, man page, examples", category=TaskCategory.DOCUMENTATION, order=5),
                TaskBreakdown(title="Package and distribute", description="Packaging, PyPI/brew, CI release", category=TaskCategory.DEPLOYMENT, order=6),
            ],
        )

    def _add_data_pipeline_template(self) -> None:
        self._templates["data_pipeline"] = MissionTemplate(
            template_id="data_pipeline",
            name="Data Pipeline",
            description="ETL/ELT data pipeline with ingestion, transformation, and storage",
            category="development",
            tags=["data", "etl", "pipeline"],
            tasks=[
                TaskBreakdown(title="Analyze data sources", description="Data sources, formats, volume, frequency", category=TaskCategory.ANALYSIS, order=0),
                TaskBreakdown(title="Design pipeline architecture", description="ETL flow, storage, error handling", category=TaskCategory.DESIGN, order=1),
                TaskBreakdown(title="Implement data ingestion", description="Connectors, batching, streaming", category=TaskCategory.IMPLEMENTATION, order=2),
                TaskBreakdown(title="Implement transformations", description="Cleaning, enrichment, aggregation", category=TaskCategory.IMPLEMENTATION, order=3),
                TaskBreakdown(title="Implement storage layer", description="Database, data warehouse, or lake", category=TaskCategory.IMPLEMENTATION, order=4),
                TaskBreakdown(title="Test pipeline", description="Data quality tests, performance tests", category=TaskCategory.TESTING, order=5),
                TaskBreakdown(title="Document pipeline", description="Data lineage, runbook, schema docs", category=TaskCategory.DOCUMENTATION, order=6),
                TaskBreakdown(title="Deploy and schedule", description="Orchestration, monitoring, alerts", category=TaskCategory.DEPLOYMENT, order=7),
            ],
        )

    def _add_microservice_template(self) -> None:
        self._templates["microservice"] = MissionTemplate(
            template_id="microservice",
            name="Microservice",
            description="Single microservice with gRPC/REST, health checks, and Docker",
            category="development",
            tags=["microservice", "docker", "grpc"],
            tasks=[
                TaskBreakdown(title="Define service boundary", description="API contract, data ownership, dependencies", category=TaskCategory.ANALYSIS, order=0),
                TaskBreakdown(title="Design service architecture", description="Internal architecture, patterns, tech stack", category=TaskCategory.DESIGN, order=1),
                TaskBreakdown(title="Implement service core", description="Business logic, data access, gRPC/REST", category=TaskCategory.IMPLEMENTATION, order=2),
                TaskBreakdown(title="Add health and metrics", description="Health checks, metrics, logging, tracing", category=TaskCategory.IMPLEMENTATION, order=3),
                TaskBreakdown(title="Add Docker support", description="Dockerfile, docker-compose, .dockerignore", category=TaskCategory.DEPLOYMENT, order=4),
                TaskBreakdown(title="Write tests", description="Unit, contract, and integration tests", category=TaskCategory.TESTING, order=5),
                TaskBreakdown(title="Write runbook", description="Operations guide, troubleshooting", category=TaskCategory.DOCUMENTATION, order=6),
            ],
        )

    def _add_refactoring_template(self) -> None:
        self._templates["refactoring"] = MissionTemplate(
            template_id="refactoring",
            name="Code Refactoring",
            description="Systematic code refactoring with analysis, migration, and validation",
            category="development",
            tags=["refactoring", "cleanup", "migration"],
            tasks=[
                TaskBreakdown(title="Analyze codebase", description="Identify anti-patterns, tech debt, complexity hotspots", category=TaskCategory.ANALYSIS, order=0),
                TaskBreakdown(title="Design target architecture", description="Target patterns, naming conventions, structure", category=TaskCategory.DESIGN, order=1),
                TaskBreakdown(title="Refactor core modules", description="Extract, rename, restructure core logic", category=TaskCategory.OPTIMIZATION, order=2),
                TaskBreakdown(title="Update tests", description="Update tests for new structure, add missing coverage", category=TaskCategory.TESTING, order=3),
                TaskBreakdown(title="Update documentation", description="Update architecture docs, API references", category=TaskCategory.DOCUMENTATION, order=4),
                TaskBreakdown(title="Validate and review", description="Regression tests, performance comparison, code review", category=TaskCategory.REVIEW, order=5),
            ],
        )

    # ── API ──────────────────────────────────────────────────

    def list_templates(self) -> list[MissionTemplate]:
        return list(self._templates.values())

    def get_template(self, template_id: str) -> MissionTemplate | None:
        return self._templates.get(template_id)

    def register(self, template: MissionTemplate) -> None:
        self._templates[template.template_id] = template

    def search(self, query: str) -> list[MissionTemplate]:
        q = query.lower()
        results: list[MissionTemplate] = []
        for tpl in self._templates.values():
            if (q in tpl.name.lower() or q in tpl.description.lower() or
                    any(q in tag.lower() for tag in tpl.tags)):
                results.append(tpl)
        return results
