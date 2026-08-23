"""1136 lignes remplacees par trois (HOS-153).

Campagne Skill360 du 2026-08-23. `PROJECT_SPEC.md` faisait 1136 lignes au
lancement. §1 l'a remplace par :

    # Documentation related to IDENTITE DU PROJET

    - docs/identite_du_projet.md

Les vingt et une sections suivantes ont travaille sur un cahier vide, et
rien ne l'a signale : §1 s'est declaree « faite », §6 s'est declaree
« verifiee », et le bilan de campagne ne regarde pas la taille des documents
d'entree.

La liste `.hermes/proteges.txt` etait pourtant posee, correcte et relue a
chaque appel. Elle etait appliquee dans `backend/tools/file_tools.py` —
c'est-a-dire sur les outils **de Hermes OS**, que l'agent n'utilise pas pour
ecrire. Une protection hors du chemin du travail ne protege rien.

Ces tests tiennent les deux chemins par lesquels l'agent ecrit vraiment :
sa demande de permission ACP, et son terminal.
"""
from __future__ import annotations

import sys
from pathlib import Path

import backend.ral.adapters.hermes_agent_acp as acp

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "config" / "hooks"))
import garde_workspace  # noqa: E402


class _Session:
    def __init__(self, cwd: str) -> None:
        self.cwd = cwd


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / ".hermes").mkdir(parents=True)
    (tmp_path / ".hermes" / "proteges.txt").write_text(
        "# les documents qui definissent le travail\n"
        "PROJECT_SPEC.md\nAGENT.md\n", encoding="utf-8")
    (tmp_path / "PROJECT_SPEC.md").write_text("mille lignes\n",
                                              encoding="utf-8")
    return tmp_path


def _demande(chemin: str) -> dict:
    return {"toolCall": {"content": [{"path": chemin}]}}


# -- le chemin `write_file` de l'agent, par la permission ACP ---------

def test_ecrire_sur_le_cahier_est_refuse(tmp_path) -> None:
    """L'incident lui-meme, dans le sens ou il s'est produit."""
    ws = _workspace(tmp_path)

    vise = acp.HermesAgentACP._touche_un_protege(
        _demande(str(ws / "PROJECT_SPEC.md")))

    assert vise, "le cahier des charges a de nouveau ete accepte en ecriture"


def test_ecrire_un_livrable_reste_libre(tmp_path) -> None:
    """La protection ne doit pas gener le travail qu'elle protege."""
    ws = _workspace(tmp_path)

    assert acp.HermesAgentACP._touche_un_protege(
        _demande(str(ws / "docs" / "identite_du_projet.md"))) == ""


def test_sans_liste_declaree_rien_n_est_protege(tmp_path) -> None:
    (tmp_path / "PROJECT_SPEC.md").write_text("x", encoding="utf-8")

    assert acp.HermesAgentACP._touche_un_protege(
        _demande(str(tmp_path / "PROJECT_SPEC.md"))) == ""


# -- le chemin du terminal, par le hook ------------------------------

def test_le_terminal_ne_peut_pas_ecraser_le_cahier(tmp_path) -> None:
    """`session/request_permission` ne couvre pas le terminal de l'agent.

    Mesure du 2026-08-21, mot pour mot dans la reponse de l'agent apres
    trois refus d'ecriture : « The write was blocked by the ACP client. Let
    me try using the terminal directly. »
    """
    ws = _workspace(tmp_path)

    for commande in ("echo remplace > PROJECT_SPEC.md",
                     "echo ajoute >> AGENT.md",
                     "sed -i s/a/b/ PROJECT_SPEC.md",
                     "mv brouillon.md PROJECT_SPEC.md"):
        assert garde_workspace.ecrase_un_document_d_entree(commande, str(ws)), (
            f"le terminal a pu ecraser le cahier : {commande}")


def test_lire_le_cahier_reste_libre(tmp_path) -> None:
    """C'est meme ce qu'on attend d'un agent devant un cahier des charges."""
    ws = _workspace(tmp_path)

    for commande in ("cat PROJECT_SPEC.md",
                     "grep -n 'SECTION' PROJECT_SPEC.md",
                     "head -50 PROJECT_SPEC.md",
                     "cat AGENT.md | head -20"):
        assert garde_workspace.ecrase_un_document_d_entree(
            commande, str(ws)) == "", f"faux refus sur : {commande}"


def test_sauvegarder_le_cahier_ailleurs_reste_libre(tmp_path) -> None:
    """`cp SPEC.md copie.md` sauvegarde le cahier, il ne le detruit pas.

    Le garde ne regarde que le dernier jeton — la destination. Toutes les
    formes qui ecrasent nomment leur cible en dernier.
    """
    ws = _workspace(tmp_path)

    assert garde_workspace.ecrase_un_document_d_entree(
        "cp PROJECT_SPEC.md sauvegarde.md", str(ws)) == ""


def test_une_redirection_vers_un_livrable_reste_libre(tmp_path) -> None:
    ws = _workspace(tmp_path)

    assert garde_workspace.ecrase_un_document_d_entree(
        "python build.py > docs/sortie.md", str(ws)) == ""


def test_le_refus_du_hook_dit_pourquoi(tmp_path) -> None:
    """Un garde-fou muet ne se distingue pas d'un garde-fou absent."""
    ws = _workspace(tmp_path)

    verdict = garde_workspace.verdict(
        {"tool_name": "terminal",
         "tool_input": {"command": "echo x > PROJECT_SPEC.md"}},
        str(ws))

    assert verdict is not None and verdict["action"] == "block"
    assert "PROJECT_SPEC.md" in verdict["message"]
    assert "definit le travail" in verdict["message"]
