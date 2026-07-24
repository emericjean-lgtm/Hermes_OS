"""GET /messages — read access to the inter-agent message bus's trace
(cahier des charges §9.2, §24.4). Publishing happens inside the agents
that emit messages (see agents/aegis.py), not through this route — this
is query-only, the same "consult, don't drive" role /tasks and /memory
play for their own stores.

Returns plain dicts (via BusMessage.to_dict()) rather than a Pydantic
response model: the spec's exact contract is
{ id, from, to, type, payload, timestamp, task_id }, and "from" isn't a
valid Python/Pydantic field name — a dict sidesteps needing an alias.
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.core.message_bus import get_message_bus

router = APIRouter()


@router.get("/messages")
async def list_messages(
    task_id: str | None = None,
    agent: str | None = None,
    project_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    messages = get_message_bus().list_messages(
        task_id=task_id, agent=agent, project_id=project_id, limit=limit
    )
    return [m.to_dict() for m in messages]
