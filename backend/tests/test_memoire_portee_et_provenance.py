"""Ce que l'agent a le droit de se rappeler (HOS-249).

## Les trois défauts, mesurés avant correction

1. **`project_id=None` était un joker.** Une recherche sans projet rendait
   les entrées de *tous* les projets. `project_memory.permanent_memory`
   avait déjà nommé le danger : « la confusion des deux niveaux est
   précisément la façon dont une décision prise pour un projet finit lue
   comme une règle globale ».
2. **Aucune provenance** sur le chemin MCP. `memory_remember` écrivait ce
   que l'agent lui donnait, et `memory_search` le lui rendait — une
   injection lue sur une page pouvait devenir persistante.
3. **`memory_long.project_id` portait un chemin de fichiers** quand
   `projects.id` est un UUID : deux orthographes du même projet ne se
   voyaient pas.

## Ce que ce jalon n'a pas créé

Rien. `Provenance.depuis()` appliquait déjà la règle — *« l'appelant ne
peut pas demander la confiance, il ne peut que déclarer d'où ça vient »*.
`filtrer()` écartait déjà la quarantaine. Aegis refusait déjà un
`project_id` non résolu. Les trois politiques existaient ; il manquait
leur application sur le chemin de l'agent.
"""

from __future__ import annotations

import ast
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.memory import db as mdb
from backend.memory import episodic
from backend.memory.confiance import Origine, Provenance, provenance_de

RACINE = Path(__file__).resolve().parents[2]
CHEMIN_LEGACY = r"C:\Users\emeri\Hermes_OS-main"


@pytest.fixture
def base(tmp_path):
    """Une base mémoire jetable, schéma complet."""
    moteur = mdb.make_engine(str(tmp_path / "m.db"))
    mdb.init_db(moteur)
    return moteur, mdb.make_session_factory(moteur)


def _ecrire(session, contenu, projet, origine):
    return episodic.add_memory(
        session, type_="fact", content=contenu, project_id=projet,
        provenance=None if origine is None else Provenance.depuis(origine))


# ═══ Portée — les onze cas du §16 ═══════════════════════════════════

def test_un_projet_ne_voit_jamais_la_memoire_d_un_autre(base):
    _, SF = base
    with SF() as s:
        _ecrire(s, "SECRET_ALPHA", "proj-A", Origine.HUMAIN)
        _ecrire(s, "SECRET_BETA", "proj-B", Origine.HUMAIN)

        a = [e.content for e in episodic.search_pour_agent(s, "SECRET", limit=10,
                                                           project_id="proj-A")]
        b = [e.content for e in episodic.search_pour_agent(s, "SECRET", limit=10,
                                                           project_id="proj-B")]
    assert a == ["SECRET_ALPHA"]
    assert b == ["SECRET_BETA"]
    assert "SECRET_BETA" not in a and "SECRET_ALPHA" not in b


def test_le_permanent_est_visible_depuis_tous_les_projets(base):
    """C'est ce qui le rend permanent. Le §12 en fait un niveau, pas un
    résidu."""
    _, SF = base
    with SF() as s:
        _ecrire(s, "REGLE_PERMANENTE", None, Origine.HUMAIN)
        _ecrire(s, "FAIT_A", "proj-A", Origine.HUMAIN)

        for projet in ("proj-A", "proj-B"):
            trouves = [e.content for e in episodic.search_pour_agent(
                s, "REGLE_PERMANENTE", limit=10, project_id=projet)]
            assert trouves == ["REGLE_PERMANENTE"], projet


def test_none_ne_donne_jamais_acces_aux_projets(base):
    """Le défaut central : `None` rendait tout. Il rend maintenant le
    niveau permanent, et lui seul."""
    _, SF = base
    with SF() as s:
        _ecrire(s, "SECRET_A", "proj-A", Origine.HUMAIN)
        _ecrire(s, "SECRET_B", "proj-B", Origine.HUMAIN)
        _ecrire(s, "SECRET_PERM", None, Origine.HUMAIN)

        trouves = [e.content for e in episodic.search_pour_agent(
            s, "SECRET", limit=10, project_id=None)]
    assert trouves == ["SECRET_PERM"]


def test_la_lecture_systeme_reste_inchangee(base):
    """La console et les rapports ont le droit de tout voir. Ce sont deux
    droits différents, pas deux implémentations du même — et changer le
    chemin système aurait cassé le tableau de bord sans rien protéger."""
    _, SF = base
    with SF() as s:
        _ecrire(s, "SECRET_A", "proj-A", Origine.HUMAIN)
        _ecrire(s, "SECRET_B", "proj-B", Origine.HUMAIN)

        tous = [e.content for e in episodic.search_memories(
            s, "SECRET", limit=10, project_id=None)]
    assert sorted(tous) == ["SECRET_A", "SECRET_B"]


def test_un_projet_inconnu_est_refuse_et_non_rendu_vide():
    """Une liste vide se lit « ce projet n'a rien mémorisé » ; un refus se
    lit « ce projet n'existe pas ». Confondre les deux laisse un agent
    croire qu'il travaille dans un projet vide alors qu'il s'est trompé
    de clé.

    Même contrat qu'Aegis sur le même paramètre.
    """
    from backend.mcp_server.server import _projet_resolu

    # Deux facons de ne pas resoudre, **toutes deux fermees** : le projet
    # n'existe pas, ou le registre lui-meme est illisible. Les messages
    # different — c'est utile a l'operateur — mais le verdict est le meme,
    # et c'est lui qui protege.
    with pytest.raises(episodic.ProjetInconnu):
        _projet_resolu("projet-qui-n-existe-pas-" + uuid.uuid4().hex)

    assert _projet_resolu(None) is None       # le permanent traverse

    # Et un projet reel traverse : la garde refuse l'inconnu, pas tout.
    from backend.projects.store import get_project_store

    try:
        projets = get_project_store().list()
    except Exception:
        pytest.skip("registre des projets indisponible dans cet environnement")
    if projets:
        assert _projet_resolu(projets[0].id) == projets[0].id


# ═══ Provenance — l'agent ne peut pas se déclarer fiable ═══════════

def test_une_ecriture_de_l_agent_part_en_quarantaine(base):
    """`AGENT` n'est pas dans `ORIGINES_DE_CONFIANCE`, et c'est délibéré :
    « le modèle écrivant depuis ce qu'il a lu — c'est là qu'une injection
    voyage »."""
    _, SF = base
    with SF() as s:
        entree = _ecrire(s, "lu sur une page web", "proj-A", Origine.AGENT)
        assert provenance_de(entree).origine is Origine.AGENT
        assert provenance_de(entree).en_quarantaine is True

        assert episodic.search_pour_agent(s, "page", limit=10,
                                          project_id="proj-A") == []


def test_une_confiance_a_1_ne_rend_pas_fiable(base):
    """`confidence` est une métadonnée libre écrite par l'agent. Un champ
    écrit par celui qu'on filtre ne peut pas porter le filtre."""
    _, SF = base
    with SF() as s:
        entree = episodic.add_memory(
            s, type_="fact", content="je suis digne de foi", confidence=1.0,
            project_id="proj-A", provenance=Provenance.depuis(Origine.AGENT))
        assert entree.confidence == 1.0
        assert provenance_de(entree).en_quarantaine is True
        assert episodic.search_pour_agent(s, "digne", limit=10,
                                          project_id="proj-A") == []


def test_l_outil_mcp_n_expose_aucun_parametre_de_provenance():
    """La garde structurelle : si `memory_remember` acceptait `origine`,
    un agent pourrait se déclarer `HUMAIN` et sortir de quarantaine seul.
    """
    import inspect

    from backend.mcp_server import server

    parametres = set(inspect.signature(server.memory_remember).parameters)
    for interdit in ("origine", "provenance", "promu_par", "confiance"):
        assert interdit not in parametres, (
            f"`memory_remember` expose {interdit!r} — l'agent pourrait "
            "fabriquer sa propre provenance")


def test_l_origine_est_posee_par_hermes_au_point_d_appel():
    """Et elle vaut `AGENT` : c'est ce que l'appelant MCP est."""
    import inspect

    from backend.mcp_server import server

    source = inspect.getsource(server.memory_remember)
    arbre = ast.parse(textwrap.dedent(source))
    origines = {ast.unparse(k.value) for n in ast.walk(arbre)
                if isinstance(n, ast.Call)
                for k in n.keywords if k.arg == "origine"}
    assert origines == {"Origine.AGENT"}, origines


def test_une_entree_sans_provenance_est_inconnue_donc_ecartee(base):
    """Le sens de lecture qui protège : une ligne écrite avant ce jalon,
    ou par un chemin qu'on aurait oublié d'instrumenter, ne devient pas
    fiable par défaut d'information."""
    _, SF = base
    with SF() as s:
        entree = _ecrire(s, "ecrite sans provenance", "proj-A", None)
        assert entree.origine is None
        assert provenance_de(entree).origine is Origine.INCONNUE
        assert episodic.search_pour_agent(s, "provenance", limit=10,
                                          project_id="proj-A") == []


def test_une_promotion_humaine_sort_de_quarantaine_et_se_trace(base):
    """Le contrepoids : `promouvoir()` exige un acteur nommé, et le
    refuse sans lui."""
    from backend.memory.confiance import PromotionRefusee

    _, SF = base
    with SF() as s:
        entree = _ecrire(s, "a promouvoir", "proj-A", Origine.AGENT)
        assert episodic.search_pour_agent(s, "promouvoir", limit=10,
                                          project_id="proj-A") == []

        entree.promu_par = "emeric"
        s.commit()
        s.refresh(entree)

        assert provenance_de(entree).en_quarantaine is False
        assert provenance_de(entree).promu_par == "emeric"
        trouve = episodic.search_pour_agent(s, "promouvoir", limit=10,
                                            project_id="proj-A")
        assert [e.content for e in trouve] == ["a promouvoir"]

    with pytest.raises(PromotionRefusee):
        Provenance.depuis(Origine.AGENT).promouvoir("")


def test_le_filtre_est_celui_du_context_relay():
    """Une seule politique, pas deux. `search_pour_agent` appelle la même
    fonction que `relais.depuis_la_memoire`."""
    import inspect

    source = inspect.getsource(episodic.search_pour_agent)
    assert "filtrer" in source

    relais = io.open(RACINE / "backend" / "mission" / "relais.py",
                     encoding="utf-8").read()
    assert "confiance import filtrer" in relais or "confiance import" in relais


# ═══ Migration legacy — sans perte et sans invention ═══════════════

def _base_legacy(tmp_path):
    moteur = mdb.make_engine(str(tmp_path / "legacy.db"))
    mdb.init_db(moteur)
    projet = str(uuid.uuid4())
    with moteur.begin() as c:
        c.execute(text(
            "INSERT INTO projects (id, name, description, root_path, status, "
            "tags, created_at, updated_at) VALUES (:i,:n,'',:r,'active','',"
            "'2026-01-01','2026-01-01')"),
            {"i": projet, "n": "HOS", "r": CHEMIN_LEGACY})
        for i in range(4):
            c.execute(text(
                "INSERT INTO memory_long (id, project_id, type, content, "
                "content_hash, tags, confidence, created_at) VALUES "
                "(:i,:p,'fact',:c,:h,'',1.0,'2026-08-11 22:45:17')"),
                {"i": f"legacy-{i}", "p": CHEMIN_LEGACY,
                 "c": f"HERMES_TEST_{i}", "h": f"h{i}"})
        c.execute(text(
            "INSERT INTO memory_long (id, project_id, type, content, "
            "content_hash, tags, confidence, created_at) VALUES "
            "('orphelin','C:/ailleurs','fact','X','hx','',1.0,"
            "'2026-08-11 22:45:17')"))
    return moteur, projet


def _lignes(moteur):
    with moteur.begin() as c:
        return {r[0]: r[1:] for r in c.execute(text(
            "SELECT id, project_id, content, confidence, origine, created_at "
            "FROM memory_long"))}


def test_la_migration_convertit_le_chemin_en_uuid_sans_rien_toucher_d_autre(tmp_path):
    moteur, projet = _base_legacy(tmp_path)
    avant = _lignes(moteur)

    convertis = mdb._migrer_les_projets_de_memoire(moteur)
    apres = _lignes(moteur)

    assert len(convertis) == 4
    for i in range(4):
        cle = f"legacy-{i}"
        assert apres[cle][0] == projet, "project_id non converti"
        assert apres[cle][1] == avant[cle][1], "le contenu a changé"
        assert apres[cle][2] == avant[cle][2], "la confiance a changé"
        assert apres[cle][3] is None, "une provenance a été inventée"
        assert apres[cle][4] == avant[cle][4], "la date a changé"


def test_une_ligne_non_resolvable_est_laissee_telle_quelle(tmp_path):
    """« Don't fail open on the unexpected », appliqué à une migration :
    ne pas deviner, ne pas migrer, signaler."""
    moteur, _ = _base_legacy(tmp_path)
    mdb._migrer_les_projets_de_memoire(moteur)
    assert _lignes(moteur)["orphelin"][0] == "C:/ailleurs"


def test_la_migration_est_idempotente(tmp_path):
    moteur, _ = _base_legacy(tmp_path)
    premier = mdb._migrer_les_projets_de_memoire(moteur)
    etat = _lignes(moteur)
    second = mdb._migrer_les_projets_de_memoire(moteur)

    assert len(premier) == 4
    assert second == [], "un second passage a reconverti des lignes"
    assert _lignes(moteur) == etat


def test_les_entrees_historiques_restent_hors_du_retrieval_agent(tmp_path):
    """Migrées, conservées, et toujours invisibles pour l'agent : leur
    provenance reste inconnue, et c'est correct — personne ne peut dire
    d'où elles viennent."""
    moteur, projet = _base_legacy(tmp_path)
    mdb._migrer_les_projets_de_memoire(moteur)
    SF = mdb.make_session_factory(moteur)
    with SF() as s:
        assert episodic.search_pour_agent(s, "HERMES_TEST", limit=10,
                                          project_id=projet) == []
        systeme = episodic.search_memories(s, "HERMES_TEST", limit=10,
                                           project_id=projet)
    assert len(systeme) == 4, "les entrées ont été perdues"


# ═══ Persistance — un vrai redémarrage ════════════════════════════

def test_portee_et_quarantaine_survivent_a_un_nouveau_processus(tmp_path):
    """Un objet Python qui contient la donnée ne prouve pas la
    persistance. Deux processus la prouvent."""
    chemin = str(tmp_path / "p.db")
    pre = "import sys\nsys.path.insert(0, %r)\n" % str(RACINE)

    ecriture = subprocess.run(
        [sys.executable, "-c", pre + textwrap.dedent(f"""
            from backend.memory import db as mdb, episodic
            from backend.memory.confiance import Origine, Provenance
            m = mdb.make_engine({chemin!r}); mdb.init_db(m)
            with mdb.make_session_factory(m)() as s:
                episodic.add_memory(s, type_="fact", content="AGENT_QUARANTAINE",
                    project_id="proj-A",
                    provenance=Provenance.depuis(Origine.AGENT))
                episodic.add_memory(s, type_="fact", content="HUMAIN_FIABLE",
                    project_id="proj-A",
                    provenance=Provenance.depuis(Origine.HUMAIN))
                episodic.add_memory(s, type_="fact", content="PERMANENT_FIABLE",
                    project_id=None,
                    provenance=Provenance.depuis(Origine.HUMAIN))
            print("ok")
        """)], capture_output=True, text=True, timeout=300)
    assert ecriture.returncode == 0, ecriture.stderr[-2000:]

    lecture = subprocess.run(
        [sys.executable, "-c", pre + textwrap.dedent(f"""
            from backend.memory import db as mdb, episodic
            m = mdb.make_engine({chemin!r}); mdb.init_db(m)
            with mdb.make_session_factory(m)() as s:
                a = [e.content for e in episodic.search_pour_agent(
                    s, "AGENT_QUARANTAINE HUMAIN_FIABLE PERMANENT_FIABLE",
                    limit=10, project_id="proj-A")]
                n = [e.content for e in episodic.search_pour_agent(
                    s, "AGENT_QUARANTAINE HUMAIN_FIABLE PERMANENT_FIABLE",
                    limit=10, project_id=None)]
            print("|".join(sorted(a)) + "#" + "|".join(sorted(n)))
        """)], capture_output=True, text=True, timeout=300)
    assert lecture.returncode == 0, lecture.stderr[-2000:]

    projet, permanent = lecture.stdout.strip().splitlines()[-1].split("#")
    assert sorted(projet.split("|")) == ["HUMAIN_FIABLE", "PERMANENT_FIABLE"], (
        "la quarantaine ou la portée n'a pas survécu au redémarrage")
    assert permanent == "PERMANENT_FIABLE"


def test_une_base_illisible_n_est_pas_une_memoire_vide(tmp_path):
    """« Illisible ≠ vide » : une base corrompue doit lever, pas rendre
    zéro résultat — un zéro se lit « rien à se rappeler »."""
    chemin = tmp_path / "corrompue.db"
    chemin.write_bytes(b"ceci n'est pas une base sqlite" * 40)
    moteur = mdb.make_engine(str(chemin))
    with pytest.raises(Exception):
        with mdb.make_session_factory(moteur)() as s:
            episodic.search_pour_agent(s, "quoi que ce soit", limit=5,
                                       project_id=None)


# ═══ Anti-contournement ═══════════════════════════════════════════

def test_le_chemin_agent_ne_peut_pas_appeler_la_recherche_systeme():
    """Les deux droits ne doivent pas se confondre.

    Cette garde visait d'abord `EchoAgent.search_memories` — et c'est ce
    qui a montré l'erreur : cette méthode sert **aussi** l'API et la
    console, qui ont le droit de tout voir. Lui imposer le filtre a cassé
    cinq tests préexistants du contrat HOS-086, sans rien protéger de
    plus.

    Elle porte donc sur ce qu'elle devait protéger : c'est l'**appelant
    MCP** qui doit emprunter la variante filtrée.
    """
    import inspect

    from backend.agents.echo import EchoAgent
    from backend.mcp_server import server

    agent = ast.parse(textwrap.dedent(
        inspect.getsource(EchoAgent.search_memories_pour_agent)))
    appels_agent = {ast.unparse(n.func) for n in ast.walk(agent)
                    if isinstance(n, ast.Call)}
    assert any(a.endswith("search_pour_agent") for a in appels_agent)

    mcp = ast.parse(textwrap.dedent(inspect.getsource(server.memory_search)))
    appels_mcp = {ast.unparse(n.func) for n in ast.walk(mcp)
                  if isinstance(n, ast.Call)}
    assert any(a.endswith("search_memories_pour_agent") for a in appels_mcp), (
        "l'outil MCP lit par le chemin système — ni portée, ni quarantaine")
    assert not any(a.endswith("echo.search_memories") for a in appels_mcp)


def test_les_outils_mcp_resolvent_le_projet_avant_de_lire_ou_d_ecrire():
    """Sans résolution, un identifiant inventé rendrait une liste vide au
    lieu d'un refus."""
    import inspect

    from backend.mcp_server import server

    for outil in (server.memory_remember, server.memory_search):
        arbre = ast.parse(textwrap.dedent(inspect.getsource(outil)))
        appels = {ast.unparse(n.func) for n in ast.walk(arbre)
                  if isinstance(n, ast.Call)}
        assert any(a.endswith("_projet_resolu") for a in appels), (
            f"{outil.__name__} ne résout pas le projet")


def test_aucune_seconde_politique_de_quarantaine():
    """Un `QuarantineManager` serait une seconde autorité de sécurité —
    ce que ce dépôt refuse partout ailleurs."""
    interdits = ("QuarantineManager", "MemorySecurityService",
                 "MemoryPolicyEngine")
    trouves: list[str] = []
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.ClassDef) and noeud.name in interdits:
                trouves.append(f"{fichier.relative_to(RACINE)}:{noeud.name}")
    assert not trouves, trouves


def test_la_confiance_ne_peut_pas_contourner_le_filtre():
    """`filtrer` ne lit que la provenance. Le jour où il lirait
    `confidence`, l'agent pourrait s'autoriser lui-même."""
    import inspect

    from backend.memory import confiance

    source = inspect.getsource(confiance.filtrer) + inspect.getsource(
        confiance.provenance_de)
    assert "confidence" not in source
