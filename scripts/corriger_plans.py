"""Refaire les plans qui demandaient au modele de retrancher (HOS-212).

## La leçon, en une phrase

**LTX n'enleve pas ce qu'on lui donne en entree.** Deux plans rejetes la
meme nuit, pour deux sujets sans rapport, et la meme cause :

| plan | ce qu'on demandait | verdict du relecteur |
|---|---|---|
| `p02b` | que la pleine Lune de l'image de depart ne soit plus la | « sky is not empty/darker (bright moon present) » |
| `p04b` | que la houle de l'image de depart s'apaise | « ocean is too rough for the "low and unusually calm" description » |

Les deux repartaient de la derniere image du plan precedent, et les deux
demandaient **moins** que ce qu'elle montrait. Un modele distille en huit
etapes continue ce qu'il voit ; il ne le defait pas.

## Ce que fait cette version

Chaque plan repart d'une **nouvelle image de reference qui montre deja
l'etat vise**, generee avec **la meme graine que la reference d'origine**
et une consigne qui n'en differe que par ce qui doit changer. SDXL, a
graine egale et consigne quasi identique, rend une image tres proche :
meme rue ou meme cote, meme lumiere — et le ciel vide, ou la mer calme.

Le changement est alors porte par la **coupe** entre les deux plans, pas
par le modele. C'est ainsi qu'un documentaire le ferait, et c'est le seul
moyen fiable avec les outils en place.

## Ce que ca coute, et ce que ca aurait coute

Deux images (45 s chacune) et deux plans (23 min chacun). Contre 46
minutes pour redemander au modele deux choses qu'il vient de refuser.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
sys.path.insert(0, os.path.dirname(ICI))

import production_lune as P  # noqa: E402

API = "http://127.0.0.1:8010/api/v1"
SORTIE = r"E:\YouTube\Generations\lune_v4"

#: Une correction : le plan a refaire, l'image de reference qui montre
#: **deja** l'etat vise, et la graine de la reference d'origine — c'est
#: elle qui fait que les deux images montrent le meme lieu. La changer
#: donnerait un autre decor, et la coupe ne raconterait plus rien.
CORRECTIONS = [
    {
        "plan": "p02b",
        "graine_ref": P.GRAINES["ref01"],
        "reference": (
            "a completely empty night sky above a quiet Parisian street, no "
            "Moon anywhere, no bright light source in the sky at all, much "
            "darker than a moonlit night, only faint stars. The street is "
            "completely deserted, no pedestrians and no vehicles at all. "
            "Haussmann stone apartment buildings on both sides, warm sodium "
            "street lamps, wet cobblestone road reflecting the lamps, empty "
            "clean pavements, zinc rooftops. The rooftops have lost their "
            "pale illumination and the street is lit only by its own lamps. "
            "Full-frame camera, 35 mm lens, long exposure, natural night "
            "colours"),
        "consigne": (
            "Continue from the reference image. The camera drifts very "
            "slowly downward and forward along the deserted street. The sky "
            "above stays completely empty and dark for the whole shot, with "
            "no bright light source appearing at any moment. One single "
            "person stands motionless on the pavement, seen from behind, "
            "head tilted up toward the empty sky. That person does not walk "
            "and does not turn."),
    },
    {
        "plan": "p04b",
        "graine_ref": P.GRAINES["ref04"],
        "reference": (
            "aerial night photograph of a European Atlantic coastline just "
            "before dawn, a vast dark ocean stretching to the horizon, the "
            "sea surface almost flat and glassy, only very low gentle "
            "ripples reaching the shore, no breaking waves, no white foam, "
            "no surf. Dark granite rocks, two or three small distant lights "
            "on the coast, physically accurate water reflections, low "
            "atmospheric mist, deep blue hour colours, aerial documentary "
            "photography"),
        "consigne": (
            "Continue from the reference image. The camera rises slowly and "
            "steadily above the coastline, revealing more of the open "
            "ocean. The sea surface stays almost flat and glassy for the "
            "whole shot, with only very low gentle ripples and no breaking "
            "waves, no white foam and no surf at any moment. The coastline "
            "and the rocks are completely fixed."),
    },
]

#: Ce que le negatif refuse en plus, par correction : les termes memes que
#: le relecteur a cites en rejetant.
NEGATIFS = {
    "p02b": "moon, full moon, crescent moon, bright light in the sky, "
            "moonlight, glowing orb, lunar disc, ",
    "p04b": "breaking waves, whitewater, surf, sea foam, rough sea, "
            "turbulent water, storm, large swell, crashing waves, ",
}


def _appel(chemin: str, corps: dict | None = None, *,
           minutes: float = 5.0) -> dict:
    import urllib.request

    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    r = urllib.request.Request(API + chemin, data=donnees,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=minutes * 60) as rep:
        return json.loads(rep.read().decode("utf-8"))


def _dire(*mots: Any) -> None:
    print(time.strftime("[%H:%M:%S]"), *mots, flush=True)


def _rendu(identifiant: str) -> str | None:
    import glob

    for motif in (f"{identifiant}_*.mp4", f"{identifiant}_*.png"):
        t = sorted(glob.glob(os.path.join(SORTIE, motif)))
        if t:
            return t[-1]
    return None


def _attendre_libre(minutes_max: float = 180.0) -> bool:
    """Ne pas bousculer la file en cours : elle detient la carte."""
    limite = time.time() + minutes_max * 60
    annonce = False
    while time.time() < limite:
        if not _appel("/studio/night").get("en_cours"):
            return True
        if not annonce:
            _dire("une file tourne encore — on attend qu'elle rende la carte")
            annonce = True
        time.sleep(90)
    return False


def _archiver_le_journal(nom: str) -> None:
    """Garder les verdicts avant qu'une nouvelle file ne les ecrase.

    `rapport.json` est reecrit a chaque file. Les verdicts sont la seule
    trace de ce que le relecteur a vu, et le bilan du matin en depend.
    """
    import shutil

    source = os.path.join(r"E:\YouTube\Generations", "nuit", "rapport.json")
    if not os.path.isfile(source):
        return
    cible = os.path.join(SORTIE, f"journal_{nom}.json")
    shutil.copyfile(source, cible)
    _dire(f"journal archive : {os.path.basename(cible)}")


def corriger(c: dict) -> bool:
    nom = c["plan"]
    negatif = NEGATIFS.get(nom, "") + P.NEGATIF

    ref = {
        "identifiant": f"ref_{nom}",
        "gabarit": "image_sdxl",
        "consigne": f"{c['reference']}, {P.STYLE}",
        "parametres": {"largeur": P.REF_L, "hauteur": P.REF_H,
                       "graine": c["graine_ref"], "negatif": negatif,
                       "prefixe": f"lune_v4/ref_{nom}"},
    }
    r = _appel("/studio/night", {"plans": [ref], "minutes_par_plan": 10.0})
    if not r.get("success"):
        _dire(f"{nom} : la reference n'a pas demarre — {r}")
        return False
    if not _attendre_libre(minutes_max=20.0):
        return False

    image = _rendu(f"ref_{nom}")
    if not image:
        _dire(f"{nom} : la reference n'a rien produit")
        return False
    _dire(f"{nom} : reference {os.path.basename(image)}")

    depart = _appel("/studio/start-frame",
                    {"source": image, "nom": f"depart_{nom}_v5"})
    if not depart.get("success"):
        _dire(f"{nom} : depart impossible — {depart.get('error')}")
        return False

    plan = {
        "identifiant": nom,
        "gabarit": "plan_video",
        "consigne": f"{c['consigne']} {P.CONTINUITE}, {P.STYLE}",
        "parametres": {"format_": P.FORMAT_VIDEO, "images": P.IMAGES_4S,
                       "graine": P.GRAINES[nom], "negatif": negatif,
                       "avec_son": False,
                       # `v5` en suffixe : le fichier rejete reste sur le
                       # disque comme trace, et celui-ci le supplante au
                       # tri alphabetique.
                       "prefixe": f"lune_v4/{nom}_v5",
                       "image_depart": depart["nom"]},
    }
    r = _appel("/studio/night", {"plans": [plan], "minutes_par_plan": 40.0})
    if not r.get("success"):
        _dire(f"{nom} : le plan n'a pas demarre — {r}")
        return False
    _dire(f"{nom} : relance sur une reference qui montre deja l'etat vise")
    if not _attendre_libre(minutes_max=50.0):
        return False

    _archiver_le_journal(f"{nom}_v5")
    etat = _appel("/studio/night").get("rapport") or {}
    for p in etat.get("plans", []):
        _dire(f"  {p['identifiant']} : {p['etat']} "
              f"({p.get('duree_s', 0):.0f}s, confiance {p.get('confiance', 0)})")
        for d in (p.get("defauts") or []):
            _dire(f"      defaut : {d[:120]}")
    return True


def main() -> int:
    if not _attendre_libre():
        _dire("la carte n'a jamais ete rendue")
        return 1
    _archiver_le_journal("production")

    for c in CORRECTIONS:
        _dire(f"=== {c['plan']} ===")
        corriger(c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
