"""La boucle se ferme aussi du côté autonome (HOS-118).

`GraphExecutor` produisait déjà le brief de reprise quand le disque
contredit un succès annoncé. Mais `_run_retry_if_suggested` n'existait que
dans `mission/routes.py` : l'orchestrateur autonome a sa propre boucle
d'exécution et ne l'appelait pas. La vérification tournait, la décision
était prise, le brief était écrit dans `metadata["retry_brief"]` — et
personne ne le lisait.

C'est le même défaut que HOS-099 avait laissé pour les missions et que
HOS-100 a corrigé : produire la décision et s'arrêter avant d'agir.
"""
from __future__ import annotations

import pytest

from backend.mission.mission_models import (
    Mission, MissionNode, MissionStatus, NodeStatus,
)
from backend.mission.retry_policy import preparer_reprise


class _Executeur:
    """Un GraphExecutor minimal : on n'observe que ce que la reprise lui
    demande, pas ce qu'il exécute."""

    def __init__(self, redemarrage: bool = True):
        self.redemarrage = redemarrage
        self.graphes_construits = 0
        self.demarrages = 0

    def build_graph(self, mission, nodes, edges):
        self.graphes_construits += 1
        return []

    def start_mission(self, mission) -> bool:
        self.demarrages += 1
        if self.redemarrage:
            mission.status = MissionStatus.RUNNING
        return self.redemarrage


def _mission_contredite() -> Mission:
    mission = Mission(title="t", description="d", objective="écrire RAPPORT.md")
    mission.nodes = [
        MissionNode(node_id="n1", title="écrire"),
        MissionNode(node_id="n2", title="vérifier"),
    ]
    for n in mission.nodes:
        n.status = NodeStatus.COMPLETED
        n.result_summary = "j'ai écrit le fichier"
    mission.status = MissionStatus.COMPLETED
    mission.metadata["retry_brief"] = "refais-le, le disque est intact"
    return mission


class TestLaPreparation:
    def test_sans_brief_il_n_y_a_rien_a_rejouer(self):
        mission = _mission_contredite()
        del mission.metadata["retry_brief"]

        assert preparer_reprise(mission, executor=_Executeur()) is False

    def test_le_brief_devient_l_objectif(self):
        """C'est par là qu'il atteint l'agent — `_mission_brief_for`
        transmet déjà `mission.objective`, donc chaque nœud de la reprise
        voit la preuve, pas seulement le premier."""
        mission = _mission_contredite()

        preparer_reprise(mission, executor=_Executeur())

        assert mission.objective == "refais-le, le disque est intact"

    def test_l_objectif_d_origine_est_conserve(self):
        mission = _mission_contredite()

        preparer_reprise(mission, executor=_Executeur())

        assert mission.metadata["original_objective"] == "écrire RAPPORT.md"

    def test_le_brief_est_consomme_une_seule_fois(self):
        """Sinon la mission rejouerait indéfiniment sur la même preuve."""
        mission = _mission_contredite()
        executeur = _Executeur()

        assert preparer_reprise(mission, executor=executeur) is True
        assert preparer_reprise(mission, executor=executeur) is False

    def test_tous_les_noeuds_repartent(self):
        """Une reprise par nœud serait fausse : la mission n'a rien produit,
        et un nœud « réussi » qui n'a rien écrit est précisément ce qu'on
        rejoue."""
        mission = _mission_contredite()

        preparer_reprise(mission, executor=_Executeur())

        assert all(n.status == NodeStatus.PENDING for n in mission.nodes)
        assert all(n.result_summary == "" for n in mission.nodes)

    def test_les_tentatives_sont_comptees(self):
        mission = _mission_contredite()

        preparer_reprise(mission, executor=_Executeur())

        assert mission.metadata["attempts"] == 2

    def test_un_redemarrage_refuse_n_annonce_pas_une_reprise(self):
        """Rendre True sans que la mission ait redémarré ferait marcher un
        graphe qui n'est pas prêt."""
        mission = _mission_contredite()

        assert preparer_reprise(mission, executor=_Executeur(redemarrage=False)) is False


class TestLesDeuxCheminsPartagentLaMemePreparation:
    def test_la_route_des_missions_delegue(self):
        """Elle ne réimplémente plus la préparation — deux copies auraient
        divergé, et c'est la copie manquante côté autonome qui a créé ce
        défaut."""
        import inspect

        from backend.mission import routes

        source = inspect.getsource(routes._run_retry_if_suggested)  # noqa: SLF001
        assert "preparer_reprise" in source
        assert "retry_brief" not in source.replace("preparer_reprise", "")

    def test_l_orchestrateur_autonome_la_consomme_aussi(self):
        import inspect

        from backend.autonomous import autonomous_orchestrator

        source = inspect.getsource(autonomous_orchestrator.AutonomousOrchestrator)
        assert "preparer_reprise" in source, (
            "le chemin autonome ne reprend toujours pas — le brief serait "
            "produit puis abandonné"
        )

    def test_les_deux_tentatives_marchent_le_meme_graphe(self):
        """L'orchestrateur réutilise `_marcher_le_graphe` plutôt que de
        réécrire la boucle : deux boucles auraient dérivé, l'une bornée par
        MAX_EXECUTION_PASSES et l'autre non."""
        import inspect

        from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator

        source = inspect.getsource(AutonomousOrchestrator._execute_via_dag)  # noqa: SLF001
        assert source.count("_marcher_le_graphe") == 2
