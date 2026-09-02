"""POST /security/evaluate — ask Aegis whether an action is allowed.

This is the integration point future tools (Atlas's file/git tools, etc.)
will call before doing anything mutating. Exposed as its own endpoint now
so the engine is independently testable and usable ahead of those tools
existing (cahier des charges §17).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.aegis import AegisAgent
from backend.core.agent_registry import AgentNotFoundError, get_agent_registry
from backend.security.aegis_engine import ActionRequest

logger = logging.getLogger("hermes_os.api.security")

router = APIRouter()


class EvaluateRequest(BaseModel):
    action_type: str
    description: str
    target_path: str | None = None
    requesting_agent: str = "user"
    task_id: str | None = None
    project_id: str | None = None
    # When true and the verdict is require_human_validation, also runs
    # the LLM advisory pass (AegisAgent.advise()) and includes its text
    # in the response. No-op (and no extra LLM call) for allow/deny —
    # opt-in since it's an extra model call, not a default cost.
    include_advisory: bool = False


class EvaluateResponse(BaseModel):
    verdict: str
    reason: str
    action_type: str
    advisory: str | None = None


@router.post("/security/evaluate")
async def evaluate(request: EvaluateRequest) -> EvaluateResponse:
    registry = get_agent_registry()

    try:
        aegis: AegisAgent = registry.get("aegis")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    action = ActionRequest(
        action_type=request.action_type,
        description=request.description,
        target_path=request.target_path,
        requesting_agent=request.requesting_agent,
        task_id=request.task_id,
        project_id=request.project_id,
    )
    decision = aegis.evaluate(action)
    if request.include_advisory:
        decision = await aegis.advise(action, decision)

    return EvaluateResponse(
        verdict=decision.verdict.value,
        reason=decision.reason,
        action_type=decision.action_type,
        advisory=decision.advisory,
    )

def _aegis() -> AegisAgent:
    """Same lookup /security/evaluate does, factored out for the approval
    routes below."""
    try:
        return get_agent_registry().get("aegis")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/security/approvals")
async def list_approvals(status: str | None = None, project_id: str | None = None) -> list[dict]:
    """Queue of actions Aegis refused pending a human decision — the data
    behind §23's security view."""
    return _aegis().list_approvals(status=status, project_id=project_id)


class ApprovalDecision(BaseModel):
    approved: bool
    #: HOS-224. Absente, la décision reste ce qu'elle était : un accord
    #: exact, à usage unique. Une portée doit être demandée, et nommer
    #: sa racine — le corps de requête ne peut pas en obtenir une par
    #: omission.
    portee: str = "action"
    portee_racine: str | None = None
    usages: int | None = None


@router.post("/security/approvals/{approval_id}")
async def decide_approval(approval_id: str, decision: ApprovalDecision) -> dict:
    """Relay a human yes/no.

    Par défaut : usage unique, limité dans le temps, pour cette action
    exacte — jamais une permission permanente.

    Avec `portee: "arborescence"` et une `portee_racine`, l'accord couvre
    un type d'action sous un dossier, avec un budget d'usages plafonné et
    une expiration plus courte (HOS-224). Une racine manquante est un
    400, pas un accord silencieusement plus large.
    """
    try:
        result = _aegis().decide_approval(
            approval_id, approved=decision.approved, portee=decision.portee,
            portee_racine=decision.portee_racine, usages=decision.usages)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"No approval {approval_id!r}")
    return result


def _matrice():
    """La matrice réellement en service, pas une relecture du fichier.

    Aegis lit `autonomy_level` sur cet objet à chaque évaluation : c'est
    donc lui qu'il faut modifier pour qu'un changement prenne effet, et lui
    qu'il faut lire pour rapporter ce qui s'applique vraiment. Relire
    `config/security.yaml` rapporterait ce qui est écrit, pas ce qui
    s'applique — la distinction que tout ce dépôt s'efforce de tenir.
    """
    return _aegis()._engine._matrix  # noqa: SLF001


@router.get("/security/autonomy")
async def get_autonomy() -> dict:
    """Le niveau en vigueur, ceux disponibles, et ce que chacun change.

    Les quatre niveaux du §17.5 existaient depuis le début, mais rien ne
    les exposait : on ne pouvait ni savoir lequel s'appliquait ni en
    changer sans éditer un fichier et redémarrer (HOS-115).
    """
    from backend.security import autonomy

    courant = _matrice().autonomy_level
    return {
        "level": courant,
        "levels": [
            {"name": nom, "effect": autonomy.EFFETS.get(nom, "")}
            for nom in autonomy.NIVEAUX
        ],
        "overridden": autonomy.lire_derogation() is not None,
        # §17.3 ne se contourne à aucun niveau. L'annoncer ici évite que
        # l'interface laisse croire qu'un curseur au maximum supprime toute
        # validation — il ne le fait pas, et ne doit pas le laisser espérer.
        "always_validated": sorted(
            nom for nom in _matrice().known_categories()
            if (policy := _matrice().get_category(nom)) and policy.mandatory_validation
        ),
    }


class AutonomyChange(BaseModel):
    level: str


@router.put("/security/autonomy")
async def set_autonomy(change: AutonomyChange) -> dict:
    """Changer le niveau, immédiatement et durablement.

    Immédiatement parce qu'Aegis relit l'attribut à chaque évaluation ;
    durablement parce que la dérogation est écrite à côté des données du
    projet — jamais dans `config/security.yaml`, dont les commentaires
    expliquent chaque catégorie et qu'un sérialiseur détruirait.
    """
    from backend.security import autonomy

    try:
        niveau = autonomy.ecrire_derogation(change.level)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _matrice().autonomy_level = niveau
    logger.info("niveau d'autonomie changé en %r via l'API", niveau)
    return await get_autonomy()


@router.delete("/security/autonomy")
async def reset_autonomy() -> dict:
    """Revenir au niveau écrit dans `config/security.yaml`."""
    from backend.core.config import load_security_config
    from backend.security import autonomy

    autonomy.effacer_derogation()
    _matrice().autonomy_level = load_security_config().get("autonomy_level", "low")
    return await get_autonomy()
