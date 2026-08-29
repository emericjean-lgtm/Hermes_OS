"""La tuile de décodage, mesurée sur cette machine (HOS-210).

## Pourquoi une mesure et pas une table

`gabarits.PALIERS_TUILE` choisit déjà la tuile automatiquement. Ce qui a
échoué pendant la campagne HOS-205..209, ce n'est pas l'automatisme,
c'est sa **source** : une table écrite à la main, fausse deux fois — trop
prudente d'abord (elle descendait à 64 là où 128 tenait, d'où le
quadrillage), mal calibrée ensuite.

Une table figée est fausse dès que quelque chose bouge : un autre modèle,
une autre quantification, une carte différente, ou simplement Ollama qui
occupe la VRAM au moment du rendu. Et l'échec tombe **au décodage, après
la diffusion** — vingt minutes de calcul perdues pour découvrir que la
tuile ne passait pas.

## Ce que l'essai à blanc exploite

La mémoire du décodeur ne dépend que des **dimensions** du latent, jamais
de son contenu. Décoder un latent vide exerce donc exactement le même
chemin mémoire qu'un vrai plan, sans charger un seul modele de diffusion. C'est la technique qui a permis toute la campagne de mesure.

L'essai ne dit rien de la qualité — seulement « est-ce que ça tient ».
C'est précisément ce qu'on lui demande.

## Ce que la table retient

Une entrée par `(largeur, hauteur, images)`, avec la plus grande tuile
qui soit **passée pour de vrai** sur cette machine. Elle se remplit au
premier plan d'une configuration et ne coûte plus rien ensuite.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("hermes_os.studio.calibration")

#: À côté des rendus et non dans le dépôt : c'est une mesure propre à
#: cette machine, pas un fait du code. Le même raisonnement que pour le
#: journal de la file de nuit.
TABLE = r"E:\YouTube\Generations\calibration_decodeur.json"

#: Du plus grand au plus petit. Une tuile large donne plus de contexte au
#: VAE — c'en manquer est ce qui produisait le quadrillage — donc on part
#: du haut et on ne descend qu'au débordement.
#:
#: Le pas est de 32 parce que le nœud divise `tile_size` par la
#: compression spatiale du VAE, mesurée à 32 : toute valeur intermédiaire
#: est tronquée sans effet.
TUILES = [256, 224, 192, 160, 128, 96, 64]

#: Au-dela de ce multiple du premier essai reussi, une tuile plus grande
#: n'est plus « acceptee », elle **rampe**. Mesure le 2026-08-29 : la
#: tuile 160 decode 768x416x97 en quatre minutes, la 192 tenait encore
#: apres vingt sans aboutir, le processus consommant une seconde de CPU
#: par seconde ecoulee et 14,18 Gio de VRAM sur 15,98. Elle ne debordait
#: pas au sens de PyTorch : elle basculait sur la memoire partagee.
#:
#: Retenir une telle tuile serait pire que le defaut qu'on corrige —
#: l'utilisateur a dit vouloir « de la qualite, mais dans un temps
#: acceptable ». Deux fois et demie, c'est large pour une vraie
#: difference de charge, et net face a un facteur cinq.
FACTEUR_RAMPE = 2.5

#: Sous cette taille, le VAE n'a plus assez de contexte et la grille
#: réapparaît — constaté à 64 (deux unités latentes) sur 1280×704.
#: Descendre plus bas échangerait un défaut visible contre un autre.
TUILE_PLANCHER = 64


def _cle(largeur: int, hauteur: int, images: int) -> str:
    return f"{int(largeur)}x{int(hauteur)}x{int(images)}"


def lire_table() -> dict[str, Any]:
    try:
        with open(TABLE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _ecrire(table: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(TABLE), exist_ok=True)
    # Écriture puis renommage : une mesure interrompue ne doit pas laisser
    # un fichier tronqué qui ferait recalibrer tout à zéro.
    provisoire = TABLE + ".part"
    with open(provisoire, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=1, ensure_ascii=False)
    os.replace(provisoire, TABLE)


def connue(largeur: int, hauteur: int, images: int) -> Optional[int]:
    """La tuile mesurée pour ce plan, ou None si jamais essayée."""
    e = lire_table().get(_cle(largeur, hauteur, images))
    return int(e["tuile"]) if e and e.get("tuile") else None


def _graphe_a_blanc(largeur: int, hauteur: int, images: int, tuile: int,
                    vae: str) -> dict[str, Any]:
    """Décoder du vide : même chemin mémoire, aucun modèle de diffusion.

    Le recouvrement vient de `gabarits`, il n'est pas recalculé ici : un
    essai qui ne décode pas **exactement** le graphe du rendu mesure autre
    chose que ce qu'il prétend. Les deux valeurs auraient divergé au
    premier ajustement de l'un des deux.
    """
    from backend.studio.gabarits import recouvrement_spatial

    return {
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "6": {"class_type": "EmptyLTXVLatentVideo",
              "inputs": {"width": int(largeur), "height": int(hauteur),
                         "length": int(images), "batch_size": 1}},
        "12": {"class_type": "VAEDecodeTiled",
               "inputs": {"samples": ["6", 0], "vae": ["3", 0],
                          "tile_size": int(tuile),
                          "overlap": recouvrement_spatial(int(tuile)),
                          "temporal_size": 4096, "temporal_overlap": 8}},
        # `PreviewImage` écrit dans le dossier temporaire : l'essai ne
        # laisse rien dans les rendus.
        "13": {"class_type": "PreviewImage", "inputs": {"images": ["12", 0]}},
    }


def _depart(largeur: int, hauteur: int, images: int) -> int:
    """La tuile que la table ecrite a la main propose pour ce plan.

    Elle s'est trompee deux fois, mais jamais de beaucoup : partir d'elle
    et corriger coute un ou deux essais, la ou une descente depuis 256 en
    coute jusqu'a sept. Sur une machine ou un essai se compte en minutes,
    ce n'est pas un detail de vitesse — c'est la difference entre un
    reglage qu'on mesure et un qu'on renonce a mesurer.
    """
    from backend.studio.gabarits import PALIERS_TUILE
    volume = (int(largeur) * int(hauteur) * max(1, int(images))) / 1_000_000
    for plafond, tuile in PALIERS_TUILE:
        if volume <= plafond:
            return tuile if tuile in TUILES else TUILES[-1]
    return TUILES[-1]


def calibrer(largeur: int, hauteur: int, images: int, *,
             vae: str = "ltx-2.5-video-vae-bf16.safetensors",
             essayer: Optional[Callable[..., tuple[str, float]]] = None,
             minutes: float = 20.0) -> dict[str, Any]:
    """La plus grande tuile qui decode ce plan d'un seul bloc.

    Part de ce que la table ecrite a la main propose, puis **monte** tant
    que ca passe et **descend** au premier debordement. Enregistre le
    resultat avec sa date et son cout — une mesure sans sa date ne dit
    pas si elle decrit encore la machine.

    `essayer` est injectable pour les tests : sans lui, un vrai essai part
    sur la carte, ce qu'aucun test ne doit faire.
    """
    from backend.studio.comfyui import ComfyUI

    tenter = essayer or _essai_reel
    debut = time.time()
    tentatives: list[dict[str, Any]] = []
    vus: dict[int, str] = {}

    couts: dict[int, float] = {}

    def essai(tuile: int, plafond_minutes: Optional[float] = None) -> str:
        if tuile in vus:
            return vus[tuile]
        verdict, secondes = tenter(
            _graphe_a_blanc(largeur, hauteur, images, tuile, vae),
            plafond_minutes or minutes, ComfyUI)
        vus[tuile] = verdict
        couts[tuile] = secondes
        tentatives.append({"tuile": tuile, "verdict": verdict,
                           "secondes": round(secondes, 1)})
        logger.info("calibration %sx%sx%s tuile %s : %s (%.0fs)",
                    largeur, hauteur, images, tuile, verdict, secondes)
        return verdict

    def enregistrer(tuile: int) -> dict[str, Any]:
        entree = {"tuile": tuile,
                  "mesure_le": time.strftime("%Y-%m-%d %H:%M"),
                  "secondes": round(time.time() - debut, 1),
                  "tentatives": tentatives}
        table = lire_table()
        table[_cle(largeur, hauteur, images)] = entree
        _ecrire(table)
        return entree

    depart = _depart(largeur, hauteur, images)
    index = TUILES.index(depart)
    verdict = essai(depart)

    if verdict == "ok":
        # Monter tant que ca passe : la table est prudente plus souvent
        # qu'audacieuse, et c'est sa prudence qui a produit le quadrillage.
        #
        # Mais « ca passe » ne suffit pas. Une tuile qui tient en rampant
        # sur la memoire partagee aboutit quand meme, cinq fois plus
        # lentement, et la retenir couterait a chaque rendu. On borne donc
        # l'attente au multiple retenu du premier succes : au-dela, on ne
        # gagne pas une mesure, on paie une lenteur.
        meilleure = depart
        plafond_s = max(60.0, couts.get(depart, 0.0) * FACTEUR_RAMPE)
        for tuile in reversed(TUILES[:index]):
            if essai(tuile, plafond_minutes=plafond_s / 60.0) != "ok":
                break
            meilleure = tuile
        return enregistrer(meilleure)

    if verdict != "oom":
        # Ni succes ni debordement : on ne sait pas. Poursuivre reviendrait
        # a conclure d'un silence — l'erreur qui a produit trois faux
        # resultats pendant la campagne de mesure.
        return {"tuile": None, "raison": verdict, "tentatives": tentatives}

    for tuile in TUILES[index + 1:]:
        v = essai(tuile)
        if v == "ok":
            return enregistrer(tuile)
        if v != "oom":
            return {"tuile": None, "raison": v, "tentatives": tentatives}

    return {"tuile": None, "raison": "aucune_tuile", "tentatives": tentatives}


def _essai_reel(graphe: dict[str, Any], minutes: float, ComfyUI) -> tuple[str, float]:
    """Soumettre l'essai et lire son verdict réel.

    Trois verdicts distincts et jamais déduits : `ok`, `oom`, `erreur`.
    Confondre « la carte ne peut pas » et « je n'ai pas attendu assez » a
    produit trois résultats faux pendant la campagne de mesure, dont un
    « aucune tuile ne passe » alors qu'un vrai rendu avait abouti.

    `attendre()` fait déjà le suivi, le délai et la lecture de l'erreur :
    une seconde boucle ici divergerait de la première au premier
    changement.
    """
    c = ComfyUI()
    # Repartir d'une carte vide. Deux essais consecutifs ont vu 19,29 puis
    # 25,64 Gio deja alloues sur 15,98 : sans cette remise a zero, un essai
    # deborde a cause du precedent et la descente conclut sur du bruit.
    c.liberer()
    try:
        identifiant = c.soumettre(graphe)
    except ValueError as e:
        return ("erreur:" + str(e)[:120]), 0.0

    rendu = c.attendre(identifiant, minutes=minutes, periode=4.0)
    if rendu.acheve:
        return "ok", rendu.duree_s
    # L'essai n'a pas abouti, mais ComfyUI, lui, continue. On demande
    # l'arret : ca suffit pour un essai qui tourne normalement.
    #
    # Ca ne suffit pas pour un decodage deja parti en memoire partagee — le
    # nœud ne rend la main qu'entre deux allocations, et deux appels
    # verifies ont laisse la carte a 14,18 Gio. Il n'existe pas de moyen
    # propre de la lui reprendre ; c'est pourquoi la montee est plafonnee
    # en temps, et pourquoi l'appelant est prevenu que la carte peut
    # rester occupee.
    c.interrompre()
    message = (rendu.erreur or "").lower()
    if "out of memory" in message:
        return "oom", rendu.duree_s
    if "non achevé" in message:
        return "delai", rendu.duree_s
    return "erreur", rendu.duree_s


__all__ = ["FACTEUR_RAMPE", "TABLE", "TUILES", "TUILE_PLANCHER",
           "calibrer", "connue", "lire_table"]
