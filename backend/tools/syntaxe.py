"""Un fichier écrit compile-t-il ? (HOS-121)

Mesuré sur l'essai Skills360 : la mission a écrit `test_identity_extended.py`
avec une docstring ouverte par `\"\"\"` et fermée par `\"`. `pytest` s'est
arrêté à la collecte, code 2. Personne ne l'a su pendant **trente minutes**,
et la mission a rapporté `success: True`.

Le filet existant — `verification_run`, HOS-119 — n'a pas joué : il exige le
niveau d'autonomie `high` et la configuration livrée est `medium`. Il est
donc doublement inadapté à ce défaut-ci :

* il ne s'arme pas au niveau par défaut ;
* il ne tourne qu'à la **fin** de la mission, alors que l'erreur est
  connaissable à la seconde où le fichier est écrit.

Ce module est l'inverse : gratuit, déterministe, hors politique de sécurité
— on n'exécute rien, on analyse un texte — et immédiat. Le modèle reçoit
l'erreur du compilateur dans le tour d'outil suivant, pas trente minutes
plus tard.

## Ce qu'il ne fait pas

Il ne dit **pas** qu'un fichier est correct. Il dit qu'il *parse*. Un module
qui compile peut être faux, importer un nom inexistant ou ne rien faire de
ce qu'on lui demandait — c'est le travail de `verification_run`, et celui-ci
ne le remplace pas.

Et il ne se prononce pas sur ce qu'il ne sait pas lire. Une extension
inconnue rend `None`, jamais « valide » : « je n'ai pas vérifié » et « c'est
bon » sont deux verdicts différents, et les confondre est le défaut que ce
dépôt paie depuis le début.
"""
from __future__ import annotations

import ast
import json
from typing import Optional

#: Ce qu'on sait analyser sans rien exécuter. Volontairement court :
#: proposer un analyseur approximatif pour une syntaxe qu'on lit mal
#: produirait de faux échecs, aussi coûteux que les faux succès.
EXTENSIONS = (".py", ".json")


def verdict(chemin: str, contenu: str) -> Optional[str]:
    """L'erreur de syntaxe s'il y en a une, `None` sinon.

    `None` a deux sens — pas d'erreur, ou pas d'analyse possible — et
    l'appelant ne doit annoncer un succès dans aucun des deux cas : il doit
    seulement s'abstenir de signaler une erreur.
    """
    minuscule = chemin.lower()
    if minuscule.endswith(".py"):
        try:
            ast.parse(contenu, filename=chemin)
        except SyntaxError as erreur:
            ligne = erreur.lineno or 0
            return f"ligne {ligne} : {erreur.msg}"
        except ValueError as erreur:
            # Un octet nul dans la source, par exemple. `ast.parse` ne lève
            # pas SyntaxError dans ce cas et le laisser filer ferait passer
            # un fichier illisible pour valide.
            return str(erreur)
        return None
    if minuscule.endswith(".json"):
        try:
            json.loads(contenu)
        except json.JSONDecodeError as erreur:
            return f"ligne {erreur.lineno} : {erreur.msg}"
        return None
    return None


def message(chemin: str, contenu: str) -> str:
    """Ce qu'on ajoute au retour d'outil, ou une chaîne vide.

    Formulé pour être actionnable au tour suivant : le fichier *est* sur le
    disque — le dire autrement serait faux — mais il ne compile pas, et
    c'est la seule chose que le modèle doit faire ensuite.
    """
    erreur = verdict(chemin, contenu)
    if not erreur:
        return ""
    return (f"\nATTENTION : le fichier est bien écrit sur le disque, mais il "
            f"ne compile pas — {erreur}. Corrige-le maintenant, avant toute "
            f"autre chose : en l'état il est inutilisable et fera échouer "
            f"tout ce qui l'importe.")
