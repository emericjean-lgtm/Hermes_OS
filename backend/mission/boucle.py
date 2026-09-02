"""Exécuter, vérifier, diagnostiquer, réparer — et savoir s'arrêter (HOS-230).

## Ce qui existait, mesuré

Deux pilotes de reprise, et aucun ne connaît de contrat :

- `node_execution` fait tourner un `while task.status == PENDING`. Il
  reprend les **pannes de runtime**, parce que `execute_task` remet la
  tâche en attente ; il ne sait rien de ce qui devait être vrai à la fin.
- `retry_policy.decide` travaille au niveau de la **mission**, uniquement
  sur contradiction, et `graph_executor._suggest_retry` **publie** au
  lieu de relancer — avec sa raison, qui est juste : « relaunching a
  mission graph is the caller's decision (it owns scheduling, budgets and
  the operator's consent) ».

Ce module ne contredit pas ce choix : c'est une **bibliothèque que
l'appelant pilote**, pas un relanceur caché. `tourner()` ne part que si
quelqu'un l'appelle, et rend ce qu'il a constaté.

## Ce n'est pas une seconde boucle agentique

La règle qui prime sur tout dans ce dépôt : Hermes Agent est le cerveau,
Hermes OS n'exécute pas de seconde boucle agentique sur le chemin d'une
mission. Elle a déjà été violée une fois, et
`test_hermes_agent_is_the_brain.py` la garde.

Cette boucle-ci ne raisonne pas, ne choisit pas d'outil et n'appelle
aucun modèle. Elle enchaîne quatre appels que **l'appelant lui fournit**,
et décide seulement de continuer ou de s'arrêter — sur des verdicts et
des causes mesurés ailleurs. C'est de l'ordonnancement, pas de la
cognition.

## Assembler, pas recréer

Tout vient d'ailleurs, et c'est le point :

- le **contrat** et sa conjonction — HOS-221 ;
- le **verdict tri-état** — HOS-222 : `indisponible` n'est jamais un
  succès, et c'est ce qui arrête une boucle qui tournerait sur une
  ignorance ;
- le **point de reprise** — HOS-223 ;
- la **cause** et son remède — HOS-225 : une cause non reprenable arrête
  tout de suite, sans brûler le budget ;
- le **relais** — HOS-229 : ce qui a échoué arrive à la réparation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from backend.mission.relais import Phase, Relais
from backend.runs.contrat import Verdict

logger = logging.getLogger("hermes_os.mission.boucle")

#: Le catalogue d'événements, à côté de son producteur — patron HOS-181,
#: confirmé par HOS-227.
BOUCLE_EVENTS: dict[str, str] = {
    "tour": "boucle.tour",
    "arret": "boucle.arret",
}

#: Combien de tours au maximum, faute de mieux. Deux, comme
#: `retry_policy.DEFAULT_MAX_ATTEMPTS`, et pour la raison qui y est
#: écrite : sur ce déploiement une passe coûte des minutes d'inférence
#: locale, et un modèle qui échoue deux fois sur les mêmes preuves ne
#: réussira pas à la cinquième.
TOURS_PAR_DEFAUT = 2


class Arret(str, Enum):
    """Pourquoi la boucle s'est arrêtée. Jamais « terminée » tout court.

    Six raisons, et elles n'appellent pas la même suite. Les fondre en
    un booléen ferait chercher un défaut de budget là où il y a un refus
    assumé — l'erreur que HOS-225 a déjà eu à corriger dans l'abandon
    d'une tâche.
    """

    CONTRAT_TENU = "contrat_tenu"
    #: Le budget de tours est épuisé sans que le contrat soit tenu.
    BUDGET = "budget"
    #: Une cause dont le remède dit de ne pas reprendre — un refus de
    #: politique, un déclenchement de sécurité.
    CAUSE_NON_REPRENABLE = "cause_non_reprenable"
    #: La vérification n'a pas su conclure. **Pas un succès.**
    INVERIFIABLE = "inverifiable"
    #: L'exécution a levé quelque chose que la boucle ne sait pas traiter.
    ERREUR = "erreur"
    #: Aucun contrat : il n'y a rien à tenir, donc rien à boucler.
    SANS_CONTRAT = "sans_contrat"


@dataclass
class Tour:
    """Ce qu'un passage a produit."""

    numero: int
    phase: str
    verdict: str = ""
    cause: str = ""
    detail: str = ""


@dataclass
class Issue:
    """Ce que la boucle a constaté, et ce qu'elle propose ensuite."""

    arret: Arret
    tenu: bool = False
    tours: list[Tour] = field(default_factory=list)
    relais: Optional[Relais] = None
    #: L'identifiant du point de reprise pris avant le premier tour, s'il
    #: y en a eu un. **La boucle ne restaure jamais d'elle-même** : elle
    #: le propose, l'appelant décide, et la restauration passe par Aegis
    #: (HOS-223). Une boucle qui effacerait un workspace de son propre
    #: chef serait le geste destructeur le moins surveillé du système.
    checkpoint: str = ""
    raison: str = ""

    @property
    def tours_faits(self) -> int:
        return len({t.numero for t in self.tours})

    def resume(self) -> str:
        texte = f"{self.arret.value} après {self.tours_faits} tour(s)"
        if self.raison:
            texte += f" — {self.raison}"
        return texte


#: Ce que l'appelant fournit. Deux fonctions, pas plus : la boucle
#: n'appelle aucun modèle et ne connaît ni prompt ni runtime.
Executant = Callable[[Relais, Phase], Any]
Verificateur = Callable[[Relais], Any]


class Boucle:
    """Enchaîne exécution, vérification, diagnostic et réparation.

    Ne prend aucune décision cognitive : elle lit des verdicts et des
    causes produits ailleurs, et choisit de continuer ou non.
    """

    def __init__(self, executer: Executant, verifier: Verificateur, *,
                 tours: int = TOURS_PAR_DEFAUT,
                 point_de_reprise: Any = None) -> None:
        self._executer = executer
        self._verifier = verifier
        self._tours = max(1, int(tours))
        # Une fonction `(relais) -> identifiant`, ou None. Injectée
        # plutôt qu'appelée en dur : prendre un point de reprise coûte,
        # et l'appelant est le seul à savoir si ce travail le mérite.
        self._point_de_reprise = point_de_reprise

    def tourner(self, relais: Relais) -> Issue:
        """Faire tourner la boucle jusqu'à un arrêt nommé."""
        if relais.contrat is None:
            # Sans contrat, il n'y a rien à tenir — et boucler sur rien
            # produirait des tours qui se déclareraient réussis parce
            # qu'aucun critère ne les contredit. C'est le `success: true`
            # au-dessus de rien, en boucle.
            return Issue(arret=Arret.SANS_CONTRAT, tenu=False, relais=relais,
                         raison="aucun contrat : rien à vérifier")

        issue = Issue(arret=Arret.BUDGET, relais=relais)
        issue.checkpoint = self._prendre_le_filet(relais)

        for numero in range(1, self._tours + 1):
            phase = Phase.EXECUTION if numero == 1 else Phase.REPARATION

            try:
                self._executer(relais, phase)
            except Exception as exc:
                if self._arreter_sur_l_erreur(issue, numero, phase, exc):
                    return self._clore(issue)
                continue

            issue.tours.append(Tour(numero=numero, phase=phase.value,
                                    detail="exécuté"))

            verification = self._verifier(relais)
            verdict = self._verdict_de(verification)
            issue.tours.append(Tour(numero=numero,
                                    phase=Phase.VERIFICATION.value,
                                    verdict=verdict.value))

            if verdict is Verdict.REUSSI and relais.contrat.tenu:
                issue.arret = Arret.CONTRAT_TENU
                issue.tenu = True
                issue.raison = relais.contrat.resume()
                return self._clore(issue)

            if verdict is Verdict.INDISPONIBLE:
                # HOS-222 : on ne reprend pas sur une ignorance, et
                # surtout on ne la range pas du côté du succès. Boucler
                # ici userait le budget à re-produire une mesure qui
                # n'aboutit pas.
                issue.arret = Arret.INVERIFIABLE
                issue.raison = ("la vérification n'a pas su conclure — "
                                "ce n'est ni un succès ni un échec")
                return self._clore(issue)

            # Échoué : on porte les preuves à la réparation. C'est la
            # moitié utile de `retry_policy` — rendre des preuves plutôt
            # que relancer le même prompt.
            self._nourrir_le_relais(relais, verification)

        issue.raison = (f"{self._tours} tour(s) sans que le contrat soit tenu : "
                        + relais.contrat.resume())
        return self._clore(issue)

    # ── Les décisions d'arrêt ────────────────────────────────────────

    def _arreter_sur_l_erreur(self, issue: Issue, numero: int, phase: Phase,
                              exc: Exception) -> bool:
        """Une exécution a levé. La cause dit si ça vaut la peine d'insister.

        Une cause non reprenable arrête **tout de suite**, sans brûler le
        budget : réessayer un refus de politique inonde la file
        d'approbation, ce que `approvals.py` décrit déjà.
        """
        from backend.runs.taxonomie import classer, remede

        classement = classer(str(exc))
        soin = remede(classement.cause)
        issue.tours.append(Tour(numero=numero, phase=phase.value,
                                cause=classement.cause.value,
                                detail=str(exc)[:400]))
        # Porté au relais pour que la réparation sache ce qui a échoué,
        # et pas seulement qu'il y a eu un échec (HOS-229).
        issue.relais.echec = str(exc)[:400] if issue.relais else ""
        if issue.relais is not None:
            issue.relais.cause = classement.cause.value

        if not soin.reessayer:
            issue.arret = Arret.CAUSE_NON_REPRENABLE
            issue.raison = soin.explication
            return True
        return False

    @staticmethod
    def _verdict_de(verification: Any) -> Verdict:
        """Le verdict, quel que soit ce que l'appelant a rendu.

        Accepte un `MissionVerification` (qui porte `.verdict`), un
        `Verdict` nu, ou une chaîne. Une vérification illisible rend
        `INDISPONIBLE` — jamais `REUSSI` par défaut d'information.
        """
        if isinstance(verification, Verdict):
            return verification
        brut = getattr(verification, "verdict", verification)
        if isinstance(brut, Verdict):
            return brut
        try:
            return Verdict(str(brut))
        except ValueError:
            return Verdict.INDISPONIBLE

    @staticmethod
    def _nourrir_le_relais(relais: Relais, verification: Any) -> None:
        """Verser au relais ce que la vérification a constaté."""
        resume = getattr(verification, "resume", None)
        constat = ""
        if callable(resume):
            try:
                constat = str(resume())
            except Exception:  # pragma: no cover
                constat = ""
        constat = constat or str(getattr(verification, "raison", "") or "")
        if constat:
            relais.ajouter_preuve("vérification", constat, "echoue")

    def _prendre_le_filet(self, relais: Relais) -> str:
        """Un point de reprise avant le premier tour, si l'appelant en veut.

        En meilleur effort, et **jamais** restauré d'office : la boucle
        le propose dans son issue, l'appelant décide, et la restauration
        passe par Aegis. Une boucle qui effacerait un workspace de son
        propre chef serait le geste destructeur le moins surveillé du
        système.
        """
        if self._point_de_reprise is None:
            return ""
        try:
            return str(self._point_de_reprise(relais) or "")
        except Exception:
            logger.warning("point de reprise impossible pour la boucle",
                           exc_info=True)
            return ""

    def _clore(self, issue: Issue) -> Issue:
        self._publier("arret", {
            "arret": issue.arret.value, "tenu": issue.tenu,
            "tours": issue.tours_faits, "raison": issue.raison,
            "checkpoint": issue.checkpoint,
            "mission": issue.relais.mission if issue.relais else "",
            "run": issue.relais.run if issue.relais else "",
        })
        return issue

    @staticmethod
    def _publier(cle: str, charge: dict) -> None:
        try:
            from backend.core.event_hub import get_event_hub

            get_event_hub().publish(BOUCLE_EVENTS[cle], charge)
        except Exception:  # pragma: no cover - la trace ne casse pas la boucle
            logger.debug("événement de boucle non publié", exc_info=True)


__all__ = ["Arret", "BOUCLE_EVENTS", "Boucle", "Executant", "Issue",
           "TOURS_PAR_DEFAUT", "Tour", "Verificateur"]
