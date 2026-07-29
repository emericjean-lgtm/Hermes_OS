"""Oh My Pi Agent Profile (HOS-055B)."""

from dataclasses import dataclass, field


@dataclass
class OhMyPiProfile:
    agent_name: str = "OhMyPiAgent"
    agent_description: str = (
        "High-performance coding agent powered by Oh My Pi (omp). "
        "LSP-wired editing, AST manipulation, DAP debugging, code execution, "
        "40+ LLM provider routing, and structural code search via Rust-native core."
    )
    capabilities: list[str] = field(default_factory=lambda: [
        "code_generation", "code_review", "analysis",
        "testing", "optimization", "custom",
    ])

    # Specialization
    priority: str = "high"
    cost_per_task: float = 1.2

    max_concurrent_tasks: int = 1
    max_retries: int = 2
    timeout_seconds: float = 300.0
    max_tokens_per_task: int = 0

    skill_levels: dict[str, float] = field(default_factory=lambda: {
        "code_editing": 0.98,
        "debugging": 0.95,
        "code_execution": 0.92,
        "ast_manipulation": 0.90,
        "lsp_navigation": 0.95,
        "runtime_testing": 0.88,
    })

    preferred_task_types: list[str] = field(default_factory=lambda: [
        "implementation", "review", "testing", "optimization",
    ])
    excluded_task_types: list[str] = field(default_factory=list)

    reliability_score: float = 0.92
    performance_score: float = 0.90

    requires_gpu: bool = False
    requires_network: bool = False

    mcp_tools: list[str] = field(default_factory=lambda: [
        "lsp_open_file", "lsp_edit", "ast_transform",
        "debug_start", "debug_step",
        "execute_python", "execute_javascript",
        "git_operation", "code_search",
    ])

    authorized_tools: list[str] = field(default_factory=list)
    authorized_skills: list[str] = field(default_factory=list)

    workspace_required: bool = True
    sandbox_required: bool = True

    tags: list[str] = field(default_factory=lambda: [
        "oh-my-pi", "omp", "lsp", "dap", "ast",
        "rust-native", "coding", "debugging",
    ])

    def to_profile_dict(self) -> dict:
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
