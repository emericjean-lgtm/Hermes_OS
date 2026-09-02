"""Quel fournisseur appeler maintenant, et lequel laisser tranquille (HOS-228).

## Ce qui existait, mesuré

La roadmap annonçait « le disjoncteur de `task_executor` et la santé de
runtime sont réels et branchés ». Vérifié :

- `RealTaskExecutor._record_failure` incrémente `self._failures`, qui
  n'est **lu qu'une fois** — pour une ligne de statistiques. Rien
  n'ouvre de circuit. C'est un compteur, pas un disjoncteur.
- `RecoveryManager` a une vraie logique de cooldown et de backoff, et
  n'est **instancié nulle part** hors des tests. Cinquième orphelin,
  après `approvals`, `DatabaseManager`, `MigrationManager` et le
  `backup_path` de `propose_write`.
- `has_quota`, en revanche, **est** consommé : `AdaptiveRouter` l'appelle
  via `catalog.has_budget`. Cette partie-là du diagnostic était juste.

Cinquième prémisse de roadmap fausse, et la première que j'avais moi-même
corrigée deux jalons plus tôt.

## Pourquoi pas `RecoveryManager`

Il **exécute une reprise** sur un composant — le redémarrer. Un courtier
**s'abstient de choisir** un fournisseur pendant un temps. Deux verbes
différents : réutiliser le premier demanderait d'enregistrer une action de
reprise vide pour n'en garder que la comptabilité de cooldown, c'est-à-dire
de le plier jusqu'à ce qu'il ne dise plus ce qu'il dit.

## Ce que le courtier ajoute

Le cycle que le cahier décrit :

    429 → QUOTA → fournisseur B          et non
    429 → même fournisseur → 429 → …

La taxonomie de HOS-225 nomme la cause ; le courtier en tire une durée
d'écart. Elles ne sont pas les mêmes selon la cause, et c'est le point :

- **quota** — le pool gratuit d'OpenRouter est partagé par clé et se
  réarme à la minute ou à la journée. Réessayer dans la seconde est
  garanti d'échouer ;
- **fournisseur** — un service qui n'a pas répondu peut répondre dans
  dix secondes ; mais trois échecs de suite disent autre chose, et le
  circuit s'ouvre ;
- **modèle, sémantique, vérification** — ce n'est **pas** la faute du
  fournisseur. Lui mettre un écart pour une sortie que le modèle a ratée
  le mettrait à l'écart pour une raison qui ne le concerne pas ;
- **politique, sécurité** — un refus n'est pas une panne.

Et un **succès referme**. Sans ça, un disjoncteur ouvert par un incident
passager tue le fournisseur jusqu'au redémarrage — ce qui ressemble
exactement à un fournisseur en panne, et se débogue mal.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.runs.registre import Cause

logger = logging.getLogger("hermes_os.ral.courtier")

#: Le catalogue d'événements, à côté de son producteur — le patron de
#: HOS-181, revu au passage en HOS-227 : `collect_known_topics()`
#: assemble la liste blanche depuis ces dictionnaires-là.
COURTIER_EVENTS: dict[str, str] = {
    "ecarte": "cloud.fournisseur_ecarte",
    "retabli": "cloud.fournisseur_retabli",
}

#: Combien d'échecs consécutifs **imputables au fournisseur** ouvrent le
#: circuit. Trois : un incident isolé est un incident, deux peuvent être
#: une coïncidence, trois sont un motif. Plus haut, on paie trois fois le
#: délai d'attente avant de basculer ; plus bas, un hoquet réseau suffit
#: à écarter un fournisseur qui va bien.
SEUIL_DISJONCTEUR = 3

#: Combien de temps le circuit reste ouvert. Deux minutes : assez pour
#: qu'une panne courte se résorbe, assez peu pour qu'une bascule vers le
#: local ne devienne pas permanente sans que personne l'ait décidé.
OUVERTURE_S = 120.0

#: Les durées d'écart par cause. Seules les causes **imputables au
#: fournisseur** y figurent : une cause absente de cette table ne met
#: personne à l'écart, ce qui est le comportement voulu et non un oubli.
ECARTS: dict[Cause, float] = {
    # Le pool gratuit est partagé par clé et se réarme à la minute ou à
    # la journée. `taxonomie.remede(QUOTA).attendre_s` vaut 60 s, et
    # c'est la même valeur pour la même raison.
    Cause.QUOTA: 60.0,
    # Un service qui n'a pas répondu peut répondre dans dix secondes.
    Cause.FOURNISSEUR: 10.0,
    # Manquer de ressource chez un fournisseur distant est rare mais
    # réel (file d'attente saturée) : un écart court, comme un service
    # indisponible.
    Cause.RESSOURCE: 10.0,
}

#: Combien de temps un état de quota mesuré reste cru. Une minute, comme
#: `CloudModelCatalog._DEFAULT_QUOTA_TTL_S` : le redemander à chaque
#: candidat ferait un aller-retour réseau par tâche pour une valeur qui
#: bouge lentement.
FRAICHEUR_QUOTA_S = 60.0


class Etat(str, Enum):
    DISPONIBLE = "disponible"
    #: Écarté pour un temps, à cause d'un échec nommé.
    ECARTE = "ecarte"
    #: Trop d'échecs consécutifs : le circuit est ouvert.
    OUVERT = "ouvert"
    #: Le fournisseur répond, mais son quota est épuisé — ou n'a pas pu
    #: être mesuré, ce qui revient au même ici : on ne dépense pas sur
    #: une mesure qu'on n'a pas (HOS-222).
    SANS_QUOTA = "sans_quota"


@dataclass
class _Fiche:
    """Ce que le courtier retient d'un fournisseur."""

    echecs_consecutifs: int = 0
    ecarte_jusqu_a: float = 0.0
    ouvert_jusqu_a: float = 0.0
    derniere_cause: Cause | None = None
    #: Le dernier état de quota mesuré, et quand.
    quota: Any = None
    quota_mesure_a: float = 0.0


@dataclass(frozen=True)
class Verdict:
    """Pourquoi ce fournisseur est ou n'est pas candidat."""

    fournisseur: str
    etat: Etat
    #: Secondes avant qu'il redevienne candidat. Zéro s'il l'est déjà.
    dans_s: float = 0.0
    raison: str = ""

    @property
    def candidat(self) -> bool:
        return self.etat is Etat.DISPONIBLE


class Courtier:
    """Choisit un fournisseur, et retient pourquoi il en a écarté d'autres.

    Sans état persistant : un redémarrage repart avec tous les
    fournisseurs disponibles. C'est délibéré — un écart est une réaction
    à un incident en cours, et le faire survivre au redémarrage
    écarterait un fournisseur pour une panne d'hier.
    """

    def __init__(self, *, seuil: int = SEUIL_DISJONCTEUR,
                 ouverture_s: float = OUVERTURE_S,
                 horloge: Any = None) -> None:
        self._seuil = seuil
        self._ouverture_s = ouverture_s
        # Injectable pour que les tests n'aient pas à dormir : une garde
        # qui attend deux minutes n'est pas exécutée.
        self._maintenant = horloge or time.monotonic
        self._verrou = threading.RLock()
        self._fiches: dict[str, _Fiche] = {}

    # ── Ce qu'on lui apprend ─────────────────────────────────────────

    def signaler_echec(self, fournisseur: str, cause: Cause | None) -> None:
        """Un appel a échoué. La cause décide de ce que ça change.

        Une cause qui n'est **pas** imputable au fournisseur ne le touche
        pas : un modèle qui produit une sortie inutilisable ne dit rien
        de la santé d'OpenRouter, et l'écarter pour ça le retirerait du
        jeu pour une raison qui ne le concerne pas.
        """
        ecart = ECARTS.get(cause) if cause is not None else None
        if ecart is None:
            logger.debug("échec non imputable à %s (cause %s)", fournisseur,
                         cause.value if cause else "inconnue")
            return

        with self._verrou:
            fiche = self._fiches.setdefault(fournisseur, _Fiche())
            fiche.echecs_consecutifs += 1
            fiche.derniere_cause = cause
            maintenant = self._maintenant()
            fiche.ecarte_jusqu_a = max(fiche.ecarte_jusqu_a, maintenant + ecart)
            ouvert = fiche.echecs_consecutifs >= self._seuil
            if ouvert:
                fiche.ouvert_jusqu_a = maintenant + self._ouverture_s

        self._publier("ecarte", {
            "fournisseur": fournisseur,
            "cause": cause.value,
            "ecart_s": ecart,
            "echecs_consecutifs": fiche.echecs_consecutifs,
            "circuit_ouvert": ouvert,
        })

    def signaler_succes(self, fournisseur: str) -> None:
        """Un appel a réussi. Le compteur repart de zéro.

        Sans ça, un disjoncteur ouvert par un incident passager tue le
        fournisseur jusqu'au redémarrage — ce qui ressemble exactement à
        un fournisseur en panne, et se débogue mal.
        """
        with self._verrou:
            fiche = self._fiches.get(fournisseur)
            if fiche is None or (fiche.echecs_consecutifs == 0
                                 and fiche.ouvert_jusqu_a == 0.0):
                self._fiches.setdefault(fournisseur, _Fiche())
                return
            etait_ouvert = fiche.ouvert_jusqu_a > self._maintenant()
            fiche.echecs_consecutifs = 0
            fiche.ecarte_jusqu_a = 0.0
            fiche.ouvert_jusqu_a = 0.0
            fiche.derniere_cause = None

        if etait_ouvert:
            self._publier("retabli", {"fournisseur": fournisseur})

    def noter_le_quota(self, fournisseur: str, etat: Any) -> None:
        """Ranger un état de quota mesuré, avec sa date.

        Le courtier ne va pas le chercher lui-même : il serait alors
        synchrone sur le réseau au milieu d'une décision de routage. Il
        le reçoit de qui l'a mesuré.
        """
        with self._verrou:
            fiche = self._fiches.setdefault(fournisseur, _Fiche())
            fiche.quota = etat
            fiche.quota_mesure_a = self._maintenant()

    # ── Ce qu'il répond ──────────────────────────────────────────────

    def examiner(self, fournisseur: str) -> Verdict:
        """L'état d'un fournisseur, et dans combien de temps il change."""
        with self._verrou:
            fiche = self._fiches.get(fournisseur)
            maintenant = self._maintenant()

            if fiche is None:
                return Verdict(fournisseur, Etat.DISPONIBLE)

            if fiche.ouvert_jusqu_a > maintenant:
                return Verdict(
                    fournisseur, Etat.OUVERT,
                    dans_s=fiche.ouvert_jusqu_a - maintenant,
                    raison=(f"{fiche.echecs_consecutifs} échecs consécutifs "
                            f"({fiche.derniere_cause.value if fiche.derniere_cause else '?'})"))

            if fiche.ecarte_jusqu_a > maintenant:
                return Verdict(
                    fournisseur, Etat.ECARTE,
                    dans_s=fiche.ecarte_jusqu_a - maintenant,
                    raison=(fiche.derniere_cause.value
                            if fiche.derniere_cause else "écart"))

            quota = fiche.quota
            frais = (maintenant - fiche.quota_mesure_a) < FRAICHEUR_QUOTA_S
            if quota is not None and frais and not getattr(quota, "utilisable", False):
                # `mesure_possible=False` tombe ici aussi, et c'est
                # voulu : on ne dépense pas sur une mesure qu'on n'a pas.
                return Verdict(
                    fournisseur, Etat.SANS_QUOTA,
                    raison=(getattr(quota, "detail", "")
                            or "quota indisponible ou non mesurable"))

            return Verdict(fournisseur, Etat.DISPONIBLE)

    def choisir(self, candidats: list[str]) -> str | None:
        """Le premier candidat viable, dans l'ordre donné.

        `None` plutôt qu'une exception : « aucun fournisseur distant
        disponible » est un état normal — c'est même le cas le plus
        fréquent, puisqu'aucune clé n'est configurée par défaut. Lever
        ferait échouer une mission qui devait simplement rester locale.
        """
        for nom in candidats:
            if self.examiner(nom).candidat:
                return nom
        return None

    def etats(self) -> dict[str, Verdict]:
        """Tout ce que le courtier retient. Pour l'interface et l'audit."""
        with self._verrou:
            noms = list(self._fiches)
        return {nom: self.examiner(nom) for nom in noms}

    # ── Trace ────────────────────────────────────────────────────────

    def _publier(self, cle: str, charge: dict) -> None:
        try:
            from backend.core.event_hub import get_event_hub

            get_event_hub().publish(COURTIER_EVENTS[cle], charge)
        except Exception:  # pragma: no cover - la trace ne casse pas le routage
            logger.debug("événement de courtier non publié", exc_info=True)


_courtier: Courtier | None = None
_verrou_module = threading.RLock()


def courtier() -> Courtier:
    """Le courtier du processus.

    Un seul, parce que l'état qu'il retient — « ce fournisseur vient de
    rendre trois 429 » — n'a de sens que partagé. Deux courtiers
    apprendraient chacun la moitié des incidents.
    """
    global _courtier
    with _verrou_module:
        if _courtier is None:
            _courtier = Courtier()
        return _courtier


def reinitialiser() -> None:
    """Repartir de zéro. Pour les tests, et pour un rechargement."""
    global _courtier
    with _verrou_module:
        _courtier = None


__all__ = ["COURTIER_EVENTS", "Courtier", "ECARTS", "Etat", "FRAICHEUR_QUOTA_S",
           "OUVERTURE_S", "SEUIL_DISJONCTEUR", "Verdict", "courtier",
           "reinitialiser"]
