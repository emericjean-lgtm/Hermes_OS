"""Turn a verification failure into a second, better-informed attempt (HOS-099).

HOS-092 gave missions a verdict the agent cannot talk its way out of: compare
the workspace before and after, and flag a mission that reports success while
having changed nothing. But a verdict is not a loop. The system noticed the
contradiction and stopped there, which is diagnosis without treatment.

This module closes it. Given a verification result it answers two questions:
should this mission run again, and what should it be told this time. The
second half matters more than the first — re-running the identical prompt
against a model that just failed it mostly reproduces the failure. The point
is to hand back *evidence*: what was expected, what the filesystem actually
shows, and that its own account of success was contradicted.

Deliberately mission-level, not per-node. Plenty of nodes legitimately
produce no file — "analyse the requirements", "choose an approach" — so a
node that writes nothing is not a failure signal. A whole mission that
touches nothing while claiming success is.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("hermes_os.mission.retry")

#: One retry, not more. Measured on this deployment, a mission costs minutes
#: of local inference; a model that fails twice on the same evidence is not
#: going to succeed on the fifth attempt, it just burns the machine. Raising
#: this is a decision for whoever has measured that it helps.
DEFAULT_MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class RetryDecision:
    """Whether to run again, and what to say."""

    should_retry: bool
    reason: str
    brief: Optional[str] = None
    attempt: int = 1


def decide(
    verification: Optional[dict],
    *,
    objective: str,
    attempts_made: int = 1,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> RetryDecision:
    """Decide whether a completed mission deserves another attempt.

    Retries exactly one situation: the mission reported success and the
    filesystem contradicts it. Everything else is left alone, on purpose.

    A mission that genuinely failed is not retried here — it failed for a
    reason the verification layer cannot see (a timeout, an unavailable
    runtime), and re-running it blind would just repeat that. A mission that
    was never measured is not retried either: absence of evidence is not
    evidence of absence, and retrying on it would punish every workspace-less
    mission forever.
    """
    if verification is None:
        return RetryDecision(False, "no verification available")
    if not verification.get("measured"):
        return RetryDecision(False, "nothing was measured — no workspace to compare")
    if not verification.get("contradicted"):
        return RetryDecision(False, "verification agrees with the reported result")
    if attempts_made >= max_attempts:
        return RetryDecision(
            False,
            f"already attempted {attempts_made} time(s), limit is {max_attempts}",
        )
    return RetryDecision(
        should_retry=True,
        reason="reported success but the workspace did not change",
        brief=build_retry_brief(objective, verification),
        attempt=attempts_made + 1,
    )


def preparer_reprise(mission, *, executor) -> bool:
    """Remettre une mission en état de rejouer. Rend True s'il faut marcher.

    Extrait de `mission/routes.py` (HOS-118) parce qu'il y avait **deux**
    chemins d'exécution et un seul qui reprenait. `_run_retry_if_suggested`
    n'était appelé que depuis la route ; l'orchestrateur autonome a sa
    propre boucle (`_execute_via_dag`) et ne l'appelait pas. La
    vérification tournait, le brief était produit et posé dans
    `metadata["retry_brief"]`… puis abandonné.

    C'est exactement ce que HOS-100 avait corrigé pour les missions —
    « HOS-099 a produit la décision et le brief mais s'est arrêté avant
    d'agir » — resté ouvert du côté autonome.

    **Synchrone et sans marche.** Chaque appelant garde la sienne : la route
    doit céder la main à la boucle d'événements pour que `/pause` réponde
    encore, l'orchestrateur n'en a pas besoin. Imposer une marche commune
    aurait cassé l'une des deux ; dupliquer la préparation aurait garanti
    qu'elles divergent.

    Le brief atteint l'agent par `mission.objective`, que
    `_mission_brief_for` transmet déjà — aucune plomberie neuve, et chaque
    nœud de la reprise voit la preuve, pas seulement le premier.
    """
    from backend.mission.mission_models import MissionStatus, NodeStatus

    brief = mission.metadata.pop("retry_brief", None)
    if not brief:
        return False

    attempts = int(mission.metadata.get("attempts", 1))
    mission.metadata["attempts"] = attempts + 1
    mission.metadata.setdefault("original_objective",
                                mission.objective or mission.description)
    mission.objective = brief

    logger.info("mission %s: retrying (attempt %d) — workspace contradicted "
                "the reported success", mission.mission_id, attempts + 1)

    # Tous les nœuds repartent. Une reprise par nœud serait fausse ici : la
    # mission n'a rien produit, il n'y a donc pas de travail partiel à
    # garder, et un nœud « réussi » qui n'a rien écrit est précisément ce
    # qu'on rejoue.
    for node in mission.nodes:
        node.status = NodeStatus.PENDING
        node.result_summary = ""
    executor.build_graph(mission, mission.nodes, list(mission.edges or []))
    mission.status = MissionStatus.READY
    if not executor.start_mission(mission):
        logger.warning("mission %s: could not restart for retry", mission.mission_id)
        return False
    return True


def build_retry_brief(objective: str, verification: dict) -> str:
    """What to tell the agent on the second attempt.

    Three things, in this order: the original objective (it is being asked to
    do the same work), the evidence that it did not happen, and an
    instruction to verify its own output. The evidence is the part that makes
    this different from re-sending the same prompt — a model told only "try
    again" has no reason to behave differently.

    Phrased as fact rather than accusation. "The workspace is unchanged" is
    checkable; "you failed" invites the model to apologise and produce
    another confident paragraph, which is the behaviour being corrected.
    """
    workspace = verification.get("workspace") or "the workspace"
    lines = [
        objective.strip(),
        "",
        "IMPORTANT — this task was already attempted and did not take effect.",
        f"After that attempt, {workspace} was unchanged: "
        f"{verification.get('summary', 'no file was created, modified or deleted')}.",
        "",
        "A description of the work is not the work. Use your tools to make "
        "the change, then read back what you wrote to confirm it exists on "
        "disk before reporting success.",
    ]
    return "\n".join(lines)
