# -*- coding: utf-8 -*-
"""Ce que l'agent a fait de ses Skills, rattache a son Run (G-33, HOS-281).

## La chaine, mesuree avec l'observateur reellement installe

    phase 1 (Hermes OS)  RUN-ALPHA -> ffb603fc...
                         RUN-BETA  -> 9039b9d6...
    phase 2 (agent)      g33-une   turn=ffb603fc...
                         g33-deux  turn=ffb603fc...
                         g33-trois turn=9039b9d6...
    phase 3 (NOUVEAU     g33-une  -> RUN-ALPHA
             processus)  g33-deux -> RUN-ALPHA
                         g33-trois-> RUN-BETA

**ADOPT.** L'observateur est installe sous
`%LOCALAPPDATA%\\hermes\\plugins\\hermes-os-observateur-skills`, active par
`plugins.enabled`, et `scan_plugin` rend « aucun import interne » — sa
condition de survie au retrait du 2026-09-14.

## Ce que l'agent continue de faire quand le plugin ne marche pas

Mesure des trois defaillances, avec les Skills verifiees **sur le disque** :

    plugin absent      non charge   0 fait   Skills ecrites
    plugin desactive   charge, off  0 fait   Skills ecrites
    callback qui leve  charge, on   0 fait   Skills ecrites

L'observateur ne peut pas bloquer l'agent : `_emit_skill_lifecycle` ignore
le retour du hook et isole chaque callback.

## Ce que ce lecteur ne fait pas

Il ne recopie rien. Le fait appartient au plugin, la relation `T -> R` au
bus de Hermes OS, et aucun des deux ne migre dans l'autre. C'est la
troisieme lecture du disque de l'agent — apres les competences (HOS-274) et
leur provenance (HOS-275) — et la posture est la meme.
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture
def foyer(tmp_path, monkeypatch):
    """Un `HERMES_HOME` a nous, avec un etat de plugin ecrit a la main."""
    import importlib

    from backend.skills import registre

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    importlib.reload(registre)
    d = tmp_path / "plugin-data" / "agent-plugin-hermes-os-observateur-skills-abc"
    d.mkdir(parents=True)
    yield d
    monkeypatch.delenv("HERMES_HOME", raising=False)
    importlib.reload(registre)


def _poser(dossier: Path, faits: list[dict]) -> None:
    dossier.joinpath("state.json").write_text(
        json.dumps({f"fait-{i:03d}": f for i, f in enumerate(faits)},
                   ensure_ascii=False),
        encoding="utf-8")


def _fait(**extra):
    base = {"observe_a": 1.0, "action": "created", "skill_name": "s",
            "provenance": "local", "client_turn_id": "T1"}
    base.update(extra)
    return base


def _lire(relations: dict[str, str | None], limite: int = 200):
    """Les observations, avec une resolution `T -> R` posee d'avance."""
    import importlib

    from backend.runs import correlation
    from backend.skills import observations

    importlib.reload(observations)
    appels: list[str] = []

    async def _resoudre(turn_id, jours=7):
        appels.append(turn_id)
        return relations.get(turn_id)

    reel = correlation.run_du_tour
    correlation.run_du_tour = _resoudre
    try:
        return asyncio.run(observations.observations(limite)), appels
    finally:
        correlation.run_du_tour = reel


# ── Le rattachement ───────────────────────────────────────────────────

def test_une_mutation_est_rattachee_a_son_run(foyer):
    """La raison d'etre du lecteur : `client_turn_id` -> Run."""
    _poser(foyer, [_fait(skill_name="g33-une", client_turn_id="T1")])
    obs, _ = _lire({"T1": "RUN-ALPHA"})
    assert len(obs) == 1
    assert obs[0].skill == "g33-une"
    assert obs[0].run == "RUN-ALPHA"
    assert obs[0].rattachee is True
    # L'etiquette RENDUE, et pas seulement celle qui a servi a resoudre.
    # Une mutation qui vidait `turn_id` restait verte : le rattachement se
    # fait sur le fait brut, si bien qu'un ecran affichant « quel tour a
    # produit ceci » aurait montre du vide sans qu'aucun test ne bronche.
    assert obs[0].turn_id == "T1"


def test_plusieurs_skills_d_un_meme_tour_vont_au_meme_run(foyer):
    """Mesure : `g33-une` et `g33-deux` portaient la meme etiquette."""
    _poser(foyer, [_fait(skill_name="une", client_turn_id="T1"),
                   _fait(skill_name="deux", client_turn_id="T1")])
    obs, _ = _lire({"T1": "RUN-ALPHA"})
    assert {o.run for o in obs} == {"RUN-ALPHA"}


def test_deux_runs_restent_separes(foyer):
    _poser(foyer, [_fait(skill_name="une", client_turn_id="T1"),
                   _fait(skill_name="trois", client_turn_id="T2")])
    from backend.runs import correlation
    from backend.skills import observations

    async def _resoudre(turn_id, jours=7):
        return {"T1": "RUN-ALPHA", "T2": "RUN-BETA"}.get(turn_id)

    reel = correlation.run_du_tour
    correlation.run_du_tour = _resoudre
    try:
        groupes = asyncio.run(observations.par_run())
    finally:
        correlation.run_du_tour = reel
    assert {r: sorted(o.skill for o in l) for r, l in groupes.items()} == {
        "RUN-ALPHA": ["une"], "RUN-BETA": ["trois"]}


def test_chaque_etiquette_n_est_resolue_qu_une_fois(foyer):
    """Un Run emet plusieurs tours, un tour plusieurs Skills. Rejouer le bus
    par fait couterait le parcours autant de fois qu'il y a de mutations."""
    _poser(foyer, [_fait(skill_name=f"s{i}", client_turn_id="T1")
                   for i in range(6)])
    obs, appels = _lire({"T1": "RUN-ALPHA"})
    assert len(obs) == 6
    assert appels == ["T1"], f"{len(appels)} rejeux du bus pour un tour"


# ── Ce qui n'est pas rattache ─────────────────────────────────────────

def test_un_fait_sans_etiquette_n_est_rattache_a_rien(foyer):
    """Un tour hors Run — le chat — ou un agent non patche."""
    _poser(foyer, [_fait(skill_name="hors", client_turn_id="")])
    obs, appels = _lire({})
    assert obs[0].run is None and obs[0].rattachee is False
    assert appels == [], "une etiquette vide a ete resolue"


def test_une_etiquette_etrangere_n_est_rattachee_a_rien(foyer):
    """Hermes OS ne reconnait que ce qu'il a frappe."""
    _poser(foyer, [_fait(client_turn_id="venue-d-ailleurs")])
    obs, _ = _lire({"T1": "RUN-ALPHA"})
    assert obs[0].run is None


def test_les_non_rattachees_ne_deviennent_pas_un_run(foyer):
    """Les ranger sous une clef « inconnu » lui donnerait l'apparence d'un
    Run, et elle finirait affichee a cote des vrais."""
    _poser(foyer, [_fait(skill_name="a", client_turn_id="T1"),
                   _fait(skill_name="b", client_turn_id=""),
                   _fait(skill_name="c", client_turn_id="etrangere")])
    from backend.runs import correlation
    from backend.skills import observations

    async def _resoudre(turn_id, jours=7):
        return "RUN-ALPHA" if turn_id == "T1" else None

    reel = correlation.run_du_tour
    correlation.run_du_tour = _resoudre
    try:
        groupes = asyncio.run(observations.par_run())
    finally:
        correlation.run_du_tour = reel
    assert list(groupes) == ["RUN-ALPHA"]
    assert [o.skill for o in groupes["RUN-ALPHA"]] == ["a"]


# ── Le plugin absent, muet ou casse ───────────────────────────────────

def test_sans_etat_de_plugin_la_lecture_est_vide_et_non_en_erreur(foyer):
    """Plugin absent, desactive, ou qui n'a rien vu : trois situations qui
    se lisent pareil d'ici. Toutes doivent dire « aucune observation »,
    jamais « aucune mutation »."""
    import importlib

    from backend.skills import observations

    importlib.reload(observations)
    assert observations.faits_bruts() == []
    assert asyncio.run(observations.observations()) == []


def test_un_etat_illisible_ne_fait_pas_echouer_la_lecture(foyer):
    foyer.joinpath("state.json").write_text("{ pas du json", encoding="utf-8")
    import importlib

    from backend.skills import observations

    importlib.reload(observations)
    assert observations.faits_bruts() == []


def test_une_clef_qui_n_est_pas_un_fait_est_ignoree(foyer):
    """Le plugin peut ranger autre chose dans son etat ; seul le prefixe
    convenu designe un fait."""
    foyer.joinpath("state.json").write_text(
        json.dumps({"fait-001": _fait(), "reglage": {"x": 1}}),
        encoding="utf-8")
    import importlib

    from backend.skills import observations

    importlib.reload(observations)
    assert len(observations.faits_bruts()) == 1


# ── La vue produit (G-34) ─────────────────────────────────────────────

def _vue(relations, limite=200, registre=None):
    """`vue()` avec la resolution `T -> R` et le Run Ledger poses d'avance."""
    import importlib

    from backend.runs import correlation
    from backend.skills import observations

    importlib.reload(observations)

    async def _resoudre(turn_id, jours=7):
        return relations.get(turn_id)

    reel = correlation.run_du_tour
    correlation.run_du_tour = _resoudre
    reel_detail = observations._detail_des_runs
    if registre is not None:
        observations._detail_des_runs = lambda runs: registre
    try:
        return asyncio.run(observations.vue(limite))
    finally:
        correlation.run_du_tour = reel
        observations._detail_des_runs = reel_detail


def test_la_vue_est_une_partition_pas_une_liste_filtree(foyer):
    """Chaque mutation lue est dans `runs` OU dans `non_rattachees`, jamais
    dans les deux, jamais dans aucune.

    Une vue qui filtrerait au lieu de partitionner pourrait taire les
    orphelines sans qu'aucun compte ne bronche — et c'est exactement ce
    qu'un ecran a besoin de ne pas faire."""
    _poser(foyer, [_fait(skill_name="a", client_turn_id="T1"),
                   _fait(skill_name="b", client_turn_id=""),
                   _fait(skill_name="c", client_turn_id="etrangere")])
    v = _vue({"T1": "RUN-ALPHA"})
    rattachees = [m["skill"] for r in v["runs"] for m in r["skills"]]
    orphelines = [m["skill"] for m in v["non_rattachees"]]
    assert sorted(rattachees + orphelines) == ["a", "b", "c"]
    assert not set(rattachees) & set(orphelines)
    assert v["observees"] == 3


def test_deux_runs_ne_se_melangent_pas(foyer):
    """La mutation qui compte : un aplatissement mettrait les deux Skills
    sous les deux Runs, et la somme resterait juste."""
    _poser(foyer, [_fait(skill_name="alpha-seule", client_turn_id="T1"),
                   _fait(skill_name="beta-seule", client_turn_id="T2")])
    v = _vue({"T1": "RUN-ALPHA", "T2": "RUN-BETA"})
    par_run = {r["run"]: [m["skill"] for m in r["skills"]] for r in v["runs"]}
    assert par_run == {"RUN-ALPHA": ["alpha-seule"], "RUN-BETA": ["beta-seule"]}


def test_un_meme_skill_peut_servir_a_plusieurs_runs(foyer):
    """Rien ne doit dedupliquer par nom de Skill : deux Runs qui touchent
    la meme competence sont deux faits distincts."""
    _poser(foyer, [_fait(skill_name="partagee", client_turn_id="T1"),
                   _fait(skill_name="partagee", client_turn_id="T2")])
    v = _vue({"T1": "RUN-ALPHA", "T2": "RUN-BETA"})
    assert {r["run"] for r in v["runs"]} == {"RUN-ALPHA", "RUN-BETA"}
    assert all([m["skill"] for m in r["skills"]] == ["partagee"]
               for r in v["runs"])


def test_deux_tours_concurrents_gardent_chacun_leur_run(foyer):
    """Un Run emet plusieurs tours. Deux tours entrelaces dans l'etat du
    plugin ne doivent pas se rattraper l'un l'autre."""
    _poser(foyer, [_fait(skill_name="a1", client_turn_id="T1"),
                   _fait(skill_name="b1", client_turn_id="T2"),
                   _fait(skill_name="a2", client_turn_id="T1"),
                   _fait(skill_name="b2", client_turn_id="T2")])
    v = _vue({"T1": "RUN-ALPHA", "T2": "RUN-BETA"})
    par_run = {r["run"]: sorted(m["skill"] for m in r["skills"])
               for r in v["runs"]}
    assert par_run == {"RUN-ALPHA": ["a1", "a2"], "RUN-BETA": ["b1", "b2"]}


def test_une_mutation_sans_etiquette_ne_recoit_aucun_run(foyer):
    """« Ne deduis jamais une relation absente. » Meme quand un seul Run
    est connu et qu'il serait tentant de l'attribuer."""
    from backend.skills import observations

    _poser(foyer, [_fait(skill_name="rattachee", client_turn_id="T1"),
                   _fait(skill_name="orpheline", client_turn_id="")])
    v = _vue({"T1": "RUN-ALPHA"})
    assert [m["skill"] for m in v["non_rattachees"]] == ["orpheline"]
    assert v["non_rattachees"][0]["raison"] == observations.SANS_ETIQUETTE
    # Aucun identifiant de Run ne doit apparaitre dans une orpheline.
    assert "run" not in v["non_rattachees"][0]


def test_les_deux_causes_d_absence_sont_distinguees(foyer):
    """« Aucune etiquette » et « etiquette inconnue de Hermes OS » ne sont
    pas le meme fait : la premiere dit un tour hors Run, la seconde un
    autre client ACP ou une relation elaguee."""
    from backend.skills import observations

    _poser(foyer, [_fait(skill_name="sans", client_turn_id=""),
                   _fait(skill_name="etrangere", client_turn_id="ailleurs")])
    v = _vue({})
    causes = {m["skill"]: m["raison"] for m in v["non_rattachees"]}
    assert causes == {"sans": observations.SANS_ETIQUETTE,
                      "etrangere": observations.ETIQUETTE_NON_RESOLUE}


def test_le_detail_du_run_vient_du_ledger_et_manque_explicitement(foyer):
    """Un Run absent du Ledger rend `detail: None` — jamais celui du voisin."""
    _poser(foyer, [_fait(skill_name="a", client_turn_id="T1"),
                   _fait(skill_name="b", client_turn_id="T2")])
    v = _vue({"T1": "RUN-ALPHA", "T2": "RUN-BETA"},
             registre=(True, {"RUN-ALPHA": {"mission": "M", "objectif": "O",
                                            "statut": "reussi", "agent": "A"}}))
    detail = {r["run"]: r["detail"] for r in v["runs"]}
    assert detail["RUN-ALPHA"]["objectif"] == "O"
    assert detail["RUN-BETA"] is None
    assert v["registre_lisible"] is True


def test_un_ledger_illisible_ne_se_lit_pas_comme_un_run_inconnu(foyer):
    """Sans ce booleen, une panne du registre et un Run absent rendraient
    le meme `None`, et l'ecran dirait « Run inconnu » d'un Run connu."""
    _poser(foyer, [_fait(skill_name="a", client_turn_id="T1")])
    v = _vue({"T1": "RUN-ALPHA"}, registre=(False, {}))
    assert v["registre_lisible"] is False
    assert v["runs"][0]["detail"] is None


def test_un_registre_qui_leve_rend_illisible_et_non_vide(foyer):
    """La garde qui manquait, trouvee par mutation.

    `test_un_ledger_illisible_ne_se_lit_pas_comme_un_run_inconnu` passe le
    couple `(False, {})` en dur : elle mesure ce que la VUE fait du
    drapeau, jamais la fonction qui le pose. Remplacer `return False, {}`
    par `return True, {}` dans `_detail_des_runs` laissait donc tout vert
    -- et l'ecran aurait dit « absent du Run Ledger » de quatre Runs
    parfaitement enregistres, sur la foi d'une base injoignable.

    Celle-ci casse le registre pour de vrai et lit ce qui en sort."""
    import importlib

    from backend.skills import observations

    importlib.reload(observations)

    class RegistreCasse:
        def __init__(self):
            raise OSError("base injoignable")

    import backend.runs.registre as mod

    reel = mod.Registre
    mod.Registre = RegistreCasse
    try:
        lisible, detail = observations._detail_des_runs(["RUN-ALPHA"])
    finally:
        mod.Registre = reel
    assert lisible is False, "une panne du registre se lit « Run inconnu »"
    assert detail == {}


def test_un_registre_lisible_rend_ce_qu_il_connait(foyer):
    """Le pendant : sans elle, `_detail_des_runs` pourrait rendre
    `(False, {})` en toutes circonstances et la garde ci-dessus resterait
    verte -- l'ecran n'afficherait plus jamais un objectif."""
    import importlib

    from backend.skills import observations

    importlib.reload(observations)

    class RunFactice:
        mission, objectif, agent = "M", "O", "A"

        class statut:
            value = "reussi"

    class RegistreFactice:
        def lire(self, identifiant):
            return RunFactice() if identifiant == "RUN-ALPHA" else None

    import backend.runs.registre as mod

    reel = mod.Registre
    mod.Registre = RegistreFactice
    try:
        lisible, detail = observations._detail_des_runs(["RUN-ALPHA", "RUN-BETA"])
    finally:
        mod.Registre = reel
    assert lisible is True
    assert detail["RUN-ALPHA"]["objectif"] == "O"
    assert "RUN-BETA" not in detail


def test_le_ledger_n_est_pas_interroge_sans_run(foyer):
    """Zero observation rattachee : ouvrir la base pour rien couterait un
    acces disque a chaque affichage d'un ecran vide."""
    from backend.skills import observations

    assert observations._detail_des_runs([]) == (True, {})


def test_la_vue_dit_si_un_etat_de_plugin_a_ete_trouve(foyer):
    """Trois situations se lisent pareil d'ici — plugin absent, desactive,
    ou qui n'a rien vu. L'ecran doit pouvoir dire « aucune observation »
    plutot que « aucune mutation », et ce booleen est ce qui l'y autorise."""
    import importlib

    from backend.skills import observations

    importlib.reload(observations)
    assert asyncio.run(observations.vue())["etat_lisible"] is False

    _poser(foyer, [_fait()])
    importlib.reload(observations)
    assert asyncio.run(observations.vue())["etat_lisible"] is True


def test_la_retention_annoncee_est_celle_du_bus(foyer):
    """L'ecran annonce une fenetre de consultation. Une valeur decorative
    ferait promettre sept jours a un bus qui en garde trois."""
    import inspect

    from backend.sds import runtime

    source = inspect.getsource(runtime.init_eventbus_in_holder)
    assert "retention_days=7" in source, (
        "le bus ne retient plus 7 jours : la vue le promet encore")
    _poser(foyer, [_fait()])
    assert _vue({})["retention_jours"] == 7


def test_le_groupement_ne_resout_pas_le_bus_une_seconde_fois(foyer):
    """`par_run()` rejouait le bus pour la meme liste que `observations()`
    venait de resoudre. Un Run emet plusieurs tours : le cout se paie par
    etiquette, et un ecran qui affiche les deux vues le paierait deux fois."""
    import importlib

    from backend.runs import correlation
    from backend.skills import observations

    _poser(foyer, [_fait(skill_name=f"s{i}", client_turn_id="T1")
                   for i in range(4)])
    importlib.reload(observations)
    appels = []

    async def _resoudre(turn_id, jours=7):
        appels.append(turn_id)
        return "RUN-ALPHA"

    reel = correlation.run_du_tour
    correlation.run_du_tour = _resoudre
    try:
        asyncio.run(observations.vue())
    finally:
        correlation.run_du_tour = reel
    assert appels == ["T1"], f"{len(appels)} rejeux du bus pour un tour"


# ── La route, et son appelant ─────────────────────────────────────────

def test_la_route_sert_la_vue_et_non_une_seconde_lecture():
    """Une route qui recalculerait la relation deviendrait la seconde
    source de verite que G-29 a refusee."""
    source = (RACINE / "backend" / "skills"
              / "routes.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    corps = next(n for n in ast.walk(arbre)
                 if isinstance(n, ast.AsyncFunctionDef)
                 and n.name == "observations_de_l_agent")
    appels = {getattr(c.func, "attr", None) for c in ast.walk(corps)
              if isinstance(c, ast.Call)}
    assert "vue" in appels
    assert not {"replay", "publish", "run_du_tour"} & appels, (
        "la route refait le travail du lecteur")


def test_la_route_est_declaree_avant_le_joker_de_skill_id():
    """`/skills/{skill_id}` avalerait `/skills/observations` s'il etait
    declare avant : FastAPI apparie dans l'ordre de declaration, et la
    route rendrait un 404 « skill 'observations' not found »."""
    source = (RACINE / "backend" / "skills"
              / "routes.py").read_text(encoding="utf-8")
    assert (source.index('@router.get("/observations")')
            < source.index('@router.get("/{skill_id}")'))


def test_l_ecran_appelle_vraiment_la_route():
    """Le defaut que ce depot appelle « backend orphelin » : 120 routes sur
    306 sans appelant frontend au 2026-09-07. Une route de plus sans ecran
    en ferait 121."""
    client = (RACINE / "frontend" / "src" / "services"
              / "client.ts").read_text(encoding="utf-8")
    assert '"/skills/observations"' in client

    ecran = (RACINE / "frontend" / "src" / "features" / "skills"
             / "skills-center.tsx").read_text(encoding="utf-8")
    assert "skillsClient.observations()" in ecran, (
        "la route existe et aucun ecran ne l'appelle")


def test_l_ecran_n_affirme_plus_qu_aucune_competence_n_a_de_run():
    """Contrat perime par G-33, corrige par G-34. La phrase etait une
    AFFIRMATION D'ECRAN, pas une lecture de donnee : elle est restee vraie
    a l'affichage pendant que la relation devenait mesurable, et rien n'a
    rougi. Ce qui la remplace est borne a l'inventaire, qui est ce dont
    l'onglet Agent parle."""
    ecran = (RACINE / "frontend" / "src" / "features" / "skills"
             / "skills-center.tsx").read_text(encoding="utf-8")
    assert "Aucune compétence n'est rattachée à un Run" not in ecran
    assert "Cet inventaire ne porte aucun Run" in ecran


# ── Ce que le lecteur ne devient pas ──────────────────────────────────

def test_le_lecteur_n_ecrit_rien():
    """Meme garde que `registre`, `provenance` et `vue_skills` : lire l'etat
    d'un plugin de l'agent ne doit jamais devenir le tenir."""
    arbre = ast.parse((RACINE / "backend" / "skills"
                       / "observations.py").read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = (getattr(noeud.func, "attr", None)
                   or getattr(noeud.func, "id", None))
            assert nom not in {"write_text", "write_bytes", "mkdir", "unlink",
                               "rmtree", "replace", "open", "touch"}, (
                f"le lecteur appelle `{nom}`")


def test_le_lecteur_ne_recopie_pas_les_faits_chez_hermes_os():
    """Le fait appartient au plugin, la relation au bus. Recopier l'un dans
    l'autre creerait la seconde source de verite."""
    source = (RACINE / "backend" / "skills"
              / "observations.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    litteraux = {n.value for n in ast.walk(arbre)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for interdit in ("INSERT", "CREATE TABLE", "publish", "sqlite"):
        assert not any(interdit in x for x in litteraux if len(x) < 300), (
            f"le lecteur ecrit `{interdit}`")
