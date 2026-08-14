"""Mesurer la compétence de codage en exécutant ce que le modèle écrit (HOS-106).

Toutes les autres dimensions du banc comparent du texte. Pour le code, la
seule vérification qu'un modèle ne peut pas contourner est **l'exécution** :
on donne une signature et une docstring, il écrit le corps, on lance des
assertions. Un test qui passe est un fait ; un code qui « a l'air correct »
n'en est pas un.

**Le code produit n'est jamais exécuté dans ce processus.** Sous-processus
dédié, répertoire temporaire jetable, délai strict, sortie capturée. Un
modèle qui écrit une boucle infinie fait expirer son essai, pas la
campagne ; un modèle qui écrit `os.remove` touche un dossier temporaire.
Ce n'est pas un bac à sable de sécurité — c'est un banc d'essai local sur
du code produit par des modèles qu'on a choisis — mais l'isolation évite
les dégâts accidentels, qui sont le cas réel.

Trois niveaux, parce que le routage doit distinguer « ce 9B suffit ici »
de « ce 35B est nécessaire là » :

- **simple** : le modèle sait-il écrire du Python valide qui fait ce qu'on
  demande sur le cas nominal ;
- **moyen** : anticipe-t-il ce qu'on ne lui dit pas — liste vide, doublons,
  valeurs négatives ;
- **complexe** : raisonne-t-il sur la durée — état à maintenir entre
  appels, invariant à préserver.

Les assertions de chaque niveau incluent délibérément des cas absents de
l'énoncé. Un modèle qui ne code que ce qui est écrit réussit le simple et
échoue le moyen, et c'est exactement l'information cherchée.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: Généreux pour un modèle lent sur une machine chargée, fini pour une
#: boucle infinie. Un dépassement est compté comme un échec — un code qui
#: ne rend pas la main n'est pas un code qui marche.
EXEC_TIMEOUT_S = 60.0


@dataclass(frozen=True)
class CodeTask:
    """Un énoncé et les assertions qui le jugent."""

    level: str
    name: str
    prompt: str
    checks: str
    #: Ce que ce niveau isole, pour que le rapport dise pourquoi il compte.
    tests: str = ""


TASKS: tuple[CodeTask, ...] = (
    CodeTask(
        "simple", "compter_mots",
        "Écris une fonction Python `compter_mots(texte: str) -> dict[str, int]` "
        "qui renvoie le nombre d'occurrences de chaque mot, en ignorant la casse. "
        "Réponds uniquement par le code de la fonction.",
        """
assert compter_mots("le chat le chien") == {"le": 2, "chat": 1, "chien": 1}
assert compter_mots("Le LE le") == {"le": 3}
assert compter_mots("") == {}
""",
        tests="cas nominal, casse, chaîne vide",
    ),
    CodeTask(
        "moyen", "fusion_intervalles",
        "Écris une fonction Python `fusionner(intervalles: list[tuple[int, int]]) "
        "-> list[tuple[int, int]]` qui fusionne les intervalles qui se chevauchent "
        "et renvoie le résultat trié. Réponds uniquement par le code de la fonction.",
        """
assert fusionner([(1, 3), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]
assert fusionner([]) == []
assert fusionner([(5, 5)]) == [(5, 5)]
# Non trie a l'entree : l'enonce dit "trie" en sortie, pas en entree.
assert fusionner([(8, 10), (1, 3), (2, 6)]) == [(1, 6), (8, 10)]
# Intervalles adjacents : (1,2) et (2,3) se touchent.
assert fusionner([(1, 2), (2, 3)]) == [(1, 3)]
""",
        tests="entrée non triée, adjacence, vide, singleton — aucun n'est dans l'énoncé",
    ),
    CodeTask(
        "complexe", "banque_transactions",
        "Écris une classe Python `Compte` avec `depot(montant)`, `retrait(montant)`, "
        "`solde()` et `annuler()`. `annuler()` défait la dernière opération "
        "non encore annulée, et peut être appelée plusieurs fois de suite pour "
        "remonter l'historique. Un retrait supérieur au solde lève `ValueError` "
        "et ne compte pas comme une opération. Réponds uniquement par le code.",
        """
c = Compte()
c.depot(100); c.depot(50); c.retrait(30)
assert c.solde() == 120
c.annuler(); assert c.solde() == 150
c.annuler(); assert c.solde() == 100
c.annuler(); assert c.solde() == 0
# Un retrait refuse ne doit pas entrer dans l'historique.
d = Compte()
d.depot(10)
try:
    d.retrait(999)
except ValueError:
    pass
else:
    raise AssertionError("un retrait superieur au solde doit lever ValueError")
d.annuler()
assert d.solde() == 0, "annuler a defait le depot, donc le retrait refuse etait dans l'historique"
""",
        tests="état sur plusieurs tours, invariant après une erreur",
    ),
    CodeTask(
        "expert", "parseur_expressions",
        "Écris une fonction Python `evaluer(expr: str) -> float` qui évalue une "
        "expression arithmétique donnée sous forme de chaîne, en respectant la "
        "priorité des opérateurs et les parenthèses. Opérateurs : + - * / et "
        "l'unaire -. N'utilise ni `eval` ni `exec`. Réponds uniquement par le code.",
        """
import math
assert evaluer("2+3*4") == 14
assert evaluer("(2+3)*4") == 20
assert evaluer("-3+5") == 2
assert evaluer("2*(3+4)/7") == 2
assert math.isclose(evaluer("1/3"), 1/3)
assert evaluer("-(2+3)") == -5
assert evaluer("2*-3") == -6
assert evaluer("((1+2)*(3+4))") == 21
""",
        tests="priorité, parenthèses imbriquées, unaire après opérateur",
    ),
    CodeTask(
        "maitre", "cache_lru_ttl",
        "Écris une classe Python `CacheLRU(capacite: int, ttl: float)` avec "
        "`get(cle)`, `put(cle, valeur)` et `taille()`. Une entrée expire après "
        "`ttl` secondes. Quand la capacité est dépassée, la moins récemment "
        "utilisée est évincée — un `get` compte comme une utilisation. Les "
        "entrées expirées ne comptent jamais dans `taille()` ni ne sont "
        "renvoyées par `get` (qui rend None). Réponds uniquement par le code.",
        """
import time
c = CacheLRU(capacite=2, ttl=10)
c.put("a", 1); c.put("b", 2)
assert c.get("a") == 1
c.put("c", 3)                       # "b" est la moins recemment utilisee
assert c.get("b") is None, "l'eviction LRU doit tenir compte des get"
assert c.get("a") == 1 and c.get("c") == 3
assert c.taille() == 2

d = CacheLRU(capacite=5, ttl=0.2)
d.put("x", 1)
assert d.get("x") == 1
time.sleep(0.35)
assert d.get("x") is None, "une entree expiree ne doit pas etre renvoyee"
assert d.taille() == 0, "une entree expiree ne doit pas compter dans taille()"
""",
        tests="LRU + expiration temporelle, deux invariants qui interagissent",
    ),
    CodeTask(
        "extreme", "planificateur_taches",
        "Écris une fonction Python `ordonner(taches: dict[str, list[str]]) -> "
        "list[str]` qui reçoit un graphe de dépendances (clé = tâche, valeur = "
        "liste des tâches dont elle dépend) et renvoie un ordre d'exécution "
        "valide. À égalité, l'ordre alphabétique départage. Si le graphe "
        "contient un cycle, lève `ValueError` en incluant dans le message les "
        "noms des tâches du cycle. Réponds uniquement par le code.",
        """
assert ordonner({"b": ["a"], "a": [], "c": ["b"]}) == ["a", "b", "c"]
# Departage alphabetique a egalite de contraintes.
assert ordonner({"z": [], "a": [], "m": []}) == ["a", "m", "z"]
assert ordonner({"d": ["b", "c"], "b": ["a"], "c": ["a"], "a": []}) == ["a", "b", "c", "d"]
assert ordonner({}) == []
try:
    ordonner({"a": ["b"], "b": ["a"]})
except ValueError as exc:
    msg = str(exc)
    assert "a" in msg and "b" in msg, f"le message doit nommer le cycle, recu: {msg!r}"
else:
    raise AssertionError("un cycle doit lever ValueError")
""",
        tests="tri topologique déterministe + détection de cycle nommée",
    ),
)

TASKS = TASKS + (
    CodeTask(
        "legende", "moteur_motifs",
        "Écris une fonction Python `correspond(motif: str, texte: str) -> bool` "
        "qui teste si le motif décrit l'intégralité du texte. Le motif accepte "
        "`.` (un caractère quelconque), `*` (zéro ou plus du motif précédent) et "
        "`?` (zéro ou un du motif précédent). N'utilise pas le module `re`. "
        "Réponds uniquement par le code.",
        """
assert correspond("a*", "aaa") is True
assert correspond("a*", "") is True
assert correspond(".*", "nimporte quoi") is True
assert correspond("a.c", "abc") is True
assert correspond("a.c", "abbc") is False
assert correspond("ab*c", "ac") is True
assert correspond("ab?c", "abc") is True
assert correspond("ab?c", "ac") is True
assert correspond("ab?c", "abbc") is False
assert correspond("a", "ab") is False, "le motif doit couvrir tout le texte"
# s* consomme les deux s : la correspondance est totale.
assert correspond("mis*issippi", "mississippi") is True
# Le x final n'est couvert par rien.
assert correspond("mis*issippi", "mississippix") is False
assert correspond("a*b", "aaac") is False
assert correspond(".*c", "abc") is True
""",
        tests="retour arrière, quantificateurs imbriqués, correspondance totale",
    ),
    CodeTask(
        "titan", "top_k_efficace",
        "Écris une fonction Python `k_plus_grands(valeurs: list[int], k: int) -> "
        "list[int]` qui renvoie les k plus grandes valeurs, triées par ordre "
        "décroissant. La fonction doit rester efficace sur de très grandes "
        "listes : viser O(n log k), pas un tri complet. Réponds uniquement par "
        "le code.",
        """
import random, time
assert k_plus_grands([3, 1, 4, 1, 5], 2) == [5, 4]
assert k_plus_grands([], 3) == []
assert k_plus_grands([7], 5) == [7]
assert k_plus_grands([2, 2, 2], 2) == [2, 2]
# La contrainte de performance, verifiee par chronometrage : un tri complet
# de 2 millions d'elements depasse largement ce budget sur cette machine.
grand = [random.randint(0, 10**9) for _ in range(2_000_000)]
attendu = sorted(grand, reverse=True)[:10]
debut = time.perf_counter()
obtenu = k_plus_grands(grand, 10)
ecoule = time.perf_counter() - debut
assert obtenu == attendu, "resultat incorrect sur grande entree"
assert ecoule < 1.5, f"trop lent : {ecoule:.2f}s — un tri complet ne suffit pas"
""",
        tests="**efficacité mesurée au chronomètre** — correct mais naïf échoue",
    ),
    CodeTask(
        "mythique", "compteur_concurrent",
        "Écris une classe Python `CompteurSur(seuil: int)` avec `incrementer(cle)` "
        "et `au_dessus()`. `incrementer` est appelée depuis plusieurs threads "
        "simultanément et doit rester exacte. `au_dessus()` renvoie l'ensemble "
        "des clés dont le compte atteint ou dépasse le seuil, sans jamais lever "
        "d'exception même si un incrément a lieu pendant l'appel. "
        "Réponds uniquement par le code.",
        """
import threading
c = CompteurSur(seuil=1000)
cles = ["a", "b", "c"]
def travail():
    for _ in range(500):
        for k in cles:
            c.incrementer(k)
lecteurs_ok = []
def lecteur():
    try:
        for _ in range(200):
            c.au_dessus()
        lecteurs_ok.append(True)
    except Exception as exc:
        lecteurs_ok.append(exc)
threads = [threading.Thread(target=travail) for _ in range(4)]
threads += [threading.Thread(target=lecteur) for _ in range(2)]
for t in threads: t.start()
for t in threads: t.join()
assert all(v is True for v in lecteurs_ok), f"lecture concurrente cassee: {lecteurs_ok}"
assert c.au_dessus() == {"a", "b", "c"}, f"compte inexact: {c.au_dessus()}"
""",
        tests="exactitude sous contention réelle, lecture pendant écriture",
    ),
)

#: Ordre de difficulté croissante. La campagne monte tant que ça passe et
#: s'arrête après deux échecs consécutifs — un modèle peut rater un niveau
#: sur un détail et réussir le suivant, et s'arrêter au premier échec
#: sous-estimerait sa limite.
#:
#: Les trois derniers niveaux attaquent des dimensions différentes plutôt
#: qu'une difficulté simplement croissante : retour arrière (legende),
#: **efficacité chronométrée** (titan), exactitude sous concurrence
#: (mythique). Un modèle peut buter sur l'un et passer l'autre — et ce
#: profil-là est plus informatif qu'un rang unique. Le niveau titan est le
#: seul où un code *correct* échoue s'il est naïf : c'est la mesure de
#: qualité, pas seulement de justesse.
LEVEL_ORDER: tuple[str, ...] = (
    "simple", "moyen", "complexe", "expert", "maitre", "extreme",
    "legende", "titan", "mythique",
)


def extract_code(raw: str) -> str:
    """Le code, débarrassé de ce qui l'entoure.

    Les modèles encadrent leur réponse de ```python et la commentent avant
    et après. Refuser ces réponses mesurerait des habitudes de mise en
    forme plutôt que la compétence — le même écueil que l'extraction JSON,
    qui notait 0/5 des objets parfaits.
    """
    fenced = re.findall(r"```(?:python|py)?\s*(.*?)```", raw, re.DOTALL)
    if fenced:
        return max(fenced, key=len).strip()
    return raw.strip()


@dataclass
class CodeResult:
    task: str
    level: str
    passed: bool
    detail: str
    code: str = ""
    stderr: str = ""

    def as_dict(self) -> dict:
        return {"task": self.task, "level": self.level, "passed": self.passed,
                "detail": self.detail}


def run_code_task(task: CodeTask, raw_answer: str) -> CodeResult:
    """Exécuter la réponse contre les assertions, hors de ce processus."""
    code = extract_code(raw_answer)
    if not code:
        return CodeResult(task.name, task.level, False, "réponse vide")

    with tempfile.TemporaryDirectory(prefix="code_bench_") as tmp:
        script = Path(tmp) / "essai.py"
        script.write_text(code + "\n\n" + task.checks, encoding="utf-8")
        try:
            done = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, text=True, timeout=EXEC_TIMEOUT_S,
                cwd=tmp,
            )
        except subprocess.TimeoutExpired:
            return CodeResult(task.name, task.level, False,
                              f"expiré après {EXEC_TIMEOUT_S:.0f}s", code)

    if done.returncode == 0:
        return CodeResult(task.name, task.level, True, "assertions passées", code)

    stderr = (done.stderr or "").strip()
    last = stderr.splitlines()[-1] if stderr else "échec sans message"
    return CodeResult(task.name, task.level, False, last[:160], code, stderr[-600:])
