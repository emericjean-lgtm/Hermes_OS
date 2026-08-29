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

#: Ce que tous les plans refusent, en plus du négatif par défaut. Le
#: cahier des charges les énumère ; les mettre ici évite de les répéter
#: treize fois et d'en oublier un.
NEGATIF = ("cartoon, anime, illustration, fantasy, science fiction, "
           "hyper-saturated colors, oversaturated, glowing artifacts, "
           "lens flare, explosion, floating objects, distorted anatomy, "
           "deformed hands, extra limbs, text, logo, watermark, subtitles, "
           "blurry, low quality, jpeg artifacts")

STYLE = ("photorealistic, cinematic, documentary realism, physically "
         "believable lighting, natural composition, realistic human "
         "proportions, high-end cinematic photography, no text, no logos, "
         "no watermark")

CONTINUITE = ("stable architecture, coherent environment, consistent "
              "lighting throughout the shot, smooth continuous camera "
              "motion, no sudden cuts, natural parallax")


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
    _image("ref01",
           "night view of a modern Parisian street, realistic apartment "
           "buildings, wet pavement reflecting warm street lights, a few "
           "pedestrians walking, distant cars, clear dark blue night sky, "
           "a large bright full Moon clearly visible above the city, "
           "moonlight illuminating rooftops, subtle atmospheric haze"),
    _clip("p01",
          "Continue naturally from the reference image. A slow cinematic "
          "camera movement forward through the quiet Parisian street at "
          "night. Pedestrians and cars move naturally and subtly. The "
          "bright full Moon remains clearly visible in the sky. Realistic "
          "atmospheric movement, natural reflections on wet pavement.",
          depend_de="ref01"),
    _clip("p02a",
          "Continue directly from the provided reference frame with "
          "exactly the same city, architecture, lighting and camera "
          "position. The camera slowly tilts upward toward the full Moon. "
          "The night remains calm. The Moon is visually stable and "
          "detailed while subtle clouds move naturally across the sky.",
          depend_de="p01"),
    # La disparition n'est pas demandée au modèle : la caméra redescend,
    # la Lune sort du cadre, le ciel est décrit vide et sombre. C'est la
    # coupe entre 02A et 02B qui la porte.
    _clip("p02b",
          "Continue directly from the reference frame. The camera slowly "
          "tilts back down from the empty sky toward the street below. "
          "The sky above the city is now completely empty and much "
          "darker, with no bright light source in it. The street is lit "
          "only by its own street lamps, and the rooftops have lost their "
          "pale illumination. A few pedestrians below slow down and look "
          "upward. Realistic lighting transition, physically believable "
          "illumination change, no magical effects.",
          depend_de="p02a"),

    # ── Transition espace : image fixe animée au montage ─────────────
    _image("img03",
           "view of planet Earth from space at night, realistic "
           "continents and oceans, dense city lights on the visible side "
           "of the planet, thin blue atmospheric layer, deep black space, "
           "stars, no Moon anywhere in the scene, NASA-inspired "
           "photographic realism, scientifically plausible"),

    # ── Séquence océan : 04A → 04B ──────────────────────────────────
    _image("ref04",
           "aerial view of a European Atlantic coastline at night "
           "transitioning toward dawn, enormous dark ocean extending to "
           "the horizon, realistic waves approaching the shore, rocky "
           "coastline, small coastal lights in the distance, physically "
           "accurate water reflections, atmospheric mist"),
    _clip("p04a",
          "Continue naturally from the reference image. Slow aerial "
          "cinematic camera movement following the coastline. Ocean waves "
          "move naturally toward the shore while the camera advances "
          "smoothly. The water surface remains coherent across frames "
          "with stable coastline geometry and realistic wave motion.",
          depend_de="ref04"),
    _clip("p04b",
          "Continue directly from the reference frame. The camera "
          "gradually pulls higher above the coastline, revealing a larger "
          "portion of the ocean. The waves continue their natural "
          "movement, but the overall tidal motion appears unusually "
          "subdued and calm. Maintain the exact same coastline, lighting "
          "and atmosphere from the reference image. Realistic water "
          "physics, no tsunami, no exaggerated waves.",
          depend_de="p04a"),

    # ── La nuit plus sombre : image fixe animée ─────────────────────
    _image("img05",
           "night landscape with an exceptionally dark natural sky, "
           "remote European countryside, mountains and forests visible "
           "only as subtle silhouettes, an extraordinarily clear star "
           "field, natural darkness, faint distant horizon glow, "
           "high-end astrophotography combined with cinematic landscape "
           "photography, no Moon, no artificial lights"),

    # ── L'humain face au nouveau ciel ──────────────────────────────
    _image("ref06",
           "a lone person standing on a quiet hill overlooking a dark "
           "European landscape at night, seen from behind, looking upward "
           "toward an unusually dark moonless sky filled with stars, "
           "subtle silhouette, realistic clothing, gentle wind moving "
           "clothing slightly, deep natural darkness, emotional but "
           "restrained documentary cinematography"),
    _clip("p06",
          "Continue naturally from the reference image. The camera slowly "
          "moves closer to the person from behind while the person "
          "remains looking toward the dark star-filled sky. Subtle "
          "natural wind moves the clothing and nearby grass. The night "
          "sky remains stable. Maintain the exact character silhouette, "
          "environment and lighting from the reference image.",
          depend_de="ref06"),

    # ── Conclusion et boucle : images fixes animées ────────────────
    _image("img07",
           "view of planet Earth from deep space, illuminated by distant "
           "sunlight, no Moon anywhere in the scene, thin blue "
           "atmosphere, realistic cloud systems, natural planetary "
           "proportions, subtle terminator line between day and night, "
           "vast deep black space, elegant cinematic composition"),
    _image("img08",
           "night view of the same modern Parisian street, almost "
           "identical framing to the opening scene, wet pavement "
           "reflecting warm street lights, realistic buildings, quiet "
           "atmosphere, very dark empty sky, no Moon visible, subtle "
           "atmospheric haze"),
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
