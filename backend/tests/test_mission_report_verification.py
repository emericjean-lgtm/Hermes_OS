"""Le verdict du disque survit à la mission qui l'a produit (HOS-116).

`_verify_workspace` compare le workspace avant et après (HOS-092), et son
résultat n'existait que sous forme d'événement : publié une fois à la
complétion, perdu pour quiconque n'écoutait pas à cet instant. Or
« rapporté réussi » contre « vérifié sur disque » est la distinction que
ce projet existe pour tenir — et on veut la consulter *après coup*, ce qui
est exactement ce qu'un événement ne permet pas.
"""
from __future__ import annotations

from backend.mission.mission_models import (
    Mission, MissionNode, MissionStatus, NodeStatus, build_mission_report,
)


def _mission_terminee() -> Mission:
    mission = Mission(title="t", description="d", objective="o")
    mission.nodes = [MissionNode(node_id="n1", title="faire")]
    mission.nodes[0].status = NodeStatus.COMPLETED
    mission.status = MissionStatus.COMPLETED
    return mission


class TestLeRapportPorteLeVerdict:
    def test_une_verification_enregistree_se_retrouve_dans_le_rapport(self):
        mission = _mission_terminee()
        mission.metadata["verification"] = {
            "contradicted": False, "files_changed": 2, "workspace": "C:/ws",
        }

        rapport = build_mission_report(mission)

        assert rapport.verification == {
            "contradicted": False, "files_changed": 2, "workspace": "C:/ws",
        }

    def test_une_contradiction_est_rendue_telle_quelle(self):
        """Le cas qui a motivé HOS-092 : succès annoncé, workspace intact.
        Le rapport doit le porter sans l'adoucir."""
        mission = _mission_terminee()
        mission.metadata["verification"] = {"contradicted": True, "files_changed": 0}

        rapport = build_mission_report(mission)

        assert rapport.success is True          # la mission se croit réussie
        assert rapport.verification["contradicted"] is True   # le disque dit non

    def test_sans_verification_le_champ_est_None_et_non_un_succes(self):
        """`None` veut dire « pas de vérification », jamais « vérification
        réussie ». Une mission sans workspace lié n'a rien à comparer, et
        afficher un succès là où il n'y en a pas eu serait précisément le
        faux positif que tout ceci traque."""
        rapport = build_mission_report(_mission_terminee())

        assert rapport.verification is None

    def test_le_verdict_traverse_la_serialisation(self):
        """C'est `to_dict()` que la route rend — un champ présent sur le
        dataclass mais absent du JSON n'aurait servi à personne."""
        mission = _mission_terminee()
        mission.metadata["verification"] = {"contradicted": True}

        rendu = build_mission_report(mission).to_dict()

        assert rendu["verification"] == {"contradicted": True}


class TestLExecuteurEnregistre:
    def test_le_verdict_est_pose_sur_la_mission_pas_seulement_publie(self):
        """Sans cela il ne vivait que le temps d'un événement."""
        from backend.mission.graph_executor import GraphExecutor

        executeur = GraphExecutor(execute_node=lambda n: True)
        mission = Mission(title="t", description="d", objective="o")
        mission.nodes = [MissionNode(node_id="n1", title="faire")]
        executeur.build_graph(mission, mission.nodes, [])
        mission.status = MissionStatus.READY
        executeur.start_mission(mission)

        executeur._verify_workspace = lambda m, ok: {  # noqa: SLF001
            "contradicted": True, "files_changed": 0,
        }
        executeur.execute_step(mission)

        assert mission.metadata.get("verification") == {
            "contradicted": True, "files_changed": 0,
        }
