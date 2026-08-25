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

import backend.execution.task_executor as te
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


# -- la mesure ---------------------------------------------------------

def test_un_tour_au_bord_de_la_fenetre_est_signale() -> None:
    """65042 jetons sur 65536 : le tour passe, le suivant deborde."""
    assert te.contexte_sature(65042, "gpt-oss-20b-64k")


def test_un_tour_confortable_ne_coupe_rien() -> None:
    """Couper la continuite est un cout : on ne le paie qu'au bord.

    C'est tout ce que le harnais apporte au-dela du mode jetable, et le
    perdre par precaution serait payer sans rien acheter.
    """
    assert not te.contexte_sature(40_000, "gpt-oss-20b-64k")


def test_un_modele_sans_fenetre_connue_ne_coupe_rien() -> None:
    """Sans mesure, on ne coupe pas une continuite sur une supposition."""
    assert not te.contexte_sature(999_999, "modele-inexistant-42b")


def test_un_tour_sans_compteur_ne_coupe_rien() -> None:
    """`inputTokens` absent rend zero ; zero n'est pas une saturation."""
    assert not te.contexte_sature(0, "gpt-oss-20b-64k")


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
