"""Des graphes ComfyUI remplis à partir de paramètres explicites (HOS-194).

## Pourquoi ce module ne viole pas la règle qui prime sur tout

Ce dépôt interdit qu'une seconde boucle décide à la place de Hermes Agent,
et j'ai écrit ailleurs qu'« un service qui construit le bon workflow »
serait exactement cela. Ce module n'est pas ce service.

La distinction tient en un mot : **choisir**. Décider quel pipeline
convient à un objectif, c'est raisonner — interdit. Remplir un gabarit
figé avec des paramètres que l'appelant a explicitement fournis, c'est un
formulaire. Rien ici n'infère : ni la résolution, ni la durée, ni le
modèle, ni le nombre d'étapes. Tout est passé, ou vaut son défaut mesuré.

C'est d'ailleurs ce que le cahier des charges prévoyait dès l'origine :
« Le graphe vient de l'appelant — Hermes Agent par ses outils MCP, ou le
Studio Center **par un gabarit**. »

## Ce que les défauts valent, et d'où ils viennent

Chaque valeur par défaut est une mesure, pas une préférence :

- `VAEDecodeTiled` partout, y compris pour une image fixe : le décodage
  non tuilé a réclamé 2,67 Gio de plus sur une carte déjà pleine et a
  produit un `CUDA out of memory` en 1024 × 1024.
- huit étapes : c'est un modèle **distillé**, il ne gagne rien au-delà.
- `cfg` 3.0, `max_shift` 2.05, `base_shift` 0.95 : les valeurs du graphe
  de référence LTX-2.5, éprouvées sur tous les rendus de ce projet.
- 24 images/s, parce que c'est la cadence des plans déjà rendus et que
  changer de cadence changerait la durée sans le dire.
"""

from __future__ import annotations

from typing import Any

#: Ce que les chargeurs attendent, mesuré et retenu au 2026-08-27.
#: Q5_K_M : +12 % de temps sur Q3 pour 46 % de bits en plus, pic VRAM
#: identique. Voir `docs/studio-center.md`.
LTX_MODELE = "LTX-2.5-Distilled-Q5_K_M.gguf"
LTX_ENCODEUR = "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"
LTX_VAE = "ltx-2.5-video-vae-bf16.safetensors"
LTX_VAE_AUDIO = "ltx-2.5-audio-vae-bf16.safetensors"

SDXL_CHECKPOINT = "sd_xl_base_1.0.safetensors"
#: Le VAE corrigé, chargé à part : celui embarqué dans le checkpoint
#: produit des artefacts en fp16, défaut connu de SDXL 1.0.
SDXL_VAE = "sdxl_vae.safetensors"

NEGATIF_DEFAUT = "blurry, distorted, watermark, text, low quality"

#: Les formats proposés, et la raison de chacun. Aucun n'est inventé.
#:
#: Ils sont séparés par moteur, et cette séparation est née d'un défaut :
#: un premier formulaire offrait la même liste aux deux, un rendu SDXL est
#: parti en 768 × 432, et l'image est sortie **tuilée et déformée**. SDXL
#: est entraîné autour du mégapixel et s'effondre loin de ses formats
#: natifs ; LTX, lui, tient 768 × 432 et déborde au-delà de 0,9 Mpx.
#:
#: Une liste commune était donc un piège : elle laissait choisir un format
#: valide pour l'un et ruineux pour l'autre, sans rien dire.
FORMATS: dict[str, tuple[int, int]] = {
    # LTX — mesurés sur cette carte.
    "paysage": (768, 432),
    "paysage_large": (1280, 720),
    "portrait": (704, 1280),
    # SDXL — ses compartiments d'entraînement, à un mégapixel près.
    "carre": (1024, 1024),
    "paysage_sdxl": (1344, 768),
    "portrait_sdxl": (832, 1216),
}

#: Ce que chaque moteur sait rendre, et avec quoi commencer. Le premier
#: de la liste est le défaut.
FORMATS_PAR_MOTEUR: dict[str, list[str]] = {
    "ltx": ["paysage", "paysage_large", "portrait"],
    "sdxl": ["carre", "paysage_sdxl", "portrait_sdxl"],
}

#: Au-delà, LTX est à la limite de cette carte pour une image fixe :
#: 1024 × 1024 n'a pas abouti, 1280 × 720 passe de justesse à 14,58 Gio.
#: SDXL, lui, tient 1024 × 1024 en 45 s. Le garde-fou vaut donc pour LTX
#: seulement, et il refuse plutôt que de laisser déborder en silence.
PIXELS_MAX_LTX_IMAGE = 1024 * 576


class GabaritInvalide(ValueError):
    """Un paramètre est hors de ce que cette machine sait rendre."""


def _dimensions(format_: str, largeur: int | None,
                hauteur: int | None) -> tuple[int, int]:
    if largeur and hauteur:
        return int(largeur), int(hauteur)
    if format_ not in FORMATS:
        raise GabaritInvalide(
            f"format inconnu : {format_!r} — attendus {sorted(FORMATS)}")
    return FORMATS[format_]


def plan_video(consigne: str, *, format_: str = "paysage",
               largeur: int | None = None, hauteur: int | None = None,
               images: int = 49, etapes: int = 8, graine: int = 0,
               cadence: float = 24.0, negatif: str = NEGATIF_DEFAUT,
               avec_son: bool = False,
               prefixe: str = "studio/plan") -> dict[str, Any]:
    """Un plan vidéo LTX-2.5, avec son propre son si on le demande.

    `avec_son` fait passer les deux latents dans le **même**
    échantillonnage — c'est ce qui rend le son synchrone plutôt que
    juxtaposé, et cela coûte 21 % de temps mesurés.
    """
    if not consigne.strip():
        raise GabaritInvalide("consigne vide : il n'y aurait rien à rendre")
    l, h = _dimensions(format_, largeur, hauteur)
    images = max(1, int(images))

    g: dict[str, Any] = {
        "1": {"class_type": "UnetLoaderGGUF",
              "inputs": {"unet_name": LTX_MODELE}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": LTX_ENCODEUR, "type": "ltxv"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": LTX_VAE}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": consigne, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negatif, "clip": ["2", 0]}},
        "6": {"class_type": "EmptyLTXVLatentVideo",
              "inputs": {"width": l, "height": h, "length": images,
                         "batch_size": 1}},
        "7": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["4", 0], "negative": ["5", 0],
                         "frame_rate": cadence}},
        "8": {"class_type": "ModelSamplingLTXV",
              "inputs": {"model": ["1", 0], "max_shift": 2.05,
                         "base_shift": 0.95}},
        "9": {"class_type": "KSamplerSelect",
              "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "LTXVScheduler",
               "inputs": {"steps": int(etapes), "max_shift": 2.05,
                          "base_shift": 0.95, "stretch": True,
                          "terminal": 0.1}},
    }

    latent_depart = ["6", 0]
    if avec_son:
        g["3b"] = {"class_type": "LTXVAudioVAELoader",
                   "inputs": {"ckpt_name": LTX_VAE_AUDIO}}
        g["6b"] = {"class_type": "LTXVEmptyLatentAudio",
                   "inputs": {"frames_number": images, "frame_rate": cadence,
                              "batch_size": 1, "audio_vae": ["3b", 0]}}
        g["6c"] = {"class_type": "LTXVConcatAVLatent",
                   "inputs": {"video_latent": ["6", 0],
                              "audio_latent": ["6b", 0]}}
        latent_depart = ["6c", 0]

    g["11"] = {"class_type": "SamplerCustom",
               "inputs": {"model": ["8", 0], "add_noise": True,
                          "noise_seed": int(graine), "cfg": 3.0,
                          "positive": ["7", 0], "negative": ["7", 1],
                          "sampler": ["9", 0], "sigmas": ["10", 0],
                          "latent_image": latent_depart}}

    if avec_son:
        g["12s"] = {"class_type": "LTXVSeparateAVLatent",
                    "inputs": {"av_latent": ["11", 0]}}
        latent_video, latent_audio = ["12s", 0], ["12s", 1]
    else:
        latent_video, latent_audio = ["11", 0], None

    g["12"] = {"class_type": "VAEDecodeTiled",
               "inputs": {"samples": latent_video, "vae": ["3", 0],
                          "tile_size": 256, "overlap": 32,
                          "temporal_size": 16, "temporal_overlap": 4}}

    entrees_video: dict[str, Any] = {"images": ["12", 0], "fps": cadence}
    if latent_audio is not None:
        g["13b"] = {"class_type": "LTXVAudioVAEDecode",
                    "inputs": {"samples": latent_audio, "audio_vae": ["3b", 0]}}
        entrees_video["audio"] = ["13b", 0]

    g["13"] = {"class_type": "CreateVideo", "inputs": entrees_video}
    g["14"] = {"class_type": "SaveVideo",
               "inputs": {"video": ["13", 0], "filename_prefix": prefixe,
                          "format": "auto", "codec": "auto"}}
    return g


def image_ltx(consigne: str, *, format_: str = "paysage",
              largeur: int | None = None, hauteur: int | None = None,
              etapes: int = 8, graine: int = 0,
              negatif: str = NEGATIF_DEFAUT,
              prefixe: str = "studio/image") -> dict[str, Any]:
    """Une image fixe par LTX — un plan d'une seule image.

    À préférer quand l'image doit se raccorder à de la vidéo : LTX rend
    la lumière et l'ambiance que SDXL aplatit. Il est en revanche mou sur
    l'objet précis, et à la limite de la carte au-delà de 0,9 mégapixel —
    d'où le refus explicite plutôt qu'un débordement silencieux.
    """
    l, h = _dimensions(format_, largeur, hauteur)
    if l * h > PIXELS_MAX_LTX_IMAGE:
        raise GabaritInvalide(
            f"{l} × {h} dépasse ce que LTX rend de façon fiable en image "
            f"fixe sur cette carte ({PIXELS_MAX_LTX_IMAGE // 1000} kpx "
            "mesurés). Prendre SDXL, ou réduire le format.")

    g = plan_video(consigne, largeur=l, hauteur=h, images=1, etapes=etapes,
                   graine=graine, negatif=negatif, prefixe=prefixe)
    # Une image ne s'encode pas en vidéo : on remplace la sortie.
    for cle in ("13", "14"):
        g.pop(cle, None)
    g["13"] = {"class_type": "SaveImage",
               "inputs": {"images": ["12", 0], "filename_prefix": prefixe}}
    return g


def image_sdxl(consigne: str, *, format_: str = "carre",
               largeur: int | None = None, hauteur: int | None = None,
               etapes: int = 25, graine: int = 0, cfg: float = 7.0,
               negatif: str = NEGATIF_DEFAUT,
               prefixe: str = "studio/image") -> dict[str, Any]:
    """Une image fixe par SDXL — net, gravé, cinq fois plus rapide.

    Vingt-cinq étapes et `cfg` 7.0 : les valeurs de référence de SDXL,
    et non celles de LTX. Un modèle distillé se contente de huit étapes ;
    celui-ci n'est pas distillé et s'en trouverait appauvri.
    """
    if not consigne.strip():
        raise GabaritInvalide("consigne vide : il n'y aurait rien à rendre")
    l, h = _dimensions(format_, largeur, hauteur)
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": SDXL_CHECKPOINT}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": SDXL_VAE}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": consigne, "clip": ["1", 1]}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negatif, "clip": ["1", 1]}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": l, "height": h, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "seed": int(graine),
                         "steps": int(etapes), "cfg": cfg,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras",
                         "denoise": 1.0, "positive": ["3", 0],
                         "negative": ["4", 0], "latent_image": ["5", 0]}},
        # Pas de tuilage : le VAE de SDXL fait 335 Mio contre 1,37 Go pour
        # celui de LTX, et 1024 × 1024 est passé en 45 s à 13,46 Gio.
        "7": {"class_type": "VAEDecode",
              "inputs": {"samples": ["6", 0], "vae": ["2", 0]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"images": ["7", 0], "filename_prefix": prefixe}},
    }


#: Ce que l'écran propose, et ce que chaque gabarit attend. Décrit ici
#: plutôt que dupliqué dans le frontend : deux listes du même fait
#: finissent par diverger.
CATALOGUE: dict[str, dict[str, Any]] = {
    "plan_video": {
        "titre": "Plan vidéo",
        "moteur": "LTX-2.5",
        "sortie": "video",
        # Pas de « ≈ 5 min par seconde de vidéo » : cette règle venait du
        # seul rendu vertical et surestimait de 144 % en 768×432. Le temps
        # suit la surface autant que la durée, et l'estimation exacte est
        # sous le formulaire, calculée pour le format choisi.
        "note": "3 à 20 min selon le format et la durée, mesurés.",
        "parametres": ["format", "images", "cadence", "etapes", "graine",
                       "avec_son", "negatif", "prefixe"],
        "formats": FORMATS_PAR_MOTEUR["ltx"],
    },
    "image_sdxl": {
        "titre": "Image — SDXL",
        "moteur": "SDXL 1.0",
        "sortie": "image",
        "note": "35 à 45 s. Objet net, détail gravé ; lumière plus plate.",
        "parametres": ["format", "etapes", "graine", "cfg", "negatif",
                       "prefixe"],
        "formats": FORMATS_PAR_MOTEUR["sdxl"],
    },
    "image_ltx": {
        "titre": "Image — LTX",
        "moteur": "LTX-2.5",
        "sortie": "image",
        "note": "≈ 170 s. Lumière et ambiance ; mou sur l'objet précis. "
                "Limité à 0,9 mégapixel sur cette carte.",
        "parametres": ["format", "etapes", "graine", "negatif", "prefixe"],
        "formats": ["paysage"],
    },
}

#: Les longueurs de latent que LTX accepte sont de la forme `8k + 1` — 49
#: images pour 2 s, 97 pour 4 s, mesurées et consignées dans
#: `docs/studio-center.md`. À 24 im/s la coïncidence est exacte : 24 est un
#: multiple de 8, donc toute durée en secondes entières tombe pile sur une
#: longueur valide (`24·N + 1`). C'est pourquoi l'écran peut proposer une
#: durée sans jamais mentir sur ce qui sera rendu.
#:
#: Exposé ici plutôt que recopié dans le frontend, comme le reste du
#: catalogue : deux listes du même fait finissent par diverger.
PAS_IMAGES = 8
IMAGES_MAX = 257


def images_pour_duree(duree_s: float, cadence: float = 24.0) -> int:
    """La longueur valide la plus proche de la durée demandée.

    Rend un nombre d'images, jamais une durée : c'est `length` que le nœud
    `EmptyLTXVLatentVideo` attend, et l'arrondi doit être visible à
    l'appelant plutôt que subi. `duree_reelle_s()` dit ce qu'il obtiendra.
    """
    brut = max(0.0, float(duree_s)) * max(1.0, float(cadence))
    images = round(brut / PAS_IMAGES) * PAS_IMAGES + 1
    return max(1, min(IMAGES_MAX, images))


def duree_reelle_s(images: int, cadence: float = 24.0) -> float:
    """La durée qu'un nombre d'images produit réellement."""
    return max(1, int(images)) / max(1.0, float(cadence))


#: Le coût de calcul d'un plan, ajusté sur les **trois** rendus réels de
#: `docs/studio-center.md` — 512×288/49 en 170 s, 768×432/49 en 251 s,
#: 704×1280/97 en 1 218 s.
#:
#: L'écran annonçait jusqu'ici « ≈ 5 min par seconde de vidéo finie ».
#: Cette règle vient du seul rendu vertical et ne vaut que pour lui : elle
#: surestime de **+144 %** en 768×432 et de **+260 %** en 512×288, parce
#: que le temps suit les pixels autant que les images, pas la durée seule.
#: Annoncer vingt minutes pour un rendu qui en prend quatre décourage un
#: essai qui aurait été bon marché — l'erreur va dans le sens qui coûte le
#: plus cher à l'usage.
#:
#: Ajustement linéaire par moindres carrés sur `pixels × images`, écart
#: maximal 11 % sur les trois points. Trois points ne font pas une loi :
#: c'est une extrapolation, et l'écran doit le dire.
COUT_FIXE_S = 56.0
COUT_PAR_MPX_IMAGE_S = 13.27


def duree_calcul_s(largeur: int, hauteur: int, images: int) -> float:
    """Le temps de calcul attendu, en secondes."""
    mpx_images = (int(largeur) * int(hauteur) * max(1, int(images))) / 1_000_000
    return COUT_FIXE_S + COUT_PAR_MPX_IMAGE_S * mpx_images

_FABRIQUES = {
    "plan_video": plan_video,
    "image_sdxl": image_sdxl,
    "image_ltx": image_ltx,
}


def composer(gabarit: str, consigne: str, **parametres: Any) -> dict[str, Any]:
    """Rendre le graphe d'un gabarit, ou lever en nommant ce qui manque."""
    fabrique = _FABRIQUES.get(gabarit)
    if fabrique is None:
        raise GabaritInvalide(
            f"gabarit inconnu : {gabarit!r} — attendus {sorted(_FABRIQUES)}")
    connus = fabrique.__code__.co_varnames[:fabrique.__code__.co_argcount +
                                           fabrique.__code__.co_kwonlyargcount]
    inconnus = [k for k in parametres if k not in connus]
    if inconnus:
        # Refuser plutôt qu'ignorer : un paramètre silencieusement écarté
        # se lit comme un réglage qui « ne fait rien ».
        raise GabaritInvalide(
            f"paramètre(s) inconnu(s) pour {gabarit} : {inconnus}")
    return fabrique(consigne, **parametres)


__all__ = ["CATALOGUE", "COUT_FIXE_S", "COUT_PAR_MPX_IMAGE_S", "FORMATS",
           "FORMATS_PAR_MOTEUR", "IMAGES_MAX", "PAS_IMAGES",
           "GabaritInvalide", "composer", "duree_calcul_s", "duree_reelle_s",
           "image_ltx", "image_sdxl", "images_pour_duree", "plan_video"]
