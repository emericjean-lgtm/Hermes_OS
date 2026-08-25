"""Le harnais n'etait verifie qu'au demarrage (HOS-164).

Le 2026-08-24 a 22:00, le backend de Hermes OS s'est arrete au milieu d'un
cahier. L'agent tire ses outils de Hermes OS par MCP : sans backend, il
demarre avec zero outil. Le journal l'a dit a chaque tache qui a suivi —

    harnais indisponible : le backend de Hermes OS ne repond pas
    harnais ecarte

— et la file a continue. §21 a consomme ses deux passes avec un agent jete
apres usage, donc amnesique, puis s'est declaree bloquee sur des tests en
echec. Le diagnostic evident etait « le code de RiskModel est faux » ; le
vrai etait « le cerveau avait disparu depuis quatre heures ».

`verifier_le_harnais` refusait bien de **partir** sans harnais depuis
HOS-128, et ce refus a joue le lendemain. Mais il ne s'executait qu'une
fois, et un cahier de quinze heures traverse forcement une coupure.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import derouler_cahier as runner  # noqa: E402

from backend.mission import programme  # noqa: E402


class _Section:
    numero, titre, corps = 21, "RISK", "du texte"
    etiquette = "§21 RISK"


def test_une_section_sans_harnais_ne_passe_pas_pour_ratee() -> None:
    """C'est une section qui n'a pas eu lieu, pas une section echouee.

    La distinction n'est pas cosmetique : `bloquee` avec l'erreur exacte
    envoie l'operateur redemarrer son backend, alors qu'un rapport de tests
    en echec l'envoie relire du code qui n'a peut-etre rien.
    """
    def lancer(_section):
        raise runner.HarnaisPerdu(
            "le backend de Hermes OS ne repond pas")

    (etape,) = programme.derouler([_Section()], lancer=lancer, max_passes=2)

    assert etape.statut == "bloquee"
    assert "HarnaisPerdu" in etape.detail
    assert "backend" in etape.detail


def test_la_file_s_arrete_au_lieu_de_continuer_sans_cerveau() -> None:
    """La moitie qui manquait : §21 avait continue, et les suivantes aussi.

    Une nuit entiere en mode jetable ne produit pas une erreur — elle
    produit un bilan **de meme forme** qu'une nuit reussie.
    """
    class _Suivante(_Section):
        numero, titre, etiquette = 22, "KPI", "§22 KPI"

    def lancer(_section):
        raise runner.HarnaisPerdu("le backend ne repond pas")

    premiere, suivante = programme.derouler(
        [_Section(), _Suivante()], lancer=lancer, max_passes=1)

    assert premiere.statut == "bloquee"
    assert suivante.statut == "ignoree", (
        "la file doit s'arreter : les sections suivantes tourneraient sans "
        "l'agent, exactement comme §21")


def test_la_reparation_est_gardee_elle_aussi() -> None:
    """C'est pendant une reparation que §21 a brule son dernier credit."""
    appels = []

    def lancer(_section):
        appels.append("lancer")
        return {"created": [], "verification": {"tests": {"ran": True,
                                                          "passed": False}}}

    def reparer(_section, _diagnostic):
        appels.append("reparer")
        raise runner.HarnaisPerdu("le backend ne repond pas")

    (etape,) = programme.derouler([_Section()], lancer=lancer,
                                  reparer=reparer, max_passes=2)

    assert appels == ["lancer", "reparer"]
    assert etape.statut == "bloquee"
    assert "HarnaisPerdu" in etape.detail


def test_harnais_perdu_est_une_erreur_nommee() -> None:
    """Un `RuntimeError` nu se confondrait avec n'importe quelle panne."""
    assert issubclass(runner.HarnaisPerdu, RuntimeError)
    with pytest.raises(runner.HarnaisPerdu):
        raise runner.HarnaisPerdu("x")
