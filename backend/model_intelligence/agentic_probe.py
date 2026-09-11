"""Measures whether a model can actually drive an agent loop (HOS-095).

``ModelProfile.agentic_capable`` ranks its evidence — a measured run beats a
declaration, a declaration beats a name — but until now nothing produced the
measurement, so every answer came from the size heuristic. This module is
that missing producer.

It exists because declarations proved worthless on this deployment:
``qwen3.5:2b`` and even ``qwen3-embedding:0.6b`` both advertise ``tools`` to
Ollama, and the 2B model reliably narrates instead of acting. And the
heuristic that replaced them is not enough either: ``qwen3.5:9b-128k`` clears
the 7B floor, declares tools, is served 131072 of context — and still made
zero tool calls on a task ``devstral`` completes. Only a real run separates
those two.

The probe is deliberately the smallest task that cannot be faked: create one
file with known content. Success is read from the filesystem, never from the
model's reply — the same rule that exposed five false successes in the
mission path. A model that says "I've created the file" and creates nothing
fails here, which is exactly the behaviour being measured.

Existing benchmark machinery (BenchmarkEngine, BenchmarkScheduler) is not
reused because it measures a different thing: completion latency and token
throughput on a text prompt. Neither invokes a tool, so neither can tell a
narrator from an agent.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes_os.model_intelligence.agentic_probe")

#: The artifact the probe asks for. Short, unambiguous, and impossible to
#: satisfy by talking about it.
_PROBE_FILENAME = "AGENTIC_PROBE.md"
_PROBE_CONTENT = "probe ok"


def _probe_query(workspace: Path) -> str:
    """La consigne, formulee **comme une mission la formule** (G-14).

    ## Ce que cette requete disait, et ce que cela mesurait

        "Create a file named AGENTIC_PROBE.md in your working directory ..."

    Le repertoire n'etait nomme nulle part. Le sous-processus recoit bien
    le workspace en `cwd`, mais rien ne le **dit** au modele, qui doit donc
    deviner. Mesure le 2026-09-06 sur `lfm2.5-2.6b-125k`, reponse brute
    conservee : six appels d'outils, le bon contenu, et le fichier ecrit
    dans `/c/Users/emeri/` apres un premier essai dans `/home/user/` —
    deux conventions devinees, aucune n'etant le workspace. Verdict
    enregistre : echec.

    La sonde mesurait donc « ce modele devine-t-il la convention de chemin
    de cette machine », pas « ce modele sait-il piloter une boucle
    d'outils ». Meme modele, meme verification disque, chemin nomme :
    succes en 43 s. C'est un faux echec, de la classe que `CLAUDE.md`
    nomme — cinq des huit defauts de mesure du catalogue en etaient.

    ## Pourquoi cette formulation-ci

    Elle reprend **mot pour mot** la phrase que `_messages_for` donne a
    Hermes Agent quand une mission est liee a un workspace :

        Your working directory is '<racine>' and you have real filesystem
        access to it. Inspect before you write: do not guess paths.

    C'est le point entier de cette sonde : mesurer le chemin reel. Une
    sonde plus severe que la production mesure la sonde.

    Rien n'est affaibli : le verdict se lit toujours **sur le disque**, a
    l'endroit nomme. Un modele qui raconte au lieu d'agir ne produit
    toujours aucun fichier, et echoue toujours.
    """
    return (
        f"Your working directory is {str(workspace)!r} and you have real "
        f"filesystem access to it. Inspect before you write: do not guess "
        f"paths. Create a file named {_PROBE_FILENAME} in that directory "
        f"containing exactly one line: '{_PROBE_CONTENT}'."
    )

#: Generous: a cold model load plus a couple of tool rounds on local
#: hardware. A probe that times out is recorded as a failure, which is the
#: honest reading — a model too slow to finish is not usable for missions.
_PROBE_TIMEOUT_S = 420.0

_TOOL_CALL_RE = re.compile(r"(\d+)\s+tool calls?")


@dataclass(frozen=True)
class AgenticProbeResult:
    """One measured attempt at real agentic work."""

    model: str
    success: bool
    tool_calls: int
    duration_s: float
    artifact_verified: bool
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _probe_store_path() -> Path:
    """Ou vivent les verdicts mesures — **pas** dans `%TEMP%` (T-29).

    ## Ce que cette fonction faisait

        base = getattr(settings, "data_dir", None) or tempfile.gettempdir()

    `Settings` n'a **jamais** eu d'attribut `data_dir` : la branche etait
    morte, et le magasin atterrissait toujours dans le repertoire temporaire
    du systeme — que Windows et le moindre outil de nettoyage vident.

    ## Ce que cela a coute

    Tous les verdicts que ce projet a mesures ont disparu. HOS-095/096
    avaient sonde le catalogue — `lfm2.5-2.6b` a 3/3, `gemma4:12b` a 0/3,
    `devstral` a 1/3 — et c'est sur ces chiffres que le repli agentique a
    ete choisi. Mesure le 2026-09-06 : le fichier n'existe plus, et
    `measured_success_for` rend `None` pour les six modeles du catalogue,
    **le repli compris**.

    D'ou G-12 : la regle « substituer un repli connu-bon » s'appliquait avec
    une premisse devenue fausse, et annulait 100 % des decisions du routeur
    au profit du modele le plus faible du catalogue.

    Une mesure qui coute des minutes par modele, prise sous verrou exclusif,
    ne se range pas dans un repertoire que le systeme efface. Elle va la ou
    va le reste de l'etat durable — la meme racine que la base, les
    instantanes et la memoire, et qui honore `HERMES_DATA_DIR`.
    """
    from backend.core import etat

    # Sous `db/`, et non a la racine : `preserve_set()` enumere des
    # **dossiers**, et un fichier pose a la racine n'y serait pas — une
    # mise a jour l'effacerait, ce qui refabriquerait exactement la perte
    # que ce deplacement corrige. `test_tout_ce_qui_vit_sous_la_racine_est
    # _preserve` l'a dit des le premier essai, en lisant le code plutot que
    # la liste.
    return etat.racine() / "db" / "agentic_probe_results.json"


def load_results() -> dict[str, dict]:
    """Previously measured verdicts, keyed by model tag."""
    try:
        return json.loads(_probe_store_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_result(result: AgenticProbeResult) -> None:
    """Accumulate one trial into the model's running record.

    Accumulates rather than overwrites, because one trial is not a verdict:
    the rate across trials is what measured_success_for reads. But it
    accumulates onto the *current* fingerprint only (G-15): if the stored
    entry was measured under a different digest/num_ctx than what Ollama
    serves for this tag right now, the old trials answer for a model that
    no longer exists under this name, and folding a fresh trial into them
    would report a rate no single model ever produced. The entry resets
    instead — same policy `hermes_agent_bridge.NegociationRuntime` applies
    to its own cache, one line up the same problem: a result is only ever
    combined with results measured under the same observed state.

    If the fingerprint cannot be read (Ollama unreachable, tag unknown to
    it), the entry accumulates as before: a probe just ran successfully
    against this exact model, so a lookup failure here is an Ollama/network
    hiccup, not evidence of a change, and must not discard real trials.
    """
    try:
        path = _probe_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        results = load_results()
        entry = results.get(result.model) or {"trials": 0, "successes": 0, "runs": []}
        fingerprint = current_fingerprint(result.model)
        if fingerprint is not None and entry.get("fingerprint") not in (None, fingerprint):
            entry = {"trials": 0, "successes": 0, "runs": []}
        if fingerprint is not None:
            entry["fingerprint"] = fingerprint
        entry["trials"] = int(entry.get("trials", 0)) + 1
        entry["successes"] = int(entry.get("successes", 0)) + (1 if result.success else 0)
        entry["success_rate"] = entry["successes"] / entry["trials"]
        entry["measured_at"] = time.time()
        entry["runs"] = (entry.get("runs") or [])[-9:] + [result.as_dict()]
        results[result.model] = entry
        path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    except Exception:
        logger.debug("persisting probe result failed", exc_info=True)


#: A model must pass at least this share of its trials to be trusted with a
#: mission. Not 100%: measured here, agentic success on local hardware is
#: not deterministic — the same model and prompt can call two tools in 45s
#: or none in 305s. Not 1-in-N either, which would let a single lucky run
#: promote an unreliable model. A majority is the honest middle.
_MIN_SUCCESS_RATE = 0.6

_NUM_CTX_RE = re.compile(r"^num_ctx\s+(\d+)", re.MULTILINE)


def current_fingerprint(model: str) -> Optional[dict]:
    """What Ollama serves for `model` right now: its weights and num_ctx (G-15).

    A verdict in the store answers for *the model that was probed*, not for
    whatever now answers to the same tag. Two things can change that under
    an unchanged name: ``ollama pull``/``ollama create`` replacing the
    weights, or a Modelfile edit changing ``PARAMETER num_ctx`` — exactly
    the two conditions CLAUDE.md and the roadmap name for G-15. Both are
    read from Ollama itself rather than assumed:

    - ``digest`` comes from ``/api/tags`` — a content hash Ollama computes
      for the blob backing the tag, so identical weights always produce the
      same value and different weights never collide by chance.
    - ``num_ctx`` is parsed off the Modelfile text ``/api/show`` returns
      under ``parameters`` — the same value ``ollama show --modelfile``
      would print, not a guess from the catalogue.

    Returns None when the tag is absent from the catalogue or Ollama does
    not answer. Callers must treat that as "cannot verify freshness", never
    as "unchanged" — see measured_success_for and save_result, which both
    fail open (trust the stored verdict) rather than fail closed on a
    lookup they cannot perform. That is deliberate: the one production
    caller (service_registry._agentic_capable_cached) already required a
    successful /api/show for this exact model before it ever asks, so in
    practice this lookup fails only when a caller with no such guarantee
    (a test, a script) asks about a tag Ollama does not know.
    """
    try:
        import httpx

        from backend.core.config import get_settings

        base = get_settings().ollama_api_url.rstrip("/")
        with httpx.Client(timeout=10.0) as client:
            tags = client.get(f"{base}/api/tags").json().get("models") or []
            digest = next(
                (str(entry.get("digest")) for entry in tags
                 if entry.get("name") == model or entry.get("model") == model),
                None,
            )
            if digest is None:
                return None
            show = client.post(f"{base}/api/show", json={"model": model}).json()
    except Exception:
        return None
    match = _NUM_CTX_RE.search(str(show.get("parameters") or ""))
    return {"digest": digest, "num_ctx": int(match.group(1)) if match else None}


def _same_model_aliases(model: str) -> tuple[str, ...]:
    """Other names for *the same* model, never for a sibling.

    Ollama treats a bare name and its ``:latest`` tag as one model. Any
    other tag identifies a different set of weights — ``qwen3.5:2b`` and
    ``qwen3.5:9b-128k`` share a family name and nothing else.
    """
    if ":" not in model:
        return (f"{model}:latest",)
    name, _, tag = model.partition(":")
    return (name,) if tag == "latest" else ()


def measured_success_for(model: str) -> Optional[bool]:
    """What real runs said about this model, or None if never probed —
    or if probed under a model that no longer answers to this tag (G-15).

    Feeds ``ModelProfile.measured_agentic_success``, which outranks both the
    declaration and the size heuristic. A single trial is deliberately not
    treated as an answer: the first measurements taken on this deployment
    flipped both ways between runs, and a routing decision built on one
    sample is how a narrator gets promoted to mission brain.

    Before trusting a stored verdict, this checks it was measured under the
    weights and num_ctx Ollama serves for this tag *right now*. Nothing
    else in the store can drift out from under it that way: the trial
    counts are internal bookkeeping, and the structural signals
    (declares_tools, served_context, cpu_offload_bytes) already get re-read
    live on every call by ``_agentic_capable_cached`` — they were never
    stale, which is why the roadmap named specifically the weights and
    num_ctx as the gap. A mismatch answers None, the same as "never
    probed": a verdict for a model that no longer exists under this tag is
    not evidence about the model that does.
    """
    results = load_results()
    entry = results.get(model)
    matched_key = model
    if entry is None:
        # "devstral" and "devstral:latest" are one model to Ollama, so a
        # measurement of either answers for the other. Matching on the bare
        # family name would not be equivalent — it made qwen3.5:2b inherit
        # qwen3.5:9b-128k's 3/3 and be promoted despite never being probed
        # and being known to fail. Only the bare/:latest pair is the same
        # model; every other tag is a different one.
        for candidate in _same_model_aliases(model):
            if candidate in results:
                entry = results[candidate]
                matched_key = candidate
                break
    if entry is None:
        return None
    trials = entry.get("trials")
    if not trials:
        return None
    successes = entry.get("successes", 0)
    if trials < 2:
        return None  # one sample is noise, not a measurement

    stored_fingerprint = entry.get("fingerprint")
    if stored_fingerprint is not None:
        current = current_fingerprint(matched_key)
        # None means "cannot verify" (Ollama unreachable, tag now unknown to
        # it), not "unchanged" — fail open onto the stored verdict rather
        # than manufacture a false negative out of a lookup failure.
        if current is not None and current != stored_fingerprint:
            return None

    return (successes / trials) >= _MIN_SUCCESS_RATE


#: Serialises probes across threads *and* processes. Two probes running at
#: once put two models in VRAM simultaneously, and on a 16 GB card that
#: turns a measurement of the model into a measurement of the contention:
#: gemma4:12b was first recorded 0/3 while an lfm2.5 probe happened to be
#: running alongside it. Re-measured alone it was still 0/3, so that
#: particular verdict survived — but it survived by luck, and a benchmark
#: whose result depends on what else is running is not a benchmark.
_PROBE_LOCK = threading.Lock()


def _lock_file() -> Path:
    return Path(tempfile.gettempdir()) / "hermes_agentic_probe.lock"


@contextmanager
def _exclusive_probe():
    """Hold the probe slot, refusing rather than queueing.

    Refuses because a caller that silently waited would produce a result
    whose timing includes another model's load — the timings are part of the
    verdict here, not incidental.
    """
    if not _PROBE_LOCK.acquire(blocking=False):
        raise RuntimeError("another agentic probe is already running in this process")
    lock_path = _lock_file()
    handle = None
    try:
        try:
            handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # Stale locks outlive crashed probes; a lock older than one full
            # probe timeout cannot belong to a live run.
            age = time.time() - lock_path.stat().st_mtime if lock_path.exists() else 0.0
            if age <= _PROBE_TIMEOUT_S + 60:
                raise RuntimeError(
                    "another agentic probe is running (lock at "
                    f"{lock_path}); run probes one at a time so the "
                    "measurement reflects the model, not VRAM contention"
                ) from None
            logger.warning("clearing stale probe lock (%.0fs old)", age)
            lock_path.unlink(missing_ok=True)
            handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        yield
    finally:
        if handle is not None:
            os.close(handle)
            lock_path.unlink(missing_ok=True)
        _PROBE_LOCK.release()


def probe(model: str, *, config=None, timeout_s: float = _PROBE_TIMEOUT_S) -> AgenticProbeResult:
    """Run one real agentic task and read the verdict off the disk.

    Uses the installed Hermes Agent exactly as mission execution does, so a
    pass here means the same path a mission takes actually works — not that
    some simplified harness works.

    Exclusive by construction: see _exclusive_probe. Raises rather than
    queueing if another probe holds the slot.

    ``timeout_s`` is adjustable because a timeout and a refusal are
    different findings and must not be conflated: a model that would have
    answered in 500s is slow, whereas one that returns in 310s having
    called no tool has declined the work. Raise it before concluding
    anything from a timeout.
    """
    with _exclusive_probe():
        return _probe_once(model, config, timeout_s)


def _probe_once(model: str, config, timeout_s: float = _PROBE_TIMEOUT_S) -> AgenticProbeResult:
    from backend.ral.adapters.hermes_agent_cli import HermesAgentCliConfig

    cfg = config or HermesAgentCliConfig()
    workspace = Path(tempfile.mkdtemp(prefix="hermes_agentic_probe_"))
    artifact = workspace / _PROBE_FILENAME

    env = os.environ.copy()
    env["HERMES_HOME"] = cfg.hermes_home
    env["OPENAI_API_KEY"] = cfg.api_key
    env["PYTHONUTF8"] = "1"

    command = [
        cfg.python_exe, cfg.cli_py,
        "--query", _probe_query(workspace),
        "--model", model,
        "--provider", cfg.provider,
        "--base_url", cfg.base_url,
        "--toolsets", "coding",
        "--max_turns", "8",
    ]

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command, cwd=str(workspace), env=env, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout_s,
        )
        stdout = completed.stdout or ""
        detail = "" if completed.returncode == 0 else f"exit {completed.returncode}"
    except subprocess.TimeoutExpired:
        return AgenticProbeResult(
            model=model, success=False, tool_calls=0,
            duration_s=time.perf_counter() - started, artifact_verified=False,
            detail=f"timed out after {timeout_s:.0f}s",
        )
    except OSError as exc:
        return AgenticProbeResult(
            model=model, success=False, tool_calls=0,
            duration_s=time.perf_counter() - started, artifact_verified=False,
            detail=f"could not start Hermes Agent: {exc}",
        )

    duration = time.perf_counter() - started
    match = _TOOL_CALL_RE.search(stdout)
    tool_calls = int(match.group(1)) if match else 0

    # The verdict, read from the filesystem rather than from the reply.
    verified = False
    try:
        verified = artifact.is_file() and _PROBE_CONTENT in artifact.read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        verified = False

    if not verified and not detail:
        detail = ("wrote nothing" if tool_calls == 0
                  else f"called {tool_calls} tool(s) but produced no valid artifact")

    return AgenticProbeResult(
        model=model, success=verified, tool_calls=tool_calls,
        duration_s=duration, artifact_verified=verified, detail=detail,
    )
