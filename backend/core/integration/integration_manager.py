"""Integration Manager for Hermes OS (HOS-056).

Central integration layer that orchestrates component registration,
health monitoring, dependency resolution, and system-wide coordination.
"""

from __future__ import annotations

import threading
from typing import Any

from .component_registry import ComponentCategory, ComponentInfo, ComponentRegistry, ComponentStatus
from .dependency_graph import DependencyGraph
from .health_orchestrator import HealthOrchestrator


class IntegrationManager:
    """Central integration manager for all Hermes OS components.

    Orchestrates registration, health, dependencies, and provides
    a unified view of the entire Hermes OS system.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.registry = ComponentRegistry()
        self.dependency_graph = DependencyGraph()
        self.health = HealthOrchestrator(self.registry)

        # Internal state
        self._initialized = False
        self._init_errors: list[str] = []

    def initialize(self) -> bool:
        """Register all core system components."""
        with self._lock:
            if self._initialized:
                return True
            try:
                self._register_core_components()
                self._initialized = True
                return True
            except Exception as e:
                self._init_errors.append(str(e))
                return False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def register_component(self, info: ComponentInfo) -> bool:
        """Register a component and its dependencies."""
        if self.registry.register(info):
            self.dependency_graph.add_component(info.id, info.dependencies)
            return True
        return False

    def get_system_overview(self) -> dict[str, Any]:
        """Get a complete system overview."""
        return {
            "initialized": self._initialized,
            "component_count": self.registry.count(),
            "status_summary": self.registry.get_status_summary(),
            "health": self.health.get_aggregate_health(),
            "dependencies": self.dependency_graph.get_graph_summary(),
            "by_category": self.registry.get_by_category(),
            "components": [c.to_dict() for c in self.registry.list_components()],
        }

    def _register_core_components(self) -> None:
        """Register all system components with their metadata."""
        core_components = [
            # ── Runtime ──
            ComponentInfo(
                id="runtime.event_bus", name="Runtime Event Bus",
                category=ComponentCategory.RUNTIME, version="1.0.0",
                description="Central event bus for runtime subsystem events",
                dependencies=["core.event_hub"],
                capabilities=["event_dispatch", "filtered_subscriptions"],
                produced_events=["runtime.*", "execution.*"],
                consumed_events=["system.*", "agent.*", "mission.*"],
            ),
            ComponentInfo(
                id="runtime.resource_manager", name="Resource Manager",
                category=ComponentCategory.RUNTIME, version="1.0.0",
                description="Manages GPU, CPU, RAM resources",
                dependencies=["runtime.event_bus"],
                capabilities=["resource_allocation", "resource_monitoring"],
                produced_events=["runtime.resource.*"],
                consumed_events=["runtime.*"],
            ),
            ComponentInfo(
                id="runtime.orchestrator", name="Adaptive Runtime Orchestrator",
                category=ComponentCategory.RUNTIME, version="1.0.0",
                description="Selects optimal runtime for tasks (HOS-038)",
                dependencies=["runtime.event_bus", "runtime.resource_manager"],
                capabilities=["runtime_selection", "task_routing"],
                produced_events=["runtime.orchestrator.*"],
                consumed_events=["runtime.*", "execution.*"],
            ),
            ComponentInfo(
                id="runtime.simulation", name="Simulation Engine",
                category=ComponentCategory.RUNTIME, version="1.0.0",
                description="Simulates execution for planning (HOS-039)",
                dependencies=["runtime.event_bus"],
                capabilities=["execution_simulation", "what_if_analysis"],
                produced_events=["runtime.simulation.*"],
                consumed_events=["runtime.*"],
            ),
            ComponentInfo(
                id="runtime.discovery", name="Discovery & Benchmark Engine",
                category=ComponentCategory.RUNTIME, version="1.0.0",
                description="Discovers runtimes and benchmarks (HOS-040)",
                dependencies=["runtime.event_bus", "runtime.resource_manager"],
                capabilities=["runtime_discovery", "benchmarking"],
                produced_events=["runtime.discovery.*", "runtime.benchmark.*"],
                consumed_events=["runtime.*"],
            ),
            ComponentInfo(
                id="runtime.ktransformers", name="KTransformers Integration",
                category=ComponentCategory.RUNTIME, version="1.0.0",
                description="High-performance inference via KTransformers (HOS-052)",
                dependencies=["runtime.orchestrator", "runtime.resource_manager"],
                capabilities=["model_loading", "inference", "gguf_support"],
                produced_events=["ktransformers.*"],
                consumed_events=["runtime.*", "runtime.orchestrator.*"],
            ),
            # ── Mission ──
            ComponentInfo(
                id="mission.graph", name="Mission Graph Engine",
                category=ComponentCategory.MISSION, version="1.0.0",
                description="DAG-based mission graph (HOS-041)",
                dependencies=["core.event_hub"],
                capabilities=["dag_planning", "dependency_tracking"],
                produced_events=["mission.*"],
                consumed_events=["system.*"],
            ),
            ComponentInfo(
                id="mission.planner", name="Intelligent Mission Planner",
                category=ComponentCategory.MISSION, version="1.0.0",
                description="Plans missions from user goals (HOS-042)",
                dependencies=["mission.graph", "runtime.simulation"],
                capabilities=["goal_decomposition", "resource_estimation"],
                produced_events=["mission.planner.*"],
                consumed_events=["mission.*", "runtime.simulation.*"],
            ),
            # ── Agents ──
            ComponentInfo(
                id="agent.supervisor", name="Agent Supervisor",
                category=ComponentCategory.AGENT, version="1.0.0",
                description="Manages agent lifecycle and dispatch (HOS-043)",
                dependencies=["core.event_hub"],
                capabilities=["agent_lifecycle", "capability_matching", "task_dispatch"],
                produced_events=["agent.*", "agent.supervisor.*"],
                consumed_events=["mission.*", "execution.*"],
            ),
            ComponentInfo(
                id="agent.collaboration", name="Multi-Agent Collaboration",
                category=ComponentCategory.AGENT, version="1.0.0",
                description="Coordinates multi-agent workflows (HOS-044)",
                dependencies=["agent.supervisor"],
                capabilities=["agent_messaging", "delegation", "consensus"],
                produced_events=["agent.collaboration.*"],
                consumed_events=["agent.*"],
            ),
            ComponentInfo(
                id="agent.klaatcode", name="KlaatCode Agent",
                category=ComponentCategory.AGENT, version="2.0.0",
                description="Code analysis and diagnostics agent (HOS-054)",
                dependencies=["agent.supervisor", "tools.mcp_platform"],
                capabilities=["code_analysis", "code_review", "diagnostics"],
                produced_events=["klaatcode.*"],
                consumed_events=["agent.*"],
            ),
            ComponentInfo(
                id="agent.ohmypi", name="Oh My Pi Agent",
                category=ComponentCategory.AGENT, version="2.0.0",
                description="LSP/DAP/AST code editing agent (HOS-055)",
                dependencies=["agent.supervisor", "tools.mcp_platform"],
                capabilities=["lsp_editing", "debugging", "ast_manipulation", "code_execution"],
                produced_events=["ohmypi.*"],
                consumed_events=["agent.*"],
            ),
            ComponentInfo(
                id="agent.code_intelligence", name="Code Intelligence Agent",
                category=ComponentCategory.AGENT, version="1.0.0",
                description="Routes code tasks to KlaatCode/Oh My Pi (HOS-055D)",
                dependencies=["agent.klaatcode", "agent.ohmypi"],
                capabilities=["code_task_routing", "hybrid_execution"],
                produced_events=["ci.*"],
                consumed_events=["agent.*"],
            ),
            # ── Memory ──
            ComponentInfo(
                id="memory.unified", name="Unified Memory & Knowledge Graph",
                category=ComponentCategory.MEMORY, version="1.0.0",
                description="Unified memory stack with KG (HOS-047)",
                dependencies=["core.event_hub"],
                capabilities=["episodic_memory", "semantic_memory", "knowledge_graph", "experience_manager"],
                produced_events=["memory.*"],
                consumed_events=["system.*", "agent.*", "execution.*"],
            ),
            # ── Skills ──
            ComponentInfo(
                id="skills.distribution", name="Dynamic Skill Distribution",
                category=ComponentCategory.SKILL, version="1.0.0",
                description="Selects optimal skills for tasks (HOS-048)",
                dependencies=["agent.supervisor", "memory.unified"],
                capabilities=["skill_selection", "skill_caching"],
                produced_events=["skill.*"],
                consumed_events=["agent.*", "execution.*"],
            ),
            # ── Tools ──
            ComponentInfo(
                id="tools.mcp_platform", name="MCP & External Tools Platform",
                category=ComponentCategory.TOOL, version="1.0.0",
                description="MCP server and tool registry (HOS-049)",
                dependencies=["core.event_hub"],
                capabilities=["tool_registry", "mcp_server", "sandbox_execution"],
                produced_events=["tool.*", "mcp.*"],
                consumed_events=["agent.*", "execution.*"],
            ),
            # ── Policy ──
            ComponentInfo(
                id="policy.engine", name="Policy & Approval Engine",
                category=ComponentCategory.POLICY, version="1.0.0",
                description="Governance and approval (HOS-046)",
                dependencies=["core.event_hub"],
                capabilities=["policy_evaluation", "approval_workflow", "audit_logging"],
                produced_events=["policy.*", "approval.*"],
                consumed_events=["agent.*", "execution.*"],
            ),
            # ── Workspace ──
            ComponentInfo(
                id="workspace.manager", name="Workspace Manager",
                category=ComponentCategory.WORKSPACE, version="1.0.0",
                description="Sandbox and git workspace manager (HOS-045)",
                dependencies=["policy.engine"],
                capabilities=["sandbox_isolation", "git_management", "rollback"],
                produced_events=["workspace.*"],
                consumed_events=["agent.*", "execution.*"],
            ),
            # ── Execution ──
            ComponentInfo(
                id="execution.engine", name="Autonomous Mission Execution Engine",
                category=ComponentCategory.EXECUTION, version="1.0.0",
                description="Full execution pipeline (HOS-050)",
                dependencies=["mission.planner", "agent.supervisor", "skills.distribution",
                              "tools.mcp_platform", "runtime.orchestrator"],
                capabilities=["task_scheduling", "agent_coordination", "validation", "feedback_loop"],
                produced_events=["execution.*"],
                consumed_events=["mission.*", "agent.*", "runtime.*"],
            ),
            # ── Integrations ──
            ComponentInfo(
                id="integration.alexandrie", name="Alexandrie Document Integration",
                category=ComponentCategory.INTEGRATION, version="1.0.0",
                description="Document management system (HOS-053)",
                dependencies=["memory.unified"],
                capabilities=["document_sync", "hybrid_search"],
                produced_events=["alexandrie.*"],
                consumed_events=["memory.*"],
            ),
            # ── System ──
            ComponentInfo(
                id="core.event_hub", name="Core Event Hub",
                category=ComponentCategory.CORE, version="1.0.0",
                description="Core message bus and event hub",
                dependencies=[],
                capabilities=["event_publishing", "event_subscription", "event_history"],
                produced_events=["system.*", "core.*"],
                consumed_events=["*"],
            ),
            ComponentInfo(
                id="core.integration", name="System Integration Manager",
                category=ComponentCategory.CORE, version="1.0.0",
                description="Global integration audit (HOS-056)",
                dependencies=["core.event_hub"],
                capabilities=["component_registry", "health_monitoring", "dependency_graph"],
                produced_events=["system.integration.*"],
                consumed_events=["*"],
            ),
        ]

        for comp in core_components:
            self.register_component(comp)
