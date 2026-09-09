# -*- coding: utf-8 -*-
"""Qui est autorite sur l'etat de Hermes Agent (G-18, HOS-267).

## Le contrat, tel que la mesure l'a etabli

Trois choses distinctes, trois proprietaires — et c'est la confusion entre
les deux premieres qui rendait la question difficile :

    la conversation stockee         Hermes Agent      state.db, durable
    la session vivante              le gateway        ephemere
    le recit de ce qu'on a demande  Hermes OS         son bus d'evenements

Mesure du 2026-09-09, sur le vrai runtime :

- `session.resume` **ne mute rien**. Empreinte de `state.db` identique
  avant/apres ; seuls `-wal` et `-shm` bougent, ce qui est la comptabilite
  de lecture de SQLite. Et son handle meurt avec le processus — `4001
  session not found` apres redemarrage. Ce n'est donc pas une mutation
  mais une **activation**, et la presenter comme durable serait un mensonge
  d'interface.
- `session.branch` **mute vraiment** : contenu de `state.db` change, et la
  nouvelle cle est retrouvee par un processus neuf. Elle est **additive** —
  le parent reste intact.

## Ce que ces tests empechent

Qu'un futur appelant ouvre `state.db` lui-meme. Ce serait une seconde
autorite sur un etat de 114 Mio dont le schema, le WAL et les transactions
appartiennent a un autre programme — et le jour ou les deux ecrivent, c'est
la base de l'utilisateur qui arbitre.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.bridge.hermes_agent_bridge import (
    MUTATIONS_CONNUES,
    HermesAgentBridge,
    MutationInconnue,
)
from backend.services import mutations_agent

RACINE = Path(__file__).resolve().parents[2]


class _PontFaux:
    def __init__(self, reponses=None, leve=None):
        self.reponses = reponses or {}
        self.leve = leve
        self.appels: list = []

    def appeler(self, methode, params=None, timeout=None):
        self.appels.append((methode, params))
        if self.leve is not None:
            raise self.leve
        return self.reponses.get(
            methode, {"error": {"code": 4001, "message": "session not found"}})

    def demander_mutation(self, methode, params=None, timeout=None):
        if methode not in MUTATIONS_CONNUES:
            raise MutationInconnue(methode)
        return self.appeler(methode, params, timeout)


@pytest.fixture
def pont(monkeypatch):
    faux = _PontFaux()
    monkeypatch.setattr(mutations_agent, "_pont", lambda: faux)
    monkeypatch.setattr(mutations_agent, "_tracer", lambda *a, **k: None)
    return faux


# ── L'autorite : Hermes OS demande, il n'ecrit pas ────────────────────

def test_aucun_module_hermes_os_n_ouvre_l_etat_de_l_agent():
    """La garde centrale de G-18.

    `state.db` fait 114 Mio, appartient a l'agent, et deux programmes qui
    l'ecrivent, c'est la base de l'utilisateur qui tranche. Hermes OS ne
    l'ouvre donc jamais : il demande, par l'API que l'agent expose.
    """
    coupables: list[str] = []
    for f in (RACINE / "backend").rglob("*.py"):
        if "tests" in f.parts:
            continue
        arbre = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        for n in ast.walk(arbre):
            # Une chaine qui nomme state.db et qu'on passe a quelque chose
            # d'ouvrant : c'est le motif qu'on interdit.
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if n.func.attr in {"connect", "acquire", "open_database"}:
                    litteraux = " ".join(
                        a.value for a in ast.walk(n)
                        if isinstance(a, ast.Constant) and isinstance(a.value, str))
                    if "state.db" in litteraux:
                        coupables.append(f"{f.relative_to(RACINE).as_posix()}")
    assert coupables == [], (
        "des modules Hermes OS ouvrent l'etat natif de l'agent : "
        f"{coupables}. Demandez la mutation a l'agent au lieu de l'ecrire.")


def test_le_home_de_l_agent_ne_sert_qu_a_lancer_pas_a_ecrire():
    """`hermes_home` peut poser un `cwd` et un environnement ; il ne doit
    pas devenir une racine d'ecriture.

    Sans cette garde, la premiere fonction qui aurait besoin d'un fichier
    « juste a cote des sessions » l'y aurait pose, et Hermes OS aurait
    commence a posseder un bout du home de l'agent sans decision.
    """
    coupables: list[str] = []
    for f in (RACINE / "backend").rglob("*.py"):
        if "tests" in f.parts:
            continue
        source = f.read_text(encoding="utf-8", errors="replace")
        if "hermes_home" not in source:
            continue
        arbre = ast.parse(source)
        for n in ast.walk(arbre):
            if not (isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr in {"write_text", "write_bytes", "mkdir",
                                        "unlink", "touch"}):
                continue
            noms = {x.attr for x in ast.walk(n) if isinstance(x, ast.Attribute)}
            if "hermes_home" in noms:
                coupables.append(f.relative_to(RACINE).as_posix())
    assert coupables == [], (
        f"ecriture sous le home de l'agent : {coupables}")


def test_une_methode_hors_contrat_n_est_jamais_relayee():
    """Le pont ne fabrique pas d'API : ce que le runtime ne sert pas ne
    part pas. Refuser **avant** l'envoi, pas apres l'erreur."""
    pont = HermesAgentBridge(config=type("C", (), {
        "hermes_home": "x", "python_exe": "y"})())
    with pytest.raises(MutationInconnue):
        pont.demander_mutation("session.delete", {"session_id": "peu importe"})


def test_le_contrat_ne_declare_que_des_mutations_additives():
    """Une mutation qui ecrase ou supprime demanderait une autre
    conversation que celle-ci — reprise, confirmation, tracabilite du
    contenu perdu. Tant qu'elle n'a pas eu lieu, le contrat n'en porte
    aucune."""
    interdits = ("delete", "remove", "reset", "clear", "purge", "drop")
    fautives = [m for m in MUTATIONS_CONNUES
                if any(mot in m.lower() for mot in interdits)]
    assert fautives == [], (
        f"mutations destructives declarees sans decision : {fautives}")


# ── Le comportement : un refus est un resultat ────────────────────────

def test_un_refus_du_runtime_n_est_pas_une_panne(pont):
    """`4001 session not found` revient en `applique: false` avec sa
    raison, pas en exception : l'interface doit pouvoir distinguer « le
    runtime a dit non » de « le transport est mort »."""
    resultat = mutations_agent.brancher_session("cle-inconnue")
    assert resultat["applique"] is False
    assert resultat["erreur"] and "4001" in resultat["erreur"]
    assert resultat["cle_stockee"] is None


def test_une_panne_de_transport_ne_leve_pas_non_plus(monkeypatch):
    monkeypatch.setattr(mutations_agent, "_tracer", lambda *a, **k: None)
    monkeypatch.setattr(mutations_agent, "_pont",
                        lambda: _PontFaux(leve=OSError("gateway mort")))
    resultat = mutations_agent.brancher_session("peu-importe")
    assert resultat["applique"] is False
    assert "gateway mort" in resultat["erreur"]


def test_une_branche_demande_d_abord_l_activation(pont):
    """`session.branch` est `live=True` : brancher exige une session
    vivante. Les deux gestes appartiennent a l'agent ; Hermes OS ne fait
    que les demander dans l'ordre."""
    pont.reponses["session.resume"] = {"result": {"session_id": "handle42"}}
    pont.reponses["session.branch"] = {
        "result": {"stored_session_id": "neuve", "parent": "vieille",
                   "title": "T", "message_count": 3}}
    resultat = mutations_agent.brancher_session("vieille", "T")
    assert [m for m, _ in pont.appels] == ["session.resume", "session.branch"]
    # La branche porte le **handle runtime**, jamais la cle stockee : le
    # gateway refuserait la seconde, et la confusion entre les deux est
    # exactement ce que G-18 a demele.
    assert pont.appels[1][1]["session_id"] == "handle42"
    assert resultat["applique"] is True and resultat["cle_stockee"] == "neuve"


def test_un_refus_de_la_branche_elle_meme_reste_un_resultat(pont):
    """Une mutation a fait apparaitre ce trou : tous les autres cas etaient
    refuses des l'**activation**, si bien que remplacer la gestion d'erreur
    de la branche par une exception ne faisait rougir personne.

    Le runtime refuse legitimement de brancher une session sans historique
    (`4008 nothing to branch`), et ce refus-la doit se lire dans
    l'interface, pas exploser en 500.
    """
    pont.reponses["session.resume"] = {"result": {"session_id": "handle42"}}
    pont.reponses["session.branch"] = {
        "error": {"code": 4008, "message": "nothing to branch"}}
    resultat = mutations_agent.brancher_session("vieille")
    assert resultat["applique"] is False
    assert "4008" in resultat["erreur"] and "nothing to branch" in resultat["erreur"]
    assert resultat["cle_stockee"] is None


def test_une_activation_sans_handle_ne_branche_rien(pont):
    """Sans handle, brancher enverrait `session_id: ''` — et le runtime
    repondrait sur *une autre* session, ou sur aucune."""
    pont.reponses["session.resume"] = {"result": {}}
    resultat = mutations_agent.brancher_session("vieille")
    assert resultat["applique"] is False
    assert [m for m, _ in pont.appels] == ["session.resume"]


# ── La trace appartient a Hermes OS, pas a l'agent ────────────────────

def test_la_demande_et_son_issue_sont_tracees_chez_hermes_os(monkeypatch):
    """Une ecriture reelle sans trace cote OS serait la seule ecriture du
    depot que le journal ignore. La trace vit dans le bus de Hermes OS —
    pas dans `state.db`, qui ne lui appartient pas."""
    traces: list = []
    monkeypatch.setattr(mutations_agent, "_tracer",
                        lambda topic, charge: traces.append(topic))
    faux = _PontFaux({
        "session.resume": {"result": {"session_id": "h"}},
        "session.branch": {"result": {"stored_session_id": "n", "parent": "p",
                                      "title": "t", "message_count": 1}}})
    monkeypatch.setattr(mutations_agent, "_pont", lambda: faux)
    mutations_agent.brancher_session("p")
    assert traces == ["bridge.mutation.demandee", "bridge.mutation.appliquee"]


def test_un_refus_se_trace_aussi(monkeypatch):
    traces: list = []
    monkeypatch.setattr(mutations_agent, "_tracer",
                        lambda topic, charge: traces.append(topic))
    monkeypatch.setattr(mutations_agent, "_pont", lambda: _PontFaux())
    mutations_agent.brancher_session("inconnue")
    assert traces == ["bridge.mutation.demandee", "bridge.mutation.refusee"]


def test_les_topics_de_trace_sont_declares():
    """Un topic absent de `EVENT_TYPES` est delivre avec un avertissement
    et reste invisible aux filtres — donc intracable en pratique."""
    from backend.core.event_topics import SUBSYSTEM_TOPICS

    for topic in ("bridge.mutation.demandee", "bridge.mutation.appliquee",
                  "bridge.mutation.refusee"):
        assert topic in SUBSYSTEM_TOPICS, f"{topic} non declare"
