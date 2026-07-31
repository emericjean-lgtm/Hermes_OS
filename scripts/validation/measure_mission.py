"""Run a real mission end to end and measure what the machine actually did.

Samples VRAM, host RAM and CPU while the mission runs, and reports which
subsystem counters moved. Nothing is inferred: every figure comes from a
counter the running system published.

Requires a live backend and expects the GPU to be otherwise idle — it performs
real inference, so it must not run alongside a benchmark.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

OLLAMA = "http://127.0.0.1:11434"


def get(url: str, timeout: int = 20):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post(url: str, payload: dict, timeout: int = 900):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class Sampler(threading.Thread):
    """Polls VRAM / RAM / CPU while a mission runs."""

    def __init__(self, interval: float = 1.0):
        super().__init__(daemon=True)
        self.interval = interval
        self.stop_flag = threading.Event()
        self.vram: list[int] = []
        self.ram: list[float] = []
        self.cpu: list[float] = []
        self.models: set[str] = set()

    def run(self) -> None:
        try:
            import psutil
            psutil.cpu_percent(interval=None)
        except Exception:
            psutil = None
        while not self.stop_flag.is_set():
            try:
                ps = get(f"{OLLAMA}/api/ps", timeout=5).get("models") or []
                self.vram.append(sum(int(m.get("size_vram", 0) or 0) for m in ps))
                for m in ps:
                    self.models.add(m.get("name") or m.get("model") or "?")
            except Exception:
                pass
            if psutil:
                try:
                    self.ram.append(psutil.virtual_memory().used / 1024 ** 2)
                    self.cpu.append(psutil.cpu_percent(interval=None))
                except Exception:
                    pass
            time.sleep(self.interval)

    def summary(self) -> dict:
        def stat(xs, scale=1.0):
            if not xs:
                return {"samples": 0}
            return {"samples": len(xs), "min": round(min(xs) / scale, 2),
                    "max": round(max(xs) / scale, 2),
                    "mean": round(statistics.mean(xs) / scale, 2)}
        return {
            "vram_gib": stat(self.vram, 1024 ** 3),
            "ram_mib": stat(self.ram),
            "cpu_pct": stat(self.cpu),
            "models_resident": sorted(self.models),
        }


def counters(base: str) -> dict:
    """Snapshot the subsystem counters that a mission should move."""
    out = {}
    try:
        s = get(f"{base}/system/statistics").get("services", {})
        te = s.get("task_executor") or {}
        out["task_executor_executions"] = te.get("executions")
        out["task_executor_tokens"] = te.get("total_tokens")
        out["task_executor_simulated"] = te.get("simulated")
        ee = s.get("execution_engine") or {}
        out["scheduler"] = (ee.get("scheduler") or {}).get("total")
        out["validator"] = (ee.get("validator") or {}).get("total_validated")
        out["assignments"] = (ee.get("coordinator") or {}).get("active_assignments")
        bus = s.get("system_event_bus") or {}
        out["events_published"] = ((bus.get("value") or {}) or bus).get("total_published")
    except Exception as e:
        out["error"] = str(e)
    try:
        out["autonomous"] = get(f"{base}/autonomous/status").get("total_executions")
    except Exception:
        pass
    try:
        mem = get(f"{base}/memory/statistics")
        out["episodic_total"] = (mem.get("episodic") or {}).get("total")
    except Exception:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8010/api/v1")
    ap.add_argument("--goal", default="Analyse the authentication module and list its entry points")
    ap.add_argument("--surface", choices=["missions", "autonomous"], default="missions")
    ap.add_argument("--out", default="docs/release/mission_measurement.json")
    args = ap.parse_args()

    resident = get(f"{OLLAMA}/api/ps").get("models") or []
    if resident:
        print(f"GPU not idle: {[m.get('name') for m in resident]} — "
              f"refusing to measure against a shared GPU", file=sys.stderr)
        return 2

    before = counters(args.base)
    sampler = Sampler()
    sampler.start()
    started = time.perf_counter()

    if args.surface == "missions":
        created = post(f"{args.base}/missions",
                       {"title": "R-004 measured mission", "description": args.goal})
        mid = created["mission_id"]
        print(f"mission {mid}: {created['nodes']} node(s), planned={created['planned']}")
        result = post(f"{args.base}/missions/{mid}/start", {})
        detail = {"mission_id": mid, "created": created, "start": result}
        print(f"  status={result['status']} nodes_executed={result['nodes_executed']}")
    else:
        goal = post(f"{args.base}/autonomous/start", {"user_request": args.goal})
        detail = {"goal": goal}
        print(f"goal {goal['goal_id']}: {goal['status']}")

    elapsed = time.perf_counter() - started
    sampler.stop_flag.set()
    sampler.join(timeout=5)
    after = counters(args.base)

    moved = {k: (before.get(k), after.get(k))
             for k in after
             if before.get(k) != after.get(k)}

    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "surface": args.surface,
        "goal": args.goal,
        "wall_seconds": round(elapsed, 1),
        "detail": detail,
        "resources": sampler.summary(),
        "counters_before": before,
        "counters_after": after,
        "counters_moved": moved,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)

    print(f"\nwall clock: {elapsed:.1f}s")
    r = sampler.summary()
    print(f"VRAM  {r['vram_gib']}")
    print(f"RAM   {r['ram_mib']}")
    print(f"CPU   {r['cpu_pct']}")
    print(f"models resident during the mission: {r['models_resident']}")
    print("\ncounters that moved:")
    for k, (b, a) in moved.items():
        print(f"  {k:28} {b} -> {a}")
    unmoved = [k for k in after if k not in moved]
    print(f"unchanged: {', '.join(unmoved) or 'none'}")
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
