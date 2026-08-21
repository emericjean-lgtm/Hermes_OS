"""Le chat de l'Assistant servi par la session d'agent (HOS-141).

Jusqu'ici le harnais ne servait que les missions. Le chat, lui, appelait
`BaseAgent.respond_events` — donc Ollama en direct, avec les seuls outils
`workspace_*` que Hermes OS lui expose et aucune mémoire au-delà de
l'historique que le module de conversation reconstruit à chaque tour.

Ce que la session apporte ici, et que le chemin direct ne peut pas offrir :

* **les outils de l'agent**, pas seulement ceux que Hermes OS réimplémente —
  mesuré au démarrage d'une session, 16 outils MCP en plus de son propre
  toolset ;
* la compression de contexte quand la conversation s'allonge, au lieu de
  l'erreur terminale qui la clôt ;
* la continuité entre le chat et les missions **du même projet** : la clé de
  session est la même, donc une question posée dans le chat sur un dossier
  bénéficie de ce qu'une mission y a fait.

## Ce qui n'a pas changé, et ne devait pas

La session, l'historique, l'intention et l'approbation restent au module de
conversation. Ce fichier ne fait que remplacer l'inférence, exactement là où
`respond_events` l'assurait — et jamais quand aucun projet n'est lié : sans
workspace, le harnais n'a rien à faire durer, et le chemin direct reste
strictement meilleur.

## Le flux, et pourquoi il est obligatoire

Une tâche de mission tolère qu'un tour rende tout d'un coup. Une
conversation non : une minute d'attente muette est indiscernable d'une
panne. Le client ACP émet donc chaque morceau au moment où il arrive, et ce
module fait le pont entre son rappel synchrone et l'itérateur asynchrone
que la route attend — par une file, jamais en accumulant.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger("hermes_os.conversation.harnais")

#: Ce que la route lit d'un morceau. Même forme que les événements de
#: `respond_events` — `kind` et `text` —, pour que le corps de la réponse
#: n'ait pas à savoir d'où vient ce qu'il sérialise.
@dataclass
class Morceau:
    kind: str
    text: str
    tool_calls: Any = None


@dataclass
class Verdict:
    """Ce que la route doit savoir du tour, une fois fini.

    Nommé comme la `decision` de `respond_events` du point de vue de la
    route : mêmes champs lus (`model`, `num_ctx`), pour que le chemin de
    sortie soit commun.
    """

    model: str = ""
    num_ctx: int = 0
    abouti: bool = False
    erreur: str = ""
    jetons_entree: int = 0


#: `reponse`/`pensee` cote ACP contre `content`/`thinking` cote NDJSON. La
#: table est ici plutot qu'en ligne pour que les deux vocabulaires se lisent
#: cote a cote : ce sont deux protocoles differents, pas un renommage.
_GENRES = {"reponse": "content", "pensee": "thinking"}


@dataclass
class _Pont:
    file: asyncio.Queue = field(default_factory=asyncio.Queue)

    def emettre(self, genre: str, fragment: str) -> None:
        """Appelé depuis la lecture du flux ACP, dans la même boucle.

        `put_nowait` direct, et c'est une correction : une première version
        passait par `call_soon_threadsafe` « au cas où » la lecture migrerait
        vers un thread. Elle **différait** chaque morceau d'un tour de
        boucle, si bien que la sentinelle de fin — posée, elle, directement —
        les doublait tous. Un tour rapide rendait donc une réponse vide.

        La prudence inutile a produit exactement le défaut qu'elle prétendait
        prévenir. Le lecteur ACP est une coroutine de cette boucle ; si cela
        changeait un jour, c'est la file entière qu'il faudrait revoir, pas
        cette ligne.
        """
        kind = _GENRES.get(genre)
        if kind:
            self.file.put_nowait(Morceau(kind=kind, text=fragment))


def disponible(project_root: str) -> tuple[bool, str]:
    """Le chat peut-il être servi par le harnais ? Et sinon, pourquoi.

    Rendu comme un couple pour que l'appelant le **journalise** : un chat
    qui bascule silencieusement entre deux moteurs aux capacités
    différentes est indébogable — la même question donnerait deux réponses
    sans que rien n'explique l'écart.
    """
    if not project_root:
        return False, "aucun projet lié à la session : rien à faire durer"
    import os

    if os.environ.get("HERMES_HARNAIS", "1").strip().lower() in (
            "0", "false", "non", "off"):
        return False, "harnais coupé par HERMES_HARNAIS"

    from backend.ral.adapters.prerequis_harnais import verifier

    etat = verifier()
    return (True, "") if etat.pret else (False, etat.explication())


async def repondre(
    message: str, *, project_id: str, project_root: str,
    modele: str = "", amorce: str = "",
    delai: float = 900.0,
) -> tuple[AsyncIterator[Morceau], Verdict]:
    """Sert un tour de conversation par la session du projet.

    Rend un itérateur de morceaux **et** un verdict que l'appelant lira une
    fois l'itérateur épuisé : le verdict n'est renseigné qu'à la fin, parce
    que `stopReason` et l'usage n'arrivent qu'avec le résultat JSON-RPC —
    jamais dans les notifications qui portent le texte.
    """
    from backend.ral.adapters.sessions_de_mission import registre

    pont = _Pont()
    verdict = Verdict(model=modele)
    cle = f"projet:{project_id}"
    fini = object()

    async def _tour() -> None:
        try:
            tour = await registre().tour(
                cle, project_root, message, amorce=amorce, modele=modele,
                delai=delai, au_fil_de_l_eau=pont.emettre)
            verdict.abouti = tour.abouti
            verdict.erreur = tour.erreur
            verdict.jetons_entree = tour.jetons_entree
            if not tour.abouti and not tour.texte.strip():
                # Un tour sans texte ne doit pas ressembler à une réponse
                # vide : l'utilisateur croirait le modèle laconique alors
                # que la session a échoué.
                pont.file.put_nowait(Morceau(
                    kind="error",
                    text=tour.erreur or f"tour non abouti (stop={tour.stop!r})"))
        except Exception as erreur:  # noqa: BLE001 - dit, jamais avalé
            logger.warning("harnais de conversation en échec", exc_info=True)
            verdict.erreur = f"{type(erreur).__name__}: {erreur}"
            pont.file.put_nowait(Morceau(kind="error", text=verdict.erreur))
        finally:
            pont.file.put_nowait(fini)

    tache = asyncio.create_task(_tour())

    async def _flux() -> AsyncIterator[Morceau]:
        try:
            while True:
                element = await pont.file.get()
                if element is fini:
                    return
                yield element
        finally:
            # Le client a pu raccrocher. Le tour, lui, continue côté agent —
            # l'interrompre ici perdrait un travail déjà engagé, et la
            # session le gardera pour le tour suivant.
            if not tache.done():
                logger.debug("flux de conversation abandonné avant la fin")

    return _flux(), verdict


def fenetre_de(modele: str) -> int:
    """La fenêtre réellement servie, pour l'indicateur de contexte.

    Lue depuis le catalogue plutôt qu'estimée : `num_ctx` y est mesuré par
    modèle, et l'endpoint `/v1` qu'emprunte l'agent ne le transporte pas —
    c'est le Modelfile qui décide, et le catalogue qui l'enregistre.
    """
    try:
        from backend.core.config import load_models_config

        for spec in (load_models_config().get("roles") or {}).values():
            if spec.get("model") == modele:
                return int(spec.get("num_ctx") or 0)
    except Exception:  # pragma: no cover - catalogue illisible
        logger.debug("fenêtre inconnue pour %r", modele, exc_info=True)
    return 0
