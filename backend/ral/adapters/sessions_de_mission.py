"""Une session d'agent par mission, pas une par tâche (HOS-138).

`hermes_agent_cli.py` ouvre et jette un processus **à chaque appel**. Une
mission de vingt tâches, c'est vingt agents qui ne se sont jamais rencontrés.
Ce module tient une session ACP ouverte pour toute la durée d'une mission, et
c'est ce qui rend enfin atteignables les fonctions que l'agent possède déjà :
compression de contexte, revue de fond après chaque tour, curator, mémoire.

## Ce que ce module ne fait pas

Il ne raisonne pas, ne choisit pas d'outils, ne décompose rien. Il tient une
porte ouverte et note qui est passé. Tout ce qui ressemblerait à une seconde
boucle agentique appartient à Hermes Agent — c'est la règle qui prime, et
elle a déjà été violée une fois (voir
`backend/tests/test_hermes_agent_is_the_brain.py`).

## Le contexte n'est pas envoyé deux fois

Le mode jetable reconstruit tout l'historique à chaque appel, parce qu'il
parle à un processus amnésique. Ici l'agent tient son propre historique :
lui renvoyer l'historique complet le compterait deux fois et gaspillerait la
fenêtre qu'on cherche justement à ménager. Le premier tour porte donc le
contexte de mission, les suivants ne portent que ce qui est nouveau.

Mesuré le 2026-08-21 : code mémorisé au tour 1 restitué au tour 3, fichier
écrit et relu **sur le disque**. Sur huit tours, l'agent déclare 22,3 % de
sa fenêtre consommée — une mission longue a donc de la marge, et la
compression prend le relais au-delà de 75 %.

## Pourquoi un plafond

Chaque session est un processus Python complet — 56 plugins découverts au
démarrage — et toutes tapent le même Ollama, sur 16 Go de VRAM. Sans
plafond, une rafale de missions ouvrirait autant d'agents que de missions.
Le plafond ne dégrade rien : au-delà, l'appelant retombe sur le mode
jetable, en le disant.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.ral.adapters.hermes_agent_acp import (
    DELAI_TOUR_S,
    HermesAgentACP,
    Tour,
)

logger = logging.getLogger("hermes_os.ral.sessions")

#: Au-delà, on retombe sur le mode jetable plutôt que d'ouvrir un processus
#: de plus. Quatre agents résidents tiennent en RAM à côté d'Ollama ; le
#: chiffre est un garde-fou, pas une mesure.
PLAFOND_SESSIONS = 4

#: Une mission qui ne s'est pas manifestée depuis une demi-heure a
#: probablement échoué sans le dire. Sans cette purge, son processus agent
#: survivrait au serveur qui l'a lancé.
TTL_INACTIVITE_S = 1800.0


@dataclass
class _Entree:
    client: HermesAgentACP
    workspace: str
    tours: int = 0
    derniere_activite: float = 0.0


class SessionsDeMission:
    """Le registre. Une clé de mission, une session vivante."""

    def __init__(self, *, plafond: int = PLAFOND_SESSIONS,
                 ttl_s: float = TTL_INACTIVITE_S,
                 fabrique: Any = None, horloge: Any = None) -> None:
        self._entrees: dict[str, _Entree] = {}
        self._plafond = plafond
        self._ttl = ttl_s
        # Injectable pour que les tests n'aient pas à lancer un agent réel.
        self._fabrique = fabrique or (lambda: HermesAgentACP())
        # Injectable aussi : `time.monotonic` a une résolution d'environ
        # 15 ms sous Windows. Un test qui dormait 10 ms pour provoquer une
        # purge passait seul et échouait dans la suite complète — il
        # mesurait le tick du système, pas la règle d'expiration.
        self._horloge = horloge or time.monotonic
        self._verrou = asyncio.Lock()

    # -- interrogation ------------------------------------------------

    def sessions_ouvertes(self) -> int:
        return len(self._entrees)

    def connait(self, cle: str) -> bool:
        return cle in self._entrees

    def tours_de(self, cle: str) -> int:
        entree = self._entrees.get(cle)
        return entree.tours if entree else 0

    # -- cycle de vie -------------------------------------------------

    async def _purger(self) -> None:
        """Ferme ce qui ne s'est pas manifesté depuis `ttl_s`."""
        maintenant = self._horloge()
        expirees = [cle for cle, e in self._entrees.items()
                    if maintenant - e.derniere_activite > self._ttl]
        for cle in expirees:
            logger.info("session de mission %s purgée (inactive)", cle)
            await self._fermer_sans_verrou(cle)

    async def _fermer_sans_verrou(self, cle: str) -> None:
        entree = self._entrees.pop(cle, None)
        if entree is None:
            return
        try:
            await entree.client.fermer()
        except Exception:  # noqa: BLE001 - une fermeture ne casse rien
            logger.debug("fermeture de la session %s", cle, exc_info=True)

    async def fermer(self, cle: str) -> None:
        """À appeler quand une mission se termine, quelle qu'en soit l'issue."""
        async with self._verrou:
            await self._fermer_sans_verrou(cle)

    async def fermer_tout(self) -> None:
        async with self._verrou:
            for cle in list(self._entrees):
                await self._fermer_sans_verrou(cle)

    # -- usage --------------------------------------------------------

    async def disponible_pour(self, cle: str) -> tuple[bool, str]:
        """Peut-on servir cette mission par le harnais, et sinon pourquoi.

        Rendu comme un couple pour que l'appelant **dise** pourquoi il
        retombe sur le mode jetable. Un repli silencieux est ce qui a
        permis, des mois durant, à des missions de contourner l'agent sans
        que rien ne l'indique.
        """
        if not cle:
            return False, "aucun identifiant de mission : rien à faire durer"
        async with self._verrou:
            await self._purger()
            if cle in self._entrees:
                return True, ""
            if len(self._entrees) >= self._plafond:
                return False, (f"{len(self._entrees)} sessions déjà ouvertes "
                               f"(plafond {self._plafond})")
        ok, raison = self._fabrique().disponible()
        return ok, raison

    async def tour(self, cle: str, workspace: str, texte: str, *,
                   amorce: str = "", modele: str = "",
                   delai: float = DELAI_TOUR_S) -> Tour:
        """Un tour dans la session de cette mission, ouverte au besoin.

        `amorce` n'est envoyée qu'au **premier** tour : c'est le contexte de
        mission, que l'agent conserve ensuite lui-même.

        `modele` est appliqué à la session quand il change. Sans cela, le
        routeur de Hermes OS choisirait un modèle par tâche que personne
        n'écouterait — et une session ouverte au premier modèle servirait
        toute la mission. Le contexte survit à la bascule : côté agent,
        `set_session_model` reconstruit l'agent sans toucher à l'historique.
        """
        async with self._verrou:
            await self._purger()
            entree = self._entrees.get(cle)
            if entree is not None and entree.workspace != workspace:
                # Un workspace qui change en cours de mission n'est pas une
                # continuité : la session porterait des chemins qui ne
                # veulent plus rien dire.
                logger.info("session %s rouverte : le workspace a changé", cle)
                await self._fermer_sans_verrou(cle)
                entree = None
            if entree is None:
                if len(self._entrees) >= self._plafond:
                    raise RuntimeError(
                        f"plafond de {self._plafond} sessions atteint")
                client = self._fabrique()
                await client.ouvrir(workspace)
                entree = _Entree(client=client, workspace=workspace,
                                 derniere_activite=self._horloge())
                self._entrees[cle] = entree
                logger.info("session de mission %s ouverte sur %s", cle, workspace)

        if modele:
            # Hors du verrou du registre : la bascule est un aller-retour
            # avec l'agent, et tenir le verrou pendant ce temps bloquerait
            # toutes les autres missions.
            await entree.client.choisir_modele(modele)

        premier = entree.tours == 0
        message = f"{amorce}\n\n{texte}" if (premier and amorce) else texte
        resultat = await entree.client.tour(message, delai=delai)
        entree.tours += 1
        entree.derniere_activite = self._horloge()
        return resultat


#: Un registre pour le processus. Les sessions sont des processus vivants :
#: en avoir deux jeux qui s'ignorent doublerait la consommation sans que
#: personne ne le voie.
_registre: Optional[SessionsDeMission] = None


def registre() -> SessionsDeMission:
    global _registre
    if _registre is None:
        _registre = SessionsDeMission()
    return _registre
