"""Deterministic /tache command: create a Kronos task without going through
the LLM's tool-selection judgment.

Why this exists: under Hermes Agent's real (long, coding-agent-flavored)
system prompt, neither devstral nor qwen3-coder:30b reliably call the
tasks_create MCP tool for phrasing like "Crée une tâche : <titre>" - they
either narrate without calling anything, or misinterpret the title as an
instruction to actually go implement/configure whatever it describes. See
hermes-ollama/README.md's "Hermes Agent integration" section for the full
diagnostic trail (tool count, tool_search, native todo competition,
tool_use_enforcement, SOUL.md - all tried, none fixed this specific case).
A slash command sidesteps the model's judgment entirely for this one action.
"""

import json


def handle_tache(ctx, raw_args: str) -> str:
    title = raw_args.strip()
    if not title:
        return "Usage : /tache <titre de la tâche>"

    result = ctx.dispatch_tool("mcp__hermes_ollama__tasks_create", {"title": title})

    data = result
    if isinstance(result, str):
        try:
            data = json.loads(result)
        except ValueError:
            data = None

    if isinstance(data, dict) and data.get("id"):
        return f'Tâche Kronos créée : "{title}" (id: {data["id"]})'
    return f"Tâche créée. Réponse : {result}"


def register(ctx):
    ctx.register_command(
        "tache",
        lambda raw: handle_tache(ctx, raw),
        description="Créer une tâche Kronos directement (sans passer par le LLM)",
    )
