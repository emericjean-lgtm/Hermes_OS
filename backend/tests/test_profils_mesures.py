"""Le routeur doit pouvoir départager les modèles (HOS-144).

HOS-143 avait montré que **toutes** les missions tournaient sur le plus
petit modèle, y compris « écrire les tests unitaires ». HOS-144 en a donné
la cause sans la corriger : le routeur connaît les modèles, mais leurs
profils sont vides. `AdaptiveRouter.recommend()` lit
`profile.task_scores.get(type, 0.5)` — chaque modèle rendait donc le même
neutre, et le départage tombait sur le critère suivant, la taille.

Les mesures existaient dans le magasin de bancs. Rien ne les reliait.

Ces tests portent sur la traduction et sur ses deux refus, qui comptent
autant que la traduction elle-même : un axe non mesuré ne devient pas un
zéro, et une note d'épreuve n'écrase pas une course réelle.
"""

from __future__ import annotations

from backend.model_intelligence.model_intelligence_models import ModelProfile, TaskType
from backend.model_intelligence.profils_mesures import (
    CORRESPONDANCE,
    appliquer,
    notes_en_scores,
)


class _Profileur:
    """Le strict nécessaire : `appliquer` n'appelle que `get_profile`."""

    def __init__(self, *profils: ModelProfile) -> None:
        self._par_nom = {p.model_id: p for p in profils}

    def get_profile(self, model_id: str) -> ModelProfile | None:
        return self._par_nom.get(model_id)


def test_les_notes_passent_de_cent_a_un():
    """Le catalogue note sur 100, le routeur compare sur 1.

    Une conversion oubliée ferait rendre 88 là où le routeur attend une
    valeur entre 0 et 1 : tous les modèles mesurés écraseraient alors le
    neutre 0,5 dans le même ordre de grandeur absurde, et le classement
    n'aurait plus aucun sens.
    """
    scores = notes_en_scores({"code": 88, "raisonnement": 100, "capacite": 50,
                              "extraction": 100, "agentique": 50})
    assert scores[TaskType.CODE_GENERATION.value] == 0.88
    assert scores[TaskType.REASONING.value] == 1.0
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_un_axe_non_mesure_ne_produit_pas_de_score():
    """Le magasin omet les axes non mesurés ; l'écrire à zéro les trahirait.

    Sans score, le routeur retombe sur son neutre 0,5 — « je ne sais pas ».
    Avec un zéro, il conclurait « mauvais », ce que rien n'a établi.
    """
    scores = notes_en_scores({"capacite": 80})

    assert TaskType.CHAT.value in scores, "capacite est mesurée : chat doit exister"
    assert TaskType.CODE_GENERATION.value not in scores
    assert TaskType.REASONING.value not in scores
    # `general` mélange capacite et agentique : une composante manque.
    assert TaskType.GENERAL.value not in scores


def test_un_melange_exige_toutes_ses_composantes():
    """La moyenne d'une note et d'un trou serait une note inventée."""
    partiel = notes_en_scores({"code": 100})
    assert TaskType.CODE_GENERATION.value in partiel, "code seul suffit pour l'écriture"
    assert TaskType.DEBUG.value not in partiel, "debug mélange code et raisonnement"

    complet = notes_en_scores({"code": 100, "raisonnement": 0})
    assert complet[TaskType.DEBUG.value] == 0.5, "moyenne de 100 et 0"


def test_une_note_zero_reste_une_note():
    """Zéro mesuré n'est pas la même chose que non mesuré.

    `lfm2.5-vl-3b-125k` porte `raisonnement: 0` dans le catalogue réel :
    c'est un résultat, pas une absence, et il doit produire un score.
    """
    scores = notes_en_scores({"raisonnement": 0})
    assert scores[TaskType.REASONING.value] == 0.0


def test_le_routeur_peut_enfin_departager():
    """Le défaut de HOS-143, renversé.

    Deux modèles que le routeur ne distinguait pas — même 0,5 partout —
    doivent désormais rendre des scores différents sur la génération de
    code. Les notes ci-dessous sont celles du catalogue réel.
    """
    fort = ModelProfile(model_id="gpt-oss-20b-64k", name="gpt-oss-20b-64k")
    faible = ModelProfile(model_id="lfm2.5-2.6b-125k", name="lfm2.5-2.6b-125k")

    bilan = appliquer(_Profileur(fort, faible), [
        {"model": "gpt-oss-20b-64k", "notes": {"code": 100, "raisonnement": 100}},
        {"model": "lfm2.5-2.6b-125k", "notes": {"code": 28, "raisonnement": 75}},
    ])

    assert bilan["profils"] == 2
    cle = TaskType.CODE_GENERATION.value
    assert fort.task_scores[cle] > faible.task_scores[cle], (
        "le routeur ne peut toujours pas départager : c'est exactement "
        "l'état qui faisait tourner toutes les missions sur le plus petit "
        "modèle"
    )
    assert fort.task_scores[cle] == 1.0
    assert faible.task_scores[cle] == 0.28


def test_une_course_reelle_garde_la_main_sur_une_note_de_catalogue():
    """`benchmark_scheduler` écrit depuis l'exécution effective d'une tâche.

    C'est une preuve plus directe qu'une épreuve synthétique. L'écraser
    reviendrait à préférer le laboratoire au terrain.
    """
    profil = ModelProfile(model_id="m", name="m")
    profil.task_scores[TaskType.CODE_GENERATION.value] = 0.2  # mesuré en course

    appliquer(_Profileur(profil), [{"model": "m", "notes": {"code": 100}}])
    assert profil.task_scores[TaskType.CODE_GENERATION.value] == 0.2

    appliquer(_Profileur(profil), [{"model": "m", "notes": {"code": 100}}],
              remplacer=True)
    assert profil.task_scores[TaskType.CODE_GENERATION.value] == 1.0


def test_un_modele_mesure_sans_profil_est_compte_et_non_avale():
    """Un catalogue qui ne rencontre aucun profil ne change rien.

    Sans ce compte, le pont pourrait ne rien faire du tout et le journal
    afficherait le même silence que lorsqu'il fonctionne.
    """
    bilan = appliquer(_Profileur(), [{"model": "absent", "notes": {"code": 90}}])
    assert bilan == {"profils": 0, "scores": 0, "sans_profil": 1}


def test_chaque_type_de_tache_du_routeur_a_une_correspondance():
    """Un type oublié rendrait éternellement le neutre 0,5.

    Le défaut serait invisible : le routeur fonctionnerait, en ignorant
    simplement cette tâche-là dans son classement.
    """
    manquants = [t for t in TaskType if t not in CORRESPONDANCE]
    assert not manquants, f"types sans axe de référence : {manquants}"
