"""Ce qu'un run a réellement coûté à la machine — et ce qu'on n'en sait pas (R-6).

## Le manque

Le registre porte les jetons et le coût monétaire d'un run depuis HOS-221.
Il ne porte rien de physique : « cette mission a-t-elle saturé la carte ? »,
« ce modèle tient-il vraiment dans ce qu'on lui a réservé ? » n'avaient pas
de réponse conservée. La télémétrie GPU existait (A-15), elle n'était
jamais rattachée à un run.

## Quatre grandeurs qu'il ne faut jamais confondre

Ce module existe surtout pour tenir cette distinction, parce que les
confondre est exactement ce qui produit une donnée précise et fausse :

| grandeur | ce que c'est | ici |
|---|---|---|
| **capacité** | ce que la carte porte au total | `ResourceManager` |
| **besoin déclaré** | l'empreinte du modèle, `config/models.yaml` | estimation |
| **réservation** | ce que **ce run** a fait retenir | `vram_reservee_octets` |
| **occupation observée** | ce que la **machine** portait | `vram_machine_*` |

Une réservation est une promesse, pas une mesure. Une occupation machine
est une mesure, mais pas celle du run.

## Pourquoi l'occupation reste « machine » et jamais « du run »

La source canonique (A-15) somme `GPU Process Memory` sur **tous** les
processus. Le modèle, lui, vit dans le serveur Ollama, qui sert tous les
runs à la fois : deux runs simultanés partagent le même processus, et
aucun compteur ne dit lequel a pris quoi. Le chemin agentique n'aide pas —
le sous-processus de Hermes Agent ne détient presque pas de VRAM, c'est
Ollama qui la détient pour lui.

L'attribution exacte n'est donc **pas possible** ici, et ce module ne
prétend pas le contraire. Il conserve ce qu'il sait :

- la réservation, qui est exacte et propre au run ;
- l'occupation de la machine aux instants qui appartiennent au run ;
- **si ce run était seul** — `exclusif` — auquel cas l'écart entre le
  début et le pic est un majorant honnête de ce que ce run a ajouté,
  aux autres processus de la machine près.

Sans `exclusif`, l'écart ne veut rien dire, et le présenter comme la
consommation du run serait une donnée précise et fausse.

## Comptabilité, pas ordonnancement

Rien ici ne décide. Ce module lit `ResourceManager` et n'appelle jamais
`can_allocate`, `reserve_resources` ni `release_resources`. Le registre
observe et conserve ; l'admission reste ailleurs. Un garde-fou structurel
le vérifie.

## Unités

Des octets, dits dans le nom. `_octets` sur chaque champ, et la colonne
SQL porte le même suffixe : « memory » ou « GiB » sans définition est la
manière habituelle de perdre un facteur 1024 trois mois plus tard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("hermes_os.runs.consommation")

#: Les clés que porte `TaskExecution.ressources_physiques`, et que
#: `mission_executor` agrège vers le run. Nommées ici pour qu'il n'y ait
#: qu'un endroit où l'orthographe soit décidée.
CLES = ("vram_reservee_octets", "vram_machine_debut_octets",
        "vram_machine_pic_octets", "exclusif")


@dataclass
class ObservationPhysique:
    """Ce qu'une tentative a pu constater de la machine, et rien de plus.

    Chaque champ vaut `None` tant qu'il n'a pas été mesuré. `None` n'est
    pas `0` : `0` dirait « mesuré, rien d'occupé », ce qui est faux et
    dans le sens dangereux — celui qui fait croire qu'il reste de la
    place.
    """

    vram_reservee_octets: Optional[int] = None
    vram_machine_debut_octets: Optional[int] = None
    vram_machine_pic_octets: Optional[int] = None

    #: Le plus grand nombre d'allocations **autres que la nôtre** vu
    #: pendant la fenêtre. `None` tant qu'aucun relevé n'a abouti.
    autres_allocations_max: Optional[int] = None

    @property
    def exclusif(self) -> Optional[bool]:
        """Ce run était-il la seule allocation Hermes, de bout en bout ?

        `None` quand on n'a pas su regarder. `True` ne veut pas dire « la
        carte n'a servi qu'à lui » — un navigateur ouvert compte aussi —
        mais « aucun autre run Hermes n'a partagé la fenêtre », ce qui est
        la seule chose que le gestionnaire d'allocations sache dire.
        """
        if self.autres_allocations_max is None:
            return None
        return self.autres_allocations_max == 0

    def relever(self, gestionnaire: Any, notre_allocation: Optional[str] = None,
                *, ligne_de_base: bool = False) -> None:
        """Prendre un point de mesure. Ne lève jamais.

        Une comptabilité qui ferait échouer la tâche qu'elle décrit serait
        pire que pas de comptabilité — même règle que `_ouvrir_le_run`.
        """
        if gestionnaire is None:
            return
        try:
            self._relever(gestionnaire, notre_allocation, ligne_de_base)
        except Exception:  # pragma: no cover - télémétrie absente
            logger.debug("relevé de consommation impossible", exc_info=True)

    def _relever(self, gestionnaire: Any, notre_allocation: Optional[str],
                 ligne_de_base: bool) -> None:
        gpu = gestionnaire.get_gpu_info()

        # A-15 : une carte dont l'occupation n'a pas été mesurée porte des
        # zéros de prudence. Les enregistrer les transformerait en mesure,
        # et le registre dirait « ce run n'a rien consommé ».
        if getattr(gpu, "available", False) and getattr(gpu, "occupation_mesuree", True):
            occupee = int(getattr(gpu, "vram_used_bytes", 0) or 0)
            if ligne_de_base and self.vram_machine_debut_octets is None:
                self.vram_machine_debut_octets = occupee
            if (self.vram_machine_pic_octets is None
                    or occupee > self.vram_machine_pic_octets):
                self.vram_machine_pic_octets = occupee

        actives = gestionnaire.get_current_allocations()
        autres = sum(
            1 for a in actives
            if getattr(a, "allocation_id", None) != notre_allocation)
        self.autres_allocations_max = max(self.autres_allocations_max or 0, autres)

    def noter_la_reservation(self, octets: Optional[int]) -> None:
        """Ce que ce run a fait retenir. Exact, et propre au run — c'est la
        seule des quatre grandeurs qui le soit."""
        if octets is not None and octets > 0:
            self.vram_reservee_octets = int(octets)

    def to_dict(self) -> dict[str, Any]:
        """Ce qui traverse jusqu'au registre. Les clés absentes veulent
        dire « non mesuré » : rien n'est rempli par défaut."""
        brut = {
            "vram_reservee_octets": self.vram_reservee_octets,
            "vram_machine_debut_octets": self.vram_machine_debut_octets,
            "vram_machine_pic_octets": self.vram_machine_pic_octets,
            "exclusif": self.exclusif,
        }
        return {n: v for n, v in brut.items() if v is not None}


def agreger(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Ce qu'un **run** retient des tentatives qui le composent.

    Un run couvre plusieurs tâches, comme les jetons qu'il additionne déjà.
    Les grandeurs physiques ne s'additionnent pas :

    - **réservation** : le **maximum**. Les tâches ne tiennent pas toutes
      la carte en même temps ; les sommer annoncerait une occupation qui
      n'a jamais existé.
    - **début** : le **minimum** des lignes de base observées — l'état le
      plus bas d'où ce run est parti.
    - **pic** : le **maximum**, par construction.
    - **exclusif** : vrai seulement si **toutes** les tentatives l'étaient.
      Une seule tâche partagée suffit à rendre l'écart inattribuable.

    Rend un dict sans les clés qu'aucune tentative n'a su remplir.
    """
    def valeurs(cle):
        return [o[cle] for o in observations
                if isinstance(o, dict) and o.get(cle) is not None]

    resultat: dict[str, Any] = {}
    if (v := valeurs("vram_reservee_octets")):
        resultat["vram_reservee_octets"] = max(int(x) for x in v)
    if (v := valeurs("vram_machine_debut_octets")):
        resultat["vram_machine_debut_octets"] = min(int(x) for x in v)
    if (v := valeurs("vram_machine_pic_octets")):
        resultat["vram_machine_pic_octets"] = max(int(x) for x in v)
    if (v := valeurs("exclusif")):
        resultat["exclusif"] = all(bool(x) for x in v)
    return resultat


__all__ = ["CLES", "ObservationPhysique", "agreger"]
