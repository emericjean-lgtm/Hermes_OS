"""La boucle d'outils a besoin de son propre budget (HOS-121).

L'incident, mesuré en relançant l'essai Skills360 après les correctifs de
HOS-121 : la mission a tourné **878 s et terminé 1/7 tâches**, zéro fichier.
Un nœud est tombé sur

    runtime 'default' timed out after 180s

et les cinq suivants ont été bloqués en cascade. Le run précédent, sur le
même cahier, faisait 7/7.

La cause n'est pas dans la boucle : c'est de l'arithmétique.
`_chat_with_tools_for` enchaîne jusqu'à `mission_max_tool_rounds` — 12 —
inférences, chacune suivie d'une lecture ou d'une écriture. Les 180 s de
`_timeout_s` couvraient la boucle **entière**, soit 15 s par tour, sur un
matériel mesuré entre 13 et 89 tok/s.

Le plus instructif : cette leçon avait **déjà** été apprise. Six lignes
au-dessus de `_HERMES_AGENT_TIMEOUT_S = 900` on lit « a trivial single-file
task already takes 37-57s, so a real multi-step task routinely exceeded 180s
[...] producing a mission that ran for 12 minutes and completed 0/5 tasks ».
Le correctif n'avait jamais été appliqué au chemin frère, qui fait pourtant
la même chose : plusieurs tours sur du matériel local.

Pourquoi le premier run passait, lui : sans contexte amont — HOS-105 était
inerte, voir `test_task_context_continuity` — le modèle n'allait rien lire
et écrivait son module directement, en peu de tours. La correction du
contexte l'a poussé à faire le travail correctement, et le travail correct
ne tenait pas dans le budget.
"""
from __future__ import annotations

from backend.execution.task_executor import RealTaskExecutor


def _executeur() -> RealTaskExecutor:
    return RealTaskExecutor(timeout_s=180.0, agentic_timeout_s=900.0)


class TestLesTroisChosesDerriereUnMemeAppel:
    def test_une_completion_simple_garde_un_budget_serre(self):
        """Un aller-retour qui dépasse trois minutes, c'est un modèle en
        peine — relâcher ce plafond-là masquerait un vrai problème."""
        assert _executeur()._budget_d_appel("default", False) == 180.0

    def test_la_boucle_d_outils_a_le_budget_d_une_boucle(self):
        """L'incident exact : c'est ce cas qui recevait 180 s."""
        assert _executeur()._budget_d_appel("default", True) == 900.0

    def test_hermes_agent_garde_le_sien(self):
        assert _executeur()._budget_d_appel("hermes-agent", False) == 900.0

    def test_les_deux_boucles_partagent_le_meme_budget(self):
        """Elles font la même chose — plusieurs tours sur du matériel
        local — et deux constantes divergeraient au premier réglage."""
        executeur = _executeur()

        assert (executeur._budget_d_appel("hermes-agent", False)
                == executeur._budget_d_appel("default", True))


class TestLArithmetiqueQuiRendLIncidentEvident:
    def test_le_budget_couvre_au_moins_trente_secondes_par_tour(self):
        """Le garde-fou contre une régression silencieuse : si quelqu'un
        remonte `mission_max_tool_rounds` sans toucher au budget, la boucle
        se remet à mourir en plein milieu — et ça ressemblera à un modèle
        lent, pas à un plafond mal réglé.

        30 s par tour n'est pas une mesure : c'est le plancher en dessous
        duquel l'arithmétique est déjà perdue. Une tâche triviale à un seul
        fichier prend déjà 37-57 s d'après le commentaire de
        `_HERMES_AGENT_TIMEOUT_S`.
        """
        from backend.execution.task_executor import _tours_d_outils_max

        budget = _executeur()._budget_d_appel("default", True)

        assert budget >= 30.0 * _tours_d_outils_max(), (
            f"{_tours_d_outils_max()} tours pour {budget:.0f}s, soit "
            f"{budget / _tours_d_outils_max():.1f}s par inférence — c'est le "
            f"réglage qui a produit 1/7 tâches sur l'essai Skills360")


class TestLeMessageDErreurNeMentPas:
    def test_il_annonce_le_budget_reellement_applique(self):
        """Il annonçait `_timeout_s` quel que soit le budget réel : un
        « timed out after 180s » sur une boucle qui en avait eu 900 envoie
        droit sur la mauvaise constante, et c'est trente minutes perdues."""
        import inspect

        source = inspect.getsource(RealTaskExecutor.execute)

        assert "_budget_d_appel(runtime_id, boucle_d_outils)" in source
        assert 'timed out after {self._timeout_s' not in source
