"""Un non-choix de runtime ne doit pas contourner Hermes Agent (HOS-142).

L'incident, mesure le 2026-08-21 pendant un vrai deroulement de cahier.

`agent_coordinator._select_runtime` rend litteralement `"default"` quand son
registre de runtimes est vide — et il l'etait, l'avertissement le disait au
demarrage :

    registries still empty after seeding: runtimes

`execute()` ne reconnaissait que la chaine exacte `"hermes-agent"`. Avec
`"default"`, il tombait sur `_chat_with_tools_for`, **sa propre boucle
d'outils**. Une nuit entiere allait se derouler sans Hermes Agent, ni en
session ni en mode jetable : le harnais annoncait `pret`, aucun processus
d'agent n'existait, et des fichiers etaient pourtant crees — par Hermes OS
lui-meme.

C'est la meme famille que `HERMES_AGENT_BYPASS_DETECTED`, par une autre
porte. La premiere fois, la boucle d'outils **ecrasait** un agent
correctement selectionne. Ici, elle prend la place d'une selection qui n'a
jamais eu lieu — et le garde-fou existant ne la couvrait pas, parce qu'il
fournit toujours un `runtime_id` explicite.

Le seul signal etait un compte de processus a zero. Ni le journal du script,
ni le bilan, ni le rapport de mission ne l'auraient dit : les fichiers
apparaissaient, les sections etaient « faites ».
"""
from __future__ import annotations

import pytest

from backend.execution.task_executor import _NON_CHOISI, _runtime_demande


class TestUnNonChoixTombeSurLAgent:
    @pytest.mark.parametrize("brut", ["default", "auto", "", "  ", "None",
                                      "ANY", "Default"])
    def test_les_valeurs_qui_ne_choisissent_rien(self, brut):
        assert _runtime_demande(brut) == "hermes-agent"

    def test_le_cas_exact_de_l_incident(self):
        """`_select_runtime` rend `"default"` sur registre vide. C'est cette
        chaine-la qui a fait contourner l'agent."""
        assert _runtime_demande("default") == "hermes-agent"


class TestUnChoixExpliciteEstRespecte:
    """Forcer Hermes Agent partout casserait le runtime local explicite, qui
    n'a pas d'agent a lui et a besoin de la boucle d'outils de Hermes OS."""

    @pytest.mark.parametrize("brut", ["openrouter", "hermes-ollama",
                                      "hermes-agent", "stub"])
    def test_il_passe_intact(self, brut):
        assert _runtime_demande(brut) == brut

    def test_les_espaces_ne_font_pas_un_autre_runtime(self):
        assert _runtime_demande("  openrouter  ") == "openrouter"


class TestLaListeDesNonChoix:
    def test_default_en_fait_partie(self):
        """La valeur exacte que rend `agent_coordinator._select_runtime`
        quand il n'a aucun runtime enregistre. Si elle disparaissait de
        cette liste, l'incident reviendrait a l'identique."""
        assert "default" in _NON_CHOISI

    def test_hermes_agent_n_en_fait_pas_partie(self):
        """Sinon la comparaison deviendrait circulaire et le test ci-dessus
        passerait pour de mauvaises raisons."""
        assert "hermes-agent" not in _NON_CHOISI
