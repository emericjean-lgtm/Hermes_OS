"""Qui tranche quand plusieurs décideurs ont un avis (HOS-243).

## Le défaut

Six composants de ce dépôt décident d'un runtime ou d'un modèle. Ce
n'est pas en soi un défaut : ils répondent à des questions différentes,
sur des chemins différents, et chacun est justifié par ses propres
mesures. Le défaut est ailleurs.

`RealTaskExecutor.execute()` en consultait **deux pour la même
requête** :

    runtime_id = _runtime_demande(assignment.runtime_id
                                  or task.assigned_runtime)   # ① l'un
    ...
    runtime_demande = self._resolve_runtime(task)             # ② l'autre
    use_cloud = self._cloud_chat is not None and runtime_demande == "openrouter"
    if use_cloud:
        runtime_id = "openrouter"

① vient du coordinateur ou de `autonomous.DecisionEngine`. ② vient
d'`AdaptiveModelRouter`. Lequel gagne, et quand, n'était écrit nulle
part : c'était une **propriété émergente de l'ordre des lignes**. Dix
lignes plus loin, `elif` et `and` en décidaient.

Une précédence qui n'est écrite nulle part ne peut pas être discutée,
testée, ni conservée à travers un refactoring.

## Ce que ce module n'est pas

Ce n'est **pas** un septième décideur, et surtout pas « RALv2 ». Il ne
classe aucun modèle, n'interroge aucun profil, ne mesure aucune VRAM, ne
contacte rien. Il ne sait pas quel modèle est bon.

Il sait seulement **qui a le dernier mot**, et il l'écrit. Les six
décideurs restent exactement où ils sont, avec leurs données et leurs
mesures ; ce module range leurs avis dans un ordre déclaré et rend une
décision unique, tracée, exécutable et enregistrable.

## La précédence, telle qu'elle était et telle qu'elle reste

L'ordre ci-dessous **reproduit le comportement d'avant HOS-243**. Il
n'est pas une amélioration : le rendre explicite était le travail, le
changer en même temps aurait rendu impossible de dire lequel des deux
avait causé une régression.

1. Une **assignation explicite** l'emporte — un appelant qui nomme un
   runtime a tranché en connaissance de cause.
2. À défaut, le **décideur de la tâche**.
3. À défaut, le **défaut de l'exécuteur** — qui n'est pas une décision
   mais une valeur de repli documentée.

Sur cette base, une seule dérogation : le décideur de la tâche peut
**faire monter** l'exécution vers le cloud, et seulement si un
fournisseur cloud est réellement joignable. Le droit de monter est porté
par la proposition elle-même (`peut_monter`), faux par défaut : le
chercher sur toutes les propositions, comme le faisait HOS-243, donnait
cette autorité à n'importe quelle source future qui aurait nommé
`openrouter`.

## Recommandation défaite, assignation défaite : deux choses

HOS-243 affirmait « le décideur ne peut pas faire redescendre une
assignation explicite » et faisait exactement cela douze lignes plus
bas :

    elif monte is not None and runtime == MONTEE_AUTORISEE and not cloud_joignable:
        runtime, source_runtime = defaut_runtime, "repli, cloud injoignable"

Le code contredisait son propre contrat. HOS-244 les sépare :

- une **recommandation** vers le cloud qui ne peut pas aboutir est
  simplement défaite, et nommée dans `repli`. Elle n'engageait personne,
  et c'est déjà la politique de `_make_cloud_chat` : « cloud entièrement
  injoignable, quoi que recommande AdaptiveRouter » ;
- une **assignation** vers un runtime qui ne peut pas servir n'est pas
  remplacée. `Decision.impossible` est renseignée, et l'appelant lève
  `RuntimeUnavailableError` — le type que ce dépôt a déjà pour « the
  inference layer is down », que `MissionExecutor` classe en
  `FOURNISSEUR` et traite avec le remède `changer_de_fournisseur`.

L'échec honnête n'est donc pas une politique nouvelle : c'est celle qui
était déjà écrite, appliquée là où elle manquait.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

#: Les valeurs par lesquelles un appelant dit « je n'ai pas choisi ».
#: `agent_coordinator._select_runtime` rend littéralement `"default"` sur
#: registre vide — HOS-142 a payé une nuit entière pour l'apprendre.
NON_CHOISI = frozenset({"", "default", "auto", "any", "none", "null"})

#: Le seul runtime vers lequel une montée est permise. Nommé plutôt
#: qu'inféré : « tout runtime non local peut monter » ferait de la liste
#: des fournisseurs une décision de routage, ce qu'elle n'est pas.
MONTEE_AUTORISEE = "openrouter"


def _propre(valeur: Optional[str]) -> str:
    """Un choix, ou la chaîne vide — jamais `"default"` pris au mot."""
    texte = str(valeur or "").strip()
    return "" if texte.lower() in NON_CHOISI else texte


@dataclass(frozen=True)
class Proposition:
    """Ce qu'**un** décideur propose, et son identité.

    L'identité n'est pas décorative : sans elle, la décision finale dit
    ce qui a été choisi mais pas par qui, et « pourquoi cette mission
    a-t-elle tourné sur ce modèle ? » reste sans réponse.
    """

    source: str
    runtime: Optional[str] = None
    modele: Optional[str] = None
    #: Cette proposition a-t-elle le droit de faire **monter** l'exécution
    #: vers le cloud alors qu'une autre a emporté le runtime ?
    #:
    #: Réservé au décideur de la tâche (HOS-244). Avant, la montée était
    #: cherchée sur **toutes** les propositions : n'importe quelle source
    #: future qui aurait nommé `openrouter` aurait hérité d'une autorité
    #: que personne ne lui avait donnée. Le droit est maintenant porté par
    #: celui qui le détient, et il est faux par défaut.
    peut_monter: bool = False

    @property
    def propose_un_runtime(self) -> bool:
        return bool(_propre(self.runtime))

    @property
    def propose_un_modele(self) -> bool:
        return bool(_propre(self.modele))


@dataclass(frozen=True)
class Decision:
    """Ce qui sera exécuté, et comment on y est arrivé.

    `fournisseur` reste vide ici, délibérément : il n'est connu qu'après
    la réponse (HOS-242), et le deviner depuis le runtime ferait passer
    une supposition pour une mesure.
    """

    runtime: str
    modele: str
    source_runtime: str
    source_modele: str
    #: Non vide seulement quand une montée demandée n'a pas pu avoir lieu.
    repli: str = ""
    #: Non vide quand le runtime décidé **ne peut pas être servi** et
    #: qu'aucun repli n'est autorisé (HOS-244). L'arbitre ne lève pas :
    #: il n'exécute rien, et une exception depuis un module qui ne fait que
    #: ranger des avis serait une décision d'exécution déguisée. C'est
    #: l'appelant qui échoue, avec le type que le dépôt a déjà pour cela.
    impossible: str = ""
    #: Tout ce qui a été proposé, gagnants compris — la trace.
    propositions: tuple[Proposition, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        fait = {
            "runtime": self.runtime,
            "modele": self.modele,
            "source_runtime": self.source_runtime,
            "source_modele": self.source_modele,
        }
        if self.repli:
            fait["repli"] = self.repli
        if self.impossible:
            fait["impossible"] = self.impossible
        return fait


def arbitrer(propositions: list[Proposition], *,
             defaut_runtime: str = "hermes-agent",
             defaut_modele: str = "",
             cloud_joignable: bool = False) -> Decision:
    """Une seule décision sort d'ici, quel qu'ait été le nombre d'avis.

    Les propositions sont données **dans l'ordre de précédence** : la
    première qui propose quelque chose l'emporte. L'appelant déclare donc
    l'ordre, une fois, à un endroit ; il ne se déduit plus de la position
    des lignes dans une fonction de cent lignes.

    `cloud_joignable` est un **fait mesuré** passé par l'appelant, pas une
    décision prise ici : ce module ne sait pas interroger un fournisseur,
    et il ne doit pas l'apprendre — ce serait la seconde autorité de
    sécurité que le RAL ne doit jamais devenir.
    """
    propositions = list(propositions)

    runtime, source_runtime = defaut_runtime, "défaut de l'exécuteur"
    for proposition in propositions:
        if proposition.propose_un_runtime:
            runtime = _propre(proposition.runtime)
            source_runtime = proposition.source
            break

    modele, source_modele = defaut_modele, "défaut de l'exécuteur"
    for proposition in propositions:
        if proposition.propose_un_modele:
            modele = _propre(proposition.modele)
            source_modele = proposition.source
            break

    # La seule dérogation : une montée vers le cloud, demandée par une
    # source qui en a le droit, et seulement si un fournisseur répond.
    repli, impossible = "", ""
    monte = next((p for p in propositions
                  if p.peut_monter and _propre(p.runtime) == MONTEE_AUTORISEE),
                 None)
    if monte is not None and runtime != MONTEE_AUTORISEE:
        if cloud_joignable:
            runtime, source_runtime = MONTEE_AUTORISEE, monte.source
        else:
            # Une **recommandation** défaite : elle n'engageait personne, et
            # le repli local était déjà la politique de `_make_cloud_chat`
            # — « cloud entièrement injoignable, quoi que recommande
            # AdaptiveRouter ». Autorisé, donc, mais jamais silencieux.
            repli = (f"{MONTEE_AUTORISEE} demandé par {monte.source} mais "
                     f"injoignable — exécuté sur {runtime}")

    if runtime == MONTEE_AUTORISEE and not cloud_joignable:
        # HOS-244 : une **assignation** défaite, c'est autre chose. La
        # version précédente la remplaçait par le runtime par défaut, ce
        # que sa propre documentation interdisait deux paragraphes plus
        # haut : « le décideur ne peut pas faire redescendre une
        # assignation explicite ». Le code contredisait le contrat.
        #
        # Rien dans ce dépôt n'autorise à défaire une assignation. Ce qui
        # y est écrit, en revanche, c'est `RuntimeUnavailableError` —
        # « the inference layer is down », retryable, jamais la faute de
        # la tâche — que `MissionExecutor` classe déjà en `FOURNISSEUR` et
        # traite avec le remède `changer_de_fournisseur`. L'échec honnête
        # est donc la politique **existante**, pas une politique nouvelle.
        impossible = (f"runtime {runtime!r} was explicitly assigned by "
                      f"{source_runtime} but is unavailable: no cloud "
                      f"provider is configured")

    return Decision(runtime=runtime, modele=modele,
                    source_runtime=source_runtime, source_modele=source_modele,
                    repli=repli, impossible=impossible,
                    propositions=tuple(propositions))


__all__ = ["Decision", "MONTEE_AUTORISEE", "NON_CHOISI", "Proposition",
           "arbitrer"]
