"""Le client de ComfyUI, et ce qu'il refuse d'affirmer (HOS-190).

Aucun de ces tests n'a besoin d'un serveur : ils portent sur les décisions
que le client prend à partir de ce qu'il a lu, et c'est là qu'un client se
trompe silencieusement. Le transport, lui, est éprouvé par le rendu réel.
"""

from __future__ import annotations

from backend.studio.comfyui import EtatComfy, Rendu, _fichiers_de

GIO = 2**30
VRAM = 15.98 * GIO


def test_un_pic_non_mesure_ne_vaut_pas_absence_de_debordement():
    """La distinction qui porte tout le module.

    Zéro octet relevé signifie « la sonde n'a rien rendu », jamais « le
    rendu n'a rien consommé ». Rendre False est le comportement voulu —
    mais l'appelant doit tester `pic_vram_octets` avant d'y croire, et
    ce test existe pour que la nuance reste écrite quelque part.
    """
    muet = Rendu(identifiant="x", acheve=True, pic_vram_octets=0)
    assert muet.a_deborde(int(VRAM)) is False
    assert muet.pic_vram_octets == 0, (
        "c'est ce champ, et non a_deborde(), qui dit si la mesure a eu lieu"
    )


def test_le_seuil_de_debordement_est_sous_la_vram_totale():
    """98,5 % et non 100 %.

    ROCm complète en mémoire système avant que le compteur n'atteigne le
    total : un seuil à 100 % ne se déclencherait jamais, et le
    débordement resterait invisible — ce qu'il est déjà sans ce module.
    """
    total = int(VRAM)
    assert Rendu("x", pic_vram_octets=int(total * 0.97)).a_deborde(total) is False
    assert Rendu("x", pic_vram_octets=int(total * 0.99)).a_deborde(total) is True


def test_sans_vram_totale_connue_on_ne_conclut_pas():
    """Sur une machine dont on ignore la capacité, aucune conclusion.

    Comparer un pic à zéro rendrait « déborde » systématiquement vrai.
    """
    assert Rendu("x", pic_vram_octets=20 * GIO).a_deborde(0) is False


def test_letat_lit_les_drapeaux_au_lieu_de_les_supposer():
    """`--use-quad-cross-attention` décide du pic mémoire.

    Mesuré le 2026-08-27 à 16 384 jetons : sans lui, l'attention par
    défaut réclame 20,16 Gio sur une carte de 15,98 et met 3 226 ms au
    lieu de 187. Un Studio Center qui suppose le drapeau posé plutôt que
    de le lire afficherait « tout va bien » sur une configuration qui
    déborde à chaque rendu.
    """
    avec = EtatComfy(joignable=True,
                     arguments=("main.py", "--use-quad-cross-attention"))
    sans = EtatComfy(joignable=True, arguments=("main.py", "--cache-none"))
    assert avec.attention_sub_quadratique is True
    assert sans.attention_sub_quadratique is False


def test_un_serveur_injoignable_ne_pretend_pas_avoir_de_vram():
    injoignable = EtatComfy(joignable=False, detail="connexion refusée")
    assert injoignable.vram_totale == 0
    assert injoignable.attention_sub_quadratique is False


def test_les_fichiers_produits_sont_extraits_de_tous_les_noeuds():
    """Un graphe peut avoir plusieurs sorties — vidéo, images, audio.

    N'en lire qu'une laisserait des rendus inaccessibles depuis le
    Cockpit alors qu'ils existent sur le disque.
    """
    entree = {
        "outputs": {
            "14": {"video": [{"filename": "banc/LTX25_00001.mp4"}]},
            "12": {"images": [{"filename": "apercu_001.png"},
                              {"filename": "apercu_002.png"}]},
            "20": {"texte": "pas une liste"},
            "21": {"vide": []},
        }
    }
    assert _fichiers_de(entree) == [
        "banc/LTX25_00001.mp4", "apercu_001.png", "apercu_002.png",
    ]


def test_un_historique_sans_sortie_ne_leve_pas():
    assert _fichiers_de({}) == []
    assert _fichiers_de({"outputs": {}}) == []
    assert _fichiers_de({"outputs": {"1": {"images": [{"pas_de_nom": 1}]}}}) == []


def test_un_rendu_non_acheve_porte_sa_raison():
    """Un rendu qui n'a pas fini doit dire pourquoi.

    Sans cela, l'écran affiche un rendu vide et l'opérateur relance —
    plusieurs minutes de carte, pour retrouver le même silence.
    """
    r = Rendu(identifiant="x", acheve=False, erreur="non achevé après 45 min")
    assert not r.acheve and r.erreur
    assert r.fichiers == []
