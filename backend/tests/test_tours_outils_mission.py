"""Un nœud de mission n'est plus plafonné à la patience d'un chat (HOS-118).

`_MAX_TOOL_ROUNDS = 3` était écrit en dur dans `task_executor.py`, aligné
sur `agents/base_agent.py`. Le garde-fou est légitime — un modèle qui
redemande des outils sans jamais répondre ne doit pas bloquer une tâche —
mais l'échelle ne l'est pas : un tour de conversation tient en trois
échanges, une tâche qui lit des fichiers, en écrit, lance les tests et
corrige n'y tient pas. Au quatrième tour l'exécuteur coupait et forçait une
réponse *sans outils* : la tâche ne pouvait pas finir, elle rapportait ce
qu'elle avait pu.
"""
from __future__ import annotations

import pytest

from backend.execution.task_executor import _MAX_TOOL_ROUNDS, _tours_d_outils_max


class TestLePlafondVientDeLaConfiguration:
    def test_la_valeur_livree_depasse_largement_celle_du_chat(self):
        """Trois tours suffisent à un chat et pas à une tâche : si les deux
        redevenaient égales, ce serait que quelqu'un a réaligné le mauvais
        des deux."""
        assert _tours_d_outils_max() > _MAX_TOOL_ROUNDS

    def test_le_reglage_est_relu_a_chaque_appel(self, monkeypatch):
        """Relu et non figé à l'import : le plafond doit pouvoir changer
        sans redémarrage, comme le niveau d'autonomie."""
        from backend.core.config import get_settings

        monkeypatch.setenv("MISSION_MAX_TOOL_ROUNDS", "7")
        get_settings.cache_clear()
        try:
            assert _tours_d_outils_max() == 7
        finally:
            get_settings.cache_clear()

    def test_une_valeur_absurde_ne_supprime_pas_le_garde_fou(self, monkeypatch):
        """Zéro ou négatif rendrait la boucle vide : le nœud n'appellerait
        aucun outil et rapporterait quand même. Un plafond mal réglé doit
        dégrader, pas désarmer."""
        from backend.core.config import get_settings

        monkeypatch.setenv("MISSION_MAX_TOOL_ROUNDS", "0")
        get_settings.cache_clear()
        try:
            assert _tours_d_outils_max() >= 1
        finally:
            get_settings.cache_clear()

    def test_une_configuration_illisible_retombe_sur_le_repli(self, monkeypatch):
        """Un réglage cassé ne doit pas empêcher une mission de tourner —
        elle repart simplement sur l'ancien plafond."""
        import backend.core.config as config

        def _explose():
            raise RuntimeError("configuration illisible")

        monkeypatch.setattr(config, "get_settings", _explose)
        assert _tours_d_outils_max() == _MAX_TOOL_ROUNDS


class TestLeChatGardeLeSien:
    def test_le_plafond_du_chat_reste_a_trois(self):
        """Le relever aussi ferait payer à chaque tour de conversation la
        latence d'une tâche de fond — ce n'est pas le même besoin."""
        from backend.agents.base_agent import _MAX_TOOL_ROUNDS as chat_rounds

        assert chat_rounds == 3
