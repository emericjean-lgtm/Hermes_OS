"""Tests for Oh My Pi Deep Integration (HOS-055C).

Covers: LSP Bridge, AST Adapter, Debug Adapter, Workspace Adapter,
Runtime Adapter, Memory Adapter.

Minimum 52 tests.
"""

from __future__ import annotations

import threading
import pytest

from backend.memory.knowledge_graph import KnowledgeGraph
from backend.memory.memory_manager import MemoryManager
from backend.workspace.workspace_manager import WorkspaceManager
from backend.integrations.ohmypi import (
    LSPBridgeAdapter, LSPSymbol, LSPDiagnostic, CodeStructure,
    DebugAdapter, DebugSession, DebugBreakpoint, StackFrame,
    ASTAdapter, ASTNode, ASTAnalysis,
    OhMyPiWorkspaceAdapter,
    OhMyPiRuntimeAdapter, OhMyPiRuntimeInfo,
    OhMyPiMemoryAdapter, OhMyPiExperience,
)


# ═══════════════════════════════════════════════════════════════
# LSP BRIDGE (10 tests)
# ═══════════════════════════════════════════════════════════════

class TestLSPBridge:
    @pytest.fixture
    def kg(self): return KnowledgeGraph()

    @pytest.fixture
    def bridge(self, kg): return LSPBridgeAdapter(knowledge_graph=kg)

    def test_index_symbols(self, bridge):
        syms = [LSPSymbol(name="authenticate", kind="function", file_path="auth.py", line=42)]
        count = bridge.index_symbols("auth.py", syms)
        assert count == 1

    def test_find_symbol_by_name(self, bridge):
        bridge.index_symbols("auth.py", [LSPSymbol(name="login", kind="function", file_path="auth.py", line=10)])
        sym = bridge.find_symbol("login")
        assert sym is not None; assert sym.file_path == "auth.py"

    def test_find_symbol_with_file(self, bridge):
        bridge.index_symbols("a.py", [LSPSymbol(name="f", kind="function", file_path="a.py", line=1)])
        bridge.index_symbols("b.py", [LSPSymbol(name="f", kind="function", file_path="b.py", line=1)])
        sym = bridge.find_symbol("f", file_path="b.py")
        assert sym is not None; assert sym.file_path == "b.py"

    def test_find_references(self, bridge):
        syms = [LSPSymbol(name="main", kind="function", file_path="main.py", line=1),
                LSPSymbol(name="main", kind="function", file_path="cli.py", line=5)]
        bridge.index_symbols("src", syms)
        refs = bridge.find_references("main")
        assert len(refs) == 2

    def test_index_diagnostics(self, bridge):
        diags = [LSPDiagnostic(file_path="a.py", severity="error", line=1, message="syntax error"),
                 LSPDiagnostic(file_path="a.py", severity="warning", line=10, message="unused")]
        result = bridge.index_diagnostics("a.py", diags)
        assert result["errors"] == 1; assert result["warnings"] == 1

    def test_get_diagnostics_by_file(self, bridge):
        bridge.index_diagnostics("x.py", [LSPDiagnostic(file_path="x.py", severity="error", line=1, message="err")])
        diags = bridge.get_diagnostics("x.py")
        assert len(diags) == 1

    def test_get_diagnostics_all(self, bridge):
        bridge.index_diagnostics("a.py", [LSPDiagnostic(file_path="a.py", severity="error", line=1, message="e")])
        bridge.index_diagnostics("b.py", [LSPDiagnostic(file_path="b.py", severity="warning", line=2, message="w")])
        assert len(bridge.get_diagnostics()) == 2

    def test_index_structure(self, bridge):
        struct = CodeStructure(file_path="main.py", language="python",
                                symbols=[LSPSymbol(name="app", kind="class", file_path="main.py", line=5)])
        count = bridge.index_structure(struct)
        assert count == 1

    def test_get_code_structure(self, bridge):
        bridge.index_structure(CodeStructure(file_path="config.py", language="python"))
        s = bridge.get_code_structure("config.py")
        assert s is not None; assert s.file_path == "config.py"

    def test_stats(self, bridge):
        bridge.index_symbols("f.py", [LSPSymbol(name="g", kind="function", file_path="f.py", line=1)])
        s = bridge.stats()
        assert s["symbols"] >= 1


# ═══════════════════════════════════════════════════════════════
# AST ADAPTER (10 tests)
# ═══════════════════════════════════════════════════════════════

class TestASTAdapter:
    @pytest.fixture
    def kg(self): return KnowledgeGraph()

    @pytest.fixture
    def adapter(self, kg): return ASTAdapter(knowledge_graph=kg)

    def test_analyze_empty_file(self, adapter):
        analysis = adapter.analyze("empty.py", language="python")
        assert analysis.file_path == "empty.py"; assert analysis.complexity_score >= 0

    def test_analyze_with_functions(self, adapter):
        funcs = [{"name": "process", "line_start": 10, "line_end": 50, "parameters": ["x", "y"]}]
        analysis = adapter.analyze("proc.py", language="python", functions=funcs, total_lines=100)
        assert len(analysis.functions) == 1; assert analysis.complexity_score > 0

    def test_analyze_with_classes(self, adapter):
        clses = [{"name": "UserService", "line_start": 15, "line_end": 80}]
        analysis = adapter.analyze("user.py", language="python", classes=clses, total_lines=100)
        assert len(analysis.classes) == 1

    def test_analyze_with_imports(self, adapter):
        analysis = adapter.analyze("main.py", language="python", imports=["os", "sys"], total_lines=20)
        assert len(analysis.imports) == 2; analysis.imports == ["os", "sys"]

    def test_get_analysis(self, adapter):
        adapter.analyze("test.py", language="python", total_lines=50)
        a = adapter.get_analysis("test.py")
        assert a is not None

    def test_detect_complex_functions(self, adapter):
        adapter.analyze("big.py", language="python",
                         functions=[{"name": "big_func", "line_start": 1, "line_end": 200, "parameters": list(range(10))}],
                         total_lines=250)
        complex_funcs = adapter.detect_complex_functions(threshold=5.0)
        assert len(complex_funcs) >= 1

    def test_get_dependencies(self, adapter):
        adapter.analyze("dep.py", language="python", imports=["numpy", "pandas"], total_lines=30)
        deps = adapter.get_dependencies("dep.py")
        assert len(deps) == 2

    def test_stats(self, adapter):
        adapter.analyze("a.py", language="python", functions=[{"name": "f", "line_start": 1, "line_end": 10}], total_lines=20)
        s = adapter.stats()
        assert s["files_analyzed"] >= 1; assert s["total_functions"] >= 1

    def test_complexity_estimation(self, adapter):
        analysis = adapter.analyze("complex.py", language="python",
                                    functions=[{"name": "f1", "line_start": 1, "line_end": 100, "parameters": range(10)},
                                               {"name": "f2", "line_start": 101, "line_end": 200, "parameters": range(5)}],
                                    total_lines=250)
        assert analysis.complexity_score > 5.0

    def test_unknown_file_returns_none(self, adapter):
        assert adapter.get_analysis("nonexistent.py") is None


# ═══════════════════════════════════════════════════════════════
# DEBUG ADAPTER (8 tests)
# ═══════════════════════════════════════════════════════════════

class TestDebugAdapter:
    @pytest.fixture
    def adapter(self): return DebugAdapter()

    def test_create_session(self, adapter):
        s = adapter.create_session("app.py", debugger_type="debugpy")
        assert s.program == "app.py"; assert s.status == "created"

    def test_add_breakpoint(self, adapter):
        s = adapter.create_session("prog.py")
        bp = adapter.add_breakpoint(s.session_id, "prog.py", 42)
        assert bp is not None; assert bp.line == 42

    def test_update_stack(self, adapter):
        s = adapter.create_session("main.go")
        adapter.update_stack(s.session_id, [{"id": "f0", "function": "main", "file": "main.go", "line": 10, "variables": {"x": "42"}}])
        frames = adapter.get_stack_trace(s.session_id)
        assert len(frames) == 1; assert frames[0].function_name == "main"

    def test_get_variables(self, adapter):
        s = adapter.create_session("calc.py")
        adapter.update_stack(s.session_id, [{"id": "f0", "function": "add", "file": "calc.py", "line": 5, "variables": {"a": "1", "b": "2"}}])
        vars = adapter.get_variables(s.session_id)
        assert "a" in vars; assert "b" in vars

    def test_record_incident(self, adapter):
        s = adapter.create_session("bug.py")
        adapter.record_incident(s.session_id, {"type": "error", "message": "segfault"})
        assert len(s.incidents) == 1

    def test_complete_session(self, adapter):
        s = adapter.create_session("done.py")
        assert adapter.complete_session(s.session_id)
        assert s.status == "completed"

    def test_get_nonexistent_session(self, adapter):
        assert adapter.get_session("nonexistent") is None

    def test_stats(self, adapter):
        adapter.create_session("a.py"); adapter.create_session("b.py")
        s = adapter.stats()
        assert s["total_sessions"] == 2


# ═══════════════════════════════════════════════════════════════
# WORKSPACE ADAPTER (8 tests)
# ═══════════════════════════════════════════════════════════════

class TestWorkspaceAdapter:
    @pytest.fixture
    def ws_mgr(self): return WorkspaceManager(base_path="/tmp/test-omp-deep-ws")

    @pytest.fixture
    def adapter(self, ws_mgr): return OhMyPiWorkspaceAdapter(workspace_manager=ws_mgr)

    def test_prepare_edit_creates_workspace(self, adapter):
        result = adapter.prepare_edit("agent-1", "mission-1", "src/app.py")
        assert result["allowed"]; assert result["workspace_id"]
        assert "branch" in result

    def test_commit_edit(self, adapter):
        prep = adapter.prepare_edit("agent-c", "mission-c", "lib/util.py")
        result = adapter.commit_edit(prep["workspace_id"], "lib/util.py",
                                      message="Fixed util", agent_id="agent-c")
        assert result["committed"]; assert result["hash"]

    def test_rollback_edit(self, adapter):
        prep = adapter.prepare_edit("agent-rb", "mission-rb", "tmp/x.py")
        adapter.commit_edit(prep["workspace_id"], "tmp/x.py", message="test")
        result = adapter.rollback_edit(prep["workspace_id"])
        assert result["rolled_back"]

    def test_validate_edit_path_no_workspace(self, adapter):
        assert not adapter.validate_edit_path("file.py", workspace_id="")

    def test_validate_edit_path_with_workspace(self, adapter):
        prep = adapter.prepare_edit("agent-v", "mission-v", "valid.py")
        assert adapter.validate_edit_path("valid.py", workspace_id=prep["workspace_id"])

    def test_edit_count_increments(self, adapter):
        adapter.prepare_edit("a1", "m1", "f1.py")
        adapter.prepare_edit("a1", "m2", "f2.py")
        assert adapter.stats()["edit_count"] == 2

    def test_nonexistent_workspace_commit(self, adapter):
        result = adapter.commit_edit("fake-id", "f.py")
        assert not result["committed"]

    def test_without_workspace_manager(self):
        adapter_no_ws = OhMyPiWorkspaceAdapter(workspace_manager=None)
        result = adapter_no_ws.prepare_edit("a", "m", "f.py")
        assert not result["allowed"]


# ═══════════════════════════════════════════════════════════════
# RUNTIME ADAPTER (8 tests)
# ═══════════════════════════════════════════════════════════════

class TestRuntimeAdapter:
    @pytest.fixture
    def adapter(self): return OhMyPiRuntimeAdapter()

    def test_get_info(self, adapter):
        info = adapter.get_info()
        assert info.runtime_id == "ohmypi"; assert "lsp" in info.capabilities

    def test_get_suitability_high_for_editing(self, adapter):
        score = adapter.get_suitability("code_editing")
        assert score > 0.9

    def test_get_suitability_low_for_docs(self, adapter):
        score = adapter.get_suitability("documentation")
        assert score < 0.6

    def test_context_boosts_score(self, adapter):
        base = adapter.get_suitability("code_editing")
        boosted = adapter.get_suitability("code_editing", {"language": "rust", "needs_lsp": True})
        assert boosted > base

    def test_recommend(self, adapter):
        rec = adapter.recommend("lsp_navigation", {"language": "typescript"})
        assert rec["recommended"]; assert rec["suitability"] > 0.9

    def test_not_recommend_for_low_suitability(self, adapter):
        rec = adapter.recommend("deployment")
        assert not rec["recommended"]

    def test_register(self, adapter):
        assert adapter.register()

    def test_stats(self, adapter):
        adapter.get_suitability("code_editing")
        adapter.get_suitability("debugging")
        s = adapter.stats()
        assert s["tasks_evaluated"] == 2


# ═══════════════════════════════════════════════════════════════
# MEMORY ADAPTER (8 tests)
# ═══════════════════════════════════════════════════════════════

class TestMemoryAdapter:
    @pytest.fixture
    def mm(self): return MemoryManager()

    @pytest.fixture
    def adapter(self, mm): return OhMyPiMemoryAdapter(memory_manager=mm)

    def test_record_experience(self, adapter):
        exp = OhMyPiExperience(experience_id="e1", task_type="code_editing", language="python",
                                problem="TypeError in auth.py", solution="Added type hint",
                                files_modified=["auth.py"], success=True, duration_ms=120.0)
        adapter.record_experience(exp)
        assert "e1" in adapter._experiences

    def test_get_effective_corrections(self, adapter):
        adapter.record_experience(OhMyPiExperience(experience_id="e2", task_type="debugging",
                problem="null pointer", solution="Add null check", success=True))
        adapter.record_experience(OhMyPiExperience(experience_id="e3", task_type="debugging",
                problem="race condition", solution="Add mutex", success=True))
        corrections = adapter.get_effective_corrections("debugging")
        assert len(corrections) >= 1

    def test_find_pattern(self, adapter):
        adapter.record_experience(OhMyPiExperience(experience_id="e4", task_type="code_editing",
                problem="ImportError: No module named 'requests'", solution="pip install requests", success=True))
        matches = adapter.find_pattern("ImportError")
        assert len(matches) >= 1

    def test_add_code_pattern(self, adapter):
        adapter.add_code_pattern("try-except for I/O operations")
        assert len(adapter._patterns) == 1

    def test_experience_without_memory_manager(self):
        adapter_no_mm = OhMyPiMemoryAdapter(memory_manager=None)
        exp = OhMyPiExperience(experience_id="e5", task_type="test", success=True)
        adapter_no_mm.record_experience(exp)
        assert "e5" in adapter_no_mm._experiences

    def test_failed_experience(self, adapter):
        adapter.record_experience(OhMyPiExperience(experience_id="e6", task_type="debugging",
                problem="Unknown error", solution="", success=False))
        # Failed experiences should still be stored
        assert "e6" in adapter._experiences

    def test_stats(self, adapter):
        adapter.record_experience(OhMyPiExperience(experience_id="es1", task_type="code_editing", success=True))
        adapter.record_experience(OhMyPiExperience(experience_id="es2", task_type="debugging", success=True))
        adapter.record_experience(OhMyPiExperience(experience_id="es3", task_type="code_editing", success=False))
        s = adapter.stats()
        assert s["total_experiences"] == 3; assert s["success_rate"] > 0

    def test_corrections_capped(self, adapter):
        for i in range(60):
            adapter.record_experience(OhMyPiExperience(experience_id=f"c{i}", task_type="code_editing",
                    problem=f"p{i}", solution=f"s{i}", success=True))
        corrections = adapter.get_effective_corrections("code_editing", limit=10)
        assert len(corrections) <= 10


# ═══════════════════════════════════════════════════════════════
# EVENTS (3 tests)
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiDeepEvents:
    def test_lsp_events(self):
        events = []
        bridge = LSPBridgeAdapter(on_event=lambda et, p, **kw: events.append(et))
        bridge.index_symbols("f.py", [LSPSymbol(name="g", kind="function", file_path="f.py", line=1)])
        assert "ohmypi.lsp.symbols_indexed" in events

    def test_debug_events(self):
        events = []
        adapter = DebugAdapter(on_event=lambda et, p, **kw: events.append(et))
        adapter.create_session("app.py")
        assert DebugAdapter.EVENTS["started"] in events

    def test_memory_events(self):
        events = []
        adapter = OhMyPiMemoryAdapter(on_event=lambda et, p, **kw: events.append(et))
        adapter.record_experience(OhMyPiExperience(experience_id="ev1", task_type="test", success=True))
        assert "ohmypi.memory.recorded" in events


# ═══════════════════════════════════════════════════════════════
# THREAD SAFETY (3 tests)
# ═══════════════════════════════════════════════════════════════

class TestOhMyPiDeepThreadSafety:
    def test_concurrent_lsp_bridge(self):
        bridge = LSPBridgeAdapter()
        errors = []

        def worker(i):
            try:
                for _ in range(10):
                    bridge.index_symbols(f"f{i}.py", [LSPSymbol(name=f"sym{i}", kind="function", file_path=f"f{i}.py", line=i)])
                    bridge.find_symbol(f"sym{i}")
            except Exception as e: errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)
        assert len(errors) == 0

    def test_concurrent_memory_adapter(self):
        adapter = OhMyPiMemoryAdapter()
        errors = []

        def worker(i):
            try:
                for _ in range(10):
                    adapter.record_experience(OhMyPiExperience(experience_id=f"t-{i}-{_}", task_type="test", success=True))
            except Exception as e: errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)
        assert len(errors) == 0

    def test_concurrent_debug_sessions(self):
        adapter = DebugAdapter()
        errors = []

        def worker(i):
            try:
                for _ in range(10):
                    s = adapter.create_session(f"prog_{i}.py")
                    adapter.add_breakpoint(s.session_id, f"prog_{i}.py", i * 10)
                    adapter.complete_session(s.session_id)
            except Exception as e: errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)
        assert len(errors) == 0
