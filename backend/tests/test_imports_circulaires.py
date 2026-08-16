"""Un livrable dont les modules s'importent en rond (HOS-124).

L'incident, mesuré sur l'étape 2 de l'essai de mémoire : la mission a
produit `organization.py` et `workshop.py` qui s'importent mutuellement.

    ImportError: cannot import name 'Organization' from partially
    initialized module 'organization' (most likely due to a circular import)

**Aucun instrument ne le voyait.** La porte de syntaxe (HOS-121) analyse
chaque fichier isolément et les deux compilent parfaitement. Le verdict des
tests (HOS-119) l'aurait attrapé, mais il ne tournait pas au niveau
d'autonomie livré, et il ne dit rien d'un projet sans tests.

L'analyse est **statique** : importer du code écrit par un modèle, c'est
l'exécuter, ce que `verification_run` place derrière une décision
d'opérateur.
"""
from __future__ import annotations

from backend.mission import imports_locaux as il


def _projet(tmp_path, **fichiers: str):
    for nom, contenu in fichiers.items():
        chemin = tmp_path / nom.replace("__", "/")
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
    return str(tmp_path)


class TestLIncidentMesure:
    def test_la_boucle_est_trouvee_et_nommee(self, tmp_path):
        racine = _projet(
            tmp_path,
            **{"organization.py": "from workshop import Workshop\n\n"
                                  "class Organization:\n    pass\n",
               "workshop.py": "from organization import Organization\n\n"
                              "class Workshop:\n    pass\n"})

        v = il.verdict(racine)

        assert v["cycles"], "la boucle mesurée doit être vue"
        assert "organization" in v["cycles"][0]
        assert "workshop" in v["cycles"][0]

    def test_elle_est_demontree_fatale(self, tmp_path):
        """Le nom importé est défini **après** l'import qui referme la
        boucle : au moment où le module est réimporté, il n'existe pas
        encore. C'est exactement l'ImportError observée."""
        racine = _projet(
            tmp_path,
            **{"organization.py": "from workshop import Workshop\n\n"
                                  "class Organization:\n    pass\n",
               "workshop.py": "from organization import Organization\n\n"
                              "class Workshop:\n    pass\n"})

        assert il.contredit(il.verdict(racine)) is True

    def test_ce_que_la_porte_de_syntaxe_ne_voit_pas(self, tmp_path):
        """Les deux fichiers compilent : c'est pour ça qu'il fallait un
        second instrument."""
        from backend.tools import syntaxe

        for source in ("from workshop import Workshop\nclass Organization: pass\n",
                       "from organization import Organization\nclass Workshop: pass\n"):
            assert syntaxe.verdict("m.py", source) is None


class TestCeQuiNEstPasSignale:
    """Un faux échec coûte autant qu'un faux succès — cinq des huit défauts
    de mesure de ce dépôt étaient des échecs imaginaires."""

    def test_un_projet_sain_ne_produit_rien(self, tmp_path):
        racine = _projet(
            tmp_path,
            **{"a.py": "class A:\n    pass\n",
               "b.py": "from a import A\n\nclass B:\n    pass\n"})

        v = il.verdict(racine)

        assert v["cycles"] == []
        assert il.contredit(v) is False

    def test_un_import_dans_une_fonction_ne_ferme_aucune_boucle(self, tmp_path):
        """C'est même la façon canonique de casser un cycle. Le compter
        signalerait comme défaut la correction elle-même."""
        racine = _projet(
            tmp_path,
            **{"a.py": "from b import B\n\nclass A:\n    pass\n",
               "b.py": "class B:\n    def f(self):\n        from a import A\n"
                       "        return A\n"})

        assert il.verdict(racine)["cycles"] == []

    def test_un_import_sous_TYPE_CHECKING_non_plus(self, tmp_path):
        """Il ne s'exécute pas à l'import : cette boucle-là n'existe que
        pour le typeur."""
        racine = _projet(
            tmp_path,
            **{"a.py": "from b import B\n\nclass A:\n    pass\n",
               "b.py": "from typing import TYPE_CHECKING\n"
                       "if TYPE_CHECKING:\n    from a import A\n\n"
                       "class B:\n    pass\n"})

        assert il.verdict(racine)["cycles"] == []

    def test_un_fichier_qui_ne_compile_pas_n_est_pas_une_boucle(self, tmp_path):
        """Il relève de la porte de syntaxe. Le diagnostiquer ici donnerait
        une cause fausse."""
        racine = _projet(tmp_path, **{"a.py": "def f(:\n", "b.py": "x = 1\n"})

        v = il.verdict(racine)

        assert v is not None and v["cycles"] == []

    def test_ce_depot_lui_meme_ne_declenche_rien(self):
        """Le garde-fou le plus parlant : trois cents modules réels, écrits
        par des humains, dont aucun ne doit être signalé."""
        v = il.verdict("backend/mission")

        assert v is not None and v["modules"] > 5
        assert v["fatals"] == []


class TestLeDoublonEnfoui:
    """Le défaut trouvé en construisant ce module.

    `fichiers[chemin.stem] = chemin` gardait le **dernier** trouvé. Un
    doublon enfoui — exactement ce que produisait l'arbre fantôme de
    HOS-123b — masquait le vrai module : le `organization.py` fantôme
    faisait 140 octets sans un seul import, et sa présence effaçait la
    boucle que ce module est censé détecter.
    """

    def test_le_module_le_plus_proche_de_la_racine_gagne(self, tmp_path):
        racine = _projet(
            tmp_path,
            **{"organization.py": "from workshop import Workshop\n\n"
                                  "class Organization:\n    pass\n",
               "workshop.py": "from organization import Organization\n\n"
                              "class Workshop:\n    pass\n",
               "enfoui__profond__organization.py": "class Organization:\n    pass\n"})

        assert il.verdict(racine)["fatals"], (
            "un doublon enfoui ne doit pas masquer le module réel")


class TestLIntegrationDansLaVerification:
    def test_une_boucle_fatale_contredit_un_succes_annonce(self, tmp_path):
        from backend.mission.verification import snapshot, verify

        avant = snapshot(str(tmp_path))
        _projet(tmp_path,
                **{"organization.py": "from workshop import Workshop\n\n"
                                      "class Organization:\n    pass\n",
                   "workshop.py": "from organization import Organization\n\n"
                                  "class Workshop:\n    pass\n"})
        apres = snapshot(str(tmp_path))

        v = verify("m", True, str(tmp_path), avant, apres)

        assert v.changes.touched_anything, "des fichiers ont bien été écrits"
        assert v.imports_boucles is True
        assert v.contradicted is True
        assert v.verified is False

    def test_le_verdict_voyage_dans_le_rapport(self, tmp_path):
        from backend.mission.verification import snapshot, verify

        avant = snapshot(str(tmp_path))
        _projet(tmp_path,
                **{"organization.py": "from workshop import Workshop\n\n"
                                      "class Organization:\n    pass\n",
                   "workshop.py": "from organization import Organization\n\n"
                                  "class Workshop:\n    pass\n"})
        apres = snapshot(str(tmp_path))

        rendu = verify("m", True, str(tmp_path), avant, apres).as_dict()

        assert rendu["imports"]["fatals"]

    def test_l_onglet_l_affiche_comme_contredite(self):
        from backend.autonomous.autonomous_models import AutonomousReport

        rapport = AutonomousReport(
            goal_id="g", success=True,
            verification={"verified": True, "measured": True,
                          "imports": {"modules": 2,
                                      "cycles": ["a -> b -> a"],
                                      "fatals": ["a -> b -> a"]}})

        assert rapport.qualite == "contredite"
