"""Task Decomposer for the Intelligent Mission Planner (HOS-042).

Breaks down a high-level user request into a structured task hierarchy.
"""

from __future__ import annotations

from uuid import uuid4

from backend.mission.planner.planner_models import (
    PlanningRequest,
    TaskBreakdown,
    TaskCategory,
)


class TaskDecomposer:
    """Decomposes user requests into fine-grained task breakdowns."""

    # Keyword → category mapping for auto-classification
    _CATEGORY_KEYWORDS: dict[TaskCategory, list[str]] = {
        TaskCategory.ANALYSIS: [
            "analyse", "analyze", "audit", "review", "study", "investigate",
            "understand", "explore", "evaluate", "assess",
        ],
        TaskCategory.DESIGN: [
            "design", "architect", "plan", "structure", "blueprint",
            "schema", "model", "wireframe", "prototype",
        ],
        TaskCategory.IMPLEMENTATION: [
            "implement", "code", "build", "create", "develop", "write",
            "add", "install", "configure", "setup", "set up",
        ],
        TaskCategory.TESTING: [
            "test", "verify", "validate", "check", "ensure", "confirm",
            "debug", "fix", "ci", "pipeline",
        ],
        TaskCategory.DOCUMENTATION: [
            "document", "write docs", "readme", "comment", "api doc",
            "changelog", "guide",
        ],
        TaskCategory.DEPLOYMENT: [
            "deploy", "release", "publish", "launch", "ship",
            "production", "docker", "container",
        ],
        TaskCategory.REVIEW: [
            "review", "pr", "pull request", "merge", "approve",
        ],
        TaskCategory.INTEGRATION: [
            "integrate", "connect", "link", "bind", "hook up",
            "api", "auth", "oauth", "sso",
        ],
        TaskCategory.OPTIMIZATION: [
            "optimize", "improve", "enhance", "refactor", "speed",
            "performance", "cache", "tune",
        ],
        TaskCategory.SECURITY: [
            "secure", "security", "encrypt", "hash", "csrf",
            "xss", "sql injection", "vulnerability", "penetration",
        ],
    }

    # Known task patterns with subtasks
    _TASK_PATTERNS: dict[str, list[tuple[str, str, TaskCategory]]] = {
        "authentication": [
            ("Analyze auth requirements", "Study security needs, user flows, and compliance", TaskCategory.ANALYSIS),
            ("Design auth architecture", "Choose auth strategy: OAuth, JWT, sessions, SSO", TaskCategory.DESIGN),
            ("Implement backend auth", "Create auth endpoints, middleware, token management", TaskCategory.IMPLEMENTATION),
            ("Implement frontend auth", "Login/signup forms, session management, protected routes", TaskCategory.IMPLEMENTATION),
            ("Write auth tests", "Unit tests, integration tests, security tests", TaskCategory.TESTING),
            ("Document auth flow", "API docs, setup guide, security notes", TaskCategory.DOCUMENTATION),
        ],
        "database": [
            ("Analyze data requirements", "Entities, relationships, access patterns", TaskCategory.ANALYSIS),
            ("Design database schema", "Tables, indexes, migrations strategy", TaskCategory.DESIGN),
            ("Implement database layer", "Models, migrations, queries, ORM setup", TaskCategory.IMPLEMENTATION),
            ("Write database tests", "Model tests, migration tests, performance tests", TaskCategory.TESTING),
            ("Document data model", "ERD, schema docs, migration guide", TaskCategory.DOCUMENTATION),
        ],
        "api": [
            ("Analyze API requirements", "Endpoints, data formats, auth, rate limiting", TaskCategory.ANALYSIS),
            ("Design API contract", "OpenAPI spec, versioning strategy, error handling", TaskCategory.DESIGN),
            ("Implement API endpoints", "Routes, controllers, middleware, validation", TaskCategory.IMPLEMENTATION),
            ("Write API tests", "Unit tests, integration tests, contract tests", TaskCategory.TESTING),
            ("Document API", "OpenAPI docs, usage examples, SDK generation", TaskCategory.DOCUMENTATION),
        ],
        "frontend": [
            ("Analyze UI requirements", "User stories, wireframes, component tree", TaskCategory.ANALYSIS),
            ("Design UI/UX", "Layout, components, state management, routing", TaskCategory.DESIGN),
            ("Implement UI components", "Pages, components, hooks, styling", TaskCategory.IMPLEMENTATION),
            ("Write frontend tests", "Component tests, E2E tests, accessibility tests", TaskCategory.TESTING),
            ("Document UI", "Storybook, usage guide, component docs", TaskCategory.DOCUMENTATION),
        ],
        "deployment": [
            ("Analyze deployment needs", "Environment, scaling, monitoring requirements", TaskCategory.ANALYSIS),
            ("Design deployment pipeline", "CI/CD, environments, rollback strategy", TaskCategory.DESIGN),
            ("Implement CI/CD", "Build scripts, test pipelines, deployment automation", TaskCategory.IMPLEMENTATION),
            ("Test deployment", "Staging tests, smoke tests, rollback tests", TaskCategory.TESTING),
            ("Document deployment", "Runbook, troubleshooting guide, architecture diagram", TaskCategory.DOCUMENTATION),
        ],
    }

    # Generic development lifecycle pattern
    _GENERIC_PATTERN: list[tuple[str, str, TaskCategory]] = [
        ("Analyze requirements", "Study and document requirements and constraints", TaskCategory.ANALYSIS),
        ("Design solution architecture", "Design the high-level architecture and component structure", TaskCategory.DESIGN),
        ("Implement core logic", "Implement the main functionality", TaskCategory.IMPLEMENTATION),
        ("Write tests", "Create comprehensive test suite", TaskCategory.TESTING),
        ("Document the solution", "Write documentation, guides, and examples", TaskCategory.DOCUMENTATION),
    ]

    def decompose(self, request: PlanningRequest) -> list[TaskBreakdown]:
        """Decompose a planning request into task breakdowns.

        Returns an ordered list of tasks ready for dependency building.
        """
        text = (request.user_request + " " + request.objective + " " +
                request.specification + " " + request.github_issue).lower()

        breakdowns: list[TaskBreakdown] = []
        seen_patterns: set[str] = set()

        # Try matching known patterns
        for pattern_key, subtasks in self._TASK_PATTERNS.items():
            if pattern_key in text and pattern_key not in seen_patterns:
                seen_patterns.add(pattern_key)
                for i, (title, desc, cat) in enumerate(subtasks):
                    breakdowns.append(TaskBreakdown(
                        title=title,
                        description=desc,
                        category=cat,
                        order=len(breakdowns),
                    ))

        # If no patterns matched, use generic decomposition
        if not breakdowns:
            for i, (title, desc, cat) in enumerate(self._GENERIC_PATTERN):
                breakdowns.append(TaskBreakdown(
                    title=title,
                    description=desc,
                    category=cat,
                    order=len(breakdowns),
                ))

        # Add a final validation task
        breakdowns.append(TaskBreakdown(
            title="Validation finale",
            description="Final validation: ensure all criteria are met and outputs are correct",
            category=TaskCategory.REVIEW,
            order=len(breakdowns),
            depends_on=[t.task_id for t in breakdowns],  # depends on all
        ))

        # Classify any remaining uncategorized tasks
        for bd in breakdowns:
            if bd.category == TaskCategory.CUSTOM:
                bd.category = self._classify_task(bd.title + " " + bd.description)

        return breakdowns

    def _classify_task(self, text: str) -> TaskCategory:
        """Auto-classify a task based on keyword matching."""
        text_lower = text.lower()
        best_category = TaskCategory.CUSTOM
        best_score = 0

        for category, keywords in self._CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_category = category

        return best_category if best_score > 0 else TaskCategory.IMPLEMENTATION
