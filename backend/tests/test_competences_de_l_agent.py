"""Hermes OS ignorait les 81 competences de son cerveau (HOS-153).

L'agent porte 81 `SKILL.md` en quatorze domaines. Aucune ligne du depot ne
citait ce dossier. `skills_list` fait pourtant partie de son toolset ACP —
mesure du 2026-08-23, 30 outils dont les trois de competences — mais un
modele n'appelle pas un outil dont rien ne lui rappelle l'existence.

Ces tests tiennent les trois moities de la correction : le registre lit, le
rappel atteint les trois modes, et une competence peut enfin s'ecrire.
"""
from __future__ import annotations

import backend.ral.adapters.hermes_agent_acp as acp
from backend.skills import registre


def _pose(base, domaine: str, nom: str, description: str = "") -> None:
    dossier = base / "skills" / domaine / nom
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "SKILL.md").write_text(
        f'---\nname: {nom}\ndescription: "{description}"\nversion: 1.0.0\n'
        f'metadata:\n  hermes:\n    tags: [x]\n---\n\nDu corps.\n',
        encoding="utf-8")


def test_le_registre_lit_nom_description_et_domaine(tmp_path) -> None:
    _pose(tmp_path, "github", "pr-review", "Relire une pull request.")

    (competence,) = registre.lire(str(tmp_path))

    assert competence.nom == "pr-review"
    assert competence.description == "Relire une pull request."
    assert competence.domaine == "github"


def test_un_skill_md_malforme_n_emporte_pas_les_autres(tmp_path) -> None:
    """Quatre-vingts competences ne doivent pas dependre de la 81e."""
    _pose(tmp_path, "github", "bonne", "Celle-ci va bien.")
    casse = tmp_path / "skills" / "github" / "cassee"
    casse.mkdir(parents=True)
    (casse / "SKILL.md").write_text("pas de frontmatter du tout\n",
                                    encoding="utf-8")

    noms = {c.nom for c in registre.lire(str(tmp_path))}

    assert noms == {"bonne", "cassee"}, (
        "une competence sans en-tete doit rendre un nom de repli, "
        "pas disparaitre ni faire echouer la lecture")


def test_sans_dossier_de_competences_la_lecture_est_vide(tmp_path) -> None:
    assert registre.lire(str(tmp_path)) == []


def test_le_rappel_nomme_les_domaines_et_l_outil_qui_les_ouvre(tmp_path) -> None:
    """Nommer les 81 competences couterait du contexte a chaque section."""
    _pose(tmp_path, "github", "pr-review", "Relire une PR.")
    _pose(tmp_path, "research", "veille", "Chercher.")

    rappel = registre.rappel_pour_brief(str(tmp_path))

    assert "github (1)" in rappel and "research (1)" in rappel
    assert "skills_list" in rappel
    # Sans quoi la proposition de competence reste theorique.
    assert "skill_manage" in rappel
    assert "pr-review" not in rappel, (
        "le rappel nomme les domaines, pas les competences")


def test_aucun_rappel_quand_il_n_y_a_rien_a_rappeler(tmp_path) -> None:
    assert registre.rappel_pour_brief(str(tmp_path)) == ""


# -- la permission d'ecrire une competence ----------------------------

class _Session:
    def __init__(self, cwd: str) -> None:
        self.cwd = cwd


def _demande(chemin: str) -> dict:
    return {"toolCall": {"content": [{"path": chemin}]}}


def test_une_competence_s_ecrit_hors_du_workspace(tmp_path, monkeypatch) -> None:
    """Le seul moyen de capitaliser une tache reussie ne doit pas etre refuse.

    Une competence sert toutes les missions et n'appartient a aucune : elle
    vit hors de tout workspace, par nature.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    cible = tmp_path / "hermes" / "hermes-agent" / "skills" / "x" / "SKILL.md"
    cible.parent.mkdir(parents=True)

    workspace = tmp_path / "mission"
    workspace.mkdir()

    refus = acp.HermesAgentACP._hors_workspace(
        _Session(str(workspace)), _demande(str(cible)))

    assert refus == "", f"la competence a ete refusee : {refus}"


def test_l_exception_ne_perce_que_le_dossier_des_competences(
        tmp_path, monkeypatch) -> None:
    """L'incident du 2026-08-21 reste couvert : `note.txt` a la racine."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    workspace = tmp_path / "mission"
    workspace.mkdir()

    # Voisin immediat du dossier autorise, et pourtant dehors.
    voisin = tmp_path / "hermes" / "hermes-agent" / "config.yaml"
    refus = acp.HermesAgentACP._hors_workspace(
        _Session(str(workspace)), _demande(str(voisin)))

    assert refus, "seul le dossier des competences est perce"
