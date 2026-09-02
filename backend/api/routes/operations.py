"""Ce que douze jalons ont produit, servi par l'application réelle (HOS-235).

## Le défaut que ce module corrige

HOS-234 a bien créé huit routes d'opérations — et les a posées sur
`MissionControlAPI`, qui **n'est montée nulle part**. Vérifié sur le
processus en marche : `GET /api/v1/operations` rendait `404`, et
`/openapi.json` ne contenait pas la moindre route en `/api/v1/`.

`MissionControlAPI` existe, est exportée, et aucun appelant de production
ne l'inclut dans l'application. Le jalon était donc juste dans sa forme et
injoignable dans les faits — la variante la plus coûteuse de l'orphelin,
parce que ses tests passaient : ils montaient le routeur eux-mêmes.

Les routes vivent maintenant là où les autres vivent — un module de
`backend/api/routes/`, listé dans `_LEGACY_ROUTERS` — c'est-à-dire sur le
seul chemin que `backend.main` sert réellement.

## Lecture seule, entièrement

Mission Control est une **vue** du runtime, jamais une seconde autorité.
Toutes les routes sont en `GET`, et la logique vit dans
`backend.services.vue_operations`, dont deux gardes sur l'arbre
syntaxique vérifient qu'il n'écrit rien et n'ouvre aucun magasin.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.services import vue_operations

router = APIRouter(tags=["operations"])


@router.get("/operations", summary="Vue d'ensemble des opérations")
async def apercu() -> JSONResponse:
    """Registre des runs, fournisseurs, approbations, points de reprise,
    version installée et santé — en une lecture."""
    return JSONResponse(vue_operations.vue_d_ensemble())


@router.get("/operations/missions/{mission}/runs",
            summary="Les tentatives d'une mission")
async def runs_de_la_mission(mission: str) -> JSONResponse:
    return JSONResponse(vue_operations.runs_de_la_mission(mission))


@router.get("/operations/runs/{run}/lignee",
            summary="La chaîne des tentatives, de la première à celle-ci")
async def lignee(run: str) -> JSONResponse:
    """« Avec quel modèle, et pourquoi le premier essai a raté ? » — la
    question à laquelle la nuit du 29 au 30 août n'a pas su répondre."""
    return JSONResponse(vue_operations.lignee(run))


@router.get("/operations/runs/{run}/contrat",
            summary="Ce qui devait être vrai à la fin")
async def contrat(run: str) -> JSONResponse:
    return JSONResponse(vue_operations.contrat_du_run(run))


@router.get("/operations/checkpoints", summary="Les points de reprise")
async def checkpoints(workspace: Optional[str] = Query(None)) -> JSONResponse:
    return JSONResponse(vue_operations.points_de_reprise(workspace))


@router.get("/operations/fournisseurs",
            summary="Fournisseurs cloud, écarts et disjoncteurs")
async def fournisseurs() -> JSONResponse:
    return JSONResponse(vue_operations.fournisseurs())


@router.get("/operations/approbations",
            summary="Approbations en attente et portées vivantes")
async def approbations() -> JSONResponse:
    return JSONResponse(vue_operations.approbations())


@router.get("/operations/installation",
            summary="Version installée et auto-vérification")
async def installation() -> JSONResponse:
    return JSONResponse(vue_operations.installation())
