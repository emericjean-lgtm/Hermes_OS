"""Refaire p02b en ne changeant QUE le ciel (HOS-212).

## Ce que la tentative precedente a appris

L'idee etait juste : pour que la coupe raconte une disparition, les deux
plans doivent montrer **la meme rue**, l'un avec la Lune, l'autre sans. A
graine egale, SDXL rend une image tres proche — a condition que la
consigne, elle aussi, soit tres proche.

Elle ne l'etait pas. J'ai reecrit toute la consigne autour du ciel, et
SDXL a rendu **une autre rue** : plus large, d'autres immeubles, et un
ciel beige d'agglomeration au lieu du bleu nuit demande. La coupe aurait
raconte un changement de lieu, pas une disparition.

SDXL compose d'apres l'ensemble du texte, pas d'apres la graine seule.
Changer la moitie des mots change l'image autant que changer la graine.

## Ce que fait cette version

Elle part de la consigne **exacte** de `ref01` et n'y remplace que deux
fragments : la clause qui decrit la Lune, et celle qui decrit sa lumiere
sur les toits. Tout le reste — la rue, les immeubles, les lampadaires,
les paves, l'objectif, l'exposition — est identique au mot pres.

La substitution est verifiee avant le rendu : si l'un des deux fragments
n'est pas retrouve, le script s'arrete plutot que de lancer vingt-trois
minutes sur une consigne qui aurait silencieusement garde la Lune.
"""

from __future__ import annotations

import glob
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

#: Les deux seuls fragments qui changent. Le reste de la consigne de
#: `ref01` est repris tel quel.
SUBSTITUTIONS = [
    ("a large perfectly round fully lit full Moon, a complete bright white "
     "disc high in a clear dark blue night sky, above a quiet Parisian "
     "street.",
     "a completely empty clear dark blue night sky with no Moon at all and "
     "no bright light source anywhere in it, only faint distant stars, "
     "above a quiet Parisian street."),
    ("Cold moonlight on the roofs, still and silent atmosphere.",
     "No moonlight anywhere, the roofs are dark, still and silent "
     "atmosphere."),
]

NEGATIF = ("moon, full moon, crescent moon, moonlight, bright light in the "
           "sky, glowing orb, lunar disc, overcast sky, orange sky glow, "
           "brown sky, daylight, ") + P.NEGATIF

#: La consigne du plan, reecrite sur ce que le relecteur a reproche a la
#: tentative precedente — et deux de ses trois reproches visaient ma
#: consigne, pas le rendu.
#:
#: **Elle se contredisait.** « no bright light source appearing at any
#: moment » interdisait toute lumiere vive, alors que la reference exige
#: des lampadaires allumes. Le relecteur avait raison : « street lamps
#: are illuminated ». L'interdiction porte desormais sur le **ciel**,
#: explicitement.
#:
#: **Elle demandait un mouvement que le modele ne fait pas.** « camera is
#: static », a-t-il releve. A huit etapes, LTX bouge peu. Decrire un
#: travelling qu'il ne produira pas transforme un plan correct en plan
#: rejete — on decrit donc ce qu'il fait : une camera presque immobile.
#:
#: **Le personnage est retire.** La tete levee, vue de dos, est une pose
#: que ni SDXL ni LTX ne rendent — releve trois fois cette nuit. La
#: reaction humaine est deja portee par le plan 06 ; l'exiger ici ajoute
#: un motif de rejet sans rien apporter.
CONSIGNE_PLAN = (
    "Continue from the reference image. The camera holds almost still on "
    "the deserted street, with only a barely perceptible forward drift. "
    "The sky above the rooftops stays completely empty and dark for the "
    "whole shot: no Moon, no bright light and no glow anywhere in the sky "
    "at any moment. The street lamps below keep burning normally and light "
    "the pavement as before. The only motion is the faint haze and the "
    "reflections shifting on the wet cobblestones.")


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


def _attendre_libre(minutes_max: float = 180.0) -> bool:
    limite = time.time() + minutes_max * 60
    annonce = False
    while time.time() < limite:
        if not _appel("/studio/night").get("en_cours"):
            return True
        if not annonce:
            _dire("une file tourne encore — on attend la carte")
            annonce = True
        time.sleep(90)
    return False


def consigne_sans_lune() -> tuple[str, float]:
    """La consigne de ref01, moins la Lune. Rend aussi la part conservee."""
    origine = next(p for p in P.PLANS if p["identifiant"] == "ref01")["consigne"]
    texte = origine
    for avant, apres in SUBSTITUTIONS:
        if avant not in texte:
            raise SystemExit(
                f"fragment introuvable dans la consigne de ref01 :\n  {avant[:70]}…\n"
                "La consigne a change — refuser plutot que de lancer un rendu "
                "qui garderait la Lune sans que rien ne le dise.")
        texte = texte.replace(avant, apres, 1)

    mots_a, mots_b = origine.split(), texte.split()
    communs = sum(1 for m in mots_b if m in mots_a)
    return texte, communs / max(1, len(mots_b))


def main() -> int:
    consigne, part = consigne_sans_lune()
    _dire(f"consigne construite — {part * 100:.0f} % des mots identiques "
          "a celle de ref01")
    if part < 0.70:
        _dire("trop peu de mots communs : SDXL rendrait une autre rue")
        return 1

    if not _attendre_libre():
        return 1

    ref = {
        "identifiant": "ref_p02b_min",
        "gabarit": "image_sdxl",
        "consigne": consigne,
        "parametres": {"largeur": P.REF_L, "hauteur": P.REF_H,
                       "graine": P.GRAINES["ref01"], "negatif": NEGATIF,
                       "prefixe": "lune_v4/ref_p02b_min"},
    }
    if not _appel("/studio/night",
                  {"plans": [ref], "minutes_par_plan": 10.0}).get("success"):
        _dire("la reference n'a pas demarre")
        return 1
    if not _attendre_libre(minutes_max=20.0):
        return 1

    trouves = sorted(glob.glob(os.path.join(SORTIE, "ref_p02b_min_*.png")))
    if not trouves:
        _dire("la reference n'a rien produit")
        return 1
    _dire(f"reference : {os.path.basename(trouves[-1])}")

    depart = _appel("/studio/start-frame",
                    {"source": trouves[-1], "nom": "depart_p02b_v6"})
    if not depart.get("success"):
        _dire(f"depart impossible : {depart.get('error')}")
        return 1

    plan = {
        "identifiant": "p02b",
        "gabarit": "plan_video",
        "consigne": f"{CONSIGNE_PLAN} {P.CONTINUITE}, {P.STYLE}",
        "parametres": {"format_": P.FORMAT_VIDEO, "images": P.IMAGES_4S,
                       "graine": P.GRAINES["p02b"], "negatif": NEGATIF,
                       "avec_son": False, "prefixe": "lune_v4/p02b_v6",
                       "image_depart": depart["nom"]},
    }
    if not _appel("/studio/night",
                  {"plans": [plan], "minutes_par_plan": 40.0}).get("success"):
        _dire("le plan n'a pas demarre")
        return 1
    _dire("p02b relance sur la meme rue, sans Lune")
    if not _attendre_libre(minutes_max=50.0):
        return 1

    import shutil

    source = os.path.join(r"E:\YouTube\Generations", "nuit", "rapport.json")
    if os.path.isfile(source):
        shutil.copyfile(source, os.path.join(SORTIE, "journal_p02b_v6.json"))

    etat = _appel("/studio/night").get("rapport") or {}
    for p in etat.get("plans", []):
        _dire(f"  {p['identifiant']} : {p['etat']} "
              f"({p.get('duree_s', 0):.0f}s, confiance {p.get('confiance', 0)})")
        for d in (p.get("defauts") or []):
            _dire(f"      defaut : {d[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
