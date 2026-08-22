"""Une reparation qui n'a rien a reparer n'est pas un echec (HOS-147).

L'incident, mesure le 2026-08-22 sur la section §16 d'un deroule de cahier.

La passe 1 a cree les trois livrables annonces, une reprise interne les a
affines, puis la passe 2 n'a **rien ecrit** — parce qu'il n'y avait plus
rien a ecrire. `contradicted` a vu « rien change » et bloque la campagne.

Verification apres coup, sur le disque :

    docs/employee_assignment.md        969 o
    models/employee_assignment.py     2013 o
    tests/test_employee_assignment.py 1405 o
    3 passed

La section etait terminee. **Dix sections sur vingt-deux n'ont jamais ete
atteintes** a cause de ce verdict — la campagne s'est arretee a mi-parcours
sur un succes.

C'est le pendant exact du defaut que ce module existe pour attraper. « Ne
jamais croire un succes sur parole » a un jumeau, « ni un echec sur
parole », et cinq des defauts de mesure de ce depot etaient deja des echecs
imaginaires.
"""
from __future__ import annotations

import pytest

from backend.mission.verification import MissionVerification, WorkspaceDiff


def _rapport(**kw) -> MissionVerification:
    return MissionVerification(
        mission_id="m-16", reported_success=True, workspace="/w",
        measured=True, changes=kw.pop("changes", WorkspaceDiff()), **kw)


class TestLaPorteSOuvre:
    def test_le_cas_mesure(self):
        """Rien ecrit, tests executes et passes, manifeste tenu."""
        rapport = _rapport(tests={"ran": True, "passed": True})

        assert rapport.travail_deja_fait is True
        assert rapport.contradicted is False

    def test_un_manifeste_explicitement_tenu_passe_aussi(self):
        rapport = _rapport(tests={"ran": True, "passed": True},
                           manifeste={"manquants": []})

        assert rapport.contradicted is False


class TestLaPorteResteFermee:
    """Les trois conditions sont necessaires. En relacher une rouvrirait la
    porte au defaut d'origine : une mission qui rapporte un succes sans rien
    accomplir."""

    def test_sans_tests_executes(self):
        """Un projet sans test ne peut pas se declarer sain par cette voie.
        C'est precisement celui qui en aurait le plus besoin, et c'est
        pourquoi on refuse."""
        for tests in ({"ran": False}, {}, None):
            assert _rapport(tests=tests).contradicted is True

    def test_avec_des_tests_qui_echouent(self):
        assert _rapport(tests={"ran": True, "passed": False}).contradicted is True

    def test_avec_un_livrable_annonce_manquant(self):
        """Une mission qui n'a vraiment rien fait se trahit la : ses
        livrables annonces ne sont pas sur le disque."""
        rapport = _rapport(tests={"ran": True, "passed": True},
                           manifeste={"manquants": ["models/x.py"]})

        assert rapport.travail_deja_fait is False
        assert rapport.contradicted is True

    @pytest.mark.parametrize("defaut", [
        {"imports": {"fatals": ["a -> b -> a"]}},
        {"imports_remontent": {"fichier": "t/x.py", "ligne": 2,
                               "niveau": 2, "profondeur": 1}},
    ])
    def test_un_defaut_de_code_prime_sur_le_travail_deja_fait(self, defaut):
        """Une boucle d'import fatale ou un import hors paquet contredit,
        meme si les tests passent : ils peuvent passer sans jamais importer
        le module fautif."""
        rapport = _rapport(tests={"ran": True, "passed": True}, **defaut)

        assert rapport.contradicted is True


class TestCeQuiNeChangePas:
    def test_une_mission_non_mesuree_ne_contredit_rien(self):
        rapport = MissionVerification(
            mission_id="m", reported_success=True, workspace="/w",
            changes=WorkspaceDiff(), measured=False,
            tests={"ran": True, "passed": True})

        assert rapport.contradicted is False

    def test_le_rapport_porte_l_etat(self):
        """Sans cela, un operateur lisant « non contredite, rien ecrit »
        n'aurait aucun moyen de savoir pourquoi."""
        rapport = _rapport(tests={"ran": True, "passed": True})

        assert rapport.as_dict()["travail_deja_fait"] is True
