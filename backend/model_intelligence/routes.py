"""REST API routes for Hermes OS Model Intelligence (HOS-065)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from .adaptive_router import AdaptiveRouter, CloudGate
from .benchmark_scheduler import BenchmarkScheduler
from .cloud_catalog import CloudModelCatalog
from .model_evolution_adapter import ModelEvolutionAdapter
from .model_intelligence_models import RuntimeBackend, TaskContext, TaskType
from .model_memory_adapter import ModelMemoryAdapter
from .model_profiler import ModelProfiler
from .model_predictor import ModelPredictor
from .model_runtime_adapter import ModelRuntimeAdapter
from .model_runtime_optimizer import ModelRuntimeOptimizer
from .performance_analyzer import PerformanceAnalyzer

_profiler: ModelProfiler | None = None
_analyzer: PerformanceAnalyzer | None = None
_predictor: ModelPredictor | None = None
_router: AdaptiveRouter | None = None
_scheduler: BenchmarkScheduler | None = None
_optimizer: ModelRuntimeOptimizer | None = None
_runtime_adapter: ModelRuntimeAdapter | None = None
_memory: ModelMemoryAdapter | None = None
_evolution: ModelEvolutionAdapter | None = None
_cloud_catalog: CloudModelCatalog | None = None
_cloud_catalog_checked = False
_resource_manager: Any = None


def set_resource_manager(resource_manager: Any) -> None:
    """Inject the real ResourceManager (HOS-071) so recommendations reason
    about VRAM that is actually free right now, not a static guess. None
    (the default, e.g. in hermetic tests) falls back to the old fixed
    8192MB ceiling everywhere that reads it — unchanged prior behaviour."""
    global _resource_manager
    _resource_manager = resource_manager


def _real_vram_mb(*, total: bool = False) -> int | None:
    """Real, current VRAM from the GPU monitor — free by default (what a
    recommendation should actually be constrained by), or total when asked
    (what a runtime/quantization comparison should be sized against). None
    if no resource manager is wired or the GPU can't be read, so callers
    can fall back to their own static default rather than pretending 0GB
    is available."""
    if _resource_manager is None:
        return None
    try:
        gpu = _resource_manager.get_gpu_info()
        if not gpu.available or gpu.vram_total_bytes <= 0:
            return None
        bytes_value = gpu.vram_total_bytes if total else gpu.vram_free_bytes
        return max(0, int(bytes_value / (1024 * 1024)))
    except Exception:
        return None


def _get_profiler() -> ModelProfiler:
    global _profiler
    if _profiler is None:
        # HOS-071 Phase B: wires the analyzer so ranking uses the one real
        # compute_model_score() formula instead of ModelProfile's own,
        # separately-maintained overall_score property.
        _profiler = ModelProfiler(analyzer=_get_analyzer())
    return _profiler


def _get_analyzer() -> PerformanceAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = PerformanceAnalyzer()
    return _analyzer


def _get_predictor() -> ModelPredictor:
    global _predictor
    if _predictor is None:
        # HOS-071 Phase B: same analyzer instance as _get_profiler(), so
        # rank_models() (the real recommendation) and the ranking table
        # agree on what "best" means.
        _predictor = ModelPredictor(analyzer=_get_analyzer())
    return _predictor


def _get_cloud_catalog() -> CloudModelCatalog | None:
    """None when OPENROUTER_API_KEY isn't configured — the safe default:
    cloud escalation (HOS-066C) stays off and recommend() behaves exactly as
    it did before this feature existed. Checked once per process: an empty
    key is a deployment choice, not something that becomes true mid-run."""
    global _cloud_catalog, _cloud_catalog_checked
    if not _cloud_catalog_checked:
        _cloud_catalog_checked = True
        from backend.core.config import get_settings

        settings = get_settings()
        if settings.openrouter_api_key:
            _cloud_catalog = CloudModelCatalog(
                settings.openrouter_api_key,
                _get_profiler(),
                reserve_daily_requests=settings.openrouter_daily_reserve,
            )
    return _cloud_catalog


def _cloud_authorized() -> bool:
    """Aegis's cloud_inference category, evaluated fresh each time (cheap:
    load_security_config() is lru_cache'd, and AegisEngine.evaluate() is a
    pure, local rules check — no network, no model call). At the shipped
    autonomy_level "low" this always returns False (human validation
    required), which is what keeps cloud escalation off automatically out
    of the box even with a real API key configured."""
    from backend.core.config import get_settings, load_security_config
    from backend.security.aegis_engine import ActionRequest, AegisEngine, Verdict
    from backend.security.permission_matrix import PermissionMatrix

    settings = get_settings()
    matrix = PermissionMatrix(load_security_config())
    engine = AegisEngine(matrix, settings.allowed_paths_list)
    decision = engine.evaluate(ActionRequest(
        action_type="cloud_inference",
        description="OpenRouter free-model escalation",
        requesting_agent="model_intelligence",
    ))
    return decision.verdict == Verdict.ALLOW


def _get_router() -> AdaptiveRouter:
    global _router
    if _router is None:
        _router = AdaptiveRouter(
            profiler=_get_profiler(),
            analyzer=_get_analyzer(),
            predictor=_get_predictor(),
            # HOS-071 Phase D: real combined model+runtime+quantization
            # search instead of two independent heuristics — see
            # set_runtime_optimizer()'s docstring.
            runtime_optimizer=_get_optimizer(),
        )
        catalog = _get_cloud_catalog()
        if catalog is not None:
            _router.set_cloud(CloudGate(
                authorized=_cloud_authorized,
                has_quota=catalog.has_budget,
                refresh_catalog=catalog.refresh,
            ))
    return _router


def get_cloud_fallback_model(task_type: str = "") -> str | None:
    """A cloud (OpenRouter free-model) id to retry against when a *local*
    attempt has already failed for this task_type (HOS-066C) — used by
    BaseAgent/TaskDecomposer's resilience fallback, so it goes through the
    exact same authorization/quota/catalogue gate as the task-execution
    pipeline rather than a second, looser check.

    ``cloud_escalation_allowed=True`` forces the gate open regardless of
    whether local profiles look "viable" on paper — appropriate here
    specifically because local has *already* failed for a reason
    AdaptiveRouter's VRAM-only viability check cannot see (Ollama
    unreachable), not because the task is inherently cloud-worthy.

    None means "no real cloud option right now" (not configured, not
    authorized, no quota, or nothing registered) — callers must treat that
    as "give up on this attempt", never invent a model id.
    """
    router = _get_router()
    tt = TaskType(task_type) if task_type in TaskType._value2member_map_ else TaskType.GENERAL
    decision = router.recommend(TaskContext(task_type=tt, cloud_escalation_allowed=True))
    if decision.runtime == RuntimeBackend.OPENROUTER:
        return decision.model_id
    return None


def _get_scheduler() -> BenchmarkScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BenchmarkScheduler(
            profiler=_get_profiler(),
            analyzer=_get_analyzer(),
        )
    return _scheduler


def _get_optimizer() -> ModelRuntimeOptimizer:
    global _optimizer
    if _optimizer is None:
        _optimizer = ModelRuntimeOptimizer()
    return _optimizer


def _get_runtime_adapter() -> ModelRuntimeAdapter:
    """ModelRuntimeAdapter (HOS-065B) — real cross-runtime/quantization
    comparison math, previously built but never called by anything outside
    its own file and tests (HOS-071 audit). Shares the container's real
    optimizer/profiler rather than building its own, disconnected pair."""
    global _runtime_adapter
    if _runtime_adapter is None:
        _runtime_adapter = ModelRuntimeAdapter(
            optimizer=_get_optimizer(), profiler=_get_profiler(),
        )
    return _runtime_adapter


def _get_memory() -> ModelMemoryAdapter:
    global _memory
    if _memory is None:
        _memory = ModelMemoryAdapter()
    return _memory


def _get_evolution_adapter() -> ModelEvolutionAdapter:
    global _evolution
    if _evolution is None:
        _evolution = ModelEvolutionAdapter(
            profiler=_get_profiler(), analyzer=_get_analyzer(),
        )
    return _evolution


def _sync_profiler_from_ollama(profiler: ModelProfiler) -> None:
    """Best-effort real-time catalogue refresh (HOS-073) — see
    ModelProfiler.sync_from_ollama()'s own docstring. Called from the
    Cockpit's two real listing entry points so a model the user just
    pulled shows up without a backend restart."""
    from backend.core.config import get_settings

    try:
        profiler.sync_from_ollama(get_settings().ollama_api_url)
    except Exception:
        pass


def handle_get_intelligence() -> dict[str, Any]:
    """GET /models/intelligence"""
    profiler = _get_profiler()
    _sync_profiler_from_ollama(profiler)
    return {
        "success": True,
        "data": profiler.get_stats(),
    }


def handle_get_ranking(task_type: str = "", limit: int = 100) -> dict[str, Any]:
    """GET /models/ranking

    ``limit`` default raised from 5 to 100 (HOS-073) — the Cockpit's own
    ranking table and benchmark model-select called this with no explicit
    limit at all, so only the top 5 of every registered model ever
    appeared, silently hiding the rest regardless of how many were really
    available.
    """
    profiler = _get_profiler()
    _sync_profiler_from_ollama(profiler)
    tt = TaskType(task_type) if task_type and task_type in TaskType._value2member_map_ else None
    top = profiler.get_top_models(tt, limit)
    return {
        "success": True,
        "models": [
            {
                "model_id": m.model_id,
                "name": m.name,
                "score": round(profiler._score(m), 3),  # noqa: SLF001
                "parameters_b": m.parameters_b,
                "vram_mb": m.vram_required_mb,
                "tps": round(m.tokens_per_second, 1),
                "success_rate": round(m.success_rate, 3),
                "tags": m.tags,
            }
            for m in top
        ],
    }


def handle_recommend(task_description: str, language: str = "python",
                     max_vram_mb: int | None = None,
                     task_type: str = "") -> dict[str, Any]:
    """POST /models/recommend

    ``max_vram_mb=None`` (the caller didn't specify one) now resolves to
    the real, currently-free VRAM (HOS-071 Phase A) instead of a static
    8192MB guess — falls back to that same 8192 default only when no
    resource manager is wired. An explicit caller-supplied value is always
    honoured as-is, same as before.
    """
    router = _get_router()
    resolved_vram = max_vram_mb if max_vram_mb is not None else (_real_vram_mb() or 8192)
    decision = router.recommend_for_text(
        task_description, language, resolved_vram, task_type_hint=task_type or None,
    )
    return {
        "success": True,
        "decision": {
            "model_id": decision.model_id,
            "model_name": decision.model_name,
            "runtime": decision.runtime.value,
            "quantization": decision.quantization.value,
            "confidence": round(decision.confidence, 3),
            "reason": decision.reason,
            "estimated_latency_ms": decision.estimated_latency_ms,
            "estimated_tps": decision.estimated_tokens_per_second,
            "estimated_vram_mb": decision.estimated_vram_mb,
            "num_ctx": decision.num_ctx,
            "alternatives": decision.alternatives,
        },
    }


def handle_get_history(limit: int = 20) -> dict[str, Any]:
    """GET /models/history"""
    router = _get_router()
    return {
        "success": True,
        "decisions": router.get_decision_history(limit),
    }


def handle_run_benchmark(model_id: str = "", task_type: str = "code_generation") -> dict[str, Any]:
    """POST /models/benchmark"""
    scheduler = _get_scheduler()
    tt = TaskType(task_type) if task_type in TaskType._value2member_map_ else TaskType.CODE_GENERATION
    if model_id:
        result = scheduler.run_benchmark(model_id, tt)
        return {"success": True, "benchmark": {
            "benchmark_id": result.benchmark_id,
            "model_id": result.model_id,
            "task_type": result.task_type.value,
            "latency_ms": result.latency_ms,
            "tokens_per_second": result.tokens_per_second,
            "vram_usage_mb": result.vram_usage_mb,
            "quality_score": result.quality_score,
        }}
    results = scheduler.run_full_benchmark()
    return {
        "success": True,
        "benchmarks": len(results),
        "message": f"Benchmarked {len(results)} model-task combinations",
    }


def handle_get_performance(model_id: str = "") -> dict[str, Any]:
    """GET /models/performance"""
    profiler = _get_profiler()
    analyzer = _get_analyzer()
    if model_id:
        profile = profiler.get_profile(model_id)
        if not profile:
            return {"success": False, "error": f"Model {model_id} not found"}
        records = profiler.get_performance_history(model_id)
        score = analyzer.compute_model_score(profile, [])
        return {
            "success": True,
            "model_id": model_id,
            "score": round(score, 3),
            "profile": {
                "name": profile.name,
                "parameters_b": profile.parameters_b,
                "vram_mb": profile.vram_required_mb,
                "tps": profile.tokens_per_second,
                "task_scores": profile.task_scores,
                "success_rate": round(profile.success_rate, 3),
                "total_runs": profile.total_runs,
            },
            "benchmark_summary": analyzer.get_benchmark_summary(model_id),
            "recent_runs": records[-10:],
        }
    return {
        "success": True,
        "data": profiler.get_stats(),
    }


def handle_get_benchmarks(model_id: str = "") -> dict[str, Any]:
    """GET /models/benchmarks"""
    scheduler = _get_scheduler()
    return {
        "success": True,
        "benchmarks": scheduler.get_latest_benchmarks(model_id if model_id else None),
    }


def handle_get_knowledge(task_type: str = "") -> dict[str, Any]:
    """GET /models/knowledge

    ModelMemoryAdapter's decision-pattern cache — see its module docstring
    for what this is (and isn't: not the real Unified Memory/Knowledge
    Graph). ``task_type`` optionally asks "which real model has actually
    won most often for this task type" rather than the ranking's
    pre-execution estimate.
    """
    memory = _get_memory()
    result: dict[str, Any] = {"success": True, "stats": memory.get_stats()}
    if task_type:
        result["best_model_for_task"] = memory.get_best_model_for_task(task_type)
        result["relations"] = memory.query_knowledge_graph(target=task_type)
    return result


def handle_get_evolution(threshold: float = 0.7, suggest_for: str = "") -> dict[str, Any]:
    """GET /models/evolution

    Read-only diagnostic from ModelEvolutionAdapter (HOS-065B), computed
    entirely from ModelProfiler's real, execution-fed data — detect_under
    performing_models()/suggest_model_replacement() never touch
    PerformanceAnalyzer's benchmark summaries (BenchmarkScheduler's
    simulated numbers, see its module docstring), so nothing fabricated
    reaches this response.

    update_weights() is deliberately not exposed here: ModelProfile.
    overall_score has fixed coefficients (see model_intelligence_models.py)
    that never read these weights, so wiring a weight-update loop without a
    validated signal for "better" would be a behaviour change dressed as a
    fix, not the read-only visibility this endpoint is for.
    """
    adapter = _get_evolution_adapter()
    result: dict[str, Any] = {
        "success": True,
        "underperforming": adapter.detect_underperforming_models(threshold),
    }
    if suggest_for:
        result["suggestion"] = adapter.suggest_model_replacement(suggest_for)
    return result


def handle_get_optimize(model_id: str) -> dict[str, Any]:
    """GET /models/optimize?model_id=X (HOS-071 Phase D)

    Real cross-runtime/quantization comparison for one model — from
    ModelRuntimeAdapter.compare_runtimes()/ModelRuntimeOptimizer, real math
    that already existed but had no route and no caller. Sized against the
    real, current total VRAM (HOS-071 Phase A's resource manager) rather
    than the adapter's own static 16GB default, when available.
    """
    profiler = _get_profiler()
    profile = profiler.get_profile(model_id)
    if not profile:
        return {"success": False, "error": f"Model {model_id} not found"}

    adapter = _get_runtime_adapter()
    total_vram_mb = _real_vram_mb(total=True)
    if total_vram_mb:
        adapter.update_system_info({"vram_mb": total_vram_mb, "has_cuda": True})

    comparisons = adapter.compare_runtimes(profile)
    best = comparisons[0] if comparisons else None
    return {
        "success": True,
        "model_id": model_id,
        "comparisons": comparisons,
        "best": best,
    }


def handle_get_cloud_status() -> dict[str, Any]:
    """GET /models/cloud/status

    Honest, read-only visibility into OpenRouter cloud escalation (HOS-066C)
    — whether it is configured at all, whether Aegis authorizes it *right
    now* at the current autonomy level, and the real cached catalogue/quota
    state. Deliberately does not trigger a fresh network call on every
    request: quota/catalogue are read from CloudModelCatalog's own cache
    (refreshed on an actual cloud-eligible recommendation, see
    AdaptiveRouter._try_cloud_recommendation), so checking status never
    itself spends quota or adds latency.
    """
    catalog = _get_cloud_catalog()
    if catalog is None:
        return {
            "success": True,
            "configured": False,
            "authorized": False,
            "message": "OPENROUTER_API_KEY is not set — cloud escalation is disabled; every task runs local.",
        }
    authorized = _cloud_authorized()
    status = catalog.status()
    return {
        "success": True,
        "configured": True,
        "authorized": authorized,
        "message": (
            "Cloud escalation is reachable." if authorized else
            "A key is configured, but Aegis does not currently authorize cloud_inference "
            "(needs autonomy_level 'high' in config/security.yaml, or per-request approval) — "
            "every task still runs local."
        ),
        **status,
    }


# ── HTTP surface ─────────────────────────────────────────────
# Thin delegation to the handlers above (HOS-066B). The docstrings on those
# handlers already declared these paths under /models; that prefix is used here
# so the intended contract is what gets served.

router = APIRouter(prefix="/models", tags=["model-intelligence"])


def create_model_intelligence_routes(adaptive_router: AdaptiveRouter) -> APIRouter:
    """Bind the container-owned AdaptiveRouter to these routes.

    Seeds the module singleton so the lazy accessors below return the container's
    instance instead of building a second, unwired one.
    """
    global _router
    _router = adaptive_router
    return router


@router.get("")
async def get_intelligence() -> dict[str, Any]:
    return handle_get_intelligence()


@router.get("/ranking")
async def get_ranking(
    task_type: str = Query(""),
    limit: int = Query(100, ge=1, le=200),
) -> dict[str, Any]:
    return handle_get_ranking(task_type, limit)


@router.post("/recommend")
async def recommend(payload: dict = Body(...)) -> dict[str, Any]:
    # HOS-071: accepts "task_description" (the documented/API-shape name,
    # matching handle_recommend's own parameter) and "description" (what
    # the Cockpit's Recommend tab actually sends) — found via audit that
    # the Cockpit's payload key never matched what this route read, so
    # every real click silently recommended for an empty string regardless
    # of what the user typed. Both are accepted rather than picking one and
    # leaving the other caller's text still lost.
    description = payload.get("task_description") or payload.get("description") or ""
    raw_max_vram = payload.get("max_vram_mb")
    return handle_recommend(
        task_description=description,
        language=payload.get("language", "python"),
        max_vram_mb=int(raw_max_vram) if raw_max_vram is not None else None,
        task_type=payload.get("task_type", ""),
    )


@router.get("/history")
async def get_history(limit: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
    return handle_get_history(limit)


@router.post("/benchmark")
async def run_benchmark(payload: dict = Body(default_factory=dict)) -> dict[str, Any]:
    return handle_run_benchmark(
        model_id=payload.get("model_id", ""),
        task_type=payload.get("task_type", "code_generation"),
    )


@router.get("/performance")
async def get_performance(model_id: str = Query("")) -> dict[str, Any]:
    return handle_get_performance(model_id)


@router.get("/benchmarks")
async def get_benchmarks(model_id: str = Query("")) -> dict[str, Any]:
    return handle_get_benchmarks(model_id)


@router.get("/knowledge")
async def get_knowledge(task_type: str = Query("")) -> dict[str, Any]:
    return handle_get_knowledge(task_type)


@router.get("/evolution")
async def get_evolution(
    threshold: float = Query(0.7, ge=0.0, le=1.0),
    suggest_for: str = Query(""),
) -> dict[str, Any]:
    return handle_get_evolution(threshold, suggest_for)


@router.get("/cloud/status")
async def get_cloud_status() -> dict[str, Any]:
    return handle_get_cloud_status()


@router.get("/optimize")
async def get_optimize(model_id: str = Query(...)) -> dict[str, Any]:
    return handle_get_optimize(model_id)


# ── Catalogue mesuré (HOS-107/108) ───────────────────────────────────────
#
# Distinct des routes ci-dessus, qui exposent les heuristiques et les
# prédictions du ModelProfiler. Celles-ci ne rendent que des mesures
# réelles : chaque note vient d'une campagne qui a fait tourner le modèle,
# et le détail brut de l'échec est conservé à côté du chiffre. Un score
# sans son justificatif redevient une opinion.


def handle_get_catalogue() -> dict[str, Any]:
    """GET /models/catalogue — un objet par modèle, notes par axe.

    ``notes`` porte None pour un axe non mesuré, jamais 0 : un modèle
    jamais testé passerait sinon pour mauvais dans l'onglet Modèles.
    """
    from backend.model_intelligence.bench_score import noter_modele
    from backend.model_intelligence.bench_store import AXES, BenchStore

    entrees = []
    for entree in BenchStore().catalogue():
        entrees.append({
            "model": entree["model"],
            "measured_at": entree["measured_at"],
            "axes": entree["axes"],
            "notes": noter_modele(entree["axes"]),
        })
    return {"success": True, "axes": list(AXES), "models": entrees,
            "total": len(entrees)}


def handle_get_candidats(axe: str, note_minimale: int = 1) -> dict[str, Any]:
    """GET /models/catalogue/candidats — qui peut faire une tâche de cet axe.

    Rend la liste classée, pas la décision : deux modèles à note identique
    en code peuvent différer d'un facteur 7 en temps (mesuré), et c'est au
    routage d'arbitrer avec le coût.
    """
    from backend.model_intelligence.bench_score import meilleur_pour
    from backend.model_intelligence.bench_store import BenchStore

    classes = meilleur_pour(BenchStore().catalogue(), axe, note_minimale)
    return {"success": True, "axe": axe, "note_minimale": note_minimale,
            "candidats": [{"model": m, "note": n} for m, n in classes]}


@router.get("/catalogue")
async def get_catalogue() -> dict[str, Any]:
    return handle_get_catalogue()


@router.get("/catalogue/candidats")
async def get_candidats(
    axe: str = Query(...),
    note_minimale: int = Query(1, ge=0, le=100),
) -> dict[str, Any]:
    return handle_get_candidats(axe, note_minimale)
