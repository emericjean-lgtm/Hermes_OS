"""Verser les notes mesurées dans les profils du routeur (HOS-144).

## Le constat, et ce qui manquait

HOS-143 a montré que toutes les missions tournaient sur le plus petit
modèle. HOS-144 en a donné la cause : le routeur connaît les modèles du
catalogue, mais leurs profils sont **vides** — `task_scores={}`,
`benchmark_score=0.0`, `total_runs=0`. `AdaptiveRouter.recommend()` lit
`profile.task_scores.get(type, 0.5)`, donc chaque modèle rendait le même
neutre, et le départage tombait sur le critère suivant : la taille.

Les mesures existaient pourtant. Elles vivent dans le magasin de bancs —
sept axes notés de 0 à 100 par modèle, produits par
`agentic_probe.py` et `code_bench.py`. Rien ne les reliait au routeur.

Ce module est ce lien, et rien d'autre : il ne mesure pas, il ne classe
pas, il traduit.

## Ce qu'il refuse de faire

**Un axe non mesuré ne produit pas de score.** Le magasin omet
délibérément les axes absents plutôt que de les mettre à zéro ; écrire
`0.0` ici anéantirait cette précaution et ferait passer « non mesuré »
pour « nul ». Sans score, le routeur retombe sur son neutre 0,5, qui dit
« je ne sais pas » — la seule chose vraie.

**Une note de catalogue n'écrase pas une course réelle.**
`benchmark_scheduler` écrit `task_scores[type]` depuis l'exécution
effective d'une tâche. C'est une preuve plus directe qu'une note d'épreuve
synthétique, et elle garde la main : par défaut ce module ne remplit que
les cases vides.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

from .model_intelligence_models import TaskType

logger = logging.getLogger("hermes_os.model_intelligence.profils")

#: Quel axe mesuré répond de quel type de tâche.
#:
#: Les mélanges sont un choix, pas une découverte : rien ne mesure
#: « déboguer » en tant que tel. Déboguer demande de lire du code et de
#: raisonner sur ce qu'on lit, d'où la moyenne des deux. Écrire du code
#: neuf demande d'abord de savoir en écrire, d'où l'axe seul.
#:
#: Un mélange n'est retenu que si **toutes** ses composantes sont
#: mesurées : la moyenne d'une note et d'un trou serait une note inventée.
CORRESPONDANCE: dict[TaskType, tuple[str, ...]] = {
    TaskType.CODE_GENERATION: ("code",),
    TaskType.REFACTOR: ("code",),
    TaskType.CODE_REVIEW: ("code", "raisonnement"),
    TaskType.DEBUG: ("code", "raisonnement"),
    TaskType.OPTIMIZATION: ("code", "raisonnement"),
    TaskType.ANALYSIS: ("extraction", "raisonnement"),
    TaskType.REASONING: ("raisonnement",),
    TaskType.DOCUMENTATION: ("capacite",),
    TaskType.CHAT: ("capacite",),
    TaskType.GENERAL: ("capacite", "agentique"),
}


def notes_en_scores(notes: Mapping[str, Any]) -> dict[str, float]:
    """Sept axes sur 100 → des scores de tâche sur 1.

    Le routeur compare des valeurs entre 0 et 1 et prend 0,5 pour défaut ;
    le catalogue note sur 100. La conversion est ici et nulle part
    ailleurs, pour qu'un changement d'échelle d'un côté n'oblige pas à
    fouiller l'autre.
    """
    scores: dict[str, float] = {}
    for tache, axes in CORRESPONDANCE.items():
        valeurs = []
        for axe in axes:
            brut = notes.get(axe)
            if brut is None:
                break
            try:
                valeurs.append(float(brut))
            except (TypeError, ValueError):
                break
        else:
            scores[tache.value] = round(sum(valeurs) / len(valeurs) / 100.0, 4)
    return scores


def appliquer(
    profiler: Any,
    catalogue: Iterable[Mapping[str, Any]],
    *,
    remplacer: bool = False,
) -> dict[str, int]:
    """Remplir les profils depuis le catalogue mesuré.

    Rend un compte-rendu — profils touchés, scores écrits, modèles du
    catalogue sans profil correspondant. Le dernier chiffre est celui qui
    mérite qu'on le regarde : un catalogue qui ne rencontre aucun profil
    laisse le routeur exactement où il était, et sans ce compte rien ne le
    dirait.
    """
    bilan = {"profils": 0, "scores": 0, "sans_profil": 0}

    for entree in catalogue:
        nom = str(entree.get("model") or entree.get("name") or "")
        notes = entree.get("notes") or {}
        if not nom or not notes:
            continue

        profil = profiler.get_profile(nom)
        if profil is None:
            bilan["sans_profil"] += 1
            continue

        ecrits = 0
        for cle, valeur in notes_en_scores(notes).items():
            if not remplacer and cle in profil.task_scores:
                # Une course réelle a déjà répondu pour cette tâche.
                continue
            profil.task_scores[cle] = valeur
            ecrits += 1

        if ecrits:
            bilan["profils"] += 1
            bilan["scores"] += ecrits

    if bilan["sans_profil"]:
        logger.info(
            "catalogue : %d modèle(s) mesuré(s) sans profil correspondant — "
            "leurs notes ne servent à rien tant que le profil n'existe pas",
            bilan["sans_profil"],
        )
    return bilan


def appliquer_depuis_le_magasin(profiler: Any, *, remplacer: bool = False) -> dict[str, int]:
    """Le même travail, en allant chercher le catalogue soi-même.

    Enveloppé dans un `try` parce que le magasin de bancs est une base
    SQLite qui peut manquer sur une installation neuve. Un routeur sans
    notes fonctionne — mal, mais il fonctionne ; un démarrage qui échoue
    parce qu'aucune mesure n'a encore été prise serait pire.
    """
    try:
        from .bench_score import noter_modele
        from .bench_store import BenchStore

        # Le magasin rend les lignes brutes par axe ; c'est `noter_modele`
        # qui les reduit a une note. Lire directement `entree["notes"]`
        # rendait un catalogue vide sans rien dire — la forme servie par
        # `/models/catalogue` n'est pas la forme stockee.
        catalogue = [
            {"model": e["model"], "notes": noter_modele(e["axes"])}
            for e in BenchStore().catalogue()
        ]
        return appliquer(profiler, catalogue, remplacer=remplacer)
    except Exception:
        logger.debug("magasin de bancs indisponible", exc_info=True)
        return {"profils": 0, "scores": 0, "sans_profil": 0}
