"""Reassembler la video apres correction de plans (HOS-212).

La production a produit une premiere coupe avec les plans tels qu'ils
sortaient de la nuit. Deux d'entre eux ont ete refaits ensuite, parce que
le relecteur les avait rejetes. Ce script ne refait aucun rendu : il
reprend les fichiers presents et remonte.

## Comment il choisit entre deux versions d'un plan

Un plan corrige porte le suffixe `_v5`. Les deux fichiers restent sur le
disque — celui qui a ete rejete est une trace, pas un dechet — et le tri
alphabetique met `p02b_v5_...` apres `p02b_00001_...`. Le plus recent
gagne, et le rapport dit lequel a ete pris.

## Ce qu'il refuse

Assembler une production amputee. Dix plans dont trois manquent donnent
une video plus courte, avec le code 0 — et une narration de 35,7 s posee
sur 4,0 s d'image a deja ete rendue `success: true` cette nuit. Le refus
est ici parce que c'est ici qu'on sait ce qu'on attendait.
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
NARRATION = r"E:\YouTube\Generations\lune\narration_v3.wav"

#: Au-dela, l'ecart entre la voix et l'image n'est plus un decalage a
#: rapporter : c'est la preuve que le montage n'est pas celui qu'on croit.
ECART_VOIX_MAX_S = 6.0


def _appel(chemin: str, corps: dict | None = None, *,
           minutes: float = 45.0) -> dict:
    import urllib.request

    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    r = urllib.request.Request(API + chemin, data=donnees,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=minutes * 60) as rep:
        return json.loads(rep.read().decode("utf-8"))


def _dire(*mots: Any) -> None:
    print(time.strftime("[%H:%M:%S]"), *mots, flush=True)


def _clip(etape: dict) -> str | None:
    nom = etape["plan"]
    if etape["source"] == "anime":
        cible = os.path.join(SORTIE, f"{nom}_anime.mp4")
        return cible if os.path.isfile(cible) else None
    trouves = sorted(glob.glob(os.path.join(SORTIE, f"{nom}_*.mp4")))
    # Ecarter les clips animes, qui portent le meme prefixe qu'un plan
    # video homonyme n'aurait pas.
    trouves = [t for t in trouves if not t.endswith("_anime.mp4")]
    return trouves[-1] if trouves else None


def main() -> int:
    ordre: list[str] = []
    choix: dict[str, str] = {}
    absents: list[str] = []

    for etape in P.MONTAGE:
        f = _clip(etape)
        if not f:
            absents.append(etape["plan"])
            continue
        ordre.append(f)
        choix[etape["plan"]] = os.path.basename(f)

    for nom, f in choix.items():
        marque = "  (version corrigee)" if "_v5_" in f else ""
        _dire(f"  {nom:<6} -> {f}{marque}")

    if absents:
        _dire(f"MONTAGE REFUSE — plan(s) manquant(s) : {absents}")
        return 1

    m = _appel("/studio/assemble", {
        "plans": ordre,
        "sortie": os.path.join(SORTIE, "lune_v1.mp4"),
        **({"narration": NARRATION} if os.path.isfile(NARRATION) else {}),
        **({"srt": os.path.join(SORTIE, "sous_titres.srt")}
           if os.path.isfile(os.path.join(SORTIE, "sous_titres.srt")) else {}),
        "echelle": [1080, 1920],
    })

    ecart = abs(float(m.get("ecart_voix_s") or 0))
    if m.get("success") and ecart > ECART_VOIX_MAX_S:
        m["success"] = False
        m["error"] = (f"la voix et l'image different de {ecart:.1f} s — "
                      "ce n'est plus un decalage mais un montage qui n'est "
                      "pas celui qu'on croit")
        _dire(f"MONTAGE REFUSE — {m['error']}")

    _dire("montage : " + json.dumps(m, ensure_ascii=False)[:400])
    with open(os.path.join(SORTIE, "montage_final.json"), "w",
              encoding="utf-8") as f:
        json.dump({"choix": choix, "montage": m}, f, indent=1,
                  ensure_ascii=False)
    return 0 if m.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
