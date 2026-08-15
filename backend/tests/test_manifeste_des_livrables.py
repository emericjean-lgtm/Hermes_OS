"""Chaque tâche déclare ses fichiers, et on vérifie (HOS-122).

L'incident, mesuré sur le troisième lancement de l'essai Skills360 — celui
qui avait pourtant réglé la duplication du code :

    test_identity_model.py          6 passent, 1 échoue
    tests/test_identity_model.py    1 passe,  4 échouent
    TypeError: User.__init__() missing 1 required positional argument: 'email'

Deux fichiers de tests au même nom de base — ce qui suffit à faire échouer
`pytest` à la collecte — et le second appelait `User("user_001",
"auth_uid_123")`. Il avait été écrit **sans jamais lire le module qu'il
teste**, parce que rien dans la mission ne disait que ce module existait ni
qui l'avait écrit.

Corriger le contexte amont (HOS-121) a fait converger le code : un seul
module d'identité au lieu de quatre. Mais l'amont ne remonte que les
dépendances **directes**. Deux tâches sœurs, sans lien entre elles, restent
aveugles l'une à l'autre.

`expected_outputs` existait depuis toujours sur `MissionNode`, était copié
par le planificateur et sérialisé — et **n'était rempli nulle part**. Le
champ était câblé de bout en bout sur du vide.
"""
from __future__ import annotations

from backend.core.bootstrap.service_registry import _livrables_pour
from backend.execution.execution_models import TaskExecution, TaskExecutionStatus
from backend.mission import manifeste
from backend.mission.mission_models import Mission, MissionNode
from backend.mission.planner.task_decomposer import _livrables


def _tache(mission_id: str, node_id: str) -> TaskExecution:
    """Comme `node_execution.make_node_executor` la construit."""
    return TaskExecution(
        task_id=f"{node_id}-task", node_id=node_id, mission_id=mission_id,
        title=node_id, status=TaskExecutionStatus.PENDING,
    )


class TestCeQueLeDecomposeurAccepte:
    def test_une_liste_de_chemins_passe(self):
        assert _livrables(["identity_model.py", "tests/test_identity.py"]) == [
            "identity_model.py", "tests/test_identity.py"]

    def test_les_antislashs_sont_normalises(self):
        """Le modèle rend parfois des chemins Windows ; deux écritures du
        même fichier ne doivent pas compter pour deux livrables."""
        assert _livrables(["tests\\test_a.py"]) == ["tests/test_a.py"]

    def test_les_doublons_sont_ecartes(self):
        assert _livrables(["a.py", "./a.py", "a.py"]) == ["a.py"]

    def test_rien_n_est_invente_quand_le_champ_manque(self):
        """Une tâche sans livrable déclaré est un cas normal — beaucoup
        n'écrivent rien. Un manifeste fabriqué serait pire que pas de
        manifeste : les tâches suivantes le prendraient pour une décision."""
        assert _livrables(None) == []
        assert _livrables("identity.py") == []
        assert _livrables([]) == []

    def test_un_chemin_absolu_ou_remontant_est_ecarte(self):
        """Ce champ répartit des fichiers dans un workspace ; ce n'est pas
        une porte vers le disque. La frontière de sécurité reste Aegis —
        mais rien ne gagne à laisser un `C:\\Windows\\...` voyager dans un
        prompt comme s'il était légitime."""
        assert _livrables(["/etc/passwd"]) == []
        assert _livrables(["../../secrets.py"]) == []
        assert _livrables(["C:/Windows/system32/x.py"]) == []


class TestCeQueLaTacheLit:
    def _mission(self, monkeypatch) -> Mission:
        mission = Mission(title="m", objective="o")
        mission.nodes = [
            MissionNode(node_id="n1", title="Écrire le module",
                        expected_outputs=["identity_model.py"]),
            MissionNode(node_id="n2", title="Écrire les tests",
                        expected_outputs=["test_identity_model.py"]),
        ]
        from backend.mission import routes
        monkeypatch.setitem(routes._missions, mission.mission_id, mission)  # noqa: SLF001
        return mission

    def test_une_tache_voit_ses_propres_fichiers(self, monkeypatch):
        mission = self._mission(monkeypatch)

        texte = _livrables_pour(_tache(mission.mission_id, "n2"))

        assert "test_identity_model.py" in texte

    def test_elle_voit_surtout_ceux_des_autres(self, monkeypatch):
        """L'incident exact : la tâche qui a écrit le second fichier de
        tests ignorait qu'un autre existait déjà."""
        mission = self._mission(monkeypatch)

        texte = _livrables_pour(_tache(mission.mission_id, "n2"))

        assert "identity_model.py" in texte
        assert "Écrire le module" in texte, (
            "savoir quelle tâche possède un fichier permet de le lire "
            "plutôt que d'en deviner le contenu")

    def test_le_texte_dit_de_lire_plutot_que_de_deviner(self, monkeypatch):
        """`User("user_001", "auth_uid_123")` contre un `__init__` qui
        exige un `email` : le fichier existait, il n'a pas été lu."""
        mission = self._mission(monkeypatch)

        texte = _livrables_pour(_tache(mission.mission_id, "n2"))

        assert "lis-les" in texte

    def test_sans_manifeste_aucune_section_n_est_ajoutee(self, monkeypatch):
        """Une section vide dirait « il n'y a rien à écrire », ce qui est
        faux — et le planificateur ne produit pas toujours de manifeste."""
        mission = Mission(title="m", objective="o")
        mission.nodes = [MissionNode(node_id="n1", title="Faire")]
        from backend.mission import routes
        monkeypatch.setitem(routes._missions, mission.mission_id, mission)  # noqa: SLF001

        assert _livrables_pour(_tache(mission.mission_id, "n1")) is None

    def test_une_mission_inconnue_ne_leve_pas(self):
        assert _livrables_pour(_tache("inexistante", "n1")) is None


class TestLaVerificationDuManifeste:
    """Sans cette moitié-là, le manifeste serait une intention : le modèle
    lirait « ton fichier est X », en écrirait un autre, et personne ne le
    saurait."""

    def _mission_avec(self, *livrables: str) -> Mission:
        mission = Mission(title="m", objective="o")
        mission.nodes = [MissionNode(node_id="n1", title="t",
                                     expected_outputs=list(livrables))]
        return mission

    def test_un_livrable_present_tient(self, tmp_path):
        (tmp_path / "identity_model.py").write_text("x = 1", encoding="utf-8")

        v = manifeste.verdict(self._mission_avec("identity_model.py"),
                              str(tmp_path))

        assert v["tenu"] is True
        assert v["manquants"] == []
        assert manifeste.contredit(v) is False

    def test_un_livrable_absent_est_nomme(self, tmp_path):
        v = manifeste.verdict(self._mission_avec("identity_model.py"),
                              str(tmp_path))

        assert v["tenu"] is False
        assert v["manquants"] == ["identity_model.py"]
        assert manifeste.contredit(v) is True

    def test_un_fichier_non_declare_n_est_pas_une_faute(self, tmp_path):
        """Une tâche qui écrit un `conftest.py` dont personne n'avait parlé
        fait probablement bien son travail. Le signaler fabriquerait un faux
        échec, et cinq des huit défauts de mesure de ce dépôt étaient des
        échecs imaginaires."""
        (tmp_path / "identity_model.py").write_text("x = 1", encoding="utf-8")
        (tmp_path / "conftest.py").write_text("", encoding="utf-8")

        v = manifeste.verdict(self._mission_avec("identity_model.py"),
                              str(tmp_path))

        assert v["tenu"] is True

    def test_sans_manifeste_on_ne_conclut_rien(self, tmp_path):
        """Ni succès ni échec : un troisième état."""
        v = manifeste.verdict(self._mission_avec(), str(tmp_path))

        assert v is None
        assert manifeste.contredit(v) is False

    def test_sans_workspace_on_ne_conclut_rien(self):
        assert manifeste.verdict(self._mission_avec("a.py"), None) is None


class TestLIntegrationDansLaVerification:
    def test_un_livrable_manquant_contredit_un_succes_annonce(self, tmp_path):
        from backend.mission.verification import snapshot, verify

        mission = Mission(title="m", objective="o")
        mission.nodes = [MissionNode(node_id="n1", title="t",
                                     expected_outputs=["promis.py"])]
        avant = snapshot(str(tmp_path))
        (tmp_path / "autre_chose.py").write_text("x = 1", encoding="utf-8")
        apres = snapshot(str(tmp_path))

        v = verify(mission.mission_id, True, str(tmp_path), avant, apres,
                   mission=mission)

        assert v.changes.touched_anything, "un fichier a bien été écrit"
        assert v.manifeste_manque is True
        assert v.contradicted is True, (
            "écrire six fichiers dont aucun n'est celui qu'on avait promis "
            "n'est pas avoir fait le travail")
        assert v.verified is False

    def test_sans_mission_le_comportement_ne_change_pas(self, tmp_path):
        """La signature a gagné un paramètre facultatif ; les appelants qui
        ne le passent pas doivent voir exactement ce qu'ils voyaient."""
        from backend.mission.verification import snapshot, verify

        avant = snapshot(str(tmp_path))
        (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
        apres = snapshot(str(tmp_path))

        v = verify("m", True, str(tmp_path), avant, apres)

        assert v.manifeste is None
        assert v.manifeste_manque is False
        assert v.verified is True

    def test_le_verdict_voyage_dans_le_rapport(self, tmp_path):
        from backend.mission.verification import snapshot, verify

        mission = Mission(title="m", objective="o")
        mission.nodes = [MissionNode(node_id="n1", title="t",
                                     expected_outputs=["promis.py"])]
        avant = snapshot(str(tmp_path))
        (tmp_path / "x.py").write_text("1", encoding="utf-8")
        apres = snapshot(str(tmp_path))

        rendu = verify(mission.mission_id, True, str(tmp_path), avant, apres,
                       mission=mission).as_dict()

        assert rendu["manifeste"]["manquants"] == ["promis.py"]
