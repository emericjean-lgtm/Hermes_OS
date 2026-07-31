"""Sequential per-model benchmark harness for local validation.

Enforces the one-model-at-a-time discipline required for reproducible numbers:

    1. verify the GPU is idle (no resident model)
    2. load exactly one model and wait until it is genuinely ready
    3. run the benchmark suite against it
    4. collect every metric from the runtime's own counters
    5. unload it
    6. verify VRAM actually came back
    7. wait for a stable baseline
    8. move to the next model

Nothing here is simulated. Timings come from Ollama's own response fields
(``load_duration``, ``prompt_eval_duration``, ``eval_duration``, ``eval_count``),
VRAM from ``/api/ps``'s ``size_vram``, and host RAM from ``psutil``. A model that
fails to load, times out or returns nothing is recorded as a failure with the
reason — never as a pass.

Results are appended to the output file after **each model**, so an interrupted
run still leaves real measurements behind rather than nothing.

Usage:
    python scripts/validation/bench_models.py --out results.json
    python scripts/validation/bench_models.py --models qwen3:4b,qwen3:1.7b
    python scripts/validation/bench_models.py --max-size-gb 16   # skip CPU-spill
    python scripts/validation/bench_models.py --categories code,chat
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

OLLAMA = "http://127.0.0.1:11434"

#: One prompt per benchmark axis. Deliberately short and deterministic-ish:
#: the point is comparable timing and a checkable answer, not creative writing.
BENCHMARKS: dict[str, dict[str, Any]] = {
    "code": {
        "prompt": "Write a Python function `is_palindrome(s: str) -> bool` that "
                  "ignores case and non-alphanumeric characters. Code only.",
        "expect_any": ["def is_palindrome", "return"],
    },
    "chat": {
        "prompt": "In two sentences, explain what a reverse proxy does.",
        "expect_any": ["proxy", "server", "client"],
    },
    "reasoning": {
        "prompt": "A bat and a ball cost 1.10 in total. The bat costs 1.00 more "
                  "than the ball. How much does the ball cost? Answer with the "
                  "number only.",
        "expect_any": ["0.05", ".05", "5 cent"],
    },
    "agent": {
        "prompt": "You must call a tool. Reply with JSON only: "
                  '{"tool": "<name>", "args": {...}} to read the file '
                  "/etc/hosts using a tool named read_file.",
        "expect_any": ["read_file", "\"tool\""],
    },
    "tools": {
        "prompt": "Given the function signature `search(query: str, limit: int)`, "
                  "produce a JSON call object to search for 'hermes' with limit 5. "
                  "JSON only.",
        "expect_any": ["hermes", "5"],
    },
    "long_context": {
        # Built at runtime so the filler is measured, not guessed.
        "prompt": None,
        "expect_any": ["42"],
    },
    "memory": {
        "prompt": "Remember this token: ZX-9137. Now, without any preamble, "
                  "repeat the token back exactly.",
        "expect_any": ["ZX-9137", "zx-9137"],
    },
}

LONG_CONTEXT_FILLER_WORDS = 1500


def _long_context_prompt() -> str:
    filler = " ".join(
        f"line{i} irrelevant filler content" for i in range(LONG_CONTEXT_FILLER_WORDS)
    )
    return (
        "Below is a long document. The secret number is 42. "
        f"{filler} "
        "What is the secret number? Answer with the number only."
    )


@dataclass
class BenchResult:
    category: str
    ok: bool
    error: str = ""
    total_ms: float = 0.0
    load_ms: float = 0.0
    ttft_ms: float = 0.0          # prompt eval = time to first token
    eval_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tps: float = 0.0
    quality_pass: bool = False
    response_chars: int = 0
    response_head: str = ""


@dataclass
class ModelResult:
    model: str
    size_gb: float = 0.0
    loaded: bool = False
    load_error: str = ""
    load_wall_ms: float = 0.0
    unload_wall_ms: float = 0.0
    vram_used_bytes: int = 0
    vram_after_unload_bytes: int = 0
    vram_reclaimed: bool = False
    processor: str = ""
    context_length: int = 0
    ram_before_mb: float = 0.0
    ram_peak_mb: float = 0.0
    benchmarks: list[BenchResult] = field(default_factory=list)
    tps_mean: float = 0.0
    tps_stdev: float = 0.0
    stable: bool = False
    started_at: str = ""
    finished_at: str = ""


# ── Ollama plumbing (all real calls) ──────────────────────────────────


def _post(path: str, payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(f"{OLLAMA}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def resident_models() -> list[dict]:
    try:
        return _get("/api/ps").get("models") or []
    except Exception:
        return []


def vram_in_use() -> int:
    return sum(int(m.get("size_vram", 0) or 0) for m in resident_models())


def ram_used_mb() -> float:
    try:
        import psutil

        return psutil.virtual_memory().used / 1024 ** 2
    except Exception:
        return 0.0


def unload_all(settle_s: float = 3.0, timeout_s: float = 90.0) -> tuple[int, float]:
    """Unload every resident model and wait for VRAM to actually come back."""
    started = time.perf_counter()
    for m in resident_models():
        name = m.get("name") or m.get("model")
        if not name:
            continue
        try:
            # keep_alive 0 asks Ollama to evict immediately.
            _post("/api/generate", {"model": name, "prompt": "", "keep_alive": 0},
                  timeout=30)
        except Exception:
            subprocess.run(["ollama", "stop", name], capture_output=True, timeout=30)

    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if not resident_models():
            break
        time.sleep(1.0)
    time.sleep(settle_s)  # let the driver actually release
    return vram_in_use(), (time.perf_counter() - started) * 1000.0


def load_model(model: str, timeout_s: int) -> tuple[bool, str, float]:
    """Load one model and wait until it is genuinely resident."""
    started = time.perf_counter()
    try:
        _post("/api/generate", {"model": model, "prompt": "", "keep_alive": "10m"},
              timeout=timeout_s)
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:160]}", 0.0
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", 0.0

    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if any((m.get("name") or m.get("model")) == model for m in resident_models()):
            return True, "", (time.perf_counter() - started) * 1000.0
        time.sleep(0.5)
    return False, "model never became resident", (time.perf_counter() - started) * 1000.0


def run_one(model: str, category: str, spec: dict, timeout_s: int) -> BenchResult:
    prompt = spec["prompt"] or _long_context_prompt()
    try:
        r = _post("/api/generate", {
            "model": model, "prompt": prompt, "stream": False, "keep_alive": "10m",
        }, timeout=timeout_s)
    except Exception as e:
        return BenchResult(category=category, ok=False,
                           error=f"{type(e).__name__}: {e}")

    text = (r.get("response") or "").strip()
    eval_count = int(r.get("eval_count", 0) or 0)
    eval_ns = int(r.get("eval_duration", 0) or 0)
    tps = (eval_count / (eval_ns / 1e9)) if eval_ns > 0 else 0.0
    lowered = text.lower()
    quality = any(tok.lower() in lowered for tok in spec["expect_any"]) if text else False

    return BenchResult(
        category=category,
        ok=bool(text),
        error="" if text else "empty completion",
        total_ms=int(r.get("total_duration", 0) or 0) / 1e6,
        load_ms=int(r.get("load_duration", 0) or 0) / 1e6,
        ttft_ms=int(r.get("prompt_eval_duration", 0) or 0) / 1e6,
        eval_ms=eval_ns / 1e6,
        prompt_tokens=int(r.get("prompt_eval_count", 0) or 0),
        completion_tokens=eval_count,
        tps=round(tps, 2),
        quality_pass=quality,
        response_chars=len(text),
        response_head=text[:180],
    )


def bench_model(model: str, size_gb: float, categories: list[str],
                timeout_s: int) -> ModelResult:
    result = ModelResult(model=model, size_gb=size_gb,
                         started_at=datetime.now(timezone.utc).isoformat())

    # 1. GPU must be idle before we start.
    leftover, _ = unload_all()
    if leftover > 0:
        print(f"    ! {leftover/1024**2:.0f} MiB still resident before load", flush=True)

    result.ram_before_mb = ram_used_mb()

    # 2. Load exactly one model, wait until ready.
    ok, err, load_ms = load_model(model, timeout_s)
    result.loaded, result.load_error, result.load_wall_ms = ok, err, load_ms
    if not ok:
        result.finished_at = datetime.now(timezone.utc).isoformat()
        print(f"    LOAD FAILED: {err}", flush=True)
        return result

    resident = [m for m in resident_models()
                if (m.get("name") or m.get("model")) == model]
    if resident:
        result.vram_used_bytes = int(resident[0].get("size_vram", 0) or 0)
        result.context_length = int(resident[0].get("context_length", 0) or 0)
    try:
        ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=15)
        for line in ps.stdout.splitlines():
            if line.startswith(model.split(":")[0]):
                result.processor = "GPU" if "GPU" in line else (
                    "CPU" if "CPU" in line else "")
                if "%" in line:
                    result.processor = line.split()[-3:] and " ".join(
                        p for p in line.split() if "%" in p or p in ("GPU", "CPU"))
    except Exception:
        pass

    print(f"    loaded in {load_ms/1000:.1f}s | VRAM {result.vram_used_bytes/1024**3:.2f} GiB"
          f" | {result.processor or 'processor unknown'}", flush=True)

    # 3-4. Benchmarks, sequentially, with metrics from the runtime itself.
    peak_ram = result.ram_before_mb
    for category in categories:
        spec = BENCHMARKS[category]
        r = run_one(model, category, spec, timeout_s)
        result.benchmarks.append(r)
        peak_ram = max(peak_ram, ram_used_mb())
        status = "ok " if r.ok else "FAIL"
        print(f"      {category:14} {status} {r.tps:7.2f} tps  "
              f"ttft {r.ttft_ms:7.0f}ms  {r.completion_tokens:4d} tok"
              f"  quality={'Y' if r.quality_pass else 'n'}"
              f"{'  ' + r.error if r.error else ''}", flush=True)
    result.ram_peak_mb = peak_ram

    rates = [b.tps for b in result.benchmarks if b.ok and b.tps > 0]
    if rates:
        result.tps_mean = round(statistics.mean(rates), 2)
        result.tps_stdev = round(statistics.stdev(rates), 2) if len(rates) > 1 else 0.0
        # "Stable" = every run answered and throughput varied by under 20%.
        result.stable = (all(b.ok for b in result.benchmarks)
                         and result.tps_mean > 0
                         and (result.tps_stdev / result.tps_mean) < 0.20)

    # 5-7. Unload and prove the VRAM came back.
    after, unload_ms = unload_all()
    result.vram_after_unload_bytes = after
    result.unload_wall_ms = unload_ms
    result.vram_reclaimed = after == 0
    print(f"    unloaded in {unload_ms/1000:.1f}s | VRAM now {after/1024**2:.0f} MiB"
          f" | reclaimed={result.vram_reclaimed}", flush=True)

    result.finished_at = datetime.now(timezone.utc).isoformat()
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/release/bench_results.json")
    ap.add_argument("--models", default="", help="comma-separated; default all")
    ap.add_argument("--categories", default=",".join(BENCHMARKS))
    ap.add_argument("--max-size-gb", type=float, default=0.0,
                    help="skip models larger than this (0 = no limit)")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    try:
        version = _get("/api/version").get("version", "?")
    except Exception as e:
        print(f"Ollama is not reachable at {OLLAMA}: {e}", file=sys.stderr)
        return 2

    tags = _get("/api/tags").get("models") or []
    catalogue = {m["name"]: m.get("size", 0) / 1024 ** 3 for m in tags}

    wanted = [m.strip() for m in args.models.split(",") if m.strip()] or list(catalogue)
    missing = [m for m in wanted if m not in catalogue]
    if missing:
        print(f"not installed, skipping: {missing}", file=sys.stderr)
    wanted = [m for m in wanted if m in catalogue]
    if args.max_size_gb:
        wanted = [m for m in wanted if catalogue[m] <= args.max_size_gb]
    # Smallest first: fastest feedback, and the big CPU-spill models last.
    wanted.sort(key=lambda m: catalogue[m])

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    bad = [c for c in categories if c not in BENCHMARKS]
    if bad:
        print(f"unknown categories: {bad}", file=sys.stderr)
        return 2

    print(f"Ollama {version} | {len(wanted)} model(s) | {len(categories)} categories")
    print("Strictly sequential: one model resident at a time.\n")

    results: list[ModelResult] = []
    out = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ollama_version": version,
        "categories": categories,
        "models": [],
    }

    for i, model in enumerate(wanted, 1):
        print(f"[{i}/{len(wanted)}] {model} ({catalogue[model]:.1f} GB)", flush=True)
        r = bench_model(model, round(catalogue[model], 2), categories, args.timeout)
        results.append(r)
        out["models"] = [asdict(x) for x in results]
        out["finished_at"] = datetime.now(timezone.utc).isoformat()
        # Write after every model so an interrupted run still yields real data.
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        print(flush=True)

    ok = sum(1 for r in results if r.loaded)
    print(f"done: {ok}/{len(results)} model(s) loaded and benchmarked -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
