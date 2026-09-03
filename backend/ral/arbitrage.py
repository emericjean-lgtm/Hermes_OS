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
fournisseur cloud est réellement joignable. Il ne peut pas la faire
redescendre : défaire une assignation explicite serait exactement la
seconde autorité que ce module supprime.
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

    # La seule dérogation : une montée vers le cloud, et seulement si un
    # fournisseur répond vraiment. Cherchée sur **toutes** les
    # propositions et non sur la gagnante : un décideur secondaire peut
    # légitimement demander le cloud sans avoir emporté le runtime.
    repli = ""
    monte = next((p for p in propositions
                  if _propre(p.runtime) == MONTEE_AUTORISEE), None)
    if monte is not None and runtime != MONTEE_AUTORISEE:
        if cloud_joignable:
            runtime, source_runtime = MONTEE_AUTORISEE, monte.source
        else:
            # Autorisé, mais jamais silencieux : sans clé — le cas par
            # défaut de cette installation — l'opérateur croyait avoir
            # payé du cloud.
            repli = (f"{MONTEE_AUTORISEE} demandé par {monte.source} mais "
                     f"injoignable — exécuté sur {runtime}")
    elif monte is not None and runtime == MONTEE_AUTORISEE and not cloud_joignable:
        runtime, source_runtime = defaut_runtime, "repli, cloud injoignable"
        repli = (f"{MONTEE_AUTORISEE} assigné mais injoignable — exécuté "
                 f"sur {runtime}")

    return Decision(runtime=runtime, modele=modele,
                    source_runtime=source_runtime, source_modele=source_modele,
                    repli=repli, propositions=tuple(propositions))


__all__ = ["Decision", "MONTEE_AUTORISEE", "NON_CHOISI", "Proposition",
           "arbitrer"]
