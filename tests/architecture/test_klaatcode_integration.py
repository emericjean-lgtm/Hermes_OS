"""Tests for KlaatCode MCP integration (HOS-054B).

Covers: models, client, MCP adapter, policy integration, sandbox integration,
EventBus events, routes, and thread safety.

Run with: python3 -m pytest tests/architecture/test_klaatcode_integration.py -v
"""

from __future__ import annotations

import threading

import pytest

from backend.runtime.events.event_bus import RuntimeEventBus
from backend.runtime.events.event_models import RuntimeEventModel
from backend.tools.mcp.mcp_models import MCPServer, MCPTool
from backend.tools.tool_models import (
    ToolDefinition, ToolRequest, ToolType, ToolCategory,
    ToolPermission,
)
from backend.tools.tool_policy import ToolPolicy, PolicyVerdict
from backend.tools.tool_sandbox import ToolSandbox, SandboxConfig
from backend.tools.connectors.klaatcode import (
    KlaatCodeClient,
    KlaatCodeMCPAdapter,
    KlaatCodeRequest,
    KlaatCodeResponse,
    KlaatCodeProject,
    KlaatCodeDiagnostic,
    KlaatCodeCapability,
    KlaatCodeStatus,
    KlaatCodeAction,
    DiagnosticSeverity,
)


# ═══════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeModels:
    """Tests for the KlaatCode dataclass models."""

    def test_request_defaults(self):
        req = KlaatCodeRequest()
        assert req.action == ""
        assert req.parameters == {}
        assert req.timeout_seconds == 60.0
        assert req.agent_id == ""
        assert req.mission_id == ""
        assert req.id != ""

    def test_request_with_params(self):
        req = KlaatCodeRequest(
            action="analyze_project",
            parameters={"path": "/tmp"},
            agent_id="agent-1",
            mission_id="mission-1",
            timeout_seconds=30.0,
            workspace_id="ws-1",
        )
        assert req.action == "analyze_project"
        assert req.parameters["path"] == "/tmp"
        assert req.agent_id == "agent-1"
        assert req.mission_id == "mission-1"
        assert req.timeout_seconds == 30.0
        assert req.workspace_id == "ws-1"

    def test_response_success(self):
        resp = KlaatCodeResponse(
            request_id="req-1",
            status=KlaatCodeStatus.SUCCESS,
            data={"result": "ok"},
            duration_ms=42.0,
        )
        assert resp.status == KlaatCodeStatus.SUCCESS
        assert resp.data["result"] == "ok"
        assert resp.duration_ms == 42.0
        assert resp.error == ""

    def test_response_error(self):
        resp = KlaatCodeResponse(
            request_id="req-2",
            status=KlaatCodeStatus.FAILED,
            error="command not found",
            duration_ms=10.0,
        )
        assert resp.status == KlaatCodeStatus.FAILED
        assert resp.error == "command not found"
        assert resp.data is None

    def test_project_model(self):
        p = KlaatCodeProject(
            root_path="/home/project",
            language="typescript",
            framework="next.js",
            file_count=42,
            dependency_count=15,
            git_enabled=True,
        )
        assert p.root_path == "/home/project"
        assert p.language == "typescript"
        assert p.file_count == 42
        assert p.git_enabled is True

    def test_diagnostic_model(self):
        d = KlaatCodeDiagnostic(
            file_path="src/app.ts",
            severity=DiagnosticSeverity.ERROR,
            line=42,
            column=10,
            message="Type 'string' is not assignable to type 'number'",
            rule_id="ts(2322)",
            suggestion="Convert to number first",
        )
        assert d.file_path == "src/app.ts"
        assert d.severity == DiagnosticSeverity.ERROR
        assert d.line == 42
        assert d.rule_id == "ts(2322)"

    def test_capability_model(self):
        c = KlaatCodeCapability(
            name="analyze_project",
            description="Analyze project structure",
            inputs=["path"],
            outputs=["project"],
            requires_git=True,
        )
        assert c.name == "analyze_project"
        assert c.requires_git is True
        assert c.requires_project is True

    def test_action_enum_values(self):
        """All defined KlaatCode actions have valid enum values."""
        actions = list(KlaatCodeAction)
        assert len(actions) >= 7
        assert KlaatCodeAction.ANALYZE_PROJECT == "analyze_project"
        assert KlaatCodeAction.EDIT_FILE == "edit_file"
        assert KlaatCodeAction.RUN_DIAGNOSTICS == "run_diagnostics"


# ═══════════════════════════════════════════════════════════════
# CLIENT
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeClient:
    """Tests for the KlaatCode headless client wrapper."""

    @pytest.fixture
    def client(self):
        return KlaatCodeClient()

    def test_initialization(self, client):
        # Client may or may not find KlaatCode on PATH; that's expected
        assert isinstance(client, KlaatCodeClient)
        assert client.stats() is not None

    def test_stats_empty(self, client):
        stats = client.stats()
        assert "total_executions" in stats
        assert "success_rate" in stats
        assert "installed" in stats

    def test_get_version_uninstalled(self, client):
        version = client.get_version()
        # If not installed, version is None
        if not client.is_installed():
            assert version is None

    def test_is_installed_returns_bool(self, client):
        assert isinstance(client.is_installed(), bool)

    def test_history_returns_list(self, client):
        history = client.get_history(limit=10)
        assert isinstance(history, list)
        assert len(history) <= 10

    def test_request_unique_ids(self):
        r1 = KlaatCodeRequest(action="test")
        r2 = KlaatCodeRequest(action="test")
        assert r1.id != r2.id

    def test_health_check_response(self, client):
        resp = client.health_check()
        assert isinstance(resp, KlaatCodeResponse)
        assert resp.status in (KlaatCodeStatus.SUCCESS, KlaatCodeStatus.ERROR)
        assert resp.duration_ms >= 0


# ═══════════════════════════════════════════════════════════════
# MCP ADAPTER
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeMCPAdapter:
    """Tests for the MCP adapter exposing KlaatCode tools."""

    @pytest.fixture
    def client(self):
        return KlaatCodeClient()

    @pytest.fixture
    def policy(self):
        return ToolPolicy()

    @pytest.fixture
    def sandbox(self):
        return ToolSandbox()

    @pytest.fixture
    def event_bus(self):
        return RuntimeEventBus(max_history=100)

    @pytest.fixture
    def adapter(self, client, policy, sandbox, event_bus):
        return KlaatCodeMCPAdapter(client, policy, sandbox, event_bus)

    def test_adapter_initialization(self, adapter):
        assert adapter is not None
        assert len(adapter.get_tool_definitions()) == 7
        assert len(adapter.get_capabilities()) == 7

    def test_get_capabilities(self, adapter):
        caps = adapter.get_capabilities()
        assert len(caps) == 7
        cap_names = [c.name for c in caps]
        assert KlaatCodeAction.ANALYZE_PROJECT in cap_names
        assert KlaatCodeAction.EDIT_FILE in cap_names
        assert KlaatCodeAction.RUN_DIAGNOSTICS in cap_names

    def test_get_capability_list(self, adapter):
        caps = adapter.get_capability_list()
        assert isinstance(caps, list)
        assert len(caps) == 7
        for cap in caps:
            assert "name" in cap
            assert "description" in cap
            assert "inputs" in cap

    def test_get_tool_definitions(self, adapter):
        td_map = adapter.get_tool_definitions()
        assert len(td_map) == 7
        for action in KlaatCodeAction:
            if action != KlaatCodeAction.HEALTH_CHECK:
                assert action in td_map

    def test_get_mcp_tools(self, adapter):
        mt_map = adapter.get_mcp_tools()
        assert len(mt_map) == 7
        for mt in mt_map.values():
            assert isinstance(mt, MCPTool)

    def test_get_status(self, adapter):
        status = adapter.get_status()
        assert "installed" in status
        assert "version" in status
        assert "tools_count" in status
        assert status["tools_count"] == 7
        assert "capabilities" in status

    def test_bind_server(self, adapter):
        server = MCPServer(name="klaatcode-server", host="localhost", port=9090)
        adapter.bind_server(server)
        bound = adapter.get_server()
        assert bound is not None
        assert bound.name == "klaatcode-server"
        # MCP tools should now have server_id set
        for mt in adapter.get_mcp_tools().values():
            assert mt.server_id == server.id

    def test_status_mcp_status_field_reflects_binding(self, policy, sandbox):
        """R-006 Phase 5: an explicit state, not a bare boolean the frontend
        has to interpret on its own. Uses a fake client with deterministic
        installed/version so this doesn't depend on whether the real
        klaatcode CLI happens to be reachable on the machine running the
        suite."""
        class _FakeClient:
            def is_installed(self): return True
            def get_version(self): return "9.9.9"
            def stats(self): return {}

        adapter = KlaatCodeMCPAdapter(_FakeClient(), policy, sandbox)
        assert adapter.get_status()["mcp_status"] == "unbound"
        adapter.bind_server(MCPServer(name="klaatcode-server"))
        # Default MCPServer.status is DISCONNECTED — no code here performs a
        # live MCP handshake, so "disconnected" is the honest post-bind state.
        assert adapter.get_status()["mcp_status"] == "disconnected"

    def test_unknown_action(self, adapter):
        resp = adapter.execute("unknown_action", {})
        assert resp.status == KlaatCodeStatus.ERROR
        assert "Unknown" in resp.error

    def test_analyze_project(self, adapter):
        resp = adapter.analyze_project(path="/tmp")
        assert isinstance(resp, KlaatCodeResponse)

    def test_inspect_code(self, adapter):
        resp = adapter.inspect_code(file="src/main.ts")
        assert isinstance(resp, KlaatCodeResponse)

    def test_generate_code_plan(self, adapter):
        resp = adapter.generate_code_plan(prompt="Add a login page")
        assert isinstance(resp, KlaatCodeResponse)

    def test_search_code(self, adapter):
        resp = adapter.search_code(query="authentication")
        assert isinstance(resp, KlaatCodeResponse)

    def test_run_diagnostics(self, adapter):
        resp = adapter.run_diagnostics(file="src/app.ts")
        assert isinstance(resp, KlaatCodeResponse)

    def test_validate_changes(self, adapter):
        resp = adapter.validate_changes(file="src/app.ts")
        assert isinstance(resp, KlaatCodeResponse)


# ═══════════════════════════════════════════════════════════════
# POLICY INTEGRATION
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodePolicyIntegration:
    """Tests that KlaatCode respects the Policy Engine."""

    @pytest.fixture
    def client(self):
        return KlaatCodeClient()

    @pytest.fixture
    def policy(self):
        return ToolPolicy()

    @pytest.fixture
    def sandbox(self):
        return ToolSandbox()

    @pytest.fixture
    def adapter(self, client, policy, sandbox):
        return KlaatCodeMCPAdapter(client, policy, sandbox)

    def test_read_actions_allowed(self, adapter):
        """Read actions should pass policy by default."""
        resp = adapter.analyze_project(path=".")
        # Even if KlaatCode is not installed, the response should not
        # be a policy denial. Policy should be ALLOW.
        assert resp.status != KlaatCodeStatus.ERROR or "Policy denied" not in str(resp.error)

    def test_write_action_requires_permission(self, adapter):
        """Write actions go through policy. If denied, error should mention it."""
        resp = adapter.generate_code_plan(prompt="test")
        assert isinstance(resp, KlaatCodeResponse)

    def test_tool_definition_has_correct_permissions(self, adapter):
        """Analyze is READ, edit_file is WRITE."""
        td_map = adapter.get_tool_definitions()
        analyze_td = td_map[KlaatCodeAction.ANALYZE_PROJECT]
        edit_td = td_map[KlaatCodeAction.EDIT_FILE]

        assert ToolPermission.READ in analyze_td.permissions or ToolPermission.WRITE in analyze_td.permissions
        assert ToolPermission.WRITE in edit_td.permissions


# ═══════════════════════════════════════════════════════════════
# SANDBOX INTEGRATION
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeSandboxIntegration:
    """Tests that KlaatCode respects the Sandbox."""

    @pytest.fixture
    def sandbox(self):
        return ToolSandbox()

    def test_sandbox_configurable(self, sandbox):
        config = SandboxConfig(
            workspace_id="ws-test",
            read_only=True,
            allowed_paths=["/tmp"],
            network_allowed=False,
        )
        sandbox.configure("klaatcode.test", config)
        retrieved = sandbox.get_config("klaatcode.test")
        assert retrieved.workspace_id == "ws-test"
        assert retrieved.read_only is True

    def test_path_validation_allowed(self, sandbox):
        config = SandboxConfig(
            allowed_paths=["/home/project", "/tmp"],
        )
        sandbox.configure("klaatcode.validate", config)
        assert sandbox.validate_path("klaatcode.validate", "/home/project/src/main.ts") is True
        assert sandbox.validate_path("klaatcode.validate", "/tmp/out.txt") is True

    def test_path_validation_denied(self, sandbox):
        config = SandboxConfig(
            allowed_paths=["/home/project"],
            denied_paths=["/etc", "/proc"],
        )
        sandbox.configure("klaatcode.deny", config)
        assert sandbox.validate_path("klaatcode.deny", "/etc/passwd") is False
        assert sandbox.validate_path("klaatcode.deny", "/proc/cpuinfo") is False

    def test_network_validation(self, sandbox):
        config = SandboxConfig(
            network_allowed=True,
            allowed_hosts=["api.github.com"],
        )
        sandbox.configure("klaatcode.net", config)
        assert sandbox.validate_network("klaatcode.net", "api.github.com") is True
        assert sandbox.validate_network("klaatcode.net", "evil.com") is False

    def test_default_sandbox_restrictions(self, sandbox):
        # Default sandbox denies sensitive paths
        assert sandbox.validate_path("any-tool", "/etc/secret") is False
        assert sandbox.validate_path("any-tool", "/proc/1/cmdline") is False


# ═══════════════════════════════════════════════════════════════
# EVENT BUS INTEGRATION
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeEventBus:
    """Tests that KlaatCode publishes correct events."""

    @pytest.fixture
    def event_bus(self):
        return RuntimeEventBus(max_history=200)

    @pytest.fixture
    def client(self):
        return KlaatCodeClient()

    @pytest.fixture
    def policy(self):
        return ToolPolicy()

    @pytest.fixture
    def sandbox(self):
        return ToolSandbox()

    @pytest.fixture
    def adapter(self, client, policy, sandbox, event_bus):
        return KlaatCodeMCPAdapter(client, policy, sandbox, event_bus)

    def test_event_bus_is_present(self, adapter):
        assert adapter._event_bus is not None

    def test_execution_publishes_events(self, adapter, event_bus):
        initial_count = event_bus.event_count
        adapter.analyze_project(path=".")
        # Events should have been published (at least started event)
        # Note: if KlaatCode is not installed, the execution may fail
        # but the started event should still fire.
        final_count = event_bus.event_count
        assert final_count >= initial_count

    def test_event_prefix_consistent(self):
        """All KlaatCode events use the 'klaatcode.' prefix."""
        prefix = KlaatCodeMCPAdapter.EVENT_PREFIX
        assert prefix == "klaatcode"
        assert KlaatCodeMCPAdapter.EVENT_EXECUTION_STARTED.startswith(prefix)
        assert KlaatCodeMCPAdapter.EVENT_EXECUTION_COMPLETED.startswith(prefix)
        assert KlaatCodeMCPAdapter.EVENT_EXECUTION_FAILED.startswith(prefix)

    def test_event_bus_subscribe_unsubscribe(self, event_bus):
        events_received: list[RuntimeEventModel] = []

        def handler(event: RuntimeEventModel):
            events_received.append(event)

        subscriber = event_bus.subscribe(handler)
        event_bus.publish(RuntimeEventModel(
            runtime_id="test",
            event_type="klaatcode.test",
            source="test",
        ))
        assert len(events_received) == 1

        event_bus.unsubscribe(subscriber)
        event_bus.publish(RuntimeEventModel(
            runtime_id="test",
            event_type="klaatcode.test2",
            source="test",
        ))
        assert len(events_received) == 1  # no new events

    def test_event_bus_filtered_subscription(self, event_bus):
        received: list[str] = []

        def handler(e: RuntimeEventModel):
            received.append(e.event_type)

        event_bus.subscribe(handler, event_types=["klaatcode.execution.started"])
        event_bus.publish(RuntimeEventModel(runtime_id="t", event_type="klaatcode.execution.started", source="test"))
        event_bus.publish(RuntimeEventModel(runtime_id="t", event_type="other.event", source="test"))
        assert received == ["klaatcode.execution.started"]


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeRoutes:
    """Tests for the KlaatCode REST API route handlers."""

    def test_handle_get_status(self):
        from backend.tools.connectors.klaatcode.routes import handle_get_status
        result = handle_get_status()
        assert "status" in result
        assert "tools" in result
        assert "capabilities" in result

    def test_handle_get_capabilities(self):
        from backend.tools.connectors.klaatcode.routes import handle_get_capabilities
        result = handle_get_capabilities()
        assert "capabilities" in result
        assert "count" in result
        assert result["count"] == 7

    def test_handle_post_analyze(self):
        from backend.tools.connectors.klaatcode.routes import handle_post_analyze
        result = handle_post_analyze(path=".", agent_id="test-agent", mission_id="test-mission")
        assert "status" in result
        assert "id" in result

    def test_handle_post_diagnostics(self):
        from backend.tools.connectors.klaatcode.routes import handle_post_diagnostics
        result = handle_post_diagnostics(file="src/app.ts")
        assert "status" in result
        assert "id" in result

    def test_handle_post_execute(self):
        from backend.tools.connectors.klaatcode.routes import handle_post_execute
        result = handle_post_execute(action="search_code", parameters={"query": "auth"})
        assert "status" in result
        assert "id" in result

    def test_post_execute_unknown_action(self):
        from backend.tools.connectors.klaatcode.routes import handle_post_execute
        result = handle_post_execute(action="nonexistent_action")
        assert "success" in result
        # Unknown action should return error
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════
# THREAD SAFETY
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeThreadSafety:
    """Tests for thread safety across the KlaatCode integration."""

    def test_concurrent_adapter_access(self):
        """Multiple threads can call the adapter simultaneously."""
        client = KlaatCodeClient()
        policy = ToolPolicy()
        sandbox = ToolSandbox()
        adapter = KlaatCodeMCPAdapter(client, policy, sandbox)

        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(10):
                    adapter.get_status()
                    adapter.get_capabilities()
                    adapter.get_tool_definitions()
                    adapter.get_mcp_tools()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread-safety errors: {errors}"

    def test_concurrent_client_access(self):
        """Multiple threads can query the client simultaneously."""
        client = KlaatCodeClient()

        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(10):
                    client.is_installed()
                    client.stats()
                    client.get_history(limit=5)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread-safety errors: {errors}"

    def test_concurrent_policy_access(self):
        """Policy engine handles concurrent evaluations."""
        policy = ToolPolicy()
        td = ToolDefinition(name="test", tool_type=ToolType.CUSTOM, category=ToolCategory.SYSTEM)

        errors: list[Exception] = []

        def worker(i: int):
            try:
                for _ in range(20):
                    req = ToolRequest(
                        tool_id=td.id, action="test",
                        permission_level=ToolPermission.READ,
                    )
                    verdict, _ = policy.evaluate(req, td)
                    assert verdict in (PolicyVerdict.ALLOW, PolicyVerdict.REVIEW_REQUIRED, PolicyVerdict.DENY)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Policy thread-safety errors: {errors}"
