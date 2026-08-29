"""Un plan qui repart du precedent, et ce qui l'en empeche (HOS-211).

Le defaut que ces tests empechent n'est pas une erreur : c'est un
**succes**. Un plan enchaine dont le predecesseur n'a rien produit
repartirait du bruit, rendrait un MP4 parfaitement valide, et la rupture
de continuite ne se verrait qu'au montage — apres la nuit.

C'est exactement la forme de defaut que ce projet paie le plus cher :
`success: True` au-dessus de rien.
"""

from __future__ import annotations

import os

import pytest

from backend.studio import enchainement
from backend.studio.file_de_nuit import Etat, Plan, derouler


class _Rendu:
    def __init__(self, fichiers, acheve=True, erreur=None):
        self.fichiers = fichiers
        self.acheve = acheve
        self.erreur = erreur
        self.duree_s = 1.0
        self.pic_vram_octets = 0


class _Verdict:
    correspond = True
    confiance = 90
    defauts: list[str] = []
    raison = ""


def _file(plans, *, rendus=None, composer=None, preparer=None):
    """Derouler sans GPU, sans ComfyUI et sans ffmpeg.

    Un relecteur qui dit oui est injecte : sans lui tout plan finirait
    `indetermine`, ce qui est correct mais rendrait ces tests aveugles a
    la difference entre « rendu » et « pas rendu ».
    """
    rendus = rendus or {}
    soumis: list[dict] = []
    compteur = {"n": 0}

    def soumettre(graphe):
        soumis.append(graphe)
        return f"id_{len(soumis)}"

    def attendre(identifiant):
        n = compteur["n"]
        compteur["n"] += 1
        return rendus.get(n, _Rendu([f"E:/rendus/plan_{n}.mp4"]))

    rapport = derouler(
        plans, soumettre=soumettre, attendre=attendre,
        relire=lambda fichier, consigne: _Verdict(),
        composer=composer or (lambda g, c, **p: {"gabarit": g, **p}),
        preparer_depart=preparer or (lambda f, nom: f"{nom}.png"))
    rapport.soumis = soumis  # type: ignore[attr-defined]
    return rapport


# ── L'enchainement nominal ────────────────────────────────────────────

def test_un_plan_enchaine_recoit_l_image_du_precedent():
    plans = [
        Plan(identifiant="a", consigne="rue de nuit", gabarit="plan_video"),
        Plan(identifiant="b", consigne="la suite", gabarit="plan_video",
             depend_de="a"),
    ]
    r = _file(plans)
    assert [p.etat for p in r.plans] == [Etat.RETENU, Etat.RETENU]
    assert r.soumis[1]["image_depart"] == "depart_b.png"


def test_le_depart_vient_du_fichier_reellement_produit():
    # Et non d'un nom devine a partir de l'identifiant : un plan peut
    # rendre plusieurs fichiers, ou un nom que le prefixe ne predit pas.
    vus = []
    plans = [
        Plan(identifiant="a", consigne="x", gabarit="plan_video"),
        Plan(identifiant="b", consigne="y", gabarit="plan_video", depend_de="a"),
    ]
    _file(plans,
          rendus={0: _Rendu(["E:/rendus/ailleurs/AUTRE_00042.mp4"])},
          preparer=lambda f, nom: vus.append(f) or "ok.png")
    assert vus == ["E:/rendus/ailleurs/AUTRE_00042.mp4"]


def test_une_chaine_de_trois_plans_se_deroule():
    # 01 -> 02A -> 02B du cahier de production.
    plans = [
        Plan(identifiant="p01", consigne="a", gabarit="plan_video"),
        Plan(identifiant="p02a", consigne="b", gabarit="plan_video",
             depend_de="p01"),
        Plan(identifiant="p02b", consigne="c", gabarit="plan_video",
             depend_de="p02a"),
    ]
    r = _file(plans)
    assert all(p.etat == Etat.RETENU for p in r.plans)
    assert r.soumis[2]["image_depart"] == "depart_p02b.png"


# ── Ce qui doit s'arreter plutot que de rendre du bruit ───────────────

def test_un_plan_dont_le_predecesseur_a_echoue_n_est_pas_rendu():
    """Le defaut central : il rendrait un MP4 valide, sans continuite."""
    plans = [
        Plan(identifiant="a", consigne="x", gabarit="plan_video"),
        Plan(identifiant="b", consigne="y", gabarit="plan_video", depend_de="a"),
    ]
    r = _file(plans, rendus={0: _Rendu([], acheve=False, erreur="deborde")})
    assert r.plans[0].etat == Etat.ECHOUE
    assert r.plans[1].etat == Etat.ABANDONNE
    assert "a" in r.plans[1].raison
    assert len(r.soumis) == 1, "le plan enchaine ne doit pas partir"


def test_un_plan_sans_fichier_ne_sert_pas_de_source():
    # Acheve, mais rien sur le disque : le cas ou `success` ment.
    plans = [
        Plan(identifiant="a", consigne="x", gabarit="plan_video"),
        Plan(identifiant="b", consigne="y", gabarit="plan_video", depend_de="a"),
    ]
    r = _file(plans, rendus={0: _Rendu([], acheve=True)})
    assert r.plans[1].etat == Etat.ABANDONNE


def test_une_dependance_vers_l_aval_est_refusee():
    # Elle attendrait un fichier qui n'existera jamais.
    plans = [
        Plan(identifiant="a", consigne="x", gabarit="plan_video", depend_de="b"),
        Plan(identifiant="b", consigne="y", gabarit="plan_video"),
    ]
    r = _file(plans)
    assert r.plans[0].etat == Etat.ABANDONNE
    assert "après" in r.plans[0].raison


def test_une_dependance_rompue_n_arrete_pas_la_file():
    """Trois plans qui dependent du meme absent ne sont pas trois echecs.

    Les compter comme tels atteindrait `ECHECS_AVANT_ARRET` et perdrait
    les plans independants qui suivent, alors qu'un seul defaut est en
    cause.
    """
    plans = [
        Plan(identifiant="a", consigne="x", gabarit="plan_video"),
        *[Plan(identifiant=f"d{i}", consigne="y", gabarit="plan_video",
               depend_de="a") for i in range(3)],
        Plan(identifiant="libre", consigne="z", gabarit="plan_video"),
    ]
    r = _file(plans, rendus={0: _Rendu([], acheve=False, erreur="deborde")})
    assert [p.etat for p in r.plans[1:4]] == [Etat.ABANDONNE] * 3
    assert r.plans[4].etat == Etat.RETENU, "le plan independant doit passer"
    assert not r.arret_anticipe


# ── La voie de Hermes Agent reste intacte ────────────────────────────

def test_un_graphe_deja_compose_n_est_pas_recompose():
    appels = []
    plans = [Plan(identifiant="a", consigne="x", graphe={"1": {"deja": True}})]
    r = _file(plans, composer=lambda *a, **k: appels.append(a) or {})
    assert appels == []
    assert r.soumis[0] == {"1": {"deja": True}}
    assert r.plans[0].etat == Etat.RETENU


# ── preparer_depart, sur de vrais fichiers ───────────────────────────

def test_une_image_est_copiee_telle_quelle(tmp_path):
    src = tmp_path / "ref.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    dest = tmp_path / "input"
    nom = enchainement.preparer_depart(str(src), "p01", dossier=str(dest))
    assert nom == "p01.png"
    assert (dest / "p01.png").read_bytes() == src.read_bytes()


def test_un_fichier_absent_leve_au_lieu_de_rendre_un_nom(tmp_path):
    # Rendre un nom qui ne chargerait pas ferait repartir le plan du bruit.
    with pytest.raises(enchainement.DepartImpossible):
        enchainement.preparer_depart(str(tmp_path / "rien.png"),
                                     dossier=str(tmp_path))


def test_une_extension_inconnue_est_refusee_et_non_devinee(tmp_path):
    src = tmp_path / "chose.bin"
    src.write_bytes(b"0" * 32)
    with pytest.raises(enchainement.DepartImpossible) as e:
        enchainement.preparer_depart(str(src), dossier=str(tmp_path / "in"))
    assert "extension" in str(e.value)


def test_le_nom_ne_peut_pas_sortir_du_dossier_d_entree(tmp_path):
    src = tmp_path / "ref.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 8)
    dest = tmp_path / "input"
    nom = enchainement.preparer_depart(str(src), r"..\..\evade", dossier=str(dest))
    assert nom == "evade.png"
    assert os.path.isfile(dest / "evade.png")


def test_la_taille_visee_suit_le_plan_qui_enchaine():
    """Sans elle, une reference SDXL serait etiree, en silence.

    `LTXVImgToVideo` recoit les dimensions du plan et redimensionne
    **sans recadrer** : une image en 768 x 1344 (rapport 0,571) donnee a
    un plan en 704 x 1280 (0,550) est deformee. Visible sur un visage,
    et aucune erreur ne le dit.
    """
    vus = {}
    plans = [
        Plan(identifiant="ref", consigne="x", gabarit="image_sdxl"),
        Plan(identifiant="clip", consigne="y", gabarit="plan_video",
             parametres={"format_": "portrait"}, depend_de="ref"),
    ]
    _file(plans, rendus={0: _Rendu(["E:/rendus/ref_00001.png"])},
          preparer=lambda f, nom, **kw: vus.update(kw) or "ok.png")
    assert vus == {"largeur": 704, "hauteur": 1280}


def test_un_format_inconnu_ne_fait_pas_recadrer_au_hasard():
    # Recadrer au mauvais rapport serait pire que ne pas recadrer.
    vus = {"appele": False}
    plans = [
        Plan(identifiant="ref", consigne="x", gabarit="image_sdxl"),
        Plan(identifiant="clip", consigne="y", gabarit="plan_video",
             parametres={"format_": "inexistant"}, depend_de="ref"),
    ]
    _file(plans, rendus={0: _Rendu(["E:/rendus/ref.png"])},
          preparer=lambda f, nom, **kw: vus.update(kw, appele=True) or "ok.png")
    assert vus == {"appele": True}, "aucune dimension passee"


def test_une_image_de_rapport_different_est_recadree_et_non_etiree(tmp_path):
    import subprocess

    from backend.studio.relecteur import ffmpeg

    ff = ffmpeg()
    if not ff:
        pytest.skip("ffmpeg absent")
    src = tmp_path / "sdxl.png"
    subprocess.run([ff, "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=768x1344:duration=1:rate=1",
                    "-frames:v", "1", "-y", str(src)], check=True)
    dest = tmp_path / "input"
    enchainement.preparer_depart(str(src), "p01", dossier=str(dest),
                                 largeur=704, hauteur=1280)

    ffp = ff.replace("ffmpeg.EXE", "ffprobe.exe").replace("ffmpeg.exe", "ffprobe.exe")
    out = subprocess.run([ffp, "-v", "error", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0",
                          str(dest / "p01.png")],
                         capture_output=True, text=True).stdout.strip()
    assert out.startswith("704,1280"), out


def test_le_relecteur_sait_lire_une_image_fixe(tmp_path):
    """Une image n'a pas de duree, donc l'extracteur ne rendait rien.

    Consequence vue en production : les sept references SDXL d'une nuit
    finissaient toutes `indetermine`, jamais confrontees a leur consigne
    — alors que ce sont elles qui decident du decor de tous les plans qui
    en decoulent.
    """
    from backend.studio import relecteur

    img = tmp_path / "ref.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    assert relecteur.extraire(str(img), 3) == [str(img)], \
        "une image fixe est son propre cadre"
