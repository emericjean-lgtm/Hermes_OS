# -*- coding: utf-8 -*-
"""ACP et Gateway ne convergent pas — mesure et garde (G-23, HOS-272).

## Ce que la mesure a montre

Les deux transports **partagent le magasin**. L'identifiant d'une session
ACP figure tel quel dans `session.list` du Gateway, et `session.resume`
l'accepte. C'est ce qui rend la convergence tentante.

Mais le partage s'arrete a la ligne stockee. Mesure du 2026-09-09, pendant
qu'un tour ACP tournait vraiment — 3242 fragments streames, `POEME.md` de
344 octets ecrit :

    session.resume(id ACP)   -> OK, handle d50a9c14
    running vu par Gateway   -> False
    approval.pending         -> {"approvals": []}
    session.steer            -> {"status": "queued", "text": "arrete"}
    session.interrupt        -> {"status": "interrupted"}

Le tour ACP s'est **termine normalement** et a ecrit son fichier. Les deux
controles ont annonce un succes en n'agissant sur rien : `resume` avait
materialise une **seconde session vivante** dans le processus Gateway, a
partir de la meme ligne stockee, et c'est elle qui a ete steeree puis
interrompue.

Une ligne stockee, deux sessions vivantes, deux processus. Les controles
agissent sur la vivante de **leur** processus.

## Decision : REJECT

Pas DEFER — « non demontre » serait trop doux. La convergence par
identifiant partage est **activement nuisible** : elle produit des succes
HTTP confiants qui ne touchent rien, c'est-a-dire exactement le defaut que
ce depot poursuit depuis `success: True` au-dessus d'un workspace vide.

Un adaptateur n'y changerait rien : il n'existe aucun canal entre le
processus ACP et le processus Gateway, et le seul moyen d'atteindre le tour
en cours est le transport qui le porte.

## Le chemin qui existe vraiment

ACP a son propre controle natif : `acp_adapter/server.py` expose
`async def cancel(session_id)` avec un `cancel_event`. L'interruption du
chat passe donc par **ACP**, pas par le Gateway — chaque transport avec ses
propres commandes, ce qui est aussi la lecture la plus simple de la regle
qui prime sur tout : Hermes Agent possede ses sessions et ses controles.

Notre client ACP ne l'emet pas encore. C'est un chantier, pas une
convergence.
"""
from __future__ import annotations

import ast
from pathlib import Path

from backend.bridge.hermes_agent_bridge import MUTATIONS_CONNUES

RACINE = Path(__file__).resolve().parents[2]

#: Les controles du Gateway qui rendent un succes sur une session qu'ils
#: viennent de materialiser eux-memes. Les offrir au produit pour piloter
#: le chat serait un bouton qui ment.
CONTROLES_DU_GATEWAY = ("session.steer", "session.interrupt",
                        "session.redirect", "approval.respond",
                        "clarify.respond", "secret.respond")


def test_aucun_controle_du_gateway_n_est_offert_comme_mutation():
    """La garde de G-23.

    `session.steer` et `session.interrupt` rendent `queued` et
    `interrupted` **meme quand le tour vise tourne dans un autre
    processus** — mesure a l'appui. Les declarer mutations les rendrait
    appelables depuis l'interface, ou ils affirmeraient avoir agi.
    """
    offerts = sorted(m for m in CONTROLES_DU_GATEWAY if m in MUTATIONS_CONNUES)
    assert offerts == [], (
        f"{offerts} sont offerts comme mutations. Mesure du 2026-09-09 : "
        "appeles sur l'identifiant d'une session ACP en cours, ils rendent "
        "un succes et n'agissent que sur la copie que `session.resume` "
        "vient de creer dans le processus Gateway. Le tour reel continue.")


def test_aucune_route_ne_pilote_le_chat_par_le_gateway():
    """Un endpoint suffirait a fabriquer le faux succes, meme sans passer
    par `MUTATIONS_CONNUES`."""
    source = (RACINE / "backend" / "api" / "routes"
              / "bridge.py").read_text(encoding="utf-8")
    for controle in CONTROLES_DU_GATEWAY:
        assert controle not in source, (
            f"`{controle}` est cable dans une route du pont : il ne peut "
            "pas atteindre un tour ACP, et rendrait un succes malgre tout.")


def test_le_service_de_mutation_ne_relaie_aucun_controle_de_tour():
    source = (RACINE / "backend" / "services"
              / "mutations_agent.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    litteraux = {n.value for n in ast.walk(arbre)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    fautifs = sorted(set(CONTROLES_DU_GATEWAY) & litteraux)
    assert fautifs == [], (
        f"{fautifs} sont relayes par le service de mutation : ils visent un "
        "tour vivant, que ce transport ne porte pas.")


def test_le_contrat_de_mutation_reste_sur_de_l_etat_stocke():
    """Ce que le Gateway peut vraiment changer, c'est l'etat **stocke** —
    une branche, un titre, une configuration. Pas un tour en cours.

    C'est la ligne de partage que G-23 etablit, et elle explique pourquoi
    les trois mutations existantes marchent : elles n'ont jamais vise le
    vivant.
    """
    # `skills/` s'ajoute en G-36 : le dossier des competences, son verrou
    # et son journal d'audit. C'est un troisieme MAGASIN, pas une
    # troisieme semantique — il est stocke, il survit au redemarrage
    # (mesure du 2026-09-11 : la pose et les decisions sont retrouvees par
    # un processus neuf), et il ne vise aucun tour vivant. La ligne de
    # partage que G-23 etablit ne bouge pas ; c'est la liste qui etait
    # trop etroite d'un magasin.
    MAGASINS_STOCKES = ("state.db", "config.yaml", "skills/")
    for methode, etat in MUTATIONS_CONNUES.items():
        assert etat.startswith("hermes-agent:"), (methode, etat)
        assert etat.split(":", 1)[1] in MAGASINS_STOCKES, (
            f"`{methode}` ecrit {etat} : le contrat ne porte que sur de "
            "l'etat stocke, jamais sur un tour vivant.")
