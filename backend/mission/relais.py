"""Ce qui doit survivre au changement de modèle (HOS-229).

## Deux manques mesurés

**Le contrat n'arrive jamais au modèle.** HOS-221 a créé `Contrat` — ce
qui devait être vrai à la fin — et une colonne `contrat` dans le
registre des runs. Vérifié : rien n'y écrit, rien ne l'y relit, et
`backend.runs.contrat` n'est importé que par `verification.py`, pour son
énumération `Verdict`. Le modèle chargé de satisfaire des critères ne les
voit donc pas.

**Aucune preuve de vérification n'atteint un prompt.** `retry_policy`
construit bien un mémoire de reprise à partir du verdict, mais au niveau
de la **mission** et seulement sur contradiction. Une tâche qui vient
d'être vérifiée ne sait pas ce que la vérification a dit.

## Pourquoi un relais, et pas une session

`_upstream_results_for` porte déjà les résultats amont, et son
commentaire dit la règle : *« carried as plain text on purpose: it has to
survive the model being swapped between two tasks, which anything held as
KV cache or a provider session would not »*.

Cette règle est exactement celle dont on a besoin ici, appliquée aux
**phases** plutôt qu'aux tâches. Sur 16 Gio, Hermes ne fait pas tourner
quatre modèles à la fois ; il enchaîne :

    planificateur cloud → exécutant local → vérificateur cloud → réparateur local

Entre deux flèches, le modèle change, le fournisseur peut changer, et le
processus distant n'a **aucune mémoire** du tour précédent. Ce qui n'est
pas écrit dans le relais n'existe pas au tour suivant.

## Ce que chaque phase reçoit — et ne reçoit pas

Un relais qui donnerait tout à tout le monde serait un prompt géant, et
un prompt géant sur 16 Gio est une fenêtre qui se ferme. Chaque phase
reçoit ce dont elle a besoin :

- **planification** : l'objectif, le workspace, les outils. Pas les
  artefacts — il n'y en a pas encore.
- **exécution** : le contrat, les artefacts déjà produits, les résultats
  amont. Elle doit savoir ce qu'on attend d'elle.
- **vérification** : le contrat et les artefacts, **pas** le raisonnement
  de l'exécutant. Un vérificateur à qui l'on montre le raisonnement juge
  l'intention plutôt que le résultat — c'est exactement le défaut
  constaté le 2026-08-30, où le relecteur a accepté une image conforme au
  prompt et rejeté la bonne.
- **réparation** : le contrat, les preuves, et **ce qui a échoué**.

## La mémoire ne contourne pas la quarantaine

Le relais porte de la mémoire, et il la passe par le filtre de HOS-216.
Un souvenir en quarantaine — origine non humaine — n'entre pas dans un
prompt parce qu'il transite par un relais. C'était précisément le vecteur
que HOS-216 ferme : une injection installée en mémoire qui ressort comme
un fait au tour suivant.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from backend.runs.contrat import Contrat


class Phase(str, Enum):
    """Les quatre moments d'une boucle.

    Nommés ici, assemblés en HOS-230 : ce module porte le contexte, il ne
    conduit pas la boucle. Les deux dans le même fichier auraient fait
    dépendre le transport de l'ordonnancement.
    """

    PLANIFICATION = "planification"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    REPARATION = "reparation"


#: Le rôle de `config/models.yaml` que chaque phase préfère, et le
#: pourquoi. Les rôles existaient tous avant ce jalon ; ce qui manquait,
#: c'est que quelque chose les relie à une **phase** plutôt qu'à un type
#: de tâche.
#:
#: `double_check` est le cas qui le montre : il est configuré depuis
#: HOS-065C et **rien ne routait jamais une vérification vers lui**.
ROLE_PAR_PHASE: dict[Phase, str] = {
    # Planifier demande de la portée, pas de la vitesse.
    Phase.PLANIFICATION: "reasoning",
    Phase.EXECUTION: "code",
    # Un second regard, et surtout un **autre** modèle : un modèle qui
    # relit sa propre sortie confirme sa propre sortie.
    Phase.VERIFICATION: "double_check",
    Phase.REPARATION: "code",
}


@dataclass
class Artefact:
    """Quelque chose qui a été produit, et qui est sur le disque."""

    chemin: str
    phase: str = ""
    #: Ce que la vérification en a dit. Vide tant qu'elle n'a pas parlé —
    #: et jamais « bon » par défaut d'information (HOS-222).
    verdict: str = ""


@dataclass
class Preuve:
    """Ce qu'un vérificateur a constaté, avec de quoi le recouper."""

    source: str
    constat: str
    #: `reussi | echoue | indisponible`, le vocabulaire de HOS-221.
    verdict: str = "indisponible"


@dataclass
class Relais:
    """Ce qui traverse les phases, et rien d'autre.

    Sérialisable en JSON de bout en bout : il franchit une frontière de
    processus à chaque appel distant, et un objet qui ne se sérialise pas
    ne franchit rien.
    """

    mission: str = ""
    run: str = ""
    objectif: str = ""
    workspace: str = ""
    contrat: Contrat | None = None
    artefacts: list[Artefact] = field(default_factory=list)
    preuves: list[Preuve] = field(default_factory=list)
    #: Les décisions prises en chemin : approbations, verdicts de
    #: pare-feu, bascules de fournisseur. Une phase qui ignore qu'une
    #: approbation a été refusée reproposera la même action.
    decisions: list[str] = field(default_factory=list)
    #: Ce que les tâches amont ont produit — le texte que
    #: `_upstream_results_for` portait déjà.
    amont: str = ""
    outils: list[str] = field(default_factory=list)
    #: Des souvenirs **déjà filtrés**. Voir `depuis_la_memoire`.
    memoire: list[str] = field(default_factory=list)
    #: Ce qui a échoué au tour précédent, tel que la taxonomie l'a classé.
    echec: str = ""
    cause: str = ""

    # ── Alimentation ─────────────────────────────────────────────────

    def ajouter_artefact(self, chemin: str, phase: Phase | str = "",
                         verdict: str = "") -> None:
        phase = phase.value if isinstance(phase, Phase) else str(phase or "")
        self.artefacts.append(Artefact(chemin=chemin, phase=phase,
                                       verdict=verdict))

    def ajouter_preuve(self, source: str, constat: str,
                       verdict: str = "indisponible") -> None:
        self.preuves.append(Preuve(source=source, constat=constat,
                                   verdict=verdict))

    def depuis_la_memoire(self, resultats: Any, *,
                          inclure_quarantaine: bool = False) -> int:
        """Verser des souvenirs, **après** le filtre de quarantaine.

        Un relais qui contournerait `memory.confiance.filtrer` rouvrirait
        exactement le vecteur que HOS-216 ferme : une injection installée
        en mémoire qui ressort comme un fait au tour suivant, par un
        chemin que personne n'a pensé à instrumenter.

        Le drapeau existe et il est nommé, comme celui de `search()` : un
        appelant qui veut du contenu non vérifié doit le dire, et ça se
        lit à la relecture.
        """
        from backend.memory.confiance import filtrer

        retenus = filtrer(list(resultats or []),
                          inclure_quarantaine=inclure_quarantaine)
        for r in retenus:
            texte = getattr(r, "content", None) or getattr(r, "text", None) or str(r)
            self.memoire.append(str(texte))
        return len(retenus)

    # ── Ce que chaque phase reçoit ───────────────────────────────────

    def pour(self, phase: Phase) -> str:
        """Le contexte de cette phase, en texte.

        En texte et non en objet : il finit dans un prompt, et le
        fabriquer ici plutôt que chez chaque appelant garantit qu'une
        phase ne reçoit pas par accident ce qu'on avait décidé de ne pas
        lui donner.
        """
        blocs: list[str] = []

        if self.objectif:
            blocs.append(f"Objectif de la mission : {self.objectif}")

        if phase is not Phase.PLANIFICATION and self.contrat is not None:
            blocs.append(self._bloc_contrat())

        if phase is Phase.PLANIFICATION:
            if self.outils:
                blocs.append("Outils disponibles : " + ", ".join(self.outils))
        elif phase is Phase.EXECUTION:
            if self.amont:
                blocs.append("Déjà fait par les tâches dont celle-ci "
                             "dépend :\n" + self.amont)
            if self.outils:
                blocs.append("Outils disponibles : " + ", ".join(self.outils))
        elif phase is Phase.VERIFICATION:
            # Ni `amont`, ni le raisonnement de l'exécutant : un
            # vérificateur à qui l'on montre l'intention juge l'intention.
            # Le 2026-08-30, le relecteur a accepté l'image conforme au
            # prompt et rejeté la bonne.
            blocs.append(self._bloc_artefacts())
        elif phase is Phase.REPARATION:
            blocs.append(self._bloc_artefacts())
            if self.echec:
                ligne = f"Ce qui a échoué : {self.echec}"
                if self.cause:
                    ligne += f" (cause constatée : {self.cause})"
                blocs.append(ligne)

        if phase in (Phase.VERIFICATION, Phase.REPARATION) and self.preuves:
            blocs.append(self._bloc_preuves())

        if self.decisions:
            # Toutes les phases : une phase qui ignore qu'une approbation
            # a été refusée reproposera la même action.
            blocs.append("Décisions déjà prises :\n"
                         + "\n".join(f"- {d}" for d in self.decisions))

        if self.memoire:
            blocs.append("Souvenirs vérifiés :\n"
                         + "\n".join(f"- {m}" for m in self.memoire))

        return "\n\n".join(b for b in blocs if b)

    def _bloc_contrat(self) -> str:
        contrat = self.contrat
        assert contrat is not None
        lignes = ["Ce qui doit être vrai à la fin :"]
        for critere in contrat.criteres:
            marque = "interdit" if critere.genre.value == "non_objectif" else "requis"
            lignes.append(f"- [{marque}] {critere.texte}"
                          + (f" (vérifié par : {critere.verificateur})"
                             if critere.verificateur else ""))
        if contrat.conditions_d_arret:
            lignes.append("Conditions d'arrêt : "
                          + " ; ".join(contrat.conditions_d_arret))
        return "\n".join(lignes)

    def _bloc_artefacts(self) -> str:
        if not self.artefacts:
            return ("Aucun artefact produit. Ce n'est pas « rien à vérifier » : "
                    "c'est un constat à faire remonter.")
        lignes = ["Artefacts produits :"]
        for a in self.artefacts:
            ligne = f"- {a.chemin}"
            if a.phase:
                ligne += f" ({a.phase})"
            if a.verdict:
                ligne += f" — {a.verdict}"
            lignes.append(ligne)
        return "\n".join(lignes)

    def _bloc_preuves(self) -> str:
        lignes = ["Ce que la vérification a constaté :"]
        for p in self.preuves:
            lignes.append(f"- [{p.verdict}] {p.source} : {p.constat}")
        return "\n".join(lignes)

    # ── Franchir une frontière de processus ──────────────────────────

    def to_dict(self) -> dict[str, Any]:
        donnees = asdict(self)
        donnees["contrat"] = self.contrat.to_dict() if self.contrat else None
        return donnees

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, donnees: dict[str, Any]) -> "Relais":
        donnees = dict(donnees)
        contrat = donnees.pop("contrat", None)
        artefacts = [Artefact(**a) for a in donnees.pop("artefacts", []) or []]
        preuves = [Preuve(**p) for p in donnees.pop("preuves", []) or []]
        return cls(contrat=Contrat.from_dict(contrat) if contrat else None,
                   artefacts=artefacts, preuves=preuves, **donnees)

    @classmethod
    def from_json(cls, texte: str) -> "Relais":
        return cls.from_dict(json.loads(texte))


def role_pour(phase: Phase) -> str:
    """Le rôle de `config/models.yaml` que cette phase préfère.

    Rend le rôle, pas un modèle : quel modèle sert un rôle est décidé
    par la configuration et mesuré par le catalogue, et le figer ici
    ferait diverger deux sources.
    """
    return ROLE_PAR_PHASE.get(phase, "standard")


__all__ = ["Artefact", "Phase", "Preuve", "ROLE_PAR_PHASE", "Relais",
           "role_pour"]
