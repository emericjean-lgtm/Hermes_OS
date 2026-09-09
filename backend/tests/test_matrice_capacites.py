# -*- coding: utf-8 -*-
"""Un nom sonde doit exister dans le runtime (G-19, HOS-268).

## L'incident

HOS-265 a conclu « le fork n'a pas de RPC ». Faux : le fork existe, il
s'appelle `session.branch`. La negociation avait mesure juste — elle
rapportait fidelement que `session.fork` ne repond pas — mais la **liste
des noms a sonder** etait ecrite de memoire. Une liste de memoire ne vaut
pas mieux qu'une specification de memoire, et ce depot le sait pour la
capacite `tools` d'Ollama, pour les toolsets CLI et pour trois campagnes de
mesure.

Le defaut n'etait donc pas dans l'instrument mais dans son vocabulaire, et
aucun test ne regardait le vocabulaire.

## Ce que la confrontation a montre

Releve du registre reel de v0.21.0 : **206 methodes**, la ou le pont en
sondait 62. Sur les trois noms declares absents, un seul l'etait vraiment
sous un autre nom (`fork`) ; les deux autres n'existent pas du tout — mais
ils avaient ete **inventes**, et leur absence ne prouvait donc rien.

La matrice annoncait « 15 completes sur 18 ». Reconstruite depuis le
registre, elle annonce 19 sur 19 : elle mesurait le vocabulaire, pas le
runtime.

## Ce que ces tests empechent

Qu'un nom invente reentre dans la matrice. Le releve est verse au depot,
date et empreint ; s'il ne correspond plus a l'agent installe, la garde le
dit plutot que de valider des noms contre un inventaire perime — meme
lecon que G-15.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.bridge.hermes_agent_bridge import (
    METHODES_PAR_CAPACITE,
    SANS_RPC,
)

RACINE = Path(__file__).resolve().parents[2]
RELEVE = RACINE / "config" / "gateway_registre.json"


@pytest.fixture(scope="module")
def releve() -> dict:
    assert RELEVE.exists(), (
        f"{RELEVE} manquant. Relevez le registre du runtime avec "
        "`.venv/Scripts/python.exe scripts/registre_gateway.py` : sans lui, "
        "rien ne verifie que les noms sondes existent.")
    return json.loads(RELEVE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registre(releve) -> set:
    return set(releve["methodes"])


def test_les_noms_sondes_existent_dans_le_runtime(registre):
    """La garde qui aurait attrape `session.fork` le premier jour."""
    declares = {n for groupe in METHODES_PAR_CAPACITE.values() for n in groupe}
    inventes = sorted(declares - registre)
    assert inventes == [], (
        f"noms sondes qui n'existent pas dans le runtime : {inventes}.\n"
        "Une absence mesuree sur un nom invente ne prouve rien — elle "
        "fabrique un « absent » qui n'existe que dans notre vocabulaire. "
        "Cherchez l'equivalent fonctionnel dans "
        "`config/gateway_registre.json` avant de conclure.")


def test_une_surface_sans_rpc_n_a_vraiment_aucune_methode(registre):
    """« Absent » disait deux choses : « le runtime ne sait pas le faire »
    et « le runtime le fait sans nous laisser le demander ».

    `SANS_RPC` porte la seconde, et seulement si le registre entier le
    confirme — sinon c'est encore un nom mal cherche.
    """
    for surface in SANS_RPC:
        racine = surface.split("_")[0]
        trouvees = sorted(m for m in registre if m.startswith(f"{racine}."))
        assert trouvees == [], (
            f"`{surface}` est declaree sans RPC, mais le registre expose "
            f"{trouvees}. Raccordez-les au lieu de les declarer absentes.")


def test_chaque_surface_sans_rpc_porte_sa_preuve():
    """Une entree sans justification redeviendrait un « absent » de
    memoire, ce que cette passe corrige."""
    for surface, raison in SANS_RPC.items():
        # Une justification doit nommer ce qui a ete **cherche** : sans
        # cela on retombe sur « absent » affirme de memoire, qui est le
        # defaut que G-19 corrige. Une mutation qui vidait la premiere
        # phrase restait verte tant que le seuil ne portait que sur la
        # longueur totale.
        assert len(raison) > 80, (
            f"`{surface}` est declaree sans RPC sans dire ce qui a ete "
            "cherche ni ou vit la capacite.")
        assert any(indice in raison for indice in
                   ("registre", "`", "toolset", "methode")), (
            f"`{surface}` n'indique ni ce qui a ete cherche dans le "
            "registre ni ou vit la capacite : c'est un « absent » de "
            "memoire, pas une mesure.")


def test_une_absence_verifiee_ne_disparait_pas_de_la_charge_utile():
    """Corriger la matrice ne doit pas faire **s'evaporer** une absence.

    `memory` s'affichait « absente » tant qu'un faux nom la representait.
    Retirer ce nom l'aurait fait disparaitre de l'ecran — on aurait
    remplace une absence mal nommee par un silence, ce qui est pire :
    l'operateur en conclurait que la memoire est disponible.

    Une mutation a trouve ce trou : supprimer `sans_rpc` de la charge utile
    ne faisait rougir personne.
    """
    from backend.bridge.hermes_agent_bridge import NegociationRuntime

    charge = NegociationRuntime(empreinte="e", version="v", commit="c",
                                mesure_le=0.0).as_dict()
    assert "sans_rpc" in charge, (
        "la negociation ne porte plus les surfaces sans RPC : une absence "
        "verifiee redevient un silence")
    portees = {s["nom"] for s in charge["sans_rpc"]}
    assert portees == set(SANS_RPC), (
        f"charge utile {sorted(portees)} != contrat {sorted(SANS_RPC)}")
    for surface in charge["sans_rpc"]:
        assert surface["raison"].strip(), (
            f"`{surface['nom']}` est annoncee sans RPC sans dire pourquoi")


def test_le_releve_correspond_a_l_agent_installe(releve):
    """Un releve qui survit a ce qu'il decrit ment (G-15).

    Si l'agent a bouge, les noms valides ci-dessus le sont contre un
    inventaire perime — donc contre rien.
    """
    from backend.bridge import HermesAgentBridge

    racine_agent = Path(
        HermesAgentBridge()._cfg().hermes_home) / "hermes-agent"  # noqa: SLF001
    if not racine_agent.exists():
        pytest.fail(
            "Hermes Agent n'est pas installe a l'emplacement attendu : la "
            "fraicheur du releve ne peut pas etre verifiee, et les noms "
            "sondes ne sont donc valides contre rien.")
    empreinte, _, _ = HermesAgentBridge().empreinte_runtime()
    assert releve["empreinte"] == empreinte, (
        f"releve pris pour {releve['empreinte']}, agent installe "
        f"{empreinte}. Relancez `scripts/registre_gateway.py` : valider des "
        "noms contre un inventaire perime ne prouve rien.")


def test_le_releve_couvre_tout_le_registre_pas_un_sous_ensemble(registre):
    """Une premiere version du releveur lisait les decorateurs sur l'arbre
    syntaxique et n'en voyait que 110 sur 206, faute de connaitre
    `_room_method`, `_rpc` et leurs pareils.

    Un inventaire partiel est pire qu'aucun : il donne l'assurance d'avoir
    verifie. Ce test tient un plancher grossier — il ne prouve pas la
    completude, il attrape un releve manifestement tronque.
    """
    assert len(registre) >= 200, (
        f"registre a {len(registre)} methodes : un releve complet de "
        "v0.21.0 en compte 206. Verifiez que `tui_gateway.entry` est bien "
        "importe par le releveur — c'est lui qui charge les modules "
        "`methods_*`.")
    for prefixe in ("session.", "mcp.", "groups.", "profiles.", "projects."):
        assert any(m.startswith(prefixe) for m in registre), (
            f"aucune methode `{prefixe}` : releve tronque")
