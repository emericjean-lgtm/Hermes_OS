"""Project memory — cahier des charges §12, the middle of the three levels.

§12 splits memory three ways:

  - **mémoire courte** — the current conversation. Not this backend's
    concern: the agent runtime owns the live session (Hermes Agent has
    its own session store), and duplicating it here would create two
    sources of truth for the same turn.
  - **mémoire projet** — architecture, roadmap, décisions, documentation.
  - **mémoire permanente** — préférences, historique, habitudes, règles.

Storage for all of it already existed (`memory_long`, episodic.py, with a
`project_id` column). What did not exist was any way to tell the levels
apart: `type` is a free-form string, so "this project's architecture" and
"the user's standing preferences" were indistinguishable rows, and there
was no way to load a project's memory *as a whole* before starting work
on it.

This module adds the vocabulary and one grouped read. It deliberately
does **not** add validation that rejects unknown types: entries predating
it (and legitimate ad-hoc types) must keep working, so an unrecognised
type classifies as UNCLASSIFIED rather than raising. A vocabulary that
breaks existing data on introduction is a migration, not a vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy.orm import Session

from backend.memory import episodic
from backend.memory.episodic import MemoryEntry


class MemoryLevel(StrEnum):
    PROJECT = "project"
    PERMANENT = "permanent"
    # Anything whose type isn't in the §12 vocabulary. Not an error —
    # see the module docstring.
    UNCLASSIFIED = "unclassified"


# §12's own words, mapped to the type strings already in use where they
# exist (`decision` and `preference` are both live in the codebase, so
# they keep their spelling rather than being renamed for tidiness).
PROJECT_TYPES: tuple[str, ...] = ("architecture", "roadmap", "decision", "documentation")
PERMANENT_TYPES: tuple[str, ...] = ("preference", "habit", "rule", "history")

_LEVELS: dict[str, MemoryLevel] = {
    **{t: MemoryLevel.PROJECT for t in PROJECT_TYPES},
    **{t: MemoryLevel.PERMANENT for t in PERMANENT_TYPES},
}


@dataclass(frozen=True)
class ProjectBrief:
    """A project's memory, grouped the way §12 describes it.

    `by_type` holds only the §12 project types, always with all four keys
    present (empty lists included) so a caller can render a stable
    structure without checking for missing sections. `other` collects
    entries scoped to this project whose type falls outside the
    vocabulary — surfaced rather than silently dropped, because a typo'd
    type would otherwise make an entry invisible.
    """

    project_id: str
    by_type: dict[str, list[dict]] = field(default_factory=dict)
    other: list[dict] = field(default_factory=list)
    total: int = 0


def level_for(type_: str) -> MemoryLevel:
    """Which §12 level a memory type belongs to."""
    return _LEVELS.get(type_.strip().lower(), MemoryLevel.UNCLASSIFIED)


def known_types() -> dict[str, list[str]]:
    """The vocabulary, for callers that want to offer a choice rather
    than have the user guess a free-form string."""
    return {
        MemoryLevel.PROJECT.value: list(PROJECT_TYPES),
        MemoryLevel.PERMANENT.value: list(PERMANENT_TYPES),
    }


def _entry_to_dict(entry: MemoryEntry) -> dict:
    return {
        "id": entry.id,
        "type": entry.type,
        "level": level_for(entry.type).value,
        "content": entry.content,
        "tags": [t for t in entry.tags.split(",") if t],
        "confidence": entry.confidence,
        "created_at": entry.created_at.isoformat(),
    }


def project_brief(session: Session, project_id: str) -> ProjectBrief:
    """Load everything remembered about one project, grouped by §12 type.

    The point of this over `list_memories(project_id=...)` is shape: an
    agent about to work on a project wants "what is the architecture, what
    is on the roadmap, what has already been decided" as separate
    sections, not one undifferentiated list it has to sort itself.

    Scoped strictly to `project_id`: permanent memory (preferences, rules)
    is deliberately NOT folded in, even though it also applies — mixing
    the two is how a project-specific decision ends up being applied
    globally later.
    """
    entries = episodic.list_memories(session, project_id=project_id)

    by_type: dict[str, list[dict]] = {t: [] for t in PROJECT_TYPES}
    other: list[dict] = []
    for entry in entries:
        payload = _entry_to_dict(entry)
        if entry.type in by_type:
            by_type[entry.type].append(payload)
        else:
            other.append(payload)

    return ProjectBrief(
        project_id=project_id, by_type=by_type, other=other, total=len(entries)
    )
