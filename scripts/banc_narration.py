"""Quels reglages font taire les defauts de la voix clonee (HOS-212).

## Ce qu'on cherche

Deux defauts entendus sur la premiere narration clonee, absents de la
precedente : « cette nuit » repete dans la premiere replique, et un « ok »
ajoute a la toute fin. Une troisieme, trouvee par la transcription :
« les marais » a la place de « les marees » — la voix temoin, elle, dit
bien « marees ».

Les reglages en place — `exaggeration 0.3`, `cfg_weight 0.3` — ont ete
mesures en HOS-195 sur une **autre** reference. Les reprendre pour une
voix differente, c'est exactement la supposition que ce depot refuse.

## Les deux leviers essayes

`cfg_weight` gouverne l'adherence au texte. Bas, le modele derive : il
boucle sur un groupe de mots ou continue apres la fin. C'est le suspect
principal des deux defauts.

La **fin de la reference** est le second. Celle qui est en place s'arrete
en pleine parole — mesure a -24,1 dB sur la derniere demi-seconde. Rien
n'y signale qu'un enonce se termine, ce qui peut expliquer un modele qui
continue apres le texte. La variante « close » est coupee sur un silence
reel, avec un fondu et 350 ms de blanc.

## Ce que le banc mesure, et ce qu'il ne mesure pas

Il transcrit et compare. Il attrape donc les repetitions et les ajouts,
qui sont des defauts de structure. Il n'attrape pas le timbre, la
respiration ni le naturel — et il confond un mot mal prononce avec un mot
mal entendu, ce que seule la voix temoin permet de departager.

Deux repliques seulement, celles qui portent les defauts : le banc doit
coûter des minutes, pas une heure, sinon on ne le relance pas.
"""

from __future__ import annotations

import os
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
sys.path.insert(0, os.path.dirname(ICI))

import production_lune as P  # noqa: E402
from verifier_narration import verifier  # noqa: E402

from backend.studio.arbitrage import carte_reservee  # noqa: E402
from backend.studio.narration import synthetiser  # noqa: E402

DOSSIER = r"E:\YouTube\Generations\lune\banc_voix"

REFERENCES = {
    "brute": r"C:\AI\Models\Voices\narrateur\reference.wav",
    "close": r"C:\AI\Models\Voices\narrateur\reference_close.wav",
}

#: Les repliques qui portent les defauts : n1 la repetition, n7 le « ok »,
#: n5 le mot change. Les autres ne diraient rien de plus et couteraient du
#: temps de carte.
EPREUVES = [(i, t) for i, t in P.NARRATION if i in ("n1", "n5", "n7")]


def essai(nom_ref: str, reference: str, exageration: float,
          cfg: float) -> dict:
    dossier = os.path.join(DOSSIER, f"{nom_ref}_e{exageration}_c{cfg}")
    t0 = time.time()
    n = synthetiser(EPREUVES, dossier, reference=reference,
                    reglages={"langue": "fr", "exaggeration": exageration,
                              "cfg_weight": cfg},
                    reserver=carte_reservee, minutes=20.0)
    if n.erreur:
        return {"reference": nom_ref, "exageration": exageration, "cfg": cfg,
                "erreur": n.erreur}

    defauts: list[str] = []
    for identifiant, texte in EPREUVES:
        chemin = os.path.join(dossier, f"{identifiant}.wav")
        if not os.path.isfile(chemin):
            defauts.append(f"{identifiant}:absent")
            continue
        v = verifier(chemin, texte)
        if v["repetitions"]:
            defauts.append(f"{identifiant}:repete{v['repetitions']}")
        if v["queue"]:
            defauts.append(f"{identifiant}:ajoute«{v['queue']}»")
        if not v["conforme"] and not v["repetitions"] and not v["queue"]:
            defauts.append(f"{identifiant}:ecart{v['ajoute']}")

    return {"reference": nom_ref, "exageration": exageration, "cfg": cfg,
            "defauts": defauts, "secondes": round(time.time() - t0, 1),
            "duree_parole_s": round(sum(s.duree_s for s in n.segments), 2)}


def main() -> int:
    grille = [(r, 0.3, c) for r in REFERENCES for c in (0.3, 0.5, 0.7)]
    print(f"{len(grille)} configurations x {len(EPREUVES)} repliques\n")

    resultats = []
    for nom_ref, exa, cfg in grille:
        r = essai(nom_ref, REFERENCES[nom_ref], exa, cfg)
        resultats.append(r)
        if r.get("erreur"):
            print(f"{nom_ref:<6} exa {exa} cfg {cfg} : ERREUR {r['erreur'][:70]}")
            continue
        etat = "PROPRE" if not r["defauts"] else " | ".join(r["defauts"])
        print(f"{nom_ref:<6} exa {exa} cfg {cfg} : {etat}")

    propres = [r for r in resultats if not r.get("erreur") and not r["defauts"]]
    print()
    if propres:
        print("Configurations sans defaut :")
        for r in propres:
            print(f"  reference {r['reference']}, exaggeration "
                  f"{r['exageration']}, cfg_weight {r['cfg']}  "
                  f"({r['duree_parole_s']} s de parole)")
    else:
        print("Aucune configuration propre — les defauts ne viennent pas "
              "de ces deux leviers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
