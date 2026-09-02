"""Le contrat de mission, et le tri-état qu'il garde (HOS-221).

L'incident : le 2026-08-30, `img07` était `indéterminé` — le relecteur
n'avait pas su conclure. Cet état n'avait nulle part où aller dans une
vérification qui rend `bool`, et il s'est rangé à côté des plans jugés
bons.

Agent OS met la règle en capitales dans `src/lib/contract.ts` :
`GateResult = passed | failed | unavailable`, *never conflate unavailable
with passed*.
"""

from __future__ import annotations

import pytest

from backend.runs.contrat import (
    Contrat,
    ContratInvalide,
    Critere,
    EtatCritere,
    Genre,
    Verdict,
)


def _contrat() -> Contrat:
    return Contrat(objectif="produire la vidéo", criteres=[
        Critere("le fichier existe", verificateur="disque"),
        Critere("la voix est synchrone", verificateur="relecteur"),
    ])


# ── Le tri-état ──────────────────────────────────────────────────────

def test_indisponible_ne_devient_jamais_atteint():
    """La règle centrale. Tout le reste du module en découle."""
    c = _contrat()
    c.enregistrer(c.criteres[0].identifiant, Verdict.INDISPONIBLE)
    assert c.criteres[0].etat is EtatCritere.INVERIFIABLE
    assert not c.criteres[0].tenu


def test_inverifiable_n_est_pas_non_atteint_non_plus():
    """Deux états qui disent des choses opposées.

    Le premier est une lacune de mesure — on ne sait pas. Le second est
    un constat — on sait que non. Les confondre fait passer une
    ignorance pour un résultat, dans un sens ou dans l'autre.
    """
    assert EtatCritere.INVERIFIABLE is not EtatCritere.NON_ATTEINT
    c = _contrat()
    c.enregistrer(c.criteres[0].identifiant, Verdict.INDISPONIBLE)
    c.enregistrer(c.criteres[1].identifiant, Verdict.ECHOUE)
    assert len(c.inverifiables) == 1


def test_un_contrat_avec_un_inverifiable_n_est_pas_tenu():
    """C'est le point exact où ce dépôt s'est trompé le 30 août."""
    c = _contrat()
    c.enregistrer(c.criteres[0].identifiant, Verdict.REUSSI)
    c.enregistrer(c.criteres[1].identifiant, Verdict.INDISPONIBLE)
    assert not c.tenu
    assert "invérifiable" in c.resume()


def test_le_resume_dit_qu_un_inverifiable_n_est_pas_un_succes():
    """Un rapport qui compte 1/2 sans dire pourquoi ne fait pas agir."""
    c = _contrat()
    c.enregistrer(c.criteres[0].identifiant, Verdict.REUSSI)
    c.enregistrer(c.criteres[1].identifiant, Verdict.INDISPONIBLE)
    assert "n'est pas un succès" in c.resume()


def test_les_trois_verdicts_existent_et_sont_distincts():
    assert len({Verdict.REUSSI, Verdict.ECHOUE, Verdict.INDISPONIBLE}) == 3


def test_les_quatre_etats_existent_et_sont_distincts():
    assert len(set(EtatCritere)) == 4


# ── Les non-objectifs ────────────────────────────────────────────────

def test_un_non_objectif_atteint_est_une_violation():
    """Le sens s'inverse : le vérificateur cherche la chose interdite.

    « Aucune image noire » est tenu quand le vérificateur ne trouve
    rien, pas quand il trouve.
    """
    c = Contrat(objectif="o", criteres=[
        Critere("livrer", verificateur="disque"),
        Critere("aucune image noire", genre=Genre.NON_OBJECTIF,
                verificateur="relecteur"),
    ])
    c.enregistrer(c.criteres[1].identifiant, Verdict.REUSSI)
    assert c.criteres[1].etat is EtatCritere.VIOLE
    assert not c.criteres[1].tenu


def test_un_non_objectif_non_trouve_est_tenu():
    c = Contrat(objectif="o", criteres=[
        Critere("pas de fuite de secret", genre=Genre.NON_OBJECTIF,
                verificateur="canary"),
    ])
    c.enregistrer(c.criteres[0].identifiant, Verdict.ECHOUE)
    assert c.criteres[0].tenu


def test_une_violation_est_signalee_a_part_dans_le_resume():
    """Un non-objectif violé est un dégât, pas un travail inachevé.

    Les afficher au même compteur ferait lire « 2/3 » là où il faut
    lire « quelque chose a été cassé ».
    """
    c = Contrat(objectif="o", criteres=[
        Critere("livrer", verificateur="disque"),
        Critere("ne rien effacer", genre=Genre.NON_OBJECTIF,
                verificateur="disque"),
    ])
    c.enregistrer(c.criteres[1].identifiant, Verdict.REUSSI)
    assert "VIOLÉ" in c.resume()
    assert len(c.violes) == 1


def test_un_non_objectif_reste_inverifiable_si_indisponible():
    """Le tri-état prime sur l'inversion.

    Ne pas avoir pu chercher la chose interdite ne veut pas dire qu'elle
    n'y était pas.
    """
    c = Contrat(objectif="o", criteres=[
        Critere("ne rien effacer", genre=Genre.NON_OBJECTIF,
                verificateur="disque"),
    ])
    c.enregistrer(c.criteres[0].identifiant, Verdict.INDISPONIBLE)
    assert c.criteres[0].etat is EtatCritere.INVERIFIABLE


# ── La validation ────────────────────────────────────────────────────

def test_un_contrat_sans_critere_est_refuse():
    """Sinon il serait tenu quoi qu'il arrive.

    C'est le `success: true` au-dessus de rien, écrit à l'avance.
    """
    with pytest.raises(ContratInvalide, match="aucun critère"):
        Contrat(objectif="faire quelque chose").valider()


def test_un_contrat_sans_objectif_est_refuse():
    with pytest.raises(ContratInvalide, match="objectif"):
        Contrat(criteres=[Critere("x", verificateur="d")]).valider()


def test_un_critere_sans_verificateur_est_refuse():
    """Sans lui, « invérifiable » ne dit pas *ce qui* manque.

    Un rapport qui ne nomme pas le vérificateur absent ne fait pas agir.
    """
    with pytest.raises(ContratInvalide, match="vérificateur"):
        Contrat(objectif="o", criteres=[Critere("le fichier existe")]).valider()


def test_un_contrat_de_non_objectifs_seuls_est_refuse():
    """Ne rien casser n'est pas un objectif.

    Un contrat qui n'a que des interdits est tenu par une mission qui
    ne fait rien.
    """
    with pytest.raises(ContratInvalide, match="aucun critère d'acceptation"):
        Contrat(objectif="o", criteres=[
            Critere("ne rien effacer", genre=Genre.NON_OBJECTIF,
                    verificateur="disque"),
        ]).valider()


def test_un_contrat_complet_passe():
    _contrat().valider()


# ── Conjonction ──────────────────────────────────────────────────────

def test_un_contrat_est_tenu_quand_tous_ses_criteres_le_sont():
    c = _contrat()
    for critere in c.criteres:
        c.enregistrer(critere.identifiant, Verdict.REUSSI)
    assert c.tenu


def test_un_contrat_vide_n_est_pas_tenu():
    """Zéro critère sur zéro n'est pas 100 %."""
    assert not Contrat(objectif="o").tenu


def test_un_seul_echec_suffit():
    c = _contrat()
    c.enregistrer(c.criteres[0].identifiant, Verdict.REUSSI)
    c.enregistrer(c.criteres[1].identifiant, Verdict.ECHOUE)
    assert not c.tenu


def test_un_verdict_sur_un_critere_inconnu_leve():
    with pytest.raises(KeyError):
        _contrat().enregistrer("jamais_vu", Verdict.REUSSI)


# ── Sérialisation ────────────────────────────────────────────────────

def test_un_contrat_survit_a_l_aller_retour_json():
    """Il est rangé dans la colonne `contrat` du registre.

    Un aller-retour qui perdrait les états rendrait la trace inutile au
    moment où on la relit.
    """
    c = _contrat()
    c.enregistrer(c.criteres[0].identifiant, Verdict.INDISPONIBLE)
    c.budget = {"duree_s": 600, "tentatives": 3}
    c.conditions_d_arret = ["deux échecs de suite"]

    relu = Contrat.from_json(c.to_json())
    assert relu.objectif == c.objectif
    assert relu.budget == c.budget
    assert relu.conditions_d_arret == c.conditions_d_arret
    assert [x.etat for x in relu.criteres] == [x.etat for x in c.criteres]
    assert [x.identifiant for x in relu.criteres] == [x.identifiant
                                                      for x in c.criteres]


def test_un_verdict_se_pose_encore_apres_l_aller_retour():
    """Les identifiants doivent survivre, sinon `enregistrer` ne trouve plus."""
    c = _contrat()
    relu = Contrat.from_json(c.to_json())
    relu.enregistrer(relu.criteres[0].identifiant, Verdict.REUSSI)
    assert relu.criteres[0].tenu
