"""Ce qu'il fallait ajouter au montage pour produire une vidéo (HOS-211).

Trois manques bloquaient le cahier de production, et un defaut deja
present s'est revele en les eprouvant.

Ces tests passent par de **vrais** fichiers ffmpeg. Un montage se juge sur
le fichier obtenu, jamais sur le code de retour — c'est la raison d'etre
de `montage.py`, et un test qui simulerait ffmpeg ne prouverait rien de ce
que ce module existe pour prouver.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from backend.studio import montage
from backend.studio.relecteur import ffmpeg

ff = ffmpeg()
sans_ffmpeg = pytest.mark.skipif(not ff, reason="ffmpeg absent")


def _plan(dossier, nom, *, secondes=2.0, largeur=704, hauteur=1280):
    c = os.path.join(dossier, nom)
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i",
                    f"testsrc2=size={largeur}x{hauteur}:duration={secondes}:rate=24",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", c],
                   check=True)
    return c


def _son(dossier, nom, secondes, frequence=300):
    c = os.path.join(dossier, nom)
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i",
                    f"sine=frequency={frequence}:duration={secondes}",
                    "-ar", "24000", "-ac", "1", "-y", c], check=True)
    return c


def _image(dossier, nom, largeur=768, hauteur=1344):
    c = os.path.join(dossier, nom)
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i",
                    f"testsrc2=size={largeur}x{hauteur}:duration=1:rate=1",
                    "-frames:v", "1", "-y", c], check=True)
    return c


def _sonde(fichier, champs):
    import json
    ffp = ff.replace("ffmpeg.EXE", "ffprobe.exe").replace("ffmpeg.exe", "ffprobe.exe")
    out = subprocess.run([ffp, "-v", "error", "-show_entries",
                          f"stream={champs}", "-of", "json", fichier],
                         capture_output=True, text=True).stdout
    return json.loads(out)["streams"]


# ── L'image fixe devient un plan ─────────────────────────────────────

@sans_ffmpeg
def test_une_image_fixe_devient_un_plan_au_format_des_autres(tmp_path):
    """Sans ca, quatre plans du cahier ne peuvent pas entrer au montage.

    `concat` enchaine des flux video : un PNG n'en est pas un. Et il exige
    que tous les plans partagent leur resolution — un plan anime qui
    differerait ferait echouer l'assemblage a la toute fin, apres deux
    heures de rendu.
    """
    m = montage.animer(_image(str(tmp_path), "ref.png"),
                       str(tmp_path / "anime.mp4"), duree_s=3.0)
    assert m.reussi, m.erreur
    v = _sonde(str(tmp_path / "anime.mp4"), "width,height,r_frame_rate,pix_fmt")[0]
    assert (v["width"], v["height"]) == (704, 1280)
    assert v["r_frame_rate"] == "24/1"
    assert v["pix_fmt"] == "yuv420p"


@sans_ffmpeg
def test_un_plan_anime_dure_ce_qu_on_a_demande(tmp_path):
    # Un `zoompan` dont le compte d'images est faux rend une video plus
    # courte avec le code 0 : le manque ne se verrait qu'au visionnage.
    m = montage.animer(_image(str(tmp_path), "ref.png"),
                       str(tmp_path / "a.mp4"), duree_s=4.0)
    assert m.reussi, m.erreur
    assert abs(m.duree_s - 4.0) <= montage.TOLERANCE_S


@sans_ffmpeg
def test_une_image_absente_ne_produit_pas_un_plan_vide(tmp_path):
    m = montage.animer(str(tmp_path / "rien.png"), str(tmp_path / "a.mp4"))
    assert not m.reussi
    assert "introuvable" in m.erreur


# ── La voix, recollee avec ses respirations ──────────────────────────

@sans_ffmpeg
def test_les_pauses_sont_reellement_dans_la_narration(tmp_path):
    """Chatterbox ne produit pas de respirations : il lit ce qu'on donne.

    Les pauses du cahier de production n'existent que si quelque chose les
    intercale.
    """
    d = str(tmp_path)
    segments = [_son(d, "a.wav", 1.2), _son(d, "b.wav", 0.8, 420),
                _son(d, "c.wav", 2.0, 540)]
    m = montage.coller_voix(segments, str(tmp_path / "voix.wav"),
                            pauses_s=[0.5, 0.9])
    assert m.reussi, m.erreur
    assert abs(m.duree_s - (1.2 + 0.5 + 0.8 + 0.9 + 2.0)) <= montage.TOLERANCE_S


@sans_ffmpeg
def test_une_replique_manquante_n_est_pas_collee_en_silence(tmp_path):
    # Une narration amputee s'entend, mais sa duree ne la trahit pas :
    # elle est simplement plus courte, sans erreur.
    d = str(tmp_path)
    m = montage.coller_voix([_son(d, "a.wav", 1.0), str(tmp_path / "absent.wav")],
                            str(tmp_path / "v.wav"))
    assert not m.reussi
    assert "introuvable" in m.erreur


# ── Le defaut trouve en eprouvant le reste ───────────────────────────

@sans_ffmpeg
def test_une_narration_plus_courte_ne_tronque_pas_l_image(tmp_path):
    """Le commentaire disait « l'image commande » ; `-shortest` disait non.

    Mesure : trois plans de 6,0 s avec une voix de 5,4 s rendaient une
    video de 5,4 s — les six derniers dixiemes de seconde d'image
    simplement absents, sans erreur et sans avertissement sur la duree.
    """
    d = str(tmp_path)
    plans = [_plan(d, f"p{i}.mp4", secondes=2.0) for i in range(3)]
    m = montage.assembler(plans, str(tmp_path / "f.mp4"),
                          narration=_son(d, "voix.wav", 5.4))
    assert m.reussi, m.erreur
    assert abs(m.duree_s - 6.0) <= montage.TOLERANCE_S, \
        "l'image doit commander, y compris quand la voix est plus courte"


# ── Ambiance et mise a l'echelle ─────────────────────────────────────

@sans_ffmpeg
def test_l_ambiance_est_bouclee_et_ne_raccourcit_pas_le_montage(tmp_path):
    # Un lit sonore plus court que la video laisserait un silence a la
    # fin, que rien dans la duree du fichier ne signalerait.
    d = str(tmp_path)
    plans = [_plan(d, f"p{i}.mp4", secondes=2.0) for i in range(3)]
    m = montage.assembler(plans, str(tmp_path / "f.mp4"),
                          narration=_son(d, "voix.wav", 6.0),
                          ambiance=_son(d, "amb.wav", 1.5, 90))
    assert m.reussi, m.erreur
    assert m.ambiance
    assert abs(m.duree_s - 6.0) <= montage.TOLERANCE_S


@sans_ffmpeg
def test_une_ambiance_introuvable_est_dite_et_non_supposee(tmp_path):
    d = str(tmp_path)
    m = montage.assembler([_plan(d, "p.mp4", secondes=2.0)],
                          str(tmp_path / "f.mp4"),
                          ambiance=str(tmp_path / "rien.wav"))
    assert m.reussi, m.erreur
    assert not m.ambiance, "ne pas annoncer une ambiance qu'on n'a pas mixee"
    assert any("ambiance" in a for a in m.avertissements)


@sans_ffmpeg
def test_la_sortie_est_agrandie_a_la_taille_demandee(tmp_path):
    d = str(tmp_path)
    m = montage.assembler([_plan(d, "p.mp4", secondes=2.0)],
                          str(tmp_path / "f.mp4"), echelle=(1080, 1920))
    assert m.reussi, m.erreur
    v = _sonde(str(tmp_path / "f.mp4"), "width,height")[0]
    assert (v["width"], v["height"]) == (1080, 1920)
    assert m.echelle == (1080, 1920)


@sans_ffmpeg
def test_les_sous_titres_sont_incrustes_avant_l_agrandissement(tmp_path):
    """Les incruster puis agrandir les rendrait flous.

    Le test ne peut pas lire la nettete du texte ; il verifie l'ordre des
    filtres, qui est ce qui la determine.
    """
    d = str(tmp_path)
    srt = tmp_path / "st.srt"
    srt.write_text("1\n00:00:00,200 --> 00:00:01,500\nTexte.\n",
                   encoding="utf-8")
    m = montage.assembler([_plan(d, "p.mp4", secondes=2.0)],
                          str(tmp_path / "f.mp4"), srt=str(srt),
                          echelle=(1080, 1920))
    assert m.reussi, m.erreur
    if m.sous_titres:
        v = _sonde(str(tmp_path / "f.mp4"), "width,height")[0]
        assert (v["width"], v["height"]) == (1080, 1920)
