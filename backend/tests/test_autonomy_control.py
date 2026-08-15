"""Régler le niveau d'autonomie sans éditer un fichier (HOS-115).

Les quatre niveaux du §17.5 existaient depuis le début et Aegis les
appliquait, mais rien ne les exposait : on ne pouvait ni savoir lequel
s'appliquait ni en changer sans éditer `config/security.yaml` et
redémarrer. Un garde-fou qu'on ne peut pas régler pendant qu'on travaille
finit réglé une fois pour toutes, au niveau le plus permissif dont on a eu
besoin un jour.

Ce que ces tests protègent avant tout : qu'aucun niveau, si permissif
soit-il, ne contourne le §17.3.
"""
from __future__ import annotations

import pytest

from backend.security import autonomy


@pytest.fixture(autouse=True)
def _donnees_isolees(tmp_path, monkeypatch):
    """La dérogation vit dans un fichier — sans isolation, ces tests
    écriraient dans le vrai `data/` du développeur et changeraient sa
    sécurité pour de bon."""
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    yield


class TestLaDerogation:
    def test_sans_derogation_rien_n_est_impose(self):
        assert autonomy.lire_derogation() is None

    def test_un_niveau_ecrit_se_relit(self):
        autonomy.ecrire_derogation("high")
        assert autonomy.lire_derogation() == "high"

    def test_un_niveau_inconnu_est_refuse_a_l_ecriture(self):
        """Refusé au bord plutôt que traité comme rang 0 plus loin : un
        niveau inventé qui deviendrait silencieusement « low » serait un
        resserrement invisible, un qui deviendrait « high » serait pire."""
        with pytest.raises(ValueError, match="inconnu"):
            autonomy.ecrire_derogation("maximum")

    def test_effacer_revient_au_fichier(self):
        autonomy.ecrire_derogation("high")
        autonomy.effacer_derogation()
        assert autonomy.lire_derogation() is None

    def test_effacer_deux_fois_ne_leve_pas(self):
        autonomy.effacer_derogation()
        autonomy.effacer_derogation()


class TestUnFichierAbimeNeBloquePasLeDemarrage:
    """Un garde-fou dont la panne empêche de démarrer finit par être
    retiré. Un fichier illisible doit ramener au réglage écrit par un
    humain dans `security.yaml`, pas faire tomber le système."""

    def test_du_json_invalide_est_ignore(self, tmp_path):
        (tmp_path / "autonomy_override.json").write_text("{ pas du json", encoding="utf-8")
        assert autonomy.lire_derogation() is None

    def test_un_niveau_inconnu_dans_le_fichier_est_ignore(self, tmp_path):
        (tmp_path / "autonomy_override.json").write_text(
            '{"autonomy_level": "maximum"}', encoding="utf-8")
        assert autonomy.lire_derogation() is None

    def test_un_fichier_vide_est_ignore(self, tmp_path):
        (tmp_path / "autonomy_override.json").write_text("", encoding="utf-8")
        assert autonomy.lire_derogation() is None


class TestLaMatriceApplique:
    def test_la_derogation_l_emporte_sur_le_fichier(self):
        from backend.security.permission_matrix import PermissionMatrix

        autonomy.ecrire_derogation("high")
        matrice = PermissionMatrix({"autonomy_level": "low", "action_categories": {}})

        assert matrice.autonomy_level == "high"

    def test_sans_derogation_c_est_le_fichier_qui_decide(self):
        from backend.security.permission_matrix import PermissionMatrix

        matrice = PermissionMatrix({"autonomy_level": "medium", "action_categories": {}})

        assert matrice.autonomy_level == "medium"


class TestLeCurseurNeContournePasLe173:
    """Le test qui compte. `mandatory_validation` est absolu : aucun
    niveau, y compris le plus permissif, ne rend auto-autorisée une
    suppression de fichier ou une migration de données."""

    @pytest.mark.parametrize("niveau", autonomy.NIVEAUX)
    def test_une_categorie_a_validation_obligatoire_reste_bloquee(self, niveau):
        from backend.security.aegis_engine import ActionRequest, AegisEngine, Verdict
        from backend.security.permission_matrix import PermissionMatrix

        matrice = PermissionMatrix({
            "autonomy_level": niveau,
            "action_categories": {
                "file_delete": {"mutating": True, "path_based": False,
                                "mandatory_validation": True},
            },
        })
        moteur = AegisEngine(matrice, [])

        decision = moteur.evaluate(ActionRequest(
            action_type="file_delete", description="supprimer",
            requesting_agent="test",
        ))

        assert decision.verdict == Verdict.REQUIRE_HUMAN_VALIDATION

    def test_les_effets_annonces_couvrent_tous_les_niveaux(self):
        """Un niveau proposé sans description laisse l'opérateur deviner ce
        qu'il vient d'autoriser."""
        assert set(autonomy.EFFETS) == set(autonomy.NIVEAUX)
        assert all(autonomy.EFFETS[n].strip() for n in autonomy.NIVEAUX)
