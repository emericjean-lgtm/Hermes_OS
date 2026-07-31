"""FastAPI routes for the Model Discovery Engine (HOS-040)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from backend.runtime.discovery.discovery_engine import DiscoveryEngine
from backend.runtime.discovery.model_registry import ModelRegistry
from backend.runtime.discovery.discovery_models import DiscoverySource

router = APIRouter(prefix="/runtime/discovery", tags=["runtime-discovery"])

_discovery_engine: Optional[DiscoveryEngine] = None
_registry: Optional[ModelRegistry] = None


def create_discovery_routes(
    discovery: DiscoveryEngine,
    registry: ModelRegistry,
) -> APIRouter:
    global _discovery_engine, _registry
    _discovery_engine = discovery
    _registry = registry
    return router


@router.post("/scan")
async def run_scan(
    source: Optional[str] = Query(None, description="huggingface|ollama|github"),
):
    if _discovery_engine is None:
        return {"error": "DiscoveryEngine not initialised"}

    sources = None
    if source:
        try:
            sources = [DiscoverySource(source)]
        except ValueError:
            return {"error": f"Unknown source: {source}"}

    run = _discovery_engine.discover(sources)
    return {
        "run_id": run.run_id,
        "models_found": run.models_found,
        "new_models": run.new_models,
        "sources": [s.value for s in run.sources],
        "duration_ms": (
            (run.completed_at - run.started_at).total_seconds() * 1000
            if run.completed_at
            else 0
        ),
    }


@router.get("/models")
async def list_models(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    if _registry is None:
        return {"models": [], "total": 0}

    from backend.runtime.discovery.discovery_models import ModelStatus
    filter_status = ModelStatus(status) if status else None

    models = _registry.list_all(filter_status)[:limit]
    return {
        "models": [
            {
                "id": m.model_id,
                "name": m.name,
                "provider": m.provider,
                "architecture": m.architecture,
                "parameter_count_b": m.parameter_count_b,
                "quantization": m.quantization.value,
                "source": m.source.value,
                "status": m.status.value,
                "tags": m.tags,
            }
            for m in models
        ],
        "total": len(models),
    }


@router.get("/benchmarks")
async def list_benchmarks(model_name: str = Query("")):
    if _registry is None:
        return {"benchmarks": [], "total": 0}

    if model_name:
        results = _registry.get_benchmarks(model_name)
    else:
        all_bm = _registry.get_all_benchmarks()
        results = []
        for bm_list in all_bm.values():
            results.extend(bm_list)

    return {
        "benchmarks": [
            {
                "benchmark_id": r.benchmark_id,
                "model_name": r.model_name,
                "profile": r.profile.value,
                "tokens_per_second": r.tokens_per_second,
                "time_to_first_token_ms": r.time_to_first_token_ms,
                "vram_peak_bytes": r.vram_peak_bytes,
                "stability_score": r.stability_score,
                "success": r.success,
            }
            for r in results[:50]
        ],
        "total": len(results),
    }


@router.get("/stats")
async def get_stats():
    if _registry is None:
        return {"error": "ModelRegistry not initialised"}
    return _registry.get_stats()
