"""Mettre une campagne en pause sans tout reperdre (HOS-154).

Une campagne dure une quinzaine d'heures. Elle traverse forcement un besoin
de la machine — liberer la carte graphique, redemarrer, dormir — et la seule
facon de l'arreter etait de tout perdre : le plan coche les sections **a
traiter**, il ne dit pas lesquelles sont faites.

La reprise lit le journal plutot qu'un fichier d'etat, et c'est ce choix qui
la rend utilisable **sur les campagnes lancees avant qu'elle n'existe** —
verifie sur celle qui tournait au moment ou ces tests ont ete ecrits : elle
y a lu §1, §6, §7 et §8.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import derouler_cahier as runner  # noqa: E402


JOURNAL = """plan relu : 22 sections a construire

=== §1 IDENTITE DU PROJET ===
  -> faite (passe 1)  (partielle)

=== §6 MODELE D'IDENTITE ===
  -> faite (passe 1)  (verifiee)

=== §7 IDENTIFIANT EMPLOYEE ===
  -> bloquee (passe 2)  (non_mesuree)  les tests du livrable echouent

=== §8 ORGANISATION ===
  -> faite (passe 1)  (verifiee)

=== §9 ATELIERS ===
"""


def _hermes(tmp_path: Path, journal: str = JOURNAL) -> Path:
    dossier = tmp_path / ".hermes"
    dossier.mkdir(parents=True)
    (dossier / "nuit.log").write_text(journal, encoding="utf-8")
    return dossier


def test_les_sections_faites_sont_relues_du_journal(tmp_path) -> None:
    assert runner.sections_deja_faites(_hermes(tmp_path)) == {1, 6, 8}


def test_une_section_bloquee_est_rejouee(tmp_path) -> None:
    """Sauter un echec le ferait passer pour un travail fini.

    §7 a consomme ses deux passes sans aboutir. C'est exactement ce que ce
    projet passe son temps a empecher ailleurs : un `bloquee` n'est pas un
    `faite` silencieux.
    """
    assert 7 not in runner.sections_deja_faites(_hermes(tmp_path))


def test_une_section_commencee_sans_verdict_est_rejouee(tmp_path) -> None:
    """§9 etait en cours au moment de la pause : elle n'a rien rendu."""
    assert 9 not in runner.sections_deja_faites(_hermes(tmp_path))


def test_sans_journal_rien_n_est_presume_fait(tmp_path) -> None:
    (tmp_path / ".hermes").mkdir()

    assert runner.sections_deja_faites(tmp_path / ".hermes") == set()


def test_le_releve_survit_a_un_journal_tronque(tmp_path) -> None:
    """Le defaut que ce releve existe pour eviter.

    Relancer en redirigeant la sortie vers `nuit.log` le **tronque**. Une
    reprise qui ne lirait que lui perdrait tout a la seconde pause : la
    premiere marcherait, et l'utilisateur croirait la fonction acquise.
    """
    dossier = _hermes(tmp_path)
    runner.noter_les_acquis(dossier, runner.sections_deja_faites(dossier))

    # La relance ecrase le journal, comme le ferait `> nuit.log`.
    (dossier / "nuit.log").write_text("plan relu : 22 sections\n",
                                      encoding="utf-8")

    assert runner.sections_deja_faites(dossier) == {1, 6, 8}


def test_les_deux_sources_sont_unies_pas_choisies(tmp_path) -> None:
    """Une reprise ajoute des sections ; le releve ne doit pas les masquer."""
    dossier = _hermes(tmp_path, JOURNAL)
    runner.noter_les_acquis(dossier, {1, 6})  # un releve plus ancien

    assert runner.sections_deja_faites(dossier) == {1, 6, 8}


def test_noter_les_acquis_ne_leve_pas_sur_un_chemin_impossible() -> None:
    """Perdre le releve coute une reprise plus longue, pas la campagne."""
    runner.noter_les_acquis(Path("Z:/inexistant/\0"), {1})
