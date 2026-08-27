"""La file de nuit ne doit pas mentir au matin (HOS-191).

Une nuit de rendus coûte huit heures. Le rapport qu'on lit au réveil est
donc la seule chose qui reste, et sa seule valeur tient à ce qu'il ne
dise pas de bien de ce qu'il n'a pas vérifié.

Les cas éprouvés ici sont ceux où la file pourrait embellir : un plan
terminé mais non relu, un plan relu et refusé, une carte occupée, et une
série d'échecs qui ne s'arrête pas. Chacun a un précédent dans ce dépôt.

Rien ici ne demande de GPU, de ComfyUI ni d'Ollama — c'est délibéré : une
file qui ne se testerait que par des nuits entières ne serait jamais
testée.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional

from backend.studio.file_de_nuit import (ECHECS_AVANT_ARRET, Etat, Plan,
                                         derouler)


@dataclass
class FauxRendu:
    acheve: bool = True
    fichiers: list = field(default_factory=lambda: ["/faux/plan.mp4"])
    duree_s: float = 251.0
    pic_vram_octets: int = 8_150_000_000
    erreur: str = ""


@dataclass
class FauxVerdict:
    correspond: Optional[bool] = None
    confiance: int = 0
    defauts: list = field(default_factory=list)
    raison: str = ""


@dataclass
class FausseOccupation:
    obtenu: bool = True
    liberation_douteuse: bool = False
    detail: str = ""


def _plans(combien: int = 2) -> list[Plan]:
    return [Plan(identifiant=f"p{i}", consigne=f"consigne {i}",
                 graphe={"n": i}) for i in range(combien)]


def _rend_tout(_graphe):
    return "id"


def test_un_plan_relu_conforme_est_retenu():
    r = derouler(_plans(1), soumettre=_rend_tout,
                 attendre=lambda _: FauxRendu(),
                 relire=lambda f, c: FauxVerdict(correspond=True, confiance=92))
    p = r.plans[0]
    assert p.etat is Etat.RETENU
    assert p.confiance == 92
    assert p.duree_s == 251.0 and p.pic_vram_octets == 8_150_000_000


def test_un_plan_rendu_mais_non_relu_nest_pas_une_reussite():
    """Le défaut central de ce dépôt, transposé à la vidéo.

    ComfyUI rend un MP4 valide quel que soit le contenu. Sans relecteur,
    la file n'a aucun moyen de savoir si le plan correspond — et le dire
    est la seule réponse honnête.
    """
    r = derouler(_plans(1), soumettre=_rend_tout,
                 attendre=lambda _: FauxRendu(), relire=None)
    assert r.plans[0].etat is Etat.INDETERMINE
    assert r.compte().get(Etat.RETENU.value, 0) == 0
    assert "aucun relecteur" in r.plans[0].raison


def test_un_plan_refuse_par_le_relecteur_est_rejete():
    r = derouler(_plans(1), soumettre=_rend_tout,
                 attendre=lambda _: FauxRendu(),
                 relire=lambda f, c: FauxVerdict(
                     correspond=False, defauts=["le plan dérive"],
                     raison="2 image(s) sur 3 ne correspondent pas"))
    p = r.plans[0]
    assert p.etat is Etat.REJETE
    assert "le plan dérive" in p.defauts


def test_un_relecteur_qui_na_pas_pu_juger_ne_rejette_pas():
    """`None` n'est pas `False`, ici comme dans le relecteur.

    Les confondre ferait jeter au matin des plans corrects rendus pendant
    qu'Ollama était occupé — au même prix qu'une acceptation à tort.
    """
    r = derouler(_plans(1), soumettre=_rend_tout,
                 attendre=lambda _: FauxRendu(),
                 relire=lambda f, c: FauxVerdict(
                     correspond=None, raison="la fenêtre s'est fermée"))
    assert r.plans[0].etat is Etat.INDETERMINE
    assert r.plans[0].etat is not Etat.REJETE


def test_un_relecteur_qui_tombe_ne_fait_pas_tomber_la_nuit():
    r = derouler(_plans(2), soumettre=_rend_tout,
                 attendre=lambda _: FauxRendu(),
                 relire=lambda f, c: (_ for _ in ()).throw(
                     ConnectionError("Ollama injoignable")))
    assert [p.etat for p in r.plans] == [Etat.INDETERMINE, Etat.INDETERMINE]
    assert "ConnectionError" in r.plans[0].raison


def test_un_plan_sans_consigne_nest_pas_soumis_au_relecteur():
    """Juger une image contre une invite vide produirait une réponse.

    C'est exactement le danger : le modèle répondrait, avec une
    confiance, et ce chiffre ne voudrait rien dire. Mieux vaut dire
    qu'on n'avait rien à comparer.
    """
    interroge = []
    r = derouler([Plan(identifiant="sans", consigne="   ", graphe={"n": 1})],
                 soumettre=_rend_tout, attendre=lambda _: FauxRendu(),
                 relire=lambda f, c: interroge.append(c) or FauxVerdict(
                     correspond=True, confiance=99))
    assert r.plans[0].etat is Etat.INDETERMINE
    assert interroge == [], "le relecteur ne doit pas être appelé"
    assert "aucune consigne" in r.plans[0].raison


def test_un_rendu_sans_fichier_est_un_echec_pas_une_reussite():
    """`acheve` seul ne prouve rien : c'est le fichier qui prouve."""
    r = derouler(_plans(1), soumettre=_rend_tout,
                 attendre=lambda _: FauxRendu(acheve=True, fichiers=[]),
                 relire=lambda f, c: FauxVerdict(correspond=True))
    assert r.plans[0].etat is Etat.ECHOUE
    assert "aucun fichier" in r.plans[0].raison


def test_la_carte_occupee_arrete_le_plan_sans_le_rendre():
    """Un rendu lancé sans la carte ne lève pas : il déborde en silence.

    Dix-sept fois le temps, mesuré, aucune erreur. La file doit donc
    refuser plutôt que d'essayer.
    """
    lances = []

    @contextmanager
    def occupee(_besoin):
        yield FausseOccupation(obtenu=False, detail="la carte est déjà réservée")

    r = derouler(_plans(1),
                 soumettre=lambda g: lances.append(g) or "id",
                 attendre=lambda _: FauxRendu(),
                 reserver=occupee)
    assert r.plans[0].etat is Etat.ECHOUE
    assert lances == [], "aucun rendu ne doit partir sans la carte"


def test_une_liberation_douteuse_vaut_un_refus():
    """Décharger et croire que c'est fait, c'est l'erreur d'un cran plus haut.

    `carte_reservee` relit le compteur ; quand la VRAM n'est pas revenue,
    lancer quand même produirait le débordement silencieux.
    """
    lances = []

    @contextmanager
    def douteuse(_besoin):
        yield FausseOccupation(liberation_douteuse=True,
                               detail="4,20 Gio libres, 10,73 demandés")

    r = derouler(_plans(1), soumettre=lambda g: lances.append(g) or "id",
                 attendre=lambda _: FauxRendu(), reserver=douteuse)
    assert r.plans[0].etat is Etat.ECHOUE
    assert "10,73 demandés" in r.plans[0].raison
    assert lances == []


def test_la_carte_est_rendue_entre_deux_plans():
    """Sinon une mission ne reprendrait jamais la main avant le matin."""
    journal_reservations = []

    @contextmanager
    def suivie(besoin):
        journal_reservations.append(("prise", besoin))
        try:
            yield FausseOccupation()
        finally:
            journal_reservations.append(("rendue", besoin))

    derouler(_plans(2), soumettre=_rend_tout, attendre=lambda _: FauxRendu(),
             reserver=suivie, besoin_octets=42)
    assert [e for e, _ in journal_reservations] == [
        "prise", "rendue", "prise", "rendue"]


def test_trois_echecs_consecutifs_arretent_la_file():
    """Au-delà, la nuit ne sert plus qu'à confirmer le même défaut.

    Huit heures pour réapprendre ce que le troisième échec disait déjà.
    """
    r = derouler(_plans(6), soumettre=_rend_tout,
                 attendre=lambda _: (_ for _ in ()).throw(
                     RuntimeError("ComfyUI injoignable")))
    etats = [p.etat for p in r.plans]
    assert etats[:ECHECS_AVANT_ARRET] == [Etat.ECHOUE] * ECHECS_AVANT_ARRET
    assert all(e is Etat.ABANDONNE for e in etats[ECHECS_AVANT_ARRET:])
    assert "échecs consécutifs" in r.arret_anticipe


def test_un_succes_remet_le_compteur_dechecs_a_zero():
    """Deux pannes isolées séparées par une réussite ne sont pas une série."""
    resultats = iter([RuntimeError("x"), FauxRendu(), RuntimeError("y"),
                      FauxRendu(), FauxRendu()])

    def attendre(_):
        r = next(resultats)
        if isinstance(r, Exception):
            raise r
        return r

    r = derouler(_plans(5), soumettre=_rend_tout, attendre=attendre,
                 relire=lambda f, c: FauxVerdict(correspond=True))
    assert not r.arret_anticipe
    assert [p.etat for p in r.plans] == [
        Etat.ECHOUE, Etat.RETENU, Etat.ECHOUE, Etat.RETENU, Etat.RETENU]


def test_le_journal_est_ecrit_apres_chaque_plan(tmp_path):
    """Une nuit coupée à la sixième heure doit laisser cinq plans lisibles."""
    chemin = str(tmp_path / "nuit" / "rapport.json")
    vus = []

    def attendre(_):
        if os.path.exists(chemin):
            vus.append(json.load(open(chemin, encoding="utf-8"))["compte"])
        return FauxRendu()

    derouler(_plans(3), soumettre=_rend_tout, attendre=attendre,
             relire=lambda f, c: FauxVerdict(correspond=True), journal=chemin)

    # Rien n'est consigné avant le premier plan : `vus` commence donc au
    # deuxième, et compte alors un plan déjà retenu, puis deux.
    assert [v.get(Etat.RETENU.value) for v in vus] == [1, 2]
    final = json.load(open(chemin, encoding="utf-8"))
    assert final["compte"][Etat.RETENU.value] == 3
    assert final["duree_s"] >= 0


def test_le_resume_ne_compte_que_les_plans_retenus():
    """Le chiffre du matin porte sur ce qui est utilisable, pas sur ce qui
    s'est terminé — la distinction est tout l'objet de ce module."""
    r = derouler(_plans(2), soumettre=_rend_tout,
                 attendre=lambda _: FauxRendu(), relire=None)
    assert r.resume().startswith("0/2 plan(s) retenu(s)")
    assert Etat.INDETERMINE.value in r.resume()
