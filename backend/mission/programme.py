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
    #: Combien de passes ont ete faites. 1 = reussi du premier coup ;
    #: 2 = une reparation a ete necessaire (HOS-136).
    passes: int = 0


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


def en_lecture_seule(chemin) -> bool:
    """Poser l'attribut lecture seule, et dire si on a réussi.

    La seule protection qui ne suppose rien de l'outil qui écrit. Les deux
    autres — le hook de l'agent, la frontière ACP — gardent un chemin
    nommé ; celle-ci garde le fichier.

    Ne lève jamais : un cahier qu'on n'a pas pu verrouiller reste un cahier
    lisible, et faire échouer une campagne pour un attribut de fichier
    serait un remède pire que le mal. L'échec est rendu, pour que
    l'appelant puisse le dire plutôt que le supposer.
    """
    import stat as _stat
    from pathlib import Path as _Path

    try:
        cible = _Path(chemin)
        if not cible.is_file():
            return False
        cible.chmod(_stat.S_IREAD)
        return True
    except OSError:
        logger.debug("lecture seule impossible sur %s", chemin, exc_info=True)
        return False


def ecrire_proteges(chemin_workspace, documents: list[str]) -> str:
    """Déclarer les documents que le travail ne doit pas réécrire (HOS-129).

    Mesuré sur la première file réelle : une mission a écrasé
    `PROJECT_SPEC.md`, qui est passé de 23 Ko et 342 lignes à 1,2 Ko ne
    contenant plus que la section sur laquelle elle travaillait. **La
    source de vérité du projet a été détruite par le projet.**

    Le §36 de ce cahier exigeait déjà une validation explicite pour toute
    modification : la règle existait, rien ne la faisait respecter.

    La liste est écrite à côté du plan, en clair, un chemin par ligne —
    elle se relit et se corrige comme lui.

    **La phrase qui suivait ici était fausse.** Elle affirmait que
    « `file_tools` la consulte à chaque écriture, quel que soit l'outil
    appelant ». `file_tools` la consulte bien — mais ce sont les outils de
    Hermes OS, et Hermes Agent n'écrit pas avec eux. Mesuré le 2026-08-23 :
    **zéro `session/request_permission` sur deux campagnes complètes**.
    L'agent écrit par son propre `write_file`, sans rien demander, et le
    cahier a été détruit deux nuits de suite.

    Trois défenses désormais, parce qu'aucune ne couvre seule tous les
    chemins :

    * le hook `config/hooks/garde_workspace.py`, étendu à `write_file` et
      `patch` en plus du terminal ;
    * la frontière du client ACP, pour le jour où l'agent demandera une
      permission ;
    * l'attribut **lecture seule** posé ici, qui ne dépend d'aucun chemin
      d'appel. C'est la seule qui aurait tenu les deux fois, parce qu'elle
      ne suppose rien de la façon dont l'écriture arrive.
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
    from pathlib import Path as _P

    verrouilles = [d for d in documents
                   if en_lecture_seule(_P(chemin_workspace) / d)]
    logger.info("%d document(s) d'entree en lecture seule", len(verrouilles))
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

    # HOS-153 : avant les autres, parce que ce defaut-la invalide la preuve
    # sur laquelle tous les suivants s'appuient. Une suite verte obtenue avec
    # un test qui ne peut pas rougir ne dit rien de la section.
    vide = verification.get("livrable_vide") or {}
    if vide:
        return True, (f"livrable vide — {vide.get('fichier')} ne definit "
                      f"ni classe ni fonction")

    tauto = verification.get("test_tautologique") or {}
    if tauto:
        return True, (f"test qui ne peut pas echouer — {tauto.get('fichier')}:"
                      f"{tauto.get('ligne')} ({tauto.get('raison')})")

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
                     regles: str = "", racine: str = "",
                     pile: str = "") -> str:
    """Ce qu'on demande pour une section, et rien de plus.

    Le corps de la section est recopié tel quel : le modèle ne doit pas
    avoir à retrouver dans un fichier de 23 Ko la partie qui le concerne,
    et un résumé de ma part serait une réécriture de la spécification.
    """
    morceaux = [
        f"Tu travailles sur le projet décrit par `{nom_du_cahier}`, "
        f"à la racine de ce dossier.",
        "",
    ]
    if racine:
        # HOS-130 : mesuré, 101 résolutions de chemin sur 145 pointaient
        # hors du workspace — le modèle inventait `/home/user/<dossier>`,
        # `/workspace`, `/`. Il devinait parce que rien ne lui disait où il
        # était. Deux tiers de son budget d'outils y passaient.
        morceaux += [
            f"Tous les chemins que tu donnes aux outils sont **relatifs** à "
            f"la racine de ce dossier ({racine}). Un chemin absolu ou "
            f"commençant par `/home/`, `/workspace` ou `/` est refusé : "
            f"écris la forme `<dossier>/<fichier>` et rien d'autre.",
            "",
        ]
    morceaux += [
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
    if pile:
        # HOS-134 : mesuré sur la septième file — trois piles dans le même
        # projet, 14 `.ts`, 7 `.sql`, 6 `.py`, et le même concept écrit
        # deux fois dans deux langages. Le journal transmet les fichiers
        # produits ; il ne transmettait pas la **décision** qu'ils
        # incarnent, et chaque section rechoisissait sa pile.
        morceaux += ["", pile]
    morceaux += [
        "",
        "Écris réellement les fichiers sur le disque, puis relis-les pour "
        "confirmer qu'ils existent avant de conclure.",
    ]
    # HOS-153 : l'agent porte 81 competences et n'en ouvrait jamais une.
    # `skills_list` fait partie de son toolset ACP — mesure du 2026-08-23,
    # 30 outils dont les trois de competences — mais un modele n'appelle
    # pas un outil dont rien ne lui rappelle l'existence. Les domaines
    # sont nommes ici, pas les competences : quatre-vingts lignes par
    # section se feraient ignorer autant que le silence.
    from backend.skills import registre as _competences

    rappel = _competences.rappel_pour_brief()
    if rappel:
        morceaux.append(rappel)
    return "\n".join(morceaux)


def diagnostic(verification, raison: str) -> str:
    """Ce qu'on redonne au modele pour qu'il repare (HOS-136).

    Le brief de reprise de `retry_policy` opere **dans** une mission. Ici on
    est au-dessus : la mission a fini, elle s'est annoncee reussie, et la
    mesure la dement. Ce qu'il faut transmettre n'est pas « recommence »,
    c'est **l'erreur exacte** — sans quoi la seconde passe repart aussi
    aveugle que la premiere (mesure de HOS-125 : la reprise produisait
    « Créés : aucun » tant qu'on ne lui disait pas quoi corriger).
    """
    morceaux = [f"La passe precedente sur cette section a echoue : {raison}."]
    v = verification or {}
    tests = v.get("tests") or {}
    if tests.get("ran") and tests.get("passed") is False:
        sortie = str(tests.get("output") or "").strip()
        morceaux.append(
            "Voici la sortie reelle des tests. Corrige ce qu'elle rapporte, "
            "ne devine pas :\n\n" + (sortie[-1500:] if sortie else "(vide)"))
    manquants = (v.get("manifeste") or {}).get("manquants") or []
    if manquants:
        morceaux.append("Fichiers annonces et absents du disque : "
                        + ", ".join(map(str, manquants)) + ".")
    fatals = (v.get("imports") or {}).get("fatals") or []
    if fatals:
        morceaux.append("Boucle d'import fatale : " + "; ".join(map(str, fatals))
                        + ". Casse-la.")
    vide = v.get("livrable_vide") or {}
    if vide:
        morceaux.append(
            f"Livrable vide : {vide.get('fichier')} ne contient ni classe, "
            f"ni fonction, ni affectation — seulement "
            f"« {vide.get('apercu')} ». Ecris ce que la section demande. Un "
            f"test qui se contente d'importer ce fichier ne prouve rien.")

    tauto = v.get("test_tautologique") or {}
    if tauto:
        morceaux.append(
            f"Test qui ne peut pas echouer : {tauto.get('fichier')}:"
            f"{tauto.get('ligne')}, dans {tauto.get('fonction')}() — "
            f"{tauto.get('raison')}. Fais porter l'assertion sur le resultat "
            f"reel de la fonction testee, puis casse volontairement cette "
            f"fonction et verifie que le test rougit. Une suite verte est la "
            f"preuve qu'on te demande ; celle-ci n'en est pas une.")
    # Mesure du 2026-08-21 : §9 a echoue **deux fois** sur le meme
    # `from ..models import Atelier`. La sortie des tests le disait, mais
    # noyee dans une trace de collecte pytest ou l'essentiel — le fichier,
    # la ligne, la regle violee — n'apparaissait qu'implicitement. Le dire
    # en clair coute une ligne et evite une passe.
    faux = v.get("faux_paquet") or {}
    if faux:
        morceaux.append(
            f"Dependance fabriquee : le repertoire {faux.get('chemin')} "
            f"porte le nom du paquet tiers `{faux.get('paquet')}` et masque "
            f"le vrai. Supprime-le. Si ce paquet est necessaire, declare-le "
            f"comme dependance ; sinon ecris le code sans lui.")
    remontee = v.get("imports_remontent") or {}
    if remontee:
        points = "." * int(remontee.get("niveau") or 0)
        morceaux.append(
            f"Import relatif invalide : {remontee.get('fichier')} ligne "
            f"{remontee.get('ligne')}, `from {points}module import ...` "
            f"remonte de {remontee.get('niveau')} niveaux alors que ce "
            f"fichier n'en a que {remontee.get('profondeur')} au-dessus de "
            f"lui. Python refuse : « attempted relative import beyond "
            f"top-level package ». Remplace-le par un import absolu depuis "
            f"la racine du projet.")
    morceaux.append(
        "Le travail deja correct est sur le disque : lis-le, ne le reecris "
        "pas. Corrige uniquement ce qui est liste ci-dessus, puis relis tes "
        "fichiers pour confirmer.")
    return "\n\n".join(morceaux)


def derouler(
    sections: list[Section],
    *,
    lancer: Callable[[Section], dict],
    nom_du_cahier: str = "PROJECT_SPEC.md",
    on_etape: Optional[Callable[[Etape], None]] = None,
    reparer: Optional[Callable[[Section, str], dict]] = None,
    max_passes: int = 2,
) -> list[Etape]:
    """Enchainer les sections, et **reparer** avant d'abandonner.

    La premiere version s'arretait des qu'une section echouait. Mesure sur
    neuf lancements : la file franchissait **4,4 sections en moyenne** avant
    de s'arreter, soit un taux d'echec d'environ 18 % par section. A ce
    rythme, atteindre la quatorzieme demande huit reussites d'affilee —
    environ 1,7 % de chance. Un cahier de 26 sections etait donc
    structurellement condamne, quelle que soit la qualite du modele.

    Une section qui echoue est desormais **relancee avec le diagnostic
    exact** — sortie des tests, livrables manquants, boucle d'import — et
    la file ne s'arrete qu'apres `max_passes` tentatives. C'est le but du
    mode autonome : rencontrer un probleme, l'identifier, le corriger.

    `reparer` est distinct de `lancer` parce que la consigne l'est : la
    premiere passe construit, la seconde repare. Sans `reparer`, le
    comportement d'origine est conserve — on s'arrete.

    Ne leve jamais : une file de quarante missions qui tombe sur la
    trente-deuxieme doit rendre les trente et une premieres.
    """
    etapes = [Etape(section=s) for s in sections]
    arretee = False
    for etape in etapes:
        if arretee:
            etape.statut = "ignoree"
            etape.detail = "etape precedente bloquante"
            continue

        raison_finale, verif_finale = "", None
        for passe in range(1, max(1, max_passes) + 1):
            try:
                if passe == 1:
                    rapport = lancer(etape.section) or {}
                else:
                    rapport = reparer(etape.section,
                                      diagnostic(verif_finale, raison_finale)) or {}
            except Exception as erreur:  # noqa: BLE001 - une file ne casse pas
                logger.warning("section %s a leve (passe %d)",
                               etape.section.etiquette, passe, exc_info=True)
                etape.statut = "bloquee"
                etape.detail = f"{type(erreur).__name__}: {erreur}"
                raison_finale = etape.detail
                break

            etape.passes = passe
            etape.qualite = str(rapport.get("qualite") or "")
            etape.duree_s += float(rapport.get("total_duration_ms") or 0.0) / 1000.0

            # HOS-128 : une mission qui n'a pas eu lieu n'est pas une
            # mission sans mesure. Les deux se presentent pareil — pas de
            # `verification` — et `bloquant()` repondait « rien a signaler »
            # pour les deux. Mesure : 26 sections « faites » en 0 seconde
            # sur un disque vide.
            statut = str(rapport.get("statut_objectif") or "").lower()
            if statut and statut != "completed":
                etape.statut = "bloquee"
                etape.detail = f"l'objectif n'a pas abouti (statut : {statut})"
                raison_finale = etape.detail
                break
            if not rapport:
                etape.statut = "bloquee"
                etape.detail = "aucun rapport — la mission n'a pas eu lieu"
                raison_finale = etape.detail
                break

            verif_finale = rapport.get("verification")
            doit_arreter, raison = bloquant(verif_finale)
            if doit_arreter:
                raison_finale = raison
                etape.statut, etape.detail = "bloquee", raison
                if reparer is None or passe >= max(1, max_passes):
                    break
                etape.detail = f"{raison} — passe {passe} echouee, reparation"
                if on_etape is not None:
                    on_etape(etape)
                continue
            etape.statut = "reparee" if passe > 1 else (
                "signalee" if raison else "faite")
            etape.detail = raison
            break

        if etape.statut == "bloquee":
            arretee = True
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
