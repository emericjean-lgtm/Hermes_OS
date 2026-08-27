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

from backend.studio.arbitrage import carte_reservee, pic_gpu_du_processus
from backend.studio.comfyui import ComfyUI

logger = logging.getLogger("hermes_os.studio.routes")

router = APIRouter(prefix="/studio", tags=["studio"])

#: Le poids de LTX-2.5 en Q3_K_M, mesuré sur le fichier. Sert de besoin par
#: défaut quand l'appelant n'en déclare pas : mieux vaut réserver trop que
#: laisser deux locataires se disputer la carte.
BESOIN_DEFAUT = 11_525_623_808


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
    if not isinstance(graphe, dict) or not graphe:
        return {"success": False, "error": "graphe manquant"}

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


@router.get("/queue")
def file() -> dict[str, Any]:
    c = _comfy()
    e = c.etat()
    return {"joignable": e.joignable, **c.file()}


@router.get("/vram")
def vram() -> dict[str, Any]:
    """Ce que le processus de rendu détient vraiment sur la carte.

    Pas ce que PyTorch déclare : sous ROCm, `memory_allocated()` a annoncé
    20,16 Gio sur une carte de 15,98 pendant un débordement, sans erreur.
    Le compteur du processus est la seule mesure qui distingue « tient sur
    la carte » de « complète en RAM ».
    """
    import subprocess

    script = ("(Get-NetTCPConnection -LocalPort 8188 -State Listen"
              " -ErrorAction SilentlyContinue | Select-Object -First 1)"
              ".OwningProcess")
    try:
        sortie = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=20).stdout.strip()
        pid = int(sortie) if sortie.isdigit() else 0
    except Exception:
        pid = 0

    if not pid:
        return {"mesure": False, "raison": "ComfyUI n'écoute pas sur 8188"}

    octets = pic_gpu_du_processus(pid)
    if octets is None:
        # Non mesuré n'est pas zéro : l'écran doit écrire « non mesuré »
        # et non « 0 Gio », qui se lirait comme « rien ne tourne ».
        return {"mesure": False, "pid": pid,
                "raison": "compteur GPU indisponible"}
    return {"mesure": True, "pid": pid, "octets": octets}
