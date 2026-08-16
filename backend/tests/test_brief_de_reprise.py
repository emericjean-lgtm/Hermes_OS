"""Le brief de reprise doit décrire l'échec réel (HOS-125).

L'incident, mesuré le 2026-08-16 sur l'essai à deux étapes. L'étape 1 a
écrit trois fichiers, quatre de ses tests échouaient, deux livrables
annoncés manquaient. La reprise s'est déclenchée — et a produit

    - Créés : aucun

Le brief était écrit en dur pour un seul cas, celui pour lequel il avait
été conçu (HOS-099, la mission n'avait rien touché) :

    this task was already attempted and did not take effect.
    After that attempt, {workspace} was unchanged: …

Trois autres contradictions existent depuis — tests en échec (HOS-119),
livrable annoncé et absent (HOS-122), boucle d'import fatale (HOS-124) — et
le brief continuait d'annoncer « inchangé » sur un workspace qui avait
changé. On disait au modèle « rien ne s'est passé, écris les fichiers » ; il
a regardé, les a trouvés là, et n'a rien écrit. **Il a fait exactement ce
qu'on lui demandait.**

Un brief qui décrit mal l'échec ne vaut pas mieux qu'un rapport qui le
cache. C'est la même faute, un cran plus loin dans la boucle.
"""
from __future__ import annotations

from backend.mission.retry_policy import build_retry_brief, decide


def _verif(**champs) -> dict:
    base = {"measured": True, "contradicted": True, "workspace": "/w",
            "created": [], "modified": [], "deleted": [],
            "summary": "no file was created, modified or deleted"}
    base.update(champs)
    return base


class TestLIncidentMesure:
    def test_un_workspace_qui_a_change_n_est_plus_dit_inchange(self):
        """Le mensonge exact : trois fichiers écrits, et le brief affirmait
        que rien n'avait pris effet."""
        brief = build_retry_brief("objectif", _verif(
            created=["identity_model.py", "tests/test_identity_model.py"],
            summary="2 created: identity_model.py, tests/test_identity_model.py",
            tests={"ran": True, "passed": False, "exit_code": 1,
                   "runner": "pytest", "output": "4 failed"}))

        assert "was unchanged" not in brief
        assert "did not take effect" not in brief

    def test_la_sortie_reelle_des_tests_est_transmise(self):
        """« Corrige ce qu'elle rapporte, ne devine pas. » Sans l'erreur, la
        seconde tentative repart aussi aveugle que la première."""
        brief = build_retry_brief("objectif", _verif(
            created=["a.py"], summary="1 created: a.py",
            tests={"ran": True, "passed": False, "exit_code": 1,
                   "runner": "pytest",
                   "output": "E   AssertionError: assert 'three distinct "
                             "entities' in 'SECTION 6'"}))

        assert "AssertionError" in brief
        assert "SECTION 6" in brief
        assert "do not guess" in brief

    def test_les_livrables_manquants_sont_nommes(self):
        brief = build_retry_brief("objectif", _verif(
            created=["a.py"], summary="1 created: a.py",
            manifeste={"declares": 3, "manquants": ["docs/decisions.md"],
                       "tenu": False}))

        assert "docs/decisions.md" in brief

    def test_une_boucle_d_import_est_nommee(self):
        brief = build_retry_brief("objectif", _verif(
            created=["a.py"], summary="1 created: a.py",
            imports={"cycles": ["a -> b -> a"], "fatals": ["a -> b -> a"]}))

        assert "a -> b -> a" in brief
        assert "compile" in brief, (
            "le modèle doit comprendre que ses fichiers sont syntaxiquement "
            "corrects — sinon il cherchera l'erreur au mauvais endroit")

    def test_plusieurs_causes_apparaissent_toutes(self):
        """La reprise mesurée en avait deux à la fois."""
        brief = build_retry_brief("objectif", _verif(
            created=["a.py"], summary="1 created: a.py",
            manifeste={"manquants": ["docs/decisions.md"], "tenu": False},
            tests={"ran": True, "passed": False, "exit_code": 1,
                   "runner": "pytest", "output": "4 failed"}))

        assert "docs/decisions.md" in brief
        assert "FAILED" in brief


class TestLeCasDOrigineNeRegressePas:
    def test_un_workspace_reellement_vide_le_dit_encore(self):
        """HOS-099 reste couvert : c'est le cas pour lequel ce brief a été
        écrit, et il n'a pas cessé d'exister."""
        brief = build_retry_brief("objectif", _verif())

        assert "was unchanged" in brief
        assert "A description of the work is not the work" in brief

    def test_l_objectif_reste_en_tete(self):
        """Le modèle est réinterrogé sur le même travail : sans l'objectif,
        la reprise devient une consigne de correction hors sol."""
        brief = build_retry_brief("Écrire le modèle d'identité", _verif())

        assert brief.startswith("Écrire le modèle d'identité")


class TestOnNInventeAucuneCause:
    def test_une_contradiction_sans_cause_nommable_le_dit(self):
        """Plutôt que de fabriquer une explication plausible — c'est
        exactement ce que ce dépôt reproche aux rapports de mission."""
        brief = build_retry_brief("objectif", _verif(
            created=["a.py"], summary="1 created: a.py"))

        assert "without naming a specific cause" in brief


class TestLeMotifSuitLaCause:
    """Le motif voyage dans le journal et les événements ; il répétait
    « the workspace did not change » quel que soit l'échec réel."""

    def test_des_tests_en_echec_donnent_leur_propre_motif(self):
        decision = decide(_verif(
            created=["a.py"],
            tests={"ran": True, "passed": False, "exit_code": 1}),
            objective="o", attempts_made=1)

        assert decision.should_retry
        assert "tests fail" in decision.reason

    def test_un_livrable_manquant_aussi(self):
        decision = decide(_verif(
            created=["a.py"], manifeste={"manquants": ["x.md"], "tenu": False}),
            objective="o", attempts_made=1)

        assert "deliverables are missing" in decision.reason

    def test_le_workspace_vide_garde_le_sien(self):
        decision = decide(_verif(), objective="o", attempts_made=1)

        assert "did not change" in decision.reason
