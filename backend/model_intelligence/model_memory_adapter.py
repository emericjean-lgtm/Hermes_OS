"""Memory integration for Model Intelligence (HOS-065B).

Stores model decisions and performance in Episodic Memory,
Procedural Memory, and Knowledge Graph for continuous learning.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .model_intelligence_models import ModelDecision, ModelPerformanceRecord


# Knowledge Graph relation types
REL_MODEL_USED_FOR_TASK = "MODEL_USED_FOR_TASK"
REL_MODEL_OUTPERFORMED_MODEL = "MODEL_OUTPERFORMED_MODEL"
REL_MODEL_RECOMMENDED_BY_CONTEXT = "MODEL_RECOMMENDED_BY_CONTEXT"


class ModelMemoryAdapter:
    """Bridges Model Intelligence with Unified Memory (HOS-047)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # In-memory stores (simulating Episodic/Procedural/Knowledge stores)
        self._episodic_memory: list[dict[str, Any]] = []
        self._procedural_memory: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._knowledge_graph: list[dict[str, Any]] = []
        self._max_memory = 2000

    # ── Episodic Memory ──────────────────────────────────────────

    def store_execution_episode(self, record: ModelPerformanceRecord) -> None:
        """Store execution as an episodic memory."""
        episode = {
            "model_id": record.model_id,
            "task_type": record.task_type.value if hasattr(record.task_type, "value") else str(record.task_type),
            "duration_ms": record.duration_ms,
            "tokens_used": record.tokens_used,
            "success": record.success,
            "error_type": record.error_type,
            "timestamp": record.timestamp,
        }

        with self._lock:
            self._episodic_memory.append(episode)
            if len(self._episodic_memory) > self._max_memory:
                self._episodic_memory.pop(0)

    def store_decision_episode(
        self,
        decision: ModelDecision,
        task_description: str,
        success: bool = False,
    ) -> None:
        """Store a model selection decision as episodic memory."""
        episode = {
            "model_id": decision.model_id,
            "model_name": decision.model_name,
            "runtime": str(decision.runtime),
            "quantization": str(decision.quantization),
            "confidence": decision.confidence,
            "reason": decision.reason,
            "task_description": task_description,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            self._episodic_memory.append(episode)
            if len(self._episodic_memory) > self._max_memory:
                self._episodic_memory.pop(0)

    def query_episodic_memory(
        self,
        model_id: str | None = None,
        task_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Query episodic memory for model executions."""
        with self._lock:
            results = self._episodic_memory
            if model_id:
                results = [r for r in results if r.get("model_id") == model_id]
            if task_type:
                results = [r for r in results if r.get("task_type") == task_type]
            return results[-limit:]

    # ── Procedural Memory ────────────────────────────────────────

    def learn_effective_rule(self, pattern: str, recommendation: dict[str, Any]) -> None:
        """Store an effective decision rule in procedural memory.

        Example: "For Python refactoring tasks, prefer DeepSeek Coder 16B"
        """
        rule = {
            "pattern": pattern,
            "recommendation": recommendation,
            "confidence": recommendation.get("confidence", 0.5),
            "success_count": 1,
            "failure_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            self._procedural_memory[pattern].append(rule)
            if len(self._procedural_memory[pattern]) > 10:
                self._procedural_memory[pattern].pop(0)

    def reinforce_rule(self, pattern: str, index: int = -1, success: bool = True) -> None:
        """Reinforce or weaken a procedural rule based on outcome."""
        with self._lock:
            rules = self._procedural_memory.get(pattern, [])
            if rules and 0 <= index < len(rules):
                rule = rules[index]
                if success:
                    rule["success_count"] += 1
                else:
                    rule["failure_count"] += 1
                rule["confidence"] = rule["success_count"] / max(
                    rule["success_count"] + rule["failure_count"], 1
                )

    def query_procedural_memory(self, pattern: str) -> list[dict[str, Any]]:
        """Query procedural memory for matching patterns."""
        with self._lock:
            exact = list(self._procedural_memory.get(pattern, []))

            # Fuzzy match: find patterns that contain keywords from the query
            fuzzy: list[dict[str, Any]] = []
            query_keywords = set(pattern.lower().split())
            for mem_pattern, rules in self._procedural_memory.items():
                if mem_pattern == pattern:
                    continue
                mem_keywords = set(mem_pattern.lower().split())
                if query_keywords & mem_keywords:  # Any keyword overlap
                    fuzzy.extend(rules)

            # Sort by confidence descending
            all_rules = exact + fuzzy
            all_rules.sort(key=lambda r: -r["confidence"])
            return all_rules[:5]

    # ── Knowledge Graph ──────────────────────────────────────────

    def add_kg_relation(
        self,
        relation_type: str,
        source: str,
        target: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a relation to the knowledge graph."""
        relation = {
            "type": relation_type,
            "source": source,
            "target": target,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            self._knowledge_graph.append(relation)
            if len(self._knowledge_graph) > self._max_memory:
                self._knowledge_graph.pop(0)

    def record_model_for_task(self, model_id: str, task_type: str, success: bool) -> None:
        """Record MODEL_USED_FOR_TASK relation."""
        self.add_kg_relation(
            REL_MODEL_USED_FOR_TASK,
            source=model_id,
            target=task_type,
            metadata={"success": success},
        )

    def record_outperformance(self, winner: str, loser: str, context: str) -> None:
        """Record MODEL_OUTPERFORMED_MODEL relation."""
        self.add_kg_relation(
            REL_MODEL_OUTPERFORMED_MODEL,
            source=winner,
            target=loser,
            metadata={"context": context},
        )

    def query_knowledge_graph(
        self,
        relation_type: str | None = None,
        source: str | None = None,
        target: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query knowledge graph relations."""
        with self._lock:
            results = self._knowledge_graph
            if relation_type:
                results = [r for r in results if r["type"] == relation_type]
            if source:
                results = [r for r in results if r["source"] == source]
            if target:
                results = [r for r in results if r["target"] == target]
            return list(results)

    def get_best_model_for_task(self, task_type: str) -> str | None:
        """Query KG to find the best model for a task type."""
        relations = self.query_knowledge_graph(
            relation_type=REL_MODEL_USED_FOR_TASK,
            target=task_type,
        )
        if not relations:
            return None

        # Count successes per model
        model_scores: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"success": 0, "total": 0})
        for rel in relations:
            mid = rel["source"]
            model_scores[mid]["total"] += 1
            if rel["metadata"].get("success"):
                model_scores[mid]["success"] += 1

        # Find model with best success rate (min 3 uses)
        best_model = None
        best_rate = 0
        for mid, scores in model_scores.items():
            if scores["total"] >= 3:
                rate = scores["success"] / scores["total"]
                if rate > best_rate:
                    best_rate = rate
                    best_model = mid

        return best_model

    def get_stats(self) -> dict[str, Any]:
        """Get memory adapter statistics."""
        with self._lock:
            return {
                "episodic_entries": len(self._episodic_memory),
                "procedural_patterns": len(self._procedural_memory),
                "knowledge_graph_relations": len(self._knowledge_graph),
            }
