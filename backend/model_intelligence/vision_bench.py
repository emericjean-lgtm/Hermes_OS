"""Juger la vision par des images dont on connaît la réponse (HOS-110).

Les trois premières épreuves de cet axe ne départageaient rien : tout modèle
déclarant `vision` faisait 3/3, y compris un 2,3 Md qui obtient 0 en
raisonnement et boucle jusqu'à remplir sa fenêtre. Un axe dont tout le monde
atteint le sommet ne classe personne — c'est exactement ce qui était arrivé
au code avant ses six épreuves de départage, et à l'extraction, où neuf
modèles sur dix plafonnent encore.

Elles demandaient « sait-il voir ». Celles-ci demandent de voir **et** de
faire quelque chose de ce qu'on voit : retrouver une ligne désignée par son
rang, compter une couleur parmi trois, croiser une ligne et une colonne,
comparer des hauteurs, compter malgré des chevauchements, ordonner selon une
relation spatiale.

**Les images sont dessinées ici**, donc la réponse est connue au pixel près
et aucun jugement n'intervient. Le contenu dépend d'une graine : à graine
fixe une campagne rejouée compare des modèles et non des tirages, et à
graine libre aucun modèle ne peut avoir mémorisé l'épreuve.

Deux pièges trouvés en regardant les images plutôt qu'en relisant le code
qui les dessine, et corrigés avant qu'un seul modèle ne les voie : un tirage
libre pouvait poser deux cercles à dix pixels l'un de l'autre, rendant leur
ordre indécidable pour un humain aussi ; et le juge acceptait une référence
apparaissant n'importe où, ce qui donnait 100 % à un modèle qui se contente
de transcrire les dix lignes sans avoir lu la question.
"""
from __future__ import annotations

import random
import re
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

#: Les trois couleurs des épreuves de comptage et de relation. Choisies
#: franches : distinguer deux nuances proches mesurerait l'affichage.
COULEURS = {"rouge": (220, 40, 40), "bleu": (40, 80, 220), "vert": (30, 160, 60)}

#: Écart horizontal minimal entre deux cercles de 80 px dans `relation`.
#: Sans lui, un tirage pouvait les superposer et rendre l'ordre indécidable.
ECART_MINIMAL = 130


def _police(taille: int):
    for nom in ("arial.ttf", "segoeui.ttf", "calibri.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nom, taille)
        except OSError:
            continue
    return ImageFont.load_default()


def _chiffres(r: random.Random, n: int) -> str:
    return "".join(r.choice("0123456789") for _ in range(n))


# ── les six épreuves ─────────────────────────────────────────────────────

def ocr_dense(r: random.Random):
    """Lire la référence d'un rang donné, parmi dix presque identiques."""
    lignes = [f"REF-{_chiffres(r, 6)}" for _ in range(10)]
    cible = r.randrange(10)
    img = Image.new("RGB", (760, 380), "white")
    d, f = ImageDraw.Draw(img), _police(26)
    for i, ligne in enumerate(lignes):
        d.text((40, 20 + i * 34), f"{i + 1:>2}.  {ligne}", fill="black", font=f)
    return (img,
            f"Ce document contient dix references numerotees. Quelle est la "
            f"reference de la ligne {cible + 1} ? Reponds uniquement par la "
            f"reference.",
            lignes[cible])


def comptage_couleur(r: random.Random):
    """Compter une couleur parmi trois — les distracteurs sont le sujet."""
    cible = r.choice(list(COULEURS))
    n_cible = r.randint(4, 9)
    autres = {c: r.randint(3, 8) for c in COULEURS if c != cible}
    objets = [cible] * n_cible + [c for c, n in autres.items() for _ in range(n)]
    r.shuffle(objets)
    img = Image.new("RGB", (700, 500), "white")
    d = ImageDraw.Draw(img)
    for i, couleur in enumerate(objets):
        x, y = 40 + (i % 7) * 92, 40 + (i // 7) * 92
        d.ellipse([x, y, x + 62, y + 62], fill=COULEURS[couleur], outline="black")
    return (img,
            f"Combien de cercles {cible}s y a-t-il sur cette image ? Reponds "
            f"uniquement par le nombre.",
            str(n_cible))


def tableau(r: random.Random):
    """Croiser une ligne et une colonne — lire ne suffit pas, il faut situer."""
    colonnes = ["Janvier", "Fevrier", "Mars", "Avril"]
    lignes = ["Nord", "Sud", "Est", "Ouest"]
    vals = [[r.randint(100, 999) for _ in colonnes] for _ in lignes]
    li, co = r.randrange(len(lignes)), r.randrange(len(colonnes))
    img = Image.new("RGB", (700, 280), "white")
    d, f = ImageDraw.Draw(img), _police(24)
    for j, c in enumerate(colonnes):
        d.text((190 + j * 125, 30), c, fill="black", font=f)
    for i, l in enumerate(lignes):
        d.text((40, 80 + i * 45), l, fill="black", font=f)
        for j in range(len(colonnes)):
            d.text((200 + j * 125, 80 + i * 45), str(vals[i][j]), fill="black", font=f)
    d.line([(30, 65), (670, 65)], fill="black", width=2)
    d.line([(175, 20), (175, 260)], fill="black", width=2)
    return (img,
            f"Dans ce tableau, quelle valeur se trouve a la ligne "
            f"« {lignes[li]} » et a la colonne « {colonnes[co]} » ? Reponds "
            f"uniquement par le nombre.",
            str(vals[li][co]))


def histogramme(r: random.Random):
    """Comparer des hauteurs. Valeurs distinctes : un ex aequo rendrait la
    question ambiguë, et une question ambiguë note en échec une réponse
    défendable."""
    noms = ["A", "B", "C", "D", "E"]
    vals = r.sample(range(20, 96), len(noms))
    gagnant = noms[vals.index(max(vals))]
    img = Image.new("RGB", (640, 460), "white")
    d, f = ImageDraw.Draw(img), _police(22)
    base = 400
    for i, (n, v) in enumerate(zip(noms, vals)):
        x = 70 + i * 105
        d.rectangle([x, base - v * 3.4, x + 64, base], fill=(60, 110, 200))
        d.text((x + 22, base + 12), n, fill="black", font=f)
    d.line([(50, base), (610, base)], fill="black", width=3)
    for y in range(0, 100, 20):
        d.text((10, base - y * 3.4 - 10), str(y), fill="black", font=_police(18))
        d.line([(48, base - y * 3.4), (58, base - y * 3.4)], fill="black", width=2)
    return (img,
            "Quelle barre est la plus haute sur ce graphique ? Reponds "
            "uniquement par sa lettre.",
            gagnant)


def occlusion(r: random.Random):
    """Compter des formes dont certaines se chevauchent.

    La verite-terrain est `len(places)` et non le tirage voulu : la boucle
    de placement peut renoncer, et compter ce qu'on a demande plutot que ce
    qu'on a dessine noterait en echec un modele qui compte juste.
    """
    n = r.randint(5, 9)
    img = Image.new("RGB", (620, 440), "white")
    d = ImageDraw.Draw(img)
    places: list[tuple[int, int]] = []
    for _ in range(n):
        for _essai in range(80):
            x, y = r.randint(30, 500), r.randint(30, 330)
            if all(abs(x - px) > 46 or abs(y - py) > 46 for px, py in places):
                places.append((x, y))
                break
    for x, y in places:
        d.rectangle([x, y, x + 90, y + 90], fill=(250, 180, 60),
                    outline="black", width=3)
    return (img,
            "Combien de carres oranges y a-t-il, chevauchements compris ? "
            "Reponds uniquement par le nombre.",
            str(len(places)))


def relation(r: random.Random):
    """Ordonner trois objets selon une relation spatiale."""
    noms = list(COULEURS)
    r.shuffle(noms)
    while True:
        xs = sorted(r.sample(range(40, 520), 3))
        if xs[1] - xs[0] >= ECART_MINIMAL and xs[2] - xs[1] >= ECART_MINIMAL:
            break
    img = Image.new("RGB", (700, 300), "white")
    d = ImageDraw.Draw(img)
    for nom, x in zip(noms, xs):
        y = r.randint(60, 170)
        d.ellipse([x, y, x + 80, y + 80], fill=COULEURS[nom],
                  outline="black", width=3)
    return (img,
            "Nomme les trois cercles de gauche a droite, separes par des "
            "virgules, en utilisant uniquement les mots rouge, bleu et vert.",
            ",".join(noms))


EPREUVES: tuple[tuple[str, Callable], ...] = (
    ("ocr_dense", ocr_dense),
    ("comptage_couleur", comptage_couleur),
    ("tableau", tableau),
    ("histogramme", histogramme),
    ("occlusion", occlusion),
    ("relation", relation),
)


def planche(graine: int) -> list[tuple[str, str, str]]:
    """Les six épreuves d'une campagne, tirées une seule fois.

    Régénérer par modèle donnerait à l'un huit cercles à compter et à
    l'autre quatre : l'écart mesuré serait celui des tirages. Même principe
    que le foin du long contexte, identique pour tous.
    """
    r = random.Random(graine)
    return [(nom,) + fabrique(r)[1:] for nom, fabrique in EPREUVES]  # type: ignore[misc]


# ── le juge ──────────────────────────────────────────────────────────────

def _lignes(reponse: str) -> list[str]:
    return [l for l in (reponse or "").lower().splitlines() if l.strip()]


def juge(nom: str, reponse: str, attendu: str) -> bool:
    """Correspondance exacte sur une réponse connue — aucun jugement.

    On lit la **dernière ligne qui porte une réponse**, comme le juge de
    raisonnement : un modèle qui réfléchit à voix haute écrit tous les
    nombres de son brouillon avant le bon, et accepter n'importe lequel
    validerait une mauvaise réponse.
    """
    lignes = _lignes(reponse)
    if not lignes:
        return False

    if nom == "relation":
        vise = attendu.split(",")
        for ligne in reversed(lignes):
            vus, ordre = set(), []
            for mot in ligne.replace(",", " ").split():
                mot = mot.strip(".:;")
                if mot in vise and mot not in vus:
                    vus.add(mot)
                    ordre.append(mot)
            if len(ordre) == len(vise):
                return ordre == vise
        return False

    if nom == "histogramme":
        for ligne in reversed(lignes):
            lettres = [c for c in ligne.upper() if c in "ABCDE"]
            if lettres:
                return lettres[-1] == attendu
        return False

    if nom == "ocr_dense":
        # Il faut avoir RÉPONDU, pas transcrit. Un modèle qui recopie les dix
        # lignes contient forcément la bonne : accepter « la référence
        # apparaît quelque part » lui donnerait 100 % sans qu'il ait lu la
        # question. On exige une ligne ne portant qu'une seule référence.
        cible = attendu.replace("-", "").replace("REF", "")
        for ligne in reversed(lignes):
            refs = re.findall(r"\d{6}", ligne.replace("-", "").replace(" ", ""))
            if len(refs) == 1:
                return refs[0] == cible
            if len(refs) > 1:
                return False
        return False

    # comptage_couleur, tableau, occlusion : un nombre exact.
    for ligne in reversed(lignes):
        nombres = re.findall(r"\d+", ligne.replace(" ", ""))
        if nombres:
            return nombres[-1] == attendu
    return False
