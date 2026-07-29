"""Code Intelligence Agent profile (HOS-055D)."""

from dataclasses import dataclass, field


@dataclass
class CodeIntelligenceProfile:
    """Static profile for the Code Intelligence meta-agent."""

    agent_name: str = "CodeIntelligence"
    agent_description: str = (
        "Meta-agent that intelligently routes code tasks to the best "
        "provider — KlaatCode for project analysis and diagnostics, "
        "Oh My Pi for LSP/DAP/AST editing and debugging. "
        "Automatically selects single-best or hybrid execution."
    )
    agent_type: str = "code_intelligence"
    version: str = "1.0.0"

    # Capabilities (must match AgentCapability enum values)
    capabilities: list[str] = field(default_factory=lambda: [
        "analysis",
        "code_generation",
        "code_review",
        "testing",
        "documentation",
        "optimization",
        "custom",
    ])

    # Agent-specific constraints
    max_concurrent_tasks: int = 3
    max_retries: int = 2
    timeout_seconds: int = 600
    reliability_score: float = 0.90
    performance_score: float = 0.80
    max_tokens_per_task: int = 10000
    requires_gpu: bool = False
    tags: list[str] = field(default_factory=lambda: ["code_intelligence", "router", "meta_agent"])

    # Preferred task types
    preferred_task_types: list[str] = field(default_factory=lambda: [
        "code_analysis", "refactoring", "debugging", "architecture_review",
        "code_generation", "test_generation", "optimization",
    ])
    excluded_task_types: list[str] = field(default_factory=list)

    # Skill levels per domain
    skill_levels: dict[str, float] = field(default_factory=lambda: {
        "code_analysis": 0.92,
        "refactoring": 0.88,
        "debugging": 0.85,
        "architecture_review": 0.90,
        "code_generation": 0.87,
        "test_generation": 0.82,
        "optimization": 0.85,
    })

    # Available sub-providers
    providers: list[str] = field(default_factory=lambda: ["klaatcode", "ohmypi"])
