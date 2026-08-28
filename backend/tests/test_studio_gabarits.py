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

from backend.studio.gabarits import (CATALOGUE, FORMATS, FORMATS_PAR_MOTEUR,
                                     IMAGES_MAX,
                                     MODELES_INTERPOLATION, duree_calcul_s,
                                     PAS_IMAGES, GabaritInvalide, composer,
                                     duree_reelle_s, image_ltx, image_sdxl,
                                     images_pour_duree, plan_video)


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


# ── La durée, et pourquoi elle se compte en images (HOS-199) ─────────
#
# L'utilisateur ne pouvait pas choisir la durée d'un plan : le formulaire
# offrait « images », qui *est* la durée, sans que rien ne le dise. La
# conversion vit ici plutôt que dans l'écran, avec la contrainte qu'elle
# doit respecter — LTX n'accepte que des longueurs `8k + 1`.

class TestDureeEtImages:
    def test_les_longueurs_rendues_sont_celles_que_ltx_accepte(self):
        # `8k + 1` : la forme mesurée sur les rendus réels de ce projet.
        for secondes in (0.5, 1, 2, 3, 4, 5, 7.5, 10, 30):
            n = images_pour_duree(secondes)
            assert (n - 1) % PAS_IMAGES == 0, f"{secondes}s -> {n} images"

    def test_les_durees_entieres_a_24_tombent_sur_les_valeurs_mesurees(self):
        # 49 images pour 2 s et 97 pour 4 s sont les deux longueurs
        # effectivement rendues et chronométrées (docs/studio-center.md).
        # Si cette correspondance se casse, les mesures consignées ne
        # décrivent plus ce que l'écran produit.
        assert images_pour_duree(2) == 49
        assert images_pour_duree(4) == 97

    def test_la_duree_reelle_se_calcule_et_ne_se_suppose_pas(self):
        # Une image de plus que la durée exacte : 49/24 vaut 2,04 s et non
        # 2,00. L'écart est petit mais il doit être affichable, sinon
        # l'écran annonce une durée qu'il ne rend pas.
        assert duree_reelle_s(49) == pytest.approx(2.0417, abs=1e-3)
        assert duree_reelle_s(97) == pytest.approx(4.0417, abs=1e-3)

    def test_la_longueur_est_plafonnee_plutot_que_de_deborder(self):
        # Vingt secondes demandées, c'est presque deux heures de calcul à
        # cinq minutes la seconde. Le plafond est celui du gabarit, pas
        # une opinion de l'écran.
        assert images_pour_duree(20) == IMAGES_MAX
        assert images_pour_duree(1000) == IMAGES_MAX

    def test_une_duree_nulle_ou_negative_rend_au_moins_une_image(self):
        assert images_pour_duree(0) >= 1
        assert images_pour_duree(-5) >= 1

    def test_la_cadence_change_la_longueur_pour_une_meme_duree(self):
        # Deux secondes à 30 im/s, ce n'est pas deux secondes à 24 : c'est
        # exactement le piège que la note de ce module signalait — changer
        # la cadence change la durée sans le dire. Ici elle est prise en
        # compte, donc la durée demandée reste tenue.
        assert duree_reelle_s(images_pour_duree(2, 30.0), 30.0) == pytest.approx(2, abs=0.2)
        assert duree_reelle_s(images_pour_duree(2, 24.0), 24.0) == pytest.approx(2, abs=0.2)


# ── Ce que le catalogue offre à l'écran ──────────────────────────────

class TestCatalogueOffreCeQueLesGabaritsAcceptent:
    def test_aucun_parametre_annonce_n_est_refuse_par_sa_fabrique(self):
        # Le défaut inverse a existé pendant cinq versions : `negatif`,
        # `prefixe` et `cadence` étaient implémentés, testés, et absents du
        # catalogue — donc invisibles dans l'écran. Un paramètre annoncé
        # que `composer` refuserait serait le symétrique, et pire.
        for nom, fiche in CATALOGUE.items():
            for p in fiche["parametres"]:
                kwarg = "format_" if p == "format" else p
                composer(nom, "une consigne", **{kwarg: _valeur_plausible(kwarg)})

    def test_le_prompt_negatif_arrive_bien_dans_le_graphe(self):
        g = composer("plan_video", "une rue", negatif="flou, texte")
        textes = [n["inputs"]["text"] for n in g.values()
                  if n["class_type"] == "CLIPTextEncode"]
        assert "flou, texte" in textes

    def test_le_prefixe_nomme_le_fichier_de_sortie(self):
        g = composer("image_sdxl", "un portrait", prefixe="studio/essai_7")
        sortie = [n for n in g.values() if n["class_type"] == "SaveImage"][0]
        assert sortie["inputs"]["filename_prefix"] == "studio/essai_7"


def _valeur_plausible(kwarg: str):
    return {
        "format_": "paysage", "images": 49, "cadence": 24.0, "etapes": 8,
        "graine": 0, "cfg": 7.0, "avec_son": False, "negatif": "flou",
        "prefixe": "studio/essai",
        # `portrait` et non `paysage` : le depart sur image exige des
        # cotes multiples de 32 (HOS-200), et 432 n'en est pas un.
        "image_depart": None, "interpolation": "aucune",
    }[kwarg]


class TestCoutDeCalcul:
    """L'estimation annoncée avant le clic (HOS-199).

    L'écran promettait « ≈ 5 min par seconde de vidéo finie ». La règle
    venait du seul rendu vertical et ne valait que pour lui.
    """

    #: Les trois rendus réellement chronométrés (`docs/studio-center.md`).
    MESURES = [((512, 288), 49, 170), ((768, 432), 49, 251),
               ((704, 1280), 97, 1218)]

    def test_l_estimation_tient_les_trois_mesures_a_moins_de_15_pour_cent(self):
        for (l, h), images, reel in self.MESURES:
            estime = duree_calcul_s(l, h, images)
            ecart = abs(estime - reel) / reel
            assert ecart < 0.15, (
                f"{l}×{h}, {images} images : {estime:.0f} s estimées contre "
                f"{reel} s mesurées ({ecart:.0%})")

    def test_l_ancienne_regle_se_trompait_bien_de_plus_du_double(self):
        # Ce test garde la *raison* du changement. Si quelqu'un revient à
        # « 5 min par seconde » en trouvant la formule compliquée, il verra
        # ici ce que cette simplicité coûtait — et sur quel rendu.
        for (l, h), images, reel in self.MESURES[:2]:
            ancienne = (images / 24.0) * 5 * 60
            assert ancienne > reel * 2, (
                f"{l}×{h} : l'ancienne règle donnait {ancienne:.0f} s pour "
                f"{reel} s réelles")

    def test_le_cout_croit_avec_la_surface_pas_seulement_avec_la_duree(self):
        # C'est tout le defaut de l'ancienne regle : a nombre d'images egal,
        # un format quatre fois plus grand ne coutait pas plus cher.
        petit = duree_calcul_s(512, 288, 49)
        grand = duree_calcul_s(1280, 720, 49)
        assert grand > petit * 2


class TestDepartSurImage:
    """Enchainer deux plans en gardant decor et personnages (HOS-200)."""

    def test_sans_image_le_plan_part_du_bruit_comme_avant(self):
        g = plan_video("une rue")
        assert "LTXVImgToVideo" not in _types(g)
        assert g["11"]["inputs"]["latent_image"] == ["6", 0]

    def test_avec_image_le_conditionnement_vient_de_l_image(self):
        g = plan_video("une rue", format_="portrait", image_depart="fin.png")
        assert "LTXVImgToVideo" in _types(g)
        # Le conditionnement du sampler doit passer par le noeud d'image,
        # sinon l'image est chargee, payee, et ignoree.
        assert g["7"]["inputs"]["positive"] == ["6i", 0]
        assert g["11"]["inputs"]["latent_image"] == ["6i", 2]

    def test_avec_son_le_latent_concatene_est_celui_de_l_image(self):
        # Le defaut que ce test empeche : `LTXVConcatAVLatent` cable en dur
        # sur le latent vide. Le plan repartait alors du bruit des qu'on
        # demandait le son, en perdant sa continuite, sans aucune erreur.
        g = plan_video("une rue", format_="portrait", image_depart="fin.png",
                       avec_son=True)
        assert g["6c"]["inputs"]["video_latent"] == ["6i", 2]

    def test_une_taille_non_multiple_de_32_est_refusee_avant_le_rendu(self):
        # Mesure : accepte, le plan occupe la carte et echoue SEPT MINUTES
        # plus tard sur une erreur einops illisible. Refuser coute une
        # milliseconde.
        #
        # Les formats du catalogue passent tous depuis HOS-202 — ils
        # declarent enfin la taille que LTX rend vraiment. Le garde-fou
        # protege donc les tailles libres, seule voie qui reste pour lui
        # soumettre une hauteur impaire.
        with pytest.raises(GabaritInvalide, match="multiples de 32"):
            plan_video("une rue", largeur=768, hauteur=432,
                       image_depart="fin.png")

    def test_les_formats_annonces_comme_compatibles_le_sont_vraiment(self):
        for nom in FORMATS_PAR_MOTEUR["ltx"]:
            l, h = FORMATS[nom]
            if l % 32 or h % 32:
                continue
            plan_video("une rue", format_=nom, image_depart="fin.png")


class TestInterpolation:
    """L'interpolation d'images, integree au rendu (HOS-200)."""

    def test_sans_interpolation_la_cadence_de_sortie_est_celle_demandee(self):
        g = plan_video("une rue", cadence=24.0)
        assert g["13"]["inputs"]["fps"] == 24.0
        assert g["13"]["inputs"]["images"] == ["12", 0]

    def test_la_cadence_est_multipliee_pour_que_la_duree_ne_change_pas(self):
        # Sans ce doublement, interpoler x2 rendrait un ralenti : deux fois
        # plus d'images jouees a la meme cadence, donc deux fois plus long.
        g = plan_video("une rue", cadence=24.0, interpolation="film")
        assert g["13"]["inputs"]["fps"] == 48.0
        assert g["13"]["inputs"]["images"] == ["12j", 0]

    def test_l_interpolation_se_place_apres_le_decodage(self):
        # `FrameInterpolate` travaille sur des images, pas des latents.
        g = plan_video("une rue", interpolation="rife")
        assert g["12j"]["inputs"]["images"] == ["12", 0]

    def test_chaque_modele_annonce_designe_un_fichier(self):
        for cle in MODELES_INTERPOLATION:
            g = plan_video("une rue", interpolation=cle)
            assert g["12i"]["inputs"]["model_name"] == MODELES_INTERPOLATION[cle]

    def test_un_modele_inconnu_est_refuse_en_le_nommant(self):
        with pytest.raises(GabaritInvalide, match="interpolation inconnue"):
            plan_video("une rue", interpolation="rife_v9000")



class TestFormatsReels:
    """Les formats declares doivent etre ceux que LTX rend (HOS-202).

    `paysage` annoncait 768 x 432 et `paysage_large` 1280 x 720. `ffprobe`
    sur les fichiers reels donne 768 x 416 et 1280 x 704 : LTX ramene la
    hauteur au multiple de 32 inferieur, en silence. Une taille declaree
    que le modele ne produit pas fausse le calcul de cout, le choix de
    format, et le garde-fou du depart sur image.
    """

    def test_tous_les_formats_ltx_sont_des_multiples_de_32(self):
        for nom in FORMATS_PAR_MOTEUR["ltx"]:
            l, h = FORMATS[nom]
            assert l % 32 == 0 and h % 32 == 0, f"{nom} = {l}x{h}"

    def test_les_formats_ltx_acceptent_donc_tous_le_depart_sur_image(self):
        # Corollaire du precedent, et c'est ce qui rend les variantes
        # « suite » de HOS-200 inutiles : elles n'existaient que parce que
        # les formats mentaient sur leur hauteur.
        for nom in FORMATS_PAR_MOTEUR["ltx"]:
            plan_video("une rue", format_=nom, image_depart="fin.png")

    def test_les_variantes_suite_ont_disparu(self):
        for mort in ("paysage_suite", "paysage_large_suite"):
            assert mort not in FORMATS


class TestDecoupageTemporelDuVAE:
    """Le scintillement venait d'un decodage en trop petits morceaux
    (HOS-205).

    `VAEDecodeTiled` divise `temporal_size` par la compression temporelle
    du VAE — 8 pour LTX. A 16, cela faisait deux images latentes par
    tuile : un plan de 49 images (7 latentes) etait reconstruit a partir
    de SIX morceaux, un plan de 257 images a partir de trente-deux.

    Mesure a latents identiques, sur un plan a camera fixe ou toute
    vitesse est un artefact : la derive fantome passe de 0,108 a 0,035
    (graine 777) et de 0,110 a 0,065 (graine 1234). Confirme a l'oeil par
    l'utilisateur, et corrobore par le poids des fichiers a qualite
    constante — 30 % de bits en moins.
    """

    #: Ce que `nodes.py` applique : `temporal_size // compression`.
    COMPRESSION_TEMPORELLE_LTX = 8

    def _latentes_par_tuile(self, temporal_size):
        return max(2, temporal_size // self.COMPRESSION_TEMPORELLE_LTX)

    def test_un_plan_de_deux_secondes_se_decode_d_un_seul_bloc(self):
        g = plan_video("une rue", images=49)
        ts = g["12"]["inputs"]["temporal_size"]
        latentes_du_plan = (49 - 1) // self.COMPRESSION_TEMPORELLE_LTX + 1
        assert self._latentes_par_tuile(ts) >= latentes_du_plan, (
            f"temporal_size={ts} donne {self._latentes_par_tuile(ts)} latentes "
            f"par tuile pour un plan qui en compte {latentes_du_plan} : le plan "
            "serait recolle a partir de plusieurs morceaux, et c'est "
            "exactement le defaut que HOS-205 a corrige.")

    def test_le_reglage_fautif_ne_revient_pas(self):
        # 16 est la valeur d'origine. Le message porte la raison, pour que
        # quiconque la remette sache ce qu'elle coutait.
        ts = plan_video("une rue")["12"]["inputs"]["temporal_size"]
        assert ts != 16, (
            "temporal_size=16 est revenu. Il donne deux latentes par tuile, "
            "donc six morceaux pour un plan de 49 images et trente-deux pour "
            "un plan de 257 — c'est la cause mesuree du scintillement.")

    def test_le_decodage_reste_tuile(self):
        # Le non-tuile echoue vraiment sur cette carte : `CUDA out of
        # memory`, 10,51 Gio demandes d'un bloc, re-mesure en HOS-205. Le
        # correctif elargit la tuile, il ne la supprime pas.
        assert plan_video("une rue")["12"]["class_type"] == "VAEDecodeTiled"
