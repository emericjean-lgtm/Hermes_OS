# -*- coding: utf-8 -*-
"""Relier un tour de l'agent au Run qui l'a demande (G-32, HOS-280).

## La chaine, mesuree de bout en bout sur deux processus

    phase 1 (Hermes OS)  Run lie          : RUN-Z
                         requete ACP      : _meta.hermes.turnId = 2a374b49...
                         relation ecrite  : RUN-Z
    phase 2 (agent)      evenement Skill g32-une   -> client_turn_id=2a374b49...
                         evenement Skill g32-deux  -> client_turn_id=2a374b49...
    phase 3 (NOUVEAU     etiquette lue -> Run retrouve : RUN-Z
             processus)  etiquette etrangere          : (aucun)

**ADOPT.** Aucune identite ne change de proprietaire : Hermes OS garde
`run_id`, l'agent garde `task_id` et `session_id`, et l'etiquette est une
troisieme identite, opaque, que Hermes OS frappe et reconnait.

## Ce que la mesure a corrige dans ma lecture

Le chemin traverse `_run_coro`, qui pousse la coroutine vers une boucle
d'un **autre thread** par `run_coroutine_threadsafe`. J'avais conclu qu'un
`ContextVar` n'y survivrait pas et que le design etait mort. Mesure : il
survit — `call_soon_threadsafe` copie le contexte de l'appelant. La lecture
du code disait le contraire.

## Ou vit la relation, et pourquoi la

Sur le bus durable, parce que `backend/runs/registre.py` a deja tranche :
« le registre porte les runs ; le bus porte les evenements ; run_id les
relie ». Une table `turns` serait le second magasin d'evenements que ce
meme commentaire refuse.

Retention de sept jours (`EventBusImpl(retention_days=7)`) : la relation
est interrogeable une semaine, puis elaguee. C'est la politique du bus.

## La regle qui tient tout

Une etiquette n'est posee que si sa relation a ete **ecrite**. Sans bus, ou
sans Run lie, `etiquette_du_tour()` rend `""` et la requete part exactement
comme avant. Une etiquette sans relation promettrait une correlation que
personne ne pourrait resoudre — la moitie d'un contrat, que G-31 refusait
deja de livrer.
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest

from backend.runs import correlation

RACINE = Path(__file__).resolve().parents[2]


class _BusEnMemoire:
    """Le bus, reduit a ce que la correlation emploie : publier et rejouer."""

    def __init__(self, casse=False):
        self.evenements = []
        self.casse = casse

    def publish(self, topic, payload, *, publisher=None, causation_id=None):
        if self.casse:
            raise RuntimeError("bus indisponible")
        self.evenements.append(
            type("E", (), {"topic": topic, "payload": dict(payload),
                           "causation_id": causation_id})())

    async def replay(self, since, until=None, topic_pattern=None):
        for e in self.evenements:
            if topic_pattern is None or e.topic == topic_pattern:
                yield e


@pytest.fixture
def bus(monkeypatch):
    b = _BusEnMemoire()
    monkeypatch.setattr(correlation, "_bus", lambda: b)
    return b


@pytest.fixture
def sans_bus(monkeypatch):
    monkeypatch.setattr(correlation, "_bus", lambda: None)


# ── L'etiquette : ce qu'elle est, et ce qu'elle n'est pas ─────────────

def test_l_etiquette_n_est_derivee_de_rien(bus):
    """Envoyer le `run_id` comme etiquette donnerait l'identite de Hermes OS
    a l'agent. Elle doit donc n'avoir aucun lien calculable avec lui."""
    jeton = correlation.lier_run("RUN-SECRET")
    try:
        t = correlation.etiquette_du_tour()
    finally:
        correlation.delier_run(jeton)
    assert t and "RUN-SECRET" not in t
    assert t != "RUN-SECRET"
    assert len(t) == 32 and all(c in "0123456789abcdef" for c in t)


def test_deux_tours_du_meme_run_ont_deux_etiquettes(bus):
    """Un Run emet plusieurs tours. Les confondre perdrait lequel a produit
    quoi — et c'est precisement ce que la correlation doit rendre."""
    jeton = correlation.lier_run("RUN-A")
    try:
        a, b = correlation.etiquette_du_tour(), correlation.etiquette_du_tour()
    finally:
        correlation.delier_run(jeton)
    assert a != b
    assert asyncio.run(correlation.run_du_tour(a)) == "RUN-A"
    assert asyncio.run(correlation.run_du_tour(b)) == "RUN-A"


def test_sans_run_lie_aucune_etiquette(bus):
    """Le chat, une tache hors mission : rien a correler, donc rien a poser.
    Le chemin ACP reste octet pour octet celui d'avant."""
    assert correlation.run_courant() == ""
    assert correlation.etiquette_du_tour() == ""
    assert bus.evenements == []


def test_une_etiquette_n_est_jamais_posee_sans_sa_relation(monkeypatch):
    """La regle centrale. Si la relation ne peut pas etre ecrite — bus
    absent, publication en echec — l'etiquette n'est pas rendue.

    Une etiquette sans relation serait corrolable cote agent et
    introuvable cote Hermes OS : la moitie d'un contrat."""
    monkeypatch.setattr(correlation, "_bus", lambda: _BusEnMemoire(casse=True))
    jeton = correlation.lier_run("RUN-A")
    try:
        assert correlation.etiquette_du_tour() == ""
    finally:
        correlation.delier_run(jeton)


def test_sans_bus_le_tour_part_comme_avant(sans_bus):
    jeton = correlation.lier_run("RUN-A")
    try:
        assert correlation.etiquette_du_tour() == ""
    finally:
        correlation.delier_run(jeton)


# ── La resolution : ce qu'elle refuse ─────────────────────────────────

def test_une_etiquette_etrangere_n_est_associee_a_aucun_run(bus):
    """Hermes OS ne reconnait que ce qu'il a frappe. Un `turnId` venu
    d'ailleurs — un autre client ACP, un rejeu — n'est pas associe « au
    mieux »."""
    jeton = correlation.lier_run("RUN-A")
    try:
        correlation.etiquette_du_tour()
    finally:
        correlation.delier_run(jeton)
    assert asyncio.run(correlation.run_du_tour("venue-d-ailleurs")) is None


def test_une_etiquette_absente_n_est_associee_a_aucun_run(bus):
    """Un evenement Skill sans `client_turn_id` arrive avec `""`."""
    assert asyncio.run(correlation.run_du_tour("")) is None


def test_un_bus_absent_ne_fabrique_aucune_association(sans_bus):
    assert asyncio.run(correlation.run_du_tour("n-importe-quoi")) is None


# ── L'isolation ───────────────────────────────────────────────────────

def test_deux_runs_concurrents_ne_se_contaminent_pas(bus):
    """Mesure du chemin reel : `_run_coro` pousse vers une boucle d'un autre
    thread, et le contexte de l'appelant y est copie. Deux tours concurrents
    gardent donc chacun le leur."""
    async def tour(run):
        jeton = correlation.lier_run(run)
        try:
            await asyncio.sleep(0)
            return correlation.etiquette_du_tour()
        finally:
            correlation.delier_run(jeton)

    async def deux():
        return await asyncio.gather(tour("RUN-X"), tour("RUN-Y"))

    x, y = asyncio.run(deux())
    assert x != y
    assert asyncio.run(correlation.run_du_tour(x)) == "RUN-X"
    assert asyncio.run(correlation.run_du_tour(y)) == "RUN-Y"


def test_deux_runs_partageant_une_session_restent_distincts(bus):
    """`cle_de_session` groupe par PROJET (G-29) : deux missions d'un meme
    projet partagent la session de l'agent. C'est la raison d'etre de
    l'etiquette — la session ne peut pas designer le Run, elle le peut."""
    etiquettes = {}
    for run in ("RUN-P", "RUN-Q"):
        jeton = correlation.lier_run(run)
        try:
            etiquettes[run] = correlation.etiquette_du_tour()
        finally:
            correlation.delier_run(jeton)
    assert etiquettes["RUN-P"] != etiquettes["RUN-Q"]
    for run, t in etiquettes.items():
        assert asyncio.run(correlation.run_du_tour(t)) == run


def test_un_run_sans_evenement_reste_valide(bus):
    """Frapper une etiquette n'engage a rien : un Run dont l'agent ne mute
    aucune Skill laisse une relation sans consommateur, et c'est normal."""
    jeton = correlation.lier_run("RUN-MUET")
    try:
        t = correlation.etiquette_du_tour()
    finally:
        correlation.delier_run(jeton)
    assert asyncio.run(correlation.run_du_tour(t)) == "RUN-MUET"


# ── Ce qui part vraiment sur le fil ───────────────────────────────────

def _requete(turn_id: str) -> dict:
    """La charge utile `session/prompt` reellement construite par le client
    ACP — pas une reconstitution."""
    from backend.ral.adapters import hermes_agent_acp as acp

    envoyee = {}

    async def _echanger(session, methode, params, delai, collecte,
                        au_fil_de_l_eau=None):
        envoyee.update(json.loads(json.dumps(params)))
        return {"result": {}}

    client = acp.HermesAgentACP()
    client._session = acp.SessionAgent()  # noqa: SLF001
    client._session.session_id = "sess-1"  # noqa: SLF001
    client._session.verrou = asyncio.Lock()  # noqa: SLF001
    client._echanger = _echanger  # noqa: SLF001
    asyncio.run(client.tour("bonjour", delai=1, turn_id=turn_id))
    return envoyee


def test_la_requete_porte_l_etiquette_a_l_endroit_du_protocole():
    """La garde regarde la charge utile EMISE, pas la fonction qui la
    construit. `_meta` est le champ qu'ACP reserve aux extensions, et
    `_meta.hermes` l'espace que l'agent emploie deja lui-meme."""
    params = _requete("etiquette-42")
    assert params["_meta"]["hermes"]["turnId"] == "etiquette-42"
    assert params["sessionId"] == "sess-1"


def test_sans_etiquette_la_requete_ne_porte_aucune_clef_meta():
    """« Preserver les chemins ACP existants sans turnId » se verifie sur ce
    qui part : pas de `_meta` vide, pas de `turnId: ""` — la clef n'existe
    pas."""
    params = _requete("")
    assert "_meta" not in params
    assert set(params) == {"sessionId", "prompt"}


# ── Ce que la correlation ne devient pas ──────────────────────────────

def test_la_correlation_n_emploie_ni_task_id_ni_session_id():
    """Les deux appartiennent a l'agent, et sur le chemin ACP ils sont
    EGAUX (`run_conversation(..., task_id=session_id)`, G-30). Les employer
    rendrait une correlation qui n'en est pas une."""
    source = (RACINE / "backend" / "runs"
              / "correlation.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    docs = {id(n.body[0].value) for n in ast.walk(arbre)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef))
            and n.body and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)}
    noms = {n.id for n in ast.walk(arbre) if isinstance(n, ast.Name)}
    noms |= {n.attr for n in ast.walk(arbre) if isinstance(n, ast.Attribute)}
    noms |= {n.value for n in ast.walk(arbre)
             if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and id(n) not in docs}
    for identite in ("task_id", "session_id"):
        assert identite not in noms, f"la correlation emploie `{identite}`"


def test_la_correlation_ne_cree_aucune_table():
    """« Le registre porte les runs ; le bus porte les evenements. » Une
    table `turns` serait le second magasin d'evenements que
    `backend/runs/registre.py` refuse explicitement."""
    source = (RACINE / "backend" / "runs"
              / "correlation.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    litteraux = {n.value for n in ast.walk(arbre)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for interdit in ("CREATE TABLE", "INSERT INTO", "sqlite3"):
        assert not any(interdit in x for x in litteraux if len(x) < 300), (
            f"la correlation porte `{interdit}`")


def test_le_topic_est_declare_dans_l_enum():
    """« New topics must be added here rather than using raw strings. »
    Publier sur une chaine libre contournerait le seul endroit ou l'on peut
    voir ce que ce systeme emet."""
    from backend.ral.event_bus import Topic

    assert Topic(correlation.TOPIC_TOUR) is Topic.RUN_TURN_EMITTED


def test_le_run_lie_vient_d_une_correspondance_enregistree():
    """`execute_task` resout `execution_id -> run_id` par la table que
    `_ouvrir_le_run` a posee. Deviner — le dernier Run, le plus recent —
    serait la correlation synthetique que G-29 a REJETEE."""
    source = (RACINE / "backend" / "execution"
              / "mission_executor.py").read_text(encoding="utf-8")
    debut = source.index("def execute_task")
    corps = source[debut:source.index("def ", debut + 20)]
    assert "self._runs.get(sm._meta.execution_id" in corps, (
        "le Run lie ne vient pas de la correspondance enregistree")
    for devinette in ("popitem", "[-1]", "last=", "max(", "sorted("):
        assert devinette not in corps, f"`{devinette}` devine un Run"


# ── Deux gardes que des mutations ont trouvees absentes ───────────────

def test_une_reprise_apres_session_morte_garde_la_meme_etiquette(bus):
    """Un processus d'agent qui meurt en plein tour est repris : la session
    est rouverte et le message renvoye. C'est le **meme tour logique** —
    lui donner une seconde etiquette ferait croire a deux tours, et un Run
    paraitrait avoir demande deux fois ce qu'il a demande une.

    Trouve par mutation : rien ne gardait cette propriete."""
    import asyncio as _a

    from backend.ral.adapters.sessions_de_mission import SessionsDeMission

    vues = []

    # L'etat d'echec est PARTAGE : la reprise passe par `_ouvrir`, qui
    # fabrique un client NEUF. Un drapeau d'instance ferait remourir le
    # second, et le test mesurerait sa propre maladresse.
    encore_vivant = {"non": True}

    class ClientQuiMeurtUneFois:

        async def ouvrir(self, workspace, reprendre=""):
            return type("S", (), {"session_id": "s1", "reprise": False})()

        async def tour(self, texte, *, delai=0, au_fil_de_l_eau=None, turn_id=""):
            vues.append(turn_id)
            if encore_vivant["non"]:
                encore_vivant["non"] = False
                raise RuntimeError("processus mort en plein tour")
            return type("T", (), {"texte": "ok", "erreur": ""})()

        async def choisir_modele(self, m):
            return None

        async def fermer(self):
            return None

    reg = SessionsDeMission(fabrique=ClientQuiMeurtUneFois)
    jeton = correlation.lier_run("RUN-REPRISE")
    try:
        _a.run(reg.tour("mission:M", "w", "un"))
    finally:
        correlation.delier_run(jeton)

    assert len(vues) == 2, f"la reprise n'a pas eu lieu : {vues}"
    assert vues[0] == vues[1], (
        "la reprise a refrappe une etiquette : un tour en paraitrait deux")
    assert vues[0], "aucune etiquette posee"


def test_la_liaison_du_run_est_relachee_meme_en_cas_d_echec():
    """Sans `finally`, une tache qui leve laisserait son Run lie, et la
    tache suivante — d'un autre Run, ou d'aucun — heriterait de lui. La
    contamination serait silencieuse et l'etiquette pointerait le mauvais
    Run.

    La garde est structurelle et l'assume : elle verifie que la liaison est
    posee dans un `try` dont le `finally` la relache. Trouve par mutation —
    aucun test de comportement ne couvrait le chemin d'echec."""
    source = (RACINE / "backend" / "execution"
              / "mission_executor.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    fonction = next(n for n in ast.walk(arbre)
                    if isinstance(n, ast.FunctionDef) and n.name == "execute_task")

    def _appels(noeud):
        return {getattr(c.func, "attr", None) or getattr(c.func, "id", None)
                for c in ast.walk(noeud) if isinstance(c, ast.Call)}

    protege = [t for t in ast.walk(fonction)
               if isinstance(t, ast.Try) and t.finalbody
               and "delier_run" in _appels(ast.Module(body=t.finalbody,
                                                      type_ignores=[]))]
    assert protege, (
        "aucun `finally` ne relache la liaison du Run : une tache qui leve "
        "la laisserait fuir vers la suivante")
