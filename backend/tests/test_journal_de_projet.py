"""Un projet se souvient de ses missions précédentes (HOS-123).

Le contexte amont (HOS-121) et le manifeste (HOS-122) font tenir **une**
mission ensemble ; ils s'évaporent avec elle. Un cahier des charges de
quarante sections se fait en quarante missions, et jusqu'ici la douzième
repartait aveugle.

La contrainte qui décide de toute la conception : le cahier Skills360 dit
de son propre `PROJECT_STATUS.md` qu'il ne faut « jamais le compléter par
supposition », et que toute information doit venir du dépôt réel, d'un
résultat de test réel, d'une spécification ou d'une décision explicite.

Un journal rédigé **par le modèle** serait exactement cette fabrication —
et pire que pas de journal, puisque le lancement suivant le lirait comme un
fait établi. Ce journal n'écrit donc que des mesures.
"""
from __future__ import annotations

from backend.mission import journal
from backend.mission.verification import (
    MissionVerification, WorkspaceDiff, snapshot,
)


def _verif(*, created=(), modified=(), deleted=(), tests=None, manifeste=None,
           mesure=True, succes=True) -> MissionVerification:
    return MissionVerification(
        mission_id="m", reported_success=succes, workspace="/w",
        changes=WorkspaceDiff(created=created, modified=modified,
                              deleted=deleted),
        measured=mesure, tests=tests, manifeste=manifeste,
    )


class TestCeQuiEstEcrit:
    def test_les_fichiers_mesures_y_sont(self, tmp_path):
        journal.ecrire(str(tmp_path), "Modèle d'identité",
                       _verif(created=("identity_model.py",)))

        texte = (tmp_path / journal.CHEMIN_RELATIF).read_text(encoding="utf-8")

        assert "identity_model.py" in texte
        assert "Modèle d'identité" in texte

    def test_des_tests_non_lances_ne_sont_pas_ecrits_comme_passes(self, tmp_path):
        """Le défaut que ce dépôt traque depuis le début. L'écrire dans une
        mémoire persistante le ferait durer d'une mission à l'autre."""
        journal.ecrire(str(tmp_path), "o", _verif(
            created=("a.py",),
            tests={"ran": False, "reason": "verification_run needs autonomy "
                                           "level 'high'"}))

        texte = (tmp_path / journal.CHEMIN_RELATIF).read_text(encoding="utf-8")

        assert "non lancés" in texte
        assert "autonomy" in texte, "la raison doit voyager avec l'état"
        assert "passés" not in texte.split("Tests du livrable")[1][:60]

    def test_des_tests_en_echec_sont_ecrits_comme_tels(self, tmp_path):
        journal.ecrire(str(tmp_path), "o", _verif(
            created=("a.py",), tests={"ran": True, "passed": False}))

        assert "en échec" in (tmp_path / journal.CHEMIN_RELATIF).read_text(
            encoding="utf-8")

    def test_un_livrable_manquant_est_nomme(self, tmp_path):
        journal.ecrire(str(tmp_path), "o", _verif(
            created=("autre.py",),
            manifeste={"declares": 2, "manquants": ["promis.py"],
                       "nombre_manquants": 1, "tenu": False}))

        assert "promis.py" in (tmp_path / journal.CHEMIN_RELATIF).read_text(
            encoding="utf-8")

    def test_une_mission_contredite_est_signalee_a_la_suivante(self, tmp_path):
        """Repartir des conclusions d'une mission que la mesure dément est
        la façon la plus directe de propager une erreur."""
        journal.ecrire(str(tmp_path), "o", _verif(created=(), succes=True))

        texte = (tmp_path / journal.CHEMIN_RELATIF).read_text(encoding="utf-8")

        assert "contredit" in texte

    def test_une_mission_non_mesuree_n_est_pas_ecrite_comme_reussie(self, tmp_path):
        journal.ecrire(str(tmp_path), "o", _verif(mesure=False))

        texte = (tmp_path / journal.CHEMIN_RELATIF).read_text(encoding="utf-8")

        assert "Rien n'a été mesuré" in texte

    def test_l_en_tete_dit_d_ou_vient_le_contenu(self, tmp_path):
        """Un lecteur — humain ou modèle — doit pouvoir savoir qu'aucune
        ligne ne vient du récit d'un modèle."""
        journal.ecrire(str(tmp_path), "o", _verif(created=("a.py",)))

        texte = (tmp_path / journal.CHEMIN_RELATIF).read_text(encoding="utf-8")

        assert "uniquement à partir de mesures" in texte


class TestLaRelecture:
    def test_les_entrees_s_accumulent(self, tmp_path):
        journal.ecrire(str(tmp_path), "première", _verif(created=("a.py",)))
        journal.ecrire(str(tmp_path), "deuxième", _verif(created=("b.py",)))

        relu = journal.relire(str(tmp_path))

        assert "a.py" in relu and "b.py" in relu

    def test_seules_les_dernieres_sont_relues(self, tmp_path):
        """Tout relire repousserait les instructions de la tâche hors de la
        fenêtre — le mur des 64k documenté dans CLAUDE.md."""
        for i in range(10):
            journal.ecrire(str(tmp_path), f"mission {i}",
                           _verif(created=(f"f{i}.py",)))

        relu = journal.relire(str(tmp_path), entrees=3)

        assert "f9.py" in relu
        assert "f0.py" not in relu

    def test_un_projet_neuf_rend_None(self, tmp_path):
        """« Premier passage » est une information, et elle diffère de
        « les missions précédentes n'ont rien fait »."""
        assert journal.relire(str(tmp_path)) is None

    def test_l_en_tete_n_est_pas_relue_comme_une_entree(self, tmp_path):
        journal.ecrire(str(tmp_path), "seule", _verif(created=("a.py",)))

        relu = journal.relire(str(tmp_path))

        assert relu.startswith("## ")

    def test_sans_workspace_rien_n_est_lu_ni_ecrit(self):
        assert journal.relire(None) is None
        assert journal.ecrire(None, "o", _verif()) is False


class TestLeJournalNeCompteJamaisCommeDuTravail:
    """Le piège de cette fonctionnalité, et la raison pour laquelle
    `.hermes` figure dans `_IGNORED_DIRS`."""

    def test_ecrire_le_journal_ne_fait_pas_bouger_le_diff(self, tmp_path):
        """Sans ça, une mission qui n'aurait rien fait d'autre qu'écrire sa
        propre trace verrait `touched_anything` à vrai au passage suivant et
        passerait pour productive — le faux succès exact que ce module est
        censé documenter."""
        avant = snapshot(str(tmp_path))
        journal.ecrire(str(tmp_path), "une mission stérile", _verif(created=()))
        apres = snapshot(str(tmp_path))

        from backend.mission.verification import diff

        assert diff(avant, apres).touched_anything is False

    def test_le_journal_existe_bien_malgre_tout(self, tmp_path):
        """Le garde-fou du test précédent : il doit prouver que le diff
        ignore un fichier réellement écrit, pas qu'aucun ne l'a été."""
        journal.ecrire(str(tmp_path), "o", _verif(created=()))

        assert (tmp_path / journal.CHEMIN_RELATIF).is_file()


class TestCeQueLaTacheRecoit:
    def test_le_journal_est_annonce_comme_mesure(self, tmp_path, monkeypatch):
        """Un modèle qui le prendrait pour un récit pourrait le contredire
        ou le compléter ; il doit savoir que ce sont des faits."""
        from backend.core.bootstrap import service_registry

        journal.ecrire(str(tmp_path), "précédente", _verif(created=("a.py",)))
        monkeypatch.setattr(service_registry, "_workspace_project_for",
                            lambda t: ("p", str(tmp_path)))

        texte = service_registry._journal_du_projet(object())

        assert "mesuré" in texte
        assert "a.py" in texte
        assert "réellement eu lieu" in texte

    def test_sans_workspace_aucune_section(self, monkeypatch):
        from backend.core.bootstrap import service_registry

        monkeypatch.setattr(service_registry, "_workspace_project_for",
                            lambda t: None)

        assert service_registry._journal_du_projet(object()) is None

    def test_un_projet_neuf_n_ajoute_aucune_section(self, tmp_path, monkeypatch):
        """Une section vide dirait « rien n'a été fait avant », ce qui est
        vrai — mais un en-tête sans contenu se lit comme une absence de
        travail plutôt que comme un premier passage."""
        from backend.core.bootstrap import service_registry

        monkeypatch.setattr(service_registry, "_workspace_project_for",
                            lambda t: ("p", str(tmp_path)))

        assert service_registry._journal_du_projet(object()) is None
