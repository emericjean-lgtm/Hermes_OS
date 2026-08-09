"""Tests for Oh My Pi Agent Integration (HOS-055B).

Covers: models, client, MCP adapter, tools registry, policy,
sandbox, agent lifecycle, capability matching, events, routes, thread safety.

Minimum 40 tests.

Run with: python3 -m pytest tests/architecture/test_ohmypi_integration.py -v
"""

from __future__ import annotations

import threading
import pytest

from backend.tools.connectors.oh_my_pi import (
    OhMyPiClient, OhMyPiMCPAdapter, OhMyPiAction, OhMyPiStatus,
    OhMyPiRequest, OhMyPiResponse, OhMyPiCapability,
)
from backend.tools.tool_policy import ToolPolicy
from backend.tools.tool_sandbox import ToolSandbox, SandboxConfig
from backend.tools.tool_models import ToolPermission
from backend.agents.agent_models import AgentCapability, AgentStatus, TaskOutcome
from backend.agents.specialized.ohmypi import (
    OhMyPiAgent, OHMYPI_EVENTS,
    OhMyPiTaskType, create_ohmypi_agent,
)
from backend.workspace.workspace_manager import WorkspaceManager


# ═══════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiModels:
    def test_request_defaults(self):
        req = OhMyPiRequest()
        assert req.action == ""; assert req.timeout_seconds == 120.0

    def test_response_success(self):
        resp = OhMyPiResponse(request_id="r1", status=OhMyPiStatus.SUCCESS, data={"ok": True}, duration_ms=42.0)
        assert resp.status == OhMyPiStatus.SUCCESS; assert resp.data["ok"]

    def test_response_error(self):
        resp = OhMyPiResponse(request_id="r2", status=OhMyPiStatus.FAILED, error="not found")
        assert resp.error == "not found"

    def test_action_enum_values(self):
        assert OhMyPiAction.LSP_EDIT == "lsp_edit"
        assert OhMyPiAction.DEBUG_START == "debug_start"
        assert OhMyPiAction.EXECUTE_PYTHON == "execute_python"
        assert len(list(OhMyPiAction)) >= 9

    def test_capability_model(self):
        cap = OhMyPiCapability(name="lsp_edit", description="LSP edit",
                                inputs=["file", "edit"], requires_lsp=True)
        assert cap.requires_lsp; assert cap.requires_workspace


# ═══════════════════════════════════════════════════════════════
# CLIENT
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiClient:
    @pytest.fixture
    def client(self): return OhMyPiClient()

    def test_initialization(self, client):
        assert isinstance(client, OhMyPiClient); assert client.stats() is not None

    def test_stats(self, client):
        s = client.stats()
        assert "total_executions" in s; assert "installed" in s

    def test_is_installed_returns_bool(self, client):
        assert isinstance(client.is_installed(), bool)

    def test_health_check_response(self, client):
        resp = client.health_check()
        assert isinstance(resp, OhMyPiResponse)

    def test_history(self, client):
        assert isinstance(client.get_history(), list)


# ═══════════════════════════════════════════════════════════════
# MCP ADAPTER
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiMCPAdapter:
    @pytest.fixture
    def adapter(self):
        return OhMyPiMCPAdapter(OhMyPiClient(), ToolPolicy(), ToolSandbox())

    def test_tool_definitions_count(self, adapter):
        assert len(adapter.get_tool_definitions()) == 9

    def test_capabilities_count(self, adapter):
        assert len(adapter.get_capabilities()) == 9

    def test_get_status(self, adapter):
        s = adapter.get_status()
        assert "tools_count" in s; assert s["tools_count"] == 9

    def test_execute_unknown_action(self, adapter):
        resp = adapter.execute("nonexistent", {})
        assert resp.status == OhMyPiStatus.ERROR

    def test_status_reports_unbound_before_bind_server(self, adapter):
        """R-006 Phase 5: before this adapter had bind_server() at all,
        "server_bound" didn't exist in the response, so the frontend's
        Boolean(status.server_bound) was always false by construction."""
        s = adapter.get_status()
        assert s["server_bound"] is False
        assert adapter.get_server() is None

    def test_bind_server_makes_status_report_bound(self):
        """Uses a fake client with a deterministic version so this doesn't
        depend on the real omp package actually resolving on the machine
        running the suite (it's observed to NOT resolve via npx in this
        environment — real npm package, no runnable executable, R-006
        Phase 6)."""
        from backend.tools.mcp.mcp_models import MCPServer, MCPStatus

        class _FakeClient:
            def is_installed(self): return True
            def get_version(self): return "9.9.9"
            def stats(self): return {}

        adapter = OhMyPiMCPAdapter(_FakeClient(), ToolPolicy(), ToolSandbox())
        server = MCPServer(id="ohmypi", status=MCPStatus.CONNECTED)
        adapter.bind_server(server)
        assert adapter.get_server() is server
        s = adapter.get_status()
        assert s["server_bound"] is True
        assert s["mcp_status"] == "connected"

    def test_lsp_open_file(self, adapter):
        resp = adapter.execute(OhMyPiAction.LSP_OPEN_FILE, {"file": "src/test.py"})
        assert isinstance(resp, OhMyPiResponse)

    def test_debug_start(self, adapter):
        resp = adapter.execute(OhMyPiAction.DEBUG_START, {"program": "app.py"})
        assert isinstance(resp, OhMyPiResponse)

    def test_execute_python(self, adapter):
        resp = adapter.execute(OhMyPiAction.EXECUTE_PYTHON, {"code": "print('hi')"})
        assert isinstance(resp, OhMyPiResponse)

    def test_git_operation(self, adapter):
        resp = adapter.execute(OhMyPiAction.GIT_OPERATION, {"op": "status"})
        assert isinstance(resp, OhMyPiResponse)


# ═══════════════════════════════════════════════════════════════
# POLICY & SANDBOX INTEGRATION
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiPolicyIntegration:
    def test_write_action_goes_through_policy(self):
        policy = ToolPolicy()
        adapter = OhMyPiMCPAdapter(OhMyPiClient(), policy, ToolSandbox())
        td_map = adapter.get_tool_definitions()
        edit_td = td_map[OhMyPiAction.LSP_EDIT]
        assert ToolPermission.WRITE in edit_td.permissions

    def test_read_action_has_read_permission(self):
        adapter = OhMyPiMCPAdapter(OhMyPiClient(), ToolPolicy(), ToolSandbox())
        td_map = adapter.get_tool_definitions()
        open_td = td_map[OhMyPiAction.LSP_OPEN_FILE]
        assert ToolPermission.READ in open_td.permissions


class TestOhMyPiSandboxIntegration:
    def test_sandbox_configurable(self):
        sandbox = ToolSandbox()
        config = SandboxConfig(workspace_id="ws-omp", read_only=False)
        sandbox.configure("ohmypi.test", config)
        assert sandbox.get_config("ohmypi.test").workspace_id == "ws-omp"

    def test_path_validation(self):
        sandbox = ToolSandbox()
        config = SandboxConfig(allowed_paths=["/home/project"])
        sandbox.configure("ohmypi.paths", config)
        assert sandbox.validate_path("ohmypi.paths", "/home/project/src/main.py")
        assert not sandbox.validate_path("ohmypi.paths", "/etc/passwd")


# ═══════════════════════════════════════════════════════════════
# AGENT LIFECYCLE
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiAgentLifecycle:
    @pytest.fixture
    def agent(self): return OhMyPiAgent()

    def test_creation(self, agent):
        assert agent.agent_id.startswith("ohmypi_"); assert agent.status == AgentStatus.CREATED

    def test_factory(self):
        agent = create_ohmypi_agent()
        assert agent.is_available; assert agent.status == AgentStatus.READY

    def test_start(self, agent):
        assert agent.start(); assert agent.status == AgentStatus.READY

    def test_pause_resume(self, agent):
        agent.start()
        assert agent.transition(AgentStatus.PAUSED, "paused")
        assert agent.transition(AgentStatus.READY, "resumed")

    def test_mark_busy_ready(self, agent):
        agent.start()
        assert agent.mark_busy("t1"); assert agent.status == AgentStatus.BUSY
        assert agent.mark_ready(); assert agent.status == AgentStatus.READY

    def test_stop(self, agent):
        agent.start(); assert agent.stop()
        assert agent.status == AgentStatus.STOPPED

    def test_events_on_ready(self):
        events = []
        agent = OhMyPiAgent(on_event=lambda et, p, **kw: events.append(et))
        agent.start()
        assert OHMYPI_EVENTS["agent_ready"] in events

    def test_invalid_transition(self):
        agent = OhMyPiAgent()
        assert not agent.transition(AgentStatus.READY, "skip")


# ═══════════════════════════════════════════════════════════════
# CAPABILITY MATCHING
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiCapabilityMatching:
    def test_capabilities_include_code_generation(self):
        agent = create_ohmypi_agent()
        assert AgentCapability.CODE_GENERATION in agent.agent_capabilities

    def test_capabilities_include_analysis(self):
        agent = create_ohmypi_agent()
        assert AgentCapability.ANALYSIS in agent.agent_capabilities

    def test_to_agent_dataclass(self):
        agent = create_ohmypi_agent()
        ad = agent.to_agent_dataclass()
        assert ad.name == "OhMyPiAgent"; assert len(ad.capabilities) > 0

    def test_prefers_code_editing(self):
        agent = create_ohmypi_agent()
        assert "implementation" in agent.profile.preferred_task_types

    def test_profile_skill_levels(self):
        agent = create_ohmypi_agent()
        assert agent.profile.skill_levels["code_editing"] > 0.9
        assert agent.profile.skill_levels["debugging"] > 0.9


# ═══════════════════════════════════════════════════════════════
# TASK EXECUTION
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiTaskExecution:
    @pytest.fixture
    def agent(self): return create_ohmypi_agent()

    def test_execute_lsp_edit(self, agent):
        result = agent.execute_task(OhMyPiTaskType.CODE_EDITING,
                                     {"file": "src/app.py", "edit": "rename func"},
                                     mission_id="m1", node_id="n1")
        assert result.outcome == TaskOutcome.SUCCESS

    def test_execute_debug(self, agent):
        result = agent.execute_task(OhMyPiTaskType.DEBUGGING,
                                     {"program": "app.py"}, mission_id="m1", node_id="n2")
        assert result.outcome == TaskOutcome.SUCCESS

    def test_execute_python(self, agent):
        result = agent.execute_task(OhMyPiTaskType.CODE_EXECUTION,
                                     {"code": "print(42)", "language": "python"},
                                     mission_id="m1", node_id="n3")
        assert result.outcome == TaskOutcome.SUCCESS

    def test_execute_ast(self, agent):
        result = agent.execute_task(OhMyPiTaskType.AST_MANIPULATION,
                                     {"transform": "rename", "file": "src/app.ts"},
                                     mission_id="m1", node_id="n4")
        assert result.outcome == TaskOutcome.SUCCESS

    def test_metrics_after_tasks(self, agent):
        agent.execute_task(OhMyPiTaskType.CODE_EDITING, {"file": "a.py", "edit": "x"})
        agent.execute_task(OhMyPiTaskType.DEBUGGING, {"program": "b.py"})
        m = agent.get_metrics()
        assert m.total_tasks == 2

    def test_status_dict(self, agent):
        agent.execute_task(OhMyPiTaskType.CODE_SEARCH, {"query": "auth"})
        s = agent.get_status_dict()
        assert s["total_tasks"] >= 1; assert "capabilities" in s


# ═══════════════════════════════════════════════════════════════
# WORKSPACE PROTECTION
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiWorkspaceProtection:
    @pytest.fixture
    def ws_mgr(self): return WorkspaceManager(base_path="/tmp/test-omp-ws")

    def test_edit_requires_workspace(self, ws_mgr):
        agent = create_ohmypi_agent(workspace_manager=ws_mgr)
        result = agent.execute_task(OhMyPiTaskType.CODE_EDITING,
                                     {"file": "x.py", "edit": "y"},
                                     mission_id="m-ws", node_id="n-ws")
        assert "workspace" in result.error_message.lower() or "required" in result.error_message.lower()

    def test_edit_with_valid_workspace(self, ws_mgr):
        ws = ws_mgr.create(mission_id="m-omp", agent_id="ohmy-pi")
        agent = create_ohmypi_agent(workspace_manager=ws_mgr)
        result = agent.execute_task(OhMyPiTaskType.CODE_EDITING,
                                     {"file": "x.py", "edit": "y", "workspace_id": ws.workspace_id},
                                     mission_id="m-omp", node_id="n-omp")
        assert result.outcome == TaskOutcome.SUCCESS

    def test_search_no_workspace_required(self, ws_mgr):
        agent = create_ohmypi_agent(workspace_manager=ws_mgr)
        result = agent.execute_task(OhMyPiTaskType.CODE_SEARCH,
                                     {"query": "main"}, mission_id="m-no", node_id="n-no")
        assert result.outcome == TaskOutcome.SUCCESS


# ═══════════════════════════════════════════════════════════════
# EVENTS
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiEvents:
    def test_edit_events_emitted(self):
        events = []
        agent = OhMyPiAgent(on_event=lambda et, p, **kw: events.append(et))
        agent.start(); events.clear()
        agent.execute_task(OhMyPiTaskType.CODE_EDITING, {"file": "x.py", "edit": "y"})
        assert OHMYPI_EVENTS["edit_started"] in events
        assert OHMYPI_EVENTS["edit_completed"] in events

    def test_debug_event_emitted(self):
        events = []
        agent = OhMyPiAgent(on_event=lambda et, p, **kw: events.append(et))
        agent.start(); events.clear()
        agent.execute_task(OhMyPiTaskType.DEBUGGING, {"program": "app.py"})
        assert OHMYPI_EVENTS["debug_started"] in events

    def test_execution_event_emitted(self):
        events = []
        agent = OhMyPiAgent(on_event=lambda et, p, **kw: events.append(et))
        agent.start(); events.clear()
        agent.execute_task(OhMyPiTaskType.CODE_EXECUTION, {"code": "1+1"})
        assert OHMYPI_EVENTS["execution_completed"] in events

    def test_all_events_have_prefix(self):
        for key, evt in OHMYPI_EVENTS.items():
            assert evt.startswith("ohmypi.")


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiRoutes:
    def test_handle_get_status(self):
        from backend.tools.connectors.oh_my_pi.routes import handle_get_status
        result = handle_get_status()
        assert "status" in result; assert result["tools"] == 9

    def test_handle_get_capabilities(self):
        from backend.tools.connectors.oh_my_pi.routes import handle_get_capabilities
        result = handle_get_capabilities()
        assert result["count"] == 9

    def test_handle_post_execute(self):
        from backend.tools.connectors.oh_my_pi.routes import handle_post_execute
        result = handle_post_execute(action="code_search", parameters={"query": "auth"})
        assert "success" in result


# ═══════════════════════════════════════════════════════════════
# THREAD SAFETY
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiThreadSafety:
    def test_concurrent_agent_access(self):
        agent = create_ohmypi_agent()
        errors = []

        def worker():
            try:
                for _ in range(20):
                    agent.get_status_dict(); agent.get_metrics()
                    agent.agent_capabilities; agent.is_available
            except Exception as e: errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)
        assert len(errors) == 0

    def test_concurrent_client_access(self):
        client = OhMyPiClient()
        errors = []

        def worker():
            try:
                for _ in range(20):
                    client.is_installed(); client.stats(); client.get_history(5)
            except Exception as e: errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)
        assert len(errors) == 0

    def test_concurrent_task_execution(self):
        agent = create_ohmypi_agent()
        errors = []

        def worker(i):
            try:
                for _ in range(5):
                    agent.execute_task(OhMyPiTaskType.CODE_SEARCH,
                                        {"query": f"q{i}"}, mission_id="m", node_id=f"n{i}")
            except Exception as e: errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=15)
        assert len(errors) == 0
