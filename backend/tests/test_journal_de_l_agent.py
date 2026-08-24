"""Une seule ligne de l'agent sur quinze heures de campagne (HOS-157).

La sortie d'erreur de Hermes Agent partait dans un `deque` borne et un
`logger.debug` que personne n'active. Mesure du 2026-08-24 : **une ligne**
de l'agent dans tout le journal d'une campagne de quinze heures.

Consequence : impossible de savoir si l'agent avait consulte une
competence, quel outil avait ecrit un fichier, ou pourquoi un tour
n'aboutissait pas. Trois diagnostics de cette nuit-la ont du se faire par
deduction sur des traces indirectes, et l'un d'eux etait faux.
"""
from __future__ import annotations

from pathlib import Path

import backend.ral.adapters.hermes_agent_acp as acp


class _Session:
    def __init__(self, chemin) -> None:
        self.journal_fichier = chemin


def test_le_journal_atterrit_a_cote_de_ceux_de_la_campagne(tmp_path) -> None:
    """C'est la que quelqu'un qui enquete regarde deja."""
    chemin = acp._fichier_de_journal(str(tmp_path))

    assert chemin == tmp_path.resolve() / ".hermes" / "agent.log"
    assert chemin.parent.is_dir()


def test_les_lignes_sont_conservees_dans_l_ordre(tmp_path) -> None:
    session = _Session(acp._fichier_de_journal(str(tmp_path)))

    acp._archiver(session, "MCP: registered 16 tool(s)")
    acp._archiver(session, "tool skills_list completed")

    lu = (tmp_path / ".hermes" / "agent.log").read_text(encoding="utf-8")
    assert lu.splitlines() == ["MCP: registered 16 tool(s)",
                               "tool skills_list completed"]


def test_un_disque_plein_coute_un_diagnostic_pas_une_campagne(tmp_path) -> None:
    """Le fichier est un confort d'enquete, jamais une dependance.

    Et l'echec desarme l'archivage : reessayer a chaque ligne d'un disque
    plein transformerait une gene en ralentissement.
    """
    session = _Session(Path(tmp_path) / "inexistant" / "sous" / "agent.log")

    acp._archiver(session, "peu importe")

    assert session.journal_fichier is None


def test_une_session_sans_fichier_ne_leve_pas() -> None:
    acp._archiver(_Session(None), "peu importe")


def test_un_chemin_impossible_rend_none() -> None:
    """Le nom d'un lecteur inexistant ne doit pas empecher d'ouvrir une session."""
    assert acp._fichier_de_journal("Z:/inexistant\0/x") is None
