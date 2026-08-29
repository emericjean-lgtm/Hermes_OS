"""Production « Et si la Lune disparaissait ? » — TikTok V1 (HOS-211).

## Ce que ce fichier est, et ce qu'il n'est pas

C'est un **cahier de production**, pas un moteur. Il décrit dix plans,
leurs consignes et leurs dépendances, puis les remet à la file de nuit qui
existe déjà. Il ne raisonne pas, ne choisit pas de modèle, n'invente pas de
réglage : la tuile de décodage vient de la calibration mesurée, le format
du catalogue, l'arbitrage de la carte de `arbitrage.py`.

La règle qui prime dans ce dépôt s'applique ici comme ailleurs — ce script
orchestre des outils, il ne remplace pas l'agent.

## L'ordre, et pourquoi il n'est pas décoratif

Un plan enchaîné ne peut partir qu'après celui dont il reprend l'image.
La file résout les dépendances dans l'ordre de la liste et refuse une
dépendance vers l'aval : la séquence ci-dessous **est** le graphe.

## Les trois écarts au cahier des charges d'origine, et leur raison

**PLAN 02B ne demande pas au modèle de faire disparaître la Lune.** Un
modèle distillé en huit étapes, sommé de faire s'évanouir un objet en
cours de plan avec le changement d'éclairage global qui va avec, produit
un morphing ou ignore l'instruction. Le plan redescend donc vers la rue :
la Lune sort du cadre par le mouvement de caméra, le ciel est décrit comme
vide et sombre, et c'est la **coupe** entre 02A et 02B qui porte la
disparition. C'est ainsi qu'un documentaire le ferait.

**Les images de référence sont en 768 × 1344, pas en 704 × 1280.** SDXL
est entraîné sur des rapports proches du mégapixel ; 704 × 1280 en sort et
dégrade l'anatomie, ce qui compte pour le PLAN 06 qui porte un personnage.
Le recadrage centré vers 11:20 coûte 3,8 % de champ latéral et se fait au
moment de l'enchaînement.

**Les plans 03, 05, 07 et 08 ne passent pas par LTX.** Le cahier le
permet, et ça épargne quatre fois vingt minutes pour des plans où le
mouvement demandé est un zoom lent qu'un montage rend mieux qu'un modèle.

## Ce que ce script ne fait pas

Il ne monte pas. La file rend les plans ; l'assemblage, la narration et
les sous-titres sont une seconde étape, parce qu'ils dépendent de ce que
la nuit aura réellement retenu — et qu'assembler dix plans dont trois ont
échoué produirait une vidéo plus courte, sans erreur.
"""

from __future__ import annotations

#: 97 images à 24 im/s = 4,04 s. La contrainte du modèle est `8k+1` ;
#: 97 est la valeur valide la plus proche de quatre secondes.
IMAGES_4S = 97
IMAGES_2S = 49

#: Le format de rendu. Les images de référence sont plus larges et
#: recadrées à l'enchaînement — voir l'en-tête.
FORMAT_VIDEO = "portrait"          # 704 × 1280
REF_L, REF_H = 768, 1344           # bucket natif SDXL le plus proche

#: Une graine par plan, fixée. HOS-203 a montré que la graine domine tout
#: le reste : sans elle, refaire un seul plan raté obligerait à refaire la
#: chaîne entière, et un plan validé ne serait pas reproductible.
GRAINES = {
    "ref01": 101, "p01": 1010, "p02a": 1020, "p02b": 1021,
    "img03": 103, "ref04": 104, "p04a": 1040, "p04b": 1041,
    "img05": 105, "ref06": 106, "p06": 1060,
    "img07": 107, "img08": 108,
}

#: Ce que tous les plans refusent. La seconde moitié vient des défauts
#: **constatés** sur le premier rendu, pas d'une liste de précaution :
#: une voiture garée sur le trottoir, des passants trop nombreux et trop
#: rapides, qui apparaissaient et disparaissaient d'un instant à l'autre.
#:
#: Chaque terme répond à l'un d'eux. Les garder groupés ici évite de les
#: répéter treize fois et d'en oublier un.
#:
#: **Effet de bord mesuré** : les cinq formulations sur la voiture mal
#: garée suppriment la classe d'objet entière — la référence corrigée
#: n'a plus aucun véhicule. Les consignes le disent donc désormais
#: aussi. Elles demandaient des voitures que le négatif interdisait, et
#: le relecteur a rejeté l'image pour cette contradiction, à raison :
#: c'est la consigne qui était fautive, pas l'image.
NEGATIF = (
    # Style
    "cartoon, anime, illustration, fantasy, science fiction, "
    "hyper-saturated colors, oversaturated, glowing artifacts, lens flare, "
    "explosion, floating objects, text, logo, watermark, subtitles, "
    "blurry, low quality, jpeg artifacts, "
    # La voiture sur le trottoir
    "car parked on the sidewalk, vehicle on the pavement, car on footpath, "
    "vehicle blocking the walkway, badly parked car, "
    # La foule illisible
    "crowd, many people, busy street, heavy traffic, "
    "group of pedestrians, cluttered composition, "
    # La phase de la Lune. Le modele a rendu un croissant deux fois de
    # suite la ou la consigne demandait une pleine Lune. Sur un sujet qui
    # est *la disparition de la Lune*, ce n'est pas un detail de rendu :
    # c'est le sujet.
    "crescent moon, half moon, gibbous moon, quarter moon, moon phase, "
    "partially lit moon, lunar eclipse, dark moon, ring of light, "
    # La vitesse et l'incohérence des déplacements
    "time-lapse, timelapse, sped-up footage, fast motion, hyperlapse, "
    "people appearing and disappearing, flickering figures, "
    "morphing people, duplicated limbs, distorted anatomy, deformed hands, "
    "extra limbs, teleporting subjects, popping objects")

STYLE = ("photorealistic, cinematic, documentary realism, physically "
         "believable lighting, natural composition, realistic human "
         "proportions, high-end cinematic photography, no text, no logos, "
         "no watermark")

#: La leçon du premier rendu, en une phrase par défaut constaté.
#:
#: **Nommer ce qui ne bouge pas.** LTX anime tout ce qu'on ne fige pas
#: explicitement. L'architecture, les voitures garées et le mobilier
#: urbain doivent être déclarés immobiles, sinon ils respirent.
#:
#: **Dire la vitesse réelle.** Le modèle comprime volontiers une action
#: entière dans les quatre secondes qu'on lui donne, ce qui produit
#: exactement l'impression d'accéléré signalée. « Real-time speed » et
#: « not a time-lapse » sont les deux formules qui la corrigent.
#:
#: **Interdire les entrées et sorties de cadre.** Un passant qui entre
#: pendant le plan n'a aucune histoire avant : le modèle le fabrique
#: image par image, et il scintille. C'est la cause des apparitions et
#: disparitions.
CONTINUITE = (
    "The architecture, the street furniture and the ground stay "
    "perfectly static and never change shape. No object and "
    "no person enters or leaves the frame during the shot. Real-time "
    "speed, this is not a time-lapse and nothing is sped up. One single "
    "continuous take, stable framing, consistent lighting throughout, "
    "natural parallax, no sudden cuts")


def _image(identifiant: str, consigne: str) -> dict:
    """Une référence SDXL, au bucket natif du modèle."""
    return {
        "identifiant": identifiant,
        "gabarit": "image_sdxl",
        "consigne": f"{consigne}, {STYLE}",
        "parametres": {"largeur": REF_L, "hauteur": REF_H,
                       "graine": GRAINES[identifiant], "negatif": NEGATIF,
                       "prefixe": f"lune/{identifiant}"},
    }


def _clip(identifiant: str, consigne: str, depend_de: str,
          images: int = IMAGES_4S) -> dict:
    """Un plan LTX qui repart d'une image — la seule façon d'enchaîner."""
    return {
        "identifiant": identifiant,
        "gabarit": "plan_video",
        "consigne": f"{consigne} {CONTINUITE}, {STYLE}",
        "depend_de": depend_de,
        "parametres": {"format_": FORMAT_VIDEO, "images": images,
                       "graine": GRAINES[identifiant], "negatif": NEGATIF,
                       "avec_son": False, "prefixe": f"lune/{identifiant}"},
    }


PLANS: list[dict] = [
    # ── Séquence ville : 01 → 02A → 02B ──────────────────────────────
    #
    # La rue est **déserte**. Ce n'est pas un appauvrissement : les
    # passants du premier rendu apparaissaient et disparaissaient parce
    # qu'ils faisaient trop peu de pixels pour que le modèle garde leur
    # identité d'une image à l'autre. Une rue vide à trois heures du
    # matin est plausible, plus calme — donc plus juste pour le sujet —
    # et techniquement stable. Le seul humain de la séquence arrive au
    # plan 02B, immobile, quand il faut une réaction.
    _image("ref01",
           "a large perfectly round fully lit full Moon, a complete "
           "bright white disc high in a clear dark blue night sky, above "
           "a quiet Parisian street. The street is completely deserted, "
           "no pedestrians and no vehicles at all. Haussmann stone "
           "apartment buildings on both sides, warm sodium street lamps, "
           "wet cobblestone road reflecting the lamps, empty clean "
           "pavements, zinc rooftops. Cold moonlight on the roofs, still "
           "and silent atmosphere. Full-frame camera, 35 mm lens, long "
           "exposure, natural night colours"),
    _clip("p01",
          "Continue from the reference image. The camera drifts forward "
          "along the empty street at walking pace, an almost "
          "imperceptible dolly. The street stays deserted for the whole "
          "shot. The only things that move are the camera itself, the "
          "faint reflections shifting on the wet cobblestones, and a "
          "thin "
          "wisp of haze. The full Moon holds its exact position and size "
          "in the sky.",
          depend_de="ref01"),
    _clip("p02a",
          "Continue from the reference frame with exactly the same "
          "street, the same buildings and the same lighting. The camera "
          "tilts upward slowly and evenly toward the full Moon, ending "
          "on the sky above the rooftops. The Moon keeps its exact shape "
          "and brightness. A few thin clouds drift slowly across it. "
          "Nothing else in the frame moves.",
          depend_de="p01"),
    # La disparition n'est pas demandée au modèle : la caméra redescend,
    # la Lune sort du cadre par le mouvement, et c'est la coupe entre 02A
    # et 02B qui la porte. Un seul humain, immobile — le mouvement humain
    # le plus sûr qu'on puisse demander.
    _clip("p02b",
          "Continue from the reference frame. The camera tilts slowly "
          "back down from the sky toward the street below. The sky above "
          "the city is completely empty and much darker, with no bright "
          "light source anywhere in it. The rooftops have lost their "
          "pale illumination and the street is lit only by its own "
          "sodium lamps. One single person stands motionless on the "
          "pavement, seen from behind, head tilted up toward the empty "
          "sky. That person does not walk and does not turn.",
          depend_de="p02a"),

    # ── Transition espace : image fixe animée au montage ─────────────
    _image("img03",
           "planet Earth seen from space at night, realistic continents "
           "and oceans, dense warm city lights on the dark side, thin "
           "blue atmospheric limb, deep black space with faint stars, no "
           "Moon anywhere in the frame, NASA orbital photography, "
           "scientifically plausible, no lens flare"),

    # ── Séquence océan : 04A → 04B ──────────────────────────────────
    _image("ref04",
           "aerial night photograph of a European Atlantic coastline "
           "just before dawn, a vast dark ocean stretching to the "
           "horizon, long regular swell rolling toward a rocky shore, "
           "dark granite rocks, two or three small distant lights on the "
           "coast, physically accurate water reflections, low "
           "atmospheric mist, deep blue hour colours, aerial documentary "
           "photography"),
    _clip("p04a",
          "Continue from the reference image. The camera advances "
          "smoothly and slowly above the coastline, following the shore. "
          "The swell rolls toward the rocks at the speed of real ocean "
          "waves, each wave keeping its shape as it travels. The "
          "coastline geometry and the rocks are completely fixed.",
          depend_de="ref04"),
    _clip("p04b",
          "Continue from the reference frame. The camera rises slowly "
          "and steadily, revealing more of the open ocean. The same "
          "coastline, the same light and the same atmosphere as the "
          "reference. The swell keeps moving but stays low and unusually "
          "calm, with small gentle waves, no breaking surf, no "
          "whitewater walls and no tsunami.",
          depend_de="p04a"),

    # ── La nuit plus sombre : image fixe animée ─────────────────────
    _image("img05",
           "night landscape under an exceptionally dark sky, remote "
           "European countryside, low mountains and forest visible only "
           "as soft silhouettes against the horizon, an extraordinarily "
           "dense star field, natural darkness with no moonlight, faint "
           "airglow near the horizon, long-exposure astrophotography "
           "combined with landscape photography, no Moon, no artificial "
           "lights, no light pollution"),

    # ── L'humain face au nouveau ciel ──────────────────────────────
    _image("ref06",
           "one lone person standing on a quiet grassy hill at night, "
           "seen from behind, full body, looking up at an unusually dark "
           "moonless sky filled with stars, dark simple coat, natural "
           "human proportions, deep natural darkness, a dark European "
           "landscape far below, restrained documentary photography, "
           "single subject, nobody else in the frame"),
    _clip("p06",
          "Continue from the reference image. The camera moves toward "
          "the person very slowly from behind. The person stays exactly "
          "where they are, facing away, head tilted up at the sky, and "
          "does not walk or turn around. A light wind moves the fabric "
          "of the coat and the grass around them. The star field stays "
          "fixed. Nobody else appears at any point.",
          depend_de="ref06"),

    # ── Conclusion et boucle : images fixes animées ────────────────
    _image("img07",
           "planet Earth seen from deep space, lit by distant sunlight, "
           "no Moon anywhere in the frame, thin blue atmosphere, "
           "realistic cloud systems, natural planetary proportions, a "
           "soft terminator line between day and night, vast black "
           "space, elegant simple composition, no science fiction "
           "elements"),
    _image("img08",
           "night photograph of the same quiet Parisian street, almost "
           "identical framing to the opening shot, completely deserted, "
           "no pedestrians, no vehicles, the same Haussmann buildings, "
           "the same street lamps, wet cobblestones reflecting them, "
           "and a "
           "completely empty very dark sky above the rooftops with no "
           "Moon anywhere"),
]

#: L'ordre du montage, et la façon dont chaque plan y arrive. Les plans
#: `anime` sont des images fixes : `montage.animer` en fait des clips au
#: format des autres, sans quoi `concat` les refuserait.
MONTAGE: list[dict] = [
    {"plan": "p01", "source": "ltx"},
    {"plan": "p02a", "source": "ltx"},
    {"plan": "p02b", "source": "ltx"},
    {"plan": "img03", "source": "anime", "duree_s": 4.0, "sens": "avant"},
    {"plan": "p04a", "source": "ltx"},
    {"plan": "p04b", "source": "ltx"},
    {"plan": "img05", "source": "anime", "duree_s": 4.0, "sens": "avant"},
    {"plan": "p06", "source": "ltx"},
    {"plan": "img07", "source": "anime", "duree_s": 4.0, "sens": "arriere"},
    {"plan": "img08", "source": "anime", "duree_s": 2.0, "sens": "avant"},
]

#: La narration, découpée là où le cahier demande une respiration. Une
#: réplique par bloc : `coller_voix` intercale les silences, que
#: Chatterbox ne produit pas — il lit ce qu'on lui donne.
NARRATION: list[tuple[str, str]] = [
    ("n1", "Imagine que la Lune disparaisse cette nuit."),
    ("n2", "Pas qu'elle explose. Pas qu'elle s'éloigne. "
           "Elle disparaît simplement."),
    ("n3", "La première chose que tu remarquerais serait le ciel. "
           "Les nuits deviendraient beaucoup plus sombres."),
    ("n4", "Mais le vrai problème serait ailleurs."),
    ("n5", "Sans la Lune, les marées s'affaibliraient considérablement."),
    ("n6", "Et à long terme, notre planète elle-même changerait."),
    ("n7", "Et ça ne serait que le début."),
]

__all__ = ["FORMAT_VIDEO", "IMAGES_2S", "IMAGES_4S", "MONTAGE", "NARRATION",
           "PLANS"]
