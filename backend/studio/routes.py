"""Les routes du Studio (HOS-190).

Quatre verbes : dire l'état, lister ce qui est chargeable, soumettre un
rendu, suivre la file.

Ce module ne compose aucun graphe. Le graphe vient de l'appelant — Hermes
Agent par ses outils MCP, ou le Studio Center par un gabarit. La règle qui
prime sur tout dans ce dépôt interdit qu'une seconde boucle décide à la
place de l'agent, et un « service qui construit le bon workflow » serait
exactement cela.

Ce qu'il apporte, en revanche, et que ni ComfyUI ni l'agent ne peuvent
apporter : **l'arbitrage de la carte**. ComfyUI ignore qu'un modèle de
langage occupe la VRAM ; Ollama ignore qu'un rendu est en cours. Les deux
allouent jusqu'à ce que ROCm complète en mémoire système, sans lever
d'erreur — dix-sept fois le temps, mesuré. Hermes OS est le seul à voir
les deux.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body

from backend.studio.arbitrage import (BESOIN_RENDU_OCTETS, carte_reservee,
                                      pic_gpu_du_processus)
from backend.studio.comfyui import ComfyUI, pid_du_serveur

logger = logging.getLogger("hermes_os.studio.routes")

router = APIRouter(prefix="/studio", tags=["studio"])

#: Une seule definition, dans `arbitrage` : c'est le module qui
#: raisonne sur la carte. L'alias garde le nom que les routes et
#: les tests emploient deja.
BESOIN_DEFAUT = BESOIN_RENDU_OCTETS


def _comfy() -> ComfyUI:
    return ComfyUI()


@router.get("/state")
def etat() -> dict[str, Any]:
    """ComfyUI est-il là, et dans quelle configuration.

    `attention_sub_quadratique` est lu et non supposé : sans ce drapeau,
    un rendu à 16 384 jetons réclame 20,16 Gio sur une carte de 15,98 et
    met 3 226 ms au lieu de 187. L'écran doit pouvoir le dire.
    """
    e = _comfy().etat()
    return {
        "joignable": e.joignable,
        "version": e.version,
        "vram_totale": e.vram_totale,
        "vram_libre": e.vram_libre,
        "attention_sub_quadratique": e.attention_sub_quadratique,
        "detail": e.detail,
        "file": _comfy().file() if e.joignable else {"en_cours": 0, "en_attente": 0},
    }


@router.get("/models")
def modeles() -> dict[str, Any]:
    """Ce que les chargeurs voient réellement sur le disque.

    Proposer une liste plutôt qu'un champ libre : un nom de fichier mal
    tapé produit un refus de graphe que rien ne rattache à la faute de
    frappe.
    """
    c = _comfy()
    return {
        "diffusion": c.modeles("unet_name"),
        "encodeurs": c.modeles("clip_name"),
        "vae": c.modeles("vae_name"),
        # Les modèles d'image sont des *checkpoints*. Sans cette ligne,
        # SDXL — installé et mesuré — n'apparaissait nulle part dans
        # l'écran, et l'on pouvait croire qu'il n'était pas là.
        "checkpoints": c.modeles("ckpt_name"),
    }


@router.post("/render")
def rendre(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Soumettre un graphe, la carte réservée.

    Rend immédiatement après la soumission : un rendu dure des minutes et
    une requête HTTP ne doit pas les attendre. Le suivi passe par
    `/studio/queue` et par les événements.

    La réservation, elle, n'est **pas** tenue pendant le rendu : le verrou
    protège la décision de lancer, pas la durée du travail. Le tenir plus
    longtemps bloquerait le processus web entier. C'est une limite connue
    et écrite plutôt que masquée — le jour où deux appelants soumettent
    coup sur coup, la file de ComfyUI les sérialise, mais rien n'empêche
    Ollama de recharger entre-temps.
    """
    graphe = payload.get("graphe")

    # Deux façons d'arriver ici, et une seule décide de quelque chose.
    #
    # `graphe` : l'appelant a composé lui-même — c'est la voie de Hermes
    # Agent, et elle reste intacte.
    #
    # `gabarit` + `parametres` : la voie du Studio Center. Le gabarit est
    # figé, les paramètres sont explicites, rien n'est inféré. C'est un
    # formulaire, pas une seconde boucle — la distinction est écrite en
    # tête de `gabarits.py`.
    if not graphe and payload.get("gabarit"):
        from backend.studio.gabarits import GabaritInvalide, composer

        parametres = payload.get("parametres") or {}
        if not isinstance(parametres, dict):
            return {"success": False, "error": "parametres doit être un objet"}
        try:
            graphe = composer(str(payload["gabarit"]),
                              str(payload.get("consigne") or ""), **parametres)
        except GabaritInvalide as e:
            return {"success": False, "error": str(e),
                    "raison": "gabarit_invalide"}

    if not isinstance(graphe, dict) or not graphe:
        return {"success": False,
                "error": "il faut un `graphe` ou un `gabarit`"}

    besoin = int(payload.get("besoin_octets") or BESOIN_DEFAUT)

    with carte_reservee(besoin) as occ:
        if not occ.obtenu:
            return {"success": False, "error": occ.detail,
                    "raison": "carte_occupee"}
        if occ.liberation_douteuse:
            # Refuser plutôt que rendre en débordant. Un rendu qui déborde
            # aboutit — c'est bien le problème : il aboutit dix-sept fois
            # plus lentement, et l'opérateur accuse le modèle.
            return {"success": False, "error": occ.detail,
                    "raison": "vram_insuffisante",
                    "modeles_decharges": occ.modeles_decharges}

        try:
            identifiant = _comfy().soumettre(graphe)
        except ValueError as e:
            return {"success": False, "error": str(e)[:800],
                    "raison": "graphe_refuse"}

        return {
            "success": True,
            "prompt_id": identifiant,
            "modeles_decharges": occ.modeles_decharges,
            "vram_liberee_octets": occ.libere_octets,
        }


@router.get("/templates")
def gabarits() -> dict[str, Any]:
    """Ce que le Studio Center sait composer, et avec quels paramètres.

    Décrit ici et non dupliqué dans le frontend : deux listes du même
    fait finissent par diverger, et c'est toujours celle qu'on ne regarde
    pas qui se trompe.
    """
    from backend.studio.gabarits import CATALOGUE, FORMATS

    return {
        "gabarits": CATALOGUE,
        "formats": {nom: {"largeur": l, "hauteur": h}
                    for nom, (l, h) in FORMATS.items()},
    }


@router.get("/queue")
def file() -> dict[str, Any]:
    c = _comfy()
    e = c.etat()
    return {"joignable": e.joignable, **c.file()}


#: Où la file de nuit consigne son rapport. Sur E: avec les rendus : le
#: rapport et les fichiers qu'il décrit doivent voyager ensemble, sinon on
#: se retrouve à lire un verdict sur un plan qu'on ne trouve plus.
JOURNAL_NUIT = r"E:\YouTube\Generations\nuit\rapport.json"

#: Le fil de la nuit en cours. Un seul : deux files se disputeraient la
#: carte, et l'arbitrage ne protège que d'un rendu à la fois, pas de deux
#: files qui se relanceraient l'une l'autre.
_nuit: Any = None


@router.post("/night")
def nuit(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Lancer une file de plans et rendre la main aussitôt.

    Une nuit dure des heures — trois plans de quatre secondes en 704×1280
    coûtent une heure de calcul. Aucune requête HTTP ne peut l'attendre :
    l'appelant reçoit le chemin du journal, que `GET /studio/night` relit.

    Les graphes viennent de l'appelant, comme pour `/render`. Ce module
    n'en compose aucun : la règle qui prime sur tout dans ce dépôt réserve
    cette décision à Hermes Agent.
    """
    import threading

    from backend.studio.file_de_nuit import Plan, atelier

    global _nuit
    if _nuit is not None and _nuit.is_alive():
        return {"success": False, "raison": "nuit_en_cours",
                "error": "une file de nuit tourne déjà",
                "journal": JOURNAL_NUIT}

    bruts = payload.get("plans")
    if not isinstance(bruts, list) or not bruts:
        return {"success": False, "error": "aucun plan"}

    plans: list[Plan] = []
    for i, b in enumerate(bruts):
        graphe = (b or {}).get("graphe")
        if not isinstance(graphe, dict) or not graphe:
            return {"success": False, "error": f"plan {i} : graphe manquant"}
        plans.append(Plan(
            identifiant=str((b.get("identifiant") or f"plan_{i}")),
            # La consigne sert au relecteur. Sans elle il n'a rien à quoi
            # comparer, et le plan finira `indetermine` — ce qui est
            # correct, mais coûte un rendu pour rien.
            consigne=str(b.get("consigne") or ""),
            graphe=graphe))

    minutes = float(payload.get("minutes_par_plan") or 45.0)
    besoin = int(payload.get("besoin_octets") or BESOIN_DEFAUT)

    _nuit = threading.Thread(
        target=lambda: atelier(plans, minutes_par_plan=minutes,
                               besoin_octets=besoin, journal=JOURNAL_NUIT),
        name="studio-nuit", daemon=True)
    _nuit.start()

    return {"success": True, "plans": len(plans), "journal": JOURNAL_NUIT}


@router.get("/night")
def rapport_nuit() -> dict[str, Any]:
    """Le rapport du matin, tel qu'il est sur le disque.

    Relu du fichier et non d'un état en mémoire : le journal est écrit
    après chaque plan, et il survit à un redémarrage du backend là où une
    variable ne survivrait pas. Une nuit coupée à la sixième heure doit
    laisser lisibles les cinq premières.

    `en_cours` dit « **ce** backend a lancé une nuit qui tourne encore »,
    et non « une nuit tourne quelque part ». Un script lancé à côté n'y
    figure pas — comme le verrou de `carte_reservee`, qui est un objet de
    processus, et pour la même raison. Le journal, lui, reste vrai dans
    les deux cas : c'est pourquoi c'est lui qu'on lit.
    """
    import json
    import os

    en_cours = _nuit is not None and _nuit.is_alive()
    if not os.path.exists(JOURNAL_NUIT):
        return {"en_cours": en_cours, "rapport": None,
                "raison": "aucune nuit n'a encore été consignée"}
    try:
        with open(JOURNAL_NUIT, encoding="utf-8") as f:
            return {"en_cours": en_cours, "rapport": json.load(f)}
    except (OSError, json.JSONDecodeError) as e:
        return {"en_cours": en_cours, "rapport": None,
                "raison": f"journal illisible : {str(e)[:120]}"}


@router.get("/vram")
def vram() -> dict[str, Any]:
    """Ce que le processus de rendu détient vraiment sur la carte.

    Pas ce que PyTorch déclare : sous ROCm, `memory_allocated()` a annoncé
    20,16 Gio sur une carte de 15,98 pendant un débordement, sans erreur.
    Le compteur du processus est la seule mesure qui distingue « tient sur
    la carte » de « complète en RAM ».
    """
    pid = pid_du_serveur()
    if not pid:
        return {"mesure": False, "raison": "ComfyUI n'écoute pas sur 8188"}

    octets = pic_gpu_du_processus(pid)
    if octets is None:
        # Non mesuré n'est pas zéro : l'écran doit écrire « non mesuré »
        # et non « 0 Gio », qui se lirait comme « rien ne tourne ».
        return {"mesure": False, "pid": pid,
                "raison": "compteur GPU indisponible"}
    return {"mesure": True, "pid": pid, "octets": octets}
