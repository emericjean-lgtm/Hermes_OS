# -*- coding: utf-8 -*-
"""Le controle d'ecriture de l'agent, rendu visible (G-22, HOS-271).

## Ce que la mesure a trouve

Sur le chemin de conversation lie a un projet, Hermes OS ouvre une session
Hermes Agent vivante par ACP. Avant chaque **edition de fichier**, l'agent
adresse un `session/request_permission` au client et **attend** ;
`HermesAgentACP._repondre` tranche sur la politique de Hermes OS.

Ce controle agit vraiment. Mesure du 2026-09-09, un seul tour reel :
**quatre decisions, trois refus** — l'agent a tente `/home/user/NOTE.md`,
`/home/emeri/NOTE.md` puis un troisieme chemin hors du dossier confie,
refuses ; la quatrieme tentative, au bon endroit, accordee. Et pourtant :
un `logger.warning` pour les refus, **rien du tout** pour les accords.

## Le chemin etait injoignable depuis l'Assistant

Second defaut, mesure : `harnais.disponible()` sonde le backend par un
`requests.get` **synchrone** sur son propre `/health`. Appelee depuis le
handler de conversation d'un uvicorn mono-worker, cette sonde bloque la
boucle — le serveur ne peut pas repondre a la question qu'il pose, et le
harnais etait **toujours** ecarte sur `ReadTimeout`. Le backend se
demandait s'il etait vivant pendant qu'il servait la requete qui posait la
question.

Deporte hors de la boucle, le chemin ACP est emprunte : le flux passe de
`tool_calls`/`tool_result` (chemin direct) a `thinking`/`content`
(harnais), et une decision reelle apparait au journal.

## Ce que ce journal ne prouve pas

`session/request_permission` ne porte que sur les **editions de fichiers**.
Le terminal de l'agent ne demande aucune permission : il execute. Un refus
visible ici ne prouve donc pas qu'une ecriture a ete empechee.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.security import journal_permissions as jp

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def journal_vide(monkeypatch):
    jp.vider()
    monkeypatch.setattr(jp, "_publier", lambda _e: None)
    yield
    jp.vider()


# ── Les issues ne se confondent pas ───────────────────────────────────

def test_les_deux_refus_ne_se_confondent_pas():
    """« hors du dossier confie » et « fichier qui definit le travail »
    sont deux faits differents. Les fondre perdrait la seule information
    qui dit a l'operateur ce qui s'est passe."""
    # Les valeurs sont epinglees **en litteral**, pas par les constantes :
    # une mutation qui rendait les deux identiques passait au vert, parce
    # que l'attendu se construisait a partir des memes constantes et se
    # collapsait avec elles. L'assertion doit porter sur ce que l'API et
    # l'interface consomment, pas sur le nom du symbole.
    assert jp.REFUSEE_HORS_WORKSPACE == "refusee_hors_workspace"
    assert jp.REFUSEE_PROTEGE == "refusee_protege"
    jp.consigner(issue=jp.REFUSEE_HORS_WORKSPACE, chemin="/a", detail="d")
    jp.consigner(issue=jp.REFUSEE_PROTEGE, chemin="/b", detail="d")
    issues = {e["issue"] for e in jp.decisions()["elements"]}
    assert issues == {"refusee_hors_workspace", "refusee_protege"}


def test_un_accord_est_consigne_aussi():
    """Un accord ne laissait aucune ligne : le journal ne montrait que ce
    qui avait ete refuse, donc jamais ce qui avait ete laisse passer."""
    jp.consigner(issue=jp.ACCORDEE, chemin="/ok", detail="allow_once")
    vue = jp.decisions()
    assert vue["total"] == 1 and vue["refus"] == 0
    assert vue["elements"][0]["issue"] == jp.ACCORDEE


def test_le_compte_de_refus_ne_compte_que_les_refus():
    jp.consigner(issue=jp.ACCORDEE, chemin="/1")
    jp.consigner(issue=jp.REFUSEE_HORS_WORKSPACE, chemin="/2")
    jp.consigner(issue=jp.SANS_OPTION, chemin="/3")
    assert jp.decisions()["refus"] == 2


def test_la_plus_recente_d_abord():
    jp.consigner(issue=jp.ACCORDEE, chemin="/vieille")
    jp.consigner(issue=jp.ACCORDEE, chemin="/neuve")
    assert jp.decisions()["elements"][0]["chemin"] == "/neuve"


# ── Un chiffre exact peut mentir ──────────────────────────────────────

def test_la_fenetre_dit_qu_elle_tronque():
    """Meme regle qu'en HOS-267 : presenter la taille d'une fenetre comme
    un total est un chiffre exact et faux."""
    for i in range(10):
        jp.consigner(issue=jp.ACCORDEE, chemin=f"/{i}")
    vue = jp.decisions(limite=3)
    assert vue["total"] == 3 and vue["tronque"] is True
    vue = jp.decisions(limite=50)
    assert vue["tronque"] is False


def test_le_journal_est_borne():
    """Un flux, pas une memoire : la trace durable vit au bus."""
    for i in range(jp.TAILLE_MAX + 40):
        jp.consigner(issue=jp.ACCORDEE, chemin=f"/{i}")
    assert len(jp.decisions(limite=10_000)["elements"]) == jp.TAILLE_MAX


def test_une_trace_qui_echoue_ne_casse_pas_la_decision(monkeypatch):
    """La decision est deja prise quand on arrive ici ; lever ferait
    echouer un tour pour une raison d'observabilite.

    On fait tomber **le bus**, pas `_publier` : c'est `_publier` qui porte
    la protection, et le remplacer aurait teste le bouchon au lieu du code.
    Une premiere version de ce test faisait exactement cela.
    """
    monkeypatch.undo()  # rend le vrai `_publier`, celui qui protege
    jp.vider()

    def bus_mort():
        raise RuntimeError("bus mort")

    monkeypatch.setattr("backend.core.event_hub.get_event_hub", bus_mort)
    jp.consigner(issue=jp.ACCORDEE, chemin="/ok")
    assert jp.decisions()["total"] == 1


# ── L'architecture : observer, pas decider ────────────────────────────

def test_le_journal_ne_decide_rien():
    """Une seconde politique ici serait l'autorite concurrente que le
    contrat interdit. La decision reste dans l'adaptateur ACP."""
    source = (RACINE / "backend" / "security"
              / "journal_permissions.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    noms = {n.id for n in ast.walk(arbre) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(arbre) if isinstance(n, ast.Attribute)}
    for interdit in ("_hors_workspace", "_touche_un_protege", "outcome",
                     "AegisEngine"):
        assert interdit not in noms, (
            f"le journal touche a {interdit} : il observe, il ne decide pas")


def test_les_topics_sont_declares():
    from backend.core.event_topics import SUBSYSTEM_TOPICS

    for t in ("agent.permission.accordee", "agent.permission.refusee"):
        assert t in SUBSYSTEM_TOPICS, t


def test_la_sonde_du_harnais_ne_bloque_pas_la_boucle():
    """Le defaut qui rendait le chemin ACP injoignable.

    `harnais.disponible` fait un `requests.get` synchrone vers le backend
    lui-meme. Appele directement dans le handler async d'un uvicorn
    mono-worker, il bloque la boucle qui doit repondre a la sonde — donc
    `ReadTimeout` a tous les coups, et le harnais toujours ecarte.

    Garde sur l'arbre syntaxique : l'appel doit rester derriere
    `asyncio.to_thread`, jamais nu dans la coroutine.
    """
    source = (RACINE / "backend" / "conversation"
              / "routes.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    nus = []
    for n in ast.walk(arbre):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "disponible"):
            continue
        # Un appel derriere `to_thread` apparait comme argument, pas comme
        # appel evalue directement.
        nus.append(n)
    enveloppes = {
        id(a) for n in ast.walk(arbre)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "to_thread" for a in n.args
    }
    restants = [n for n in nus if id(n) not in enveloppes]
    assert restants == [], (
        "`harnais.disponible` est appele nu dans une coroutine : il sonde "
        "le backend en synchrone et bloque la boucle qui doit lui repondre. "
        "Passez par `asyncio.to_thread`.")


def test_l_onglet_permissions_ne_depend_pas_de_la_vue_d_ensemble():
    """Le journal des permissions est local a Hermes OS : il reste lisible
    quand le gateway est mort. Or l'onglet etait imbrique sous le garde de
    `useAgentVue`, si bien qu'une panne du cerveau le rendait invisible —
    exactement au moment ou savoir ce qu'on a refuse compte le plus.

    Garde structurelle, et assumee comme telle : il n'y a pas de
    comportement a affirmer ici, seulement une imbrication a interdire.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "frontend" / "src"
              / "features" / "cerveau"
              / "cerveau-center.tsx").read_text(encoding="utf-8")
    garde = source.index("!data ? null")
    assert source.index('vue === "permissions"') < garde, (
        "l'onglet Permissions est rendu sous le garde de la vue d'ensemble : "
        "une panne du gateway le fait disparaitre")
