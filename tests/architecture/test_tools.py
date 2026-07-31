"""Tests for HOS-049 — MCP & External Tools Platform."""

from __future__ import annotations

import threading
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.tools.tool_models import (
    ExecutionStatus, HealthStatus, ToolCategory, ToolDefinition,
    ToolPermission, ToolRequest, ToolStatus, ToolType,
)
from backend.tools.tool_registry import ToolRegistry
from backend.tools.tool_policy import PolicyVerdict, ToolPolicy
from backend.tools.tool_sandbox import SandboxConfig, ToolSandbox
from backend.tools.tool_executor import ToolExecutor
from backend.tools.tool_router import ToolRouter
from backend.tools.tool_health import ToolHealth
from backend.tools.tool_memory import ToolMemory
from backend.tools.mcp import (
    MCPClient, MCPRegistry, MCPServer, MCPStatus, MCPTool,
)
from backend.tools.connectors.github import GitHubConnector
from backend.tools.connectors.gitlab import GitLabConnector
from backend.tools.connectors.docker import DockerConnector
from backend.tools.connectors.database import DatabaseConnector
from backend.tools.connectors.filesystem import FilesystemConnector
from backend.tools.connectors.rest_api import RestAPIConnector
from backend.tools.connectors.browser import BrowserConnector
from backend.tools.routes import (
    handle_get_tools, handle_get_tool, handle_post_register,
    handle_post_execute, handle_post_select,
    handle_get_health, handle_get_metrics,
    handle_get_mcp_servers, handle_post_mcp_connect, handle_post_mcp_disconnect,
)


# ── Helpers ──────────────────────────────────────────────────

def _make_tool(
    tool_id: str = "", name: str = "test-tool",
    tool_type: ToolType = ToolType.CUSTOM,
    category: ToolCategory = ToolCategory.SYSTEM,
    tags: list[str] | None = None,
    status: ToolStatus = ToolStatus.AVAILABLE,
    permissions: list[ToolPermission] | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        id=tool_id, name=name, tool_type=tool_type,
        category=category, tags=tags or [], status=status,
        permissions=permissions or [ToolPermission.READ],
    )


# ── TestRegistry ─────────────────────────────────────────────

class TestToolRegistry:

    def test_register_get(self):
        reg = ToolRegistry()
        t = _make_tool("t1", "test")
        reg.register(t)
        assert reg.get("t1") is t
        assert reg.count() == 1

    def test_list_by_type(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1", "gh", ToolType.GITHUB, ToolCategory.VCS))
        reg.register(_make_tool("t2", "db", ToolType.DATABASE, ToolCategory.DATA))
        assert len(reg.list_by_type(ToolType.GITHUB)) == 1
        assert len(reg.list_by_type(ToolType.DATABASE)) == 1

    def test_list_by_status(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1", "a", status=ToolStatus.AVAILABLE))
        reg.register(_make_tool("t2", "b", status=ToolStatus.DISABLED))
        assert len(reg.list_available()) == 1
        assert len(reg.list_by_status(ToolStatus.DISABLED)) == 1

    def test_update_status(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1", "test"))
        assert reg.update_status("t1", ToolStatus.DEGRADED) is True
        assert reg.get("t1").status == ToolStatus.DEGRADED
        assert reg.update_status("nonexistent", ToolStatus.AVAILABLE) is False

    def test_delete(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1", "test"))
        assert reg.delete("t1") is True
        assert reg.get("t1") is None
        assert reg.delete("t1") is False

    def test_stats(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1", "a", ToolType.GITHUB, ToolCategory.VCS))
        reg.register(_make_tool("t2", "b", ToolType.DOCKER, ToolCategory.CONTAINER))
        s = reg.stats()
        assert s["total"] == 2


# ── TestPolicy ───────────────────────────────────────────────

class TestToolPolicy:

    def test_allow_default(self):
        policy = ToolPolicy()
        tool = _make_tool("t1", "test")
        req = ToolRequest(tool_id="t1", action="read", permission_level=ToolPermission.READ)
        verdict, reason = policy.evaluate(req, tool)
        assert verdict == PolicyVerdict.ALLOW

    def test_deny_admin(self):
        policy = ToolPolicy()
        tool = _make_tool("t1", "admin-tool")
        req = ToolRequest(tool_id="t1", action="dangerous", permission_level=ToolPermission.ADMIN)
        verdict, _ = policy.evaluate(req, tool)
        assert verdict == PolicyVerdict.REVIEW_REQUIRED

    def test_deny_timeout(self):
        policy = ToolPolicy()
        tool = _make_tool("t1", "test")
        req = ToolRequest(tool_id="t1", action="long", timeout_seconds=999.0)
        verdict, _ = policy.evaluate(req, tool)
        assert verdict == PolicyVerdict.DENY

    def test_deny_disabled(self):
        policy = ToolPolicy()
        tool = _make_tool("t1", "disabled-tool", status=ToolStatus.DISABLED)
        req = ToolRequest(tool_id="t1", action="test")
        verdict, _ = policy.evaluate(req, tool)
        assert verdict == PolicyVerdict.DENY

    def test_add_rule(self):
        policy = ToolPolicy()
        policy.add_rule("t1", "deny all writes")
        tool = _make_tool("t1", "test")
        req = ToolRequest(tool_id="t1", action="write")
        verdict, reason = policy.evaluate(req, tool)
        assert verdict == PolicyVerdict.DENY
        assert "deny" in reason.lower()


# ── TestSandbox ──────────────────────────────────────────────

class TestToolSandbox:

    def test_validate_path_allowed(self):
        sandbox = ToolSandbox()
        sandbox.configure("t1", SandboxConfig(allowed_paths=["/home/project"]))
        assert sandbox.validate_path("t1", "/home/project/src/main.py") is True

    def test_validate_path_denied(self):
        sandbox = ToolSandbox()
        sandbox.configure("t1", SandboxConfig())
        assert sandbox.validate_path("t1", "/etc/passwd") is False

    def test_validate_network(self):
        sandbox = ToolSandbox()
        sandbox.configure("t1", SandboxConfig(network_allowed=True, allowed_hosts=["api.github.com"]))
        assert sandbox.validate_network("t1", "api.github.com") is True
        assert sandbox.validate_network("t1", "evil.com") is False

    def test_default_allows(self):
        sandbox = ToolSandbox()
        assert sandbox.validate_path("t-unknown", "/tmp/test") is True

    def test_destroy(self):
        sandbox = ToolSandbox()
        sandbox.configure("t1", SandboxConfig())
        assert sandbox.destroy("t1") is True
        assert sandbox.destroy("t1") is False


# ── TestExecutor ─────────────────────────────────────────────

class TestToolExecutor:

    def test_execute_success(self):
        policy = ToolPolicy()
        sandbox = ToolSandbox()
        executor = ToolExecutor(policy, sandbox)
        executor.register_executor("t1", lambda req: {"ok": True})
        tool = _make_tool("t1", "test")
        req = ToolRequest(tool_id="t1", action="test", permission_level=ToolPermission.READ)
        result = executor.execute(req, tool)
        assert result.status == ExecutionStatus.COMPLETED
        assert result.data == {"ok": True}

    def test_execute_denied(self):
        policy = ToolPolicy()
        sandbox = ToolSandbox()
        executor = ToolExecutor(policy, sandbox)
        tool = _make_tool("t1", "disabled-tool", status=ToolStatus.DISABLED)
        req = ToolRequest(tool_id="t1", action="test", permission_level=ToolPermission.READ)
        result = executor.execute(req, tool)
        assert result.status == ExecutionStatus.DENIED

    def test_execute_no_executor(self):
        policy = ToolPolicy()
        sandbox = ToolSandbox()
        executor = ToolExecutor(policy, sandbox)
        tool = _make_tool("t1", "test")
        req = ToolRequest(tool_id="t1", action="test")
        result = executor.execute(req, tool)
        assert result.status == ExecutionStatus.FAILED

    def test_history(self):
        policy = ToolPolicy()
        sandbox = ToolSandbox()
        executor = ToolExecutor(policy, sandbox)
        executor.register_executor("t1", lambda req: {"ok": True})
        tool = _make_tool("t1", "test")
        req = ToolRequest(tool_id="t1", action="test")
        executor.execute(req, tool)
        history = executor.get_history()
        assert len(history) >= 1

    def test_stats(self):
        policy = ToolPolicy()
        sandbox = ToolSandbox()
        executor = ToolExecutor(policy, sandbox)
        executor.register_executor("t1", lambda req: {"ok": True})
        stats = executor.stats()
        assert "total_executions" in stats
        assert "executors_registered" in stats


# ── TestRouter ───────────────────────────────────────────────

class TestToolRouter:

    def test_select(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1", "github-tool", ToolType.GITHUB, ToolCategory.VCS))
        reg.register(_make_tool("t2", "docker-tool", ToolType.DOCKER, ToolCategory.CONTAINER))
        router = ToolRouter(reg)
        tool, _, confidence = router.select(action="fix github issue")
        assert tool is not None
        assert tool.tool_type == ToolType.GITHUB

    def test_select_no_match(self):
        reg = ToolRegistry()
        router = ToolRouter(reg)
        tool, reason, confidence = router.select(action="some unknown action")
        assert tool is None
        assert confidence == 0.0

    def test_select_type_preference(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1", "gh", ToolType.GITHUB, ToolCategory.VCS))
        reg.register(_make_tool("t2", "gl", ToolType.GITLAB, ToolCategory.VCS))
        router = ToolRouter(reg)
        tool, _, _ = router.select(action="git", preferred_type=ToolType.GITLAB)
        assert tool is not None
        assert tool.tool_type == ToolType.GITLAB


# ── TestHealth ───────────────────────────────────────────────

class TestToolHealth:

    def test_register_check(self):
        health = ToolHealth()
        tool = _make_tool("t1", "test")
        health.register(tool)
        status = health.check("t1")
        assert status == HealthStatus.HEALTHY

    def test_check_all(self):
        health = ToolHealth()
        health.register(_make_tool("t1", "a"))
        health.register(_make_tool("t2", "b"))
        results = health.check_all()
        assert len(results) == 2

    def test_record_execution(self):
        health = ToolHealth()
        tool = _make_tool("t1", "test")
        health.register(tool)
        health.record_execution("t1", success=True, latency_ms=100.0)
        inst = health.get("t1")
        assert inst.total_executions == 1
        assert inst.error_count == 0
        health.record_execution("t1", success=False)
        assert inst.error_count == 1

    def test_stats(self):
        health = ToolHealth()
        health.register(_make_tool("t1", "a"))
        health.register(_make_tool("t2", "b"))
        s = health.stats()
        assert s["total"] == 2


# ── TestMemory ───────────────────────────────────────────────

class TestToolMemory:

    def test_record_query(self):
        mem = ToolMemory()
        tool = _make_tool("t1", "test")
        from backend.tools.tool_models import ToolResult
        req = ToolRequest(tool_id="t1", action="test", agent_id="a1", mission_id="m1")
        result = ToolResult(tool_id="t1", status=ExecutionStatus.COMPLETED, duration_ms=50.0)
        mem.record(req, result, tool)
        entries = mem.query(tool_id="t1")
        assert len(entries) == 1
        assert entries[0]["success"] is True

    def test_get_tool_stats(self):
        mem = ToolMemory()
        tool = _make_tool("t1", "test")
        from backend.tools.tool_models import ToolResult
        for i in range(3):
            req = ToolRequest(tool_id="t1", action=f"test-{i}")
            result = ToolResult(tool_id="t1", status=ExecutionStatus.COMPLETED, duration_ms=10.0)
            mem.record(req, result, tool)
        stats = mem.get_tool_stats("t1")
        assert stats["total"] == 3
        assert stats["success_rate"] == 1.0

    def test_query_by_agent(self):
        mem = ToolMemory()
        tool = _make_tool("t1", "test")
        from backend.tools.tool_models import ToolResult
        req = ToolRequest(tool_id="t1", action="test", agent_id="coder-agent")
        result = ToolResult(tool_id="t1", status=ExecutionStatus.COMPLETED)
        mem.record(req, result, tool)
        stats = mem.get_agent_stats("coder-agent")
        assert stats["total"] == 1

    def test_stats(self):
        mem = ToolMemory()
        s = mem.stats()
        assert s["total"] == 0


# ── TestMCP ──────────────────────────────────────────────────

# ── R-001: MCP now performs real transport ────────────────────────────
#
# connect()/call() used to set CONNECTED and return a canned {"status": "ok"}
# without emitting a packet, so these tests passed against a fabrication. They
# now assert the real contract, driven through MCPClient's injectable opener so
# they stay hermetic (no socket, no live server).


class _FakeHTTPResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def _answering_opener(result: dict | None = None):
    """An opener that answers every JSON-RPC request successfully."""
    import json as _json

    def _open(_request, timeout=None):  # noqa: ANN001 - urlopen signature
        return _FakeHTTPResponse(_json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": result if result is not None else {
                "serverInfo": {"name": "fake", "version": "9.9.9"},
                "capabilities": {"tools": {}},
            },
        }))

    return _open


def _refusing_opener(_request, timeout=None):  # noqa: ANN001
    raise ConnectionRefusedError("connection refused")


class TestMCP:

    def test_register_server(self):
        reg = MCPRegistry()
        server = MCPServer(name="test-mcp", host="localhost", port=9000)
        reg.register_server(server)
        assert reg.count() == 1
        assert reg.get(server.id) is server

    def test_connect_disconnect(self):
        reg = MCPRegistry()
        server = MCPServer(name="test")
        reg.register_server(server)
        client = MCPClient(reg, opener=_answering_opener())
        assert client.connect(server) is True
        assert server.status == MCPStatus.CONNECTED
        assert server.connected_at is not None
        assert server.version == "9.9.9", "serverInfo must come from the handshake"
        assert client.disconnect(server.id) is True

    def test_connect_fails_when_the_server_does_not_answer(self):
        """The behaviour R-001 added: no packet, no connection."""
        reg = MCPRegistry()
        server = MCPServer(name="dead")
        reg.register_server(server)
        client = MCPClient(reg, opener=_refusing_opener)
        assert client.connect(server) is False
        assert server.status == MCPStatus.ERROR
        assert server.error
        assert server.connected_at is None

    def test_register_tool(self):
        reg = MCPRegistry()
        server = MCPServer(name="test")
        reg.register_server(server)
        tool = MCPTool(server_id=server.id, name="search", description="Search tool")
        reg.register_tool(tool)
        assert reg.count_tools() == 1

    def test_call_tool(self):
        reg = MCPRegistry()
        server = MCPServer(name="test")
        reg.register_server(server)
        client = MCPClient(reg, opener=_answering_opener({"content": "hello"}))
        client.connect(server)
        tool = MCPTool(server_id=server.id, name="echo")
        call = client.call(tool, server, {"msg": "hello"})
        assert call.success is True
        assert call.result == {"content": "hello"}, "the result must come from the server"
        assert call.duration_ms > 0

    def test_call_fails_when_the_transport_fails(self):
        reg = MCPRegistry()
        server = MCPServer(name="test", status=MCPStatus.CONNECTED)
        reg.register_server(server)
        client = MCPClient(reg, opener=_refusing_opener)
        tool = MCPTool(server_id=server.id, name="echo")
        call = client.call(tool, server, {})
        assert call.success is False
        assert "ConnectionRefusedError" in call.error

    def test_call_disconnected(self):
        reg = MCPRegistry()
        server = MCPServer(name="test")
        reg.register_server(server)
        client = MCPClient(reg)
        tool = MCPTool(server_id=server.id, name="echo")
        call = client.call(tool, server, {"msg": "hello"})
        assert call.success is False
        assert "not connected" in call.error.lower()

    def test_stats(self):
        reg = MCPRegistry()
        server = MCPServer(name="test")
        reg.register_server(server)
        client = MCPClient(reg, opener=_answering_opener())
        client.connect(server)
        stats = client.stats()
        assert stats["connected_servers"] == 1


# ── TestConnectors ───────────────────────────────────────────

class TestConnectors:

    def test_github(self):
        gh = GitHubConnector()
        req = ToolRequest(action="get_repo", parameters={"owner": "me", "repo": "test"})
        result = gh.execute(req)
        assert "repo" in result

    def test_github_create_branch(self):
        gh = GitHubConnector()
        req = ToolRequest(action="create_branch", parameters={"name": "feature/x"})
        result = gh.execute(req)
        assert result["branch"]["name"] == "feature/x"

    def test_gitlab(self):
        gl = GitLabConnector()
        req = ToolRequest(action="get_project", parameters={"project_id": "123", "project": "test"})
        result = gl.execute(req)
        assert "project" in result

    def test_docker(self):
        d = DockerConnector()
        req = ToolRequest(action="list_images")
        result = d.execute(req)
        assert "images" in result

    def test_database(self):
        db = DatabaseConnector()
        req = ToolRequest(action="list_tables", parameters={"db_type": "sqlite"})
        result = db.execute(req)
        assert "tables" in result

    def test_filesystem(self):
        fs = FilesystemConnector()
        req = ToolRequest(action="list", parameters={"path": "/tmp"})
        result = fs.execute(req)
        assert result["path"] == "/tmp"

    def test_rest_api(self):
        api = RestAPIConnector()
        req = ToolRequest(action="get", parameters={"url": "https://api.example.com"})
        result = api.execute(req)
        assert result["method"] == "GET"

    def test_browser(self):
        b = BrowserConnector()
        req = ToolRequest(action="navigate", parameters={"url": "https://example.com"})
        result = b.execute(req)
        assert result["status"] == "loaded"


# ── TestRoutes ───────────────────────────────────────────────

class TestRoutes:

    def test_get_tools(self):
        from backend.tools.routes import _registry
        _registry.register(_make_tool("rt1", "route-tool", ToolType.GITHUB, ToolCategory.VCS))
        result = handle_get_tools()
        assert result["count"] >= 1

    def test_get_tool(self):
        from backend.tools.routes import _registry, _health
        t = _make_tool("rt-get", "get-tool")
        _registry.register(t)
        _health.register(t)
        result = handle_get_tool("rt-get")
        assert result is not None
        assert result["tool"]["name"] == "get-tool"

    def test_post_register(self):
        result = handle_post_register({
            "name": "dynamic-tool", "tool_type": "github",
            "category": "vcs", "permissions": ["read", "write"],
        })
        assert result["registered"] is True

    def test_post_execute(self):
        from backend.tools.routes import _registry, _executor
        t = _make_tool("rt-exec", "exec-tool")
        _registry.register(t)
        _executor.register_executor("rt-exec", lambda req: {"done": True})
        result = handle_post_execute("rt-exec", "test", {})
        assert result["executed"] is True

    def test_post_select(self):
        from backend.tools.routes import _registry
        _registry.register(_make_tool("rt-sel", "gh", ToolType.GITHUB, ToolCategory.VCS))
        result = handle_post_select(action="fix github bug")
        assert result["selected"] is True

    def test_get_health(self):
        result = handle_get_health()
        assert "total" in result

    def test_get_metrics(self):
        result = handle_get_metrics()
        assert "registry" in result
        assert "executor" in result

    def test_mcp_servers(self):
        result = handle_get_mcp_servers()
        assert "servers" in result

    def test_mcp_connect(self):
        """With no MCP server on the given host, connect must report failure.

        Previously this asserted connected is True against a fabrication, which
        is exactly what R-001 removed: the Tools Center showed servers as
        connected that had never been contacted.
        """
        result = handle_post_mcp_connect("test-server", host="127.0.0.1", port=59999)
        assert result["connected"] is False
        assert result["server"]["error"]

    def test_mcp_disconnect(self):
        from backend.tools.routes import _mcp_registry
        server = MCPServer(name="disc-test", status=MCPStatus.CONNECTED)
        _mcp_registry.register_server(server)
        result = handle_post_mcp_disconnect(server.id)
        assert result["disconnected"] is True


# ── TestThreadSafety ─────────────────────────────────────────

class TestThreadSafety:

    def test_concurrent_registry(self):
        reg = ToolRegistry()
        errors = []
        def worker(start: int):
            try:
                for i in range(start, start + 25):
                    reg.register(_make_tool(f"t{i}", f"tool-{i}"))
                    reg.get(f"t{i}")
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=worker, args=(i * 25,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert 25 <= reg.count() <= 100

    def test_concurrent_executor(self):
        policy = ToolPolicy()
        sandbox = ToolSandbox()
        executor = ToolExecutor(policy, sandbox)
        executor.register_executor("shared", lambda req: {"ok": True})
        tool = _make_tool("shared", "shared")

        def worker():
            for _ in range(10):
                req = ToolRequest(tool_id="shared", action="test")
                result = executor.execute(req, tool)
                assert result.status in (ExecutionStatus.COMPLETED, ExecutionStatus.DENIED)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
