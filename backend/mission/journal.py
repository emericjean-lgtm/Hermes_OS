"""La mémoire d'un projet entre deux lancements (HOS-123).

Un cahier des charges de quarante sections ne se fait pas en une mission.
Il se fait en quarante, et jusqu'ici chacune repartait aveugle : la
douzième ignorait tout de la onzième. Le contexte amont (HOS-121) et le
manifeste (HOS-122) font tenir une mission ensemble ; ils s'évaporent avec
elle.

## La règle qui décide de tout ici

Le cahier Skills360 dit, à propos de son propre `PROJECT_STATUS.md` :

    Ne jamais compléter ce fichier par supposition. Toute information
    ajoutée doit provenir du repository réel, d'un résultat de test réel,
    d'une spécification, ou d'une décision explicitement fournie.
    Si l'information ne peut pas être vérifiée : [À COMPLÉTER]

Un journal rédigé **par le modèle** serait exactement la fabrication que
cette règle interdit — et pire que l'absence de journal, puisque le
lancement suivant le lirait comme un fait établi.

Ce journal n'écrit donc que ce qui a été **mesuré** : le diff du workspace,
le verdict du manifeste, le verdict des tests. Aucune ligne ne vient du
récit d'un modèle. Ce qui n'a pas été mesuré est écrit comme non mesuré.

## Pourquoi un fichier dans le workspace

Parce que la mémoire appartient au projet, pas au processus. Elle survit à
un redémarrage — ce que le registre des missions ne fait pas encore
(HOS-120) — et elle voyage avec le dossier.

`.hermes/` est ajouté aux répertoires ignorés par `verification.py` : sans
ça, une mission qui n'aurait rien fait d'autre qu'écrire son journal
verrait `touched_anything` à vrai et passerait pour productive. Le journal
mesure le travail, il ne doit pas compter comme du travail.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hermes_os.mission.journal")

#: Le journal vit là, pas à la racine : il appartient à l'outil, pas au
#: projet, et il ne doit pas se retrouver dans une revue de code ni dans
#: le manifeste des livrables.
CHEMIN_RELATIF = ".hermes/journal.md"

#: Combien d'entrées passées sont relues et transmises. Assez pour savoir
#: où en est le projet, assez peu pour ne pas repousser les instructions de
#: la tâche hors de la fenêtre — le mur des 64k de CLAUDE.md.
ENTREES_RELUES = 6

_EN_TETE = (
    "# Journal des missions Hermes\n\n"
    "> Écrit automatiquement, **uniquement à partir de mesures** : diff du\n"
    "> workspace, verdict du manifeste, verdict des tests. Aucune ligne ne\n"
    "> vient du récit d'un modèle. Ce qui n'a pas été mesuré est écrit comme\n"
    "> non mesuré.\n"
)

_SEPARATEUR = "\n---\n\n"


def _liste(valeurs: Any, maximum: int = 8) -> str:
    elements = [str(v) for v in (valeurs or [])]
    if not elements:
        return "aucun"
    visibles = ", ".join(sorted(elements)[:maximum])
    reste = len(elements) - maximum
    return f"{visibles} (+{reste})" if reste > 0 else visibles


def _ligne_tests(tests: Optional[dict]) -> str:
    """Les trois états, tels quels.

    « Non lancés » n'est pas « passés ». C'est le défaut que ce dépôt
    traque depuis le début, et l'écrire dans une mémoire persistante le
    ferait durer d'une mission à l'autre.
    """
    if not tests:
        return "non lancés (aucun runner applicable)"
    if not tests.get("ran"):
        raison = str(tests.get("reason") or "").strip() or "non exécuté"
        return f"**non lancés** — {raison}"
    return "passés" if tests.get("passed") else "**en échec**"


def _ligne_manifeste(manifeste: Optional[dict]) -> str:
    if not manifeste:
        return "aucun livrable déclaré"
    if manifeste.get("tenu"):
        return f"{manifeste.get('declares', 0)} livrable(s) déclaré(s), tous présents"
    return (f"**{manifeste.get('nombre_manquants', 0)} livrable(s) annoncé(s) "
            f"et absent(s)** : {_liste(manifeste.get('manquants'))}")


def entree(objectif: str, verification: Any) -> str:
    """Une entrée de journal, à partir du seul verdict mesuré."""
    horodatage = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    changes = getattr(verification, "changes", None)
    mesure = getattr(verification, "measured", False)

    lignes = [f"## {horodatage}", "", f"**Objectif** : {objectif.strip()[:400]}", ""]
    if not mesure:
        lignes += ["Rien n'a été mesuré pour cette mission (aucun workspace lié "
                   "ou instantané impossible). Elle n'est **pas** rapportée "
                   "comme réussie ici.", ""]
        return "\n".join(lignes)

    lignes += [
        f"- Créés : {_liste(getattr(changes, 'created', ()))}",
        f"- Modifiés : {_liste(getattr(changes, 'modified', ()))}",
        f"- Supprimés : {_liste(getattr(changes, 'deleted', ()))}",
        f"- Manifeste : {_ligne_manifeste(getattr(verification, 'manifeste', None))}",
        f"- Tests du livrable : {_ligne_tests(getattr(verification, 'tests', None))}",
        "",
    ]
    if getattr(verification, "contradicted", False):
        lignes += ["> Cette mission s'est annoncée réussie et la mesure la "
                   "contredit. Ne pas repartir de ses conclusions.", ""]
    return "\n".join(lignes)


def ecrire(workspace: Optional[str], objectif: str, verification: Any) -> bool:
    """Ajouter une entrée. Ne lève jamais.

    Un journal qui échoue ne doit pas faire échouer la mission dont il rend
    compte : ce serait faire perdre le travail à cause de sa trace.
    """
    if not workspace or verification is None:
        return False
    try:
        chemin = Path(workspace).expanduser().resolve() / CHEMIN_RELATIF
        chemin.parent.mkdir(parents=True, exist_ok=True)
        existant = chemin.read_text(encoding="utf-8") if chemin.exists() else _EN_TETE
        chemin.write_text(existant + _SEPARATEUR + entree(objectif, verification),
                          encoding="utf-8")
        return True
    except Exception:  # pragma: no cover - dépend du système de fichiers
        logger.debug("journal non écrit pour %r", workspace, exc_info=True)
        return False


def relire(workspace: Optional[str], entrees: int = ENTREES_RELUES) -> Optional[str]:
    """Les dernières entrées, ou `None` s'il n'y en a aucune.

    `None` veut dire « premier passage sur ce projet », ce qui est une
    information — et différent de « les missions précédentes n'ont rien
    fait ».
    """
    if not workspace:
        return None
    try:
        chemin = Path(workspace).expanduser().resolve() / CHEMIN_RELATIF
        if not chemin.is_file():
            return None
        contenu = chemin.read_text(encoding="utf-8")
    except OSError:
        return None

    blocs = [b.strip() for b in contenu.split(_SEPARATEUR.strip()) if b.strip()]
    # Le premier bloc est l'en-tête, pas une entrée.
    blocs = [b for b in blocs if b.startswith("## ")]
    if not blocs:
        return None
    return "\n\n".join(blocs[-entrees:])
