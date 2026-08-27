"""Qui occupe la carte, et ce qui arrive quand on se trompe (HOS-190).

Le défaut que l'arbitrage empêche ne se manifeste **jamais** comme une
erreur. ROCm ne lève pas quand une allocation dépasse la VRAM : il complète
en mémoire système. Mesuré le 2026-08-27 sur cette machine, attention à
16 384 jetons — 3 226 ms en débordement contre 187 ms sur la carte, résultat
identique, journal muet.

Ces tests portent donc moins sur le chemin heureux que sur les trois façons
de croire à tort que la carte est libre : le verrou qu'on n'a pas obtenu, le
déchargement qui n'a rien rendu, et la sonde qui n'a rien mesuré.
"""

from __future__ import annotations

import threading

from backend.studio.arbitrage import (
    Occupation,
    carte_reservee,
    modeles_ollama_residents,
    vram_libre_octets,
)

GIO = 2**30


def test_la_carte_libre_ne_decharge_rien():
    """Assez de place : personne ne doit être dérangé.

    Décharger « par précaution » coûterait le rechargement du modèle de
    mission — plusieurs dizaines de secondes — pour rien.
    """
    appels: list[str] = []
    with carte_reservee(
        4 * GIO,
        sonde_vram=lambda: 15 * GIO,
        sonde_residents=lambda: ["gpt-oss-20b-64k"],
        decharge=lambda m: appels.append(m) or True,
    ) as occ:
        assert occ.obtenu
        assert occ.modeles_decharges == []
        assert not occ.liberation_douteuse
    assert appels == [], "un modèle a été déchargé alors que la place suffisait"


def test_la_carte_pleine_decharge_puis_verifie():
    """Le chemin nominal : on libère, et on constate que c'est libéré."""
    etat = {"libre": 2 * GIO}

    def decharge(modele: str) -> bool:
        etat["libre"] = 15 * GIO
        return True

    with carte_reservee(
        11 * GIO,
        sonde_vram=lambda: etat["libre"],
        sonde_residents=lambda: ["gpt-oss-20b-64k"],
        decharge=decharge,
        pause_s=0,
    ) as occ:
        assert occ.modeles_decharges == ["gpt-oss-20b-64k"]
        assert not occ.liberation_douteuse
        assert occ.libere_octets == 13 * GIO


def test_un_dechargement_sans_effet_est_signale_et_non_avale():
    """Le cas qui compte.

    Ollama rend `success: true` dès que la requête aboutit, pas quand la
    mémoire est rendue. Un arbitrage qui s'en contenterait laisserait
    partir un rendu qui déborde — c'est-à-dire dix-sept fois plus lent,
    sans erreur, et attribué au modèle plutôt qu'à la mémoire.
    """
    with carte_reservee(
        11 * GIO,
        sonde_vram=lambda: 2 * GIO,           # rien n'a bougé
        sonde_residents=lambda: ["un-modele"],
        decharge=lambda m: True,               # le serveur a dit oui
        pause_s=0,
    ) as occ:
        assert occ.obtenu
        assert occ.modeles_decharges == ["un-modele"]
        assert occ.liberation_douteuse, (
            "un déchargement sans effet a été pris pour un succès : c'est "
            "exactement le succès sur parole que ce projet refuse"
        )
        assert "2.00" in occ.detail and "11.00" in occ.detail


def test_une_sonde_muette_ne_declare_pas_la_carte_pleine():
    """Zéro veut dire « non mesuré », jamais « rien de libre ».

    Confondre les deux ferait décharger le modèle de mission à chaque
    rendu sur une machine où la sonde ne répond pas — un remède pire que
    le mal.
    """
    appels: list[str] = []
    with carte_reservee(
        11 * GIO,
        sonde_vram=lambda: 0,                  # non mesurable
        sonde_residents=lambda: ["gpt-oss"],
        decharge=lambda m: appels.append(m) or True,
        pause_s=0,
    ) as occ:
        assert occ.obtenu
        assert not occ.liberation_douteuse, (
            "une mesure absente a été lue comme une mémoire pleine"
        )
    assert appels == []


def test_deux_travaux_lourds_ne_partagent_pas_la_carte():
    """Le verrou est la raison d'être du module.

    Sans lui, deux rendus concurrents allouent chacun 10,73 Gio de poids
    sur une carte de 15,98 — et ROCm les sert tous les deux, en mémoire
    système.
    """
    dedans = threading.Event()
    relacher = threading.Event()
    second: dict = {}

    def premier():
        with carte_reservee(GIO, sonde_vram=lambda: 15 * GIO) as occ:
            assert occ.obtenu
            dedans.set()
            relacher.wait(timeout=5)

    fil = threading.Thread(target=premier, daemon=True)
    fil.start()
    assert dedans.wait(timeout=5)

    with carte_reservee(GIO, sonde_vram=lambda: 15 * GIO) as occ:
        second["obtenu"] = occ.obtenu
        second["detail"] = occ.detail

    relacher.set()
    fil.join(timeout=5)

    assert second["obtenu"] is False
    assert "réservée" in second["detail"]


def test_le_verrou_est_rendu_meme_si_le_travail_echoue():
    """Un rendu qui lève ne doit pas confisquer la carte.

    Le mode de panne serait silencieux et durable : plus aucun rendu ne
    passerait jusqu'au redémarrage, sans que rien n'explique pourquoi.
    """
    try:
        with carte_reservee(GIO, sonde_vram=lambda: 15 * GIO):
            raise RuntimeError("le rendu a échoué")
    except RuntimeError:
        pass

    with carte_reservee(GIO, sonde_vram=lambda: 15 * GIO) as occ:
        assert occ.obtenu, "le verrou n'a pas été rendu après une exception"


def test_les_sondes_reelles_ne_levent_jamais():
    """Sur une machine sans GPU ni Ollama, elles rendent zéro et une liste
    vide — un Studio Center doit pouvoir afficher « indisponible » au lieu
    de planter."""
    assert isinstance(vram_libre_octets(), int)
    assert isinstance(modeles_ollama_residents(), list)


def test_occupation_refusee_ne_pretend_rien_avoir_libere():
    occ = Occupation(obtenu=False, detail="occupée")
    assert occ.modeles_decharges == []
    assert occ.libere_octets == 0
