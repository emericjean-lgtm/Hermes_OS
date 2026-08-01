"""P-002 — le Cockpit n'a plus qu'une seule base d'API.

Hermes servait deux racines : ``/api/v1`` pour les sous-systèmes HOS et la racine
nue pour l'API Hermes-Ollama d'origine. Le client du Cockpit ne connaît que la
première, donc la seconde moitié du produit lui était inaccessible.

Ces tests verrouillent la propriété obtenue : toute route héritée est joignable
sous ``/api/v1``, **sans qu'aucune implémentation existante n'ait été masquée**.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from backend.main import _LEGACY_ROUTERS, create_app

CLIENT_TS = pathlib.Path("frontend/src/services/client.ts")

#: Chemins d'infrastructure servis par FastAPI, hors périmètre.
INFRA = {"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture(scope="module")
def client(app):
    """Un seul TestClient pour tout le module.

    Le gestionnaire de session MCP ne peut être démarré qu'une fois par app :
    ouvrir un second TestClient sur la même instance échoue.
    """
    with TestClient(app) as c:
        yield c


def _endpoints(app) -> dict[tuple[str, str], str]:
    """(méthode, chemin) -> module du handler."""
    out: dict[tuple[str, str], str] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path:
            continue
        fn = getattr(route, "endpoint", None)
        module = getattr(fn, "__module__", "?")
        for method in (getattr(route, "methods", None) or {"WS"}):
            if method not in ("HEAD", "OPTIONS"):
                out[(method, path)] = module
    return out


# ── Namespace unique ──────────────────────────────────────────────────


def test_every_legacy_route_is_reachable_under_api_v1(app):
    """Aucune capacité ne doit rester joignable uniquement hors /api/v1."""
    endpoints = _endpoints(app)
    unreachable = []

    for module in _LEGACY_ROUTERS:
        router = getattr(module, "router", None)
        if router is None:
            continue
        for route in router.routes:
            path = getattr(route, "path", "")
            if path in INFRA:
                continue
            for method in (getattr(route, "methods", None) or {"WS"}):
                if method in ("HEAD", "OPTIONS"):
                    continue
                canonical = ("/api/v1" + path) in [p for _m, p in endpoints]
                subspace = ("/api/v1/legacy" + path) in [p for _m, p in endpoints]
                if not (canonical or subspace):
                    unreachable.append(f"{method} {path}")

    assert not unreachable, (
        "routes héritées sans équivalent sous /api/v1 : " + ", ".join(unreachable[:10]))


def test_migration_did_not_shadow_any_existing_handler(app):
    """Republier une route héritée ne doit jamais voler un chemin /api/v1.

    ``/skills`` est servi par deux implémentations **différentes** —
    ``api.routes.skills`` d'un côté, ``skills.routes`` de l'autre. Les monter au
    même endroit ferait taire l'une des deux en silence.
    """
    owners = _endpoints(app)
    expected = {
        ("GET", "/api/v1/skills"): "backend.skills.routes",
        ("GET", "/api/v1/memory/search"): "backend.memory.routes",
        ("GET", "/api/v1/health"): "backend.sds.routes",
        ("GET", "/api/v1/agents"): "backend.agents.routes",
        ("GET", "/api/v1/missions"): "backend.mission.routes",
    }
    for key, module_prefix in expected.items():
        assert key in owners, f"{key} a disparu"
        assert owners[key].startswith(module_prefix), (
            f"{key[1]} est désormais servi par {owners[key]}, "
            f"pas par {module_prefix} — une implémentation a été masquée")


def test_colliding_routes_live_in_the_legacy_subspace(app):
    """Les chemins disputés sont servis sous /api/v1/legacy, pas perdus."""
    paths = {p for _m, p in _endpoints(app)}
    for path in ("/api/v1/legacy/skills", "/api/v1/legacy/memory/search"):
        assert path in paths, f"{path} absent : la route héritée est inaccessible"


def test_frontend_uses_a_single_api_root():
    """Une seule constante de base dans le client, pas de racine secondaire."""
    src = CLIENT_TS.read_text(encoding="utf-8")
    bases = set(re.findall(r"const (\w*BASE\w*)\s*=", src))
    assert bases == {"API_BASE"}, f"racines multiples dans le client : {bases}"
    assert "LEGACY_BASE" not in src


# ── Aucune action du Cockpit ne doit viser une route morte ────────────


def _client_paths() -> set[str]:
    """Chemins littéraux demandés par le client frontend."""
    src = CLIENT_TS.read_text(encoding="utf-8")
    found = set()
    for match in re.finditer(r'fetchJSON<[^>]*>\(\s*[`"]([^`"$]+)', src):
        found.add(match.group(1))
    for match in re.finditer(r'fetchJSON<[^>]*>\(\s*`([^`]*)`', src):
        # Chemins paramétrés : on garde le préfixe stable avant l'interpolation.
        literal = match.group(1).split("${")[0]
        if literal:
            found.add(literal)
    # Les chaînes de requête ne font pas partie du chemin servi.
    return {p.split("?")[0].rstrip("/") or "/"
            for p in found if p.startswith("/")}


def test_no_frontend_method_points_at_a_dead_endpoint(app):
    """Chaque appel du client doit correspondre à une route réelle."""
    served = {p for _m, p in _endpoints(app)}
    dead = []
    for path in sorted(_client_paths()):
        full = "/api/v1" + path
        # Une route paramétrée ne matche pas littéralement : on compare le
        # préfixe stable, ce qui suffit à détecter un chemin inexistant.
        if any(s == full or s.startswith(full.rstrip("/") + "/") for s in served):
            continue
        dead.append(path)
    assert not dead, f"méthodes client visant une route inexistante : {dead}"


# ── Rien ne doit prétendre réussir sans backend ───────────────────────


def test_actions_report_failure_when_the_target_does_not_exist(client):
    """Un identifiant inconnu doit produire une erreur, pas un faux succès."""
    response = client.post("/api/v1/evolution/apply/inexistant")
    assert response.status_code >= 400 or _looks_like_failure(response.json()), (
        "appliquer une proposition inexistante a répondu comme un succès : "
        f"{response.status_code} {response.text[:120]}")


def _looks_like_failure(payload: object) -> bool:
    if isinstance(payload, dict):
        if payload.get("success") is False or payload.get("error"):
            return True
        if "detail" in payload:
            return True
    return False


# ── Les actions destructives passent par une confirmation ─────────────

DESTRUCTIVE_CENTERS = {
    "frontend/src/features/evolution/evolution-center.tsx": ("simulate", "approve", "apply"),
    "frontend/src/features/workspace/workspace-center.tsx": ("remove",),
}


@pytest.mark.parametrize("path,verbs", DESTRUCTIVE_CENTERS.items())
def test_destructive_actions_require_confirmation(path, verbs):
    """Aucune action irréversible ne doit partir sur un simple clic."""
    src = pathlib.Path(path).read_text(encoding="utf-8")
    assert "ConfirmAction" in src, (
        f"{path} déclenche {verbs} sans passer par ConfirmAction")


def test_confirmation_component_does_not_bypass_backend_authorisation():
    """La confirmation est une garde d'interface, pas une autorisation."""
    src = pathlib.Path("frontend/src/components/confirm-action.tsx").read_text(
        encoding="utf-8")
    assert "ne remplace pas" in src, (
        "le composant doit documenter qu'il ne se substitue pas à "
        "Policy / Security / Approval")


# ── Le contrat Validation reste honnête ───────────────────────────────


def test_verification_run_payload_is_actually_documented(client):
    """This used to assert the opposite — that POST /verification/run had no
    schema and that no button should call it. That premise was simply wrong:
    VerificationRunRequest (backend/api/routes/verification.py) has always
    had a full Pydantic schema, visible on this exact endpoint. Honesty now
    means confirming the documented contract stays documented, not that the
    Cockpit avoids a route it was mistaken about."""
    schema = client.get("/openapi.json").json()
    request_schema = schema["components"]["schemas"]["VerificationRunRequest"]
    assert set(request_schema["required"]) == {"repo_path", "runner"}
    assert "repo_path" in request_schema["properties"]
    assert "runner" in request_schema["properties"]


def test_validation_center_calls_the_documented_verification_run():
    """The Validation Center's trigger form must post repo_path/runner —
    the fields VerificationRunRequest actually requires — not a guessed
    shape."""
    src = pathlib.Path(
        "frontend/src/features/validation/validation-center.tsx").read_text(
        encoding="utf-8")
    assert "verification/run" not in src or "runVerification.mutate" in src, (
        "the Center mentions /verification/run but never calls it")
    assert "repo_path" in src and "runner:" in src, (
        "the trigger must send the fields VerificationRunRequest requires")


def test_verification_runners_is_served_under_the_canonical_namespace(client):
    response = client.get("/api/v1/verification/runners")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
