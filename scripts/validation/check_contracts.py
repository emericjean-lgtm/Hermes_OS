"""Compare every frontend client declaration against what the API really returns.

The Cockpit's contract drift was invisible for a long time because the frontend
could not reach the backend at all, so every call failed and the components fell
back to empty state. This checks the two against each other directly: for each
`fetchJSON<T>("/path")` in services/client.ts, call the live endpoint and report
whether an array-typed method actually receives an array.

Read-only: only parameter-free GETs are called.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

CLIENT = pathlib.Path("frontend/src/services/client.ts")


def declarations() -> list[tuple[str, str, str]]:
    """(method, declared type, path) for every literal-path fetchJSON call."""
    src = CLIENT.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(
            r"(\w+):\s*\([^)]*\)\s*=>\s*\n?\s*fetchJSON<([^>]+)>\(\s*[\"`]([^\"`$]+)[\"`]", src):
        out.append((m.group(1), m.group(2).strip(), m.group(3)))
    return out


def fetch(base: str, path: str) -> tuple[int, object | None, str]:
    url = f"{base}{path}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8")), ""
    except urllib.error.HTTPError as e:
        return e.code, None, e.reason
    except Exception as e:
        return 0, None, f"{type(e).__name__}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8010/api/v1")
    ap.add_argument("--out", default="docs/release/contract_check.json")
    args = ap.parse_args()

    rows, mismatches = [], []
    for method, declared, path in declarations():
        if "{" in path or "$" in path:
            continue
        status, body, err = fetch(args.base, path)
        row = {"method": method, "declared": declared, "path": path, "status": status}

        if body is None:
            row["verdict"] = "not checked"
            row["detail"] = err or f"HTTP {status}"
        else:
            actual = ("array" if isinstance(body, list)
                      else "object" if isinstance(body, dict) else type(body).__name__)
            row["actual"] = actual
            if isinstance(body, dict):
                row["keys"] = sorted(body.keys())[:6]
            wants_array = declared.endswith("[]")
            if wants_array and actual != "array":
                row["verdict"] = "MISMATCH"
                row["detail"] = (f"declared {declared} but endpoint returns an object"
                                 f" with keys {row.get('keys')}")
                mismatches.append(row)
            else:
                row["verdict"] = "ok"
        rows.append(row)

    report = {"base": args.base, "checked": len(rows),
              "mismatches": len(mismatches), "rows": rows}
    pathlib.Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"{len(rows)} literal-path client methods checked against {args.base}")
    ok = sum(1 for r in rows if r.get("verdict") == "ok")
    skipped = sum(1 for r in rows if r.get("verdict") == "not checked")
    print(f"  ok: {ok} | mismatches: {len(mismatches)} | not checked: {skipped}")
    for r in mismatches:
        print(f"  MISMATCH {r['method']:20} {r['path']:26} {r['detail']}")
    for r in rows:
        if r.get("verdict") == "not checked":
            print(f"  skipped  {r['method']:20} {r['path']:26} {r['detail']}")
    print(f"\nwritten to {args.out}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
