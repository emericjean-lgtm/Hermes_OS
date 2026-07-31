"""Skill models for the Dynamic Skill Distribution Engine (HOS-048)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4


# ── Enums ────────────────────────────────────────────────────

class SkillCategory(str, Enum):
    CODING = "coding"
    REASONING = "reasoning"
    WRITING = "writing"
    ANALYSIS = "analysis"
    SECURITY = "security"
    DEPLOYMENT = "deployment"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    GENERAL = "general"


class SkillDomain(str, Enum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    DEVOPS = "devops"
    DATA = "data"
    AI_ML = "ai_ml"
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    INFRASTRUCTURE = "infrastructure"


class SkillStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"
    DISABLED = "disabled"


class LoadState(str, Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    UNLOADING = "unloading"
    ERROR = "error"


class CacheStrategy(str, Enum):
    LRU = "lru"
    TTL = "ttl"
    PRIORITY = "priority"
    NONE = "none"


# ── Dataclasses ──────────────────────────────────────────────

@dataclass
class SkillDefinition:
    """A registered skill — what it does, its cost, its dependencies."""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    version: str = "1.0.0"
    author: str = "hermes-os"
    description: str = ""
    category: SkillCategory = SkillCategory.GENERAL
    domain: SkillDomain = SkillDomain.BACKEND
    tags: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # skill IDs
    status: SkillStatus = SkillStatus.ACTIVE
    # Cost estimates
    memory_cost_mb: float = 0.0
    token_cost_estimate: int = 0
    vram_cost_mb: float = 0.0
    # Quality metrics
    quality_score: float = 0.0  # 0.0–1.0
    usage_count: int = 0
    success_count: int = 0
    success_rate: float = 0.0  # derived
    avg_duration_ms: float = 0.0
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if self.success_count > 0 and self.usage_count > 0:
            self.success_rate = self.success_count / self.usage_count


@dataclass
class SkillInstance:
    """A loaded instance of a skill — tracks runtime state."""
    id: str = field(default_factory=lambda: str(uuid4()))
    skill_id: str = ""
    load_state: LoadState = LoadState.UNLOADED
    loaded_at: Optional[datetime] = None
    unloaded_at: Optional[datetime] = None
    current_memory_mb: float = 0.0
    current_tokens: int = 0
    agent_id: Optional[str] = None
    mission_id: Optional[str] = None


@dataclass
class SkillSelection:
    """Result of an automatic skill selection."""
    skill_id: str = ""
    skill_name: str = ""
    relevance_score: float = 0.0  # 0.0–1.0
    justification: str = ""
    priority: int = 0
    estimated_cost_mb: float = 0.0
    estimated_tokens: int = 0


@dataclass
class SkillDistribution:
    """A distribution of skills across agents for a mission."""
    id: str = field(default_factory=lambda: str(uuid4()))
    mission_id: str = ""
    assignments: dict[str, list[SkillSelection]] = field(default_factory=dict)  # agent_id → skills
    total_memory_mb: float = 0.0
    total_tokens: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SkillCacheEntry:
    """A cached skill entry."""
    skill_id: str = ""
    loaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    use_count: int = 0
    ttl_seconds: float = 300.0  # 5 min default
    priority: int = 0


@dataclass
class SkillProfile:
    """Runtime performance profile of a skill."""
    skill_id: str = ""
    avg_load_time_ms: float = 0.0
    avg_memory_mb: float = 0.0
    avg_tokens: int = 0
    avg_duration_ms: float = 0.0
    max_memory_mb: float = 0.0
    failure_rate: float = 0.0
    last_profiled: Optional[datetime] = None
    sample_count: int = 0


@dataclass
class DependencyGraph:
    """Resolved dependency graph for a set of skills."""
    skill_ids: set[str] = field(default_factory=set)
    adjacency: dict[str, set[str]] = field(default_factory=dict)  # skill_id → dep_ids
    resolved_order: list[str] = field(default_factory=list)  # topological sort
    conflicts: list[str] = field(default_factory=list)
    circular_deps: list[list[str]] = field(default_factory=list)
