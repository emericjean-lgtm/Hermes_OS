"""Exercise every REST route on the real assembled app and report the truth.

Every parameter-free GET is called. Mutating verbs are called only where a safe,
reversible payload exists — this sweep must not delete a user's data to prove a
route answers. Routes that require a body or a path parameter are reported as
"not exercised" with the reason, never as passing.

Deliberately performs no inference: a benchmark may be running, and the local
validation rules forbid competing for the GPU.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import sys
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.ERROR)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import create_app  # noqa: E402

#: Routes that would run a model. Skipped so the sweep never competes with a
#: benchmark for the GPU.
INFERENCE_ROUTES = (
    "/autonomous/start", "/missions/{mission_id}/start", "/conversation/message",
    "/klaatcode/analyze", "/klaatcode/execute", "/klaatcode/diagnostics",
    "/ohmypi/execute", "/execution/start", "/models/benchmark",
    "/agents/{agent_id}/execute", "/tools/execute",
)

#: Safe, reversible bodies for mutating routes worth exercising.
SAFE_POSTS = {
    "/api/v1/missions": {"title": "sweep probe", "description": "endpoint sweep",
                         "nodes": [], "edges": []},
    "/api/v1/conversation/start": {"user_request": "endpoint sweep"},
    "/api/v1/policy/evaluate": {"action": "read", "resource": "sweep"},
    "/api/v1/memory/search": {"query": "sweep", "mode": "keyword"},
    "/api/v1/models/recommend": {"task_type": "code", "description": "sweep"},
    "/api/v1/skills/select": {"task_description": "endpoint sweep probe"},
    "/api/v1/alexandrie/missions/relevant": {"mission_id": "sweep", "limit": 1},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/release/endpoint_sweep.json")
    args = ap.parse_args()

    app = create_app()

    routes: list[tuple[str, str]] = []
    for r in app.routes:
        path = getattr(r, "path", "")
        for m in sorted(getattr(r, "methods", []) or []):
            if m in ("HEAD", "OPTIONS"):
                continue
            routes.append((m, path))
    routes.sort(key=lambda x: (x[1], x[0]))

    rows: list[dict] = []
    tally: collections.Counter = collections.Counter()

    with TestClient(app) as client:
        for method, path in routes:
            entry = {"method": method, "path": path}

            if any(path.endswith(s) or s in path for s in INFERENCE_ROUTES):
                entry.update(status=None, outcome="skipped",
                             reason="would run a model; benchmarks must not share the GPU")
                tally["skipped-inference"] += 1
                rows.append(entry)
                continue

            if "{" in path:
                entry.update(status=None, outcome="not exercised",
                             reason="requires a path parameter")
                tally["needs-param"] += 1
                rows.append(entry)
                continue

            if method == "GET":
                try:
                    resp = client.get(path)
                    entry.update(status=resp.status_code,
                                 outcome="ok" if resp.status_code < 400 else "error",
                                 body_head=_head(resp))
                    tally[f"GET {resp.status_code}"] += 1
                except Exception as exc:
                    entry.update(status=None, outcome="exception",
                                 reason=f"{type(exc).__name__}: {exc}")
                    tally["GET exception"] += 1
            elif method == "POST" and path in SAFE_POSTS:
                try:
                    resp = client.post(path, json=SAFE_POSTS[path])
                    entry.update(status=resp.status_code,
                                 outcome="ok" if resp.status_code < 400 else "error",
                                 body_head=_head(resp))
                    tally[f"POST {resp.status_code}"] += 1
                except Exception as exc:
                    entry.update(status=None, outcome="exception",
                                 reason=f"{type(exc).__name__}: {exc}")
                    tally["POST exception"] += 1
            else:
                entry.update(status=None, outcome="not exercised",
                             reason="mutating verb without a safe payload")
                tally["no-safe-payload"] += 1
            rows.append(entry)

        # WebSocket is part of the contract; prove it accepts and delivers.
        ws = {"path": "/ws", "outcome": "not exercised"}
        try:
            with client.websocket_connect("/ws") as socket:
                socket.send_text(json.dumps({"type": "ping"}))
                ws.update(outcome="ok", note="connected and sent a frame")
        except Exception as exc:
            ws.update(outcome="error", reason=f"{type(exc).__name__}: {exc}")
        tally[f"ws {ws['outcome']}"] += 1

    report = {
        "total_routes": len(routes),
        "tally": dict(tally),
        "websocket": ws,
        "routes": rows,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)

    print(f"{len(routes)} method+path pairs on the assembled app")
    for k, v in sorted(tally.items()):
        print(f"  {k:22} {v}")
    failures = [r for r in rows if r["outcome"] in ("error", "exception")]
    print(f"\nfailures: {len(failures)}")
    for f_ in failures:
        print(f"  {f_['method']:6} {f_['path']:48} "
              f"{f_.get('status')} {f_.get('reason', '')[:60]}")
    print(f"\nwebsocket: {ws}")
    print(f"\nwritten to {args.out}")
    return 1 if failures else 0


def _head(resp) -> str:
    try:
        return json.dumps(resp.json())[:140]
    except Exception:
        return resp.text[:140]


if __name__ == "__main__":
    raise SystemExit(main())
