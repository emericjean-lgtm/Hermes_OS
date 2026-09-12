# -*- coding: utf-8 -*-
"""Un endpoint sans appelant frontend n'est pas une fonctionnalite (HOS-265).

## Le defaut que cette regle rend visible

HOS-235 l'a paye au prix fort : huit routes d'operations, correctes, testees,
posees sur `MissionControlAPI` — une surface que **rien ne montait**. Sur le
processus en marche, `GET /api/v1/operations` rendait `404`, et leurs tests
passaient parce qu'ils montaient le routeur eux-memes.

Le meme motif a produit les trois defauts les plus couteux du depot : le
pipeline de connecteurs, `Statut.PERDU` que rien ne posait, et deux controles
de securite livres, testes, marques faits, sans un seul appelant. Le §0 de la
roadmap maitre le nomme : `PRESENT` ne vaut pas `CALLED`, et `CALLED` ne vaut
pas `ACTUALLY USED`.

Ce test ferme la porte cote produit : **une route neuve doit avoir un
appelant frontend reel**, ou etre inscrite ici avec sa raison.

## Ce qu'il mesure, et ce qu'il ne mesure pas

Il cherche le chemin de chaque route `/api/v1/...` dans les sources de
`frontend/src`, en tolerant les parametres (`/agents/{id}/pause` retrouve
`/agents/${x}/pause`). Il ne prouve pas que l'appel est *execute* — un client
peut exister sans etre monte — mais il attrape ce qui n'a meme pas
d'appelant, et c'etait 39 pour cent des routes le 2026-09-07.

Le premier instrument ecrit pour cette mesure annoncait 144 orphelins : il
remplacait `{id}` par du vide et fabriquait `/agents//pause`, qui ne
correspond a rien. Trente-deux faux orphelins, trouves en relisant un chiffre
invraisemblable — la lecon de `CLAUDE.md`, et elle vaut aussi pour un
instrument qu'on ecrit soi-meme.

## L'inventaire n'est pas une permission

Les entrees ci-dessous sont une **dette constatee**, pas une norme. La liste
doit retrecir, jamais grandir : y ajouter une ligne est un acte visible en
revue, et c'est precisement l'effet recherche.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
SOURCES_FRONTEND = RACINE / "frontend" / "src"

#: Routes sans appelant frontend au 2026-09-07, relevees et gelees. Une
#: entree retiree parce que le frontend l'appelle enfin est un progres ; une
#: entree ajoutee doit porter sa raison dans le message de commit.
ORPHELINS_CONNUS: frozenset = frozenset({
    "/agents/status",
    "/alexandrie/sync/mark-outdated",
    "/classify",
    "/code-intelligence/analyze",
    "/code-intelligence/debug",
    "/code-intelligence/explain",
    "/code-intelligence/review",
    "/collaboration/consensus",
    "/collaboration/consensus/{proposal_id}/vote",
    "/collaboration/delegations",
    "/collaboration/delegations/{delegation_id}/accept",
    "/collaboration/delegations/{delegation_id}/complete",
    # G-16 (2026-09-12) retire /collaboration/history : appelee reellement
    # depuis client.ts (`/collaboration/history${qs}`), masquee jusqu'ici
    # par le trou d'interpolation de `_motif` corrige dans la meme passe.
    "/collaboration/messages/broadcast",
    "/collaboration/messages/conversation/{conversation_id}",
    "/collaboration/messages/unread",
    "/collaboration/review/{review_id}",
    "/documents/formats",
    "/documents/index",
    "/evolution/process/{task_id}",
    "/evolution/progression",
    "/explainability/explain",
    "/explainability/explanations",
    "/explainability/{decision_id}",
    "/files",
    "/files/apply",
    "/files/content",
    "/files/diff",
    # G-16 (2026-09-12) retire /filesystem/browse : meme trou d'interpolation
    # que /collaboration/history, appelant reel dans client.ts confirme.
    "/git/branch",
    "/git/branches",
    "/git/commit",
    "/git/diff",
    "/git/log",
    "/git/push",
    "/git/revert",
    "/healthz",
    "/legacy/memory/index",
    "/legacy/memory/search",
    "/legacy/skills",
    "/legacy/skills/{skill_id}",
    # G-16 (2026-09-12) retire /logs : meme trou d'interpolation, appelant
    # reel `` `/logs${qs}` `` dans client.ts. /logs/{session_id} reste EN
    # BAS malgre l'air de famille : sa seule correspondance est une coincidence de
    # texte dans un commentaire JSDoc de hermes.ts (« ... fichiers sous
    # `data/logs/` ... ») qui referme sur une apostrophe inverse, pas un
    # appelant. Verifie par lecture directe du site — aucun fetchJSON ne
    # construit ce chemin. Tenter de filtrer les commentaires du cote sonde
    # a ete essaye et abandonne : sur ce depot, ca supprime aussi du vrai
    # code (une regex `/\*.*?\*/` traverse les bornes de fichier) et a
    # fabrique 37 nouveaux faux orphelins instantanement — pire que le
    # defaut qu'elle visait a corriger. Limite connue, non resolue ici.
    "/logs/latency",
    "/logs/{session_id}",
    "/memory",
    "/memory/permanent",
    "/memory/project/{project_id}",
    "/memory/types",
    "/memory/{memory_id}/promote",
    # G-16 (2026-09-12) retire /models/benchmarks : meme trou
    # d'interpolation, appelant reel dans client.ts.
    "/models/catalogue/candidats",
    "/models/evolution",
    "/models/knowledge",
    "/operations/agents/{agent}",
    # G-16 (2026-09-12) retire /operations/checkpoints : meme trou
    # d'interpolation, appelant reel dans client.ts.
    "/planner/plan",
    "/planner/plan/template/{template_id}",
    "/planner/results",
    "/planner/results/{result_id}",
    "/planner/results/{result_id}/build",
    "/planner/templates",
    "/readyz",
    "/research",
    "/runtime",
    "/runtime/discovery/benchmarks",
    "/runtime/discovery/models",
    "/runtime/discovery/scan",
    "/runtime/discovery/stats",
    "/runtime/ktransformers/benchmark",
    "/runtime/ktransformers/discover",
    "/runtime/ktransformers/events",
    "/runtime/ktransformers/infer",
    "/runtime/ktransformers/load",
    "/runtime/ktransformers/models",
    "/runtime/ktransformers/models/{model_id}",
    "/runtime/ktransformers/optimize",
    "/runtime/ktransformers/orchestrator/candidates",
    "/runtime/ktransformers/resources",
    "/runtime/ktransformers/statistics",
    "/runtime/ktransformers/status",
    "/runtime/ktransformers/unload",
    "/runtime/orchestrator/decision/{decision_id}",
    "/runtime/orchestrator/evaluate",
    "/runtime/orchestrator/history",
    "/runtime/recovery/history",
    "/runtime/recovery/status",
    "/runtime/recovery/{incident_id}/retry",
    "/runtime/simulation/history",
    "/runtime/simulation/run",
    "/runtime/simulation/{simulation_id}",
    "/runtimes/types",
    "/runtimes/{name}/select",
    # G-36 les avait fait QUITTER la dette — le cockpit lit enfin la file
    # d'Aegis, celle qui garde les actions reelles. `/approval/*` y etait
    # entre a leur place, seul ajout que cette liste ait jamais recu.
    #
    # G-38 les retire des deux cotes : les routes n'existent plus. Une
    # entree d'orphelin qui designe une route absente ne garde rien et
    # laisse croire a une dette qui n'existe plus.
    "/security/check",
    "/security/evaluate",
    "/security/permissions/grant",
    "/security/permissions/revoke",
    "/security/threats/mitigate",
    "/skills/distribute",
    "/skills/search",
    "/skills/{skill_id}/index",
    "/skills/{skill_id}/use",
    "/snapshots",
    "/snapshots/{snapshot_id}/preview",
    "/snapshots/{snapshot_id}/restore",
    "/studio/animate",
    "/studio/assemble",
    "/studio/start-frame",
    "/system/status",
    "/tasks",
    "/tasks/{task_id}",
    "/verify",
    "/vision/analyze",
    "/workflows",
    "/workflows/runs/{run_id}",
    "/workflows/{workflow_id}",
    "/workflows/{workflow_id}/run",
    "/workflows/{workflow_id}/simulate",
    "/write",
})


def _routes_api() -> list:
    from backend.main import app

    prefixe = "/api/v1"
    return sorted({
        r.path[len(prefixe):] for r in app.routes
        if getattr(r, "path", "").startswith(prefixe + "/")
    })


def _sources_frontend() -> str:
    fichiers = list(SOURCES_FRONTEND.rglob("*.ts")) + list(
        SOURCES_FRONTEND.rglob("*.tsx"))
    return "".join(f.read_text(encoding="utf-8", errors="replace")
                   for f in fichiers)


def _motif(route: str) -> re.Pattern:
    """Le chemin, avec ses parametres rendus a ce qu'un template ecrit.

    `/agents/{agent_id}/pause` doit retrouver `/agents/${id}/pause`. Le
    segment substitue ne peut pas franchir un delimiteur de chaine, sans quoi
    le motif sauterait d'un litteral a l'autre et rendrait n'importe quelle
    route « appelee ».

    La fin est **ancree**, et une mutation a montre pourquoi : sans elle,
    `/bridge/capabilities` se trouvait a l'interieur de
    `/bridge/capabilities/refresh`, si bien que supprimer l'appel a la
    premiere ne faisait rougir personne. Toute route prefixe d'une autre
    heritait ainsi d'un appelant qu'elle n'avait pas. Ce qui suit le chemin
    doit clore le litteral (`` ` ``, `"`, `'`), ouvrir une requete (`?`,
    `&`), ou ouvrir une interpolation (`$`, pour `` `/logs${qs}` ``).

    G-16 (2026-09-12) a trouve 4 faux orphelins par cette omission :
    `/collaboration/history`, `/filesystem/browse`, `/models/benchmarks` et
    `/operations/checkpoints` s'ecrivent tous
    `` `/chemin${condition ? `?x=${v}` : ""}` `` cote frontend — le litteral
    est bien la, mais rien avant `$` ne fermait la chaine. Verifie sur les
    quatre call sites reels avant correction, pas sur le chiffre.
    """
    parts = [re.escape(s) for s in re.split(r"\{[^}]+\}", route)]
    return re.compile("[^`\"']*".join(parts) + "(?=[`\"'?&$])")


@pytest.fixture(scope="module")
def orphelins() -> set:
    blob = _sources_frontend()
    return {r for r in _routes_api() if not _motif(r).search(blob)}


def test_aucune_route_neuve_sans_appelant_frontend(orphelins):
    """La regle. Une route qui n'existait pas dans la dette et que personne
    n'appelle est un orphelin neuf — donc un produit qui n'existe pas."""
    neufs = sorted(orphelins - ORPHELINS_CONNUS)
    assert neufs == [], (
        "routes backend sans appelant frontend, et absentes de la dette "
        "constatee :\n  " + "\n  ".join(neufs) +
        "\n\nUn endpoint sans appelant frontend n'est pas une fonctionnalite "
        "produit. Cablez-le au cockpit, ou inscrivez-le dans "
        "`ORPHELINS_CONNUS` avec sa raison dans le message de commit.")


def test_l_inventaire_ne_pourrit_pas():
    """Une entree qui ne designe plus aucune route existante rend la dette
    fausse : elle donnerait l'impression d'un orphelin la ou il n'y a plus de
    route du tout."""
    connues = set(_routes_api())
    fantomes = sorted(ORPHELINS_CONNUS - connues)
    assert fantomes == [], (
        "entrees de `ORPHELINS_CONNUS` qui ne correspondent a aucune route :"
        "\n  " + "\n  ".join(fantomes) + "\n\nRetirez-les.")


def test_l_interpolation_ne_masque_pas_un_appelant_reel(orphelins):
    """G-16 : un consommateur legitime ne doit pas passer pour un orphelin.

    Ces cinq routes ont toutes un appelant reel dans `client.ts`, ecrit
    `` `/chemin${condition ? `?x=${v}` : ""}` `` — le `$` d'interpolation
    suit immediatement le chemin, sans guillemet ni backtick entre les deux.
    Avant le correctif de `_motif` (G-16, 2026-09-12), la sonde les classait
    orphelines : `?` n'apparait qu'a l'interieur de la branche conditionnelle,
    jamais colle au chemin lui-meme. Neutraliser le `$` dans `_motif` fait
    rougir ce test — c'est la mutation qui prouve qu'il teste bien le
    correctif et pas autre chose.
    """
    appelants_reels = {
        "/collaboration/history",
        "/filesystem/browse",
        "/logs",
        "/models/benchmarks",
        "/operations/checkpoints",
    }
    faussement_orphelines = sorted(appelants_reels & orphelins)
    assert faussement_orphelines == [], (
        "routes a appelant reel reclassees orphelines — regression du "
        "correctif d'interpolation de `_motif` :\n  "
        + "\n  ".join(faussement_orphelines))


def test_les_routes_du_pont_ont_un_appelant(orphelins):
    """Le pont doit respecter la regle qu'il introduit.

    Sans ce test, le premier orphelin de la serie serait celui qui a apporte
    l'interdiction — et rien ne l'aurait vu, puisque `ORPHELINS_CONNUS` gele
    l'etat *avant* le pont.
    """
    du_pont = sorted(r for r in _routes_api() if r.startswith("/bridge"))
    assert du_pont, "aucune route de pont montee — le routeur n'est pas servi"
    sans_appelant = sorted(set(du_pont) & orphelins)
    assert sans_appelant == [], (
        "le pont introduit ses propres orphelins :\n  "
        + "\n  ".join(sans_appelant))
