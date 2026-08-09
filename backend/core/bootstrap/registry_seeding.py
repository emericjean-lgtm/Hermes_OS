"""Populates the runtime registries from the resources Hermes actually has.

Every subsystem here already existed and already knew how to enumerate itself;
nothing called any of it, so a fully assembled Hermes served ``agents: 0``,
``tools: 0``, ``mcp/servers: 0`` and a coordinator that made assignments against
empty catalogues. The composition root is where that gap belongs (R-002 P2).

Nothing in this module invents a resource. Every entry comes from a declared,
verifiable source:

* **Agents** — the ten enabled entries in ``config/agents.yaml``, already
  instantiated by :class:`backend.core.agent_registry.AgentRegistry`.
* **Tools / MCP servers** — the definitions the KlaatCode and Oh My Pi MCP
  adapters produce from their live clients. KlaatCode's own
  ``register_klaatcode()`` helper is reused rather than reimplemented.
* **Runtimes** — the runtimes the SDS registry has actually started.
* **Skills** — nothing. The repository contains no ``SkillDefinition`` anywhere,
  so the skill registry is legitimately empty and seeding it would mean
  fabricating capabilities. Reported as zero rather than filled with fiction.

Seeding is best-effort per resource: a source that cannot be reached is logged
and skipped, never allowed to fail startup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("hermes_os.bootstrap.seeding")


#: ``config/agents.yaml`` gives every agent a ``role``; the supervisor speaks
#: :class:`~backend.agents.agent_models.AgentCapability`. This is the translation
#: between the two existing vocabularies — the roles are declared, not invented.
ROLE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "orchestrator": ("ANALYSIS", "DESIGN"),
    "swift": ("CHAT",),
    "code": ("CODE_GENERATION", "CODE_REVIEW"),
    "standard": ("CHAT", "RESEARCH"),
    "security": ("SECURITY_AUDIT",),
    "vision": ("ANALYSIS",),
    "reasoning": ("ANALYSIS", "CODE_REVIEW"),
    "embedding": ("DATA_PROCESSING",),
}


@dataclass
class SeedingReport:
    """What was registered, and what could not be."""

    agents: int = 0
    tools: int = 0
    mcp_servers: int = 0
    mcp_tools: int = 0
    runtimes: int = 0
    skills: int = 0
    coordinator_agents: int = 0
    coordinator_runtimes: int = 0
    coordinator_tools: int = 0
    orchestrator_runtimes: int = 0
    skipped: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agents": self.agents,
            "tools": self.tools,
            "mcp_servers": self.mcp_servers,
            "mcp_tools": self.mcp_tools,
            "runtimes": self.runtimes,
            "skills": self.skills,
            "coordinator": {
                "agents": self.coordinator_agents,
                "runtimes": self.coordinator_runtimes,
                "tools": self.coordinator_tools,
            },
            "orchestrator_runtimes": self.orchestrator_runtimes,
            "skipped": dict(self.skipped),
            "notes": list(self.notes),
        }

    def empty_registries(self) -> list[str]:
        """Registries that are still empty after seeding.

        ``skills`` is excluded: it has no declared source in this repository, so
        an empty skill registry is the truthful state, not a wiring failure.
        """
        return [
            name for name, count in (
                ("agents", self.agents),
                ("tools", self.tools),
                ("mcp_servers", self.mcp_servers),
                ("runtimes", self.runtimes),
            ) if count == 0
        ]


def seed_registries(container: Any, runtimes_only: bool = False) -> SeedingReport:
    """Fill every registry the Cockpit reads from. Never raises.

    Args:
        runtimes_only: re-seed just the runtime catalogues. The SDS runtime
            registry is populated by the app's ``lifespan``, which runs *after*
            the composition root has built everything, so at build time it is
            legitimately empty. The lifespan calls back here once the runtimes
            are installed rather than leaving the coordinator with none.
    """
    report = SeedingReport()

    if not runtimes_only:
        _seed_agents(container, report)
        _seed_tools_and_mcp(container, report)
        _count_skills(container, report)

    _count_runtimes(report)
    _seed_coordinator(container, report, runtimes_only=runtimes_only)
    if not runtimes_only:
        _recount(container, report)

    if runtimes_only:
        # A runtimes-only pass never looks at the other catalogues, so reporting
        # them as "still empty" would be a false alarm about work it did not do.
        logger.info("runtime catalogues re-seeded: %d runtime(s), "
                    "%d to the coordinator, %d to the orchestrator",
                    report.runtimes, report.coordinator_runtimes,
                    report.orchestrator_runtimes)
        return report

    still_empty = report.empty_registries()
    if still_empty:
        logger.warning("registries still empty after seeding: %s",
                       ", ".join(still_empty))
    logger.info(
        "registries seeded: %d agents, %d tools, %d MCP servers (%d MCP tools), "
        "%d runtimes", report.agents, report.tools, report.mcp_servers,
        report.mcp_tools, report.runtimes,
    )
    return report


# ── Agents ────────────────────────────────────────────────────────────


def _seed_agents(container: Any, report: SeedingReport) -> None:
    """Register the agents declared in config/agents.yaml with the supervisor.

    ``AgentRegistry`` instantiates them and ``AgentSupervisor`` tracks lifecycle
    and dispatch, and the two were never introduced to each other, so
    ``GET /api/v1/agents`` returned an empty list on a system with ten working
    agents.
    """
    try:
        supervisor = container.get("agent_supervisor")
    except Exception as exc:
        report.skipped["agents"] = f"no agent_supervisor: {exc}"
        return

    try:
        from backend.agents.agent_models import AgentCapability
        from backend.core.agent_registry import get_agent_registry
        from backend.core.config import load_agents_config

        registry = get_agent_registry()
        declared = load_agents_config().get("agents", {})
    except Exception as exc:
        report.skipped["agents"] = f"{type(exc).__name__}: {exc}"
        logger.warning("agent seeding unavailable", exc_info=True)
        return

    existing = {a.name for a in supervisor.list_agents()}

    for key in registry.list_enabled():
        if key in existing:
            continue
        spec = declared.get(key, {})
        role = str(spec.get("role", "standard"))
        names = ROLE_CAPABILITIES.get(role, ("CHAT",))
        capabilities = [getattr(AgentCapability, n) for n in names
                        if hasattr(AgentCapability, n)]
        if not capabilities:
            capabilities = [AgentCapability.CHAT]

        try:
            supervisor.create_agent(
                name=key,
                capabilities=capabilities,
                description=str(spec.get("description", "")),
            )
            report.agents += 1
        except Exception:
            logger.warning("could not register agent %s", key, exc_info=True)

    if report.agents == 0 and existing:
        report.notes.append(
            f"{len(existing)} agent(s) were already registered before seeding")


# ── Tools and MCP ─────────────────────────────────────────────────────


def _seed_tools_and_mcp(container: Any, report: SeedingReport) -> None:
    """Register the KlaatCode and Oh My Pi tools and MCP servers.

    KlaatCode ships ``register_klaatcode()``, which registers its seven tools in
    the Tool Registry and itself in the MCP Registry. Its docstring shows the
    intended call site and no such call existed anywhere in the repository.
    """
    tool_registry = _tool_registry(container)
    if tool_registry is None:
        report.skipped["tools"] = "no tool registry reachable"
        return

    mcp_registry = _mcp_registry(container)

    # Both registries are module-level globals that outlive any one app, so a
    # process that builds a second app (every test run does) would register
    # everything twice. Seeding is therefore idempotent by name.
    known_tools = _existing_tool_names(tool_registry)
    known_servers = _existing_server_names(mcp_registry)

    # KlaatCode — reuse its own registration helper.
    if "klaatcode" in known_servers:
        report.notes.append("KlaatCode was already registered; left as-is")
    else:
        try:
            from backend.tools.connectors.klaatcode.registration import (
                register_klaatcode,
            )

            # Without this, register_klaatcode() builds its own throwaway
            # KlaatCodeMCPAdapter and binds *that* to the MCP server record —
            # the adapter GET /klaatcode/status and this seeding step's own
            # container["klaatcode"] actually read never gets bound, so
            # "MCP bound" reads false forever regardless of real state
            # (R-006 Phase 5).
            klaatcode_adapter = container.get("klaatcode") if container.has("klaatcode") else None
            result = register_klaatcode(
                tool_registry=tool_registry, mcp_registry=mcp_registry,
                adapter=klaatcode_adapter,
            )
            report.tools += int(result.get("registered_tools", 0) or 0)
            report.mcp_tools += int(result.get("registered_mcp_tools", 0) or 0)
            if result.get("registered_mcp_tools"):
                report.mcp_servers += 1
        except Exception as exc:
            report.skipped["klaatcode"] = f"{type(exc).__name__}: {exc}"
            logger.warning("KlaatCode registration failed", exc_info=True)

    # Oh My Pi — no registration helper of its own, but its adapter produces the
    # same ToolDefinition objects, so the tools register the same way.
    try:
        from backend.tools.connectors.oh_my_pi.ohmypi_mcp_adapter import OhMyPiMCPAdapter

        adapter = container.get("ohmypi") if container.has("ohmypi") else None
        if adapter is None or not hasattr(adapter, "get_tool_definitions"):
            adapter = OhMyPiMCPAdapter()

        for definition in adapter.get_tool_definitions().values():
            if definition.name in known_tools:
                continue
            try:
                tool_registry.register(definition)
                known_tools.add(definition.name)
                report.tools += 1
            except Exception:
                logger.warning("could not register Oh My Pi tool %s",
                               getattr(definition, "name", "?"), exc_info=True)

        if mcp_registry is not None and "oh my pi" not in known_servers:
            report.mcp_servers += _register_ohmypi_server(adapter, mcp_registry)
    except Exception as exc:
        report.skipped["ohmypi"] = f"{type(exc).__name__}: {exc}"
        logger.warning("Oh My Pi registration failed", exc_info=True)


def _recount(container: Any, report: SeedingReport) -> None:
    """Report what each registry *holds*, not only what this pass added.

    Seeding is idempotent, so a second app in the same process adds nothing and
    would otherwise report zero tools on a registry holding sixteen — which
    reads as a wiring failure rather than as "already done".
    """
    registry = _tool_registry(container)
    if registry is not None:
        try:
            report.tools = registry.count()
        except Exception:
            pass

    mcp = _mcp_registry(container)
    if mcp is not None:
        try:
            report.mcp_servers = mcp.count()
            report.mcp_tools = mcp.count_tools()
        except Exception:
            pass

    try:
        report.agents = len(container.get("agent_supervisor").list_agents())
    except Exception:
        pass


def _existing_tool_names(tool_registry: Any) -> set[str]:
    try:
        return {t.name for t in tool_registry.list_all()}
    except Exception:
        return set()


def _existing_server_names(mcp_registry: Any) -> set[str]:
    if mcp_registry is None:
        return set()
    try:
        return {str(s.name).strip().lower() for s in mcp_registry.list_servers()}
    except Exception:
        return set()


def _register_ohmypi_server(adapter: Any, mcp_registry: Any) -> int:
    """Declare Oh My Pi in the MCP registry. Returns 1 if registered."""
    from backend.tools.mcp.mcp_models import MCPServer, MCPStatus

    status = adapter.get_status() or {}
    installed = bool(status.get("installed"))
    try:
        server = mcp_registry.register_server(MCPServer(
            id="ohmypi",
            name="Oh My Pi",
            version=str(status.get("version") or ""),
            capabilities=[c.name for c in adapter.get_capabilities()],
            status=MCPStatus.CONNECTED if installed else MCPStatus.DISCONNECTED,
        ))
        # Mirrors register_klaatcode()'s adapter.bind_server() — without
        # this, OhMyPiMCPAdapter.get_status() (what GET /ohmypi/status
        # actually returns) never learns a server was registered at all
        # (R-006 Phase 5; OhMyPiMCPAdapter previously had no bind_server()
        # or _server concept whatsoever).
        if hasattr(adapter, "bind_server"):
            adapter.bind_server(server)
        return 1
    except Exception:
        logger.warning("could not register Oh My Pi MCP server", exc_info=True)
        return 0


def _tool_registry(container: Any) -> Any:
    """The ToolRegistry the /tools routes actually serve from."""
    try:
        platform = container.get("tool_platform")
    except Exception:
        platform = None
    for attr in ("registry", "_registry", "tool_registry"):
        candidate = getattr(platform, attr, None)
        if candidate is not None and hasattr(candidate, "register"):
            return candidate
    if platform is not None and hasattr(platform, "register"):
        return platform
    try:
        import backend.tools.routes as tool_routes

        return tool_routes._registry
    except Exception:
        return None


def _mcp_registry(container: Any) -> Any:
    """The MCPRegistry ``GET /api/v1/mcp/servers`` actually serves from.

    It is a module global in ``backend.tools.routes`` — the same module that
    serves ``/tools`` — and unlike the tool registry it is never rebound by
    ``create_tool_routes()``. Registering into a fresh instance instead would
    succeed and still leave the endpoint reporting zero servers.
    """
    try:
        import backend.tools.routes as tool_routes

        return getattr(tool_routes, "_mcp_registry", None)
    except Exception:
        return None


# ── Runtimes and skills (counted, not fabricated) ─────────────────────


def _count_runtimes(report: SeedingReport) -> None:
    try:
        from backend.sds.runtime import get_runtime_registry

        report.runtimes = len(get_runtime_registry().list_available())
    except Exception as exc:
        report.skipped["runtimes"] = f"{type(exc).__name__}: {exc}"


def _count_skills(container: Any, report: SeedingReport) -> None:
    """Count skills. Deliberately does not create any.

    There is no ``SkillDefinition`` instantiated anywhere in this repository, so
    there is nothing real to register. An empty skill registry is the honest
    answer; inventing entries would put fabricated capabilities in front of the
    coordinator that selects them.
    """
    try:
        import backend.skills.routes as skill_routes

        report.skills = skill_routes._registry.count()
    except Exception as exc:
        report.skipped["skills"] = f"{type(exc).__name__}: {exc}"
        return
    if report.skills == 0:
        report.notes.append(
            "skill registry is empty: the repository declares no SkillDefinition, "
            "so there is no real skill to register")


# ── Coordinator ───────────────────────────────────────────────────────


def _seed_coordinator(container: Any, report: SeedingReport,
                      runtimes_only: bool = False) -> None:
    """Introduce the populated registries to the assignment coordinator.

    ``AgentCoordinator`` chooses the agent, runtime, skills and tools for every
    task from four catalogues it exposes registration methods for. Nothing
    populated them, so it reported ``agents_registered: 0`` while assigning work
    on a system with ten agents and sixteen tools.
    """
    try:
        engine = container.get("execution_engine")
        coordinator = getattr(engine, "_coordinator", None)
    except Exception as exc:
        report.skipped["coordinator"] = f"{type(exc).__name__}: {exc}"
        return
    if coordinator is None:
        report.skipped["coordinator"] = "execution engine exposes no coordinator"
        return

    if not runtimes_only:
        try:
            supervisor = container.get("agent_supervisor")
            for agent in supervisor.list_agents():
                coordinator.register_agent(
                    agent_id=agent.name,
                    capabilities=[c.value for c in agent.capabilities],
                    preferred_runtime=getattr(agent, "preferred_runtime", "")
                    or "auto",
                )
                report.coordinator_agents += 1
        except Exception:
            logger.warning("coordinator agent seeding failed", exc_info=True)

    try:
        from backend.sds.runtime import get_runtime_registry

        available = list(get_runtime_registry().list_available())
        for name in available:
            coordinator.register_runtime(runtime_id=name, specs={"source": "sds"})
            report.coordinator_runtimes += 1
    except Exception:
        available = []
        logger.warning("coordinator runtime seeding failed", exc_info=True)

    # The RuntimeOrchestrator selects a runtime per task from its own catalogue,
    # and register_runtime() was only ever called by the Oh My Pi adapter. It
    # reported known_runtimes: 0 during a real mission, so its selection was a
    # no-op on a system with working runtimes (R-002 P4).
    try:
        orchestrator = container.get("runtime_orchestrator")
        for name in available:
            orchestrator.register_runtime(name)
        report.orchestrator_runtimes = len(available)
    except Exception:
        logger.warning("runtime orchestrator seeding failed", exc_info=True)

    if runtimes_only:
        return

    registry = _tool_registry(container)
    if registry is not None:
        try:
            for tool in registry.list_all():
                coordinator.register_tool(
                    tool_id=tool.name,
                    metadata={"category": getattr(tool.category, "value",
                                                  str(tool.category))},
                )
                report.coordinator_tools += 1
        except Exception:
            logger.warning("coordinator tool seeding failed", exc_info=True)
