"""Deterministic slash commands for the Hermes Ollama backend.

Why these exist: under Hermes Agent's real (long, coding-agent-flavored)
system prompt, neither devstral nor qwen3-coder:30b reliably calls the
right MCP tool for a plain-language request — they narrate without
calling anything, or misread the request as an instruction to go do the
thing the text describes. See README.md's "Telegram gateway" section for
the full diagnostic trail. A slash command sidesteps the model's judgment
entirely, one action at a time.

The approval commands matter most on a phone. At the shipped
`autonomy_level: low`, every mutating action waits for a human, and the
dashboard is not always the device in your hand.

**These talk HTTP to the backend, not MCP — deliberately.** The first
version went through `ctx.dispatch_tool`, and that was backwards for two
reasons:

  - The MCP surface is capped. `mcp_servers.hermes-ollama.tools.include`
    keeps the tool count under ~30, above which local models stop calling
    tools at all (measured; see README.md). Slash commands never involve
    the model, so spending model-facing tool slots on them is exactly the
    wrong trade — adding /projet and /verif that way would have reached
    32 and re-broken natural-language tool use.
  - It made a plain call fragile. dispatch_tool returns a JSON string,
    and FastMCP serialises the same tool six different ways depending on
    item count and transport; /attente shipped broken twice on that alone.

Talking to the REST API directly removes both problems: one JSON shape,
no budget pressure, and a new command needs no config change. Aegis still
gates everything on the backend side, so this bypasses Hermes Agent's
tool pipeline, not the security engine — and the authority here is the
human who typed the command, not a model acting on its own.

**Index stability is load-bearing.** `/attente` numbers the queue
oldest-first, not newest-first, on purpose: a refusal arriving between
listing and answering appends at the end instead of shifting every number
— approving the wrong action because the list moved would be a security
bug, not a UI annoyance. `/ok` and `/non` echo back *what* they decided
rather than just "done", so a shift is visible instead of silent. An
8-character id prefix is accepted too, and an ambiguous one resolves to
nothing rather than being guessed.
"""

import json
import os
import urllib.error
import urllib.request

BACKEND_URL = os.environ.get("HERMES_OLLAMA_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_REPO = os.environ.get("HERMES_OLLAMA_REPO", "C:/Users/emeri/hermes-ollama")
_TIMEOUT = 30


class BackendError(Exception):
    """The backend could not be reached, or answered something unusable.

    Raised rather than returning an empty result, because the first
    version of `/attente` reported "rien en attente" whenever it failed to
    read the answer — a confident, wrong statement about a security queue,
    which is worse than an error precisely because it looks like it
    worked.
    """


def _request(method: str, path: str, body=None):
    url = f"{BACKEND_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310 - fixed local base URL
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("detail", exc.reason)
        except Exception:  # noqa: BLE001 - an error body can be anything
            detail = exc.reason
        raise BackendError(f"{exc.code} — {detail}") from exc
    except urllib.error.URLError as exc:
        raise BackendError(
            f"backend injoignable sur {BACKEND_URL} ({exc.reason}). "
            "Lance : uvicorn backend.main:app --host 0.0.0.0 --port 8000"
        ) from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise BackendError(str(exc)) from exc


def _get(path: str):
    return _request("GET", path)


def _post(path: str, body):
    return _request("POST", path, body)


def _fail(exc: BackendError) -> str:
    return f"Échec : {exc}"


# ── /tache ───────────────────────────────────────────────────────────
def handle_tache(raw_args: str) -> str:
    title = raw_args.strip()
    if not title:
        return "Usage : /tache <titre de la tâche>"
    try:
        task = _post("/tasks", {"title": title})
    except BackendError as exc:
        return _fail(exc)
    return f'Tâche Kronos créée : "{task["title"]}" (id {task["id"][:8]})'


# ── /projet ──────────────────────────────────────────────────────────
def handle_projet(raw_args: str) -> str:
    name = raw_args.strip()
    try:
        if not name:
            projects = _get("/projects")
            if not projects:
                return "Aucun projet. /projet <nom> pour en créer un."
            lines = [f"{len(projects)} projet(s) :", ""]
            for project in projects:
                lines.append(f"• {project['name']} [{project['status']}] · id {project['id'][:8]}")
            lines += ["", "/projet <nom> pour en créer un"]
            return "\n".join(lines)
        created = _post("/projects", {"name": name})
    except BackendError as exc:
        return _fail(exc)
    return f'Projet créé : "{created["name"]}" (id {created["id"][:8]})'


# ── /verif ───────────────────────────────────────────────────────────
def handle_verif(raw_args: str) -> str:
    """Run a whitelisted lint/build/test runner.

    With no argument this lists what may be run: the whitelist is the only
    discovery surface, and there is deliberately no way to pass a command
    or an argument through it (see config/verification.yaml).
    """
    parts = raw_args.split()
    try:
        if not parts:
            runners = _get("/verification/runners")
            lines = ["Runners disponibles :", ""]
            lines += [f"• {r['name']} ({r['kind']})" for r in runners]
            lines += ["", "/verif <runner> [chemin]  ·  défaut : le dépôt hermes-ollama"]
            return "\n".join(lines)

        runner = parts[0]
        repo = parts[1] if len(parts) > 1 else DEFAULT_REPO
        result = _post("/verification/run", {"repo_path": repo, "runner": runner})
    except BackendError as exc:
        return _fail(exc)

    if not result["ran"]:
        if result.get("verdict") == "require_human_validation":
            # The expected outcome at autonomy low. Say so plainly and
            # point at the command that unblocks it, rather than letting
            # it read as a failure.
            return (
                f"{runner} : en attente de ta validation.\n"
                f"→ {result['reason']}\n"
                "Fais /attente puis /ok <n>, et relance /verif."
            )
        return f"{runner} : non exécuté.\n→ {result['reason']}"

    verdict = "réussi" if result["passed"] else "échoué"
    lines = [f"{runner} : {verdict} (code {result['exit_code']}, {result['duration_seconds']}s)"]
    tail = (result.get("output") or "").strip().splitlines()[-3:]
    if tail:
        lines += [""] + tail
    return "\n".join(lines)


# ── /statut ──────────────────────────────────────────────────────────
def handle_statut(raw_args: str) -> str:
    try:
        status = _get("/system/status")
        models = _get("/system/models")
        tasks = _get("/tasks")
        pending = _get("/security/approvals?status=pending")
    except BackendError as exc:
        return _fail(exc)

    gpu = status.get("gpu") or {}
    by_status: dict = {}
    for task in tasks:
        by_status[task["status"]] = by_status.get(task["status"], 0) + 1

    lines = ["État du système", ""]
    if gpu.get("vram_used_gb") is not None and gpu.get("vram_total_gb"):
        lines.append(f"VRAM   {gpu['vram_used_gb']} / {gpu['vram_total_gb']} GB")
    lines.append(f"RAM    {status.get('ram_used_gb')} / {status.get('ram_total_gb')} GB")
    lines.append(f"CPU    {status.get('cpu_load_pct')}%")
    lines.append(
        f"Modèles résidents {models['loaded_count']} "
        f"(épinglés {models['always_loaded_count']})"
    )
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(by_status.items())) or "aucune"
    lines += ["", f"Tâches  {summary}"]

    # Last, because it is the only line that asks something of the reader
    # rather than informing them.
    if pending:
        lines += ["", f"⚠ {len(pending)} action(s) attendent ta validation — /attente"]
    for alert in status.get("alerts") or []:
        lines.append(f"⚠ {alert}")
    return "\n".join(lines)


# ── approvals ────────────────────────────────────────────────────────
def _pending():
    """Pending approvals, oldest first — see the module docstring on why
    the ordering is load-bearing."""
    entries = _get("/security/approvals?status=pending")
    if not isinstance(entries, list):
        raise BackendError(f"forme inattendue : {type(entries).__name__}")
    return sorted(entries, key=lambda a: a.get("created_at") or "")


def handle_attente(raw_args: str) -> str:
    try:
        entries = _pending()
    except BackendError as exc:
        return _fail(exc)
    if not entries:
        return "Rien en attente de validation."

    lines = [f"{len(entries)} action(s) en attente :", ""]
    for i, entry in enumerate(entries, start=1):
        lines.append(f"{i}. [{entry['action_type']}] {entry['description']}")
        # The reason Aegis gave is the whole point of showing this at all:
        # approving without it is rubber-stamping, and a phone screen is
        # where that temptation peaks.
        lines.append(f"   → {entry['reason']}")
        lines.append(f"   demandé par {entry['requesting_agent']} · id {entry['id'][:8]}")
        lines.append("")
    lines.append("/ok <n> pour approuver · /non <n> pour refuser")
    return "\n".join(lines)


def _resolve(entries, token: str):
    """Accept a 1-based index or an id prefix. Anything ambiguous or out
    of range resolves to nothing rather than being guessed."""
    token = token.strip()
    if not token:
        return None
    if token.isdigit():
        index = int(token)
        return entries[index - 1] if 1 <= index <= len(entries) else None
    matches = [e for e in entries if e["id"].startswith(token)]
    return matches[0] if len(matches) == 1 else None


def _decide(raw_args: str, *, approved: bool) -> str:
    verb = "/ok" if approved else "/non"
    try:
        entries = _pending()
    except BackendError as exc:
        return _fail(exc)
    if not entries:
        return "Rien en attente de validation."

    entry = _resolve(entries, raw_args)
    if entry is None:
        return (
            f"Usage : {verb} <n> (numéro affiché par /attente) ou {verb} <id>.\n"
            f"Il y a {len(entries)} action(s) en attente."
        )

    try:
        _post(f"/security/approvals/{entry['id']}", {"approved": approved})
    except BackendError as exc:
        return _fail(exc)

    if approved:
        return (
            f"Approuvé : {entry['description']}\n"
            "Valable une seule fois et l'autorisation expire — "
            "l'agent doit relancer l'action maintenant."
        )
    return f"Refusé : {entry['description']}"


def handle_ok(raw_args: str) -> str:
    return _decide(raw_args, approved=True)


def handle_non(raw_args: str) -> str:
    return _decide(raw_args, approved=False)


def register(ctx):
    for name, handler, description in (
        ("tache", handle_tache, "Créer une tâche Kronos"),
        ("projet", handle_projet, "Lister les projets, ou en créer un : /projet <nom>"),
        ("verif", handle_verif, "Lancer un runner lint/build/test : /verif <runner>"),
        ("statut", handle_statut, "État système : VRAM, modèles, tâches, validations"),
        ("attente", handle_attente, "Lister les actions en attente de ta validation"),
        ("ok", handle_ok, "Approuver une action en attente : /ok <n>"),
        ("non", handle_non, "Refuser une action en attente : /non <n>"),
    ):
        ctx.register_command(name, handler, description=description)
