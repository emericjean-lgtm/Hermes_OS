"""Quatre épreuves de raisonnement, une réponse exacte chacune (HOS-110).

Artificial Analysis place Qwen3.6-27B à 38 d'indice d'intelligence contre 15
pour gpt-oss-20b, alors que les deux atteignent `mythique` en code. Aucun axe
existant ne touchait cette dimension : le code mesure la construction, pas la
déduction.

**Les quatre vérités-terrain ont été obtenues par force brute avant d'être
opposées au moindre modèle, et deux des quatre posées de tête étaient
fausses** — « bruno » au lieu d'amel, 475 au lieu de 479. Lancée telle
quelle, la campagne aurait noté en échec tous les modèles qui répondaient
juste, et conclu que le raisonnement est le point faible du catalogue.
L'énigme de déduction admet exactement une solution ; l'atelier se vérifie
avec une calculette.

La dernière épreuve est la plus discriminante : un énoncé dont la réponse
intuitive est fausse. Un modèle qui reconnaît un motif y tombe, un modèle
qui raisonne résiste.
"""
from __future__ import annotations

import re

#: Les quatre prénoms de l'énigme, pour distinguer une réponse d'un
#: raisonnement qui les cite tous.
PRENOMS = ("amel", "bruno", "chloe", "diego")

#: L'ordre chronologique attendu de l'épreuve temporelle.
EVENEMENTS = ("commande", "livraison", "installation", "inspection", "paiement")

EPREUVES: tuple[tuple[str, str, str], ...] = (
    ("deduction", """
Quatre collègues — Amel, Bruno, Chloe et Diego — occupent quatre bureaux
alignés numérotés 1 à 4, et chacun a un métier différent : comptable,
juriste, graphiste, développeur.

1. Le développeur est au bureau 1 ou au bureau 4.
2. Chloe est exactement deux bureaux à droite d'Amel.
3. Bruno n'est pas voisin du graphiste.
4. Le juriste occupe le bureau 3.
5. Diego est comptable.
6. Amel n'est pas développeuse.

Qui est graphiste ? Termine ta réponse par le prénom seul.
""", "amel"),

    ("arithmetique", """
Un atelier produit des pièces. Chaque lot contient 24 pièces.
Lundi il a produit 7 lots, mardi 40 % de plus que lundi (arrondi à l'entier
inférieur en nombre de lots), mercredi la moitié de mardi arrondie au
supérieur.
Sur l'ensemble des trois jours, 5 % des pièces sont rebutées, arrondi à
l'entier inférieur.
Combien de pièces conformes reste-t-il ? Termine ta réponse par le nombre
seul.
""", "479"),

    ("temporel", """
Cinq événements : la livraison, l'inspection, le paiement, la commande et
l'installation.
- L'inspection a lieu après l'installation.
- Le paiement a lieu juste après l'inspection.
- La commande précède tous les autres événements.
- L'installation a lieu après la livraison.
Termine ta réponse par l'ordre chronologique des cinq événements sur une
seule ligne, séparés par des virgules.
""", ",".join(EVENEMENTS)),

    ("piege", """
Une machine met 5 minutes pour usiner 5 pièces, chaque pièce étant usinée
par un poste distinct fonctionnant en parallèle.
L'atelier possède 100 postes identiques.
Combien de minutes faut-il pour usiner 100 pièces ? Termine ta réponse par
le nombre seul.
""", "5"),
)


def _sans_accents(texte: str) -> str:
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ô", "o")):
        texte = texte.replace(a, b)
    return texte


def juge(reponse: str, attendu: str) -> bool:
    """La réponse, pas le raisonnement.

    Un modèle qui raisonne à voix haute écrit tous les nombres de son
    brouillon avant le bon. On lit donc la *dernière ligne qui porte une
    réponse*, et sur cette ligne le *dernier* nombre — l'énoncé demande de
    terminer par le nombre seul.

    Accepter n'importe quel nombre de cette ligne serait plus tolérant et
    faux : « 100 pièces / 5 = 20 minutes » contient bien un 5 et passerait
    l'épreuve piège en donnant la mauvaise réponse. Le juge s'en tient donc
    au dernier, quitte à rejeter « 479 pièces sur 504 produites » — un échec
    de forme, visible dans le journal parce que la fin de chaque réponse y
    est conservée, préférable à une réussite fausse qui ne se voit pas.
    """
    lignes = [l for l in _sans_accents((reponse or "").lower()).splitlines()
              if l.strip()]

    if attendu.isdigit():
        for ligne in reversed(lignes):
            nombres = re.findall(r"-?\d+", ligne.replace(" ", "").replace(" ", ""))
            if nombres:
                return nombres[-1] == attendu
        return False

    if "," in attendu:
        vise = attendu.split(",")
        for ligne in reversed(lignes):
            vus, ordre = set(), []
            for mot in re.findall(r"[a-z]+", ligne):
                if mot in vise and mot not in vus:
                    vus.add(mot)
                    ordre.append(mot)
            if len(ordre) == len(vise):
                return ordre == vise
        return False

    for ligne in reversed(lignes):
        presents = {p for p in PRENOMS if p in ligne}
        if presents:
            return presents == {attendu}
    return False
