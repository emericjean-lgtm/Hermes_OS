"""La narration ne doit pas contourner l'arbitrage de la carte (HOS-195).

Chatterbox mesure 4,38 Gio de pic — pas gratuit comme Piper. Ces tests
portent donc sur les mêmes garde-fous que les rendus vidéo : la carte
refuse, aucun appel ne part ; le sous-processus tombe, la nuit ne casse
pas ; un segment échoue, les autres restent lisibles.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from backend.studio.narration import (ChatterboxIndisponible, Narration,
                                      synthetiser)


@dataclass
class FausseOccupation:
    obtenu: bool = True
    liberation_douteuse: bool = False
    detail: str = ""


def _reserve_normalement(_besoin):
    @contextmanager
    def ctx():
        yield FausseOccupation()
    return ctx()


def test_aucun_texte_ne_produit_rien_a_synthetiser():
    n = synthetiser([], "/faux/dossier")
    assert n.reussie and n.segments == []


def test_sans_chatterbox_installe_leve_un_message_nomme(tmp_path, monkeypatch):
    import backend.studio.narration as mod
    monkeypatch.setattr(mod, "PYTHON_CHATTERBOX", str(tmp_path / "absent.exe"))
    with pytest.raises(ChatterboxIndisponible, match="Michael"):
        synthetiser([("1", "bonjour")], str(tmp_path))


def test_une_reference_explicite_contourne_le_controle_de_michael(tmp_path):
    """Un test — ou un appel avec une autre voix un jour — ne doit pas
    dépendre de l'installation de Chatterbox sur cette machine."""
    ref = tmp_path / "autre_voix.wav"
    ref.write_bytes(b"faux wav")
    appels = []

    def faux_appel(requete, minutes):
        appels.append(requete)
        return {"appareil": "cuda", "charge_s": 9.0,
                "resultats": [{"id": "1", "chemin": "/x/1.wav", "duree_s": 2.0}]}

    n = synthetiser([("1", "bonjour")], str(tmp_path), reference=str(ref),
                    appeler=faux_appel)
    assert n.reussie
    assert appels[0]["reference"] == str(ref)


def test_les_reglages_passent_au_synthetiseur_sans_etre_modifies():
    appels = []

    def faux_appel(requete, minutes):
        appels.append(requete)
        return {"appareil": "cuda", "charge_s": 1.0, "resultats": []}

    synthetiser([("1", "x")], "/d", reference="/r.wav",
               reglages={"langue": "fr", "exaggeration": 0.3, "cfg_weight": 0.3},
               appeler=faux_appel)
    assert appels[0]["exaggeration"] == 0.3
    assert appels[0]["cfg_weight"] == 0.3


def test_plusieurs_segments_partent_dans_un_seul_appel():
    """Le chargement coûte 9 à 27 s mesurées : les recharger par phrase
    rendrait une narration de dix répliques inutilisable."""
    appels = []

    def faux_appel(requete, minutes):
        appels.append(requete)
        return {"appareil": "cuda", "charge_s": 10.0, "resultats": [
            {"id": s["id"], "chemin": f"/d/{s['id']}.wav", "duree_s": 1.5}
            for s in requete["segments"]
        ]}

    synthetiser([("1", "a"), ("2", "b"), ("3", "c")], "/d",
               reference="/r.wav", appeler=faux_appel)
    assert len(appels) == 1
    assert len(appels[0]["segments"]) == 3


def test_un_segment_en_echec_ne_fait_pas_echouer_les_autres():
    def faux_appel(requete, minutes):
        return {"appareil": "cuda", "charge_s": 9.0, "resultats": [
            {"id": "1", "chemin": "/d/1.wav", "duree_s": 2.0},
            {"id": "2", "erreur": "texte vide"},
        ]}

    n = synthetiser([("1", "a"), ("2", "")], "/d", reference="/r.wav",
                    appeler=faux_appel)
    assert not n.reussie
    a, b = n.segments
    assert a.reussi and not b.reussi
    assert b.erreur == "texte vide"


def test_la_carte_occupee_empeche_tout_appel():
    """Le pic mesuré est de 4,38 Gio — pas gratuit. Lancer sans la carte
    déborderait en silence, comme pour un rendu vidéo."""
    appels = []

    def faux_appel(requete, minutes):
        appels.append(requete)
        return {"appareil": "cuda", "charge_s": 0.0, "resultats": []}

    @contextmanager
    def occupee(_besoin):
        yield FausseOccupation(obtenu=False, detail="la carte est déjà réservée")

    n = synthetiser([("1", "a")], "/d", reference="/r.wav",
                    reserver=occupee, appeler=faux_appel)
    assert not n.reussie
    assert "réservée" in n.erreur
    assert appels == []


def test_une_liberation_douteuse_empeche_tout_appel():
    appels = []

    def faux_appel(requete, minutes):
        appels.append(requete)
        return {"resultats": []}

    @contextmanager
    def douteuse(_besoin):
        yield FausseOccupation(liberation_douteuse=True, detail="3,1 Gio libres")

    n = synthetiser([("1", "a")], "/d", reference="/r.wav",
                    reserver=douteuse, appeler=faux_appel)
    assert not n.reussie
    assert "3,1 Gio" in n.erreur
    assert appels == []


def test_un_delai_depasse_ne_leve_pas():
    import subprocess

    def lent(requete, minutes):
        raise subprocess.TimeoutExpired(cmd="chatterbox", timeout=minutes * 60)

    n = synthetiser([("1", "a")], "/d", reference="/r.wav",
                    reserver=_reserve_normalement, appeler=lent)
    assert not n.reussie
    assert "délai" in n.erreur


def test_une_sortie_illisible_est_rapportee_pas_levee():
    def casse(requete, minutes):
        raise RuntimeError("aucune sortie du synthétiseur (code 1) : Traceback...")

    n = synthetiser([("1", "a")], "/d", reference="/r.wav", appeler=casse)
    assert not n.reussie
    assert "code 1" in n.erreur


def test_une_reference_introuvable_cote_ouvrier_est_rapportee():
    """Le script ouvrier vérifie aussi lui-même, côté sous-processus."""
    def sans_reference(requete, minutes):
        return {"erreur": f"référence introuvable : {requete['reference']}"}

    n = synthetiser([("1", "a")], "/d", reference="/absent.wav",
                    appeler=sans_reference)
    assert not n.reussie
    assert "introuvable" in n.erreur
