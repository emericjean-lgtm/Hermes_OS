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
_PROBE_QUERY = (
    f"Create a file named {_PROBE_FILENAME} in your working directory "
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
    from backend.core.config import get_settings

    settings = get_settings()
    base = getattr(settings, "data_dir", None) or tempfile.gettempdir()
    return Path(base) / "agentic_probe_results.json"


def load_results() -> dict[str, dict]:
    """Previously measured verdicts, keyed by model tag."""
    try:
        return json.loads(_probe_store_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_result(result: AgenticProbeResult) -> None:
    """Accumulate one trial into the model's running record.

    Accumulates rather than overwrites, because one trial is not a verdict:
    the rate across trials is what measured_success_for reads.
    """
    try:
        path = _probe_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        results = load_results()
        entry = results.get(result.model) or {"trials": 0, "successes": 0, "runs": []}
        entry["trials"] = int(entry.get("trials", 0)) + 1
        entry["successes"] = int(entry.get("successes", 0)) + (1 if result.success else 0)
        entry["success_rate"] = entry["successes"] / entry["trials"]
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
    """What real runs said about this model, or None if never probed.

    Feeds ``ModelProfile.measured_agentic_success``, which outranks both the
    declaration and the size heuristic. A single trial is deliberately not
    treated as an answer: the first measurements taken on this deployment
    flipped both ways between runs, and a routing decision built on one
    sample is how a narrator gets promoted to mission brain.
    """
    results = load_results()
    entry = results.get(model)
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
                break
    if entry is None:
        return None
    trials = entry.get("trials")
    if not trials:
        return None
    successes = entry.get("successes", 0)
    if trials < 2:
        return None  # one sample is noise, not a measurement
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
        "--query", _PROBE_QUERY,
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
