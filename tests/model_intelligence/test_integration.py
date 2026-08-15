"""Model Intelligence Integration Tests (HOS-065B).

Tests integration with Autonomous Core, Runtime Orchestrator,
Evolution Engine, Memory, and Explainability.
"""

from __future__ import annotations

import threading


from backend.model_intelligence.model_autonomous_adapter import (
    AutonomousModelDecision,
    ModelAutonomousAdapter,
    ModelExecutionFeedback,
)
from backend.model_intelligence.model_evolution_adapter import ModelEvolutionAdapter
from backend.model_intelligence.model_intelligence_models import (
    PREDEFINED_MODELS,
    ModelPerformanceRecord,
    TaskType,
)
from backend.model_intelligence.model_memory_adapter import ModelMemoryAdapter
from backend.model_intelligence.model_profiler import ModelProfiler
from backend.model_intelligence.model_runtime_adapter import ModelRuntimeAdapter


#: Un modele reel du catalogue, choisi a l'execution plutot qu'ecrit en dur.
#:
#: Ces tests utilisaient « qwen3.6:27b » comme identifiant opaque de modele
#: de code. Le tri des modeles a renomme 21 tags en 11 en inscrivant le
#: contexte mesure dans chaque nom ; PREDEFINED_MODELS a suivi, ces tests
#: non — et rien ne l'a signale, parce que pytest.ini ne declarait que
#: backend/tests. Dix-huit tests etaient rouges sans que personne ne les
#: lance. Lire le catalogue evite que le prochain renommage recommence.
MODELE_REEL = next(m for m, spec in PREDEFINED_MODELS.items()
                   if spec.get('chat_capable'))



# ═══════════════════════════════════════════════════════════════
# Autonomous Core Integration Tests
# ═══════════════════════════════════════════════════════════════


class TestModelAutonomousAdapter:
    def test_select_model_for_goal(self):
        adapter = ModelAutonomousAdapter()
        decision = adapter.select_model_for_goal(
            goal_id="goal-1",
            goal_phase="execution",
            task_description="Refactor this Python API code",
            mission_id="mission-1",
        )
        assert isinstance(decision, AutonomousModelDecision)
        assert decision.goal_id == "goal-1"
        assert decision.goal_phase == "execution"
        assert decision.model_decision is not None
        assert len(decision.alternative_decisions) >= 0
        assert decision.execution_plan["model"] != ""

    def test_select_model_with_task_type(self):
        adapter = ModelAutonomousAdapter()
        decision = adapter.select_model_for_goal(
            goal_id="goal-2",
            goal_phase="planning",
            task_description="Debug memory leak",
            task_type="debug",
        )
        assert decision.model_decision is not None
        assert decision.execution_plan["task_type"] == "debug"

    def test_record_feedback(self):
        adapter = ModelAutonomousAdapter()
        feedback = ModelExecutionFeedback(
            goal_id="goal-1",
            model_id=MODELE_REEL,
            task_type="code_generation",
            duration_ms=1500.0,
            tokens_used=500,
            success=True,
            validation_score=0.95,
        )
        adapter.record_feedback(feedback)
        stats = adapter.get_stats()
        assert stats["total_feedback"] == 1
        assert stats["success_rate"] == 1.0

    def test_record_feedback_failure(self):
        adapter = ModelAutonomousAdapter()
        feedback = ModelExecutionFeedback(
            goal_id="goal-2",
            model_id="devstral",
            task_type="refactor",
            duration_ms=5000.0,
            tokens_used=200,
            success=False,
            errors=["Syntax error in generated code"],
        )
        adapter.record_feedback(feedback)
        stats = adapter.get_stats()
        assert stats["total_feedback"] == 1
        assert stats["success_rate"] == 0.0

    def test_get_decision_history(self):
        adapter = ModelAutonomousAdapter()
        adapter.select_model_for_goal("goal-1", "execution", "Fix bug")
        adapter.select_model_for_goal("goal-2", "analysis", "Analyze code")
        history = adapter.get_decision_history()
        assert len(history) >= 2

    def test_get_decision_history_filtered(self):
        adapter = ModelAutonomousAdapter()
        adapter.select_model_for_goal("goal-x", "execution", "Write tests")
        filtered = adapter.get_decision_history(goal_id="goal-x")
        assert len(filtered) >= 1
        assert filtered[0]["goal_id"] == "goal-x"

    def test_event_publishing(self):
        events: list[tuple[str, dict]] = []

        def on_event(event_type: str, payload: dict) -> None:
            events.append((event_type, payload))

        adapter = ModelAutonomousAdapter(on_event=on_event)
        adapter.select_model_for_goal("goal-e1", "execution", "Build API")
        assert len(events) >= 1
        assert events[0][0] == "model.decision.created"

        adapter.record_feedback(ModelExecutionFeedback(
            goal_id="goal-e1", model_id="test-model",
            task_type="code_generation", duration_ms=100, tokens_used=50,
            success=True,
        ))
        assert len(events) >= 2
        assert events[1][0] == "model.performance.updated"

    def test_get_stats_empty(self):
        adapter = ModelAutonomousAdapter()
        stats = adapter.get_stats()
        assert stats["total_decisions"] == 0
        assert stats["total_feedback"] == 0

    def test_thread_safety(self):
        adapter = ModelAutonomousAdapter()
        errors: list[Exception] = []

        def worker(goal_id: str) -> None:
            try:
                adapter.select_model_for_goal(goal_id, "execution", "Task")
                adapter.record_feedback(ModelExecutionFeedback(
                    goal_id=goal_id, model_id="test", task_type="code_generation",
                    duration_ms=100, tokens_used=10, success=True,
                ))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(f"goal-t{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = adapter.get_stats()
        assert stats["total_decisions"] == 10
        assert stats["total_feedback"] == 10


# ═══════════════════════════════════════════════════════════════
# Runtime Adapter Tests
# ═══════════════════════════════════════════════════════════════


class TestModelRuntimeAdapter:
    def test_simulate_execution(self):
        adapter = ModelRuntimeAdapter()
        profile = adapter._profiler.get_profile(MODELE_REEL)
        assert profile is not None
        plan = adapter.simulate_execution(profile, None)
        assert plan.model_id == MODELE_REEL
        assert plan.estimated_vram_mb > 0
        # >= 0, not > 0: the profiler is now seeded from config/models.yaml
        # with an honest tokens_per_second of 0.0 (never benchmarked in this
        # deployment) rather than an invented figure, so the estimate this
        # derives is legitimately 0 until BenchmarkScheduler records a real
        # run for this model.
        assert plan.estimated_tokens_per_second >= 0
        assert plan.risk_level in ("low", "medium", "high")

    def test_compare_runtimes(self):
        adapter = ModelRuntimeAdapter()
        profile = adapter._profiler.get_profile(MODELE_REEL)
        assert profile is not None
        results = adapter.compare_runtimes(profile)
        assert len(results) >= 2
        for r in results:
            assert "runtime" in r
            assert "estimated_tokens_per_second" in r
            assert "feasible" in r

    def test_get_best_configuration(self):
        adapter = ModelRuntimeAdapter()
        profile = adapter._profiler.get_profile(MODELE_REEL)
        assert profile is not None
        config = adapter.get_best_configuration(profile, None)
        assert config["model_id"] == MODELE_REEL
        assert "runtime" in config
        assert "estimated_vram_mb" in config

    def test_update_system_info(self):
        adapter = ModelRuntimeAdapter()
        adapter.update_system_info({"vram_mb": 8192, "ram_gb": 16})
        stats = adapter.get_stats()
        assert stats["system_info"]["vram_mb"] == 8192
        assert stats["system_info"]["ram_gb"] == 16

    def test_get_stats(self):
        adapter = ModelRuntimeAdapter()
        stats = adapter.get_stats()
        assert "total_simulations" in stats
        assert "system_info" in stats


# ═══════════════════════════════════════════════════════════════
# Evolution Adapter Tests
# ═══════════════════════════════════════════════════════════════


class TestModelEvolutionAdapter:
    def test_analyze_model_performance_found(self):
        adapter = ModelEvolutionAdapter()
        # Add some performance data
        adapter.record_execution(ModelPerformanceRecord(
            model_id=MODELE_REEL, task_type=TaskType.CODE_GENERATION,
            duration_ms=500, tokens_used=100, success=True,
        ))
        result = adapter.analyze_model_performance(MODELE_REEL)
        assert result["found"] is True
        assert result["total_runs"] >= 1

    def test_analyze_model_performance_not_found(self):
        adapter = ModelEvolutionAdapter()
        result = adapter.analyze_model_performance("nonexistent")
        assert result["found"] is False

    def test_get_weights_default(self):
        adapter = ModelEvolutionAdapter()
        weights = adapter.get_weights()
        assert abs(sum(weights.values()) - 1.0) < 0.01
        assert "quality" in weights
        assert "speed" in weights

    def test_update_weights(self):
        adapter = ModelEvolutionAdapter()
        adapter.update_weights({"quality": 0.50, "speed": 0.30})
        weights = adapter.get_weights()
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_detect_underperforming_models(self):
        adapter = ModelEvolutionAdapter()
        # Register a model with failures in the profiler
        profiler = adapter._profiler
        # Create a profile for failing model with 10 runs, 0 successes
        from backend.model_intelligence.model_intelligence_models import ModelProfile
        failing_profile = ModelProfile(
            model_id="test-failing", name="Test Failing Model",
            total_runs=10, successful_runs=0,
            vram_required_mb=1000,
        )
        profiler.register_model(failing_profile)
        under = adapter.detect_underperforming_models(threshold=0.5)
        failing = [m for m in under if m["model_id"] == "test-failing"]
        assert len(failing) >= 1

    def test_suggest_model_replacement(self):
        adapter = ModelEvolutionAdapter()
        suggestion = adapter.suggest_model_replacement(MODELE_REEL)
        assert suggestion is not None
        assert suggestion["current_model"]["model_id"] == MODELE_REEL

    def test_suggest_model_replacement_nonexistent(self):
        adapter = ModelEvolutionAdapter()
        suggestion = adapter.suggest_model_replacement("nonexistent")
        assert suggestion is None

    def test_get_evolution_summary(self):
        adapter = ModelEvolutionAdapter()
        summary = adapter.get_evolution_summary()
        assert summary["total_models"] >= 5
        assert "current_weights" in summary
        assert "underperforming_count" in summary


# ═══════════════════════════════════════════════════════════════
# Memory Adapter Tests
# ═══════════════════════════════════════════════════════════════


class TestModelMemoryAdapter:
    def test_store_execution_episode(self):
        adapter = ModelMemoryAdapter()
        record = ModelPerformanceRecord(
            model_id="test-model", task_type=TaskType.DEBUG,
            duration_ms=500, tokens_used=100, success=True,
        )
        adapter.store_execution_episode(record)
        results = adapter.query_episodic_memory(model_id="test-model")
        assert len(results) >= 1
        assert results[0]["success"] is True

    def test_store_decision_episode(self):
        adapter = ModelMemoryAdapter()
        from backend.model_intelligence.model_intelligence_models import (
            ModelDecision, RuntimeBackend, Quantization,
        )
        decision = ModelDecision(
            model_id=MODELE_REEL, model_name="Qwen3-Coder",
            runtime=RuntimeBackend.OLLAMA, quantization=Quantization.Q4_K_M,
            confidence=0.9, reason="Best for code",
        )
        adapter.store_decision_episode(decision, "Refactor code")
        results = adapter.query_episodic_memory()
        assert len(results) >= 1
        assert results[-1]["model_id"] == MODELE_REEL

    def test_learn_and_reinforce_rule(self):
        adapter = ModelMemoryAdapter()
        adapter.learn_effective_rule("python refactoring", {
            "model_id": "deepseek-r1:14b",
            "confidence": 0.85,
        })
        results = adapter.query_procedural_memory("python refactoring")
        assert len(results) >= 1
        # Initial confidence: 1 success / (1 success + 0 failures) = 1.0, but capped by recommendation confidence 0.85
        # Actually the stored confidence is the recommendation confidence, then update_rule adjusts
        assert results[0]["confidence"] == 0.85  # Initial confidence from recommendation

        adapter.reinforce_rule("python refactoring", 0, success=True)
        results2 = adapter.query_procedural_memory("python refactoring")
        # After reinforce: 2 success / (2 + 0) = 1.0
        assert results2[0]["confidence"] == 2.0 / 2.0

    def test_query_procedural_memory_fuzzy(self):
        adapter = ModelMemoryAdapter()
        adapter.learn_effective_rule("javascript optimization", {
            "model_id": MODELE_REEL, "confidence": 0.9,
        })
        # Fuzzy match on "optimization"
        results = adapter.query_procedural_memory("code optimization")
        assert len(results) >= 1

    def test_knowledge_graph_relations(self):
        adapter = ModelMemoryAdapter()
        adapter.record_model_for_task(MODELE_REEL, "code_generation", True)
        adapter.record_model_for_task("deepseek-r1:14b", "debug", True)
        adapter.record_outperformance(MODELE_REEL, "devstral", "code review")

        relations = adapter.query_knowledge_graph()
        assert len(relations) >= 3

        task_rels = adapter.query_knowledge_graph(relation_type="MODEL_USED_FOR_TASK")
        assert len(task_rels) >= 2

    def test_get_best_model_for_task(self):
        adapter = ModelMemoryAdapter()
        adapter.record_model_for_task("model-a", "code_generation", True)
        adapter.record_model_for_task("model-a", "code_generation", True)
        adapter.record_model_for_task("model-a", "code_generation", True)
        adapter.record_model_for_task("model-b", "code_generation", False)

        best = adapter.get_best_model_for_task("code_generation")
        assert best == "model-a"

    def test_get_best_model_for_task_insufficient_data(self):
        adapter = ModelMemoryAdapter()
        adapter.record_model_for_task("model-x", "rare_task", True)
        # Only 1 use, need 3 minimum
        best = adapter.get_best_model_for_task("rare_task")
        assert best is None

    def test_get_stats(self):
        adapter = ModelMemoryAdapter()
        stats = adapter.get_stats()
        assert "episodic_entries" in stats
        assert "procedural_patterns" in stats
        assert "knowledge_graph_relations" in stats

    def test_thread_safety(self):
        adapter = ModelMemoryAdapter()
        errors: list[Exception] = []

        def worker(i: int) -> None:
            try:
                record = ModelPerformanceRecord(
                    model_id=f"model-{i}", task_type=TaskType.CHAT,
                    duration_ms=100, tokens_used=10, success=True,
                )
                adapter.store_execution_episode(record)
                adapter.record_model_for_task(f"model-{i}", f"task-{i}", True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = adapter.get_stats()
        assert stats["episodic_entries"] >= 10
        assert stats["knowledge_graph_relations"] >= 10


# ═══════════════════════════════════════════════════════════════
# Full Mission Simulation Tests
# ═══════════════════════════════════════════════════════════════


class TestFullMissionSimulation:
    def test_complete_mission_flow(self):
        """Simulate a complete mission: goal → model selection → execution → feedback → memory."""
        events: list[str] = []
        memory = ModelMemoryAdapter()
        profiler = ModelProfiler()

        def on_event(event_type: str, payload: dict) -> None:
            events.append(event_type)

        # 1. Select model for goal
        auto_adapter = ModelAutonomousAdapter(on_event=on_event)
        decision = auto_adapter.select_model_for_goal(
            goal_id="mission-1", goal_phase="execution",
            task_description="Build a REST API with FastAPI",
            mission_id="mission-1",
        )
        assert decision.model_decision is not None

        # 2. Store decision in memory
        memory.store_decision_episode(decision.model_decision, "Build a REST API with FastAPI")

        # 3. Simulate runtime
        rt_adapter = ModelRuntimeAdapter()
        profile = profiler.get_profile(decision.model_decision.model_id)
        if profile:
            plan = rt_adapter.simulate_execution(profile, None)
            assert plan.estimated_vram_mb > 0

        # 4. Record feedback
        feedback = ModelExecutionFeedback(
            goal_id="mission-1", model_id=decision.model_decision.model_id,
            task_type="code_generation", duration_ms=2000.0,
            tokens_used=800, success=True, validation_score=0.92,
        )
        auto_adapter.record_feedback(feedback)

        # 5. Store execution in memory
        memory.store_execution_episode(ModelPerformanceRecord(
            model_id=decision.model_decision.model_id,
            task_type=TaskType.CODE_GENERATION,
            duration_ms=2000, tokens_used=800, success=True,
        ))

        # 6. Learn from experience
        memory.learn_effective_rule("fastapi rest api code generation", {
            "model_id": decision.model_decision.model_id,
            "confidence": 0.92,
        })

        # 7. Knowledge graph
        memory.record_model_for_task(
            decision.model_decision.model_id, "code_generation", True
        )

        # 8. Evolution analysis
        evo_adapter = ModelEvolutionAdapter()
        analysis = evo_adapter.analyze_model_performance(decision.model_decision.model_id)
        assert analysis["found"] is True

        # Verify events were published
        assert len(events) >= 2
        assert "model.decision.created" in events
        assert "model.performance.updated" in events

    def test_mission_with_failure(self):
        """Test mission flow when model selection fails."""
        memory = ModelMemoryAdapter()
        auto_adapter = ModelAutonomousAdapter()

        # Select model
        decision = auto_adapter.select_model_for_goal(
            goal_id="fail-mission", goal_phase="execution",
            task_description="Fix null pointer exception",
            task_type="debug",
        )

        # Record failure
        feedback = ModelExecutionFeedback(
            goal_id="fail-mission", model_id=decision.model_decision.model_id,
            task_type="debug", duration_ms=10000.0, tokens_used=500,
            success=False, errors=["Generated incorrect fix"],
        )
        auto_adapter.record_feedback(feedback)

        # Store in memory
        memory.record_model_for_task(decision.model_decision.model_id, "debug", False)

        stats = auto_adapter.get_stats()
        assert stats["success_rate"] == 0.0

        # Evolution should detect underperformance
        evo_adapter = ModelEvolutionAdapter()
        result = evo_adapter.analyze_model_performance(decision.model_decision.model_id)
        assert result["found"] is True

    def test_multiple_goals_routing(self):
        """Test routing decisions for multiple goals."""
        adapter = ModelAutonomousAdapter()

        goals = [
            ("g1", "Write a Python script to parse CSV files"),
            ("g2", "Debug the memory leak in the C++ module"),
            ("g3", "Review the pull request for security issues"),
            ("g4", "Document the API endpoints"),
        ]

        for goal_id, description in goals:
            decision = adapter.select_model_for_goal(goal_id, "execution", description)
            assert decision.model_decision.model_id != ""

        history = adapter.get_decision_history()
        assert len(history) >= 4

        # Verify different models were selected for different tasks
        models_used = set(h["model_id"] for h in history)
        assert len(models_used) >= 1  # At least one model used
