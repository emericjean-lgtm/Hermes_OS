"""Des sous-titres qui disent le texte, pas ce qu'on a cru entendre.

## Le defaut que ca corrige

Les sous-titres etaient produits en **transcrivant** la narration. Or on
connait deja le texte : c'est nous qui l'avons donne au synthetiseur. La
transcription n'apportait donc que ses propres erreurs — et elles
finissent incrustees dans l'image.

Constate sur le premier montage : « La premiere chose que tu
**remarqueras** serait le ciel », la ou le texte dit « remarquerais ».
Un spectateur lit la faute ; le script ne l'avait pas.

## Ce qu'il faut vraiment de la transcription : rien

Chaque replique a ete synthetisee dans son propre fichier, et les
silences entre elles sont poses par le montage. Les bornes se calculent
donc exactement : duree lue sur chaque WAV, plus les pauses connues. Pas
d'alignement, pas d'estimation, pas de modele.

C'est plus juste **et** plus simple que ce qui existait.
"""

from __future__ import annotations

import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
sys.path.insert(0, os.path.dirname(ICI))

import lancer_production_lune as L  # noqa: E402
import production_lune as P  # noqa: E402

from backend.studio.montage import ecrire_srt  # noqa: E402
from backend.studio.relecteur import duree_s  # noqa: E402

VOIX = r"E:\YouTube\Generations\lune\voix_narrateur_v2"
SORTIE = r"E:\YouTube\Generations\lune_v4"

#: Un sous-titre qui apparait pile sur la premiere syllabe se lit mal. Un
#: dixieme de seconde d'avance, et il est deja la quand la voix arrive.
AVANCE_S = 0.10

#: Au-dela, le carton depasse les deux lignes que le cahier des charges
#: demande, et il couvre l'image au lieu de la servir. Mesure sur la
#: largeur reelle : 1080 px en police epaisse tiennent une soixantaine de
#: caracteres par ligne.
CARACTERES_MAX = 62


def _decouper(texte: str) -> list[str]:
    """Couper une replique en cartons, sur les fins de phrase.

    Une replique de cent caracteres tient sur trois ou quatre lignes a
    l'ecran : elle masque l'image au lieu de l'accompagner. On coupe donc
    aux points, qui sont aussi les respirations naturelles de la lecture.
    """
    import re

    if len(texte) <= CARACTERES_MAX:
        return [texte]
    phrases = [p.strip() for p in re.split(r"(?<=[.!?])\s+", texte) if p.strip()]
    if len(phrases) < 2:
        return [texte]

    cartons: list[str] = []
    courant = ""
    for phrase in phrases:
        candidat = (courant + " " + phrase).strip()
        if courant and len(candidat) > CARACTERES_MAX:
            cartons.append(courant)
            courant = phrase
        else:
            courant = candidat
    if courant:
        cartons.append(courant)
    return cartons


def segments() -> list[dict]:
    """Les bornes de chaque replique, calculees et non estimees."""
    pauses = list(L.PAUSES_S)
    horloge = 0.0
    faits: list[dict] = []
    for i, (identifiant, texte) in enumerate(P.NARRATION):
        chemin = os.path.join(VOIX, f"{identifiant}.wav")
        if not os.path.isfile(chemin):
            raise SystemExit(f"replique absente : {chemin}")
        d = duree_s(chemin)
        if not d:
            raise SystemExit(f"duree illisible : {chemin}")

        # Le temps se repartit au prorata des caracteres. Ce n'est pas un
        # alignement — on ne sait pas ou tombe chaque mot — mais sur des
        # phrases lues au meme debit, l'ecart se compte en dixiemes de
        # seconde, et un carton un peu large vaut mieux qu'un carton
        # illisible.
        cartons = _decouper(texte)
        total = sum(len(c) for c in cartons) or 1
        debut_replique = horloge
        for carton in cartons:
            part = d * len(carton) / total
            # L'avance ne doit jamais remonter avant la fin du carton
            # precedent : deux sous-titres affiches ensemble, meme un
            # dixieme de seconde, se voient a l'ecran.
            debut = max(0.0, debut_replique - AVANCE_S)
            if faits and debut < faits[-1]["fin"]:
                debut = faits[-1]["fin"]
            faits.append({"debut": debut,
                          "fin": debut_replique + part,
                          "texte": carton})
            debut_replique += part
        horloge += d + (pauses[i] if i < len(pauses) else 0.0)
    return faits


def main() -> int:
    faits = segments()
    cible = os.path.join(SORTIE, "sous_titres.srt")
    n = ecrire_srt(faits, cible)
    print(f"{n} sous-titres ecrits — {faits[-1]['fin']:.2f} s de narration")
    for f in faits:
        print(f"  {f['debut']:>6.2f} → {f['fin']:>6.2f}  {f['texte'][:58]}")
    return 0 if n == len(faits) else 1


if __name__ == "__main__":
    raise SystemExit(main())
