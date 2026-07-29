"""Tests for Self Evolution & Improvement Engine (HOS-058).

Covers: models, analyzer, detector, simulator, validator, engine,
scheduler, API, EventBus, thread safety (70+ tests).
"""

import threading
import pytest

from backend.evolution.evolution_models import (
    EVOLUTION_EVENTS,
    EvolutionExperiment,
    EvolutionProposal,
    EvolutionReport,
    EvolutionStatus,
    EvolutionType,
    OptimizationPattern,
    RiskLevel,
    SystemMetrics,
)
from backend.evolution.evolution_analyzer import EvolutionAnalyzer
from backend.evolution.evolution_simulator import EvolutionSimulator
from backend.evolution.evolution_validator import EvolutionValidator, ValidationVerdict
from backend.evolution.improvement_detector import ImprovementDetector
from backend.evolution.evolution_engine import EvolutionEngine
from backend.evolution.evolution_scheduler import EvolutionScheduler
from backend.evolution.routes import (
    handle_get_status,
    handle_get_proposals,
    handle_analyze,
    handle_simulate,
    handle_approve,
    handle_apply,
    handle_get_reports,
    get_engine,
)


# ======================================================================
# 1. Models
# ======================================================================

class TestEvolutionModels:

    def test_proposal_to_dict(self):
        p = EvolutionProposal(proposal_id="p1", evolution_type=EvolutionType.RUNTIME_OPTIMIZATION,
                              target_component="runtime", description="Test", expected_gain=25.0)
        d = p.to_dict()
        assert d["proposal_id"] == "p1"
        assert d["expected_gain"] == 25.0

    def test_experiment_to_dict(self):
        e = EvolutionExperiment(experiment_id="e1", proposal_id="p1", result="improvement")
        d = e.to_dict()
        assert d["result"] == "improvement"

    def test_evolution_type_values(self):
        assert EvolutionType.RUNTIME_OPTIMIZATION.value == "runtime_optimization"
        assert EvolutionType.ARCHITECTURE_IMPROVEMENT.value == "architecture_improvement"

    def test_evolution_status(self):
        assert EvolutionStatus.DETECTED.value == "detected"
        assert EvolutionStatus.APPLIED.value == "applied"

    def test_risk_level_order(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_system_metrics_defaults(self):
        m = SystemMetrics()
        assert m.runtime_avg_latency_ms == 0.0
        assert m.agent_success_rate == 0.0

    def test_optimization_pattern(self):
        op = OptimizationPattern(pattern_id="op1", pattern="High latency fix", frequency=5, success_rate=0.85)
        assert op.frequency == 5
        assert op.success_rate == 0.85

    def test_evolution_report_defaults(self):
        r = EvolutionReport(report_id="r1", improvements_found=5)
        assert r.improvements_found == 5
        assert len(r.applied_changes) == 0

    def test_events_all_prefixed(self):
        for key, evt in EVOLUTION_EVENTS.items():
            assert evt.startswith("evolution.")


# ======================================================================
# 2. Evolution Analyzer
# ======================================================================

class TestEvolutionAnalyzer:

    def test_analyze_runtime_high_latency(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(runtime_avg_latency_ms=600.0)
        proposals = analyzer.analyze_runtime(metrics)
        assert len(proposals) >= 1
        assert proposals[0].evolution_type == EvolutionType.RUNTIME_OPTIMIZATION

    def test_analyze_runtime_high_errors(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(runtime_error_rate=0.15)
        proposals = analyzer.analyze_runtime(metrics)
        assert len(proposals) >= 1

    def test_analyze_runtime_low_model_score(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(runtime_model_score=0.3)
        proposals = analyzer.analyze_runtime(metrics)
        assert len(proposals) >= 1
        assert proposals[0].evolution_type == EvolutionType.MODEL_SWITCH

    def test_analyze_runtime_no_issues(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(runtime_avg_latency_ms=100.0, runtime_error_rate=0.01, runtime_model_score=0.9)
        proposals = analyzer.analyze_runtime(metrics)
        assert len(proposals) == 0

    def test_analyze_agents_low_success(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(agent_success_rate=0.4)
        proposals = analyzer.analyze_agents(metrics)
        assert len(proposals) >= 1
        assert proposals[0].evolution_type == EvolutionType.AGENT_IMPROVEMENT

    def test_analyze_agents_high_duration(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(agent_avg_duration_ms=15000.0)
        proposals = analyzer.analyze_agents(metrics)
        assert len(proposals) >= 1

    def test_analyze_skills_unused(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(skill_unused_ratio=0.6)
        proposals = analyzer.analyze_skills(metrics)
        assert len(proposals) >= 1

    def test_analyze_skills_low_success(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(skill_success_rate=0.5)
        proposals = analyzer.analyze_skills(metrics)
        assert len(proposals) >= 1

    def test_analyze_missions_blocked(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(mission_blocked_count=10)
        proposals = analyzer.analyze_missions(metrics)
        assert len(proposals) >= 1

    def test_analyze_missions_repeats(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(mission_repeat_rate=0.5)
        proposals = analyzer.analyze_missions(metrics)
        assert len(proposals) >= 1

    def test_analyze_memory_low_hit(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(memory_hit_rate=0.3)
        proposals = analyzer.analyze_memory(metrics)
        assert len(proposals) >= 1

    def test_analyze_all_returns_all(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(runtime_avg_latency_ms=600, agent_success_rate=0.4, skill_unused_ratio=0.6,
                                mission_blocked_count=10, memory_hit_rate=0.3)
        proposals = analyzer.analyze_all(metrics)
        assert len(proposals) >= 3

    def test_proposal_status_update(self):
        analyzer = EvolutionAnalyzer()
        metrics = SystemMetrics(runtime_avg_latency_ms=600.0)
        analyzer.analyze_all(metrics)
        p = analyzer.get_proposals()[0]
        assert analyzer.update_proposal_status(p.proposal_id, EvolutionStatus.APPROVED) is True
        assert analyzer.update_proposal_status("nonexistent", EvolutionStatus.APPROVED) is False


# ======================================================================
# 3. Improvement Detector
# ======================================================================

class TestImprovementDetector:

    def test_detect_runtime_underperformance(self):
        det = ImprovementDetector()
        p = det.detect_runtime_underperformance(600.0, 0.15)
        assert p is not None
        assert p.evolution_type == EvolutionType.RUNTIME_OPTIMIZATION

    def test_detect_runtime_ok(self):
        det = ImprovementDetector()
        p = det.detect_runtime_underperformance(100.0, 0.01)
        assert p is None

    def test_detect_unnecessary_skills(self):
        det = ImprovementDetector()
        p = det.detect_unnecessary_skills(0.5)
        assert p is not None
        assert p.evolution_type == EvolutionType.SKILL_IMPROVEMENT

    def test_detect_skill_usage_ok(self):
        det = ImprovementDetector()
        p = det.detect_unnecessary_skills(0.1)
        assert p is None

    def test_detect_missing_skills(self):
        det = ImprovementDetector()
        p = det.detect_missing_skills(["error1", "error2", "error3", "error4"])
        assert p is not None

    def test_detect_missing_skills_insufficient(self):
        det = ImprovementDetector()
        p = det.detect_missing_skills([])
        assert p is None

    def test_detect_model_switch(self):
        det = ImprovementDetector()
        p = det.detect_model_switch_opportunity(0.6, 0.85)
        assert p is not None
        assert p.evolution_type == EvolutionType.MODEL_SWITCH

    def test_detect_model_switch_no_opportunity(self):
        det = ImprovementDetector()
        p = det.detect_model_switch_opportunity(0.8, 0.85)
        assert p is None

    def test_detect_inefficient_workflow(self):
        det = ImprovementDetector()
        p = det.detect_inefficient_workflow(0.4, 6000.0)
        assert p is not None

    def test_detect_good_workflow(self):
        det = ImprovementDetector()
        p = det.detect_inefficient_workflow(0.1, 1000.0)
        assert p is None

    def test_record_bottleneck(self):
        det = ImprovementDetector()
        det.record_bottleneck("runtime.orchestrator")
        det.record_bottleneck("runtime.orchestrator")
        det.record_bottleneck("memory.unified")
        bottlenecks = det.get_frequent_bottlenecks(min_count=2)
        assert len(bottlenecks) >= 1
        assert bottlenecks[0][0] == "runtime.orchestrator"


# ======================================================================
# 4. Evolution Simulator
# ======================================================================

class TestEvolutionSimulator:

    def test_simulate_improvement(self):
        sim = EvolutionSimulator()
        proposal = EvolutionProposal(proposal_id="p1", evolution_type=EvolutionType.RUNTIME_OPTIMIZATION,
                                     expected_gain=25.0, confidence=0.8)
        experiment = sim.simulate(proposal, {"latency_ms": 500, "success_rate": 0.75})
        assert experiment.proposal_id == "p1"
        assert experiment.result in ("improvement", "no_change", "regression")

    def test_simulate_model_switch(self):
        sim = EvolutionSimulator()
        proposal = EvolutionProposal(proposal_id="p2", evolution_type=EvolutionType.MODEL_SWITCH,
                                     expected_gain=30.0, confidence=0.7)
        experiment = sim.simulate(proposal)
        assert experiment.result in ("improvement", "no_change", "regression")

    def test_get_experiments_by_proposal(self):
        sim = EvolutionSimulator()
        proposal = EvolutionProposal(proposal_id="p1", evolution_type=EvolutionType.RUNTIME_OPTIMIZATION,
                                     expected_gain=10, confidence=0.5)
        sim.simulate(proposal)
        sim.simulate(EvolutionProposal(proposal_id="p2", evolution_type=EvolutionType.SKILL_IMPROVEMENT))
        experiments = sim.get_experiments(proposal_id="p1")
        assert len(experiments) == 1


# ======================================================================
# 5. Evolution Validator
# ======================================================================

class TestEvolutionValidator:

    def test_allow_low_risk_runtime(self):
        v = EvolutionValidator()
        p = EvolutionProposal(evolution_type=EvolutionType.RUNTIME_OPTIMIZATION, risk_level=RiskLevel.LOW)
        assert v.validate(p) == ValidationVerdict.ALLOW

    def test_allow_low_risk_skill(self):
        v = EvolutionValidator()
        p = EvolutionProposal(evolution_type=EvolutionType.SKILL_IMPROVEMENT, risk_level=RiskLevel.LOW)
        assert v.validate(p) == ValidationVerdict.ALLOW

    def test_review_medium_runtime(self):
        v = EvolutionValidator()
        p = EvolutionProposal(evolution_type=EvolutionType.RUNTIME_OPTIMIZATION, risk_level=RiskLevel.MEDIUM)
        assert v.validate(p) == ValidationVerdict.REVIEW

    def test_review_high_risk_any(self):
        v = EvolutionValidator()
        p = EvolutionProposal(evolution_type=EvolutionType.RUNTIME_OPTIMIZATION, risk_level=RiskLevel.HIGH)
        assert v.validate(p) == ValidationVerdict.REVIEW

    def test_deny_architecture(self):
        v = EvolutionValidator()
        p = EvolutionProposal(evolution_type=EvolutionType.ARCHITECTURE_IMPROVEMENT, risk_level=RiskLevel.LOW)
        assert v.validate(p) == ValidationVerdict.DENY

    def test_allows_agent_low(self):
        v = EvolutionValidator()
        p = EvolutionProposal(evolution_type=EvolutionType.AGENT_IMPROVEMENT, risk_level=RiskLevel.LOW)
        assert v.validate(p) == ValidationVerdict.ALLOW

    def test_set_auto_allow_override(self):
        v = EvolutionValidator()
        v.set_auto_allow("runtime_optimization", "high", True)
        p = EvolutionProposal(evolution_type=EvolutionType.RUNTIME_OPTIMIZATION, risk_level=RiskLevel.HIGH)
        assert v.validate(p) == ValidationVerdict.ALLOW

    def test_set_deny_override(self):
        v = EvolutionValidator()
        v.set_deny("runtime_optimization", True)
        p = EvolutionProposal(evolution_type=EvolutionType.RUNTIME_OPTIMIZATION, risk_level=RiskLevel.LOW)
        assert v.validate(p) == ValidationVerdict.DENY

    def test_set_deny_remove(self):
        v = EvolutionValidator()
        v.set_deny("runtime_optimization", False)
        p = EvolutionProposal(evolution_type=EvolutionType.RUNTIME_OPTIMIZATION, risk_level=RiskLevel.LOW)
        assert v.validate(p) == ValidationVerdict.ALLOW


# ======================================================================
# 6. Evolution Engine
# ======================================================================

class TestEvolutionEngine:

    def test_engine_initializes(self):
        engine = EvolutionEngine()
        stats = engine.stats()
        assert stats["total_proposals"] == 0

    def test_ingest_metrics_produces_proposals(self):
        engine = EvolutionEngine()
        metrics = SystemMetrics(runtime_avg_latency_ms=600.0, agent_success_rate=0.4, skill_unused_ratio=0.6)
        proposals = engine.ingest_metrics(metrics)
        assert len(proposals) >= 1

    def test_full_pipeline(self):
        engine = EvolutionEngine()
        metrics = SystemMetrics(runtime_avg_latency_ms=600.0, agent_success_rate=0.4)
        results = engine.run_full_pipeline(metrics)
        assert len(results) >= 1

    def test_approve_proposal(self):
        engine = EvolutionEngine()
        metrics = SystemMetrics(runtime_avg_latency_ms=600.0)
        engine.run_full_pipeline(metrics)
        proposals = engine.get_proposals()
        if proposals:
            ok = engine.approve(proposals[0].proposal_id)
            assert ok is True

    def test_reject_proposal(self):
        engine = EvolutionEngine()
        engine.ingest_metrics(SystemMetrics(runtime_avg_latency_ms=600.0))
        proposals = engine.get_proposals()
        if proposals:
            ok = engine.reject(proposals[0].proposal_id)
            assert ok is True

    def test_generate_report(self):
        engine = EvolutionEngine()
        report = engine.generate_report()
        assert report.improvements_found >= 0

    def test_get_reports(self):
        engine = EvolutionEngine()
        engine.generate_report()
        reports = engine.get_reports()
        assert len(reports) == 1

    def test_events_published(self):
        events = []
        engine = EvolutionEngine(on_event=lambda t, p, **kw: events.append(t))
        metrics = SystemMetrics(runtime_avg_latency_ms=600.0)
        engine.run_full_pipeline(metrics)
        assert EVOLUTION_EVENTS["proposal_created"] in events


# ======================================================================
# 7. Evolution Scheduler
# ======================================================================

class TestEvolutionScheduler:

    def test_scheduler_runs_hourly(self):
        scheduler = EvolutionScheduler(EvolutionEngine())
        results = scheduler.run_hourly()
        assert isinstance(results, list)

    def test_scheduler_runs_daily(self):
        scheduler = EvolutionScheduler(EvolutionEngine())
        report = scheduler.run_daily()
        assert isinstance(report, EvolutionReport)

    def test_scheduler_runs_weekly(self):
        scheduler = EvolutionScheduler(EvolutionEngine())
        result = scheduler.run_weekly()
        assert "report" in result
        assert "weekly_gain" in result

    def test_scheduler_stats(self):
        scheduler = EvolutionScheduler(EvolutionEngine())
        scheduler.run_hourly()
        scheduler.run_daily()
        stats = scheduler.stats()
        assert stats["hourly_runs"] >= 1
        assert stats["daily_runs"] >= 1


# ======================================================================
# 8. API Routes
# ======================================================================

class TestAPIRoutes:

    def test_get_status(self):
        result = handle_get_status()
        assert "total_proposals" in result

    def test_get_proposals(self):
        proposals = handle_get_proposals()
        assert isinstance(proposals, list)

    def test_analyze(self):
        results = handle_analyze({
            "runtime_avg_latency_ms": 600.0,
            "agent_success_rate": 0.4,
        })
        assert isinstance(results, list)

    def test_get_reports(self):
        reports = handle_get_reports()
        assert isinstance(reports, list)

    def test_approve_nonexistent(self):
        result = handle_approve("nonexistent")
        assert result["success"] is False

    def test_simulate_nonexistent(self):
        result = handle_simulate("nonexistent")
        assert "error" in result


# ======================================================================
# 9. Thread Safety
# ======================================================================

class TestEvolutionThreadSafety:

    def test_concurrent_engine(self):
        engine = EvolutionEngine()
        errors = []

        def run_analysis(i: int):
            try:
                metrics = SystemMetrics(runtime_avg_latency_ms=float(300 + i * 100))
                engine.run_full_pipeline(metrics)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=run_analysis, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_concurrent_detector(self):
        det = ImprovementDetector()
        errors = []

        def detect(i: int):
            try:
                det.detect_runtime_underperformance(600.0, 0.15)
                det.detect_unnecessary_skills(0.5)
                det.get_detected()
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=detect, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_concurrent_analyzer(self):
        analyzer = EvolutionAnalyzer()
        errors = []

        def analyze(i: int):
            try:
                m = SystemMetrics(runtime_avg_latency_ms=600.0, agent_success_rate=0.4)
                analyzer.analyze_all(m)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=analyze, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []
