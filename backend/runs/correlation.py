r"""Relier un tour de l'agent au Run qui l'a demandé (G-32, HOS-280).

Hermes OS frappe une étiquette opaque par tour, la pose dans
`_meta.hermes.turnId` de la requête ACP, et **enregistre chez lui** la
relation `étiquette → run`. L'agent la transporte et la restitue dans
`on_skill_lifecycle` (contrat G-31, `turn-id.patch`). Aucune identité ne
change de propriétaire.

    Hermes OS          Hermes Agent
    ─────────          ────────────
    run_id  R          task_id, session_id   (les siens, jamais employés ici)
    turnId  T  ────→   transporté, opaque  ────→  restitué dans l'événement
    T → R              (l'agent ne la connaît pas)

## Pourquoi un ContextVar, et pourquoi il fallait le mesurer

Le Run naît dans `mission_executor._ouvrir_le_run`, la requête ACP se
construit trois modules plus loin, et rien entre les deux ne portait le
Run — G-29 l'avait mesuré, `run_de()` n'avait aucun appelant.

Le chemin traverse `_run_coro`, qui pousse la coroutine vers une boucle
tournant **dans un autre thread** par `run_coroutine_threadsafe`. On
pouvait croire qu'un `ContextVar` n'y survivrait pas. Mesure du
2026-09-10 : il survit — `call_soon_threadsafe` copie le contexte de
l'appelant. La lecture du code disait le contraire ; c'est la mesure qui
a tranché.

## Ce que l'étiquette n'est pas

`frapper()` rend un `uuid4`. Elle n'est **dérivée de rien** : ni du
`run_id` (l'envoyer reviendrait à donner l'identité de Hermes OS à
l'agent), ni de l'horloge, ni d'un compteur. Deux tours du même Run ont
deux étiquettes ; c'est voulu — un Run émet plusieurs tours, et les
confondre perdrait lequel a produit quoi.

## Où vit la relation

Sur le **bus durable**, et c'est une règle que ce dépôt s'est déjà
donnée, écrite dans `backend/runs/registre.py` :

    « Le registre porte les runs ; le bus porte les événements ;
      run_id les relie. »

Une table `turns` serait le second magasin d'événements que ce même
commentaire refuse. Le bus est adossé à SQLite, ses identifiants sont
idempotents, et il se rejoue par plage et par motif.

**Sa rétention est de sept jours** (`EventBusImpl(retention_days=7)`).
La relation est donc interrogeable une semaine, puis élaguée. Ce n'est
pas un oubli : c'est la politique du bus, et la changer serait une
décision de bus, pas une raison de bâtir un magasin parallèle.

## Ce qui reste absent, et le reste

Sans Run lié — le chat, une tâche hors mission, un runtime qui ne passe
pas par là — `etiquette_du_tour()` rend `""`, et rien n'est posé dans la
requête. Le chemin ACP d'avant est alors exactement celui d'avant.
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from typing import Optional

logger = logging.getLogger("hermes_os.runs.correlation")

#: Le Run pour lequel le tour courant travaille, ou `""`.
#:
#: Lié par `mission_executor.execute_task`, qui tient la correspondance
#: `execution_id → run_id` **enregistrée** — pas devinée. Lu au moment où la
#: requête ACP se construit.
_run_courant: contextvars.ContextVar[str] = contextvars.ContextVar(
    "hermes_os_run_courant", default="")

#: Le topic sous lequel la relation est publiée.
TOPIC_TOUR = "run.turn.emitted"


def lier_run(run_id: str) -> contextvars.Token[str]:
    """Déclarer pour quel Run le travail qui suit est fait."""
    return _run_courant.set(str(run_id or ""))


def delier_run(jeton: contextvars.Token[str]) -> None:
    _run_courant.reset(jeton)


def run_courant() -> str:
    """Le Run lié, ou `""` — jamais une supposition."""
    return _run_courant.get()


def frapper() -> str:
    """Une étiquette de tour, opaque et neuve.

    `uuid4`, donc sans lien calculable avec le Run. Un lecteur qui
    voudrait remonter au Run doit passer par la relation enregistrée : il
    n'y a rien à déduire de l'étiquette elle-même.
    """
    return uuid.uuid4().hex


def _bus():
    """Le bus durable du processus, ou `None` s'il n'est pas installé.

    Il est posé par le cycle de vie FastAPI. Hors application — un test,
    un script — il n'y en a pas, et l'absence doit se lire comme telle
    plutôt que faire échouer le tour qu'elle décrit.
    """
    try:
        from backend.sds.runtime import get_holder

        return get_holder().bus
    except Exception:  # noqa: BLE001 - une trace ne casse pas ce qu'elle décrit
        logger.debug("bus durable indisponible", exc_info=True)
        return None


def enregistrer(turn_id: str, run_id: str) -> bool:
    """Publier `turn_id → run_id`. Rend `False` si rien n'a été écrit.

    Le booléen n'est pas décoratif : un appelant qui poserait l'étiquette
    dans la requête sans que la relation soit écrite produirait un tour
    corrélable côté agent et introuvable côté Hermes OS — la moitié d'un
    contrat, exactement ce que G-31 refusait de livrer.
    """
    if not turn_id or not run_id:
        return False
    bus = _bus()
    if bus is None:
        return False
    try:
        from backend.ral.event_bus import Topic

        bus.publish(Topic(TOPIC_TOUR),
                    {"turn_id": turn_id, "run_id": run_id},
                    publisher="hermes_os.runs.correlation",
                    causation_id=run_id)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("relation tour->run non publiee", exc_info=True)
        return False


async def run_du_tour(turn_id: str, *, jours: int = 7) -> Optional[str]:
    """Le Run d'une étiquette, ou `None`.

    `None` couvre trois cas qu'on ne cherche pas à distinguer ici, parce
    qu'ils appellent la même conduite — ne rien associer : étiquette
    jamais frappée par Hermes OS, étiquette élaguée par la rétention, bus
    absent.

    `jours` borne la fenêtre de rejeu sur la rétention du bus : chercher
    au-delà rendrait toujours `None` en coûtant le parcours.
    """
    if not turn_id:
        return None
    bus = _bus()
    if bus is None:
        return None
    from datetime import datetime, timedelta, timezone

    from backend.ral.event_bus import Topic

    depuis = datetime.now(timezone.utc) - timedelta(days=jours)
    try:
        async for evenement in bus.replay(since=depuis,
                                          topic_pattern=Topic(TOPIC_TOUR)):
            charge = getattr(evenement, "payload", None) or {}
            if charge.get("turn_id") == turn_id:
                return str(charge.get("run_id") or "") or None
    except Exception:  # noqa: BLE001
        logger.warning("rejeu du bus impossible", exc_info=True)
    return None


def etiquette_du_tour() -> str:
    """Frapper et enregistrer une étiquette pour le Run lié, ou `""`.

    Le point unique où un tour reçoit son identité. Rend `""` quand aucun
    Run n'est lié **ou** quand la relation n'a pas pu être écrite : dans
    les deux cas, la requête part sans étiquette, et l'événement de Skill
    qui en naîtra ne sera associé à rien. Une étiquette posée sans
    relation enregistrée serait pire — elle promettrait une corrélation
    que personne ne pourrait résoudre.
    """
    run = run_courant()
    if not run:
        return ""
    turn_id = frapper()
    if not enregistrer(turn_id, run):
        return ""
    return turn_id
