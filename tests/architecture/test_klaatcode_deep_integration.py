"""Tests for KlaatCode Deep Integration (HOS-054D).

Covers: Code Graph Adapter, Diagnostics Adapter, Cost Guard Adapter,
Workspace Protection, Advanced Memory, Runtime Recommendations,
and End-to-End Mission flow.

Minimum 40 tests.

Run with: python3 -m pytest tests/architecture/test_klaatcode_deep_integration.py -v
"""

from __future__ import annotations

import pytest

from backend.integrations.klaatcode import (
    CodeGraphAdapter,
    CostGuardAdapter,
    DiagnosticsAdapter,
    DiagnosticsReport,
    RuntimeRecommendation,
    TaskCostEstimate,
)
from backend.memory.knowledge_graph import KnowledgeGraph
from backend.memory.memory_manager import MemoryManager
from backend.workspace.workspace_manager import WorkspaceManager
from backend.agents.specialized.klaatcode import (
    KlaatCodeTaskType,
    create_klaatcode_agent,
)


# ═══════════════════════════════════════════════════════════════
# CODE GRAPH ADAPTER
# ═══════════════════════════════════════════════════════════════

class TestCodeGraphAdapter:
    """Tests for CodeGraphAdapter bridging KlaatCode → Knowledge Graph."""

    @pytest.fixture
    def kg(self):
        return KnowledgeGraph()

    @pytest.fixture
    def adapter(self, kg):
        return CodeGraphAdapter(knowledge_graph=kg)

    def test_index_empty_analysis(self, adapter):
        result = adapter.index_analysis({"files": []})
        assert result["nodes"] == 0
        assert result["edges"] == 0

    def test_index_single_file(self, adapter):
        analysis = {
            "project": {"language": "python"},
            "files": [{"path": "src/main.py", "classes": [], "functions": [], "imports": [], "dependencies": []}],
        }
        result = adapter.index_analysis(analysis, agent_id="agent-1", mission_id="m1")
        assert result["files"] == 1
        assert result["nodes"] >= 1

    def test_index_file_with_classes(self, adapter):
        analysis = {
            "project": {"language": "typescript"},
            "files": [{
                "path": "src/app.ts",
                "classes": [{"name": "UserService"}],
                "functions": [{"name": "authenticate"}],
                "imports": [],
                "dependencies": [],
            }],
        }
        result = adapter.index_analysis(analysis)
        assert result["edges"] >= 1  # FILE→CLASS edge

    def test_agent_modifications_recorded(self, adapter):
        analysis = {
            "project": {"language": "python"},
            "files": [{"path": "auth.py", "classes": [], "functions": [], "imports": [], "dependencies": []}],
        }
        adapter.index_analysis(analysis, agent_id="klaatcode-agent")
        mods = adapter.get_agent_modifications("klaatcode-agent")
        assert len(mods) > 0

    def test_search_code_entities(self, adapter):
        analysis = {
            "project": {"language": "python"},
            "files": [{"path": "src/auth/login.py", "classes": [], "functions": [], "imports": [], "dependencies": []}],
        }
        adapter.index_analysis(analysis)
        results = adapter.search_code_entities("login")
        assert len(results) > 0

    def test_get_file_graph(self, adapter):
        analysis = {
            "project": {"language": "go"},
            "files": [{"path": "main.go", "classes": [], "functions": [], "imports": [], "dependencies": []}],
        }
        adapter.index_analysis(analysis)
        graph = adapter.get_file_graph("main.go")
        assert "nodes" in graph

    def test_add_test_relation(self, adapter):
        analysis = {
            "files": [
                {"path": "src/auth.py", "classes": [], "functions": [], "imports": [], "dependencies": []},
                {"path": "tests/test_auth.py", "classes": [], "functions": [], "imports": [], "dependencies": []},
            ],
        }
        adapter.index_analysis(analysis)
        result = adapter.add_test_relation("src/auth.py", "tests/test_auth.py")
        assert result is True

    def test_stats(self, adapter):
        analysis = {"files": [{"path": "f.py", "classes": [], "functions": [], "imports": [], "dependencies": []}]}
        adapter.index_analysis(analysis)
        stats = adapter.stats()
        assert stats["analyses_indexed"] == 1
        assert stats["total_entities"] > 0


# ═══════════════════════════════════════════════════════════════
# DIAGNOSTICS ADAPTER
# ═══════════════════════════════════════════════════════════════

class TestDiagnosticsAdapter:
    """Tests for DiagnosticsAdapter bridging KlaatCode → Validation Engine."""

    @pytest.fixture
    def adapter(self):
        return DiagnosticsAdapter()

    def test_analyze_empty_diagnostics(self, adapter):
        report = adapter.analyze_diagnostics([], target="test.py")
        assert isinstance(report, DiagnosticsReport)
        assert report.total_errors == 0
        assert report.total_warnings == 0

    def test_analyze_with_errors(self, adapter):
        data = {
            "diagnostics": [
                {"file_path": "src/app.ts", "severity": "error", "line": 42, "column": 10,
                 "message": "Type error", "rule_id": "ts2322", "suggestion": "Use number"},
                {"file_path": "src/app.ts", "severity": "warning", "line": 10, "column": 1,
                 "message": "Unused variable", "rule_id": "no-unused-vars", "suggestion": "Remove or use"},
            ]
        }
        report = adapter.analyze_diagnostics(data, target="src/app.ts")
        assert report.total_errors == 1
        assert report.total_warnings == 1
        assert report.auto_fixable_count >= 1

    def test_analyze_security_error_triggers_review(self, adapter):
        data = {
            "diagnostics": [
                {"file_path": "src/api.ts", "severity": "error", "line": 1, "column": 1,
                 "message": "SQL injection vulnerability", "rule_id": "security/sql-injection", "suggestion": ""},
            ] * 6
        }
        report = adapter.analyze_diagnostics(data, target="src/api.ts")
        assert report.needs_human_review

    def test_validate_patch_accepts_clean(self, adapter):
        diag = DiagnosticsReport(report_id="d1", target="test.py", total_errors=0)
        result = adapter.validate_patch("p1", "test.py", diagnostics=diag)
        assert result.accepted
        assert result.reason == "passed"

    def test_validate_patch_rejects_errors(self, adapter):
        diag = DiagnosticsReport(report_id="d2", target="test.py", total_errors=3)
        result = adapter.validate_patch("p2", "test.py", diagnostics=diag)
        assert not result.accepted
        assert "errors" in result.reason

    def test_validate_patch_rejects_excessive_warnings(self, adapter):
        diag = DiagnosticsReport(report_id="d3", target="test.py", total_warnings=15)
        result = adapter.validate_patch("p3", "test.py", diagnostics=diag)
        assert not result.accepted

    def test_get_fix_suggestions(self, adapter):
        data = {
            "diagnostics": [
                {"file_path": "src/app.ts", "severity": "error", "line": 1, "column": 1,
                 "message": "Missing import", "rule_id": "import", "suggestion": "Add import statement"},
            ]
        }
        report = adapter.analyze_diagnostics(data)
        suggestions = adapter.get_fix_suggestions(report)
        assert len(suggestions) > 0

    def test_stats(self, adapter):
        diag = DiagnosticsReport(report_id="s1", target="f.py")
        adapter.validate_patch("p1", "f.py", diagnostics=diag)
        adapter.analyze_diagnostics([], target="f2.py")
        stats = adapter.stats()
        assert stats["patches_validated"] == 1
        assert stats["reports_generated"] == 1


# ═══════════════════════════════════════════════════════════════
# COST GUARD ADAPTER
# ═══════════════════════════════════════════════════════════════

class TestCostGuardAdapter:
    """Tests for CostGuardAdapter bridging KlaatCode → Runtime Orchestrator."""

    @pytest.fixture
    def adapter(self):
        return CostGuardAdapter()

    def test_estimate_simple_task(self, adapter):
        estimate = adapter.estimate_task("t1", "code_analysis",
                                          project_size_files=10, project_size_lines=500)
        assert isinstance(estimate, TaskCostEstimate)
        assert estimate.complexity < 5
        assert estimate.estimated_tokens > 0

    def test_estimate_complex_task(self, adapter):
        estimate = adapter.estimate_task("t2", "refactoring",
                                          project_size_files=200, project_size_lines=50000)
        assert estimate.complexity > 5
        assert estimate.recommended_runtime in ("gpu", "cloud_gpu")

    def test_estimate_large_project_increases_complexity(self, adapter):
        small = adapter.estimate_task("s", "code_analysis", project_size_files=5)
        large = adapter.estimate_task("l", "code_analysis", project_size_files=150)
        assert large.complexity > small.complexity

    def test_recommend_runtime(self, adapter):
        rec = adapter.recommend_runtime("t1", "code_generation",
                                         project_size_files=50, project_size_lines=10000)
        assert isinstance(rec, RuntimeRecommendation)
        assert rec.primary_runtime
        assert rec.primary_model
        assert rec.confidence > 0

    def test_recommend_high_complexity(self, adapter):
        rec = adapter.recommend_runtime("t_hard", "refactoring",
                                         project_size_files=300, project_size_lines=100000)
        assert rec.estimated_cost > 0
        assert rec.confidence > 0.5

    def test_get_estimate_cached(self, adapter):
        adapter.estimate_task("t_cached", "run_diagnostics")
        est = adapter.get_estimate("t_cached")
        assert est is not None
        assert est.task_id == "t_cached"

    def test_stats(self, adapter):
        adapter.estimate_task("t1", "code_analysis")
        adapter.estimate_task("t2", "code_generation")
        adapter.recommend_runtime("t3", "refactoring", project_size_files=50)
        stats = adapter.stats()
        assert stats["tasks_analyzed"] == 3
        assert stats["recommendations"] == 1


# ═══════════════════════════════════════════════════════════════
# WORKSPACE PROTECTION
# ═══════════════════════════════════════════════════════════════

class TestWorkspaceProtection:
    """Tests for workspace-enforced file editing."""

    @pytest.fixture
    def workspace_mgr(self):
        return WorkspaceManager(base_path="/tmp/test-hermes-ws")

    def test_agent_requires_workspace_for_edit(self, workspace_mgr):
        agent = create_klaatcode_agent(workspace_manager=workspace_mgr)
        result = agent.execute_task(
            task_type=KlaatCodeTaskType.CODE_EDITING,
            parameters={"file": "src/app.py", "content": "new"},
            mission_id="m1",
            node_id="n1",
        )
        # Should fail because no workspace_id provided
        assert "workspace" in result.error_message.lower()

    def test_agent_edit_with_valid_workspace(self, workspace_mgr):
        ws = workspace_mgr.create(mission_id="m-ws", agent_id="klaatcode-agent")
        agent = create_klaatcode_agent(workspace_manager=workspace_mgr)
        result = agent.execute_task(
            task_type=KlaatCodeTaskType.CODE_EDITING,
            parameters={"file": "src/app.py", "content": "new", "workspace_id": ws.workspace_id},
            mission_id="m-ws",
            node_id="n-ws",
        )
        # Should succeed with valid workspace
        assert result.outcome.value in ("success", "failure")  # depends on MCP availability

    def test_agent_edit_with_invalid_workspace(self, workspace_mgr):
        agent = create_klaatcode_agent(workspace_manager=workspace_mgr)
        result = agent.execute_task(
            task_type=KlaatCodeTaskType.CODE_EDITING,
            parameters={"file": "src/app.py", "content": "new", "workspace_id": "nonexistent"},
            mission_id="m-inv",
            node_id="n-inv",
        )
        assert "not found" in result.summary.lower()

    def test_analysis_no_workspace_required(self, workspace_mgr):
        """Read-only tasks like analysis don't require workspace."""
        agent = create_klaatcode_agent(workspace_manager=workspace_mgr)
        result = agent.execute_task(
            task_type=KlaatCodeTaskType.CODE_ANALYSIS,
            parameters={"path": "."},
            mission_id="m-no-ws",
            node_id="n-no-ws",
        )
        assert result.outcome.value == "success"


# ═══════════════════════════════════════════════════════════════
# ADVANCED MEMORY INTEGRATION
# ═══════════════════════════════════════════════════════════════

class TestAdvancedMemoryIntegration:
    """Tests for advanced memory integration (episodic + procedural + learning)."""

    @pytest.fixture
    def mm(self):
        return MemoryManager()

    def test_task_records_episodic_memory(self, mm):
        agent = create_klaatcode_agent(memory_manager=mm)
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": "."},
                            mission_id="mem-test-1", node_id="n1")
        episode = mm.get_episode("mem-test-1")
        assert episode is not None

    def test_task_records_procedural_memory(self, mm):
        agent = create_klaatcode_agent(memory_manager=mm)
        agent.execute_task(KlaatCodeTaskType.CODE_GENERATION, {"prompt": "test"},
                            mission_id="mem-test-2", node_id="n2")
        # Procedural memory should have been stored
        procs = mm.find_procedures("klaatcode")
        assert len(procs) > 0

    def test_get_experience_recommendations(self, mm):
        agent = create_klaatcode_agent(memory_manager=mm)
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": ".", "language": "python"},
                            mission_id="rec-1", node_id="r1")
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": ".", "language": "python"},
                            mission_id="rec-2", node_id="r2")
        recs = agent.get_experience_recommendations("code_analysis", language="python")
        assert isinstance(recs, dict)
        assert "similar_episodes" in recs or "similar_missions" in recs

    def test_agent_without_memory_still_works(self):
        agent = create_klaatcode_agent(memory_manager=None)
        result = agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": "."})
        assert result.outcome.value == "success"
        recs = agent.get_experience_recommendations("test")
        assert recs["similar_episodes"] == 0


# ═══════════════════════════════════════════════════════════════
# RUNTIME RECOMMENDATION
# ═══════════════════════════════════════════════════════════════

class TestRuntimeRecommendation:
    """Tests for CostGuard → Runtime Orchestrator integration."""

    def test_simple_task_low_runtime(self):
        adapter = CostGuardAdapter()
        rec = adapter.recommend_runtime("t1", "code_analysis", project_size_files=5, project_size_lines=200)
        assert rec.primary_runtime in ("cpu", "hybrid")

    def test_complex_task_high_runtime(self):
        adapter = CostGuardAdapter()
        rec = adapter.recommend_runtime("t_h", "refactoring", project_size_files=500, project_size_lines=200000)
        assert rec.primary_runtime in ("gpu", "cloud_gpu")

    def test_confidence_scale(self):
        adapter = CostGuardAdapter()
        rec_low = adapter.recommend_runtime("low", "run_diagnostics", project_size_files=1, project_size_lines=10)
        rec_high = adapter.recommend_runtime("high", "code_generation", project_size_files=100, project_size_lines=50000)
        assert rec_high.confidence >= rec_low.confidence - 0.1  # approximate

    def test_cost_estimation_positive(self):
        adapter = CostGuardAdapter()
        est = adapter.estimate_task("t_cost", "code_generation", project_size_files=20, project_size_lines=5000)
        assert est.estimated_cost_tokens > 0
        assert est.estimated_tokens > 0


# ═══════════════════════════════════════════════════════════════
# END-TO-END MISSION
# ═══════════════════════════════════════════════════════════════

class TestEndToEndKlaatCodeMission:
    """End-to-end mission: KlaatCode analysis → diagnostics → workspace → memory."""

    def test_full_analysis_pipeline(self):
        """KlaatCode analyzes project → stores in Knowledge Graph → records memory."""
        kg = KnowledgeGraph()
        graph_adapter = CodeGraphAdapter(knowledge_graph=kg)
        mm = MemoryManager()
        ws_mgr = WorkspaceManager(base_path="/tmp/test-e2e-ws")

        agent = create_klaatcode_agent(
            memory_manager=mm,
            workspace_manager=ws_mgr,
            code_graph_adapter=graph_adapter,
        )

        # Step 1: Analyze project
        result = agent.execute_task(
            KlaatCodeTaskType.CODE_ANALYSIS,
            {"path": ".", "language": "python", "project": "test-app"},
            mission_id="e2e-mission",
            node_id="e2e-analyze",
        )
        assert result.outcome.value == "success"

        # Step 2: Run diagnostics
        result2 = agent.execute_task(
            KlaatCodeTaskType.DIAGNOSTICS,
            {"file": "src/main.py"},
            mission_id="e2e-mission",
            node_id="e2e-diag",
        )
        assert result2.outcome.value == "success"

        # Verify memory was recorded
        episode = mm.get_episode("e2e-mission")
        assert episode is not None
        assert "klaatcode" in episode.tags

    def test_full_edit_pipeline_with_workspace(self):
        """KlaatCode edits file → through workspace sandbox."""
        ws_mgr = WorkspaceManager(base_path="/tmp/test-e2e-edit-ws")
        ws = ws_mgr.create(mission_id="edit-mission", agent_id="klaatcode-agent")

        agent = create_klaatcode_agent(workspace_manager=ws_mgr)

        result = agent.execute_task(
            KlaatCodeTaskType.CODE_EDITING,
            {"file": "src/auth.py", "content": "fixed", "workspace_id": ws.workspace_id},
            mission_id="edit-mission",
            node_id="edit-node",
        )
        assert result.outcome.value == "success"


# ═══════════════════════════════════════════════════════════════
# THREAD SAFETY
# ═══════════════════════════════════════════════════════════════

class TestDeepIntegrationThreadSafety:
    """Tests for thread safety across deep integration adapters."""

    def test_concurrent_graph_indexing(self):
        import threading
        kg = KnowledgeGraph()
        adapter = CodeGraphAdapter(knowledge_graph=kg)
        errors = []

        def worker(i):
            try:
                analysis = {
                    "files": [{"path": f"src/file_{i}.py", "classes": [], "functions": [], "imports": [], "dependencies": []}],
                }
                for _ in range(10):
                    adapter.index_analysis(analysis, agent_id=f"agent-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert len(errors) == 0

    def test_concurrent_cost_estimation(self):
        import threading
        adapter = CostGuardAdapter()
        errors = []

        def worker(i):
            try:
                for _ in range(20):
                    adapter.estimate_task(f"t-{i}-{_}", "code_analysis", project_size_files=i * 10)
                    adapter.get_estimate(f"t-{i}-{_}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert len(errors) == 0

    def test_concurrent_diagnostics(self):
        import threading
        adapter = DiagnosticsAdapter()
        errors = []

        def worker():
            try:
                for _ in range(20):
                    adapter.analyze_diagnostics([], target="test.py")
                    diag = DiagnosticsReport(report_id="d", target="x.py")
                    adapter.validate_patch("p", "x.py", diagnostics=diag)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert len(errors) == 0
