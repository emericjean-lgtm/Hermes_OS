"""Router auto-registration and namespace unification (HOS-066B, STEP 3 + 4).

Two jobs.

**Mount everything.** The routers come from :class:`HermesBootstrap`, which
produced them by binding each route module to its owning service. Mounting is
therefore driven by the service catalogue rather than by a hand-maintained list
in ``main.py`` — the list is what silently lost 19 complete routers before
HOS-066B, leaving the entire Hermes OS API answering 404.

**One namespace.** ``/api/v1`` is canonical. The SDS router carries a baked-in
``/api/hermes-os`` prefix from HOS-003 and the frontend grew a second client
against it, so the same system was reachable under two names. Rather than
duplicate handlers, :func:`rebase_router` re-registers the *same* endpoint
functions under ``/api/v1``, and :func:`add_legacy_redirects` leaves
``/api/hermes-os/*`` as a redirect so existing clients keep working.

Collisions are detected rather than tolerated: FastAPI resolves a duplicate
(method, path) by first-registered-wins and says nothing, which is how a
validated mission-creation endpoint ended up shadowed by an unvalidated one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

logger = logging.getLogger("hermes_os.routers")

#: The one canonical API prefix.
API_V1 = "/api/v1"

#: Kept only so clients written against HOS-003 keep working.
LEGACY_SDS_PREFIX = "/api/hermes-os"


@dataclass
class MountReport:
    """What was mounted, and what collided."""

    mounted: int = 0
    routers: int = 0
    collisions: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "routers": self.routers,
            "endpoints": self.mounted,
            "distinct_paths": len(set(self.paths)),
            "collisions": self.collisions,
        }


def rebase_router(source: APIRouter, strip_prefix: str) -> APIRouter:
    """Return a router serving ``source``'s endpoints without ``strip_prefix``.

    The endpoint callables are reused as-is, so there is exactly one
    implementation of each handler no matter how many prefixes it is served
    under. Used to bring the SDS router (whose ``/api/hermes-os`` prefix is
    baked into its construction) under the canonical namespace.
    """
    rebased = APIRouter()
    for route in source.routes:
        path = getattr(route, "path", "")
        if not path.startswith(strip_prefix):
            continue
        new_path = path[len(strip_prefix):] or "/"
        methods = sorted(getattr(route, "methods", {"GET"}) - {"HEAD"})
        rebased.add_api_route(
            new_path,
            route.endpoint,
            methods=methods,
            name=getattr(route, "name", None),
            tags=list(getattr(route, "tags", []) or []),
            summary=getattr(route, "summary", None),
            description=getattr(route, "description", None),
            include_in_schema=getattr(route, "include_in_schema", True),
            response_model=getattr(route, "response_model", None),
        )
    return rebased


def _route_keys(router: APIRouter, prefix: str) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for route in router.routes:
        path = prefix + getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if methods is None:
            # WebSocket routes have no methods; key them on the path alone.
            keys.append(("WS", path))
            continue
        for m in sorted(methods):
            keys.append((m, path))
    return keys


def mount_all(
    app: Any,
    routers: Iterable[APIRouter],
    *,
    prefix: str = API_V1,
    report: Optional[MountReport] = None,
) -> MountReport:
    """Mount every router under ``prefix``, refusing to hide a collision."""
    report = report or MountReport()
    seen: dict[tuple[str, str], int] = {}

    # Seed with what the app already serves so legacy routes are considered too.
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or {"WS"}
        for m in methods:
            seen[(m, path)] = seen.get((m, path), 0) + 1

    for router in routers:
        for key in _route_keys(router, prefix):
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                report.collisions.append(f"{key[0]} {key[1]}")
        app.include_router(router, prefix=prefix)
        report.routers += 1
        report.mounted += len(router.routes)
        report.paths.extend(prefix + getattr(r, "path", "") for r in router.routes)

    if report.collisions:
        # Loud, because FastAPI would otherwise resolve these silently by
        # registration order and one implementation would simply never run.
        logger.warning(
            "%d duplicate route(s) detected while mounting: %s",
            len(report.collisions),
            ", ".join(sorted(set(report.collisions))[:10]),
        )
    return report


def add_legacy_redirects(app: Any, *, legacy: str = LEGACY_SDS_PREFIX,
                         canonical: str = API_V1) -> None:
    """Redirect the pre-HOS-066B namespace onto the canonical one.

    A 307 rather than a 301/302 so the method and body survive the hop, which
    matters because several of the redirected endpoints are POSTs.
    """

    @app.get(f"{legacy}/{{path:path}}", include_in_schema=False)
    async def _legacy_get(path: str) -> RedirectResponse:  # pragma: no cover - thin
        return RedirectResponse(url=f"{canonical}/{path}", status_code=307)

    @app.post(f"{legacy}/{{path:path}}", include_in_schema=False)
    async def _legacy_post(path: str) -> RedirectResponse:  # pragma: no cover - thin
        return RedirectResponse(url=f"{canonical}/{path}", status_code=307)

    @app.patch(f"{legacy}/{{path:path}}", include_in_schema=False)
    async def _legacy_patch(path: str) -> RedirectResponse:  # pragma: no cover - thin
        return RedirectResponse(url=f"{canonical}/{path}", status_code=307)

    @app.delete(f"{legacy}/{{path:path}}", include_in_schema=False)
    async def _legacy_delete(path: str) -> RedirectResponse:  # pragma: no cover - thin
        return RedirectResponse(url=f"{canonical}/{path}", status_code=307)


#: Sous-espace réservé aux routes héritées dont le chemin est déjà pris sous
#: ``/api/v1`` par une implémentation différente. Ce n'est pas une seconde base :
#: le Cockpit continue de n'utiliser que ``/api/v1``.
LEGACY_SUBSPACE = f"{API_V1}/legacy"


def _split_router(router: APIRouter, prefix: str,
                  taken: set[tuple[str, str]]) -> tuple[APIRouter, APIRouter]:
    """Sépare ``router`` en (routes libres, routes en collision) sous ``prefix``.

    Les callables sont réutilisés tels quels : il n'existe toujours qu'une seule
    implémentation de chaque handler, quel que soit le nombre de préfixes sous
    lesquels elle est servie.
    """
    free, clashing = APIRouter(), APIRouter()
    for route in router.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        keys = ([("WS", prefix + path)] if methods is None
                else [(m, prefix + path) for m in sorted(methods)])
        target = clashing if any(k in taken for k in keys) else free
        target.routes.append(route)
    return free, clashing


def mount_legacy_under_api(app: Any, modules: Iterable[Any],
                           *, prefix: str = API_V1) -> MountReport:
    """Sert les routeurs historiques sous le namespace canonique.

    Hermes exposait deux racines : ``/api/v1`` pour les sous-systèmes HOS et la
    racine nue pour l'API Hermes-Ollama d'origine (``/files``, ``/git``,
    ``/tasks``…). Le client du Cockpit n'en connaît qu'une, donc la seconde
    moitié du produit lui était inaccessible (P-002).

    Chaque route héritée est republiée sous ``/api/v1``. Quand le chemin y est
    déjà occupé par une implémentation **différente** — ``/skills`` est servi par
    ``api.routes.skills.list_skills`` d'un côté et ``skills.routes.get_skills``
    de l'autre — la republier écraserait silencieusement l'une des deux. Ces
    routes-là partent sous :data:`LEGACY_SUBSPACE`, ce qui les rend joignables
    depuis la base unique sans masquer quoi que ce soit.

    Les montages historiques à la racine restent en place : les casser romprait
    tout client existant, et ils ne coûtent rien puisque les handlers sont
    partagés.
    """
    report = MountReport()

    taken: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or {"WS"}
        for method in methods:
            taken.add((method, path))

    for module in modules:
        router = getattr(module, "router", None)
        if router is None:
            continue
        free, clashing = _split_router(router, prefix, taken)

        if free.routes:
            app.include_router(free, prefix=prefix)
            report.routers += 1
            report.mounted += len(free.routes)
            for route in free.routes:
                path = prefix + getattr(route, "path", "")
                report.paths.append(path)
                for method in (getattr(route, "methods", None) or {"WS"}):
                    taken.add((method, path))

        if clashing.routes:
            app.include_router(clashing, prefix=LEGACY_SUBSPACE)
            report.mounted += len(clashing.routes)
            for route in clashing.routes:
                path = LEGACY_SUBSPACE + getattr(route, "path", "")
                report.paths.append(path)
                # Signalé, pas masqué : ces chemins portent deux implémentations
                # distinctes dans le produit et le rapport doit le dire.
                report.collisions.append(
                    f"{getattr(route, 'path', '')} -> {LEGACY_SUBSPACE}")

    if report.collisions:
        logger.info(
            "%d route(s) héritée(s) servie(s) sous %s pour éviter un masquage : %s",
            len(report.collisions), LEGACY_SUBSPACE,
            ", ".join(sorted(set(report.collisions))[:8]),
        )
    logger.info("routes héritées republiées sous %s : %d", prefix, report.mounted)
    return report
