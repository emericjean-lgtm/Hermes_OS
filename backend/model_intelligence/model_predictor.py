"""Model Predictor for Hermes OS (HOS-065).

Predicts model performance for tasks based on historical data,
model profiles, and task characteristics.
"""

from __future__ import annotations

import threading
from typing import Any

from .model_intelligence_models import (
    ModelPerformanceRecord,
    ModelProfile,
    TaskContext,
)
from .performance_analyzer import PerformanceAnalyzer


class ModelPredictor:
    """Predicts model performance for specific tasks."""

    def __init__(self, analyzer: Any = None) -> None:
        """``analyzer`` (a PerformanceAnalyzer, HOS-071 Phase B): rank_models()'s
        overall score is always built from compute_model_score() — the same
        formula ModelProfiler._score() uses for the Cockpit's ranking table
        — blended with this task's own type-fit. Replaces an independent
        third formula that used to decide every real recommendation without
        ever agreeing with either the ranking table or the documented
        Quality/Reliability/Speed/Efficiency/Benchmark weights. None (the
        default) builds a private PerformanceAnalyzer rather than reviving
        that old formula — same reasoning as ModelProfiler's own default."""
        self._lock = threading.RLock()
        self._predictions: list[dict[str, Any]] = []
        self._analyzer = analyzer or PerformanceAnalyzer()

    def predict_latency(self, profile: ModelProfile,
                        task: TaskContext) -> float:
        base_latency = profile.latency_ms if profile.latency_ms > 0 else 100.0
        complexity_factor = 1.0 + (task.complexity * 2.0)
        return base_latency * complexity_factor

    def predict_tokens_per_second(self, profile: ModelProfile,
                                   task: TaskContext) -> float:
        tps = profile.tokens_per_second
        if tps == 0:
            tps = self._estimate_tps(profile)
        complexity_penalty = 1.0 - (task.complexity * 0.3)
        return tps * max(0.5, complexity_penalty)

    def predict_success_probability(self, profile: ModelProfile,
                                     records: list[ModelPerformanceRecord],
                                     task: TaskContext) -> float:
        if records:
            success_rate = sum(1 for r in records if r.success) / len(records)
        else:
            success_rate = profile.historical_success_rate or 0.5
        task_fit = profile.task_scores.get(task.task_type.value, 0.5)
        return min(1.0, (success_rate * 0.6 + task_fit * 0.4))

    def predict_vram_usage(self, profile: ModelProfile,
                            task: TaskContext) -> int:
        """L'empreinte declaree du modele, sans multiplicateur invente (§6.1).

        ## Ce que cette methode faisait

            context_mult = min(2.0, task.complexity + 1.0)
            return int(base_vram * context_mult)

        Elle multipliait une empreinte **mesuree** par 1,3 a 2,0 selon
        `task.complexity` — qui est le **nombre de mots du titre de la
        tache** (`_infer_complexity` : >30 mots -> 0,8 ; >15 -> 0,5 ; sinon
        0,3). La longueur d'une phrase decidait donc si un modele tenait
        sur la carte.

        ## Pourquoi c'etait faux, mesure

        Le cache KV est alloue a la taille de la **fenetre**, pas a celle du
        prompt. A-18 l'a mesure sur `lfm2.5-2.6b-125k` : 2,02 Gio a
        `num_ctx` 16384 et 4,33 a 131072 — c'est le contexte servi qui
        change l'empreinte, et il est deja dans le chiffre declare. R-6 a
        mesure ce que l'usage reel y ajoute : entre un cache vide et un
        cache rempli de 3 210 jetons, 14,954 -> 15,115 Gio, soit **+1 %**.
        Le multiplicateur en inventait jusqu'a +100 %.

        ## Ce que cela produisait

        Mesure sur le catalogue reel, `code_generation`, plafond 15 000 Mo :
        les cinq modeles capables etaient elimines — `gpt-oss-20b-64k`
        declare 13 342 Mo, le multiplicateur en annoncait 17 344 — et seul
        `lfm2.5-2.6b-125k` survivait. Le classement, lui, etait juste :
        sans le filtre, gpt-oss sort a 0,672 contre 0,434, avec un
        `task_score` de 1,00 contre 0,28.

        Le motif rendu disait « Low VRAM footprint » : le modele n'avait pas
        ete choisi pour sa sobriete, les autres avaient ete elimines par une
        estimation gonflee.

        ## L'invariant

        La capacite se decide **une fois**. `ResourceManager` en est
        l'autorite depuis R-3 ; le catalogue porte l'empreinte declaree
        depuis A-18. Une troisieme estimation, ici, en faisait une seconde
        autorite silencieuse — et c'est elle qui gagnait.
        """
        return int(profile.vram_required_mb)

    def rank_models(self, profiles: list[ModelProfile],
                     records: list[ModelPerformanceRecord],
                     task: TaskContext) -> list[dict[str, Any]]:
        scored = []
        for profile in profiles:
            latency = self.predict_latency(profile, task)
            tps = self.predict_tokens_per_second(profile, task)
            success_prob = self.predict_success_probability(profile, records, task)
            vram = self.predict_vram_usage(profile, task)

            if vram > task.max_vram_mb:
                continue
            if latency > task.max_latency_ms:
                continue

            task_score = profile.task_scores.get(task.task_type.value, 0.5)
            # The same general "how good is this model" score the Cockpit's
            # ranking table shows (HOS-071 Phase B), with this task's own
            # type-fit layered on top — the one per-task dimension the
            # general score deliberately doesn't carry.
            general_score = self._analyzer.compute_model_score(profile, records)
            overall = general_score * 0.75 + task_score * 0.25

            scored.append({
                "model_id": profile.model_id,
                "name": profile.name,
                "score": round(overall, 3),
                "confidence": round(success_prob, 3),
                "estimated_latency_ms": int(latency),
                "estimated_tps": round(tps, 1),
                "estimated_vram_mb": vram,
                "task_score": round(task_score, 3),
                "parameters_b": profile.parameters_b,
                "reason": self._generate_reason(profile, task_score, success_prob, vram),
            })

        scored.sort(key=lambda x: -x["score"])
        return scored

    def _estimate_tps(self, profile: ModelProfile) -> float:
        params = profile.parameters_b
        if params <= 3:
            return 80.0
        if params <= 7:
            return 50.0
        if params <= 14:
            return 35.0
        if params <= 30:
            return 25.0
        if params <= 70:
            return 15.0
        return 8.0

    def _generate_reason(self, profile: ModelProfile, task_score: float,
                         success_prob: float, vram: int) -> str:
        parts = []
        if task_score > 0.85:
            parts.append(f"Excellent task fit ({task_score:.0%})")
        elif task_score > 0.7:
            parts.append(f"Good task fit ({task_score:.0%})")
        if success_prob > 0.85:
            parts.append(f"High reliability ({success_prob:.0%})")
        if vram <= 4000:
            parts.append("Low VRAM footprint")
        return " · ".join(parts) if parts else "Reasonable choice"

    def log_prediction(self, model_id: str, task_type: str,
                        confidence: float, selected: bool) -> None:
        self._predictions.append({
            "model_id": model_id,
            "task_type": task_type,
            "confidence": confidence,
            "selected": selected,
        })
        if len(self._predictions) > 500:
            self._predictions = self._predictions[-500:]

    def get_prediction_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._predictions[-limit:]
