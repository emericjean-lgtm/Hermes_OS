"""Un cahier des charges se déroule, il ne se lance pas (HOS-127).

Mesuré : les quarante sections de Skills360 données d'un coup produisent
**un fichier de 176 lignes**, 10 concepts sur 18, et zéro marqueur
`À DÉCIDER` — alors que la même règle tenait à 26 marqueurs quand une seule
section était demandée. Une section, elle, produit un résultat `verifiee`
en 390 secondes.

Ce module découpe, classe, et enchaîne. Deux heuristiques y ont déjà été
prises en défaut par la mesure, et les deux tests correspondants les
empêchent de revenir.
"""
from __future__ import annotations

from backend.mission.programme import (
    Etape, Section, bilan, bloc_de_regles, bloquant, brief_de_section,
    classer, concepts_du_cahier, decouper, derouler, ecrire_plan, lire_plan,
)

_CAHIER = """\
# 1. IDENTITÉ

Un projet.

# 4. RÈGLE CONTRE L'INVENTION

Ne jamais inventer une règle métier.

# 6. MODÈLE D'IDENTITÉ

```text
Auth
  ↓
User
  ↓
Employee
```

# 30. MODÈLE DE DONNÉES

```text
Auth
User
Employee
Workshop
```
"""


class TestLeDecoupage:
    def test_les_sections_sont_dans_l_ordre_du_document(self):
        """L'ordre du document est l'ordre des dépendances ; en inventer un
        autre serait exactement ce que le §4 interdit."""
        assert [s.numero for s in decouper(_CAHIER)] == [1, 4, 6, 30]

    def test_une_section_courte_et_dense_n_est_pas_ecartee(self):
        """La première version filtrait sous 400 caractères. Mesuré sur le
        vrai cahier, ce filtre était **à l'envers** : il jetait §6
        (identité), §9 (ateliers), §11 (postes) — courtes parce qu'écrites
        en schémas — et gardait §4 « RÈGLE CONTRE L'INVENTION » et §34
        « MATRICE DE VÉRITÉ », deux pages qui ne construisent rien. La
        longueur mesure le bavardage, pas la matière."""
        sections = decouper(_CAHIER)

        assert 6 in [s.numero for s in sections]
        assert len(next(s for s in sections if s.numero == 6).corps) < 400

    def test_les_sous_titres_ne_coupent_pas(self):
        cahier = "# 1. A\n\ntexte\n\n## Sous-partie\n\nsuite\n\n# 2. B\n\nfin\n"

        sections = decouper(cahier)

        assert len(sections) == 2
        assert "Sous-partie" in sections[0].corps


class TestLeClassement:
    def test_les_concepts_viennent_du_cahier_lui_meme(self):
        """Pas d'une liste que j'aurais écrite : c'est le cahier qui dit ce
        qu'il contient."""
        assert concepts_du_cahier(decouper(_CAHIER)) == {
            "Auth", "User", "Employee", "Workshop"}

    def test_une_section_qui_nomme_une_entite_est_a_construire(self):
        a_construire, _ = classer(decouper(_CAHIER))

        assert 6 in [s.numero for s in a_construire]

    def test_une_regle_de_travail_n_a_pas_de_mission_propre(self):
        """Douze missions de dix minutes pour produire de la paraphrase."""
        _, regles = classer(decouper(_CAHIER))

        assert 4 in [s.numero for s in regles]

    def test_sans_modele_de_donnees_tout_est_a_construire(self):
        """Mieux vaut une mission de trop qu'une règle silencieusement
        transformée en livrable."""
        a_construire, regles = classer(decouper("# 1. A\n\nx\n\n# 2. B\n\ny\n"))

        assert len(a_construire) == 2 and regles == []


class TestLePlanSeRelitAvantDeLancer:
    """Le classement automatique se trompe — mesuré à environ 30 % sur le
    vrai cahier : « CONFORMITÉ », « ALERTES », « API » et « BACKEND »
    classés en règles, « OBJECTIF FINAL » en livrable. Une classification
    silencieusement fausse ferait sauter un quart du cahier."""

    def test_sans_plan_on_ne_deroule_rien(self, tmp_path):
        """`None` veut dire « personne n'a encore regardé », pas « rien à
        faire »."""
        assert lire_plan(tmp_path / "absent.md") is None

    def test_le_plan_ecrit_propose_et_n_impose_pas(self, tmp_path):
        sections = decouper(_CAHIER)
        a_construire, _ = classer(sections)

        texte = ecrire_plan(tmp_path / "plan.md", sections, a_construire)

        assert "À relire avant de lancer" in texte
        assert "- [x] §6" in texte
        assert "- [ ] §4" in texte

    def test_les_corrections_a_la_main_font_foi(self, tmp_path):
        chemin = tmp_path / "plan.md"
        chemin.write_text("- [ ] §6 — a\n- [x] §4 — b\n- [X] §30 — c\n",
                          encoding="utf-8")

        assert lire_plan(chemin) == {4, 30}

    def test_les_regles_sont_recopiees_et_non_resumees(self):
        """Résumer une règle de spécification, c'est la réécrire."""
        _, regles = classer(decouper(_CAHIER))

        bloc = bloc_de_regles(regles)

        assert "Ne jamais inventer une règle métier." in bloc


class TestCeQuiArreteLaFile:
    """La décision de conception de ce module, et elle vient d'une mesure :
    l'étape 1 du dernier essai était `contredite` **uniquement** parce
    qu'elle avait déclaré `docs/identity_design.md` et écrit
    `docs/decisions.md` — ses tests passaient."""

    def _v(self, **champs) -> dict:
        base = {"created": ["a.py"], "modified": [], "deleted": [],
                "contradicted": False}
        base.update(champs)
        return base

    def test_des_tests_en_echec_arretent_tout(self):
        """Trente sections s'appuieraient dessus."""
        arret, raison = bloquant(self._v(
            contradicted=True, tests={"ran": True, "passed": False}))

        assert arret and "tests" in raison

    def test_une_boucle_d_import_fatale_aussi(self):
        arret, raison = bloquant(self._v(
            contradicted=True, imports={"fatals": ["a -> b -> a"]}))

        assert arret and "a -> b -> a" in raison

    def test_rien_d_ecrit_arrete_aussi(self):
        arret, raison = bloquant(self._v(created=[], contradicted=True))

        assert arret and "aucun fichier" in raison

    def test_un_nom_de_livrable_qui_diverge_n_arrete_pas(self):
        """Le cas mesuré. Arrêter une nuit entière pour un nom de fichier
        serait absurde."""
        arret, raison = bloquant(self._v(
            contradicted=True,
            manifeste={"manquants": ["docs/identity_design.md"], "tenu": False},
            tests={"ran": True, "passed": True}))

        assert arret is False
        assert "docs/identity_design.md" in raison, "mais ça doit être dit"

    def test_une_contradiction_sans_cause_arrete(self):
        """Ne pas savoir pourquoi n'est pas une raison de continuer."""
        arret, raison = bloquant(self._v(contradicted=True))

        assert arret and "sans cause" in raison

    def test_l_absence_de_mesure_n_arrete_pas(self):
        """L'absence de mesure n'est pas une preuve d'échec — la règle
        appliquée partout ailleurs ici."""
        assert bloquant(None) == (False, "")


class TestLeDeroulement:
    def _section(self, n: int) -> Section:
        return Section(numero=n, titre=f"S{n}", corps="corps")

    def test_les_sections_s_enchainent(self):
        vues = []

        def lancer(section):
            vues.append(section.numero)
            return {"qualite": "verifiee",
                    "verification": {"created": ["a.py"], "contradicted": False}}

        etapes = derouler([self._section(1), self._section(2)], lancer=lancer)

        assert vues == [1, 2]
        assert [e.statut for e in etapes] == ["faite", "faite"]

    def test_une_etape_bloquante_ignore_la_suite(self):
        """Construire les postes sur une identité cassée propage l'erreur
        sur trente sections."""
        def lancer(section):
            if section.numero == 1:
                return {"verification": {"created": ["a.py"], "contradicted": True,
                                         "tests": {"ran": True, "passed": False}}}
            raise AssertionError("la suite ne doit pas être lancée")

        etapes = derouler([self._section(1), self._section(2)], lancer=lancer)

        assert etapes[0].statut == "bloquee"
        assert etapes[1].statut == "ignoree"

    def test_une_etape_signalee_n_arrete_pas(self):
        def lancer(section):
            return {"verification": {
                "created": ["a.py"], "contradicted": True,
                "tests": {"ran": True, "passed": True},
                "manifeste": {"manquants": ["x.md"], "tenu": False}}}

        etapes = derouler([self._section(1), self._section(2)], lancer=lancer)

        assert [e.statut for e in etapes] == ["signalee", "signalee"]

    def test_une_exception_ne_perd_pas_les_etapes_precedentes(self):
        """Une file de quarante missions qui tombe sur la trente-deuxième
        doit rendre les trente et une premières."""
        def lancer(section):
            if section.numero == 2:
                raise RuntimeError("ollama injoignable")
            return {"verification": {"created": ["a.py"], "contradicted": False}}

        etapes = derouler([self._section(i) for i in (1, 2, 3)], lancer=lancer)

        assert etapes[0].statut == "faite"
        assert etapes[1].statut == "bloquee"
        assert "ollama injoignable" in etapes[1].detail
        assert etapes[2].statut == "ignoree"


class TestLeBrief:
    def test_la_section_est_recopiee_mot_pour_mot(self):
        """Le modèle ne doit pas avoir à retrouver dans 23 Ko la partie qui
        le concerne, et un résumé de ma part serait une réécriture de la
        spécification."""
        section = Section(numero=6, titre="MODÈLE D'IDENTITÉ",
                          corps="Auth puis User puis Employee.")

        brief = brief_de_section(section, nom_du_cahier="SPEC.md")

        assert "Auth puis User puis Employee." in brief
        assert "§6" in brief
        assert "SPEC.md" in brief

    def test_les_regles_permanentes_y_sont_jointes(self):
        section = Section(numero=6, titre="T", corps="Auth.")

        brief = brief_de_section(section, nom_du_cahier="SPEC.md",
                                 regles="Ne jamais inventer.")

        assert "Ne jamais inventer." in brief

    def test_il_dit_de_regarder_l_existant(self):
        """C'est ce qui distingue une file d'une suite de missions
        indépendantes."""
        brief = brief_de_section(Section(6, "T", "Auth."), nom_du_cahier="S.md")

        assert "ne le réécris pas" in brief


class TestLeBilan:
    def test_il_nomme_l_endroit_de_l_arret(self):
        etapes = [Etape(Section(1, "A", "x"), statut="faite"),
                  Etape(Section(2, "B", "x"), statut="bloquee",
                        detail="les tests du livrable échouent"),
                  Etape(Section(3, "C", "x"), statut="ignoree")]

        resultat = bilan(etapes)

        assert resultat["arret"]["section"] == "§2 B"
        assert "tests" in resultat["arret"]["raison"]
        assert resultat["par_statut"] == {"faite": 1, "bloquee": 1, "ignoree": 1}

    def test_sans_arret_il_le_dit(self):
        resultat = bilan([Etape(Section(1, "A", "x"), statut="faite")])

        assert resultat["arret"] is None


class TestUneMissionQuiNAPasEuLieu:
    """L'incident de la première file réelle (HOS-128).

    26 sections, `{"faite": 26}`, **0 seconde**, zéro fichier sur le disque.

    Les objectifs refusaient de démarrer — le dossier n'était pas autorisé,
    le lanceur ne posait pas `ALLOWED_PATHS` — chacun rendait
    `status: failed` et un rapport vide. `bloquant()` recevait donc
    `verification = None` et répondait « rien à signaler », au motif que
    l'absence de mesure n'est pas une preuve d'échec.

    C'est vrai d'une mission qui a **tourné** sans workspace lié. C'est
    faux d'une mission qui n'a jamais eu lieu. Les deux se présentaient de
    la même façon, et j'ai raisonné sur la première en oubliant la seconde
    — produisant le faux succès exact que ce module est chargé de
    détecter.
    """

    def _section(self, n: int) -> Section:
        return Section(numero=n, titre=f"S{n}", corps="corps")

    def test_un_objectif_qui_refuse_de_demarrer_bloque(self):
        etapes = derouler([self._section(1), self._section(2)],
                          lancer=lambda s: {"statut_objectif": "failed"})

        assert etapes[0].statut == "bloquee"
        assert "n'a pas abouti" in etapes[0].detail
        assert etapes[1].statut == "ignoree", "la suite ne doit pas partir"

    def test_un_rapport_vide_bloque(self):
        """Zéro seconde et aucun rapport : la mission n'a pas eu lieu."""
        etapes = derouler([self._section(1)], lancer=lambda s: {})

        assert etapes[0].statut == "bloquee"
        assert "n'a pas eu lieu" in etapes[0].detail

    def test_une_mission_qui_a_tourne_sans_workspace_ne_bloque_pas(self):
        """La distinction. Celle-ci a réellement tourné : elle n'avait
        simplement rien à confronter, et l'absence de mesure n'est pas une
        preuve d'échec."""
        etapes = derouler([self._section(1)], lancer=lambda s: {
            "statut_objectif": "completed", "qualite": "non_mesuree",
            "execution_summary": "3/3 task(s) completed"})

        assert etapes[0].statut == "faite"

    def test_le_bilan_nomme_l_arret(self):
        etapes = derouler([self._section(1), self._section(2)],
                          lancer=lambda s: {"statut_objectif": "failed"})

        assert bilan(etapes)["arret"]["section"] == "§1 S1"


class TestLeLanceurAutoriseLeDossier:
    def test_il_pose_allowed_paths_avant_le_bootstrap(self):
        """La cause première : sans whitelist, Aegis refuse le dossier et
        chaque objectif meurt avant d'exister. La whitelist est lue à la
        construction du conteneur, donc la variable doit être posée avant.
        """
        from pathlib import Path

        source = Path("scripts/derouler_cahier.py").read_text(encoding="utf-8")
        avant = source.index('os.environ.setdefault("ALLOWED_PATHS"')
        apres = source.index("HermesBootstrap()")

        assert avant < apres

    def test_le_statut_de_l_objectif_voyage_avec_le_rapport(self):
        from pathlib import Path

        source = Path("scripts/derouler_cahier.py").read_text(encoding="utf-8")

        assert '"statut_objectif": goal.get("status")' in source
