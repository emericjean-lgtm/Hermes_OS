"""Le budget d'un tour doit suivre la vitesse du modele (HOS-151).

Le meme defaut, une seconde fois, avec un modele dix fois plus lent.

Mesure du 2026-08-22 : une campagne confiant le code a Qwen3.8-27B
(8,7 tok/s) contre gpt-oss-20b (92,7) a rendu **18 taches « executees » en
2 secondes cumulees**. Un chiffre absurde — et c'est lui qui a mis sur la
piste, comme le `0 s par tentative` d'un HTTP 400 jamais regarde.

Le journal de l'agent disait la verite :

    API call #2: model=qwen38-27b-64k ... latency=198.8s
    harnais : tour non abouti ... TimeoutError

Le modele travaillait. C'est le **tour** qui expirait : plusieurs appels a
200 s chacun, plus le raisonnement et les outils, ne tiennent pas dans les
900 s prevus. Exactement ce que raconte le commentaire de
`_HERMES_AGENT_TIMEOUT_S` — « 180 s dimensionnes pour un seul appel » —
reproduit a l'echelle d'un 27 Md qui deborde de 20 % sur CPU.

Le budget n'est **pas** augmente par defaut : un tour qui n'aboutit pas en
quinze minutes sur un modele rapide est un blocage, et l'allonger le
rendrait invisible.
"""
from __future__ import annotations

import pytest

from backend.execution.task_executor import (
    _HERMES_AGENT_TIMEOUT_S,
    RealTaskExecutor,
    budget_du_tour,
)


class TestLeDefaut:
    def test_il_ne_bouge_pas(self, monkeypatch):
        """Allonger le budget pour tout le monde masquerait les vrais
        blocages — celui que ce budget existe pour reveler."""
        monkeypatch.delenv("HERMES_AGENT_TIMEOUT_S", raising=False)

        assert budget_du_tour() == _HERMES_AGENT_TIMEOUT_S == 900.0


class TestQuandLOperateurTranche:
    def test_sa_valeur_est_retenue(self, monkeypatch):
        monkeypatch.setenv("HERMES_AGENT_TIMEOUT_S", "3600")

        assert budget_du_tour() == 3600.0

    def test_l_executeur_la_lit_a_la_construction(self, monkeypatch):
        """Lue a l'import, une variable posee ensuite resterait sans effet
        — et le reglage paraitrait pris en compte sans l'etre."""
        monkeypatch.setenv("HERMES_AGENT_TIMEOUT_S", "2400")

        executeur = RealTaskExecutor(chat=lambda **_: None)

        assert executeur._agentic_timeout_s == 2400.0

    def test_un_argument_explicite_prime(self, monkeypatch):
        """Un appelant qui passe une valeur sait ce qu'il fait ; la
        variable ne doit pas l'ecraser."""
        monkeypatch.setenv("HERMES_AGENT_TIMEOUT_S", "3600")

        executeur = RealTaskExecutor(chat=lambda **_: None,
                                     agentic_timeout_s=120.0)

        assert executeur._agentic_timeout_s == 120.0


class TestLesValeursAbsurdes:
    """Un budget nul ferait echouer chaque tour instantanement, ce qui
    ressemblerait a un modele incapable — le faux echec que ce depot a deja
    paye six fois."""

    @pytest.mark.parametrize("valeur", ["0", "-1", "abc", "", "   "])
    def test_elles_sont_ignorees(self, monkeypatch, valeur):
        monkeypatch.setenv("HERMES_AGENT_TIMEOUT_S", valeur)

        assert budget_du_tour() == _HERMES_AGENT_TIMEOUT_S

    def test_le_refus_est_dit(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("HERMES_AGENT_TIMEOUT_S", "0")

        with caplog.at_level(logging.WARNING):
            budget_du_tour()

        assert "budget nul" in caplog.text
