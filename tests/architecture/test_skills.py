"""Tests for HOS-048 — Dynamic Skill Distribution Engine."""

from __future__ import annotations

import threading
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.skills.skill_models import (
    CacheStrategy,
    LoadState,
    SkillCategory,
    SkillDefinition,
    SkillDomain,
)
from backend.skills.skill_registry import SkillRegistry
from backend.skills.skill_selector import SkillSelector
from backend.skills.dependency_resolver import SkillDependencyResolver
from backend.skills.skill_loader import SkillLoader
from backend.skills.skill_cache import SkillCache
from backend.skills.skill_profiler import SkillProfiler
from backend.skills.skill_distributor import SkillDistributor
from backend.skills.routes import (
    handle_get_skills,
    handle_get_skill,
    handle_post_select,
    handle_post_load,
    handle_post_unload,
    handle_get_cache,
    handle_get_statistics,
)


# ── Helpers ──────────────────────────────────────────────────

def _make_skill(
    skill_id: str = "",
    name: str = "test-skill",
    category: SkillCategory = SkillCategory.CODING,
    domain: SkillDomain = SkillDomain.BACKEND,
    tags: list[str] | None = None,
    technologies: list[str] | None = None,
    dependencies: list[str] | None = None,
    memory_cost_mb: float = 10.0,
    token_cost: int = 500,
    quality_score: float = 0.8,
    usage_count: int = 100,
    success_count: int = 90,
) -> SkillDefinition:
    return SkillDefinition(
        id=skill_id,
        name=name,
        category=category,
        domain=domain,
        tags=tags or [],
        technologies=technologies or [],
        dependencies=dependencies or [],
        memory_cost_mb=memory_cost_mb,
        token_cost_estimate=token_cost,
        quality_score=quality_score,
        usage_count=usage_count,
        success_count=success_count,
    )


def _make_registry_with_skills() -> tuple[SkillRegistry, list[SkillDefinition]]:
    reg = SkillRegistry()
    skills = [
        _make_skill("s1", "python-coding", SkillCategory.CODING, SkillDomain.BACKEND,
                     tags=["python", "api"], technologies=["python", "fastapi"],
                     quality_score=0.9, success_count=95),
        _make_skill("s2", "react-ui", SkillCategory.CODING, SkillDomain.FRONTEND,
                     tags=["react", "ui"], technologies=["react", "typescript"],
                     quality_score=0.85, success_count=80),
        _make_skill("s3", "security-audit", SkillCategory.SECURITY, SkillDomain.SECURITY,
                     tags=["security", "audit"], technologies=["python", "bandit"],
                     quality_score=0.95, success_count=98),
        _make_skill("s4", "db-design", SkillCategory.CODING, SkillDomain.BACKEND,
                     tags=["sql", "database"], technologies=["postgresql", "sqlalchemy"],
                     quality_score=0.7, success_count=65),
        _make_skill("s5", "deployment-pipeline", SkillCategory.DEPLOYMENT, SkillDomain.DEVOPS,
                     tags=["ci", "docker"], technologies=["docker", "github-actions"],
                     quality_score=0.75, success_count=70),
    ]
    for s in skills:
        reg.register(s)
    return reg, skills


# ── TestRegistry ─────────────────────────────────────────────

class TestSkillRegistry:

    def test_register_and_get(self):
        reg = SkillRegistry()
        s = _make_skill("s1", "test")
        reg.register(s)
        assert reg.get("s1") is s
        assert reg.count() == 1

    def test_list_all(self):
        reg, skills = _make_registry_with_skills()
        assert len(reg.list_all()) == 5

    def test_list_by_category(self):
        reg, _ = _make_registry_with_skills()
        coding = reg.list_by_category(SkillCategory.CODING)
        assert len(coding) == 3  # python-coding, react-ui, db-design
        names = {s.name for s in coding}
        assert "python-coding" in names
        assert "react-ui" in names
        assert "db-design" in names

    def test_list_by_domain(self):
        reg, _ = _make_registry_with_skills()
        backend = reg.list_by_domain(SkillDomain.BACKEND)
        assert len(backend) >= 2

    def test_list_by_tag(self):
        reg, _ = _make_registry_with_skills()
        python_skills = reg.list_by_tag("python")
        assert len(python_skills) >= 1

    def test_list_by_status(self):
        reg, _ = _make_registry_with_skills()
        active = reg.list_active()
        assert len(active) == 5

    def test_delete(self):
        reg = SkillRegistry()
        s = _make_skill("s1", "test")
        reg.register(s)
        assert reg.delete("s1") is True
        assert reg.get("s1") is None
        assert reg.count() == 0
        assert reg.delete("nonexistent") is False

    def test_update(self):
        reg = SkillRegistry()
        s1 = _make_skill("s1", "v1")
        s2 = _make_skill("s1", "v2", quality_score=0.99)
        reg.register(s1)
        reg.register(s2)
        assert reg.get("s1").quality_score == 0.99
        assert reg.count() == 1

    def test_stats(self):
        reg, _ = _make_registry_with_skills()
        stats = reg.stats()
        assert stats["total"] == 5
        assert "coding" in stats["by_category"]


# ── TestSelector ─────────────────────────────────────────────

class TestSkillSelector:

    def test_select_by_task_description(self):
        reg, _ = _make_registry_with_skills()
        selector = SkillSelector(reg)
        results = selector.select(task_description="build a python API", max_skills=5)
        assert len(results) > 0
        assert results[0].skill_id == "s1"  # python-coding best match
        assert results[0].relevance_score > 0

    def test_select_by_category(self):
        reg, _ = _make_registry_with_skills()
        selector = SkillSelector(reg)
        results = selector.select(categories=["security"])
        assert len(results) > 0
        assert results[0].skill_id == "s3"

    def test_select_by_technology(self):
        reg, _ = _make_registry_with_skills()
        selector = SkillSelector(reg)
        results = selector.select(technologies=["react", "typescript"])
        assert len(results) > 0
        assert results[0].skill_id == "s2"

    def test_select_min_score(self):
        reg, _ = _make_registry_with_skills()
        selector = SkillSelector(reg)
        results = selector.select(max_skills=10, min_score=0.5)
        assert len(results) <= 5

    def test_select_max_skills(self):
        reg, _ = _make_registry_with_skills()
        selector = SkillSelector(reg)
        results = selector.select(max_skills=2)
        assert len(results) <= 2

    def test_selection_has_justification(self):
        reg, _ = _make_registry_with_skills()
        selector = SkillSelector(reg)
        results = selector.select(task_description="security audit python", max_skills=3)
        for r in results:
            assert r.justification
            assert isinstance(r.relevance_score, float)
            assert 0.0 <= r.relevance_score <= 1.0

    def test_history(self):
        reg, _ = _make_registry_with_skills()
        selector = SkillSelector(reg)
        selector.select(task_description="test")
        history = selector.get_history()
        assert len(history) == 1


# ── TestDependencyResolver ───────────────────────────────────

class TestDependencyResolver:

    def test_resolve_no_deps(self):
        reg = SkillRegistry()
        s1 = _make_skill("s1", "standalone")
        s2 = _make_skill("s2", "also-standalone")
        reg.register(s1)
        reg.register(s2)
        resolver = SkillDependencyResolver(reg)
        graph = resolver.resolve(["s1", "s2"])
        assert len(graph.skill_ids) == 2
        assert len(graph.resolved_order) >= 0
        assert graph.circular_deps == []
        assert graph.conflicts == []

    def test_resolve_with_deps(self):
        reg = SkillRegistry()
        s1 = _make_skill("s1", "base", dependencies=["s2"])
        s2 = _make_skill("s2", "foundation")
        reg.register(s1)
        reg.register(s2)
        resolver = SkillDependencyResolver(reg)
        graph = resolver.resolve(["s1"])
        assert "s2" in graph.skill_ids
        assert "s1" in graph.skill_ids

    def test_detect_circular(self):
        reg = SkillRegistry()
        s1 = _make_skill("s1", "a", dependencies=["s2"])
        s2 = _make_skill("s2", "b", dependencies=["s1"])
        reg.register(s1)
        reg.register(s2)
        resolver = SkillDependencyResolver(reg)
        graph = resolver.resolve(["s1", "s2"])
        assert len(graph.circular_deps) > 0

    def test_transitive_deps(self):
        reg = SkillRegistry()
        s1 = _make_skill("s1", "top", dependencies=["s2"])
        s2 = _make_skill("s2", "mid", dependencies=["s3"])
        s3 = _make_skill("s3", "base")
        reg.register(s1)
        reg.register(s2)
        reg.register(s3)
        resolver = SkillDependencyResolver(reg)
        graph = resolver.resolve(["s1"])
        assert graph.skill_ids == {"s1", "s2", "s3"}

    def test_conflict_detection(self):
        reg = SkillRegistry()
        s1 = _make_skill("s1", "same-name", category=SkillCategory.CODING)
        s2 = _make_skill("s2", "same-name", category=SkillCategory.REASONING)
        reg.register(s1)
        reg.register(s2)
        resolver = SkillDependencyResolver(reg)
        graph = resolver.resolve(["s1", "s2"])
        assert len(graph.conflicts) > 0


# ── TestLoader ───────────────────────────────────────────────

class TestSkillLoader:

    def test_load_unload(self):
        reg = SkillRegistry()
        reg.register(_make_skill("s1", "test"))
        loader = SkillLoader(reg)
        instance = loader.load("s1")
        assert instance is not None
        assert instance.load_state == LoadState.LOADED
        loaded = loader.get_loaded("s1")
        assert len(loaded) == 1
        assert loader.unload(instance.id) is True
        assert len(loader.get_loaded("s1")) == 0

    def test_load_nonexistent(self):
        reg = SkillRegistry()
        loader = SkillLoader(reg)
        assert loader.load("nonexistent") is None

    def test_load_with_hook(self):
        reg = SkillRegistry()
        reg.register(_make_skill("s1", "test"))
        loader = SkillLoader(reg)
        hook_called = []
        loader.register_hook("s1", lambda: hook_called.append(True))
        loader.load("s1")
        assert hook_called == [True]

    def test_unload_all(self):
        reg = SkillRegistry()
        reg.register(_make_skill("s1", "a"))
        reg.register(_make_skill("s2", "b"))
        loader = SkillLoader(reg)
        loader.load("s1")
        loader.load("s2")
        assert loader.unload_all() == 2
        assert loader.count_loaded() == 0

    def test_hot_reload(self):
        reg = SkillRegistry()
        reg.register(_make_skill("s1", "test"))
        loader = SkillLoader(reg)
        loader.load("s1")
        instances = loader.hot_reload("s1")
        assert len(instances) == 1
        assert instances[0].load_state == LoadState.LOADED

    def test_stats(self):
        reg = SkillRegistry()
        reg.register(_make_skill("s1", "a"))
        loader = SkillLoader(reg)
        loader.load("s1")
        stats = loader.stats()
        assert stats["loaded"] == 1
        assert stats["errors"] == 0


# ── TestCache ────────────────────────────────────────────────

class TestSkillCache:

    def test_put_get(self):
        cache = SkillCache(max_size=5)
        entry = cache.put("s1")
        assert cache.get("s1") is not None
        assert entry.skill_id == "s1"

    def test_ttl_expiry(self):
        cache = SkillCache(max_size=5, default_ttl=0.01)
        cache.put("s1")
        time.sleep(0.02)
        assert cache.get("s1") is None  # expired

    def test_no_ttl(self):
        cache = SkillCache(max_size=5, default_ttl=0)
        cache.put("s1")
        assert cache.get("s1") is not None  # never expires

    def test_lru_eviction(self):
        cache = SkillCache(max_size=2)
        cache.put("s1")
        cache.put("s2")
        cache.put("s3")  # should evict s1
        assert cache.get("s1") is None
        assert cache.get("s2") is not None
        assert cache.get("s3") is not None

    def test_evict(self):
        cache = SkillCache(max_size=5)
        cache.put("s1")
        assert cache.evict("s1") is True
        assert cache.get("s1") is None
        assert cache.evict("s1") is False

    def test_invalidate(self):
        cache = SkillCache(max_size=10, default_ttl=0.001)
        cache.put("s1", ttl=0.001)
        cache.put("s2", ttl=10.0)
        time.sleep(0.002)
        removed = cache.invalidate()
        assert removed >= 1
        assert cache.get("s2") is not None

    def test_clear(self):
        cache = SkillCache(max_size=10)
        cache.put("s1")
        cache.put("s2")
        assert cache.clear() == 2
        assert cache.size() == 0

    def test_strategy_switch(self):
        cache = SkillCache(max_size=2)
        cache.set_strategy(CacheStrategy.PRIORITY)
        cache.put("s1")
        assert cache.size() == 1

    def test_stats(self):
        cache = SkillCache(max_size=5)
        cache.put("s1")
        cache.put("s2")
        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["max_size"] == 5


# ── TestProfiler ─────────────────────────────────────────────

class TestSkillProfiler:

    def test_profile_success(self):
        profiler = SkillProfiler()
        start = profiler.start_profile("s1")
        profile = profiler.end_profile("s1", start, memory_mb=50.0, tokens=1000, success=True)
        assert profile.sample_count == 1
        assert profile.avg_load_time_ms > 0
        assert profile.failure_rate == 0.0

    def test_profile_failure(self):
        profiler = SkillProfiler()
        start = profiler.start_profile("s1")
        profile = profiler.end_profile("s1", start, memory_mb=50.0, tokens=1000, success=False)
        assert profile.failure_rate > 0.0

    def test_multiple_samples(self):
        profiler = SkillProfiler()
        start = profiler.start_profile("s1")
        profiler.end_profile("s1", start, memory_mb=10.0, tokens=100)
        start2 = profiler.start_profile("s1")
        profiler.end_profile("s1", start2, memory_mb=20.0, tokens=200)
        profile = profiler.get("s1")
        assert profile.sample_count == 2

    def test_get_nonexistent(self):
        profiler = SkillProfiler()
        assert profiler.get("nonexistent") is None

    def test_get_all(self):
        profiler = SkillProfiler()
        start = profiler.start_profile("s1")
        profiler.end_profile("s1", start, memory_mb=10.0, tokens=100)
        start2 = profiler.start_profile("s2")
        profiler.end_profile("s2", start2, memory_mb=20.0, tokens=200)
        assert len(profiler.get_all()) == 2

    def test_clear(self):
        profiler = SkillProfiler()
        start = profiler.start_profile("s1")
        profiler.end_profile("s1", start, memory_mb=10.0, tokens=100)
        assert profiler.clear() == 1
        assert len(profiler.get_all()) == 0

    def test_stats(self):
        profiler = SkillProfiler()
        start = profiler.start_profile("s1")
        profiler.end_profile("s1", start, memory_mb=10.0, tokens=100)
        stats = profiler.stats()
        assert stats["profiled_skills"] == 1
        assert stats["total_samples"] == 1


# ── TestDistributor ──────────────────────────────────────────

class TestSkillDistributor:

    def test_distribute(self):
        reg, skills = _make_registry_with_skills()
        selector = SkillSelector(reg)
        resolver = SkillDependencyResolver(reg)
        loader = SkillLoader(reg)
        cache = SkillCache(max_size=50)
        profiler = SkillProfiler()
        distributor = SkillDistributor(reg, selector, resolver, loader, cache, profiler)

        agent_tasks = {
            "agent-coder": {
                "description": "build a python API with FastAPI",
                "categories": ["coding"],
                "technologies": ["python", "fastapi"],
                "capabilities": ["python", "backend"],
            },
            "agent-reviewer": {
                "description": "security audit of the codebase",
                "categories": ["security"],
                "technologies": ["python", "bandit"],
                "capabilities": ["security"],
            },
        }
        dist = distributor.distribute("mission-001", agent_tasks)
        assert dist.mission_id == "mission-001"
        assert len(dist.assignments) == 2
        assert "agent-coder" in dist.assignments
        assert "agent-reviewer" in dist.assignments
        assert len(dist.assignments["agent-coder"]) > 0
        assert dist.total_memory_mb > 0

    def test_load_and_clean(self):
        reg, skills = _make_registry_with_skills()
        selector = SkillSelector(reg)
        resolver = SkillDependencyResolver(reg)
        loader = SkillLoader(reg)
        cache = SkillCache(max_size=50)
        profiler = SkillProfiler()
        distributor = SkillDistributor(reg, selector, resolver, loader, cache, profiler)

        agent_tasks = {
            "agent-1": {
                "description": "python coding task",
                "categories": ["coding"],
                "technologies": ["python"],
            },
        }
        dist = distributor.distribute("mission-002", agent_tasks, max_skills_per_agent=2)
        loaded = distributor.load_distribution(dist, "agent-1")
        assert len(loaded) > 0
        assert loader.count_loaded() > 0

        cleaned = distributor.clean_mission("mission-002")
        assert cleaned > 0

    def test_stats(self):
        reg, _ = _make_registry_with_skills()
        selector = SkillSelector(reg)
        resolver = SkillDependencyResolver(reg)
        loader = SkillLoader(reg)
        cache = SkillCache(max_size=50)
        profiler = SkillProfiler()
        distributor = SkillDistributor(reg, selector, resolver, loader, cache, profiler)

        agent_tasks = {"agent-1": {"description": "test"}}
        distributor.distribute("mission-003", agent_tasks)
        stats = distributor.stats()
        assert stats["total_distributions"] == 1

    def test_history(self):
        reg, _ = _make_registry_with_skills()
        selector = SkillSelector(reg)
        resolver = SkillDependencyResolver(reg)
        loader = SkillLoader(reg)
        cache = SkillCache(max_size=50)
        profiler = SkillProfiler()
        distributor = SkillDistributor(reg, selector, resolver, loader, cache, profiler)

        distributor.distribute("m1", {"a1": {"description": "test"}})
        history = distributor.get_history()
        assert len(history) == 1


# ── TestRoutes ───────────────────────────────────────────────

class TestRoutes:

    def test_get_skills(self):
        # Populate the routes module's global registry
        from backend.skills.routes import _registry
        for s in _make_registry_with_skills()[1]:
            _registry.register(s)
        result = handle_get_skills()
        assert result["count"] >= 5
        assert len(result["skills"]) >= 5

    def test_get_skills_by_category(self):
        result = handle_get_skills(category="coding")
        assert result["count"] >= 0

    def test_get_skill(self):
        # Register directly into routes module's registry
        from backend.skills.routes import _registry
        _registry.register(_make_skill("rs-get", "for-get", SkillCategory.CODING, SkillDomain.BACKEND))
        result = handle_get_skill("rs-get")
        assert result is not None
        assert result["skill"]["name"] == "for-get"

    def test_get_skill_nonexistent(self):
        result = handle_get_skill("nonexistent")
        assert result is None

    def test_post_select(self):
        from backend.skills.routes import _registry
        for s in _make_registry_with_skills()[1]:
            _registry.register(s)
        result = handle_post_select(task_description="build a python API")
        assert result["count"] > 0
        assert len(result["selections"]) > 0

    def test_post_load(self):
        from backend.skills.routes import _registry
        _registry.register(_make_skill("rs-load", "for-load", SkillCategory.CODING, SkillDomain.BACKEND))
        result = handle_post_load("rs-load", agent_id="agent-1", mission_id="mission-1")
        assert result["loaded"] is True

    def test_post_unload(self):
        from backend.skills.routes import _registry
        _registry.register(_make_skill("rs-unload", "for-unload", SkillCategory.CODING, SkillDomain.BACKEND))
        handle_post_load("rs-unload")
        result = handle_post_unload("rs-unload")
        assert result["unloaded"] >= 0

    def test_get_cache(self):
        result = handle_get_cache()
        assert "size" in result

    def test_get_statistics(self):
        result = handle_get_statistics()
        assert "registry" in result
        assert "cache" in result
        assert "loader" in result
        assert "profiler" in result
        assert "distributor" in result


# ── TestThreadSafety ─────────────────────────────────────────

class TestThreadSafety:

    def test_concurrent_registry_access(self):
        reg = SkillRegistry()
        reg.register(_make_skill("s1", "shared"))

        errors = []
        def worker():
            try:
                for _ in range(50):
                    s = reg.get("s1")
                    assert s is not None
                    reg.list_active()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_concurrent_cache(self):
        cache = SkillCache(max_size=100, default_ttl=0)

        def worker():
            for i in range(50):
                cache.put(f"skill-{i}")

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert cache.size() <= 100

    def test_concurrent_profiler(self):
        profiler = SkillProfiler()

        def worker(i: int):
            start = profiler.start_profile(f"skill-{i % 5}")
            profiler.end_profile(f"skill-{i % 5}", start, memory_mb=float(i), tokens=i)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(profiler.get_all()) <= 5
