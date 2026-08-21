"""Le terminal de l'agent ne demande aucune permission (HOS-141).

L'incident, mesuré le 2026-08-21. La frontière du client ACP a refusé
**trois fois** une écriture hors du workspace. L'agent a alors répondu, mot
pour mot :

    The write was blocked by the ACP client.
    Let me try using the terminal directly.

et le fichier est apparu hors du workspace. `session/request_permission` ne
porte que sur les éditions de fichiers (`kind: "edit"`) ; le terminal, lui,
exécute sans rien demander. Refuser côté client détournait donc l'agent vers
un chemin non gardé, sans rien empêcher.

Un garde-fou existait pourtant : un hook `pre_tool_call` déclaré dans la
configuration de l'agent. **Il pointait vers `C:/Users/emeri/hermes-ollama`,
dossier disparu au renommage du projet.** Il ne s'exécutait plus depuis des
mois, et rien ne le disait — la même famille de défaut que les recettes de
modèles perdues (HOS-140). Le script vit désormais dans le dépôt.

## Ce que ces tests garantissent, et ce qu'ils ne garantissent pas

Ils vérifient que le garde attrape les **erreurs franches** : un chemin
absolu qui désigne un ailleurs. C'est le cas réel — un modèle qui interprète
mal « le répertoire courant ».

Ils ne prétendent pas que le garde arrête quelqu'un qui cherche à sortir :
une variable shell, un `$(...)`, un `cd` préalable ne se lisent pas dans une
chaîne sans exécuter un interpréteur. La seule contrainte réelle est un
backend d'exécution isolé (`terminal.backend: docker`).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_CHEMIN = Path("config/hooks/garde_workspace.py")


def _charger():
    """Le hook n'est pas un module du paquet : il s'exécute seul, appelé par
    l'agent avec son propre interpréteur."""
    spec = importlib.util.spec_from_file_location("garde_workspace", _CHEMIN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["garde_workspace"] = module
    spec.loader.exec_module(module)
    return module


garde = _charger()

WS = r"C:\Users\emeri\projet"


class TestCeQuiEstRefuse:
    def test_le_chemin_exact_qui_s_est_echappe(self):
        """`C:\\Users\\emeri\\note_fuite.txt` depuis le terminal — la
        commande qui a réellement produit un fichier hors workspace."""
        verdict = garde.verdict(
            {"tool_name": "terminal",
             "tool_input": {"command": r"echo EVADE > C:\Users\emeri\note_fuite.txt"}},
            WS)

        assert verdict is not None
        assert verdict["action"] == "block"
        assert "note_fuite.txt" in verdict["message"]

    @pytest.mark.parametrize("commande", [
        "cat /c/Users/emeri/secret.txt",          # graphie Git Bash
        r"copy x \\serveur\partage\y",            # partage réseau
        "python C:/Windows/System32/x.py",        # dossier système
    ])
    def test_les_autres_graphies_aussi(self, commande):
        assert garde.verdict({"tool_name": "terminal",
                              "tool_input": {"command": commande}}, WS) is not None

    def test_tous_les_arguments_sont_regardes(self):
        """Les outils d'exécution n'ont pas tous un paramètre `command` ;
        n'en surveiller qu'un laisserait les autres passer en silence."""
        assert garde.verdict(
            {"tool_name": "execute_code",
             "tool_input": {"code": "open(r'C:/Users/emeri/x.txt','w')"}}, WS) is not None


class TestCeQuiPasse:
    """Un faux refus coûte autant qu'une fuite — à ceci près qu'il se voit.
    Le garde a déjà, ailleurs, coûté trois tentatives à une écriture
    parfaitement légitime."""

    @pytest.mark.parametrize("commande", [
        "echo ok > note.txt",                       # relatif
        "pytest -q",                                # aucun chemin
        r"type C:\Users\emeri\projet\src\a.py",     # dans le workspace
        "ls src/",
    ])
    def test_le_travail_legitime_n_est_pas_bloque(self, commande):
        assert garde.verdict({"tool_name": "terminal",
                              "tool_input": {"command": commande}}, WS) is None

    def test_la_casse_ne_fait_pas_une_evasion(self):
        """Windows est insensible à la casse. Une comparaison exacte
        refuserait le workspace lui-même écrit autrement — défaut déjà payé
        cinq fois côté Hermes OS (HOS-129 à 133)."""
        assert garde.verdict(
            {"tool_name": "terminal",
             "tool_input": {"command": r"echo x > c:\users\EMERI\Projet\a.txt"}},
            WS) is None

    def test_un_outil_non_surveille_passe(self):
        """Les éditions de fichiers ont déjà leur frontière côté client ACP.
        Les refuser deux fois n'ajoute rien et double le risque de faux
        refus."""
        assert garde.verdict(
            {"tool_name": "write_file",
             "tool_input": {"path": r"C:\ailleurs\x.txt"}}, WS) is None


class TestQuandLeGardeSeTait:
    def test_sans_workspace_il_ne_bloque_rien(self):
        """Sans référence, tout chemin est également suspect : bloquer au
        hasard casserait le travail légitime sans rien protéger."""
        assert garde.verdict(
            {"tool_name": "terminal",
             "tool_input": {"command": r"echo x > C:\ailleurs\y.txt"}}, "") is None

    def test_une_charge_malformee_ne_bloque_pas(self):
        """Un garde-fou qui plante ne doit pas arrêter l'agent : refuser par
        défaut transformerait la moindre anomalie de plomberie en panne
        totale des missions."""
        for charge in ({}, {"tool_name": "terminal"},
                       {"tool_name": "terminal", "tool_input": "pas un dict"}):
            assert garde.verdict(charge, WS) is None


class TestLaTrameReelle:
    """Les premiers tests de ce fichier construisaient la charge avec `args`.

    Ils passaient tous — et ne mesuraient rien : Hermes Agent serialise la
    charge du hook au format Claude-Code, ou les arguments arrivent sous
    **`tool_input`**. Le garde lisait `args`, obtenait `None`, et autorisait
    tout en silence. Mesure du 2026-08-21, dans le journal du garde :

        VU outil='terminal' racine='C:\...\fuite_j90xq1y6' args=None

    Les tests mesuraient l'idee qu'on se faisait du contrat, pas le contrat.
    Seizieme defaut d'instrument de ce projet, et le premier ou un test vert
    couvrait une protection inerte.
    """

    #: La trame exacte que `_serialize_payload` construit — cles comprises.
    def _trame(self, commande: str) -> dict:
        return {
            "hook_event_name": "pre_tool_call",
            "tool_name": "terminal",
            "tool_input": {"command": commande},
            "session_id": "s-1",
            "cwd": "",
            "extra": {},
        }

    def test_la_trame_de_l_agent_est_comprise(self):
        verdict = garde.verdict(
            self._trame(r"echo EVADE > C:\Users\emeri\note_fuite.txt"), WS)

        assert verdict is not None and verdict["action"] == "block"

    def test_le_travail_legitime_passe_sur_la_meme_trame(self):
        assert garde.verdict(self._trame("pytest -q"), WS) is None

    def test_l_ancien_format_reste_accepte(self):
        """`args` est le nom documente cote plugin Python. Le refuser
        casserait un appelant legitime pour rien."""
        assert garde.verdict(
            {"tool_name": "terminal",
             "args": {"command": r"echo x > C:\ailleurs\y.txt"}}, WS) is not None


class TestUnWorkspaceAvecDesEspaces:
    r"""Le faux refus qui a bloque une nuit (HOS-142).

    Une ligne de commande n'offre aucun moyen fiable de delimiter un chemin
    qui contient des espaces. La premiere version de la regex s'arretait
    donc au premier espace : le dossier confie
    « C:\Users\emeri\Skill360 Nuit HOS-141 » etait tronque a
    « C:\Users\emeri\Skill360 », qui n'est evidemment pas sous le
    workspace — donc refuse.

    Mesure, en plein deroulement : deux refus sur des commandes
    parfaitement legitimes, dans le dossier confie, et la section notee
    « contredite, aucun fichier ecrit ». Le garde bloquait le travail qu'il
    devait proteger.

    On ote desormais les mentions du workspace avant d'analyser le reste.
    Ce qui subsiste ne peut plus etre un chemin du workspace, et les vraies
    sorties restent entieres — y compris celle qui compte le plus ici : le
    dossier **voisin**, dont le nom partage le meme premier mot.
    """

    ESPACES = r"C:\Users\emeri\Skill360 Nuit HOS-141"

    def _dit_oui(self, commande: str) -> bool:
        return garde.verdict({"tool_name": "terminal",
                              "tool_input": {"command": commande}},
                             self.ESPACES) is None

    @pytest.mark.parametrize("commande", [
        r'cd "C:\Users\emeri\Skill360 Nuit HOS-141\tests" && pytest',
        r'cat "C:/Users/emeri/Skill360 Nuit HOS-141/AGENT.md"',
        r'ls "/c/Users/emeri/Skill360 Nuit HOS-141"',
        r'cd "c:\users\EMERI\skill360 nuit hos-141"',
    ])
    def test_le_workspace_lui_meme_passe(self, commande):
        assert self._dit_oui(commande), (
            "un chemin du dossier confie ne doit jamais etre refuse")

    def test_le_dossier_voisin_reste_refuse(self):
        """« Skill360 Industry » partage son premier mot avec le workspace.
        Retirer les mentions du workspace ne doit pas le blanchir — sans
        quoi le correctif du faux refus ouvrirait une vraie fuite."""
        assert not self._dit_oui(
            r'cat "C:\Users\emeri\Skill360 Industry\PROJECT_SPEC.md"')

    def test_un_ailleurs_franc_reste_refuse(self):
        assert not self._dit_oui(r"echo x > C:\Users\emeri\dehors.txt")
