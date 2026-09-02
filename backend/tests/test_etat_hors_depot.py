"""L'état de l'utilisateur ne vit pas dans le dépôt (HOS-215).

Mesuré le 2026-09-02 : `data/db` 17,1 Mio, `data/eventbus` 8,2, les
instantanés 1,1 — **tout l'état vivait dans le répertoire de
l'application**. `.gitignore` le protégeait de git ; rien ne le
protégeait d'une mise à jour, qui remplace ce répertoire.

Ce qui aurait disparu à la première mise à jour : la base, la mémoire, le
bus d'événements, et les instantanés — c'est-à-dire la capacité de
reprise elle-même.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core import etat


def test_la_racine_par_defaut_tombe_hors_du_depot():
    r = etat.resoudre_racine()
    with pytest.raises(ValueError):
        # `relative_to` lève quand le chemin n'est pas sous la racine :
        # c'est exactement ce qu'on veut prouver.
        r.resolve().relative_to(etat.RACINE_DEPOT)


def test_une_racine_dans_le_depot_est_refusee():
    """Même demandée explicitement.

    Le permettre par configuration laisserait le défaut revenir par la
    porte qu'on vient de fermer.
    """
    with pytest.raises(etat.RacineInvalide) as e:
        etat.resoudre_racine(str(etat.RACINE_DEPOT / "data"))
    assert "HOS-215" in str(e.value)


def test_une_racine_demandee_l_emporte(tmp_path):
    assert etat.resoudre_racine(str(tmp_path)) == tmp_path


def test_la_variable_d_environnement_est_lue(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path / "ailleurs"))
    assert etat.resoudre_racine() == tmp_path / "ailleurs"


def test_le_dossier_ne_se_confond_pas_avec_celui_de_l_agent():
    """`%LOCALAPPDATA%\\hermes` appartient à Hermes Agent.

    C'est son `HERMES_HOME`, avec ses profils et ses clés. Deux logiciels
    dans le même dossier, c'est une mise à jour de l'un qui casse
    l'autre.
    """
    assert etat.NOM_DOSSIER.lower() != "hermes"


def test_le_preserve_set_couvre_ce_que_les_reglages_utilisent(monkeypatch,
                                                              tmp_path):
    """La liste à préserver ne doit pas diverger des chemins réels.

    C'est le piège d'une liste écrite en prose dans un document de mise à
    jour : elle vieillit pendant que le code bouge, et la première chose
    oubliée est la première effacée.
    """
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    etat.racine.cache_clear()
    try:
        preserve = {p.resolve() for p in etat.preserve_set()}
        from backend.core.config import Settings

        reglages = Settings()
        for chemin in (reglages.sqlite_path, reglages.chroma_path,
                       reglages.logs_dir, reglages.snapshot_dir):
            p = Path(chemin).resolve()
            couvert = any(p == d or d in p.parents for d in preserve)
            assert couvert, (
                f"{chemin} n'est couvert par aucun dossier du preserve set : "
                "une mise à jour l'effacerait sans que rien ne le dise")
    finally:
        etat.racine.cache_clear()


def test_aucun_reglage_ne_pointe_dans_le_depot():
    """La garde de fond : un défaut écrit en dur y ramènerait tout."""
    from backend.core.config import get_settings

    reglages = get_settings()
    for nom in ("sqlite_path", "chroma_path", "logs_dir", "snapshot_dir"):
        p = Path(getattr(reglages, nom)).resolve()
        dans_le_depot = True
        try:
            p.relative_to(etat.RACINE_DEPOT)
        except ValueError:
            dans_le_depot = False
        assert not dans_le_depot, (
            f"{nom} = {p} tombe dans le dépôt — une mise à jour l'effacerait")


def test_le_contenu_livre_reste_dans_le_depot():
    """Le critère n'est pas « où c'est rangé » mais **qui l'a écrit**.

    `data/workflows/*.yaml` est suivi par git : c'est du contenu livré
    avec l'application, qui doit être remplacé à chaque mise à jour. Le
    déplacer hors du dépôt a fait passer `/workflows` de deux entrées à
    zéro, et un test l'a dit tout de suite — « no workflows shipped, this
    test would pass vacuously ».

    L'état de l'utilisateur sort ; le contenu de l'application reste.
    """
    from backend.core.config import get_settings

    livres = Path(get_settings().workflows_dir).resolve()
    assert livres.relative_to(etat.RACINE_DEPOT)
    assert livres not in {p.resolve() for p in etat.preserve_set()}
