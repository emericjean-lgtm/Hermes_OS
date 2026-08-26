"""L'agent envoyait plus que ce que le modele sert (HOS-165).

Campagne Skill360, §21, modele servi a 65536 :

    in=59940  total=61623   passe
    in=64696  total=65465   passe (98,7 %)
    in=68753  total=70431   ECHEC — 5 000 jetons au-dela de la fenetre

La compression de l'agent tournait — trente fois — mais **huit de ces
trente ont echoue**, et elle ne rattrapait plus l'accumulation d'une
session tenue ouverte sur vingt sections. Cote Ollama la requete meurt en
`APIConnectionError`, cote Hermes OS le tour est perdu. §21 a echoue quatre
fois de suite sur ce seul motif, sur trois lancements differents.

Elargir la fenetre n'etait pas une option : gpt-oss-20b a 131072 demande
22,46 Gio et deborde a 100 % sur CPU, pour une carte qui en offre seize.
"""
from __future__ import annotations

import asyncio

from backend.ral.adapters.sessions_de_mission import SessionsDeMission


class _Client:
    session_id = "s-neuve"

    def disponible(self):
        return True, ""

    async def ouvrir(self, cwd, reprendre=None):
        self.reprise = reprendre
        return None

    async def fermer(self):
        return None


# -- la remise a neuf --------------------------------------------------

def test_repartir_a_neuf_oublie_l_identifiant() -> None:
    """`fermer` seul aurait fait reprendre la meme session saturee.

    Les identifiants survivent deliberement a la fermeture, pour qu'un
    agent mort en pleine campagne reprenne son contexte. C'est le bon
    comportement en general, et exactement le mauvais ici.
    """
    async def scenario():
        client = _Client()
        registre = SessionsDeMission(fabrique=lambda: client)
        registre._identifiants["projet:x"] = "session-saturee"

        await registre.repartir_a_neuf("projet:x")

        assert "projet:x" not in registre._identifiants

        # La prochaine ouverture ne doit demander aucune reprise.
        await registre._ouvrir("projet:x", "/ws")
        assert client.reprise == ""

    asyncio.run(scenario())


def test_fermer_seul_conserve_l_identifiant() -> None:
    """Le contraste qui justifie la nouvelle methode."""
    async def scenario():
        registre = SessionsDeMission(fabrique=lambda: _Client())
        registre._identifiants["projet:x"] = "session-a-reprendre"

        await registre.fermer("projet:x")

        assert registre._identifiants["projet:x"] == "session-a-reprendre"

    asyncio.run(scenario())


def test_le_compte_de_tours_perdus_est_remis_a_zero() -> None:
    """Une session neuve ne porte pas les echecs de l'ancienne."""
    async def scenario():
        registre = SessionsDeMission(fabrique=lambda: _Client())
        registre.noter("projet:x", abouti=False)
        registre.noter("projet:x", abouti=False)
        assert registre.tours_perdus_de("projet:x") == 2

        await registre.repartir_a_neuf("projet:x")

        assert registre.tours_perdus_de("projet:x") == 0

    asyncio.run(scenario())


# -- le declencheur correct (HOS-167) ---------------------------------

def test_deux_tours_perdus_sans_secours_demandent_une_session_neuve() -> None:
    """HOS-165 comparait un cumul de session a une fenetre par requete.

    Mesure du 2026-08-25, 37 declenchements : min 80 414, mediane 503 792,
    max 2 692 449 jetons — contre un seuil de 58 982. Deux millions de
    jetons d'entree dans une fenetre de 65 536 est impossible :
    `jetons_entree` est un cumul de session, pas l'entree d'une requete.
    La regle se declenchait donc presque toujours (74 remises a neuf) et
    detruisait la continuite qui fait tout l'interet du harnais.

    Le signal retenu ne suppose rien d'un compteur dont on ignore la
    semantique : deux tours perdus d'affilee sur la meme cle est un fait
    observe. Et quand aucun modele de secours n'existe, changer de session
    est la seule variable qui reste — rejouer a l'identique est ce qui a
    coute quatre heures a §7.
    """
    import backend.execution.task_executor as te
    from backend.ral.adapters.sessions_de_mission import (
        PLAFOND_TOURS_PERDUS, SessionsDeMission)

    registre = SessionsDeMission()
    for _ in range(PLAFOND_TOURS_PERDUS):
        registre.noter("projet:x", abouti=False)

    te._apres_des_tours_perdus("gpt-oss-20b-64k", "projet:x", registre)

    assert registre.doit_repartir_a_neuf("projet:x")


def test_avec_un_secours_on_change_de_modele_pas_de_session(monkeypatch) -> None:
    """Une variable a la fois : le modele d'abord, il est plus informatif."""
    import backend.execution.task_executor as te
    from backend.ral.adapters.sessions_de_mission import (
        PLAFOND_TOURS_PERDUS, SessionsDeMission)

    monkeypatch.setenv("HERMES_MISSION_MODEL",
                       "code_review=qwen38-27b-64k,*=gpt-oss-20b-64k")
    registre = SessionsDeMission()
    for _ in range(PLAFOND_TOURS_PERDUS):
        registre.noter("projet:x", abouti=False)

    obtenu = te._apres_des_tours_perdus("qwen38-27b-64k", "projet:x", registre)

    assert obtenu == "gpt-oss-20b-64k"
    assert not registre.doit_repartir_a_neuf("projet:x")


def test_la_demande_est_consommee_une_seule_fois() -> None:
    """Sans cela, chaque tour repartirait a neuf et la continuite mourrait.

    C'est exactement le defaut que HOS-165 avait produit.
    """
    from backend.ral.adapters.sessions_de_mission import SessionsDeMission

    registre = SessionsDeMission()
    registre.a_repartir_a_neuf("projet:x")

    assert registre.doit_repartir_a_neuf("projet:x")
    assert not registre.doit_repartir_a_neuf("projet:x")
