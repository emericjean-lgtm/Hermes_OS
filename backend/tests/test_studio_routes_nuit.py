"""POST /studio/night accepte un gabarit, pas seulement un graphe (HOS-206).

L'onglet Nuit du Studio Center n'affichait qu'un rapport, et aucun bouton
n'y menait : la route exigeait un `graphe` complet, que l'ecran ne sait
pas composer — la regle du depot reserve cette decision au gabarit ou a
l'agent. La file de nuit etait donc une capacite reelle, testee, et
inaccessible autrement qu'en la demandant a l'agent dans le chat.

Meme defaut que la voix Michael (HOS-196) et que les trois parametres de
HOS-199 : du code qui marche, sans commande a l'ecran.
"""

from __future__ import annotations

import backend.studio.routes as routes


class _FauxFil:
    def __init__(self, *a, **k): self._vivant = False
    def start(self): self._vivant = True
    def is_alive(self): return self._vivant


def _sans_thread(monkeypatch):
    """Ne pas lancer de vraie nuit : elle durerait des heures."""
    monkeypatch.setattr(routes, "_nuit", None)
    import threading
    monkeypatch.setattr(threading, "Thread", _FauxFil)


def test_un_gabarit_suffit_desormais(monkeypatch):
    _sans_thread(monkeypatch)
    r = routes.nuit({"plans": [
        {"identifiant": "p1", "consigne": "une rue de nuit",
         "gabarit": "plan_video", "parametres": {"images": 49}},
    ]})
    assert r["success"] is True
    assert r["plans"] == 1


def test_la_voie_du_graphe_reste_intacte(monkeypatch):
    # C'est celle de Hermes Agent : elle ne doit pas regresser.
    _sans_thread(monkeypatch)
    r = routes.nuit({"plans": [
        {"identifiant": "p1", "graphe": {"1": {"class_type": "X", "inputs": {}}}},
    ]})
    assert r["success"] is True


def test_un_plan_sans_gabarit_ni_graphe_est_refuse_en_le_nommant(monkeypatch):
    _sans_thread(monkeypatch)
    r = routes.nuit({"plans": [{"identifiant": "p1", "consigne": "x"}]})
    assert r["success"] is False
    assert "plan 0" in r["error"]


def test_un_gabarit_invalide_nomme_le_plan_fautif(monkeypatch):
    # Sur une file de dix plans, savoir lequel est mal decrit evite de
    # relire les dix.
    _sans_thread(monkeypatch)
    r = routes.nuit({"plans": [
        {"gabarit": "plan_video", "consigne": "ok"},
        {"gabarit": "gabarit_inexistant", "consigne": "x"},
    ]})
    assert r["success"] is False
    assert r["raison"] == "gabarit_invalide"
    assert "plan 1" in r["error"]


def test_la_consigne_passe_au_gabarit_et_au_relecteur(monkeypatch):
    # Sans consigne, le relecteur n'a rien a quoi comparer et le plan
    # finit `indetermine` : un rendu paye pour rien.
    _sans_thread(monkeypatch)
    vus = {}
    vrai = routes.__dict__.get("nuit")
    from backend.studio import file_de_nuit
    class Espion(file_de_nuit.Plan):
        def __init__(self, identifiant, consigne, graphe):
            vus["consigne"] = consigne
            super().__init__(identifiant=identifiant, consigne=consigne, graphe=graphe)
    monkeypatch.setattr(file_de_nuit, "Plan", Espion)
    routes.nuit({"plans": [{"gabarit": "plan_video", "consigne": "une rue de nuit"}]})
    assert vus["consigne"] == "une rue de nuit"
