"""Deterministic slash commands for the Hermes Ollama backend.

Why these exist: under Hermes Agent's real (long, coding-agent-flavored)
system prompt, neither devstral nor qwen3-coder:30b reliably calls the
right MCP tool for a plain-language request — they narrate without
calling anything, or misread the request as an instruction to go do the
thing the text describes. See README.md's "Telegram gateway" section for
the full diagnostic trail. A slash command sidesteps the model's judgment
entirely, one action at a time.

The approval commands matter most on a phone. With the shipped
`autonomy_level: low`, every mutating action waits for a human, and until
now the only place to answer was the dashboard. `/attente` and `/ok` put
that within reach of the device you actually have on you.

**Index stability is load-bearing here.** `/attente` numbers the queue
oldest-first, not newest-first, on purpose: a refusal arriving between
listing and answering then appends at the end instead of shifting every
number — approving the wrong action because the list moved would be a
security bug, not a UI annoyance. `/ok` and `/non` also echo back *what*
they decided rather than just "done", so a shift caused by something else
being decided is visible instead of silent. An 8-character id prefix is
accepted too, for when precision matters more than typing comfort.
"""

import json


def _as_data(result):
    """MCP tool results arrive as either a parsed object or a JSON string
    depending on the tool's declared output schema — normalise both."""
    if isinstance(result, str):
        try:
            return json.loads(result)
        except ValueError:
            return None
    return result


def handle_tache(ctx, raw_args: str) -> str:
    title = raw_args.strip()
    if not title:
        return "Usage : /tache <titre de la tâche>"

    data = _as_data(ctx.dispatch_tool("mcp__hermes_ollama__tasks_create", {"title": title}))
    if isinstance(data, dict) and data.get("id"):
        return f'Tâche Kronos créée : "{title}" (id: {data["id"]})'
    return f"Tâche créée. Réponse : {data}"


def _pending(ctx):
    """Pending approvals, oldest first — see the module docstring on why
    the ordering is load-bearing."""
    data = _as_data(
        ctx.dispatch_tool("mcp__hermes_ollama__approvals_list", {"status": "pending"})
    )
    if not isinstance(data, list):
        return []
    return sorted(data, key=lambda a: a.get("created_at") or "")


def handle_attente(ctx, raw_args: str) -> str:
    entries = _pending(ctx)
    if not entries:
        return "Rien en attente de validation."

    lines = [f"{len(entries)} action(s) en attente :", ""]
    for i, entry in enumerate(entries, start=1):
        lines.append(f"{i}. [{entry['action_type']}] {entry['description']}")
        # The reason Aegis gave is the whole point of showing this at all:
        # approving without it is rubber-stamping.
        lines.append(f"   → {entry['reason']}")
        lines.append(f"   demandé par {entry['requesting_agent']} · id {entry['id'][:8]}")
        lines.append("")
    lines.append("/ok <n> pour approuver · /non <n> pour refuser")
    return "\n".join(lines)


def _resolve(entries, token: str):
    """Accept either a 1-based index or an id prefix."""
    token = token.strip()
    if not token:
        return None
    if token.isdigit():
        index = int(token)
        return entries[index - 1] if 1 <= index <= len(entries) else None
    matches = [e for e in entries if e["id"].startswith(token)]
    return matches[0] if len(matches) == 1 else None


def _decide(ctx, raw_args: str, *, approved: bool) -> str:
    verb = "/ok" if approved else "/non"
    entries = _pending(ctx)
    if not entries:
        return "Rien en attente de validation."

    entry = _resolve(entries, raw_args)
    if entry is None:
        return (
            f"Usage : {verb} <n> (numéro affiché par /attente) ou {verb} <id>.\n"
            f"Il y a {len(entries)} action(s) en attente."
        )

    _as_data(
        ctx.dispatch_tool(
            "mcp__hermes_ollama__approvals_decide",
            {"approval_id": entry["id"], "approved": approved},
        )
    )

    # Echo the description back: if the queue shifted between listing and
    # answering, this is what makes it visible instead of silent.
    if approved:
        return (
            f"Approuvé : {entry['description']}\n"
            "Valable une seule fois et l'autorisation expire — "
            "l'agent doit relancer l'action maintenant."
        )
    return f"Refusé : {entry['description']}"


def handle_ok(ctx, raw_args: str) -> str:
    return _decide(ctx, raw_args, approved=True)


def handle_non(ctx, raw_args: str) -> str:
    return _decide(ctx, raw_args, approved=False)


def register(ctx):
    ctx.register_command(
        "tache",
        lambda raw: handle_tache(ctx, raw),
        description="Créer une tâche Kronos directement (sans passer par le LLM)",
    )
    ctx.register_command(
        "attente",
        lambda raw: handle_attente(ctx, raw),
        description="Lister les actions en attente de ta validation (Aegis)",
    )
    ctx.register_command(
        "ok",
        lambda raw: handle_ok(ctx, raw),
        description="Approuver une action en attente : /ok <n>",
    )
    ctx.register_command(
        "non",
        lambda raw: handle_non(ctx, raw),
        description="Refuser une action en attente : /non <n>",
    )
