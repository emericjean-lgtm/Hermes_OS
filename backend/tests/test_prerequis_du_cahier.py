"""Une nuit en mode jetable rend un bilan de meme forme qu'une nuit reussie.

`derouler_cahier.py` construit ses services **en memoire** ; il ne sert
aucun HTTP. Or l'agent rappelle Hermes OS par MCP pour obtenir ses outils :
sans backend qui ecoute, il demarre avec zero outil et chaque tache retombe
sur un agent jete apres usage.

Une nuit entiere dans cet etat ne produit pas une erreur. Elle produit un
bilan **indiscernable** d'une nuit ou la continuite a joue, avec des
sections qui ont chacune redecouvert le workspace. C'est la classe de defaut
que ce depot traque depuis HOS-128 — « une mission qui n'a pas eu lieu n'est
pas une mission sans mesure ».

D'ou le refus de partir : soit la nuit tourne avec le harnais, soit elle ne
tourne pas ; jamais une nuit qui croit l'avoir et ne l'a pas.
"""
from __future__ import annotations

import backend.ral.adapters.prerequis_harnais as pre
from scripts.derouler_cahier import verifier_le_harnais


def _etat(pret: bool):
    return pre.Prerequis(agent_installe=True, mcp_declare=True,
                         backend_joignable=pret)


class TestLeRefusDePartir:
    def test_sans_backend_le_cahier_ne_part_pas(self, monkeypatch, capsys):
        monkeypatch.setattr(pre, "verifier", lambda **_: _etat(False))

        assert verifier_le_harnais(accepte_le_mode_jetable=False) is False

        sortie = capsys.readouterr().out
        # La commande exacte, pas seulement le diagnostic : a 23 h, un
        # message qui dit ce qui manque sans dire quoi faire coute la nuit.
        assert "uvicorn backend.main:app" in sortie
        assert "--sans-harnais" in sortie

    def test_le_mode_degrade_reste_possible_mais_explicite(self, monkeypatch,
                                                           capsys):
        """Comparer les deux modes est legitime — il faut juste l'ecrire."""
        monkeypatch.setattr(pre, "verifier", lambda **_: _etat(False))

        assert verifier_le_harnais(accepte_le_mode_jetable=True) is True
        assert "sans memoire" in capsys.readouterr().out

    def test_avec_le_harnais_on_part_sans_bruit(self, monkeypatch, capsys):
        monkeypatch.setattr(pre, "verifier", lambda **_: _etat(True))

        assert verifier_le_harnais(accepte_le_mode_jetable=False) is True
        assert "INDISPONIBLE" not in capsys.readouterr().out
