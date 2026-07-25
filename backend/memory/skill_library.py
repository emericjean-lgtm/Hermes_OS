"""Skill library — cahier des charges §20 (self-evolution), §24.3 (skills table).

Skills are reusable procedures extracted from successfully completed
tasks (see backend/self_evolution/skill_extractor.py). This module is
plain SQLAlchemy CRUD, no policy, mirroring episodic.py's split between
storage and the modules that decide what to store — "is this skill
validated" is a threshold comparison against .env's
SKILL_AUTO_VALIDATE_THRESHOLD/SKILL_MIN_CONFIDENCE, computed at read
time (see status_for()) rather than stored, so changing the threshold
re-classifies every existing skill without a migration.

Column names follow this codebase's existing conventions rather than
the cahier des charges' literal schema string (§24.3's `success` becomes
`successes`, an int count, to read unambiguously next to `uses`).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.memory.db import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    procedure: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float)
    decay: Mapped[float] = mapped_column(Float, default=0.0)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    successes: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[str] = mapped_column(String, default="")  # comma-separated
    source_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    @property
    def tags_list(self) -> list[str]:
        return [t for t in self.tags.split(",") if t]


def status_for(confidence: float, *, min_confidence: float, auto_validate_threshold: float) -> str:
    """§20: "une skill n'est appliquée automatiquement qu'au-dessus du
    seuil de confiance ; sinon elle reste « en révision »" — plus a
    third bucket below SKILL_MIN_CONFIDENCE, low enough it shouldn't be
    surfaced for reuse at all."""
    if confidence >= auto_validate_threshold:
        return "validated"
    if confidence >= min_confidence:
        return "in_review"
    return "below_floor"


def create_skill(
    session: Session,
    *,
    name: str,
    description: str = "",
    procedure: str = "",
    confidence: float,
    tags: list[str] | None = None,
    project_id: str | None = None,
    source_task_id: str | None = None,
) -> Skill:
    now = datetime.now(UTC)
    skill = Skill(
        id=str(uuid.uuid4()),
        project_id=project_id,
        name=name,
        description=description,
        procedure=procedure,
        confidence=confidence,
        decay=0.0,
        uses=0,
        successes=0,
        tags=",".join(tags or []),
        source_task_id=source_task_id,
        created_at=now,
        updated_at=now,
    )
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return skill


def get_skill(session: Session, skill_id: str) -> Skill | None:
    return session.get(Skill, skill_id)


def get_skill_by_name(session: Session, name: str, *, project_id: str | None = None) -> Skill | None:
    """Case-insensitive exact match, scoped to a project (or the global/
    no-project scope when project_id is None) — the deterministic half
    of skill dedup (see self_evolution/pipeline.py): a task with the
    same title recurring shouldn't spawn a fresh near-identical skill
    every time, it should reinforce the one that already exists."""
    stmt = select(Skill).where(
        Skill.project_id == project_id, Skill.name.ilike(name.strip())
    )
    return session.execute(stmt).scalars().first()


def list_skills(
    session: Session, *, project_id: str | None = None, tag: str | None = None
) -> list[Skill]:
    stmt = select(Skill).order_by(Skill.confidence.desc())
    if project_id is not None:
        stmt = stmt.where(Skill.project_id == project_id)
    skills = list(session.execute(stmt).scalars())
    if tag is not None:
        skills = [s for s in skills if tag in s.tags_list]
    return skills


def record_use(session: Session, skill_id: str, *, success: bool, reinforcement: float = 0.05) -> Skill | None:
    """§11.6: "les remontées d'usage le renforcent" — a successful reuse
    nudges confidence toward 1.0, a failed one toward 0.0, both by
    `reinforcement`, clamped to [0, 1]. The other half of §11.6 (time-
    based forgetting for *unused* skills) is apply_decay() below."""
    skill = session.get(Skill, skill_id)
    if skill is None:
        return None
    skill.uses += 1
    if success:
        skill.successes += 1
        skill.confidence = min(1.0, round(skill.confidence + reinforcement, 4))
    else:
        skill.confidence = max(0.0, round(skill.confidence - reinforcement, 4))
    skill.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(skill)
    return skill


def apply_decay(session: Session, *, rate: float = 0.01) -> int:
    """Ebbinghaus-style forgetting curve (§11.6), meant to be called
    periodically (e.g. once per process start — there is no scheduled-
    job runner in this project yet) rather than per-request. Returns how
    many skills were touched. Gated by .env's EBBINGHAUS_DECAY_ENABLED
    at the caller (EchoAgent.decay_skills), not here — this function is
    unconditional so tests don't depend on that setting."""
    skills = list(session.execute(select(Skill)).scalars())
    for skill in skills:
        skill.decay = round(skill.decay + rate, 4)
        skill.confidence = max(0.0, round(skill.confidence - rate, 4))
        skill.updated_at = datetime.now(UTC)
    session.commit()
    return len(skills)


def delete_skill(session: Session, skill_id: str) -> bool:
    skill = session.get(Skill, skill_id)
    if skill is None:
        return False
    session.delete(skill)
    session.commit()
    return True
