"""Inventaire des routes servies hors du namespace /api/v1.

Pour chaque route héritée : chemin, méthode, module propriétaire, présence d'un
doublon sous /api/v1, et atteignabilité depuis le Cockpit. Sert de table de
migration pour P-002 — rien n'est migré sur une intuition.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.ERROR)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from backend.main import create_app  # noqa: E402


def owning_module(app, path: str, method: str) -> str:
    """Le module qui définit l'endpoint, via son callable."""
    for route in app.routes:
        if getattr(route, "path", None) != path:
            continue
        if method not in (getattr(route, "methods", None) or set()):
            continue
        fn = getattr(route, "endpoint", None)
        if fn is not None:
            return getattr(fn, "__module__", "?")
    return "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/release/legacy_routes.json")
    args = ap.parse_args()

    app = create_app()

    api, legacy = {}, {}
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = sorted(m for m in (getattr(route, "methods", None) or set())
                         if m not in ("HEAD", "OPTIONS"))
        if not path or not methods:
            continue
        target = api if path.startswith("/api/v1") else legacy
        target.setdefault(path, set()).update(methods)

    # Chemins /api/v1 normalisés, pour détecter les doublons.
    api_norm = {p.replace("/api/v1", "", 1): verbs for p, verbs in api.items()}

    front = ""
    for f in Path("frontend/src").rglob("*.ts*"):
        front += f.read_text(encoding="utf-8", errors="ignore")

    rows = []
    for path in sorted(legacy):
        for method in sorted(legacy[path]):
            duplicate = path in api_norm and method in api_norm[path]
            # Atteignable depuis le Cockpit ? Le client ne connaît que API_BASE,
            # donc seule une base secondaire explicite permettrait d'y accéder.
            literal = f'"{path}"' in front or f"`{path}" in front
            rows.append({
                "path": path,
                "method": method,
                "module": owning_module(app, path, method),
                "duplicate_under_api_v1": duplicate,
                "referenced_literally_in_frontend": literal,
                # Migrable sans risque si aucun doublon ne se disputerait le chemin.
                "safe_to_migrate": not duplicate,
            })

    infra = {"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}
    real = [r for r in rows if r["path"] not in infra]

    report = {
        "api_v1_paths": len(api),
        "legacy_paths": len(legacy),
        "legacy_endpoints": len(real),
        "duplicated": sum(1 for r in real if r["duplicate_under_api_v1"]),
        "safe_to_migrate": sum(1 for r in real if r["safe_to_migrate"]),
        "reachable_from_cockpit": sum(
            1 for r in real if r["referenced_literally_in_frontend"]),
        "routes": real,
    }
    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"/api/v1 : {report['api_v1_paths']} chemins")
    print(f"hérité  : {report['legacy_paths']} chemins, "
          f"{report['legacy_endpoints']} endpoints")
    print(f"  doublons sous /api/v1        : {report['duplicated']}")
    print(f"  migrables sans conflit       : {report['safe_to_migrate']}")
    print(f"  cités littéralement au front : {report['reachable_from_cockpit']}")
    print()

    by_module: dict[str, list[dict]] = {}
    for r in real:
        by_module.setdefault(r["module"], []).append(r)
    print(f"{'module':46} {'n':>3}  exemple")
    print("-" * 100)
    for module, items in sorted(by_module.items(), key=lambda x: -len(x[1])):
        print(f"{module[:46]:46} {len(items):>3}  "
              f"{items[0]['method']} {items[0]['path'][:38]}")
    print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
