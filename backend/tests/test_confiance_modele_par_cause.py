"""Ne pas juger un modèle sur un échec qui n'est pas le sien (HOS-231).

## Deux faits mesurés avant d'écrire

- `ModelPerformanceRecord.error_type` existe depuis HOS-062 et **n'est
  renseigné par personne**. Deux modules le relisent ; aucun ne l'écrit.
- `ModelProfiler.update_performance` compte `success=False` dans
  `historical_success_rate` **quelle qu'en soit la raison**. Un refus
  d'admission VRAM, un quota épuisé, une coupure réseau et une mauvaise
  réponse abaissaient identiquement la note du modèle.

C'est le thème central du dépôt appliqué à sa propre télémétrie : *ni un
échec sur parole*. Sur huit défauts de mesure trouvés pendant la
construction du catalogue, **cinq produisaient de faux échecs**.
"""

from __future__ import annotations

import pytest

from backend.model_intelligence.model_intelligence_models import (
    ModelArchitecture,
    ModelPerformanceRecord,
    ModelProfile,
    Quantization,
    TaskType,
)
from backend.model_intelligence.model_profiler import (
    CAUSES_IMPUTABLES_AU_MODELE,
    ModelProfiler,
)


@pytest.fixture
def profileur() -> ModelProfiler:
    p = ModelProfiler()
    p.register_model(ModelProfile(
        model_id="m", name="M", architecture=ModelArchitecture.OTHER,
        vram_required_mb=100, context_window=8192, available_backends=[],
        recommended_quantization=Quantization.NONE))
    # Une réussite d'abord : sans elle, un taux à 0 ne prouverait rien.
    p.update_performance(ModelPerformanceRecord(
        model_id="m", task_type=TaskType.REASONING, duration_ms=10,
        tokens_used=5, success=True))
    return p


def _echec(profileur: ModelProfiler, cause: str) -> ModelProfile:
    profileur.update_performance(ModelPerformanceRecord(
        model_id="m", task_type=TaskType.REASONING, duration_ms=10,
        tokens_used=5, success=False, error_type=cause))
    return profileur.get_profile("m")


# ═══ Ce qui ne doit pas compter contre le modèle ═════════════════════

@pytest.mark.parametrize("cause", [
    "ressource", "quota", "fournisseur", "outil", "politique", "securite",
])
def test_un_echec_d_infrastructure_ne_baisse_pas_la_note(profileur, cause):
    """Un modèle qui n'a pas pu tourner parce que la carte était pleine
    n'est pas un modèle qui a échoué."""
    profil = _echec(profileur, cause)
    assert profil.historical_success_rate == 1.0
    assert profil.total_runs == 1


def test_une_fenetre_fermee_ne_baisse_pas_la_note(profileur):
    """Le cas le mieux documenté du dépôt.

    CLAUDE.md : « une réponse tronquée n'est pas une erreur de
    raisonnement et ne doit pas se noter comme telle ». Le départage de
    code a coupé qwen3.6-35b en plein milieu et l'a noté comme une faute,
    alors que c'était le réglage de la fenêtre qui était en cause.
    """
    assert _echec(profileur, "contexte").historical_success_rate == 1.0


def test_une_cause_inconnue_ne_baisse_pas_la_note(profileur):
    """Attribuer au modèle ce qu'on n'a pas su expliquer est exactement
    la façon dont on a déjà disqualifié des modèles compétents.

    Sur huit défauts de mesure trouvés pendant la construction du
    catalogue, cinq produisaient de faux échecs.
    """
    assert _echec(profileur, "inconnue").historical_success_rate == 1.0


# ═══ Ce qui doit compter ═════════════════════════════════════════════

@pytest.mark.parametrize("cause", ["modele", "semantique", "verification"])
def test_un_echec_du_modele_baisse_la_note(profileur, cause):
    """Sinon la note ne dirait plus rien du tout.

    Une table qui n'imputerait rien rendrait tous les modèles
    équivalents, ce qui est le symétrique du défaut corrigé.
    """
    profil = _echec(profileur, cause)
    assert profil.total_runs == 2
    assert profil.historical_success_rate == 0.5


def test_la_table_des_causes_imputables_est_courte():
    """Le reste décrit la machine, le réseau ou une décision humaine —
    jamais la compétence de ce qui a été appelé."""
    assert CAUSES_IMPUTABLES_AU_MODELE == {"modele", "semantique",
                                           "verification"}


def test_une_cause_absente_compte_comme_avant(profileur):
    """Une chaîne **vide** signifie « personne n'a transmis de cause ».

    C'est un appelant d'avant ce jalon, et son comportement doit être
    conservé — sinon la réparation ferait disparaître en silence toutes
    les notes d'échec des producteurs non migrés.
    """
    profil = _echec(profileur, "")
    assert profil.total_runs == 2
    assert profil.historical_success_rate == 0.5


def test_vide_et_inconnue_ne_disent_pas_la_meme_chose(profileur):
    """« Pas transmise » et « cherchée sans être trouvée » sont deux
    états, et seul le second signifie qu'on a regardé."""
    avant = _echec(profileur, "inconnue").total_runs
    apres = _echec(profileur, "").total_runs
    assert apres == avant + 1


# ═══ La trace reste complète ═════════════════════════════════════════

def test_tous_les_echecs_restent_dans_l_historique(profileur):
    """L'échec a eu lieu : c'est le **jugement** qui est étroit, pas la
    trace.

    Un historique amputé rendrait impossible de savoir qu'un modèle
    tombe systématiquement sur des refus de VRAM — ce qui est une
    information réelle, sur autre chose que sa compétence.
    """
    for cause in ("ressource", "quota", "contexte", "modele"):
        _echec(profileur, cause)
    historique = profileur.get_performance_history("m")
    assert len(historique) == 5
    assert {h["error_type"] for h in historique} >= {"ressource", "contexte"}


def test_la_vitesse_ne_se_mesure_que_sur_les_reussites(profileur):
    """Comportement d'avant, laissé intact.

    Un échec ne porte ni jetons ni durée exploitables, et l'inclure
    fabriquerait une moyenne à partir de rien.
    """
    avant = profileur.get_profile("m").tokens_per_second
    _echec(profileur, "modele")
    assert profileur.get_profile("m").tokens_per_second == avant


# ═══ La cause arrive jusque-là ═══════════════════════════════════════

def test_l_executeur_classe_la_cause_avant_de_la_remonter():
    """`error_type` existait depuis HOS-062 et personne ne l'écrivait."""
    from backend.execution.task_executor import _cause_de

    assert _cause_de(RuntimeError("no VRAM admission for 'x'")) == "ressource"
    assert _cause_de(RuntimeError("runtime 'x' timed out after 900s")) == "fournisseur"
    assert _cause_de(RuntimeError("KeyError: 'z'")) == "inconnue"


def test_chaque_site_d_echec_transmet_une_cause():
    """Un site oublié laisserait passer des échecs non classés, et le
    profileur les compterait comme avant — sans que rien le dise."""
    import ast
    import inspect

    from backend.execution import task_executor

    source = inspect.getsource(task_executor.RealTaskExecutor.execute)
    appels = [n for n in ast.walk(ast.parse(source.strip()))
              if isinstance(n, ast.Call)
              and ast.unparse(n.func).endswith("_report_execution")]
    echecs = [a for a in appels
              if any(isinstance(x, ast.Constant) and x.value is False
                     for x in a.args)]
    assert echecs, "aucun site d'échec trouvé — la garde serait vide"
    for appel in echecs:
        assert any(k.arg == "cause" for k in appel.keywords), ast.unparse(appel)


def test_le_resolveur_passe_la_cause_au_profileur():
    import ast
    import inspect
    import textwrap

    from backend.core.bootstrap import service_registry

    source = inspect.getsource(service_registry._make_task_executor)
    interne = next(n for n in ast.walk(ast.parse(textwrap.dedent(source)))
                   if isinstance(n, ast.FunctionDef)
                   and n.name == "_record_feedback")
    assert "cause" in {a.arg for a in interne.args.args}
    assert "error_type=cause" in ast.unparse(interne)


def test_un_rappel_d_avant_le_jalon_ne_casse_pas():
    """Le rappel est injecté, et un appelant qui n'accepte pas la cause
    ne doit pas devenir une erreur d'exécution.

    C'est la règle de toute la télémétrie de ce module : elle ne fait
    jamais échouer le travail qu'elle décrit.
    """
    from types import SimpleNamespace

    from backend.execution.task_executor import RealTaskExecutor

    recu = []

    def ancien(task, model, duration_ms, tokens_used, success):
        recu.append(success)

    executeur = RealTaskExecutor(on_execution=ancien)
    executeur._report_execution(SimpleNamespace(task_id="t"), "m", 10.0, 5,
                                False, cause="ressource")
    assert recu == [False]
