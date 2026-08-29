"""La tuile de decodage se mesure au lieu de se supposer (HOS-210).

La campagne HOS-205..209 a corrige le scintillement puis le quadrillage,
mais chaque fois sur une table ECRITE A LA MAIN — fausse deux fois : trop
prudente d'abord (elle descendait a 64 la ou 128 tenait, d'ou le
quadrillage), mal calibree ensuite.

Une table figee est fausse des que quelque chose bouge. Et l'echec tombe
au decodage, APRES la diffusion : vingt minutes perdues pour decouvrir
que la tuile ne passait pas.

L'essai a blanc exploite le fait que la memoire du decodeur ne depend que
des DIMENSIONS du latent, jamais de son contenu.
"""

from __future__ import annotations

import json

import pytest

from backend.studio import calibration


@pytest.fixture(autouse=True)
def table_isolee(tmp_path, monkeypatch):
    """Jamais la vraie table : un test ne touche pas aux mesures reelles."""
    monkeypatch.setattr(calibration, "TABLE", str(tmp_path / "calib.json"))


def _essais(verdicts):
    """Un faux essai qui rend les verdicts donnes, dans l'ordre des tuiles."""
    vus = []

    def essayer(graphe, minutes, ComfyUI):
        t = graphe["12"]["inputs"]["tile_size"]
        vus.append(t)
        return verdicts.get(t, "oom"), 1.0

    essayer.vus = vus
    return essayer


def test_retient_la_plus_grande_tuile_qui_passe():
    # Une tuile large donne plus de contexte au VAE — en manquer est ce
    # qui produisait le quadrillage. La table ecrite a la main propose 128
    # pour ce plan ; s'arreter la retiendrait un reglage inutilement
    # etroit, c'est exactement sa prudence qui a produit le defaut.
    e = _essais({128: "ok", 160: "ok", 192: "ok", 224: "oom"})
    r = calibration.calibrer(1280, 704, 121, essayer=e)
    assert r["tuile"] == 192
    assert e.vus == [128, 160, 192, 224], "monter tant que ca passe"


def test_descend_quand_la_table_est_trop_audacieuse():
    # Le symetrique : la table s'est trompee dans les deux sens.
    e = _essais({160: "oom", 128: "ok"})
    r = calibration.calibrer(768, 416, 97, essayer=e)
    assert r["tuile"] == 128
    assert e.vus == [160, 128]


def test_part_de_la_table_et_non_du_maximum():
    # Un essai coute des minutes sur cette carte. Descendre depuis 256 en
    # coute jusqu'a sept ; partir de ce que la table propose en coute un
    # ou deux. C'est la difference entre un reglage qu'on mesure et un
    # qu'on renonce a mesurer.
    e = _essais({128: "ok", 160: "oom"})
    calibration.calibrer(1280, 704, 121, essayer=e)
    assert e.vus[0] == 128, "le premier essai est celui que la table propose"
    assert len(e.vus) == 2


def test_la_mesure_est_enregistree_et_relue():
    calibration.calibrer(768, 416, 49, essayer=_essais({256: "ok"}))
    assert calibration.connue(768, 416, 49) == 256


def test_une_configuration_jamais_mesuree_rend_None():
    assert calibration.connue(1280, 704, 257) is None


def test_un_verdict_incertain_n_est_jamais_lu_comme_un_debordement():
    # Ni succes ni debordement : on ne sait pas. Poursuivre reviendrait a
    # conclure d'un silence — c'est l'erreur qui a produit trois faux
    # resultats pendant la campagne, dont un « aucune tuile ne passe »
    # alors qu'un vrai rendu avait abouti.
    e = _essais({128: "delai", 96: "ok"})
    r = calibration.calibrer(1280, 704, 121, essayer=e)
    assert r["tuile"] is None
    assert r["raison"] == "delai"
    assert e.vus == [128], "rien ne se poursuit sur une non-mesure"
    assert calibration.connue(1280, 704, 121) is None


def test_une_montee_interrompue_n_enregistre_que_ce_qui_a_ete_mesure():
    # 128 a reellement passe ; 160 n'a rien dit. Retenir 128 est vrai,
    # retenir 160 serait invente.
    e = _essais({128: "ok", 160: "erreur"})
    r = calibration.calibrer(1280, 704, 121, essayer=e)
    assert r["tuile"] == 128


def test_l_essai_ne_charge_aucun_modele_de_diffusion():
    # C'est tout l'interet : deux a sept minutes au lieu de vingt.
    g = calibration._graphe_a_blanc(768, 416, 49, 128, "vae.safetensors")
    types = {n["class_type"] for n in g.values()}
    assert "UnetLoaderGGUF" not in types
    assert "SamplerCustom" not in types
    assert types == {"VAELoader", "EmptyLTXVLatentVideo",
                     "VAEDecodeTiled", "PreviewImage"}


def test_l_essai_decode_bien_d_un_seul_bloc_temporel():
    # Sinon il mesurerait autre chose que ce que le rendu fera.
    g = calibration._graphe_a_blanc(768, 416, 121, 128, "vae.safetensors")
    assert g["12"]["inputs"]["temporal_size"] == 4096


def test_l_essai_n_ecrit_pas_dans_les_rendus():
    # `PreviewImage` va dans le temporaire ; `SaveImage` polluerait
    # E:\YouTube\Generations d'images grises.
    g = calibration._graphe_a_blanc(768, 416, 49, 128, "vae.safetensors")
    assert g["13"]["class_type"] == "PreviewImage"


def test_la_mesure_prime_sur_les_paliers_ecrits_a_la_main(monkeypatch):
    from backend.studio import gabarits
    # Les paliers donneraient 128 pour ce volume ; la mesure dit 192.
    assert gabarits.tuile_spatiale(1280, 704, 121) == 128
    calibration.calibrer(1280, 704, 121,
                         essayer=_essais({128: "ok", 160: "ok",
                                          192: "ok", 224: "oom"}))
    assert gabarits.tuile_spatiale(1280, 704, 121) == 192


def test_une_table_illisible_ne_bloque_pas_le_rendu(monkeypatch):
    # La calibration est un confort, pas une dependance.
    monkeypatch.setattr(calibration, "lire_table",
                        lambda: (_ for _ in ()).throw(OSError("disque")))
    from backend.studio import gabarits
    assert gabarits.tuile_spatiale(768, 416, 49) == 256


def test_la_mesure_porte_sa_date():
    # Une mesure sans sa date ne dit pas si elle decrit encore la machine.
    r = calibration.calibrer(768, 416, 49, essayer=_essais({256: "ok"}))
    assert r["mesure_le"]
    assert r["tentatives"][0]["tuile"] == 256


def test_chaque_essai_repart_d_une_carte_vide():
    """ComfyUI ne rend pas sa VRAM entre deux graphes, et c'est voulu.

    Mais en enchainant des essais de MESURE, l'occupation s'accumule :
    deux essais consecutifs ont vu 19,29 puis 25,64 Gio deja alloues sur
    une carte de 15,98, si bien que le second debordait pour une raison
    etrangere a ce qu'il mesurait. Sans cette remise a zero, la descente
    conclut sur du bruit.
    """
    appels = []

    class FauxComfy:
        def liberer(self):
            appels.append("libere")
            return True

        def soumettre(self, graphe):
            appels.append("soumis")
            return "id"

        def attendre(self, identifiant, minutes=0, periode=0):
            class R:
                acheve = True
                duree_s = 1.0
                erreur = None
            return R()

    calibration._essai_reel({}, 1.0, FauxComfy)
    assert appels == ["libere", "soumis"], \
        "la carte se libere AVANT la soumission, sinon on mesure le voisin"


def test_un_essai_qui_n_aboutit_pas_est_interrompu():
    """Un decodage qui deborde ne s'arrete pas de lui-meme.

    Il bascule sur la memoire partagee et rampe — un essai a tenu
    quarante minutes ainsi. Rendre la main sans l'interrompre laisserait
    la carte occupee pour tout ce qui suit, essais comme vrais rendus.
    """
    appels = []

    class FauxComfy:
        def liberer(self): return True
        def soumettre(self, graphe): return "id"
        def interrompre(self): appels.append("interrompu"); return True

        def attendre(self, identifiant, minutes=0, periode=0):
            class R:
                acheve = False
                duree_s = 1200.0
                erreur = "non achevé"
            return R()

    verdict, _ = calibration._essai_reel({}, 1.0, FauxComfy)
    assert verdict == "delai"
    assert appels == ["interrompu"]


def test_un_delai_n_est_pas_rapporte_comme_une_impossibilite(monkeypatch, tmp_path):
    """« Aucune tuile ne passe » est une affirmation, pas un aveu d'ignorance.

    Confondre « la carte ne peut pas » et « je n'ai pas su lire » a produit
    trois faux resultats pendant HOS-207, dont un « aucune tuile ne passe »
    alors qu'un vrai rendu de la meme configuration avait abouti.
    """
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.studio import calibration as c

    monkeypatch.setattr(c, "TABLE", str(tmp_path / "t.json"))
    monkeypatch.setattr(c, "calibrer",
                        lambda *a, **k: {"tuile": None, "raison": "delai",
                                         "tentatives": []})
    r = TestClient(app).post("/api/v1/studio/calibration",
                             json={"largeur": 768, "hauteur": 416,
                                   "images": 97})
    corps = r.json()
    assert corps["success"] is False
    assert corps["raison"] == "delai"
    assert "aucune tuile" not in corps["error"], \
        "un delai ne prouve rien sur la capacite de la carte"
    assert "inconnue" in corps["error"]


def test_une_tuile_qui_rampe_n_est_pas_retenue():
    """« Ca passe » ne suffit pas : encore faut-il que ce soit utilisable.

    Mesure du 2026-08-29 : la tuile 160 decode 768x416x97 en quatre
    minutes, la 192 tenait encore apres vingt sans aboutir — elle ne
    debordait pas au sens de PyTorch, elle basculait sur la memoire
    partagee. La retenir couterait cette lenteur a chaque rendu, alors que
    la consigne est « de la qualite, mais dans un temps acceptable ».
    """
    delais = []

    def essayer(graphe, minutes, ComfyUI):
        delais.append(minutes)
        t = graphe["12"]["inputs"]["tile_size"]
        if t == 160:
            return "ok", 240.0          # quatre minutes
        return "delai", minutes * 60.0  # la suivante rampe

    r = calibration.calibrer(768, 416, 97, essayer=essayer)
    assert r["tuile"] == 160, "la tuile utilisable, pas la plus grande"
    assert delais[1] <= 240.0 * calibration.FACTEUR_RAMPE / 60.0 + 0.01, \
        "la montee n'attend pas vingt minutes une reponse qu'elle rejettera"


def test_l_essai_decode_le_graphe_exact_du_rendu():
    """Un essai qui ne mesure pas le graphe du rendu ne mesure rien.

    Le recouvrement etait recalcule dans le module de calibration, en
    double de `gabarits.recouvrement_spatial()`. Les deux auraient diverge
    au premier ajustement de l'un des deux, et l'essai aurait continue a
    repondre « ca passe » sur un graphe que le rendu n'utilisait plus.
    """
    from backend.studio import gabarits

    for tuile in calibration.TUILES:
        g = calibration._graphe_a_blanc(768, 416, 97, tuile, "vae.safetensors")
        assert g["12"]["inputs"]["overlap"] == \
            gabarits.recouvrement_spatial(tuile), f"tuile {tuile}"
        assert g["12"]["inputs"]["temporal_size"] == 4096
