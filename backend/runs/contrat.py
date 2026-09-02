"""Ce qu'une mission s'engage à faire, et comment on le vérifiera (HOS-221).

## Le manque

Une mission part aujourd'hui d'une consigne en prose. À l'arrivée, on
sait qu'elle a « réussi » — ce qui ne veut rien dire tant que personne
n'a écrit ce que « réussi » recouvrait. La nuit du 29 au 30 août l'a
montré en production : trois plans rejetés, un rapport qui disait
`success: true` sur quatre secondes d'image, et aucune façon de répondre
à « qu'est-ce qui devait être vrai à la fin ? ».

Un contrat écrit **avant** rend la question vérifiable.

## Le modèle d'états, repris d'Agent OS

`src/lib/contract.ts` porte quatre états de critère et trois de vérificateur,
avec un commentaire qui vaut la règle entière :

    GateResult = "passed" | "failed" | "unavailable"
    // ← TRI-STATE, never conflate unavailable with passed

C'est la correction du défaut le plus fréquent de ce dépôt. Le
2026-08-30, `img07` était `indeterminé` — le relecteur n'avait pas pu
conclure — et cet état n'avait nulle part où aller dans une vérification
qui rend `bool`. Il s'est rangé à côté des plans jugés.

**Ce qui est repris** : les quatre états, les trois verdicts, et le fait
que ce soit gardé comme un invariant de sécurité et non comme une
commodité.

**Ce qui change** : leurs critères s'écrivent en EARS, une syntaxe
d'exigences anglophone. Les missions de Hermes viennent de l'agent, pas
d'un formulaire. Un critère est ici un **texte** plus le **nom du
vérificateur** qui doit le trancher — ce qui rend `UNVERIFIABLE`
actionnable : on sait quel vérificateur a manqué.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class Genre(str, Enum):
    """Ce qu'un critère exprime."""

    ACCEPTATION = "acceptation"
    #: Ce que la mission ne doit **pas** faire. Un non-objectif violé est
    #: plus grave qu'un objectif non atteint : le premier est un dégât,
    #: le second un travail inachevé.
    NON_OBJECTIF = "non_objectif"
    CONTRAINTE = "contrainte"


class EtatCritere(str, Enum):
    """Où en est un critère. Quatre états, pas deux.

    `INVERIFIABLE` et `NON_ATTEINT` disent des choses opposées : le
    premier est une lacune de mesure, le second un constat. Les confondre
    fait passer une ignorance pour un échec — ou pire, pour un succès.
    """

    NON_ATTEINT = "non_atteint"
    ATTEINT = "atteint"
    INVERIFIABLE = "inverifiable"
    #: Réservé aux non-objectifs : la mission a fait ce qu'elle s'était
    #: interdit.
    VIOLE = "viole"


class Verdict(str, Enum):
    """Ce qu'un vérificateur a répondu.

    `INDISPONIBLE` n'est **jamais** `REUSSI`. C'est la règle que le
    commentaire d'Agent OS met en capitales, et celle que ce dépôt a
    enfreinte le 2026-08-30.
    """

    REUSSI = "reussi"
    ECHOUE = "echoue"
    INDISPONIBLE = "indisponible"


class ContratInvalide(ValueError):
    """Un contrat qu'on ne pourrait pas vérifier n'est pas un contrat."""


@dataclass
class Critere:
    texte: str
    genre: Genre = Genre.ACCEPTATION
    #: Qui doit trancher. Sans lui, `INVERIFIABLE` ne dit pas *quoi*
    #: manque — et un rapport qui ne dit pas ce qui manque ne fait pas
    #: agir.
    verificateur: str = ""
    etat: EtatCritere = EtatCritere.NON_ATTEINT
    identifiant: str = field(default_factory=lambda: uuid4().hex)

    @property
    def tenu(self) -> bool:
        if self.genre is Genre.NON_OBJECTIF:
            return self.etat is not EtatCritere.VIOLE
        return self.etat is EtatCritere.ATTEINT

    def to_dict(self) -> dict[str, Any]:
        return {"identifiant": self.identifiant, "texte": self.texte,
                "genre": self.genre.value, "verificateur": self.verificateur,
                "etat": self.etat.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Critere":
        return cls(texte=d["texte"], genre=Genre(d.get("genre", "acceptation")),
                   verificateur=d.get("verificateur", ""),
                   etat=EtatCritere(d.get("etat", "non_atteint")),
                   identifiant=d.get("identifiant") or uuid4().hex)


@dataclass
class Contrat:
    """Ce qu'une mission s'engage à faire, avant de commencer."""

    objectif: str = ""
    criteres: list[Critere] = field(default_factory=list)
    ressources_autorisees: list[str] = field(default_factory=list)
    conditions_d_arret: list[str] = field(default_factory=list)
    #: Plafonds : durée, coût, tentatives. Un contrat sans limite se
    #: découvre en regardant la facture.
    budget: dict[str, Any] = field(default_factory=dict)
    niveau_de_risque: str = "moyen"

    # ── Validation ───────────────────────────────────────────────────

    def valider(self) -> None:
        """Refuser un contrat qu'on ne saurait pas vérifier.

        Un contrat sans critère d'acceptation passerait toujours : rien
        ne pourrait le contredire. C'est le `success: true` au-dessus de
        rien, écrit à l'avance.
        """
        if not self.objectif.strip():
            raise ContratInvalide("un contrat sans objectif n'engage à rien")

        acceptation = [c for c in self.criteres if c.genre is Genre.ACCEPTATION]
        if not acceptation:
            raise ContratInvalide(
                "aucun critère d'acceptation : ce contrat serait tenu quoi "
                "qu'il arrive, puisque rien ne pourrait le contredire")

        sans_verificateur = [c.texte for c in acceptation if not c.verificateur]
        if sans_verificateur:
            raise ContratInvalide(
                "critère(s) sans vérificateur nommé : "
                + " | ".join(sans_verificateur[:3])
                + " — sans lui, « invérifiable » ne dirait pas ce qui manque")

    # ── Lecture ──────────────────────────────────────────────────────

    @property
    def tenu(self) -> bool:
        """Tous les critères sont-ils tenus ?

        **Conjonctif, et un `INVERIFIABLE` suffit à dire non.** On ne
        peut pas déclarer tenu ce qu'on n'a pas su mesurer — c'est le
        point exact où ce dépôt s'est trompé le 2026-08-30.
        """
        return bool(self.criteres) and all(c.tenu for c in self.criteres)

    @property
    def inverifiables(self) -> list[Critere]:
        return [c for c in self.criteres
                if c.etat is EtatCritere.INVERIFIABLE]

    @property
    def violes(self) -> list[Critere]:
        return [c for c in self.criteres if c.etat is EtatCritere.VIOLE]

    def resume(self) -> str:
        if not self.criteres:
            return "contrat sans critère"
        tenus = sum(1 for c in self.criteres if c.tenu)
        texte = f"{tenus}/{len(self.criteres)} critère(s) tenu(s)"
        if self.violes:
            texte += f" — {len(self.violes)} non-objectif(s) VIOLÉ(s)"
        if self.inverifiables:
            texte += (f" — {len(self.inverifiables)} invérifiable(s), "
                      "ce qui n'est pas un succès")
        return texte

    # ── Vérification ─────────────────────────────────────────────────

    def enregistrer(self, identifiant: str, verdict: Verdict) -> Critere:
        """Poser le verdict d'un vérificateur sur un critère.

        La traduction verdict → état est la seule chose que ce module
        décide, et elle tient en trois lignes qu'il faut lire avec
        attention : `INDISPONIBLE` ne devient jamais `ATTEINT`.
        """
        critere = next((c for c in self.criteres if c.identifiant == identifiant),
                       None)
        if critere is None:
            raise KeyError(f"aucun critère {identifiant!r} dans ce contrat")

        if verdict is Verdict.INDISPONIBLE:
            critere.etat = EtatCritere.INVERIFIABLE
        elif critere.genre is Genre.NON_OBJECTIF:
            # Sur un non-objectif, le sens s'inverse : le vérificateur
            # cherche si la chose interdite s'est produite.
            critere.etat = (EtatCritere.VIOLE if verdict is Verdict.REUSSI
                            else EtatCritere.ATTEINT)
        else:
            critere.etat = (EtatCritere.ATTEINT if verdict is Verdict.REUSSI
                            else EtatCritere.NON_ATTEINT)
        return critere

    # ── Sérialisation ────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "objectif": self.objectif,
            "criteres": [c.to_dict() for c in self.criteres],
            "ressources_autorisees": list(self.ressources_autorisees),
            "conditions_d_arret": list(self.conditions_d_arret),
            "budget": dict(self.budget),
            "niveau_de_risque": self.niveau_de_risque,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Contrat":
        return cls(
            objectif=d.get("objectif", ""),
            criteres=[Critere.from_dict(c) for c in d.get("criteres") or []],
            ressources_autorisees=list(d.get("ressources_autorisees") or []),
            conditions_d_arret=list(d.get("conditions_d_arret") or []),
            budget=dict(d.get("budget") or {}),
            niveau_de_risque=d.get("niveau_de_risque", "moyen"),
        )

    @classmethod
    def from_json(cls, texte: str) -> "Contrat":
        return cls.from_dict(json.loads(texte))


__all__ = ["Contrat", "ContratInvalide", "Critere", "EtatCritere", "Genre",
           "Verdict"]
