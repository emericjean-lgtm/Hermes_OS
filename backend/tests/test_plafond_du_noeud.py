"""Le filet de securite coupait avant le budget qu'il devait couvrir (HOS-152).

`STEP_TIMEOUT_S` porte ce commentaire depuis HOS-112 :

    Le budget d'un noeud appartient a l'executeur injecte — 900 s pour une
    boucle d'agent Hermes. Ce plafond est choisi bien au-dessus pour ne
    jamais couper un agent qui travaille reellement.

1200 contre 900 : l'invariant tenait tant que les deux valeurs etaient
figees. Le budget du tour est devenu reglable (HOS-151) et a ete porte a
3600 s pour un modele dix fois plus lent ; le plafond, lui, est reste a
1200. **Le rapport s'est inverse.**

Mesure du 2026-08-22 :

    mission b96305fe : 2 noeud(s) n'ont pas rendu la main en 1200 s
    — Tests unitaires du modele d'identite, Documentation de la section

Les deux noeuds travaillaient. L'un attendait une compression de contexte
qui a dure **8 min 41** — 116 messages ramenes a 93 — un temps qui s'ajoute
au travail sans lui appartenir.

Aucune relecture n'aurait montre le defaut : les deux constantes vivent dans
des fichiers differents et ne se citent que par commentaire.
"""
from __future__ import annotations

import pytest

from backend.execution.task_executor import budget_du_tour
from backend.mission.graph_executor import (
    MARGE_SUR_LE_BUDGET,
    STEP_TIMEOUT_S,
    GraphExecutor,
    plafond_du_noeud,
)


class TestLInvariant:
    """Le plafond doit toujours depasser le budget, quel que soit ce
    dernier. C'est la seule chose que ce module promet."""

    @pytest.mark.parametrize("budget", ["", "1800", "3600", "7200", "36000"])
    def test_le_plafond_depasse_toujours_le_budget(self, monkeypatch, budget):
        if budget:
            monkeypatch.setenv("HERMES_AGENT_TIMEOUT_S", budget)
        else:
            monkeypatch.delenv("HERMES_AGENT_TIMEOUT_S", raising=False)

        assert plafond_du_noeud() > budget_du_tour()

    def test_le_cas_exact_de_l_incident(self, monkeypatch):
        """3600 s de budget contre 1200 s de plafond : le filet coupait
        avant."""
        monkeypatch.setenv("HERMES_AGENT_TIMEOUT_S", "3600")

        assert plafond_du_noeud() == pytest.approx(4800.0)


class TestLeDefautNeBougePas:
    def test_sans_reglage_le_plafond_reste_celui_d_avant(self, monkeypatch):
        """900 s de budget, 1200 s de plafond : le rapport historique, qui
        n'avait pas de defaut."""
        monkeypatch.delenv("HERMES_AGENT_TIMEOUT_S", raising=False)

        assert plafond_du_noeud() == STEP_TIMEOUT_S == 1200.0

    def test_la_marge_est_celle_des_deux_constantes_figees(self):
        assert MARGE_SUR_LE_BUDGET == pytest.approx(1200.0 / 900.0)


class TestLaResolutionALaConstruction:
    def test_un_executeur_lit_le_reglage_courant(self, monkeypatch):
        """Un defaut de parametre serait evalue a l'import et figerait la
        valeur — le defaut meme qu'on corrige, reintroduit par la porte de
        service."""
        monkeypatch.setenv("HERMES_AGENT_TIMEOUT_S", "3600")

        executeur = GraphExecutor(execute_node=lambda n: None)

        assert executeur._step_timeout_s == pytest.approx(4800.0)

    def test_une_valeur_explicite_est_respectee(self, monkeypatch):
        monkeypatch.setenv("HERMES_AGENT_TIMEOUT_S", "3600")

        executeur = GraphExecutor(execute_node=lambda n: None,
                                  step_timeout_s=60.0)

        assert executeur._step_timeout_s == 60.0
