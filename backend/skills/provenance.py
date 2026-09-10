r"""D'ou vient une competence de Hermes Agent, et ce qu'on n'en sait pas (G-27, HOS-275).

Hermes OS **lit** trois fichiers que l'agent tient sous `HERMES_HOME/skills`.
Il n'en ecrit aucun, n'en copie rien dans `hermes.db`, et ne fabrique aucune
categorie que ces fichiers ne portent pas.

    .bundled_manifest   `nom:hash` par ligne — ce que la synchronisation a
                        pose, et l'empreinte des octets qu'elle a poses
    .hub/lock.json      les poses par le hub, avec leur `install_path`
    .usage.json         un enregistrement par competence, dont `created_by`

## Ce que la mesure du 2026-09-10 a etabli

Les trois existent : 69 entrees au manifeste, 75 au `.usage.json`, et un
`lock.json` **vide** — aucune des competences installees n'est passee par le
chemin trace du hub. Cinq enregistrements portent `created_by: "agent"`.

La chaine complete a ete demontree sur un `HERMES_HOME` de substitution :
une creation au premier plan laisse `created_by: None`, une creation sous
`BACKGROUND_REVIEW` laisse `created_by: "agent"`, et **un nouveau processus
relit les deux**. La persistance et le redemarrage sont donc acquis.

Et 69 des 69 competences du manifeste correspondent encore a leur empreinte
d'origine : aucune n'a ete modifiee sur le disque.

## Ce qu'on refuse de dire

**« Utilisateur » n'est pas une categorie disponible.** `created_by: None`
couvre a la fois « creee au premier plan, donc a l'utilisateur » et « aucun
enregistrement d'origine n'a jamais ete ecrit ». Rien ne les separe. La
categorie s'appelle donc `SANS_MARQUEUR`, et elle ne pretend rien.

**« Apprise » et « approuvee » n'existent pas.** Aucun champ ne les porte, et
la file d'approbation des Skills n'a jamais servi (G-26 : le dossier
`pending/` n'existe pas). Les nommer serait inventer.

**`skill_usage.is_agent_created()` n'est pas utilise ici, et ne doit pas
l'etre.** Malgre son nom, il ne lit jamais `created_by` : il rend « ni
bundled ni hub ». Mesure — une competence creee au premier plan, donc
`created_by: None`, en ressort `True`, pendant que
`list_agent_created_skill_names()`, qui lit l'enregistrement, l'exclut a
juste titre. Deux fonctions voisines, deux methodes opposees. La provenance
se lit dans l'enregistrement, jamais dans une localisation.

## Le conflit de clef

Le magasin est indexe par **nom de frontmatter** dans 74 cas sur 75. Une
competence dont le dossier et le `name:` different peut donc porter **deux
enregistrements** — mesure : `documentation-verification` (`created_by:
"agent"`, jamais utilisee) et `Documentation & Identity Verification`
(`created_by: None`, trois usages) designent le meme dossier.

On ne choisit pas. `CONFLIT` est un etat rendu tel quel, avec les deux
valeurs : preferer l'une serait exactement l'inference que ce module refuse.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Optional

logger = logging.getLogger("hermes_os.skills.provenance")

#: Les categories rendues. Bornees : rien d'autre ne sort d'ici.
SYSTEME_INTACTE = "systeme_intacte"
SYSTEME_MODIFIEE = "systeme_modifiee"
POSEE_PAR_LE_HUB = "posee_par_le_hub"
GENEREE_PAR_L_AGENT = "generee_par_l_agent"
SANS_MARQUEUR = "sans_marqueur"
CONFLIT = "conflit"
INCONNUE = "inconnue"

CATEGORIES = (SYSTEME_INTACTE, SYSTEME_MODIFIEE, POSEE_PAR_LE_HUB,
              GENEREE_PAR_L_AGENT, SANS_MARQUEUR, CONFLIT, INCONNUE)


@dataclass(frozen=True)
class Provenance:
    """Une categorie, et la preuve qui la soutient.

    `preuve` n'est pas decoratif : une categorie sans son fichier de
    provenance serait une affirmation d'interface, et c'est precisement ce
    que G-27 interdit. Un lecteur doit pouvoir aller verifier.
    """

    categorie: str
    preuve: str
    #: Renseigne seulement quand le magasin porte deux enregistrements.
    conflit: Optional[tuple[str, str]] = None


def _skills() -> Path:
    """Le meme dossier que `registre.lire()` parcourt, et par le meme appel.

    Le recalculer ici les ferait diverger au premier changement — c'est
    exactement la faute que HOS-274 est alle corriger.
    """
    from backend.skills.registre import racine_des_competences

    return racine_des_competences()


# ── Les trois magasins de l'agent, lus tels quels ─────────────────────

def _manifeste() -> dict[str, str]:
    """`{nom: empreinte}` du `.bundled_manifest`. Vide si absent ou illisible."""
    chemin = _skills() / ".bundled_manifest"
    try:
        lignes = chemin.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    entrees: dict[str, str] = {}
    for ligne in lignes:
        nom, _, empreinte = ligne.partition(":")
        if nom.strip():
            entrees[nom.strip()] = empreinte.strip()
    return entrees


def _poses_par_le_hub() -> set[str]:
    """Les noms du `.hub/lock.json`. Mesure : vide sur cette installation."""
    try:
        brut = json.loads((_skills() / ".hub" / "lock.json")
                          .read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return set()
    installees = brut.get("installed") if isinstance(brut, dict) else None
    return {str(k) for k in installees} if isinstance(installees, dict) else set()


def _usage() -> dict[str, dict]:
    try:
        brut = json.loads((_skills() / ".usage.json")
                          .read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return brut if isinstance(brut, dict) else {}


def _empreinte_du_dossier(dossier: Path) -> str:
    """La meme empreinte que `skills_sync._dir_hash` : md5 des chemins relatifs
    et des octets, dans l'ordre trie.

    Recalculee ici plutot que demandee a l'agent parce qu'aucune RPC ne la
    rend — et c'est ce recalcul qui rend la categorie **refutable** : elle ne
    depend d'aucune declaration, seulement des octets presents.
    """
    h = hashlib.md5()
    for chemin in sorted(p for p in dossier.rglob("*") if p.is_file()):
        try:
            h.update(str(chemin.relative_to(dossier)).encode("utf-8"))
            h.update(chemin.read_bytes())
        except OSError:
            return ""
    return h.hexdigest()


# ── La lecture ────────────────────────────────────────────────────────

class _Magasins(NamedTuple):
    """Les trois fichiers, lus une fois et passes ensemble."""

    manifeste: dict
    hub: set
    usage: dict


def provenance(nom: str, dossier: Optional[Path] = None) -> Provenance:
    """La provenance d'une competence, ou `INCONNUE`.

    `nom` est le **nom de frontmatter** — celui que `registre.lire()` rend et
    que toutes les surfaces emploient. `dossier` sert a verifier l'empreinte
    d'une competence du manifeste ; sans lui, une competence systeme est
    rendue `INCONNUE` plutot que supposee intacte.
    """
    return _provenance(nom, dossier,
                       _Magasins(_manifeste(), _poses_par_le_hub(), _usage()))


def _provenance(nom: str, dossier: Optional[Path],
                magasins: "_Magasins") -> Provenance:
    identifiant = (nom or "").strip()
    if not identifiant:
        return Provenance(INCONNUE, "aucun nom demande")

    manifeste, hub, usage = magasins

    # Deux enregistrements pour un meme dossier : on ne tranche pas.
    if dossier is not None and dossier.name != identifiant:
        a, b = usage.get(identifiant), usage.get(dossier.name)
        if isinstance(a, dict) and isinstance(b, dict) and (
                a.get("created_by") != b.get("created_by")):
            return Provenance(
                CONFLIT,
                f"deux enregistrements dans .usage.json : « {identifiant} » et "
                f"« {dossier.name} »",
                conflit=(str(a.get("created_by")), str(b.get("created_by"))))

    if identifiant in hub:
        return Provenance(POSEE_PAR_LE_HUB, ".hub/lock.json")

    if identifiant in manifeste:
        attendue = manifeste[identifiant]
        if not attendue:
            return Provenance(
                INCONNUE,
                ".bundled_manifest v1 : le nom est la, l'empreinte manque")
        if dossier is None:
            return Provenance(
                INCONNUE,
                ".bundled_manifest porte une empreinte, mais aucun dossier "
                "n'a ete fourni pour la verifier")
        obtenue = _empreinte_du_dossier(dossier)
        if not obtenue:
            return Provenance(INCONNUE, "dossier illisible")
        return Provenance(
            SYSTEME_INTACTE if obtenue == attendue else SYSTEME_MODIFIEE,
            f".bundled_manifest {attendue[:8]} / disque {obtenue[:8]}")

    enregistrement = usage.get(identifiant)
    if isinstance(enregistrement, dict):
        origine = enregistrement.get("created_by")
        if origine == "agent":
            return Provenance(GENEREE_PAR_L_AGENT,
                              '.usage.json created_by: "agent"')
        if origine == "installed":
            return Provenance(POSEE_PAR_LE_HUB,
                              '.usage.json created_by: "installed"')
        return Provenance(
            SANS_MARQUEUR,
            ".usage.json created_by: null — « creee au premier plan » et "
            "« aucune origine enregistree » ne se distinguent pas")

    return Provenance(INCONNUE, "aucun des trois magasins ne la nomme")


def dossiers_par_nom() -> dict[str, Path]:
    """`{nom de frontmatter: dossier}`, une seule marche de l'arbre.

    Le dossier ne porte pas toujours le nom de la competence — c'est
    justement ce decalage qui produit le `CONFLIT` mesure — donc la table se
    construit en lisant les en-tetes, pas en supposant le nom du dossier.
    """
    base = _skills()
    if not base.is_dir():
        return {}
    table: dict[str, Path] = {}
    for chemin in base.rglob("SKILL.md"):
        if any(p.startswith(".") for p in chemin.parts):
            continue
        table.setdefault(_nom_de_frontmatter(chemin), chemin.parent)
    return table


def par_competence(competences) -> dict[str, Provenance]:
    """La provenance de chaque `Competence` de `registre.lire()`.

    Les trois magasins et l'arbre sont lus **une fois** : `provenance()` les
    relit a chaque appel, ce qui convient a un appel isole et coute
    soixante-cinq relectures autrement.
    """
    magasins = _Magasins(_manifeste(), _poses_par_le_hub(), _usage())
    dossiers = dossiers_par_nom()
    return {c.nom: _provenance(c.nom, dossiers.get(c.nom), magasins)
            for c in competences}


def _nom_de_frontmatter(skill_md: Path) -> str:
    """Le `name:` de l'en-tete, ou le nom du dossier.

    Meme lecture primitive que `registre._entete` : on ne cherche qu'une clef
    de premier niveau, et un fichier mal forme rend le nom du dossier plutot
    que de faire echouer la lecture des soixante-quatre autres.
    """
    try:
        texte = skill_md.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return skill_md.parent.name
    if not texte.startswith("---"):
        return skill_md.parent.name
    fin = texte.find("\n---", 3)
    for ligne in texte[3:fin if fin > 0 else None].splitlines():
        if ligne.startswith("name:"):
            valeur = ligne.split(":", 1)[1].strip().strip('"').strip("'")
            if valeur:
                return valeur
    return skill_md.parent.name


#: Ce que Hermes OS ne peut PAS dire, mesure le 2026-09-10 — et pourquoi la
#: relation « cette competence vient de ce Run » n'est pas offerte.
#:
#: `skill_manage` transmet bien `task_id` et `session_id` a
#: `record_created` / `bump_patch`. Mais `_apply` n'ecrit que `created_by`
#: dans l'enregistrement : les deux identifiants partent dans le hook
#: `on_skill_lifecycle`, consomme ici par le relais de metriques partagees,
#: qui « emet un fait sans son identite locale » et n'agrege que des
#: compteurs a dimensions bucketisees. Mesure : **0 des 75 enregistrements**
#: porte `task_id` ou `session_id`, et `telemetry/shared_metrics` ne contient
#: aucun nom de competence.
#:
#: Sans clef de jointure, le Run Ledger de Hermes OS ne peut porter aucune
#: relation de provenance. La table `skills` de `hermes.db` a bien une
#: colonne `source_task_id` — elle est vide, et la remplir avec les
#: competences de l'agent en ferait une seconde verite.
#:
#: **Amende par G-34 (HOS-282).** La mesure ci-dessus reste exacte, et sa
#: portee est celle qu'elle a toujours eue : les **enregistrements de
#: l'agent**. Ce qui a change n'est pas eux — c'est qu'une relation vit
#: desormais ailleurs, chez Hermes OS : `_meta.hermes.turnId` pose a
#: l'aller (G-31), la relation `turnId -> run` publiee sur le bus durable
#: (G-32), et l'observateur qui restitue l'etiquette au retour (G-33).
#:
#: La consequence pour cette colonne ne bouge pas d'un pouce : la
#: provenance d'une competence **installee** ne porte toujours aucun Run,
#: parce qu'aucun de ses fichiers n'en nomme un. La relation ne concerne
#: que les **mutations observees**, et c'est `/skills/observations` qui les
#: sert. Confondre les deux populations ferait dire a l'inventaire ce que
#: seul le journal des mutations sait.
CORRELATION_IMPOSSIBLE = (
    "les enregistrements de l'agent ne portent ni task_id ni session_id : "
    "0 des 75 les porte. La relation Run <-> Skill existe ailleurs, sur les "
    "mutations observees — voir /skills/observations")
