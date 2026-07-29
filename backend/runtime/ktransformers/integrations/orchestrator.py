"""KT ↔ Runtime Orchestrator integration (HOS-038).

Presents KTransformers as a runtime candidate to the Adaptive Runtime
Orchestrator. KT's load_model, infer, and optimize are the native
capabilities — Hermes just routes to them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from backend.runtime.ktransformers.hermes_adapter import HermesKTAdapter
from backend.runtime.ktransformers.kt_models import KTBackend, KTModelInfo, KTModelStatus


@dataclass
class KTCandidate:
    """A KT runtime candidate for the orchestrator."""
    model_id: str
    model_name: str
    backend: KTBackend
    status: KTModelStatus
    suitability_score: float = 0.0
    vram_required_gb: float = 0.0
    ram_required_gb: float = 0.0
    supports_streaming: bool = True
    supports_tools: bool = False
    max_context_length: int = 32768
    tags: list[str] = field(default_factory=list)


class KTOchestratorIntegration:
    """Bridge: KTransformers → Runtime Orchestrator (HOS-038).

    KT does NOT reimplement orchestration. It provides:
    - as_candidate() → present as runtime option
    - can_handle_task() → capability check
    - suitability_score() → how well it fits the task
    - execute() → run the actual inference (delegates to HermesKTAdapter)
    """

    def __init__(self) -> None:
        self._adapter = HermesKTAdapter.get_instance()

    def as_candidate(self, info: KTModelInfo) -> KTCandidate:
        """Present a KT model as a runtime candidate to the orchestrator."""
        score = self._compute_base_score(info)
        return KTCandidate(
            model_id=info.id,
            model_name=info.name,
            backend=info.backend,
            status=info.status,
            suitability_score=score,
            vram_required_gb=info.vram_required_gb,
            ram_required_gb=info.ram_required_gb,
            max_context_length=info.context_length,
            tags=self._extract_tags(info),
        )

    def can_handle_task(self, info: KTModelInfo, task_type: str) -> bool:
        """Check if this model can handle a task type."""
        if info.status not in (KTModelStatus.LOADED, KTModelStatus.CACHED):
            return False

        task_lower = task_type.lower()

        # Coding tasks: prefer coding-focused models
        if "code" in task_lower or "programming" in task_lower:
            name_lower = info.name.lower()
            return any(
                kw in name_lower
                for kw in ("qwen", "deepseek", "codellama", "code", "coder", "starcoder")
            )

        # Reasoning: prefer large models, MoE
        if "reason" in task_lower or "plan" in task_lower:
            return info.is_moe or info.num_parameters and int(
                info.num_parameters.replace("B", "").replace("M", "").split("x")[-1].strip()
                or "0"
            ) >= 30

        return True  # general task

    def suitability_score(self, info: KTModelInfo, task_type: str, constraints: Optional[dict[str, Any]] = None) -> float:
        """Compute suitability score (0-1) for a task.

        Factors: backend performance, model size match, MoE vs task type, availability.
        KT natively handles the actual performance characteristics.
        """
        score = self._compute_base_score(info)

        if not self.can_handle_task(info, task_type):
            return 0.0

        # Task-type affinity
        task_lower = task_type.lower()
        name_lower = info.name.lower()

        if "code" in task_lower:
            if any(kw in name_lower for kw in ("qwen3-coder", "deepseek-coder", "codellama")):
                score += 0.15
        elif "reason" in task_lower:
            if info.is_moe:
                score += 0.10
            if "deepseek" in name_lower and "r1" in name_lower:
                score += 0.10

        # Apply constraints
        if constraints:
            max_vram = constraints.get("max_vram_gb")
            if max_vram is not None and info.vram_required_gb > max_vram:
                score -= 0.3
            max_ram = constraints.get("max_ram_gb")
            if max_ram is not None and info.ram_required_gb > max_ram:
                score -= 0.2

        return max(0.0, min(1.0, score))

    def execute(self, info: KTModelInfo, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Execute inference via KT adapter.

        Returns a dict compatible with Hermes execution result format.
        """
        from backend.runtime.ktransformers.kt_models import KTInferenceRequest

        request = KTInferenceRequest(
            model_id=info.id,
            prompt=prompt,
            max_tokens=kwargs.get("max_tokens", 2048),
            temperature=kwargs.get("temperature", 0.7),
        )
        result = self._adapter.infer(info, request)

        return {
            "text": result.text,
            "tokens_generated": result.tokens_generated,
            "tokens_per_second": result.tokens_per_second,
            "time_to_first_token_ms": result.time_to_first_token_ms,
            "total_time_ms": result.total_time_ms,
            "backend_used": result.backend_used.value,
            "vram_used_gb": result.vram_used_gb,
            "error": result.error,
        }

    def _compute_base_score(self, info: KTModelInfo) -> float:
        """Compute base suitability from model characteristics."""
        score = 0.5

        # Backend performance
        perf_scores: dict[KTBackend, float] = {
            KTBackend.AMX_INT4: 1.0, KTBackend.AMX_INT8: 0.95,
            KTBackend.AVX512_FP8_BF16: 0.85, KTBackend.AVX512_VBMI: 0.70,
            KTBackend.AVX512_VNNI: 0.65, KTBackend.AVX512_BASE: 0.50,
            KTBackend.AVX2_LLAMAFILE: 0.30, KTBackend.BLIS_AMD: 0.35,
            KTBackend.CUDA: 0.90, KTBackend.ROCM: 0.85,
            KTBackend.HYBRID: 0.60, KTBackend.CPU: 0.15,
        }
        score *= perf_scores.get(info.backend, 0.5)

        # Availability
        if info.status == KTModelStatus.LOADED:
            score *= 1.0
        elif info.status == KTModelStatus.CACHED:
            score *= 0.7
        else:
            score *= 0.2

        return score

    @staticmethod
    def _extract_tags(info: KTModelInfo) -> list[str]:
        tags: list[str] = [info.backend.value, info.quantization.value]
        if info.is_moe:
            tags.append("moe")
        if info.supports_cuda:
            tags.append("cuda")
        if info.supports_rocm:
            tags.append("rocm")
        name_lower = info.name.lower()
        for kw in ("coder", "reasoning", "chat", "vision", "embedding"):
            if kw in name_lower:
                tags.append(kw)
        return tags
