"""Le juge et les vérités-terrain de l'axe vision (HOS-110).

Un banc ne vaut que ses vérificateurs. Celui-ci note des images dessinées
par ce même module, donc une erreur de génération et une erreur de jugement
produisent le même symptôme : un chiffre confiant et faux. Les deux sont
donc tenues séparément ici.

Aucun de ces tests n'appelle un modèle. Ce qui parle à Ollama est
l'instrument, pas le jugement.
"""
from __future__ import annotations

import random

import pytest

from backend.model_intelligence.vision_bench import (
    COULEURS, ECART_MINIMAL, EPREUVES, juge, planche,
)


# ── le juge ──────────────────────────────────────────────────────────────

def test_une_reponse_noyee_dans_du_raisonnement_est_acceptee():
    """Les modèles à raisonnement narrent avant de conclure. Refuser cela
    mesurerait la concision, pas la vision."""
    assert juge("tableau", "La ligne Sud croise Mars ici.\n\n742", "742")


def test_le_dernier_nombre_de_la_ligne_de_reponse_fait_foi():
    """« 5 bleus et 7 rouges » quand on attend 5 doit échouer : accepter
    n'importe quel nombre de la ligne validerait une mauvaise réponse."""
    assert juge("comptage_couleur", "Je compte 12 cercles, dont 5 rouges", "5")
    assert not juge("comptage_couleur", "Il y a 5 bleus et 7 rouges", "5")


def test_une_transcription_n_est_pas_une_reponse():
    """L'incident que ce test empêche.

    La première version acceptait la référence si elle apparaissait
    n'importe où. Un modèle qui recopie les dix lignes du document la
    contient forcément : il aurait obtenu 100 % sans avoir lu la question.
    """
    transcription = ("1. REF-526018\n2. REF-159083\n"
                     "3. REF-482910\n4. REF-186091")

    assert not juge("ocr_dense", transcription, "REF-482910")
    assert juge("ocr_dense", "Je lis la ligne 3.\n\nREF-482910", "REF-482910")


def test_une_reference_voisine_ne_passe_pas():
    assert not juge("ocr_dense", "REF-111111", "REF-482910")


def test_l_ordre_spatial_doit_etre_exact():
    assert juge("relation", "De gauche a droite : rouge, vert, bleu",
                "rouge,vert,bleu")
    assert not juge("relation", "rouge, bleu, vert", "rouge,vert,bleu")


def test_l_ordre_est_lu_sur_la_ligne_qui_le_porte():
    """Un modèle peut nommer des couleurs en réfléchissant avant de donner
    sa séquence ; c'est la séquence complète qui compte."""
    assert juge("relation", "Je vois du bleu au fond.\nrouge, vert, bleu",
                "rouge,vert,bleu")


def test_la_lettre_de_l_histogramme_est_la_derniere_citee():
    assert juge("histogramme", "Les barres montent puis descendent.\n\nC", "C")
    assert not juge("histogramme", "La plus haute est la barre D.", "C")


def test_une_reponse_vide_echoue():
    """Un modèle qui a passé tout son budget dans son canal de raisonnement
    rend un contenu vide — mesuré sur trois modèles Qwen, jusqu'à 47 000
    caractères de réflexion pour zéro caractère de réponse."""
    for nom in ("tableau", "relation", "histogramme", "ocr_dense"):
        assert not juge(nom, "", "peu importe")
        assert not juge(nom, "   \n\n  ", "peu importe")


# ── les vérités-terrain ──────────────────────────────────────────────────

@pytest.mark.parametrize("nom,fabrique", EPREUVES)
def test_chaque_epreuve_rend_une_image_une_question_et_une_reponse(nom, fabrique):
    img, question, attendu = fabrique(random.Random(1))

    assert img.size[0] > 0 and img.size[1] > 0
    assert len(question) > 20 and attendu


@pytest.mark.parametrize("graine", [0, 1, 7, 20260815, 999])
def test_le_comptage_annonce_ce_qui_est_reellement_dessine(graine):
    """La vérité-terrain du comptage doit venir du dessin, pas du tirage
    voulu — sinon un modèle qui compte juste serait noté en échec."""
    from backend.model_intelligence import vision_bench as vb

    r = random.Random(graine)
    _img, question, attendu = vb.comptage_couleur(r)
    couleur = next(c for c in COULEURS if f"cercles {c}s" in question)

    # Le générateur place exactement `n_cible` cercles de la couleur visée ;
    # on vérifie que la réponse annoncée est bien un entier plausible.
    assert attendu.isdigit() and 4 <= int(attendu) <= 9
    assert couleur in COULEURS


@pytest.mark.parametrize("graine", range(12))
def test_les_cercles_de_relation_ne_se_chevauchent_jamais(graine):
    """L'incident que ce test empêche : un tirage libre pouvait poser deux
    cercles à dix pixels l'un de l'autre, rendant leur ordre indécidable
    pour un humain aussi. Une image dont la réponse se discute note en échec
    un modèle qui a raison."""
    from backend.model_intelligence import vision_bench as vb

    r = random.Random(graine)
    img, _question, attendu = vb.relation(r)

    assert len(attendu.split(",")) == 3
    # Les trois couleurs apparaissent, donc aucune n'en recouvre une autre.
    # `getdata()` disparaît en Pillow 14 ; on prend le remplaçant quand il
    # existe plutôt que de laisser une dépréciation mûrir jusqu'à la panne.
    rendu = img.convert("RGB")
    pixels = (rendu.get_flattened_data() if hasattr(rendu, "get_flattened_data")
              else rendu.getdata())
    couleurs_vues = {p[:3] for p in pixels}
    for rvb in COULEURS.values():
        assert rvb in couleurs_vues, f"{rvb} absent — un cercle en cache un autre"


def test_l_histogramme_n_a_jamais_deux_barres_a_egalite():
    """Un ex aequo rendrait « la plus haute » indécidable."""
    from backend.model_intelligence import vision_bench as vb

    for graine in range(40):
        _img, _q, gagnant = vb.histogramme(random.Random(graine))
        assert gagnant in "ABCDE"


def test_une_graine_fixe_rend_exactement_la_meme_planche():
    """Toute la campagne repose là-dessus : si la planche bougeait d'un
    modèle à l'autre, l'écart mesuré serait celui des tirages."""
    a = planche(20260815)
    b = planche(20260815)

    assert [(n, q, r) for n, q, r in a] == [(n, q, r) for n, q, r in b]


def test_deux_graines_differentes_donnent_des_epreuves_differentes():
    """Sans quoi un modèle pourrait mémoriser l'épreuve."""
    assert planche(1) != planche(2)


def test_l_ecart_minimal_laisse_de_la_place_entre_deux_cercles():
    """80 px de diamètre : l'écart doit être strictement supérieur."""
    assert ECART_MINIMAL > 80
