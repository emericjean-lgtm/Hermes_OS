"""KlaatCode Agent Profile (HOS-054C).

Defines the static profile, constraints, and runtime characteristics
of the KlaatCodeAgent. Used by the AgentSupervisor and CapabilityMatcher
for task assignment scoring.
"""

from dataclasses import dataclass, field


@dataclass
class KlaatCodeProfile:
    """Profile defining the KlaatCodeAgent's capabilities and constraints.

    This is a specialized coding agent that uses KlaatCode MCP tools
    for code analysis, generation, editing, diagnostics, and review.
    """

    # Identity
    agent_name: str = "KlaatCodeAgent"
    agent_description: str = (
        "Specialized coding agent using KlaatCode MCP tools for "
        "code analysis, generation, editing, refactoring, diagnostics, "
        "test analysis, project navigation, patch generation, and code review."
    )

    # Capabilities (mapped to Hermes AgentCapability enum)
    capabilities: list[str] = field(default_factory=lambda: [
        "analysis",
        "code_generation",
        "code_review",
        "testing",
        "optimization",
        "documentation",
    ])

    # Priority & cost
    priority: str = "normal"
    cost_per_task: float = 1.0  # Relative cost compared to other agents

    # Runtime constraints
    max_concurrent_tasks: int = 2
    max_retries: int = 3
    timeout_seconds: float = 300.0
    max_tokens_per_task: int = 0  # No limit (KlaatCode doesn't use LLM tokens)

    # Skill levels (0.0 - 1.0)
    skill_levels: dict[str, float] = field(default_factory=lambda: {
        "analysis": 0.95,
        "code_generation": 0.90,
        "code_review": 0.88,
        "testing": 0.85,
        "optimization": 0.82,
        "documentation": 0.75,
    })

    # Task type preferences
    preferred_task_types: list[str] = field(default_factory=lambda: [
        "analysis",
        "implementation",
        "review",
        "testing",
        "optimization",
    ])
    excluded_task_types: list[str] = field(default_factory=list)

    # Reliability & performance
    reliability_score: float = 0.90
    performance_score: float = 0.85

    # Hardware requirements
    requires_gpu: bool = False
    requires_network: bool = False  # KlaatCode runs locally

    # MCP tool integration
    mcp_tools: list[str] = field(default_factory=lambda: [
        "analyze_project",
        "inspect_code",
        "generate_code_plan",
        "edit_file",
        "search_code",
        "run_diagnostics",
        "validate_changes",
    ])

    # Authorized external tools
    authorized_tools: list[str] = field(default_factory=list)
    authorized_skills: list[str] = field(default_factory=list)

    # Workspace settings
    workspace_required: bool = True
    sandbox_required: bool = True

    # Metadata
    tags: list[str] = field(default_factory=lambda: [
        "klaatcode",
        "coding",
        "mcp",
        "specialized",
        "code-analysis",
    ])

    def to_agent_profile_dict(self) -> dict:
        """Convert to a dict suitable for AgentProfile construction."""
        return {
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "skill_levels": self.skill_levels,
            "preferred_task_types": self.preferred_task_types,
            "excluded_task_types": self.excluded_task_types,
            "reliability_score": self.reliability_score,
            "performance_score": self.performance_score,
            "max_tokens_per_task": self.max_tokens_per_task,
            "requires_gpu": self.requires_gpu,
            "tags": self.tags,
        }
