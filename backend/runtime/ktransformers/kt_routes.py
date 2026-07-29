"""KTransformers REST API — HOS-052C final."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.runtime.ktransformers.kt_models import (
    KTBackend,
    KTInferenceRequest,
    KTLoadConfig,
    KTModelStatus,
    KTQuantization,
)
from backend.runtime.ktransformers.kt_runtime import get_kt_runtime

router = APIRouter(prefix="/runtime/ktransformers", tags=["ktransformers"])


@router.get("/models")
def list_models(
    status: Optional[KTModelStatus] = Query(None),
    backend: Optional[KTBackend] = Query(None),
    quantization: Optional[KTQuantization] = Query(None),
):
    rt = get_kt_runtime()
    models = rt.list_models(status=status, backend=backend, quantization=quantization)
    return {
        "total": len(models),
        "models": [
            {"id": m.id, "name": m.name, "full_name": m.full_name, "architecture": m.architecture,
             "num_parameters": m.num_parameters, "active_parameters": m.active_parameters,
             "size_gb": m.size_gb, "quantization": m.quantization.value, "backend": m.backend.value,
             "status": m.status.value, "vram_required_gb": m.vram_required_gb,
             "ram_required_gb": m.ram_required_gb, "context_length": m.context_length,
             "is_moe": m.is_moe, "supports_moe_offloading": m.supports_moe_offloading, "source": m.source,
             "registered_at": m.registered_at.isoformat() if m.registered_at else None,
             "loaded_at": m.loaded_at.isoformat() if m.loaded_at else None}
            for m in models
        ],
    }


@router.get("/models/{model_id}")
def get_model(model_id: str):
    rt = get_kt_runtime()
    model = rt.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return {
        "id": model.id, "name": model.name, "full_name": model.full_name,
        "architecture": model.architecture, "num_parameters": model.num_parameters,
        "size_gb": model.size_gb, "quantization": model.quantization.value,
        "backend": model.backend.value, "status": model.status.value,
        "vram_required_gb": model.vram_required_gb, "ram_required_gb": model.ram_required_gb,
        "context_length": model.context_length, "is_moe": model.is_moe,
        "supports_rocm": model.supports_rocm, "supports_cuda": model.supports_cuda,
        "supports_moe_offloading": model.supports_moe_offloading, "source": model.source,
    }


@router.post("/discover")
def discover():
    rt = get_kt_runtime()
    models = rt.discover_and_register()
    return {"discovered": len(models), "models": [{"id": m.id, "name": m.name} for m in models]}


@router.post("/load")
def load_model(config: dict):
    rt = get_kt_runtime()
    model_id = config.get("model_id", "")
    load_cfg = KTLoadConfig(
        model_id=model_id,
        backend=KTBackend(config.get("backend")) if config.get("backend") else None,
        n_gpu_layers=config.get("n_gpu_layers", 0),
        context_length=config.get("context_length"),
        use_moe_offloading=config.get("use_moe_offloading", False),
    )
    ok, msg = rt.load_model(model_id, load_cfg)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "loaded", "model_id": model_id, "message": msg}


@router.post("/unload")
def unload_model(config: dict):
    rt = get_kt_runtime()
    model_id = config.get("model_id", "")
    if not rt.unload_model(model_id):
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return {"status": "unloaded", "model_id": model_id}


@router.post("/infer")
def infer(request: dict):
    rt = get_kt_runtime()
    req = KTInferenceRequest(
        model_id=request["model_id"],
        prompt=request["prompt"],
        max_tokens=request.get("max_tokens", 2048),
        temperature=request.get("temperature", 0.7),
        top_p=request.get("top_p", 0.95),
    )
    result = rt.infer(req)
    if result.error:
        raise HTTPException(status_code=500, detail=result.error)
    return {
        "model_id": result.model_id, "text": result.text,
        "tokens_generated": result.tokens_generated, "tokens_per_second": result.tokens_per_second,
        "time_to_first_token_ms": result.time_to_first_token_ms, "total_time_ms": result.total_time_ms,
        "vram_used_gb": result.vram_used_gb, "ram_used_gb": result.ram_used_gb,
        "backend_used": result.backend_used.value, "fallback_reason": result.fallback_reason.value,
    }


@router.post("/benchmark")
def run_benchmark(config: dict):
    rt = get_kt_runtime()
    result = rt.run_benchmark(
        model_id=config["model_id"],
        profile=config.get("profile", "general_chat"),
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {
        "model_id": result.model_id, "profile": result.profile,
        "backend": result.backend.value, "quantization": result.quantization.value,
        "tokens_per_second": result.tokens_per_second, "time_to_first_token_ms": result.time_to_first_token_ms,
        "vram_peak_gb": result.vram_peak_gb, "ram_peak_gb": result.ram_peak_gb, "success": result.success,
    }


@router.post("/optimize")
def optimize(config: dict):
    rt = get_kt_runtime()
    result = rt.optimize(model_id=config["model_id"], task_type=config.get("task_type", "general"))
    return {
        "model_id": result.model_id, "recommended_backend": result.recommended_backend.value,
        "recommended_quantization": result.recommended_quantization.value,
        "n_gpu_layers": result.n_gpu_layers, "context_length": result.context_length,
        "chunk_size": result.chunk_size, "use_moe_offloading": result.use_moe_offloading,
        "hot_experts": result.hot_experts,
        "fallback_chain": [f.value for f in result.fallback_chain],
        "reasoning": result.reasoning,
    }


@router.get("/orchestrator/candidates")
def orchestrator_candidates():
    rt = get_kt_runtime()
    candidates = []
    for model in rt.list_models():
        c = rt.orchestrator.as_candidate(model)
        candidates.append({
            "model_id": c.model_id, "model_name": c.model_name,
            "backend": c.backend.value, "status": c.status.value,
            "suitability_score": c.suitability_score, "vram_required_gb": c.vram_required_gb,
            "ram_required_gb": c.ram_required_gb, "max_context_length": c.max_context_length,
            "tags": c.tags,
        })
    return {"total": len(candidates), "candidates": candidates}


@router.get("/status")
def get_status():
    return get_kt_runtime().get_status()


@router.get("/statistics")
def get_statistics():
    return get_kt_runtime().get_statistics()


@router.post("/resources")
def update_resources(metrics: dict):
    get_kt_runtime().resources.update_resources(metrics)
    return {"status": "updated"}


@router.get("/events")
def get_events(limit: int = Query(default=50, ge=1, le=500)):
    history = get_kt_runtime().events.get_history()
    return {"total": len(history), "events": list(history)[-limit:]}
