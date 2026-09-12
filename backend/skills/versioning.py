r"""Le versioning des Skills : le ledger de mutations de l'agent, LU (G-42, HOS-303).

§10 nommait ce manque explicitement : *« le ledger de l'agent
(`.curator_ledger.jsonl`) [porterait le versioning et le rollback], mais il
n'existe pas sur cette installation, et aucune RPC ne l'expose »* (G-35,
HOS-283). Remesuré le 2026-09-12 : `tools/skill_ledger.py` existe bien chez
l'agent depuis son commit `693641aa8b` (17 aout), et il tient exactement ce
que §10 attendait — un JSONL en ajout seul, une ligne par mutation, avec
avant/apres content-addressed (sha256, deduplique) sous
`.curator_backups/blobs/`. Le fichier lui-meme n'existe simplement pas
encore sur CETTE installation, parce qu'aucune mutation n'a eu lieu depuis
que l'agent le tient.

Ce module en est la **cinquieme lecture** du disque de l'agent — apres les
competences (HOS-274), leur provenance (HOS-275), les mutations observees
(HOS-281) et le dossier du hub (HOS-283) — et la posture ne change pas :
lire, jamais ecrire, ne jamais fabriquer un second magasin.

## Ce que cette passe ADOPTE

**La lecture du ledger, et le diff qu'elle en derive.** Chaque entree porte
`before`/`after` — deux listes de `{path, sha256}` — et ce module calcule
localement, sans importer l'agent, quels fichiers ont ete ajoutes, retires
ou modifies entre les deux. C'est une derivation directe des octets que le
ledger porte, pas une version fabriquee : ni horodatage ni hash de fichier
ne tiennent lieu de version ici, c'est l'entree elle-meme, telle que
l'agent l'a ecrite, qui EST la version.

Verifie sur un `HERMES_HOME` de substitution, avec `tools/skill_ledger.py`
de l'agent important reellement pour ecrire les entrees (pas un JSONL
imite) : creation, edition et suppression produisent chacune une entree
lisible ici a l'identique, et **un nouveau processus retrouve les trois**
apres la fin du premier — persistance et redemarrage acquis, sans copier un
octet dans `hermes.db`.

## Ce que cette passe ne fait PAS

**Le declenchement du rollback reste DEFER**, exactement le motif que G-35
a nomme pour l'installation : `hermes curator rollback <id>` existe cote
agent (`hermes_cli/curator.py:_cmd_rollback`), mais aucune RPC ne l'expose,
et l'invoquer depuis Hermes OS demanderait la meme decision de gouvernance
que G-36 a prise pour la pose — quelle autorite approuve l'ecriture, par
quelle file. Cette passe fournit la lecture qui rend cette decision
possible a prendre plus tard ; elle ne la prend pas elle-meme.

**Pas de creation/edition/suppression pilotee depuis Hermes OS.** Le
ledger n'enregistre QUE des mutations faites par l'agent lui-meme
(`skill_manager_tool`) ou par le CLI curator ; rien ici ne declenche l'une
d'elles.

Reimplemente plutot qu'importe : `plugin_compat` desactive au 2026-09-14
tout code externe qui importe les internes de l'agent. Ce lecteur ne
depend d'aucun module de l'agent, seulement du format JSONL que son
docstring documente comme durable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hermes_os.skills.versioning")

#: Les acteurs que l'agent ecrit (`tools/skill_ledger.py::_VALID_ACTORS`).
#: Toute autre valeur est une entree corrompue ou une future extension,
#: rendue `ACTEUR_INCONNU` plutot que fabriquee.
ACTEURS_VALIDES = frozenset({"curator", "agent", "user"})
ACTEUR_INCONNU = "acteur_inconnu"

#: L'etat d'un fichier entre `before` et `after` d'une entree. Borne, comme
#: les categories de provenance (G-27) et de gouvernance (G-35) : une
#: chaine libre laisserait l'ecran broder sur ce que l'entree ne dit pas.
AJOUTE = "ajoute"
SUPPRIME = "supprime"
MODIFIE = "modifie"
INCHANGE = "inchange"


@dataclass(frozen=True)
class FichierDiff:
    """Un chemin touche par une mutation, et ce qui lui est arrive."""

    chemin: str
    etat: str

    def as_dict(self) -> dict:
        return {"chemin": self.chemin, "etat": self.etat}


@dataclass(frozen=True)
class EntreeVersion:
    """Une ligne du ledger, telle que l'agent l'a ecrite — la version."""

    id: str
    horodatage: str
    acteur: str
    action: str
    skill: str
    fichiers: tuple[FichierDiff, ...]
    #: Renseigne seulement quand l'entree est elle-meme un rollback d'une
    #: autre — `evidence.rollback_target` chez l'agent.
    rollback_de: Optional[str]
    #: Renseigne seulement quand une consolidation a absorbe cette
    #: competence dans une autre — `evidence.absorbed_into` chez l'agent.
    absorbe_dans: Optional[str]

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "horodatage": self.horodatage,
            "acteur": self.acteur,
            "action": self.action,
            "skill": self.skill,
            "fichiers": [f.as_dict() for f in self.fichiers],
            "rollback_de": self.rollback_de,
            "absorbe_dans": self.absorbe_dans,
        }


def _skills() -> Path:
    """Le meme dossier que `registre.lire()` et `provenance.py` — jamais
    recalcule independamment, pour la meme raison qu'eux."""
    from backend.skills.registre import racine_des_competences

    return racine_des_competences()


def ledger_path() -> Path:
    """Le meme chemin que `tools/skill_ledger.py::ledger_path()` chez
    l'agent : `<racine des competences>/.curator_ledger.jsonl`."""
    return _skills() / ".curator_ledger.jsonl"


def _lire_lignes() -> list[dict[str, Any]]:
    """Le JSONL brut, dans l'ordre du fichier (le plus ancien d'abord — il
    est ecrit en ajout seul). Une ligne malformee est ignoree plutot que de
    faire echouer la lecture des autres, meme posture que
    `gouvernance.journal()`."""
    try:
        texte = ledger_path().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lignes: list[dict[str, Any]] = []
    for brute in texte.splitlines():
        brute = brute.strip()
        if not brute:
            continue
        try:
            ligne = json.loads(brute)
        except json.JSONDecodeError:
            logger.debug("ligne de ledger illisible, ignoree", exc_info=True)
            continue
        if isinstance(ligne, dict):
            lignes.append(ligne)
    return lignes


def _diff(before: list[Any], after: list[Any]) -> tuple[FichierDiff, ...]:
    """Ce qui a change entre deux instantanes `{path, sha256}`.

    Derive directement des octets que l'entree porte : un chemin present
    seulement dans `after` est AJOUTE, seulement dans `before` est
    SUPPRIME, present des deux cotes avec une empreinte differente est
    MODIFIE. Rien ici ne vient d'une declaration — c'est pourquoi une
    entree qui ne changerait rien (meme empreinte des deux cotes) rend
    INCHANGE plutot que d'etre confondue avec un ajout.
    """
    avant = {
        str(i.get("path")): str(i.get("sha256", ""))
        for i in before if isinstance(i, dict) and i.get("path")
    }
    apres = {
        str(i.get("path")): str(i.get("sha256", ""))
        for i in after if isinstance(i, dict) and i.get("path")
    }
    resultat = []
    for chemin in sorted(set(avant) | set(apres)):
        dans_avant, dans_apres = chemin in avant, chemin in apres
        if dans_avant and not dans_apres:
            etat = SUPPRIME
        elif dans_apres and not dans_avant:
            etat = AJOUTE
        elif avant[chemin] != apres[chemin]:
            etat = MODIFIE
        else:
            etat = INCHANGE
        resultat.append(FichierDiff(chemin, etat))
    return tuple(resultat)


def _entree(ligne: dict[str, Any]) -> EntreeVersion:
    evidence = ligne.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    acteur = ligne.get("actor")
    return EntreeVersion(
        id=str(ligne.get("id") or ""),
        horodatage=str(ligne.get("ts") or ""),
        acteur=str(acteur) if acteur in ACTEURS_VALIDES else ACTEUR_INCONNU,
        action=str(ligne.get("action") or ""),
        skill=str(ligne.get("skill") or ""),
        fichiers=_diff(ligne.get("before") or [], ligne.get("after") or []),
        rollback_de=(str(evidence["rollback_target"])
                     if evidence.get("rollback_target") else None),
        absorbe_dans=(str(evidence["absorbed_into"])
                      if evidence.get("absorbed_into") else None),
    )


def entrees(skill: Optional[str] = None,
            limite: Optional[int] = None) -> list[EntreeVersion]:
    """Les mutations du ledger, de la plus recente a la plus ancienne.

    `skill` filtre sur le nom exact que l'entree porte — pas de
    resolution de conflit de clef ici, `provenance.py` la fait deja pour
    l'inventaire. `limite` s'applique APRES le filtre et le tri, comme
    `skill_ledger.list_entries()` cote agent.
    """
    lignes = _lire_lignes()
    if skill:
        lignes = [l for l in lignes if l.get("skill") == skill]
    lignes.reverse()
    if limite is not None and limite >= 0:
        lignes = lignes[:limite]
    return [_entree(l) for l in lignes]


def entree(entry_id: str) -> Optional[EntreeVersion]:
    """Une entree par son id, ou `None` — l'id n'existe pas, ou est vide."""
    if not entry_id:
        return None
    for ligne in _lire_lignes():
        if ligne.get("id") == entry_id:
            return _entree(ligne)
    return None


#: Pourquoi `rollback_declenchable` reste `False` partout : voir le
#: docstring de module. Nomme ici plutot qu'en dur dans `vue()` pour qu'un
#: test puisse citer exactement le texte affiche.
ROLLBACK_ABSENT_RAISON = (
    "le declenchement existe cote agent (`hermes curator rollback <id>`), "
    "mais aucune RPC ne l'expose depuis Hermes OS : meme DEFER que G-35 "
    "pour l'installation, faute d'une decision de gouvernance sur quelle "
    "autorite approuverait cette ecriture-ci"
)


def vue(skill: Optional[str] = None, limite: int = 200) -> dict:
    """La vue produit : le versioning des Skills, tel que le ledger de
    l'agent le porte.

    `ledger_lisible` distingue « aucune mutation n'a jamais ete ecrite »
    de « Hermes OS n'a pas su lire le fichier » — meme distinction que
    `dossier_lisible` en gouvernance, pour la meme raison : un ecran vide
    dirait sinon la meme chose dans les deux cas, et le second est une
    panne.
    """
    chemin = ledger_path()
    lignes = entrees(skill=skill, limite=limite)
    return {
        "ledger_lisible": chemin.is_file(),
        "racine": str(chemin),
        "total": len(lignes),
        "entrees": [e.as_dict() for e in lignes],
        "rollback_declenchable": False,
        "rollback_absent_raison": ROLLBACK_ABSENT_RAISON,
    }
