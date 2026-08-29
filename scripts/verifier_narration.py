"""Ce que la voix a REELLEMENT dit, compare a ce qu'on lui a demande.

## Pourquoi cette mesure existe

Chatterbox rend un WAV valide, d'une duree plausible, quoi qu'il ait
prononce. Une replique ou il repete un morceau de phrase, ou bien ou il
ajoute un mot apres la fin du texte, ne se distingue en rien d'une bonne
replique : meme format, meme duree approximative, aucune erreur.

C'est exactement la forme de defaut que ce depot paie le plus cher — un
`success: True` au-dessus de quelque chose de faux. La narration etait
jusqu'ici jugee sur sa duree et son existence, jamais sur son contenu.

Deux defauts signales a l'oreille sur une narration clonee, absents de la
precedente : « cette nuit » prononce deux fois dans la premiere replique,
et un « ok » ajoute a la toute fin. Aucun des deux n'aurait pu etre vu
autrement qu'en ecoutant — jusqu'a maintenant.

## L'instrument

`faster-whisper`, deja installe et deja utilise pour minuter les
sous-titres. Il tourne sur processeur : il ne dispute donc pas la carte a
un rendu en cours, et cette verification reste possible pendant une nuit.

## Ce que la comparaison vaut

Une transcription n'est pas une verite : elle se trompe sur les noms
propres, la ponctuation et parfois un mot court. On ne compare donc pas
caractere pour caractere — on cherche **ce qui a ete ajoute** et **ce qui
a ete repete**, les deux defauts qui comptent ici. Un ecart isole sur un
mot est rapporte sans etre appele une faute.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from difflib import SequenceMatcher


def _mots(texte: str) -> list[str]:
    """Les mots nus : sans accents, sans ponctuation, en minuscules.

    La transcription ne restitue pas la ponctuation de l'original et
    accentue differemment ; comparer sans ca produirait des ecarts qui ne
    veulent rien dire.
    """
    t = unicodedata.normalize("NFD", texte.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9']+", t)


def repetitions(mots: list[str], longueur_min: int = 2) -> list[str]:
    """Les groupes de mots repetes coup sur coup.

    « imagine que la lune disparaisse cette nuit cette nuit » rend
    « cette nuit ». On ne cherche que la repetition **immediate** : celle
    que le modele produit en bouclant, et non une reprise voulue par le
    texte.
    """
    trouves: list[str] = []
    n = len(mots)
    for taille in range(longueur_min, max(longueur_min, n // 2) + 1):
        i = 0
        while i + 2 * taille <= n:
            a = mots[i:i + taille]
            if a == mots[i + taille:i + 2 * taille]:
                trouves.append(" ".join(a))
                i += taille
            i += 1
    return trouves


def verifier(chemin: str, attendu: str, langue: str = "fr") -> dict:
    """Comparer une replique a son texte, et nommer ce qui differe."""
    from backend.studio.montage import transcrire_en_segments

    segments = transcrire_en_segments(chemin, langue=langue)
    dit = " ".join(s["texte"] for s in segments).strip()
    a, b = _mots(attendu), _mots(dit)

    ajouts: list[str] = []
    manques: list[str] = []
    for balise, i1, i2, j1, j2 in SequenceMatcher(None, a, b).get_opcodes():
        if balise in ("insert", "replace"):
            ajouts.append(" ".join(b[j1:j2]))
        if balise in ("delete", "replace"):
            manques.append(" ".join(a[i1:i2]))

    return {
        "fichier": os.path.basename(chemin),
        "attendu": attendu,
        "dit": dit,
        "ajoute": [x for x in ajouts if x],
        "manque": [x for x in manques if x],
        "repetitions": repetitions(b),
        # Ce qui vient APRES le dernier mot attendu : c'est la que se loge
        # le « ok » ajoute en fin de replique.
        "queue": " ".join(b[len(a):]) if len(b) > len(a) else "",
        "conforme": a == b,
    }


def main(argv: list[str]) -> int:
    ici = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, ici)
    # La racine du depot : sans elle, `backend` n'est pas importable quand
    # le script est lance par son chemin plutot que comme module.
    sys.path.insert(0, os.path.dirname(ici))
    import production_lune as P

    dossier = argv[1] if len(argv) > 1 else None
    if not dossier:
        print("usage : verifier_narration.py <dossier des repliques>")
        return 2

    fautives = 0
    for identifiant, texte in P.NARRATION:
        chemin = os.path.join(dossier, f"{identifiant}.wav")
        if not os.path.isfile(chemin):
            print(f"{identifiant} : absent")
            fautives += 1
            continue
        r = verifier(chemin, texte)
        marque = "ok " if r["conforme"] else "ECART"
        print(f"{identifiant} {marque}")
        if not r["conforme"]:
            fautives += 1
            print(f"    demande : {r['attendu']}")
            print(f"    dit     : {r['dit']}")
            if r["repetitions"]:
                print(f"    REPETE  : {r['repetitions']}")
            if r["queue"]:
                print(f"    AJOUT FINAL : « {r['queue']} »")
            elif r["ajoute"]:
                print(f"    ajoute  : {r['ajoute']}")
            if r["manque"]:
                print(f"    manque  : {r['manque']}")
    print()
    print(f"{len(P.NARRATION) - fautives}/{len(P.NARRATION)} répliques conformes")
    return 0 if not fautives else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
