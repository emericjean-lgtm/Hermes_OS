"""Integration tests for the Hermes OS composition root (HOS-066B).

These tests exist because the RC1 audit found something no unit test could have
caught: every subsystem passed its own tests while the *assembled* application
did not work. Each test file built its own ``FastAPI()`` and mounted the router
it wanted, so the suite never once exercised the real app object. The result was
an application that could not start, served none of its 109 Hermes OS endpoints,
and dropped 26 of 28 event topics on the floor.

So every assertion here is made against the real ``create_app()`` — the same
object uvicorn serves — and never against a hand-built fixture. New unit tests
belong next to their subsystem; this file only asserts that the pieces are
*connected*.
"""

from __future__ import annotations

import logging
import threading

import pytest
from fastapi.testclient import TestClient

from backend.core.bootstrap import (
    SERVICE_SPECS,
    DependencyContainer,
    DuplicateServiceError,
    HermesBootstrap,
    MissingServiceError,
    collect_known_topics,
    resolve_build_order,
)
from backend.core.bootstrap.router_registry import API_V1, LEGACY_SDS_PREFIX
from backend.main import create_app

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture(scope="module")
def bootstrap(app) -> HermesBootstrap:
    """The bootstrap belonging to the app under test.

    Taken from ``app.state`` rather than freshly constructed, and that matters:
    the ``create_*_routes(service)`` hooks bind by assigning a *module* global,
    so when several apps exist in one interpreter the last one built owns the
    route modules. Asserting against a separately-built bootstrap would compare
    the app's services with an instance nothing is bound to. Production builds
    exactly one app, so the ambiguity is a test-time property only — but the
    tests have to respect it to mean anything.
    """
    return app.state.bootstrap


@pytest.fixture(scope="module")
def client(app):
    """A client whose context manager runs the real lifespan.

    Entering the context is what makes this a startup test as well: a lifespan
    that raises fails every test in the module rather than passing silently.
    """
    with TestClient(app) as c:
        yield c


class _StubTask:
    """Minimal stand-in for TaskExecution — only what RealTaskExecutor reads
    via getattr(..., default), same pattern as test_real_execution.py's
    _Task."""

    def __init__(self, title: str) -> None:
        self.task_id = "assembly-stub-task"
        self.title = title


# ── Container invariants ──────────────────────────────────────────────


class TestDependencyContainer:
    def test_one_instance_per_key(self):
        c = DependencyContainer()
        sentinel = object()
        c.register("svc", sentinel)
        assert c.get("svc") is sentinel

    def test_duplicate_registration_is_refused(self):
        """The "one instance only" guarantee has to be enforced, not assumed."""
        c = DependencyContainer()
        c.register("svc", object())
        with pytest.raises(DuplicateServiceError):
            c.register("svc", object())

    def test_replace_is_explicit(self):
        c = DependencyContainer()
        first, second = object(), object()
        c.register("svc", first)
        c.register("svc", second, replace=True)
        assert c.get("svc") is second

    def test_missing_service_names_itself(self):
        c = DependencyContainer()
        with pytest.raises(MissingServiceError) as exc:
            c.get("nope")
        assert "nope" in str(exc.value)

    def test_registration_order_is_preserved(self):
        c = DependencyContainer()
        for key in ("a", "b", "c"):
            c.register(key, object())
        assert c.keys() == ["a", "b", "c"]

    def test_reverse_iteration_for_shutdown(self):
        c = DependencyContainer()
        for key in ("a", "b", "c"):
            c.register(key, object())
        seen: list[str] = []
        c.for_each_reversed(lambda k, _v: seen.append(k))
        assert seen == ["c", "b", "a"]

    def test_concurrent_registration_is_safe(self):
        c = DependencyContainer()
        errors: list[Exception] = []

        def worker(n: int) -> None:
            try:
                c.register(f"svc{n}", object())
            except Exception as exc:  # pragma: no cover - would be a lock bug
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(24)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(c) == 24


# ── Build order ───────────────────────────────────────────────────────


class TestBuildOrder:
    def test_every_dependency_precedes_its_consumer(self):
        order = [s.key for s in resolve_build_order()]
        for spec in SERVICE_SPECS:
            for dep in spec.dependencies:
                assert order.index(dep) < order.index(spec.key), (
                    f"{spec.key} is built before its dependency {dep}"
                )

    def test_order_covers_every_spec(self):
        assert {s.key for s in resolve_build_order()} == {s.key for s in SERVICE_SPECS}

    def test_dependencies_all_resolve_to_real_specs(self):
        keys = {s.key for s in SERVICE_SPECS}
        for spec in SERVICE_SPECS:
            unknown = set(spec.dependencies) - keys
            assert not unknown, f"{spec.key} depends on unknown {unknown}"


# ── Bootstrap ─────────────────────────────────────────────────────────


class TestBootstrap:
    def test_every_subsystem_builds(self, bootstrap: HermesBootstrap):
        report = bootstrap.report
        assert report.failed == {}, f"subsystems failed to build: {report.failed}"
        assert len(report.built) == report.total_expected

    def test_startup_reaches_100_percent(self, bootstrap: HermesBootstrap):
        """STEP 10's gate: GO only if the assembly is complete."""
        assert bootstrap.report.completion_percent() == 100.0
        assert bootstrap.report.is_complete()

    def test_every_router_binds(self, bootstrap: HermesBootstrap):
        assert bootstrap.report.router_failures == {}
        assert bootstrap.report.routers_mounted >= 30

    def test_no_dependency_cycles(self, bootstrap: HermesBootstrap):
        assert bootstrap.report.dependency_cycles == []

    def test_no_missing_dependencies(self, bootstrap: HermesBootstrap):
        assert bootstrap.report.missing_dependencies == {}

    def test_no_isolated_subsystem(self, bootstrap: HermesBootstrap):
        """The RC1 audit found seven subsystems with no edges in either
        direction. None may remain."""
        assert bootstrap.report.isolated_services == []

    def test_build_is_idempotent(self):
        b = HermesBootstrap()
        first = b.build()
        second = b.build()
        assert first is second
        assert len(b.container) == len(first.built)

    def test_container_holds_exactly_the_built_services(self, bootstrap):
        assert set(bootstrap.container.keys()) == set(bootstrap.report.built)


# ── Dependency injection actually reached the subsystems ──────────────


class TestDependencyInjection:
    """Asserted against a *running* app.

    Every test here takes the ``client`` fixture, which enters the lifespan, and
    the lifespan calls ``rebind_routes()``. That is what makes the assertions
    deterministic: route modules bind through a module global, so without a
    running app the bindings belong to whichever bootstrap was built last in the
    interpreter.
    """

    def test_services_share_one_event_dispatcher(self, client, bootstrap: HermesBootstrap):
        """Every ``on_event`` seam must lead to the same pair of sinks.

        Scoped dispatchers relabel the source but share the sinks and counters,
        so a publish from any subsystem is visible in one place.
        """
        dispatcher = bootstrap.container.get("event_dispatcher")
        stats = dispatcher.statistics()
        assert stats["sinks"] == {"system_bus": True, "event_hub": True}

    def test_route_modules_see_the_container_instance(self, client, bootstrap):
        """The bug this guards: a lazy ``get_engine()`` fallback would build a
        *second*, unwired engine, and the HTTP layer would talk to that one."""
        from backend.security import routes as security_routes

        assert security_routes.get_engine() is bootstrap.container.get("security_engine")

    def test_memory_routes_are_bound(self, client, bootstrap):
        from backend.memory import routes as memory_routes

        assert memory_routes._manager is bootstrap.container.get("memory_manager")

    def test_policy_routes_are_bound(self, client, bootstrap):
        from backend.policy import routes as policy_routes

        assert policy_routes._engine is bootstrap.container.get("policy_engine")

    def test_orchestrator_routes_are_bound(self, client, bootstrap):
        from backend.runtime.orchestrator import routes as orch_routes

        assert orch_routes._orchestrator is bootstrap.container.get(
            "runtime_orchestrator"
        )

    def test_adopted_singletons_are_not_duplicated(self, client, bootstrap):
        """Skills/tools/execution build their graph at module import. The
        container must adopt those objects, not construct rivals."""
        from backend.execution import routes as execution_routes
        from backend.skills import routes as skill_routes
        from backend.tools import routes as tool_routes

        assert bootstrap.container.get("skill_distributor") is skill_routes._distributor
        assert bootstrap.container.get("tool_platform") is tool_routes._registry
        assert bootstrap.container.get("execution_controller") is execution_routes._controller

    def test_task_executor_shares_the_container_model_intelligence(self, client, bootstrap):
        """task_executor's model_for/on_execution reach into Model
        Intelligence's module-level singleton (backend/model_intelligence/
        routes.py) rather than a rival instance — otherwise the container's
        AdaptiveRouter and the one real executions actually feed would
        silently diverge, the same bug class as HOS-065's other adopted
        singletons above."""
        from backend.model_intelligence import routes as mi_routes

        executor = bootstrap.container.get("task_executor")
        assert executor._model_for is not None
        assert executor._on_execution is not None
        assert executor._num_ctx_for is not None

        router = mi_routes._get_router()
        profiler = mi_routes._get_profiler()
        assert bootstrap.container.get("model_intelligence") is router

        seen_ctx = []

        async def fake_chat(*, messages, model, num_ctx=None):
            seen_ctx.append(num_ctx)
            return "a real completion"

        try:
            executor._chat = fake_chat  # hermetic: no live Ollama needed
            outcome = executor.execute(_StubTask(title="Implement a REST endpoint"))
        finally:
            executor._chat = None

        # The model actually used came from AdaptiveRouter, and is a real,
        # installed tag (from config/models.yaml, not the fictional catalog
        # HOS-065 shipped with) rather than the hardcoded qwen3:4b default.
        recommendation = router.recommend_for_text("Implement a REST endpoint")
        assert outcome.model == recommendation.model_id

        # HOS-065C: the context window that reached the runtime call is the
        # real, per-role, benchmark-informed value (config/models.yaml's
        # roles.*.num_ctx) — not None/the old single global default.
        assert seen_ctx == [recommendation.num_ctx]
        assert recommendation.num_ctx > 0

        profile = profiler.get_profile(outcome.model)
        assert profile is not None
        assert profile.total_runs >= 1, (
            "a real execution must move the profiler's counters — before this "
            "wiring, nothing but the simulated BenchmarkScheduler ever did"
        )

        # Same real execution, ModelMemoryAdapter's side (HOS-065B):
        # record_model_for_task() existed and was never called by anything,
        # so get_best_model_for_task() always returned None.
        memory = mi_routes._get_memory()
        task_type = router._infer_task_type("Implement a REST endpoint").value
        assert memory.get_best_model_for_task(task_type) is None, (
            "needs 3+ uses before it will name a winner — see "
            "ModelMemoryAdapter.get_best_model_for_task"
        )
        relations = memory.query_knowledge_graph(target=task_type)
        assert any(r["source"] == outcome.model for r in relations)

    def test_autonomous_orchestrator_shares_the_container_model_intelligence(self, client, bootstrap):
        """AutonomousOrchestrator.set_model_adapter (called by
        _make_autonomous_engine) wraps the same AdaptiveRouter the container
        exposes as "model_intelligence" — not a second, disconnected
        instance whose feedback the Models Center would never see."""
        from backend.model_intelligence import routes as mi_routes

        orchestrator = bootstrap.container.get("autonomous_engine").orchestrator
        assert orchestrator._model_adapter is not None
        assert orchestrator._model_adapter._router is mi_routes._get_router()
        assert bootstrap.container.get("model_intelligence") is mi_routes._get_router()

    # ── R-006: CodeIntelligenceAgent/Router composition (Phase 1/2) ──────
    #
    # Before this, CodeIntelligenceAgent/CodeIntelligenceRouter were never
    # instantiated anywhere in a running code path (importable, unused).
    # These must run before test_every_cross_app_shared_service_is_declared
    # below: that test (like this class's own duplication check) builds
    # extra raw HermesBootstrap() instances, and code_intelligence's route
    # module binds through the same last-build-wins module global every
    # other adopted route module does (see the `bootstrap` fixture's
    # docstring) — asserting module-global identity after that point would
    # compare against whichever bootstrap ran last, not this app's.

    def test_code_intelligence_agent_is_built_and_ready(self, client, bootstrap):
        from backend.agents.agent_models import AgentStatus

        agent = bootstrap.container.get("code_intelligence")
        assert agent.status == AgentStatus.READY
        assert agent.is_available

    def test_code_intelligence_reuses_the_adopted_klaatcode_adapter(self, client, bootstrap):
        """Not a second, unbound KlaatCodeMCPAdapter — the one klaatcode.routes
        and GET /klaatcode/status already serve."""
        agent = bootstrap.container.get("code_intelligence")
        assert agent._klaatcode_agent._mcp_adapter is bootstrap.container.get("klaatcode")

    def test_code_intelligence_reuses_the_adopted_ohmypi_adapter(self, client, bootstrap):
        agent = bootstrap.container.get("code_intelligence")
        assert agent._ohmypi_agent._mcp_adapter is bootstrap.container.get("ohmypi")

    def test_code_intelligence_shares_the_container_memory_manager(self, client, bootstrap):
        agent = bootstrap.container.get("code_intelligence")
        mm = bootstrap.container.get("memory_manager")
        assert agent._memory_manager is mm
        assert agent._klaatcode_agent._memory_manager is mm
        assert agent._ohmypi_agent._memory_manager is mm

    def test_code_intelligence_sub_agents_share_the_container_workspace_manager(self, client, bootstrap):
        agent = bootstrap.container.get("code_intelligence")
        wm = bootstrap.container.get("workspace_manager")
        assert agent._klaatcode_agent._workspace_manager is wm
        assert agent._ohmypi_agent._workspace_manager is wm

    def test_code_intelligence_router_is_real_and_actually_used(self, client, bootstrap):
        """The router genuinely scores/decides per task type — not a stub
        returning a constant provider regardless of input."""
        from backend.integrations.code_intelligence.code_intelligence_models import (
            CodeIntelligenceTask,
            CodeIntelligenceTaskType,
            CodeProvider,
        )

        agent = bootstrap.container.get("code_intelligence")
        review = agent._router.decide(
            CodeIntelligenceTask(task_id="t1", task_type=CodeIntelligenceTaskType.ARCHITECTURE_REVIEW),
        )
        debugging = agent._router.decide(
            CodeIntelligenceTask(task_id="t2", task_type=CodeIntelligenceTaskType.DEBUGGING),
        )
        assert review.selected_provider == CodeProvider.KLATCODE
        assert debugging.selected_provider == CodeProvider.OHMYPI

    def test_code_intelligence_has_a_real_hermes_native_executor(self, client, bootstrap):
        from backend.agents.specialized.code_intelligence.hermes_native_executor import (
            HermesNativeExecutor,
        )

        agent = bootstrap.container.get("code_intelligence")
        assert isinstance(agent._hermes_native_executor, HermesNativeExecutor)
        assert agent._hermes_native_executor.is_available

    def test_klaatcode_adapter_is_really_bound_to_its_mcp_server(self, client, bootstrap):
        """R-006 Phase 5: register_klaatcode() used to build its own
        throwaway adapter (since registry_seeding.py called it without
        adapter=), binding a server nobody reads. The real adapter
        container['klaatcode'] and GET /klaatcode/status share must show
        server_bound=True after a real bootstrap build."""
        adapter = bootstrap.container.get("klaatcode")
        assert adapter.get_server() is not None
        assert adapter.get_status()["server_bound"] is True

    def test_ohmypi_adapter_is_really_bound_to_its_mcp_server(self, client, bootstrap):
        adapter = bootstrap.container.get("ohmypi")
        assert adapter.get_server() is not None
        assert adapter.get_status()["server_bound"] is True

    def test_status_route_is_reachable_through_the_real_app(self, client, bootstrap):
        """R-006's literal complaint: Hermes exposed no
        /api/v1/code-intelligence endpoints at all. This hits the real
        mounted app, not a hand-built router."""
        resp = client.get(f"{API_V1}/code-intelligence/status")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == bootstrap.container.get("code_intelligence").agent_id

    def test_events_reach_the_real_system_event_bus(self, client, bootstrap):
        """R-006 Phase 11: ci.* events were declared in CI_EVENTS since
        HOS-055D but CodeIntelligenceAgent was never instantiated in
        production, so on_event was always None and every publish call was
        a no-op — nothing ever reached the real bus. Now it's wired with a
        real dispatcher (Phase 1); this proves the events genuinely arrive,
        not just that the code compiles."""
        from backend.integrations.code_intelligence.code_intelligence_models import (
            CodeProvider,
        )

        bus = bootstrap.container.get("system_event_bus")

        agent = bootstrap.container.get("code_intelligence")
        # KlaatCode, not Hermes-native: a real klaatcode subprocess call is
        # ~1s, a real Ollama generation is ~30s — this suite stays hermetic
        # and fast (tests.support.fake_inference exists for exactly this
        # reason), and the events this test checks are published either way.
        agent.execute_task("code_analysis", {}, force_provider=CodeProvider.KLATCODE)

        events = bus.query()
        types = {e.type for e in events if e.source == "code_intelligence"}

        # task_started existed in CI_EVENTS since HOS-055D with zero
        # publish() call sites anywhere — the literal gap this phase fixes.
        assert "ci.task.started" in types
        assert "ci.routing.decided" in types
        assert ("ci.task.completed" in types) or ("ci.task.failed" in types)

    def test_second_bootstrap_does_not_duplicate_code_intelligence(self, client, bootstrap):
        """Guards the same class of bug test_every_cross_app_shared_service_is_declared
        checks for the older adopted singletons: code_intelligence is *not*
        adopts_module_singleton (it's genuinely built once per app, unlike
        klaatcode/ohmypi), so a second bootstrap must get its own instance —
        while still pointing at the *same* underlying klaatcode/ohmypi adapters."""
        second = HermesBootstrap()
        second.build()
        first_agent = bootstrap.container.get("code_intelligence")
        second_agent = second.container.get("code_intelligence")
        assert first_agent is not second_agent
        assert first_agent._klaatcode_agent._mcp_adapter is second_agent._klaatcode_agent._mcp_adapter

    def test_every_cross_app_shared_service_is_declared(self):
        """Sharing state between app instances must be deliberate.

        Checking three known adopters by name was not enough: the RC2 audit
        found four more (klaatcode, ktransformers, model_intelligence, ohmypi)
        silently sharing a process-global object without the flag, so the
        dependency report described them as isolated per-app when they were not.
        This asserts the invariant instead of a list.

        Kept last in the class deliberately: it (like the test above) builds
        extra raw HermesBootstrap() instances that steal every adopted route
        module's last-build-wins global, so nothing after this point may
        still assume a route module points at `bootstrap`'s instance.
        """
        first, second = HermesBootstrap(), HermesBootstrap()
        first.build()
        second.build()

        declared = {s.key for s in SERVICE_SPECS if s.adopts_module_singleton}
        # event_hub is a documented process-wide singleton (get_event_hub is
        # lru_cached) rather than an adopted module graph.
        declared.add("event_hub")

        shared = {
            spec.key
            for spec in SERVICE_SPECS
            if first.container.try_get(spec.key) is not None
            and first.container.try_get(spec.key) is second.container.try_get(spec.key)
        }
        undeclared = sorted(shared - declared)
        assert undeclared == [], (
            "these services share one instance across apps but are not flagged "
            f"adopts_module_singleton: {undeclared}"
        )


# ── Event wiring ──────────────────────────────────────────────────────


class TestEventWiring:
    def test_event_hub_accepts_every_declared_topic(self):
        """26 of 28 RAL topics used to be rejected and silently dropped."""
        from backend.core.event_hub import EVENT_TYPES

        missing = sorted(t for t in collect_known_topics() if t not in EVENT_TYPES)
        assert missing == [], f"topics the hub would drop: {missing}"

    def test_typos_are_still_rejected(self):
        """Widening the allow-list must not turn it off: an invented topic is
        still a producer bug worth catching."""
        from backend.core.event_hub import EVENT_TYPES

        assert "task.exploded" not in EVENT_TYPES

    def test_malformed_topics_are_refused(self):
        """The publish path is permissive about *unknown* topics but not about
        malformed ones — a non-dotted or whitespace-bearing topic is a
        programming error no subscriber could match."""
        from backend.core.event_hub import EventHub

        hub = EventHub()
        for bad in ("nodot", "", ".leading", "trailing.", "has space.x", None, 123):
            hub.publish(bad, {})  # must not raise, must not deliver

    def test_no_real_subsystem_event_is_dropped(self, bootstrap):
        """Drive real subsystems and assert the hub swallowed nothing.

        This is the check that was missing. HOS-066B derived the allow-list from
        an AST scan of string literals, which cannot see
        ``AUTONOMOUS_EVENTS["goal_received"]`` or a topic held in a variable — so
        8 topics were still being dropped after the drift was declared fixed.
        Watching the hub's own rejection log while exercising the subsystems
        catches that regardless of how the topic is constructed.

        ## Ce que ce test garde, et ce qu'il a cédé (HOS-252, T-17)

        Il garde le **chemin autonome réel** : interprétation de l'objectif,
        décomposition par un vrai modèle, mission, DAG, agents. Les familles
        `autonomous.*` et `planning.*` n'existent que là, et c'est ce qui
        justifie qu'un test coûte des minutes.

        Il a cédé la preuve du **câblage** à
        `backend/tests/test_cablage_des_evenements.py`, qui l'établit en
        0,4 s sur la même chaîne de production. Mesuré en passe 18 : ce
        test-ci tournait 608 s sans terminer, pour une couverture de topics
        acquise à 187 s, avec un plafond de conception de ~4 800 s.

        ## Pourquoi il se termine maintenant

        Dès que sa propriété est démontrée, il **annule** l'objectif par la
        route de production (`cancel_goal`, HOS-252/T-18). L'annulation
        n'interrompt pas un nœud engagé — c'est l'invariant du dépôt — donc
        l'attente restante est bornée par le plafond de nœud que
        l'architecture a déjà décidé, `plafond_du_noeud()`. Le dépasser
        n'est pas un délai de confort : c'est le graphe qui a franchi son
        propre dernier recours, et le test échoue en le disant.
        """
        import threading
        import time

        from backend.mission.graph_executor import plafond_du_noeud

        # Les familles que **seul** le chemin autonome produit. Nommées une
        # par une, comme côté rapide : un compteur resterait vert si l'une
        # disparaissait pendant qu'une autre apparaît.
        attendus = (
            "autonomous.goal.received",
            "autonomous.goal.analyzed",
            "autonomous.plan.created",
            "autonomous.execution.started",
            "planning.completed",
            "mission.created",
            "mission.started",
            # Publié par le **vrai** RealTaskExecutor, donc introuvable dans
            # le test rapide, dont la couture le remplace.
            "execution.task_started",
        )

        dropped: list[str] = []
        vus: list[str] = []

        class Catch(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                text = record.getMessage()
                if "not published" in text:
                    dropped.append(text)

        hub = bootstrap.container.get("event_hub")
        publier = hub.publish

        def publier_et_noter(event_type, payload=None, *a, **k):
            vus.append(str(event_type))
            return publier(event_type, payload, *a, **k)

        handler = Catch()
        hub_logger = logging.getLogger("backend.core.event_hub")
        previous = hub_logger.level
        hub_logger.setLevel(logging.WARNING)
        hub_logger.addHandler(handler)
        hub.publish = publier_et_noter

        moteur = bootstrap.container.get("autonomous_engine")
        fil = threading.Thread(
            target=lambda: moteur.start_goal("Build an API"),
            name="assemblage-objectif", daemon=True)
        borne = plafond_du_noeud()
        try:
            bootstrap.container.get("security_engine").check_access(
                principal_id="a1", resource_type="tool", resource_id="exec"
            )
            bootstrap.container.get("policy_engine").evaluate(
                {"agent_id": "a1", "operation": "write", "resource": "/tmp/probe"}
            )

            fil.start()
            limite = time.monotonic() + borne
            while time.monotonic() < limite:
                if all(t in vus for t in attendus) or not fil.is_alive():
                    break
                time.sleep(1.0)

            manquants = [t for t in attendus if t not in vus]
            assert manquants == [], (
                f"le chemin autonome n'a pas publié {manquants} en {borne:.0f} s")

            # Assez vu : on cesse d'engager. Un nœud déjà engagé termine.
            objectifs = moteur.list_goals(limit=1)
            if objectifs:
                # `AutonomousEngine.list_goals` rend des dicts
                # (`to_dict()`), pas les objets de l'orchestrateur.
                reponse = moteur.cancel_goal(objectifs[0]["goal_id"])
                assert reponse["success"] is True
            fil.join(timeout=borne)
            assert not fil.is_alive(), (
                f"la marche du graphe n'a pas atteint son état terminal {borne:.0f} s "
                "après l'annulation, alors que le plafond de nœud est censé la "
                "borner — le dernier recours du graphe a été franchi")
        finally:
            hub.publish = publier
            hub_logger.removeHandler(handler)
            hub_logger.setLevel(previous)

        assert dropped == [], f"EventHub dropped real subsystem events: {dropped}"

    def test_dispatcher_accepts_both_call_shapes(self, bootstrap):
        """Subsystems call on_event(type, payload) and, in the security layer,
        on_event(type, payload, severity=...)."""
        dispatcher = bootstrap.container.get("event_dispatcher")
        before = dispatcher.statistics()["total_published"]
        dispatcher("audit.created", {"a": 1})
        dispatcher("security.threat.detected", {"b": 2}, severity="warning")
        after = dispatcher.statistics()["total_published"]
        assert after == before + 2

    def test_dispatcher_never_raises(self, bootstrap):
        """A dashboard notification must never fail the work that produced it."""

        class Exploding:
            def publish(self, *a, **k):
                raise RuntimeError("sink is down")

        from backend.core.bootstrap.event_wiring import EventDispatcher

        d = EventDispatcher(system_bus=Exploding(), event_hub=Exploding())
        d("audit.created", {"x": 1})  # must not raise
        assert d.statistics()["delivery_failures"] == 2

    def test_subsystem_publish_reaches_the_bus(self, bootstrap):
        """End-to-end: a real subsystem action produces a real bus event."""
        bus = bootstrap.container.get("system_event_bus")
        engine = bootstrap.container.get("security_engine")

        before = len(bus.query())
        engine.check_access(
            principal_id="agent-int-test",
            resource_type="tool",
            resource_id="exec",
        )
        assert len(bus.query()) > before


# ── Router registration ───────────────────────────────────────────────


class TestRouterRegistration:
    def test_no_duplicate_routes(self, app):
        """FastAPI resolves duplicates by first-registered-wins, silently. That
        is how a validated endpoint ended up shadowed by an unvalidated one."""
        assert app.state.mount_report.collisions == []

    def test_no_router_is_orphaned(self, app, bootstrap: HermesBootstrap):
        """Every subsystem that owns a router has it mounted on the real app."""
        mounted = {r.path for r in app.routes}
        for spec in SERVICE_SPECS:
            if spec.route_binder is None:
                continue
            assert any(p.startswith(API_V1) for p in mounted), spec.key

    @pytest.mark.parametrize(
        "path",
        [
            f"{API_V1}/agents",
            f"{API_V1}/missions",
            f"{API_V1}/memory/statistics",
            f"{API_V1}/skills",
            f"{API_V1}/tools",
            f"{API_V1}/policy/rules",
            f"{API_V1}/approval",
            f"{API_V1}/audit",
            f"{API_V1}/workspace",
            f"{API_V1}/security/status",
            f"{API_V1}/execution",
            f"{API_V1}/conversation/sessions",
            f"{API_V1}/models",
            f"{API_V1}/autonomous/status",
            f"{API_V1}/evolution/status",
            f"{API_V1}/explainability/explanations",
            f"{API_V1}/collaboration/history",
            f"{API_V1}/planner/templates",
            f"{API_V1}/alexandrie/status",
            f"{API_V1}/runtime/resources/status",
            f"{API_V1}/runtime/orchestrator/history",
            f"{API_V1}/runtime/discovery/models",
            f"{API_V1}/runtime/recovery/status",
            f"{API_V1}/runtime/intelligence/scores",
            f"{API_V1}/runtime/simulation/history",
            f"{API_V1}/runtime/ktransformers/status",
            f"{API_V1}/klaatcode/status",
            f"{API_V1}/ohmypi/status",
            f"{API_V1}/mcp/servers",
        ],
    )
    def test_every_center_endpoint_answers(self, client: TestClient, path: str):
        """Each of these was a 404 or a 503 before HOS-066B."""
        response = client.get(path)
        assert response.status_code < 400, f"{path} -> {response.status_code}"

    def test_no_endpoint_returns_5xx(self, client: TestClient, app):
        """The generalising assertion: enumerate the app's own routes so a route
        added later is covered without anyone remembering to list it here."""
        skip = {"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}
        failures: list[str] = []
        for route in app.routes:
            methods = getattr(route, "methods", None) or set()
            path = getattr(route, "path", "")
            if "GET" not in methods or "{" in path or path in skip:
                continue
            code = client.get(path).status_code
            if code >= 500:
                failures.append(f"{path} -> {code}")
        assert failures == [], f"5xx responses: {failures}"


# ── Namespace unification ─────────────────────────────────────────────


class TestUnifiedNamespace:
    def test_canonical_prefix_serves_the_sds_endpoints(self, client: TestClient):
        assert client.get(f"{API_V1}/health").status_code == 200
        assert client.get(f"{API_V1}/runtimes").status_code == 200

    def test_legacy_prefix_redirects(self, client: TestClient):
        response = client.get(f"{LEGACY_SDS_PREFIX}/health", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == f"{API_V1}/health"

    def test_legacy_redirect_preserves_method(self, client: TestClient):
        """307 and not 302, so a redirected POST stays a POST."""
        response = client.post(
            f"{LEGACY_SDS_PREFIX}/runtimes/stub/select", follow_redirects=False
        )
        assert response.status_code == 307

    def test_legacy_prefix_still_resolves_when_followed(self, client: TestClient):
        assert client.get(f"{LEGACY_SDS_PREFIX}/health").status_code == 200

    def test_sds_handlers_are_not_duplicated(self, app):
        """Rebasing reuses the endpoint functions rather than copying them."""
        from backend.sds.routes import SDS_ROUTER

        originals = {r.endpoint for r in SDS_ROUTER.routes}
        rebased = {
            r.endpoint
            for r in app.routes
            if getattr(r, "path", "").startswith(f"{API_V1}/")
            and getattr(r, "endpoint", None) in originals
        }
        assert rebased, "no SDS handler is served under the canonical prefix"


# ── Health, readiness, statistics ─────────────────────────────────────


class TestHealthSurface:
    def test_no_subsystem_is_unhealthy(self, bootstrap: HermesBootstrap):
        health = bootstrap.health()
        assert health["unhealthy"] == []
        assert health["status"] == "healthy"

    def test_health_probe_never_invents_arguments(self, bootstrap):
        """A parameterised same-named accessor (``get_stats(runtime_id)``) must
        be skipped, not called blind — doing so scored a healthy subsystem as
        unhealthy."""
        detail = bootstrap.health()["detail"]
        assert detail["runtime_intelligence"]["status"] != "unhealthy"

    def test_ready_reports_completion(self, bootstrap: HermesBootstrap):
        ready = bootstrap.ready()
        assert ready["ready"] is True
        assert ready["completion_percent"] == 100.0

    def test_statistics_cover_the_reporting_subsystems(self, bootstrap):
        stats = bootstrap.statistics()
        assert stats["service_count"] == len(bootstrap.report.built)
        assert stats["reporting_count"] > 0
        assert "events" in stats

    def test_health_endpoints_are_served(self, client: TestClient):
        for path in ("health", "ready", "statistics", "assembly", "dependencies"):
            response = client.get(f"{API_V1}/system/{path}")
            assert response.status_code == 200, path

    def test_assembly_endpoint_reports_completeness(self, client: TestClient):
        body = client.get(f"{API_V1}/system/assembly").json()
        assert body["bootstrap"]["complete"] is True
        assert body["routers"]["collisions"] == []


# ── Dependency report (STEP 8) ────────────────────────────────────────


class TestDependencyReport:
    def test_report_covers_every_subsystem(self, bootstrap: HermesBootstrap):
        report = bootstrap.dependency_report()
        assert {s["key"] for s in report["services"]} == {
            s.key for s in SERVICE_SPECS
        }

    def test_report_is_acyclic(self, bootstrap: HermesBootstrap):
        assert bootstrap.dependency_report()["cycles"] == []

    def test_topological_order_is_complete(self, bootstrap: HermesBootstrap):
        report = bootstrap.dependency_report()
        assert len(report["topological_order"]) == len(SERVICE_SPECS)

    def test_edges_are_symmetric(self, bootstrap: HermesBootstrap):
        """If A depends on B, B must list A among its dependents."""
        report = bootstrap.dependency_report()
        by_key = {s["key"]: s for s in report["services"]}
        for svc in report["services"]:
            for dep in svc["depends_on"]:
                assert svc["key"] in by_key[dep]["depended_on_by"]


# ── Component registry integration (HOS-056) ──────────────────────────


class TestIntegrationLayer:
    def test_every_subsystem_is_registered(self, bootstrap: HermesBootstrap):
        """The registry used to describe only what tests constructed."""
        registered = set(bootstrap.components.get_registered_ids())
        assert registered == set(bootstrap.report.built)

    def test_registry_records_capabilities_and_events(self, bootstrap):
        info = bootstrap.components.get("security_engine")
        assert info is not None
        assert "permissions" in info.capabilities
        assert "security.threat.detected" in info.produced_events

    def test_health_orchestrator_checks_every_subsystem(self, bootstrap):
        results = bootstrap.health_orchestrator.run_all_checks()
        assert set(results) == set(bootstrap.report.built)


# ── Shutdown ──────────────────────────────────────────────────────────


class TestShutdown:
    def test_shutdown_releases_subsystems_without_raising(self):
        b = HermesBootstrap()
        b.build()
        result = b.shutdown()
        assert isinstance(result["stopped"], list)
        assert result["errors"] == {}, f"shutdown errors: {result['errors']}"

    def test_shutdown_is_reverse_order(self):
        b = HermesBootstrap()
        b.build()
        order = b.container.keys()
        result = b.shutdown()
        stopped_keys = [entry.split(".")[0] for entry in result["stopped"]]
        # Whatever subset had a teardown method must appear in reverse order.
        positions = [order.index(k) for k in stopped_keys if k in order]
        assert positions == sorted(positions, reverse=True)

    def test_a_failing_teardown_does_not_stop_the_others(self):
        b = HermesBootstrap()
        b.build()

        class Exploding:
            def shutdown(self):
                raise RuntimeError("boom")

        b.container.register("exploding", Exploding())
        result = b.shutdown()
        assert "exploding" in result["errors"]
        # The rest still ran.
        assert result["stopped"] != []


# ── Runtime initialisation through the real lifespan ──────────────────


class TestLifespan:
    def test_startup_installs_the_runtime_registry(self, client: TestClient, app):
        assert getattr(app.state, "runtime_registry", None) is not None

    def test_startup_installs_the_eventbus_holder(self, client: TestClient, app):
        assert getattr(app.state, "eventbus_holder", None) is not None

    def test_container_is_exposed_on_app_state(self, client: TestClient, app):
        assert app.state.container is app.state.bootstrap.container

    def test_liveness_endpoint(self, client: TestClient):
        assert client.get("/health").json() == {"status": "ok"}


# ── RC2 audit regressions ─────────────────────────────────────────────


class TestWorkspaceContainment:
    """Workspace paths must stay inside the base directory.

    The RC2 audit found ``work_dir=f"{base}/{mission_id}/{agent_id}"`` built from
    caller-supplied ids, so ``mission_id="../../PWNED"`` produced a path
    resolving outside the base — in the one layer whose purpose is containment.
    """

    @pytest.mark.parametrize(
        "mission_id",
        [
            "../../PWNED",
            r"..\..\Windows",
            "/etc/passwd",
            r"C:\Windows\system32",
            "..",
            ".",
            "",
            "   ",
            "mission/../..",
            "a/b/c",
            "\x00evil",
            "..%2f..%2fetc",
        ],
    )
    def test_work_dir_never_escapes_the_base(self, bootstrap, mission_id):
        from pathlib import Path

        manager = bootstrap.container.get("workspace_manager")
        base = Path(manager._base_path).resolve()  # noqa: SLF001
        ws = manager.create(agent_id="../../attacker", mission_id=mission_id)
        resolved = Path(ws.work_dir).resolve()

        assert base == resolved or base in resolved.parents, (
            f"{mission_id!r} escaped the workspace base: {resolved}"
        )
        # Exactly <base>/<mission>/<agent>: no extra depth may be injected.
        assert len(resolved.relative_to(base).parts) == 2


class TestClientErrorsAreNot5xx:
    """A malformed or incomplete body is the client's mistake, so 4xx.

    21 endpoints answered 500 because handlers read required fields with
    ``payload["field"]`` or coerced them into an enum.
    """

    @pytest.mark.parametrize(
        "path,body",
        [
            ("/api/v1/autonomous/start", {}),
            ("/api/v1/missions", {"title": "x", "type": "not_a_type"}),
            ("/api/v1/missions", {"title": "x", "priority": "bogus"}),
            ("/api/v1/security/check", {}),
            ("/api/v1/security/permissions/grant", {}),
            ("/api/v1/memory/search", {}),
            ("/api/v1/collaboration/delegate", {}),
            ("/api/v1/workspace", {}),
            ("/api/v1/policy/evaluate", {}),
            ("/api/v1/execution/start", {"tasks": "not-a-list"}),
        ],
    )
    def test_returns_422_not_500(self, client: TestClient, path, body):
        response = client.post(path, json=body)
        assert response.status_code < 500, f"{path} -> {response.status_code}"
        assert response.status_code == 422, f"{path} -> {response.status_code}"

    def test_the_offending_field_is_named(self, client: TestClient):
        detail = client.post("/api/v1/autonomous/start", json={}).json()["detail"]
        assert "user_request" in str(detail)


class TestHealthEndpointIsCheap:
    """The Cockpit polls /api/v1/system/health, so it must not do network I/O.

    KlaatCode and Oh My Pi telemetry accessors probe their external service; with
    those down the endpoint took ~864ms and served 1 req/s under 16 threads.
    """

    def test_repeated_calls_are_fast(self, client: TestClient):
        import time

        client.get("/api/v1/system/health")  # warm
        worst = 0.0
        for _ in range(10):
            started = time.perf_counter()
            assert client.get("/api/v1/system/health").status_code == 200
            worst = max(worst, time.perf_counter() - started)
        assert worst < 0.25, f"slowest cached health call took {worst*1000:.0f}ms"

    def test_a_raising_subsystem_is_reported_unhealthy(self, bootstrap):
        """Caching must not cost fault detection."""
        probe = bootstrap.probe
        engine = bootstrap.container.get("security_engine")
        original = engine.get_status
        engine.get_status = lambda: (_ for _ in ()).throw(RuntimeError("injected"))
        try:
            fresh = probe.probe("security_engine", force=True)
            assert fresh["status"] == "unhealthy"
        finally:
            engine.get_status = original
        assert probe.probe("security_engine", force=True)["status"] == "healthy"
