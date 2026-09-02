"""« On n'a pas pu regarder » n'est ni un succès ni un échec (HOS-222).

## Les deux défauts mesurés

`snapshot()` rendait un instantané **vide** pour un arbre illisible,
indiscernable d'un dossier réellement vide. Deux faux verdicts en
partaient, en sens opposés :

- un workspace de deux fichiers devenu illisible se lisait « 2
  supprimés », donc `touched_anything`, donc **`verified: True`** — le
  module produisait exactement le faux positif qu'il existe pour
  attraper ;
- deux instantanés illisibles se lisaient « rien n'a changé », donc
  **`contradicted: True`** — une accusation portée sur une mission qui
  avait peut-être travaillé.

Et `_fingerprint` rendait la chaîne constante `"unreadable"` : deux
fichiers différents comparés égaux, et un fichier illisible des deux
côtés déclaré inchangé alors qu'on ne l'avait jamais lu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.mission.verification import (
    WorkspaceSnapshot,
    _fingerprint,
    diff,
    snapshot,
    verify,
)
from backend.runs.contrat import Verdict


@pytest.fixture
def arbre(tmp_path: Path) -> Path:
    (tmp_path / "a.txt").write_text("bonjour", encoding="utf-8")
    (tmp_path / "b.txt").write_text("monde", encoding="utf-8")
    return tmp_path


# ── L'instantané sait dire qu'il n'a pas pu lire ─────────────────────

def test_un_arbre_absent_n_est_pas_un_arbre_vide(tmp_path):
    """Le défaut d'origine, dans sa forme la plus simple."""
    vu = snapshot(str(tmp_path / "nexiste_pas"))
    assert vu.lisible is False
    assert vu.file_count == 0


def test_un_arbre_lisible_le_dit(arbre):
    vu = snapshot(str(arbre))
    assert vu.lisible is True
    assert vu.file_count == 2
    assert vu.illisibles == ()


def test_un_fichier_illisible_sort_des_empreintes(arbre, monkeypatch):
    """Il va dans `illisibles`, pas dans `entries` avec un marqueur.

    Un marqueur constant faisait comparer égaux deux fichiers différents.
    On simule ici le contrat de `_fingerprint` — rendre `None` — plutôt
    que de refuser le `stat` : `is_file()` avale l'erreur et le fichier
    disparaîtrait de la marche avant d'atteindre l'empreinte, ce qui ne
    mesurerait pas ce qu'on veut mesurer.
    """
    from backend.mission import verification as module

    vraie = module._fingerprint
    monkeypatch.setattr(module, "_fingerprint",
                        lambda p: None if p.name == "a.txt" else vraie(p))
    vu = snapshot(str(arbre))
    assert "a.txt" in vu.illisibles
    assert "a.txt" not in vu.entries
    assert "b.txt" in vu.entries


def test_une_empreinte_illisible_est_none(tmp_path):
    """Rendait `"unreadable"` — la même valeur pour tous.

    Deux fichiers différents comparaient égaux, et un fichier réécrit
    mais toujours illisible passait pour inchangé.
    """
    assert _fingerprint(tmp_path / "x") is None
    assert _fingerprint(tmp_path / "y") is None


# ── Le diff range l'inconnu à part ───────────────────────────────────

def test_un_fichier_illisible_n_est_ni_cree_ni_supprime():
    """« Illisible avant, lisible après » comptait comme créé.

    C'est une permission qui change, pas un travail qui s'accomplit.
    """
    avant = WorkspaceSnapshot(root="/w", entries={"b": "1"}, illisibles=("a",))
    apres = WorkspaceSnapshot(root="/w", entries={"a": "2", "b": "1"})

    d = diff(avant, apres)
    assert d.created == ()
    assert d.modified == ()
    assert d.deleted == ()
    assert d.indetermines == ("a",)


def test_les_indetermines_ne_comptent_pas_comme_du_travail():
    """`touched_anything` est une affirmation de constat.

    On ne peut pas la fonder sur un fichier qu'on n'a pas su lire.
    """
    avant = WorkspaceSnapshot(root="/w", illisibles=("a",))
    apres = WorkspaceSnapshot(root="/w", illisibles=("a",))
    assert diff(avant, apres).touched_anything is False


def test_le_resume_ne_dit_pas_rien_n_a_change_quand_il_ne_sait_pas():
    """Sans ça, un rapport d'indéterminés se lisait « rien n'a changé ».

    Une affirmation qu'on n'est pas en position de faire.
    """
    d = diff(WorkspaceSnapshot(root="/w", illisibles=("a",)),
             WorkspaceSnapshot(root="/w", illisibles=("a",)))
    resume = d.summary()
    assert "no change could be established" in resume
    assert "1 unreadable: a" in resume


def test_un_changement_reel_reste_lisible_dans_le_resume():
    d = diff(WorkspaceSnapshot(root="/w", entries={"a": "1"}),
             WorkspaceSnapshot(root="/w", entries={"a": "2", "b": "1"}))
    assert "1 created: b" in d.summary()
    assert "1 modified: a" in d.summary()


# ── Les deux faux verdicts, chacun dans son sens ─────────────────────

def test_un_workspace_devenu_illisible_n_est_pas_verifie(arbre, tmp_path):
    """Le faux **positif** : les fichiers d'avant comptaient comme supprimés.

    Une mission qui n'a rien fait, dans un workspace qui a disparu, se
    déclarait `verified: True`.
    """
    avant = snapshot(str(arbre))
    apres = snapshot(str(tmp_path / "envole"))

    v = verify("m", True, str(arbre), avant, apres)
    assert v.verified is False
    assert v.measured is False
    assert v.verdict is Verdict.INDISPONIBLE


def test_deux_instantanes_illisibles_ne_contredisent_personne(tmp_path):
    """Le faux **négatif** : « rien n'a changé » devenait une accusation.

    C'est le jumeau de la règle centrale du dépôt — ni un succès sur
    parole, ni un échec sur parole.
    """
    absent = snapshot(str(tmp_path / "nexiste_pas"))
    v = verify("m", True, str(tmp_path), absent, absent)
    assert v.contradicted is False
    assert v.verdict is Verdict.INDISPONIBLE


def test_le_cas_normal_n_a_pas_bouge(arbre):
    """La réparation ne doit pas désarmer la mesure qui marchait."""
    avant = snapshot(str(arbre))
    (arbre / "c.txt").write_text("nouveau", encoding="utf-8")
    v = verify("m", True, str(arbre), avant, snapshot(str(arbre)))
    assert v.verified is True
    assert v.verdict is Verdict.REUSSI


def test_un_workspace_intact_est_toujours_contredit(arbre):
    """Le défaut que ce module existe pour attraper reste attrapé."""
    avant = snapshot(str(arbre))
    v = verify("m", True, str(arbre), avant, snapshot(str(arbre)))
    assert v.contradicted is True
    assert v.verdict is Verdict.ECHOUE


# ── Le verdict nommé ─────────────────────────────────────────────────

def test_le_verdict_reutilise_le_vocabulaire_du_contrat():
    """Un second tri-état aurait donné deux façons de dire « on ne sait pas ».

    Donc une de trop, et la question « laquelle croire ? » à chaque
    lecture.
    """
    from backend.mission import verification
    import inspect
    source = inspect.getsource(verification.MissionVerification.verdict.fget)
    assert "backend.runs.contrat" in source


def test_les_trois_etats_sont_atteignables(arbre, tmp_path):
    avant = snapshot(str(arbre))
    obtenus = {
        verify("a", True, str(arbre), avant, avant).verdict,
        verify("b", True, None, None, None).verdict,
    }
    (arbre / "c.txt").write_text("x", encoding="utf-8")
    obtenus.add(verify("c", True, str(arbre), avant, snapshot(str(arbre))).verdict)
    assert obtenus == {Verdict.REUSSI, Verdict.ECHOUE, Verdict.INDISPONIBLE}


def test_le_verdict_est_dans_le_rapport(arbre):
    avant = snapshot(str(arbre))
    rapport = verify("m", True, str(arbre), avant, avant).as_dict()
    assert rapport["verdict"] == "echoue"
    assert "indetermines" in rapport
    assert "mesure_impossible" in rapport


# ── L'alarme actionnable, et celle qu'on refuse de poser ─────────────

def test_une_mission_sans_workspace_ne_declenche_pas_d_alarme():
    """Le cas normal et fréquent.

    Une alarme qui sonne tout le temps se débranche dans la semaine —
    c'est la leçon du canary (HOS-218), et elle vaut ici aussi.
    """
    v = verify("m", True, None, None, None)
    assert v.measured is False
    assert v.mesure_impossible is False


def test_un_workspace_lie_et_illisible_declenche_l_alarme(arbre, tmp_path):
    """Un instrument muet se répare, il ne s'ignore pas."""
    avant = snapshot(str(arbre))
    v = verify("m", True, str(arbre), avant, snapshot(str(tmp_path / "envole")))
    assert v.mesure_impossible is True


def test_l_evenement_de_mesure_impossible_est_declare():
    """Un événement non déclaré est refusé par le bus au moment où il compte.

    C'est-à-dire précisément quand quelque chose va mal.
    """
    from backend.core.event_topics import BASELINE_TOPICS

    assert "mission.non_mesuree" in BASELINE_TOPICS


def test_le_graphe_distingue_les_deux_signaux():
    """`unverified` dit « le disque contredit », `non_mesuree` dit « le
    disque n'a rien dit ». Les confondre ferait passer un instrument muet
    pour un verdict.
    """
    import inspect
    from backend.mission import graph_executor

    source = inspect.getsource(graph_executor.GraphExecutor)
    assert "mission.non_mesuree" in source
    assert "mission.unverified" in source
