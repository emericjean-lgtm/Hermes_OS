"""La seule sortie de quarantaine, et elle est humaine (HOS-250).

## Le défaut, tracé avant correction

HOS-249 a mis en quarantaine tout ce que l'agent écrit — correctement.
Mais l'échappatoire que cette politique présuppose n'existait pas :

* **aucune route, aucun outil, aucune UI** ne permettait de promouvoir ;
* et `MemoryManager.promouvoir()` **annonçait un succès sans rien
  écrire**. Tracé : l'affectation `souvenir.provenance = …` levait
  `AttributeError` (la propriété est calculée depuis les colonnes), le
  repli cherchait un `metadata` que `MemoryEntry` n'a pas, rien n'était
  persisté — puis `memory.promoted` était publié.

`memory_remember` n'était donc pas write-only *jusqu'à promotion* : il
l'était **définitivement**.

## Ce que la promotion ne change pas

**L'origine.** Une mémoire écrite par l'agent reste `agent` pour
toujours : c'est le fait historique, et l'effacer rendrait impossible de
répondre à « d'où venait cette information ? » après coup.

Ce qui change est la **confiance** — et `Provenance` séparait déjà les
deux. Aucune colonne n'a été inventée : `promu_par` renseigné suffit à
faire basculer la seconde en laissant la première intacte.

## Ce que le nom du promoteur prouve

Rien, cryptographiquement. Hermes OS n'a pas de mécanisme d'identité
humaine, et son conventionnel d'accord existant —
`POST /security/approvals/{id}` — n'en porte pas davantage. **Ce qui fait
foi est le canal** : cette route est servie par l'API locale et n'existe
pas comme outil MCP. Le nom est une trace d'audit. C'est le modèle de
confiance déjà retenu pour Aegis, et le dire évite d'y croire davantage.
"""

from __future__ import annotations

import ast
import io
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from backend.memory import db as mdb
from backend.memory import episodic
from backend.memory.confiance import (
    Origine,
    PromotionRefusee,
    Provenance,
    provenance_de,
)

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture
def base(tmp_path):
    moteur = mdb.make_engine(str(tmp_path / "m.db"))
    mdb.init_db(moteur)
    return moteur, mdb.make_session_factory(moteur)


def _agent(session, contenu="souvenir de l'agent", projet="proj-A"):
    return episodic.add_memory(
        session, type_="fact", content=contenu, project_id=projet,
        provenance=Provenance.depuis(Origine.AGENT))


# ═══ T1 — la promotion est réelle ═══════════════════════════════════

def test_T1_une_memoire_agent_devient_visible_apres_promotion(base):
    _, SF = base
    with SF() as s:
        entree = _agent(s)
        assert provenance_de(entree).en_quarantaine is True
        assert episodic.search_pour_agent(s, "souvenir", limit=5,
                                          project_id="proj-A") == []

        promue = episodic.promouvoir(s, entree.id, par="emeric")

        assert provenance_de(promue).en_quarantaine is False
        trouve = episodic.search_pour_agent(s, "souvenir", limit=5,
                                            project_id="proj-A")
        assert [e.content for e in trouve] == ["souvenir de l'agent"]


# ═══ T3/T4 — l'historique et le promoteur ══════════════════════════

def test_T3_l_origine_initiale_reste_tracable(base):
    """« Cette mémoire était initialement non fiable et a ensuite été
    explicitement validée par X. » Les deux moitiés doivent rester
    lisibles."""
    _, SF = base
    with SF() as s:
        entree = _agent(s)
        promue = episodic.promouvoir(s, entree.id, par="emeric")

        assert promue.origine == "agent", "l'origine historique a été effacée"
        assert provenance_de(promue).origine is Origine.AGENT
        assert provenance_de(promue).en_quarantaine is False


def test_T4_le_promoteur_et_sa_date_sont_enregistres(base):
    _, SF = base
    with SF() as s:
        promue = episodic.promouvoir(s, _agent(s).id, par="emeric")
        assert promue.promu_par == "emeric"
        assert promue.verifie_le is not None
        assert provenance_de(promue).promu_par == "emeric"


def test_une_promotion_sans_acteur_est_refusee(base):
    """« Une promotion sans acteur nommé n'est pas une promotion » — la
    règle de `Provenance`, appliquée aussi à la persistance, pour que la
    base ne soit pas une porte plus permissive que l'objet."""
    _, SF = base
    with SF() as s:
        entree = _agent(s)
        for acteur in ("", "   "):
            with pytest.raises(PromotionRefusee):
                episodic.promouvoir(s, entree.id, par=acteur)
        assert provenance_de(entree).en_quarantaine is True


# ═══ T5–T8 — l'agent ne peut pas s'élever ══════════════════════════

def test_T5_T6_l_outil_mcp_n_expose_aucun_champ_de_promotion():
    import inspect

    from backend.mcp_server import server

    parametres = set(inspect.signature(server.memory_remember).parameters)
    for interdit in ("promu_par", "origine", "verifie_le", "provenance"):
        assert interdit not in parametres, (
            f"`memory_remember` expose {interdit!r} — l'agent pourrait "
            "se promouvoir lui-même")


def test_T13_aucun_outil_mcp_ne_promeut():
    """La garde centrale de T-16 : la promotion doit rester hors de portée
    de l'agent. Un outil de promotion exposé viderait tout le modèle."""
    from backend.mcp_server import server

    source = io.open(RACINE / "backend" / "mcp_server" / "server.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)

    outils = [n.name for n in ast.walk(arbre)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    suspects = [n for n in outils
                if "promo" in n.lower() or "promouv" in n.lower()]
    assert not suspects, f"outil de promotion exposé au MCP : {suspects}"

    exposes = getattr(server, "_ALL_TOOLS", ())
    noms = {getattr(t, "__name__", "") for t in exposes}
    assert not any("promo" in n.lower() for n in noms), noms


def test_T7_confidence_ne_promeut_pas(base):
    _, SF = base
    with SF() as s:
        entree = episodic.add_memory(
            s, type_="fact", content="je me declare fiable", confidence=1.0,
            project_id="proj-A", provenance=Provenance.depuis(Origine.AGENT))
        assert entree.confidence == 1.0
        assert provenance_de(entree).en_quarantaine is True
        assert episodic.search_pour_agent(s, "declare", limit=5,
                                          project_id="proj-A") == []


def test_T8_un_tag_de_confiance_n_eleve_rien(base):
    """Les tags sont écrits par l'agent. Un champ écrit par celui qu'on
    filtre ne peut pas porter le filtre."""
    _, SF = base
    with SF() as s:
        episodic.add_memory(
            s, type_="fact", content="contenu avec tag", project_id="proj-A",
            tags=["trusted", "humain", "promu", "verified"],
            provenance=Provenance.depuis(Origine.AGENT))
        assert episodic.search_pour_agent(s, "contenu", limit=5,
                                          project_id="proj-A") == []


# ═══ T9–T12 — portée, double promotion, erreurs ═══════════════════

def test_T9_une_memoire_promue_reste_dans_son_projet(base):
    """La promotion change la confiance, jamais la portée."""
    _, SF = base
    with SF() as s:
        entree = _agent(s, "SECRET_A", projet="proj-A")
        episodic.promouvoir(s, entree.id, par="emeric")

        depuis_a = episodic.search_pour_agent(s, "SECRET_A", limit=5,
                                              project_id="proj-A")
        depuis_b = episodic.search_pour_agent(s, "SECRET_A", limit=5,
                                              project_id="proj-B")
    assert [e.content for e in depuis_a] == ["SECRET_A"]
    assert depuis_b == [], "une mémoire promue a traversé vers un autre projet"


def test_T10_une_double_promotion_est_refusee_sans_rien_ecraser(base):
    """Réécrire effacerait le nom du premier promoteur et sa date —
    c'est-à-dire la trace de la décision qu'on veut pouvoir relire."""
    _, SF = base
    with SF() as s:
        entree = _agent(s)
        episodic.promouvoir(s, entree.id, par="emeric")
        date = entree.verifie_le

        with pytest.raises(episodic.DejaPromue):
            episodic.promouvoir(s, entree.id, par="quelqu-un-dautre")

        s.refresh(entree)
        assert entree.promu_par == "emeric"
        assert entree.verifie_le == date


def test_T11_une_memoire_inexistante_leve(base):
    _, SF = base
    with SF() as s:
        with pytest.raises(KeyError):
            episodic.promouvoir(s, "jamais-vue", par="emeric")


def test_T12_un_succes_ne_peut_pas_etre_annonce_sans_persistance(base, monkeypatch):
    """Le critère de la passe : « une promotion qui retourne un succès
    sans que la mémoire soit réellement promue est un échec ».

    On simule une écriture qui ne prend pas : la relecture doit constater
    la quarantaine et lever, plutôt que rendre l'entrée.
    """
    _, SF = base
    with SF() as s:
        entree = _agent(s)

        def _annuler(self):
            """Le commit passe, mais la ligne revient à son état d'avant."""
            entree.promu_par = None
            entree.verifie_le = None

        monkeypatch.setattr(type(s), "refresh", lambda self, obj: _annuler(self))

        with pytest.raises(RuntimeError, match="non effective"):
            episodic.promouvoir(s, entree.id, par="emeric")


# ═══ La façade ne ment plus ═══════════════════════════════════════

def test_la_facade_refuse_une_memoire_persistante_au_lieu_de_mentir(base):
    """Le défaut exact de HOS-249 : `MemoryManager.promouvoir()` rendait
    l'objet inchangé et publiait `memory.promoted`."""
    from backend.memory.memory_manager import MemoryManager

    _, SF = base
    with SF() as s:
        entree = _agent(s)
        evenements: list[str] = []
        gestionnaire = MemoryManager(
            on_event=lambda t, p, **k: evenements.append(t))

        with pytest.raises(TypeError, match="episodic.promouvoir"):
            gestionnaire.promouvoir(entree, "emeric")

        assert evenements == [], "un événement de succès a été publié"
        assert entree.promu_par is None
        assert provenance_de(entree).en_quarantaine is True


def test_la_facade_promeut_toujours_ses_propres_souvenirs():
    """Sa mémoire de travail, elle, a une provenance assignable — le
    comportement historique ne doit pas être cassé."""
    from backend.memory.memory_manager import MemoryManager

    class _Souvenir:
        def __init__(self):
            self.provenance = None

    gestionnaire = MemoryManager()
    souvenir = gestionnaire.marquer(_Souvenir(), Origine.WEB, "example.com")
    assert provenance_de(souvenir).en_quarantaine is True

    promu = gestionnaire.promouvoir(souvenir, "emeric")
    assert provenance_de(promu).en_quarantaine is False
    assert provenance_de(promu).promu_par == "emeric"


# ═══ T2/T14 — persistance, deux vrais processus ═══════════════════

def test_T2_T14_la_promotion_survit_a_un_redemarrage(tmp_path):
    """Un objet Python qui porte la promotion ne prouve rien. Deux
    processus la prouvent."""
    chemin = str(tmp_path / "p.db")
    pre = "import sys\nsys.path.insert(0, %r)\n" % str(RACINE)

    ecriture = subprocess.run(
        [sys.executable, "-c", pre + textwrap.dedent(f"""
            from backend.memory import db as mdb, episodic
            from backend.memory.confiance import Origine, Provenance
            m = mdb.make_engine({chemin!r}); mdb.init_db(m)
            with mdb.make_session_factory(m)() as s:
                e = episodic.add_memory(s, type_="fact",
                    content="PROMUE_AVANT_REDEMARRAGE", project_id="proj-A",
                    provenance=Provenance.depuis(Origine.AGENT))
                episodic.add_memory(s, type_="fact",
                    content="RESTEE_EN_QUARANTAINE", project_id="proj-A",
                    provenance=Provenance.depuis(Origine.AGENT))
                episodic.promouvoir(s, e.id, par="emeric")
            print("ok")
        """)], capture_output=True, text=True, timeout=300)
    assert ecriture.returncode == 0, ecriture.stderr[-2000:]

    lecture = subprocess.run(
        [sys.executable, "-c", pre + textwrap.dedent(f"""
            from backend.memory import db as mdb, episodic
            from backend.memory.confiance import provenance_de
            m = mdb.make_engine({chemin!r}); mdb.init_db(m)
            with mdb.make_session_factory(m)() as s:
                vus = [e.content for e in episodic.search_pour_agent(
                    s, "PROMUE_AVANT_REDEMARRAGE RESTEE_EN_QUARANTAINE",
                    limit=10, project_id="proj-A")]
                toutes = episodic.search_memories(
                    s, "PROMUE_AVANT_REDEMARRAGE", limit=5,
                    project_id="proj-A")
                p = provenance_de(toutes[0])
            print("|".join(sorted(vus)) + "#" + toutes[0].origine + "#"
                  + str(p.promu_par))
        """)], capture_output=True, text=True, timeout=300)
    assert lecture.returncode == 0, lecture.stderr[-2000:]

    vus, origine, promoteur = lecture.stdout.strip().splitlines()[-1].split("#")
    assert vus == "PROMUE_AVANT_REDEMARRAGE", (
        "la promotion ou la quarantaine n'a pas survécu au redémarrage")
    assert origine == "agent", "l'origine historique a été perdue"
    assert promoteur == "emeric", "le promoteur n'a pas survécu"


# ═══ La route humaine ═════════════════════════════════════════════

def test_la_route_de_promotion_existe_et_n_est_pas_un_outil_mcp():
    from backend.api.routes.memory import router

    chemins = {r.path: getattr(r, "methods", set()) for r in router.routes}
    assert "/memory/{memory_id}/promote" in chemins
    assert "POST" in chemins["/memory/{memory_id}/promote"]


def test_la_route_distingue_ses_erreurs():
    """404 introuvable, 409 déjà promue, 422 acteur manquant — les
    conventions déjà présentes dans ce routeur."""
    import inspect

    from backend.api.routes import memory as routes

    arbre = ast.parse(textwrap.dedent(
        inspect.getsource(routes.promote_memory)))
    codes = {k.value.value for n in ast.walk(arbre)
             if isinstance(n, ast.Call)
             and ast.unparse(n.func).endswith("HTTPException")
             for k in n.keywords
             if k.arg == "status_code" and isinstance(k.value, ast.Constant)}
    assert codes == {404, 409, 422}, codes


def test_le_promoteur_est_obligatoire_dans_le_contrat_de_la_route():
    from backend.api.routes.memory import MemoryPromoteRequest

    champs = MemoryPromoteRequest.model_fields
    assert "promu_par" in champs
    assert champs["promu_par"].is_required(), (
        "`promu_par` a un défaut — une promotion anonyme redeviendrait "
        "possible")


def test_une_seule_transition_de_promotion_persistante():
    """Deux chemins d'écriture divergeraient. `episodic.promouvoir` est le
    seul qui écrive `promu_par` en base."""
    ecrivains: list[str] = []
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            if (isinstance(noeud, ast.Assign)
                    and any(isinstance(c, ast.Attribute)
                            and c.attr == "promu_par" for c in noeud.targets)):
                ecrivains.append(str(fichier.relative_to(RACINE)))
    assert ecrivains == [str(Path("backend") / "memory" / "episodic.py")], (
        f"`promu_par` est écrit à plusieurs endroits : {ecrivains}")
