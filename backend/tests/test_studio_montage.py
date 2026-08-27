"""Le montage doit prouver ce qu'il a produit (HOS-191).

`ffmpeg` sort avec le code 0 dans plusieurs cas où le résultat n'est pas
celui qu'on croit : une concaténation dont un fichier manque rend une
vidéo plus courte, un filtre de sous-titres sans libass rend une vidéo
sans texte. Aucun des deux ne lève.

C'est la règle centrale de ce dépôt appliquée au dernier maillon : après
une nuit de rendu, un montage silencieusement amputé se découvrirait au
visionnage. Ces tests portent donc sur ce que le module refuse de faire.

Les mesures réelles — trois plans de 2,04 s assemblés en 6,12 s, sous-
titres incrustés et constatés par comparaison d'empreintes — ont été
faites sur la machine le 2026-08-27 et ne sont pas rejouées ici : elles
demandent ffmpeg et des fichiers de plusieurs mégaoctets.
"""

from __future__ import annotations

import os

from backend.studio import montage as M
from backend.studio.montage import (TOLERANCE_S, Montage, assembler,
                                    ecrire_srt, _horodatage)


def test_un_montage_vide_ne_pretend_rien():
    m = Montage()
    assert not m.reussi and not m.duree_conforme


def test_une_duree_non_mesuree_nest_pas_une_conformite():
    """Zéro veut dire « pas mesuré », jamais « conforme ».

    C'est la même règle que le pic de VRAM : affirmer sans avoir vu est
    exactement le succès sur parole que ce module existe pour empêcher.
    """
    assert not Montage(duree_s=0.0, duree_attendue_s=6.12).duree_conforme
    assert not Montage(duree_s=6.12, duree_attendue_s=0.0).duree_conforme
    assert Montage(duree_s=6.12, duree_attendue_s=6.12).duree_conforme


def test_la_tolerance_couvre_lecart_dune_image():
    """Un plan dure un nombre entier d'images, pas la narration."""
    assert Montage(duree_s=6.12, duree_attendue_s=6.12 + TOLERANCE_S / 2).duree_conforme
    assert not Montage(duree_s=6.12, duree_attendue_s=8.0).duree_conforme


def test_un_plan_manquant_annule_le_montage(tmp_path):
    """Assembler ce qui reste produirait une vidéo plus courte, code 0.

    L'absence ne se verrait qu'au visionnage — après la nuit de rendu qui
    a payé les autres plans.
    """
    present = tmp_path / "a.mp4"
    present.write_bytes(b"x")
    m = assembler([str(present), str(tmp_path / "absent.mp4")],
                  str(tmp_path / "sortie.mp4"))
    assert not m.reussi
    assert "introuvable" in m.erreur
    assert not os.path.exists(tmp_path / "sortie.mp4")


def test_sans_plan_il_ny_a_rien_a_assembler(tmp_path):
    m = assembler([], str(tmp_path / "sortie.mp4"))
    assert not m.reussi and m.erreur


def test_une_duree_de_plan_illisible_arrete_avant_dencoder(monkeypatch, tmp_path):
    """Encoder sans savoir la durée attendue rendrait la vérification
    impossible — et un montage invérifiable ne vaut pas mieux qu'aucun."""
    p = tmp_path / "a.mp4"
    p.write_bytes(b"x")
    monkeypatch.setattr(M, "duree_s", lambda v: 0.0)
    appels = []
    monkeypatch.setattr(M, "_monter", lambda *a, **k: appels.append(a) or (True, ""))

    m = assembler([str(p)], str(tmp_path / "sortie.mp4"))
    assert not m.reussi
    assert "illisible" in m.erreur
    assert appels == [], "aucun encodage ne doit partir"


def test_un_montage_plus_court_que_ses_plans_est_un_echec(monkeypatch, tmp_path):
    """Le cas exact de la concaténation amputée : ffmpeg rend 0."""
    p = tmp_path / "a.mp4"
    p.write_bytes(b"x")
    sortie = tmp_path / "sortie.mp4"

    durees = {str(p): 4.0, str(sortie): 2.0}
    monkeypatch.setattr(M, "duree_s", lambda v: durees.get(v, 0.0))
    monkeypatch.setattr(M, "_monter",
                        lambda *a, **k: (sortie.write_bytes(b"video"), (True, ""))[1])

    m = assembler([str(p)], str(sortie))
    assert not m.reussi
    assert "2.00 s pour 4.00 s" in m.erreur


def test_un_fichier_absent_malgre_le_code_zero_est_signale(monkeypatch, tmp_path):
    p = tmp_path / "a.mp4"
    p.write_bytes(b"x")
    monkeypatch.setattr(M, "duree_s", lambda v: 4.0 if str(v) == str(p) else 0.0)
    monkeypatch.setattr(M, "_monter", lambda *a, **k: (True, ""))

    m = assembler([str(p)], str(tmp_path / "sortie.mp4"))
    assert not m.reussi
    assert "aucun fichier" in m.erreur


def test_une_narration_trop_longue_est_rapportee_pas_corrigee(monkeypatch, tmp_path):
    """Étirer changerait la voix, couper perdrait la fin.

    L'appelant est le seul à savoir lequel des deux il préfère ; le
    module se contente de le dire.
    """
    p, voix = tmp_path / "a.mp4", tmp_path / "v.wav"
    p.write_bytes(b"x")
    voix.write_bytes(b"x")
    sortie = tmp_path / "sortie.mp4"

    durees = {str(p): 6.12, str(voix): 9.96, str(sortie): 6.12}
    monkeypatch.setattr(M, "duree_s", lambda v: durees.get(v, 0.0))
    monkeypatch.setattr(M, "_monter",
                        lambda *a, **k: (sortie.write_bytes(b"v"), (True, ""))[1])

    m = assembler([str(p)], str(sortie), narration=str(voix))
    assert m.reussi, "l'écart n'est pas une erreur, c'est un avertissement"
    assert m.ecart_voix_s == 3.84
    assert any("9.96" in a or "10.0" in a for a in m.avertissements)


def test_sans_libass_les_sous_titres_ne_sont_pas_promis(monkeypatch, tmp_path):
    """Le cas silencieux : la vidéo sortirait sans texte, code 0.

    Annoncer `sous_titres: True` reviendrait à certifier ce qu'on n'a pas
    produit — la forme même du défaut que ce dépôt traque.
    """
    p, srt = tmp_path / "a.mp4", tmp_path / "s.srt"
    p.write_bytes(b"x")
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nsalut\n", encoding="utf-8")
    sortie = tmp_path / "sortie.mp4"

    durees = {str(p): 4.0, str(sortie): 4.0}
    monkeypatch.setattr(M, "duree_s", lambda v: durees.get(v, 0.0))
    monkeypatch.setattr(M, "libass_disponible", lambda: False)
    monkeypatch.setattr(M, "_monter",
                        lambda *a, **k: (sortie.write_bytes(b"v"), (True, ""))[1])

    m = assembler([str(p)], str(sortie), srt=str(srt))
    assert m.reussi
    assert not m.sous_titres, "ne pas promettre des sous-titres qu'on n'a pas mis"
    assert any("libass" in a for a in m.avertissements)


def test_un_srt_absent_est_signale_et_nempeche_pas_le_montage(monkeypatch, tmp_path):
    p = tmp_path / "a.mp4"
    p.write_bytes(b"x")
    sortie = tmp_path / "sortie.mp4"
    durees = {str(p): 4.0, str(sortie): 4.0}
    monkeypatch.setattr(M, "duree_s", lambda v: durees.get(v, 0.0))
    monkeypatch.setattr(M, "_monter",
                        lambda *a, **k: (sortie.write_bytes(b"v"), (True, ""))[1])

    m = assembler([str(p)], str(sortie), srt=str(tmp_path / "absent.srt"))
    assert m.reussi and not m.sous_titres
    assert any("introuvables" in a for a in m.avertissements)


# ── SRT ───────────────────────────────────────────────────────────────

def test_lhorodatage_srt_utilise_la_virgule():
    """Le point est le format WebVTT ; ffmpeg lit alors mal les bornes."""
    assert _horodatage(0) == "00:00:00,000"
    assert _horodatage(1.5) == "00:00:01,500"
    assert _horodatage(3661.234) == "01:01:01,234"


def test_un_segment_incoherent_est_ecarte(tmp_path):
    """ffmpeg accepte un SRT dont la fin précède le début, et affiche
    alors un sous-titre qui ne disparaît jamais."""
    chemin = str(tmp_path / "s.srt")
    n = ecrire_srt([
        {"debut": 0.0, "fin": 1.5, "texte": "bon"},
        {"debut": 5.0, "fin": 4.0, "texte": "à l'envers"},
        {"debut": 2.0, "fin": 3.0, "texte": "   "},
    ], chemin)
    assert n == 1
    contenu = open(chemin, encoding="utf-8").read()
    assert "bon" in contenu
    assert "envers" not in contenu


def test_les_sous_titres_sont_numerotes_sans_trou(tmp_path):
    """Un rang manquant fait ignorer la suite du fichier par certains
    lecteurs — et le montage sortirait alors à moitié sous-titré."""
    chemin = str(tmp_path / "s.srt")
    ecrire_srt([{"debut": 0, "fin": 1, "texte": "un"},
                {"debut": 5, "fin": 4, "texte": "rejete"},
                {"debut": 2, "fin": 3, "texte": "deux"}], chemin)
    rangs = [l for l in open(chemin, encoding="utf-8").read().splitlines()
             if l.isdigit()]
    assert rangs == ["1", "2"]
