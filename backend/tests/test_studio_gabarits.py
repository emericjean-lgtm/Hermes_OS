"""Un gabarit remplit, il ne décide pas (HOS-194).

La règle qui prime sur tout interdit qu'une seconde boucle décide à la
place de Hermes Agent. Ce module en est à la limite exacte, et ces tests
sont là pour qu'il n'en franchisse pas le bord : chaque valeur du graphe
doit venir d'un paramètre explicite ou d'un défaut mesuré et nommé.

Le jour où quelqu'un ajoutera « si la consigne parle de mouvement, mettre
plus d'images » — une inférence — c'est ici que ça doit casser.
"""

from __future__ import annotations

import pytest

from backend.studio.gabarits import (CATALOGUE, FORMATS, GabaritInvalide,
                                     composer, image_ltx, image_sdxl,
                                     plan_video)


def _types(graphe: dict) -> list[str]:
    return [n["class_type"] for n in graphe.values()]


# ── Ce que chaque gabarit produit ────────────────────────────────────

def test_le_plan_video_sort_une_video():
    g = plan_video("une rue de nuit")
    assert "SaveVideo" in _types(g)
    assert "SaveImage" not in _types(g)


def test_les_gabarits_dimage_sortent_une_image():
    for fabrique in (image_sdxl, lambda c: image_ltx(c, format_="paysage")):
        g = fabrique("une rue de nuit")
        assert "SaveImage" in _types(g)
        assert "SaveVideo" not in _types(g), "une image ne s'encode pas en vidéo"


def test_le_decodage_ltx_est_toujours_tuile():
    """`VAEDecode` non tuilé a produit un CUDA OOM en 1024 × 1024.

    Y compris pour une **image fixe** : j'avais supposé qu'une dimension
    temporelle valant un mettait à l'abri, et la mesure a dit non.
    """
    for g in (plan_video("x"), image_ltx("x")):
        assert "VAEDecodeTiled" in _types(g)
        assert "VAEDecode" not in _types(g)


def test_sdxl_ne_tuile_pas_et_charge_son_vae_corrige():
    """Le VAE de SDXL fait 335 Mio et passe en 45 s : tuiler coûterait
    sans rien rendre. Mais il se charge à part, celui du checkpoint
    produisant des artefacts en fp16."""
    g = image_sdxl("x")
    assert "VAEDecode" in _types(g) and "VAEDecodeTiled" not in _types(g)
    assert "VAELoader" in _types(g)


# ── Rien n'est inféré ─────────────────────────────────────────────────

def test_les_parametres_passes_se_retrouvent_dans_le_graphe():
    """Le test qui garde la frontière : ce qui sort vient de ce qui entre."""
    g = plan_video("consigne exacte", largeur=640, hauteur=360, images=25,
                   etapes=12, graine=777, cadence=30.0, negatif="flou")
    latent = g["6"]["inputs"]
    assert (latent["width"], latent["height"], latent["length"]) == (640, 360, 25)
    assert g["10"]["inputs"]["steps"] == 12
    assert g["11"]["inputs"]["noise_seed"] == 777
    assert g["7"]["inputs"]["frame_rate"] == 30.0
    assert g["4"]["inputs"]["text"] == "consigne exacte"
    assert g["5"]["inputs"]["text"] == "flou"


def test_un_format_nomme_donne_ses_dimensions_mesurees():
    for nom, (l, h) in FORMATS.items():
        g = plan_video("x", format_=nom)
        assert (g["6"]["inputs"]["width"], g["6"]["inputs"]["height"]) == (l, h)


def test_des_dimensions_explicites_priment_sur_le_format():
    g = plan_video("x", format_="portrait", largeur=800, hauteur=600)
    assert (g["6"]["inputs"]["width"], g["6"]["inputs"]["height"]) == (800, 600)


def test_sdxl_garde_ses_propres_reglages():
    """Vingt-cinq étapes et cfg 7, pas les huit d'un modèle distillé.

    Appliquer les réglages de LTX à SDXL l'appauvrirait, et le
    rapprochement serait d'autant plus tentant que les deux gabarits se
    ressemblent.
    """
    g = image_sdxl("x")
    assert g["6"]["inputs"]["steps"] == 25
    assert g["6"]["inputs"]["cfg"] == 7.0
    assert plan_video("x")["10"]["inputs"]["steps"] == 8


# ── Le son natif ──────────────────────────────────────────────────────

def test_sans_son_aucun_noeud_audio():
    g = plan_video("x")
    assert not [t for t in _types(g) if "Audio" in t]
    assert "audio" not in g["13"]["inputs"]


def test_avec_son_les_deux_latents_passent_dans_le_meme_echantillonnage():
    """C'est ce qui rend le son synchrone plutôt que juxtaposé.

    Si l'audio était échantillonné à part puis collé, rien ne le
    rattacherait à l'image — et c'est précisément ce que LTX apporte de
    plus qu'un TTS posé par-dessus.
    """
    g = plan_video("pluie", avec_son=True)
    assert "LTXVConcatAVLatent" in _types(g)
    assert "LTXVSeparateAVLatent" in _types(g)
    # L'échantillonneur reçoit le latent **fusionné**, pas le latent vidéo.
    assert g["11"]["inputs"]["latent_image"] == ["6c", 0]
    assert g["13"]["inputs"]["audio"] == ["13b", 0]


# ── Les refus ─────────────────────────────────────────────────────────

def test_une_consigne_vide_est_refusee():
    for fabrique in (plan_video, image_sdxl, image_ltx):
        with pytest.raises(GabaritInvalide, match="vide"):
            fabrique("   ")


def test_ltx_refuse_une_image_au_dela_de_ce_quil_rend(caplog):
    """1024 × 1024 n'a pas abouti et 1280 × 720 passe à 14,58 Gio sur
    15,98. Refuser vaut mieux que laisser déborder en silence — le
    débordement, lui, aboutit, dix-sept fois plus lentement."""
    with pytest.raises(GabaritInvalide, match="SDXL"):
        image_ltx("x", format_="carre")
    # SDXL, lui, tient ce format en 45 s mesurées.
    assert image_sdxl("x", format_="carre")


def test_un_format_inconnu_est_nomme():
    with pytest.raises(GabaritInvalide, match="format inconnu"):
        plan_video("x", format_="cinemascope")


def test_un_parametre_inconnu_est_refuse_pas_ignore():
    """Un réglage silencieusement écarté se lit comme un réglage qui
    « ne fait rien » — le pire des deux, puisqu'on le croit appliqué."""
    with pytest.raises(GabaritInvalide, match="inconnu"):
        composer("plan_video", "x", nombre_de_licornes=3)


def test_un_gabarit_inconnu_nomme_ceux_qui_existent():
    with pytest.raises(GabaritInvalide, match="image_sdxl"):
        composer("magie", "x")


# ── Le catalogue ──────────────────────────────────────────────────────

def test_chaque_gabarit_nomme_des_formats_quil_sait_rendre():
    """Le défaut qui a produit une image tuilee.

    Un premier formulaire offrait la meme liste de formats aux deux
    moteurs. Un rendu SDXL est parti en 768 x 432 — valide pour LTX,
    ruineux pour SDXL, qui est entraine autour du megapixel — et l'image
    est sortie deformee. Rien ne l'avait signale : le graphe etait
    correct, le rendu a abouti, seul le resultat etait mauvais.
    """
    from backend.studio.gabarits import FORMATS_PAR_MOTEUR

    for nom, fiche in CATALOGUE.items():
        assert fiche["formats"], f"{nom} n'offre aucun format"
        for f in fiche["formats"]:
            assert f in FORMATS, f"{nom} propose {f}, absent de FORMATS"
        # Le premier est le defaut, et il doit composer.
        assert composer(nom, "x", format_=fiche["formats"][0])

    # Les deux moteurs n'ont aucun format en commun : c'est la separation
    # qui protege, et la voir disparaitre serait le retour du defaut.
    ltx = set(FORMATS_PAR_MOTEUR["ltx"])
    sdxl = set(FORMATS_PAR_MOTEUR["sdxl"])
    assert not (ltx & sdxl), "un format commun laisserait choisir le mauvais"


def test_les_formats_sdxl_sont_autour_du_megapixel():
    """SDXL s'effondre loin de ses compartiments d'entrainement."""
    from backend.studio.gabarits import FORMATS_PAR_MOTEUR

    for nom in FORMATS_PAR_MOTEUR["sdxl"]:
        l, h = FORMATS[nom]
        assert 0.8e6 <= l * h <= 1.2e6, f"{nom} ({l}x{h}) hors du megapixel"


def test_le_catalogue_decrit_exactement_ce_qui_se_compose():
    """L'écran lit ce catalogue. S'il annonçait un gabarit qui n'existe
    pas, le bouton échouerait au clic et non à l'affichage."""
    for nom, fiche in CATALOGUE.items():
        assert composer(nom, "une consigne")
        assert fiche["sortie"] in ("image", "video")
        assert fiche["titre"] and fiche["moteur"] and fiche["note"]
