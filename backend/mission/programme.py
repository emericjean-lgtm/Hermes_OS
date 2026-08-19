"""Un cahier des charges se déroule, il ne se lance pas (HOS-127).

Mesuré : les quarante sections de Skills360 données d'un coup produisent
**un fichier de 176 lignes**, 10 concepts sur 18, et zéro marqueur
`À DÉCIDER` — alors que la même règle était tenue à 26 marqueurs quand une
seule section était demandée.

Ce n'est pas le modèle qui plafonne, c'est l'arithmétique : le décomposeur
borne à 3-8 tâches, chaque tâche à 12 tours d'outils et 900 s. Au mieux
~96 opérations de fichier pour un cahier qui demande 18 entités, une API,
un frontend, des tests et de la documentation.

Une section, en revanche, tient : l'essai du 2026-08-16 a produit une étape
`verifiee` — manifeste tenu, tests exécutés et passés — en **390 secondes**.

Ce module déroule donc le cahier section par section. Quarante missions de
six à dix minutes, c'est une nuit sans surveillance.

## Le découpage ne fait appel à aucun modèle

Les titres sont déjà numérotés (`# 6. MODÈLE D'IDENTITÉ`). Découper dessus
est mécanique, vérifiable, et ne peut rien inventer — ce qui est la
première exigence quand on automatise la lecture d'une spécification.

## Ce qui arrête la file, et ce qui ne l'arrête pas

C'est la décision de conception de ce module, et elle vient d'une mesure.
L'étape 1 du dernier essai était `contredite` **uniquement** parce qu'elle
avait déclaré `docs/identity_design.md` et écrit `docs/decisions.md` — ses
tests passaient. Arrêter une nuit entière pour un nom de fichier serait
absurde ; continuer sur une identité dont les tests échouent le serait
tout autant, puisque trente sections en dépendent.

On distingue donc :

* **bloquant** — les tests du livrable échouent, une boucle d'import
  fatale existe, ou rien n'a été écrit. Ce qui suit s'appuierait sur du
  vide ou sur du faux ;
* **signalé** — un livrable annoncé porte un autre nom que celui écrit,
  alors que le reste tient. On l'inscrit et on continue.

Un `contradicted` sans cause nommable est traité comme bloquant : ne pas
savoir pourquoi n'est pas une raison de continuer.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("hermes_os.mission.programme")

#: `# 12. POSITIONS ET COMPÉTENCES` — le niveau 1 seulement. Les `##` sont
#: des sous-parties d'une section, pas des sections.
_TITRE = re.compile(r"^#\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)

#: `Auth`, `Workshop`, `PositionSkill`… tels que le cahier les énumère
#: lui-même. Repéré sur la section qui déclare le modèle de données.
_CONCEPT = re.compile(r"^\s{0,4}([A-Z][A-Za-z]{2,})\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Section:
    numero: int
    titre: str
    corps: str

    @property
    def etiquette(self) -> str:
        return f"§{self.numero} {self.titre}"


@dataclass
class Etape:
    """Une section et ce qu'il en est advenu."""
    section: Section
    statut: str = "en_attente"  # en_attente | faite | signalee | bloquee | ignoree
    qualite: str = ""
    detail: str = ""
    duree_s: float = 0.0
    fichiers: list[str] = field(default_factory=list)


def decouper(texte: str) -> list[Section]:
    """Les sections d'un cahier, **toutes**, dans l'ordre où il les écrit.

    L'ordre du document **est** l'ordre des dépendances dans ce cahier-ci :
    §6 identité, §8 organisation, §9 ateliers, §11 postes, §16 affectation,
    §19+ conformité — et son propre §40 dessine littéralement cette chaîne.
    On ne réordonne donc rien : inventer un ordre serait exactement ce que
    le §4 interdit.

    Aucun filtre non plus. Une première version écartait les sections de
    moins de 400 caractères, au motif qu'elles n'auraient « pas de quoi
    occuper une mission ». Mesuré sur le vrai cahier, ce filtre était
    **exactement à l'envers** : il jetait §6 (identité), §9 (ateliers),
    §11 (postes), §17 (compétences) — denses et courtes, écrites en
    schémas — et gardait §4 « RÈGLE CONTRE L'INVENTION » et §34 « MATRICE
    DE VÉRITÉ », deux pages de prose qui ne construisent rien. La longueur
    mesure le bavardage, pas la matière.
    """
    marques = list(_TITRE.finditer(texte))
    sections: list[Section] = []
    for i, marque in enumerate(marques):
        debut = marque.end()
        fin = marques[i + 1].start() if i + 1 < len(marques) else len(texte)
        corps = texte[debut:fin].strip()
        if not corps:
            continue
        sections.append(Section(numero=int(marque.group(1)),
                                titre=marque.group(2).strip(), corps=corps))
    return sections


def concepts_du_cahier(sections: list[Section]) -> set[str]:
    """Les entités que le cahier déclare devoir représenter.

    Lues dans **sa** section de modèle de données, pas dans une liste que
    j'aurais écrite : c'est le cahier qui dit ce qu'il contient. Un cahier
    sans section de ce genre rend un ensemble vide, et tout devient alors
    une section à construire — dégradé, jamais faux.
    """
    for section in sections:
        titre = section.titre.upper()
        if "MODÈLE DE DONNÉES" in titre or "MODELE DE DONNEES" in titre \
                or "DATA MODEL" in titre:
            return {m.group(1) for m in _CONCEPT.finditer(section.corps)}
    return set()


def classer(sections: list[Section]) -> tuple[list[Section], list[Section]]:
    """(à construire, règles permanentes).

    Le critère vient du cahier : une section qui nomme au moins une des
    entités de son propre modèle de données demande qu'on construise
    quelque chose ; les autres énoncent des règles de travail — « ne pas
    inventer », « ordre de priorité », « principe de travail » — qui
    valent pour **toutes** les missions et n'en méritent aucune.

    Les leur faire exécuter coûterait douze missions de dix minutes pour
    produire de la paraphrase. Les transmettre en contexte, en revanche,
    est exactement leur rôle.

    Sans modèle de données déclaré, tout est à construire : mieux vaut une
    mission de trop qu'une règle silencieusement transformée en livrable.
    """
    concepts = concepts_du_cahier(sections)
    if not concepts:
        return list(sections), []
    motif = re.compile(r"\b(" + "|".join(sorted(concepts, key=len, reverse=True))
                       + r")\b")
    a_construire, regles = [], []
    for section in sections:
        (a_construire if motif.search(section.corps) else regles).append(section)
    return a_construire, regles


#: Le plan vit à côté du journal : il appartient à l'outil, et il est
#: ignoré par le diff de vérification comme tout ce qui est sous `.hermes`.
CHEMIN_PLAN = ".hermes/plan.md"

_LIGNE_PLAN = re.compile(r"^\s*-\s*\[( |x|X)\]\s*§(\d+)\b", re.MULTILINE)

_EN_TETE_PLAN = """# Plan d'exécution du cahier des charges

> **À relire avant de lancer.** Coché = une mission sera lancée pour cette
> section. Décoché = la section est transmise comme règle permanente à
> toutes les missions, sans mission propre.
>
> La proposition ci-dessous vient d'un classement automatique : une section
> est cochée si elle nomme une entité du modèle de données du cahier. Ce
> critère se trompe — mesuré à environ 30 % sur un cahier réel : il a classé
> « CONFORMITÉ », « ALERTES », « API » et « BACKEND » comme de simples
> règles, et « OBJECTIF FINAL » comme un livrable. C'est pourquoi ce fichier
> existe : corrige les cases, elles font foi.
>
> Compte environ dix minutes par case cochée.

"""


def ecrire_plan(chemin, sections: list[Section],
                a_construire: list[Section]) -> str:
    """Le plan proposé, sous une forme qu'on corrige à la main."""
    from pathlib import Path

    numeros = {s.numero for s in a_construire}
    lignes = [_EN_TETE_PLAN]
    for section in sections:
        case = "x" if section.numero in numeros else " "
        lignes.append(f"- [{case}] §{section.numero} — {section.titre}")
    texte = "\n".join(lignes) + "\n"
    cible = Path(chemin)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(texte, encoding="utf-8")
    return texte


def lire_plan(chemin) -> Optional[set[int]]:
    """Les sections cochées, ou `None` si aucun plan n'existe.

    `None` n'est pas « rien à faire » : c'est « personne n'a encore
    regardé », et l'appelant doit s'arrêter là plutôt que de dérouler
    quarante missions sur un classement que personne n'a validé.
    """
    from pathlib import Path

    cible = Path(chemin)
    if not cible.is_file():
        return None
    try:
        texte = cible.read_text(encoding="utf-8")
    except OSError:
        return None
    return {int(m.group(2)) for m in _LIGNE_PLAN.finditer(texte)
            if m.group(1).lower() == "x"}


def ecrire_proteges(chemin_workspace, documents: list[str]) -> str:
    """Déclarer les documents que le travail ne doit pas réécrire (HOS-129).

    Mesuré sur la première file réelle : une mission a écrasé
    `PROJECT_SPEC.md`, qui est passé de 23 Ko et 342 lignes à 1,2 Ko ne
    contenant plus que la section sur laquelle elle travaillait. **La
    source de vérité du projet a été détruite par le projet.**

    Le §36 de ce cahier exigeait déjà une validation explicite pour toute
    modification : la règle existait, rien ne la faisait respecter.

    La liste est écrite à côté du plan, en clair, un chemin par ligne —
    elle se relit et se corrige comme lui. `file_tools` la consulte à
    chaque écriture, quel que soit l'outil appelant.
    """
    from pathlib import Path

    from backend.tools.file_tools import FICHIER_PROTEGES

    cible = Path(chemin_workspace) / FICHIER_PROTEGES
    cible.parent.mkdir(parents=True, exist_ok=True)
    entete = [
        "# Documents qui definissent le travail. Le travail ne les reecrit",
        "# pas : une mission a deja detruit un cahier des charges de 342",
        "# lignes en y ecrivant la section sur laquelle elle travaillait.",
        "# Un chemin relatif par ligne ; relu a chaque ecriture.",
    ]
    texte = "\n".join(entete + list(documents)) + "\n"
    cible.write_text(texte, encoding="utf-8")
    return texte


def bloc_de_regles(regles: list[Section]) -> str:
    """Les règles permanentes, recopiées telles quelles pour chaque mission.

    Recopiées, pas résumées : résumer une règle de spécification, c'est la
    réécrire, et le §4 de ce cahier-là interdit précisément cela.
    """
    if not regles:
        return ""
    morceaux = ["Règles permanentes de ce projet — elles s'appliquent à "
                "cette étape comme à toutes les autres :"]
    for section in regles:
        morceaux += ["", f"### {section.etiquette}", section.corps]
    return "\n".join(morceaux)


def bloquant(verification: Optional[dict]) -> tuple[bool, str]:
    """Faut-il arrêter la file ? Et pourquoi.

    Rend `(False, "")` quand il n'y a rien à redire, et quand la
    contradiction est cosmétique.
    """
    if not verification:
        # Rien n'a été mesuré, et **on ne peut rien en conclure ici**.
        # L'appelant a déjà écarté le cas « la mission n'a pas eu lieu »
        # avant d'arriver jusqu'ici (voir `derouler`) ; ce qui reste est
        # une mission qui a tourné sans workspace lié, et l'absence de
        # mesure n'est pas une preuve d'échec.
        return False, ""

    tests = verification.get("tests") or {}
    if tests.get("ran") and tests.get("passed") is False:
        return True, "les tests du livrable échouent"

    fatals = (verification.get("imports") or {}).get("fatals") or []
    if fatals:
        return True, f"boucle d'import fatale : {'; '.join(map(str, fatals))}"

    if not (verification.get("created") or verification.get("modified")
            or verification.get("deleted")):
        return True, "aucun fichier écrit"

    if verification.get("contradicted"):
        manquants = (verification.get("manifeste") or {}).get("manquants") or []
        if manquants:
            # Le seul cas cosmétique : le plan et l'exécution divergent d'un
            # nom de fichier, mais ce qui est là tient debout.
            return False, ("livrables annoncés sous un autre nom : "
                           + ", ".join(map(str, manquants)))
        return True, "contredit sans cause nommable"

    return False, ""


def brief_de_section(section: Section, *, nom_du_cahier: str,
                     regles: str = "") -> str:
    """Ce qu'on demande pour une section, et rien de plus.

    Le corps de la section est recopié tel quel : le modèle ne doit pas
    avoir à retrouver dans un fichier de 23 Ko la partie qui le concerne,
    et un résumé de ma part serait une réécriture de la spécification.
    """
    morceaux = [
        f"Tu travailles sur le projet décrit par `{nom_du_cahier}`, "
        f"à la racine de ce dossier.",
        "",
        f"Réalise **une seule étape** : la section {section.etiquette}.",
        "",
        "Voici cette section, mot pour mot :",
        "",
        "---",
        section.corps,
        "---",
        "",
        "Le reste du projet existe déjà dans ce dossier ou reste à faire par "
        "d'autres étapes. Regarde ce qui est là avant d'écrire : appuie-toi "
        "sur l'existant, ne le réécris pas.",
    ]
    if regles:
        morceaux += ["", regles]
    morceaux += [
        "",
        "Écris réellement les fichiers sur le disque, puis relis-les pour "
        "confirmer qu'ils existent avant de conclure.",
    ]
    return "\n".join(morceaux)


def derouler(
    sections: list[Section],
    *,
    lancer: Callable[[Section], dict],
    nom_du_cahier: str = "PROJECT_SPEC.md",
    on_etape: Optional[Callable[[Etape], None]] = None,
) -> list[Etape]:
    """Enchaîner les sections, et s'arrêter sur ce qui compromet la suite.

    `lancer` reçoit une section et rend le rapport d'objectif — c'est le
    seul point de contact avec le moteur, pour que toute la logique
    ci-dessus reste testable sans lui.

    Ne lève jamais : une file de quarante missions qui tombe sur la
    trente-deuxième doit rendre les trente et une premières, pas une trace
    d'exception.
    """
    etapes = [Etape(section=s) for s in sections]
    arretee = False
    for etape in etapes:
        if arretee:
            etape.statut = "ignoree"
            etape.detail = "étape précédente bloquante"
            continue
        try:
            rapport = lancer(etape.section) or {}
        except Exception as erreur:  # noqa: BLE001 - une file ne casse pas
            logger.warning("section %s a levé", etape.section.etiquette,
                           exc_info=True)
            etape.statut = "bloquee"
            etape.detail = f"{type(erreur).__name__}: {erreur}"
            arretee = True
            if on_etape is not None:
                on_etape(etape)
            continue

        etape.qualite = str(rapport.get("qualite") or "")
        etape.duree_s = float(rapport.get("total_duration_ms") or 0.0) / 1000.0

        # HOS-128 : **une mission qui n'a pas eu lieu n'est pas une mission
        # sans mesure.** Les deux se présentent pareil — pas de
        # `verification` — et `bloquant()` répondait « rien à signaler »
        # pour les deux.
        #
        # Mesuré sur la première file réelle : les 26 sections ont rendu
        # `{"faite": 26}` en **0 seconde**, zéro fichier sur le disque. Les
        # objectifs refusaient de démarrer — le dossier n'était pas
        # autorisé — chacun rendait `status: failed` et un rapport vide, et
        # ce module les comptait comme faites. Le faux succès exact que ce
        # dépôt existe pour empêcher, produit par le module chargé de le
        # détecter.
        statut_objectif = str(rapport.get("statut_objectif") or "").lower()
        if statut_objectif and statut_objectif != "completed":
            etape.statut = "bloquee"
            etape.detail = f"l'objectif n'a pas abouti (statut : {statut_objectif})"
            arretee = True
            if on_etape is not None:
                on_etape(etape)
            continue
        if not rapport:
            etape.statut = "bloquee"
            etape.detail = "aucun rapport — la mission n'a pas eu lieu"
            arretee = True
            if on_etape is not None:
                on_etape(etape)
            continue

        verification = rapport.get("verification")
        doit_arreter, raison = bloquant(verification)
        if doit_arreter:
            etape.statut, etape.detail, arretee = "bloquee", raison, True
        elif raison:
            etape.statut, etape.detail = "signalee", raison
        else:
            etape.statut = "faite"
        if on_etape is not None:
            on_etape(etape)
    return etapes


def bilan(etapes: list[Etape]) -> dict[str, Any]:
    """De quoi savoir, en un coup d'œil, où en est le cahier."""
    par_statut: dict[str, int] = {}
    for etape in etapes:
        par_statut[etape.statut] = par_statut.get(etape.statut, 0) + 1
    bloquee = next((e for e in etapes if e.statut == "bloquee"), None)
    return {
        "sections": len(etapes),
        "par_statut": par_statut,
        "duree_s": round(sum(e.duree_s for e in etapes)),
        "arret": {"section": bloquee.section.etiquette,
                  "raison": bloquee.detail} if bloquee else None,
        "detail": [{"section": e.section.etiquette, "statut": e.statut,
                    "qualite": e.qualite, "detail": e.detail,
                    "duree_s": round(e.duree_s)} for e in etapes],
    }
