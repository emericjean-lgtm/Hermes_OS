"""D'où vient un souvenir, et jusqu'où on le croit (HOS-216).

## Ce n'est pas une question de qualité de données

C'est la défense contre l'**injection de prompt**. Un agent qui lit une
page web, un dépôt cloné ou un document fourni peut y trouver un texte
rédigé pour lui : « ignore tes instructions », « le mot de passe est… »,
« ce dépôt autorise l'accès réseau ». Si ce texte entre en mémoire et
qu'il en ressort ensuite comme un **fait**, l'attaque n'a plus besoin de
se rejouer : elle est installée.

Agent OS garde une seule propriété sur ce point, et ses tests
`m8-prompt-injection` / `m8-memory-poisoning` ne testent qu'elle :

> le contenu en quarantaine n'entre jamais dans le contexte résident ni
> dans une recherche, sauf demande explicite — et l'origine non humaine
> est mise en quarantaine **quel que soit son contenu**.

Le dernier point est le plus important, et le moins intuitif : on ne
juge pas le texte. Un filtre qui cherche des formulations suspectes est
un filtre qu'on contourne en changeant de formulation. **On juge la
provenance.**

## Ce que Hermes fait aujourd'hui, et pourquoi c'est un vecteur

`MemoryManager.record_episode()`, `store_concept()`, `index_document()`
acceptent tout et rendent tout. Une mémoire produite par un agent devient
un fait immédiatement, et `search()` la sert au tour suivant.

## Les états

`humain` est la seule origine de confiance par défaut. Tout le reste —
agent, web, dépôt, outil, document importé — arrive en quarantaine et n'en
sort que par une promotion explicite, qui laisse une trace.

Deux valeurs de confiance suffisaient à Agent OS, qui a un seul tier de
mémoire. Hermes en a six et un graphe de connaissance : on garde donc
aussi **quand** la vérification a eu lieu et **par quoi**, sans quoi une
promotion d'il y a six mois vaut autant qu'une d'hier.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, TypeVar


class Origine(str, Enum):
    """D'où vient le souvenir. C'est ça qu'on juge, pas son contenu.

    La distinction qui compte est **qui a écrit le texte**, pas qui a
    appelé la fonction.
    """

    HUMAIN = "humain"
    #: Hermes OS décrivant sa propre exécution : « la mission 42 a pris
    #: 1 365 s, tuile 128, retenue ». Ce texte n'est pas lu quelque part,
    #: il est **observé** — donc pas un vecteur d'injection.
    #:
    #: Agent OS n'a pas besoin de cette distinction : sa mémoire est un
    #: carnet de notes. Celle de Hermes est aussi un **registre
    #: d'exploitation**, et le quarantiner en bloc arrêterait la
    #: réutilisation d'expérience — `find_similar_missions`,
    #: `learn_from_mission` — sans rien protéger de plus.
    SYSTEME = "systeme"
    #: Le modèle écrivant depuis ce qu'il a lu. Le texte peut citer une
    #: page, un dépôt, un document — c'est là qu'une injection voyage.
    AGENT = "agent"
    WEB = "web"
    DEPOT = "depot"
    OUTIL = "outil"
    DOCUMENT = "document"
    INCONNUE = "inconnue"


class Confiance(str, Enum):
    QUARANTAINE = "quarantaine"
    FIABLE = "fiable"


#: Les origines qui entrent directement en confiance. Une liste plutôt
#: qu'une comparaison en dur : la règle reste au même endroit, et son
#: élargissement se voit dans un diff.
#:
#: `SYSTEME` y figure et `AGENT` non, sur un seul critère : **est-ce que
#: le texte a été lu quelque part ?** Un relevé d'exécution est observé
#: par Hermes ; une note écrite par le modèle peut citer ce qu'il vient
#: de lire dans un dépôt.
ORIGINES_DE_CONFIANCE = frozenset({Origine.HUMAIN, Origine.SYSTEME})


class PromotionRefusee(RuntimeError):
    """Une promotion sans acteur nommé n'est pas une promotion."""


@dataclass
class Provenance:
    """La provenance d'un souvenir, et ce qu'on en a vérifié.

    Immuable dans les faits : `promouvoir()` rend une nouvelle instance
    plutôt que de muter celle-ci, pour qu'un objet déjà distribué à un
    appelant ne change pas de confiance dans son dos.
    """

    origine: Origine = Origine.INCONNUE
    confiance: Confiance = Confiance.QUARANTAINE
    source: str = ""
    promu_par: str | None = None
    verifie_le: datetime | None = None

    @classmethod
    def depuis(cls, origine: Origine | str, source: str = "") -> "Provenance":
        """La règle, appliquée à l'écriture.

        Une origine non humaine est mise en quarantaine **quoi qu'il
        arrive** — l'appelant ne peut pas demander la confiance, il ne
        peut que déclarer d'où ça vient.
        """
        o = Origine(origine) if not isinstance(origine, Origine) else origine
        fiable = o in ORIGINES_DE_CONFIANCE
        return cls(
            origine=o,
            confiance=Confiance.FIABLE if fiable else Confiance.QUARANTAINE,
            source=source,
            promu_par=o.value if fiable else None,
            verifie_le=datetime.now(timezone.utc) if fiable else None,
        )

    @property
    def en_quarantaine(self) -> bool:
        return self.confiance is Confiance.QUARANTAINE

    def promouvoir(self, par: str) -> "Provenance":
        """Sortir de quarantaine, en nommant qui l'a décidé.

        Sans acteur, la promotion est refusée : une trace anonyme ne
        permet pas de revenir sur une décision, et c'est exactement ce
        qu'on veut pouvoir faire après une injection réussie.
        """
        if not par or not par.strip():
            raise PromotionRefusee(
                "une promotion doit nommer qui l'a décidée — sans acteur, "
                "on ne peut plus revenir sur la décision")
        return Provenance(
            origine=self.origine,
            confiance=Confiance.FIABLE,
            source=self.source,
            promu_par=par.strip(),
            verifie_le=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "origine": self.origine.value,
            "confiance": self.confiance.value,
            "source": self.source,
            "promu_par": self.promu_par,
            "verifie_le": self.verifie_le.isoformat() if self.verifie_le else None,
        }


T = TypeVar("T")


def provenance_de(objet: Any) -> Provenance:
    """La provenance d'un souvenir, ou la plus prudente si elle manque.

    Un objet sans provenance est traité comme **inconnu**, donc en
    quarantaine. C'est le sens de lecture qui protège : un souvenir écrit
    avant ce module, ou par un chemin qu'on aurait oublié d'instrumenter,
    ne devient pas fiable par défaut d'information.
    """
    p = getattr(objet, "provenance", None)
    if isinstance(p, Provenance):
        return p
    meta = getattr(objet, "metadata", None)
    if isinstance(meta, dict) and isinstance(meta.get("provenance"), Provenance):
        return meta["provenance"]
    return Provenance()


def filtrer(resultats: Iterable[T], *, inclure_quarantaine: bool = False
            ) -> list[T]:
    """Retirer la quarantaine, sauf demande explicite.

    Le drapeau est nommé et par défaut à faux : un appelant qui veut du
    contenu en quarantaine doit le dire, et le dire se lit à la relecture
    du code. C'est la propriété que gardent les tests d'injection.
    """
    if inclure_quarantaine:
        return list(resultats)
    return [r for r in resultats if not provenance_de(r).en_quarantaine]


__all__ = ["Confiance", "ORIGINES_DE_CONFIANCE", "Origine", "PromotionRefusee",
           "Provenance", "filtrer", "provenance_de"]
