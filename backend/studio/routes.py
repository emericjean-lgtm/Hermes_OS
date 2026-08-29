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
import os
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
    from backend.studio.gabarits import (CATALOGUE, COUT_FIXE_S,
                                         COUT_PAR_MPX_IMAGE_S, FORMATS,
                                         IMAGES_MAX, PAS_IMAGES)

    return {
        "gabarits": CATALOGUE,
        "formats": {nom: {"largeur": l, "hauteur": h}
                    for nom, (l, h) in FORMATS.items()},
        # La contrainte de longueur de LTX (`8k + 1`) vient d'ici et non
        # d'une constante recopiée dans l'écran : c'est elle qui permet au
        # formulaire de proposer une durée en secondes tout en n'envoyant
        # que des longueurs que le modèle accepte.
        "images": {"pas": PAS_IMAGES, "max": IMAGES_MAX},
        # Le coût de calcul, ajusté sur les trois rendus réels. Servi plutôt
        # que recopié pour la même raison que le reste : la mesure vit à
        # côté des autres mesures, pas dans le composant qui l'affiche.
        "cout": {"fixe_s": COUT_FIXE_S, "par_mpx_image_s": COUT_PAR_MPX_IMAGE_S},
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

    Deux façons de décrire un plan, et une seule décide de quelque chose.

    `graphe` : l'appelant a composé lui-même — c'est la voie de Hermes
    Agent, et elle reste intacte.

    `gabarit` + `parametres` : la voie du Studio Center (HOS-206). Le
    gabarit est figé, les paramètres explicites, rien n'est inféré —
    exactement le même arrangement que `/render`, pour la même raison. Un
    écran qui ne sait pas composer de graphe ne pouvait pas lancer de
    nuit, et l'onglet Nuit n'affichait donc qu'un rapport qu'aucun bouton
    ne permettait de produire.
    """
    import threading

    from backend.studio.file_de_nuit import Plan, atelier
    from backend.studio.gabarits import GabaritInvalide, composer

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
        b = b or {}
        graphe = b.get("graphe")
        consigne = str(b.get("consigne") or "")

        if not graphe and b.get("gabarit"):
            parametres = b.get("parametres") or {}
            if not isinstance(parametres, dict):
                return {"success": False,
                        "error": f"plan {i} : parametres doit être un objet"}
            try:
                graphe = composer(str(b["gabarit"]), consigne, **parametres)
            except GabaritInvalide as e:
                return {"success": False, "raison": "gabarit_invalide",
                        "error": f"plan {i} : {e}"}

        if not isinstance(graphe, dict) or not graphe:
            return {"success": False,
                    "error": f"plan {i} : il faut un `graphe` ou un `gabarit`"}
        plans.append(Plan(
            identifiant=str((b.get("identifiant") or f"plan_{i}")),
            # La consigne sert au relecteur. Sans elle il n'a rien à quoi
            # comparer, et le plan finira `indetermine` — ce qui est
            # correct, mais coûte un rendu pour rien.
            consigne=consigne,
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


#: Où la narration écrit quand l'écran ne précise pas de dossier — la
#: voie MCP, elle, reçoit toujours `output_dir` de l'agent explicitement
#: (voir `mcp_server/server.py:studio_narrate`). Un sous-dossier horodaté
#: évite qu'un deuxième essai écrase le premier sans qu'on l'ait demandé.
DOSSIER_NARRATION = r"E:\YouTube\Generations\narration"


@router.post("/narrate")
def narrer(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Synthétiser des répliques avec la voix clonée « Michael » (HOS-196).

    Même fonction que l'outil MCP `studio_narrate` — reste du Studio, pas
    une seconde implémentation : les deux appellent `narration.synthetiser`
    avec le même arbitrage de carte. Celle-ci existe pour que l'écran
    puisse déclencher une narration sans passer par l'agent, exactement
    comme `/render` le permet déjà pour l'image.
    """
    import datetime

    from backend.studio.narration import ChatterboxIndisponible, synthetiser

    lignes = payload.get("lignes")
    if not isinstance(lignes, list) or not lignes:
        return {"success": False, "error": "il faut au moins une réplique"}

    textes = [(str((l or {}).get("id") or i), str((l or {}).get("texte") or ""))
              for i, l in enumerate(lignes)]
    if not any(t.strip() for _, t in textes):
        return {"success": False, "error": "chaque réplique doit avoir un texte"}

    dossier = payload.get("dossier") or os.path.join(
        DOSSIER_NARRATION, datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))

    try:
        n = synthetiser(textes, dossier, reserver=carte_reservee)
    except ChatterboxIndisponible as e:
        return {"success": False, "error": str(e), "raison": "chatterbox_absent"}

    return {
        "success": n.reussie, "appareil": n.appareil, "charge_s": n.charge_s,
        "erreur": n.erreur, "dossier": dossier,
        "segments": [{"id": s.identifiant, "reussi": s.reussi,
                      "chemin": s.chemin, "duree_s": s.duree_s,
                      "erreur": s.erreur} for s in n.segments],
    }


#: Où ComfyUI lit les images d'entrée. C'est le seul dossier que
#: `LoadImage` sait nommer, donc le seul endroit où déposer une image de
#: départ. Déduit du processus plutôt que codé en dur serait plus robuste,
#: mais l'installation est fixe sur cette machine et un chemin lisible
#: vaut mieux qu'une déduction qui échoue en silence.
DOSSIER_ENTREE_COMFY = (
    r"C:\AI\Apps\ComfyUI-ROCm\comfyui-rocm-091926\input")


@router.post("/last-frame")
def derniere_image(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Extraire la dernière image d'un plan, pour enchaîner le suivant.

    C'est la moitié manquante de l'enchaînement (HOS-200) : `plan_video`
    sait partir d'une image, mais rien ne savait produire cette image à
    partir du plan précédent. L'écran a besoin des deux pour que « faire
    la suite » tienne en un clic.

    L'image est écrite dans le dossier d'entrée de ComfyUI parce que
    `LoadImage` ne sait lire que là — ce n'est pas un choix de rangement,
    c'est la seule adresse que le nœud accepte.
    """
    import subprocess

    from backend.studio.relecteur import ffmpeg as _localiser_ffmpeg

    source = str(payload.get("video") or "").strip()
    if not source:
        return {"success": False, "error": "il faut le chemin d'un plan"}
    if not os.path.isfile(source):
        return {"success": False, "error": f"introuvable : {source}",
                "raison": "video_absente"}

    ff = _localiser_ffmpeg()
    if not ff:
        return {"success": False, "error": "ffmpeg introuvable",
                "raison": "ffmpeg_absent"}

    nom = str(payload.get("nom") or "").strip()
    if not nom:
        base = os.path.splitext(os.path.basename(source))[0]
        nom = f"suite_{base}.png"
    if not nom.lower().endswith(".png"):
        nom += ".png"
    # Le nom vient de l'appelant : on ne garde que le nom de fichier, pour
    # qu'un « ../.. » ne fasse pas écrire hors du dossier d'entrée.
    nom = os.path.basename(nom)
    cible = os.path.join(DOSSIER_ENTREE_COMFY, nom)

    os.makedirs(DOSSIER_ENTREE_COMFY, exist_ok=True)
    # `-sseof -0.1` : se placer un dixième de seconde avant la fin plutôt
    # que de décoder tout le plan pour n'en garder que la dernière image.
    p = subprocess.run([ff, "-v", "error", "-sseof", "-0.1", "-i", source,
                        "-vframes", "1", "-y", cible],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    # Vérifié sur le disque, pas d'après le code de retour : `ffmpeg` rend
    # 0 dans des cas où il n'a rien écrit — c'est consigné dans
    # `montage.py`, et la même prudence vaut ici.
    if not os.path.isfile(cible) or os.path.getsize(cible) == 0:
        return {"success": False, "raison": "extraction_vide",
                "error": (p.stderr or "aucune image extraite")[:400]}

    return {"success": True, "nom": nom, "chemin": cible,
            "octets": os.path.getsize(cible)}


@router.get("/calibration")
def calibration() -> dict[str, Any]:
    """Ce que le decodeur a reellement mesure sur cette machine (HOS-210).

    L'ecran s'en sert pour dire, avant le clic, si le reglage du plan
    visee a ete **eprouve** ou s'il repose encore sur les paliers ecrits
    dans le code — lesquels se sont deja reveles faux deux fois.
    """
    from backend.studio.calibration import lire_table

    table = lire_table()
    return {
        "mesures": table,
        "compte": len(table),
        # Les paliers de repli, pour que l'ecran puisse dire d'ou vient la
        # valeur qu'il affiche.
        "paliers": [{"volume_max": p, "tuile": t}
                    for p, t in _paliers()],
    }


def _paliers() -> list[tuple[float, int]]:
    from backend.studio.gabarits import PALIERS_TUILE
    return PALIERS_TUILE


@router.post("/calibration")
def calibrer_decodeur(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Mesurer la plus grande tuile qui decode ce plan d'un seul bloc.

    Decode un latent **vide** aux dimensions visees : la memoire du
    decodeur ne depend que des dimensions, jamais du contenu, donc l'essai
    predit exactement ce qui se passera au vrai rendu, sans charger un
    seul modele de diffusion. La recherche part du palier ecrit dans le
    code, puis monte tant que ca passe et descend au premier debordement
    — un a trois essais dans le cas courant.

    Passe par l'arbitrage de la carte comme un rendu : un essai a blanc
    occupe la VRAM tout autant, et le laisser partir pendant qu'une
    mission tient la carte fausserait sa propre mesure.
    """
    from backend.studio.calibration import calibrer, connue

    largeur = int(payload.get("largeur") or 0)
    hauteur = int(payload.get("hauteur") or 0)
    images = int(payload.get("images") or 0)
    if not (largeur and hauteur and images):
        return {"success": False,
                "error": "il faut `largeur`, `hauteur` et `images`"}

    if not payload.get("refaire"):
        deja = connue(largeur, hauteur, images)
        if deja:
            return {"success": True, "tuile": deja, "deja_mesure": True}

    with carte_reservee(BESOIN_DEFAUT) as occ:
        if not occ.obtenu:
            return {"success": False, "raison": "carte_occupee",
                    "error": occ.detail}
        resultat = calibrer(largeur, hauteur, images)

    if not resultat.get("tuile"):
        # Ne jamais dire « aucune tuile ne passe » quand la recherche s'est
        # arretee sur une non-mesure : c'est cette confusion entre « la
        # carte ne peut pas » et « je n'ai pas su lire » qui a produit trois
        # faux resultats pendant la campagne HOS-207.
        raison = resultat.get("raison")
        explications = {
            "aucune_tuile": "aucune tuile ne decode ce plan d'un seul bloc",
            "delai": "l'essai n'a pas abouti dans le temps imparti — un "
                     "decodage qui deborde rampe sur la memoire partagee "
                     "au lieu d'echouer. La mesure est inconnue, pas "
                     "negative, et la carte peut rester occupee : un tel "
                     "decodage ne repond pas a la demande d'arret",
        }
        return {"success": False, "raison": raison,
                "error": explications.get(
                    raison, f"la mesure n'a pas abouti ({raison})"),
                "tentatives": resultat.get("tentatives", [])}
    return {"success": True, **resultat}


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
