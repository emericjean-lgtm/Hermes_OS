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
#: de plus.
#:
#: Le chiffre valait 4 et était posé au jugé — le commentaire d'origine le
#: disait : « un garde-fou, pas une mesure ». Mesuré depuis, six sessions
#: ouvertes simultanément sur cette machine :
#:
#:     220 Mio par session (219,2 à 220,2 — remarquablement stable)
#:     1 318 Mio au total pour six
#:     latence d'un tour : 20,7 s pour les deux premières,
#:                         24,7 s pour les deux dernières (+19 %)
#:
#: La RAM n'est donc pas la contrainte, et la contention reste modeste.
#: **La vraie limite est ailleurs** : toutes ces sessions parlent au même
#: Ollama, qui ne tient qu'un modèle à la fois
#: (`OLLAMA_MAX_LOADED_MODELS=1`). Six missions réclamant six modèles
#: différents feraient s'évincer les poids en boucle — un coût qui ne se
#: voit pas dans les chiffres ci-dessus, parce qu'elles employaient toutes
#: le même modèle.
#:
#: D'où six et non davantage : la mesure autorise plus, l'éviction non.
PLAFOND_SESSIONS = 6

#: Combien de tours consecutifs sans aboutir avant de cesser de refaire la
#: meme experience.
#:
#: Mesure du 2026-08-23, campagne Skill360 §7. Le budget d'un tour etait a
#: 3600 s et Qwen3.8-27B, sur une boucle agentique a contexte long, ne rend
#: pas la main dedans. Le journal montre quatre tours a la seconde pres :
#:
#:     03:47:59  harnais : tour non abouti (stop='')
#:     04:47:59  harnais : tour non abouti (stop='')
#:     05:47:59  harnais : tour non abouti (stop='')
#:     06:47:59  harnais : tour non abouti (stop='')
#:
#: Quatre heures — 59 % de la nuit — pour zero livrable, a rejouer une
#: experience dont le resultat etait connu des la deuxieme. Le defaut n'est
#: pas la lenteur du modele : c'est que personne ne comptait les repetitions.
#:
#: Deux, et pas un : un premier tour perdu peut etre une coupure reseau
#: (l'agent a bien vu des `APIConnectionError` cette nuit-la). Un second, sur
#: la meme session et le meme modele, est une reproduction.
PLAFOND_TOURS_PERDUS = 2

#: Une mission qui ne s'est pas manifestée depuis une demi-heure a
#: probablement échoué sans le dire. Sans cette purge, son processus agent
#: survivrait au serveur qui l'a lancé.
TTL_INACTIVITE_S = 1800.0


def cle_de_session(runtime_ctx: dict) -> str:
    """Sur quoi la continuité doit porter : le projet, sinon la mission.

    Une mission par section, c'est une session par section — et la section 4
    ignore alors tout de ce qu'a fait la section 3. Or c'est exactement le
    cas d'usage : `derouler_cahier.py` lance les 26 sections d'un cahier
    comme autant d'objectifs successifs **sur le même dossier**, donc sur le
    même Project. Grouper par projet donne la continuité à toute la campagne.

    Deux missions concurrentes sur un même projet partagent alors leur
    session. Ce n'est pas un accident : leurs tours restent sérialisés par
    le verrou de session, et travailler sur le même workspace en sachant ce
    que l'autre y a fait vaut mieux que l'ignorer. La fenêtre se remplit
    plus vite, et c'est la compression de l'agent qui prend le relais — la
    raison même pour laquelle elle a été rendue atteignable.

    Sans projet, on retombe sur la mission : une mission isolée n'a rien à
    partager avec personne.
    """
    projet = str(runtime_ctx.get("project_id") or "").strip()
    if projet:
        return f"projet:{projet}"
    mission = str(runtime_ctx.get("mission_id") or "").strip()
    return f"mission:{mission}" if mission else ""


def porte_sur_une_mission_seule(cle: str) -> bool:
    """La clé est-elle propre à une seule mission ?

    Décide qui a le droit de fermer la session à la fin d'une mission. Une
    session de projet survit à la mission qui l'a ouverte — la fermer
    reviendrait à jeter le contexte juste avant la section suivante, soit
    précisément l'amnésie qu'on corrige.
    """
    return cle.startswith("mission:")


@dataclass
class _Entree:
    client: HermesAgentACP
    workspace: str
    tours: int = 0
    #: Tours consecutifs qui n'ont pas abouti. Remis a zero des qu'un tour
    #: aboutit : ce qui compte est la repetition, pas le total.
    tours_perdus: int = 0
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
        # Les identifiants de session **survivent a la fermeture**. L'agent
        # persiste ses sessions sur disque : garder l'identifiant permet de
        # reprendre le contexte apres un processus mort, ou apres un
        # redemarrage du backend. Sans cela, un agent qui meurt a la section
        # 18 d'un cahier emporte toute la campagne — et le harnais ne
        # vaudrait alors, a cet instant, que le mode jetable qu'il remplace.
        self._identifiants: dict[str, str] = {}

    # -- interrogation ------------------------------------------------

    def sessions_ouvertes(self) -> int:
        return len(self._entrees)

    def connait(self, cle: str) -> bool:
        return cle in self._entrees

    def tours_de(self, cle: str) -> int:
        entree = self._entrees.get(cle)
        return entree.tours if entree else 0

    def tours_perdus_de(self, cle: str) -> int:
        """Combien de tours consecutifs cette session vient de perdre.

        Lu par l'executeur avant d'engager un tour : une session qui a deja
        perdu `PLAFOND_TOURS_PERDUS` tours ne merite pas qu'on lui confie le
        meme budget avec le meme modele une fois de plus.
        """
        entree = self._entrees.get(cle)
        return entree.tours_perdus if entree else 0

    def noter(self, cle: str, abouti: bool) -> int:
        """Enregistrer l'issue d'un tour, et rendre le compte des echecs.

        Le registre ne peut pas la deduire seul : `tour()` rend un `Tour`
        non abouti sans lever, exactement comme il rend un tour normal. La
        difference est dans le champ `abouti`, que seul l'appelant regarde.
        """
        entree = self._entrees.get(cle)
        if entree is None:
            return 0
        entree.tours_perdus = 0 if abouti else entree.tours_perdus + 1
        return entree.tours_perdus

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

    async def fermer_projet(self, project_id: str) -> None:
        """Fin de campagne : libère la session qui traversait les missions.

        Une session de projet ne se ferme pas à la fin d'une mission — c'est
        tout son intérêt. Sans ce point de sortie, elle attendrait la purge
        d'inactivité, soit une demi-heure de processus retenu après le
        dernier travail utile.
        """
        await self.fermer(f"projet:{project_id}")

    async def fermer_tout(self) -> None:
        async with self._verrou:
            for cle in list(self._entrees):
                await self._fermer_sans_verrou(cle)

    async def _ouvrir(self, cle: str, workspace: str) -> _Entree:
        """Ouvre — ou **reprend** — la session de cette clé."""
        client = self._fabrique()
        session = await client.ouvrir(
            workspace, reprendre=self._identifiants.get(cle, ""))
        identifiant = getattr(session, "session_id", "") if session else ""
        if identifiant:
            self._identifiants[cle] = identifiant
        reprise = bool(getattr(session, "reprise", False))
        logger.info("session %s %s sur %s", cle,
                    "reprise" if reprise else "ouverte", workspace)
        entree = _Entree(client=client, workspace=workspace,
                         derniere_activite=self._horloge())
        self._entrees[cle] = entree
        return entree

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
                   delai: float = DELAI_TOUR_S,
                   au_fil_de_l_eau: Any = None) -> Tour:
        """Un tour dans la session de cette mission, ouverte au besoin.

        `amorce` n'est envoyée qu'au **premier** tour : c'est le contexte de
        mission, que l'agent conserve ensuite lui-même.

        `au_fil_de_l_eau(genre, fragment)` reçoit chaque morceau au moment
        où il arrive. Une tâche de mission n'en a pas besoin ; une
        conversation si, où une minute d'attente muette ne se distingue pas
        d'une panne.

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
                entree = await self._ouvrir(cle, workspace)

        if modele:
            # Hors du verrou du registre : la bascule est un aller-retour
            # avec l'agent, et tenir le verrou pendant ce temps bloquerait
            # toutes les autres missions.
            await entree.client.choisir_modele(modele)

        premier = entree.tours == 0
        message = f"{amorce}\n\n{texte}" if (premier and amorce) else texte
        try:
            resultat = await entree.client.tour(
                message, delai=delai, au_fil_de_l_eau=au_fil_de_l_eau)
        except Exception as erreur:  # noqa: BLE001 - une seule reprise
            # Un processus d'agent mort en plein tour ne doit pas emporter la
            # campagne. L'agent persiste ses sessions : on rouvre, on reprend
            # l'identifiant, et on rejoue **le tour, une fois**.
            #
            # Une seule fois, et c'est delibere : reessayer en boucle sur une
            # panne persistante transformerait un echec lisible en attente
            # muette, ce qui a deja coute une seance entiere a ce projet.
            logger.warning("session %s perdue en plein tour (%s) — reprise",
                           cle, erreur)
            async with self._verrou:
                await self._fermer_sans_verrou(cle)
                entree = await self._ouvrir(cle, workspace)
            resultat = await entree.client.tour(
                message, delai=delai, au_fil_de_l_eau=au_fil_de_l_eau)
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
