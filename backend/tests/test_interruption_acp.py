# -*- coding: utf-8 -*-
"""Interrompre le tour que l'utilisateur regarde (G-24, HOS-273).

## Ce que la mesure a etabli

`session/cancel` est le mecanisme **natif d'ACP**, et il atteint vraiment
le tour en cours. Meme demande, meme modele :

    sans annulation              50 s   9898 caracteres
    cancel a t+12s               12 s      0 caractere
    cancel a t+12s, MAUVAIS id  195 s  14120 caracteres

Le controle est donc reel *et* correle : un identifiant errone laisse le
tour aller au bout. C'est la difference avec le Gateway, ou
`session.interrupt` rendait `interrupted` sur une session qu'il venait de
materialiser lui-meme pendant que le vrai tour continuait (G-23).

De bout en bout, par la route HTTP :

    reference                    217 s   564 caracteres
    POST /cancel a t+15s          17 s     0 caractere

## Les deux faux controles que cette passe corrige

`POST /conversation/{id}/cancel` marquait la conversation `CANCELLED` cote
Hermes OS et rendait `"success": true, "status": "cancelled"` **sans
toucher le tour**. Et dans l'interface, `stop` n'appelait que
`abort()` sur le `fetch` : le navigateur cessait de lire, l'agent
continuait d'ecrire — sur le GPU, dans le workspace et dans l'historique.

Les deux affirmaient avoir arrete quelque chose. Aucun ne le faisait.

## Ce que `tour_interrompu` dit, et ne dit pas

Il dit que l'ordre est **parti** vers une session vivante. Pas que le tour
s'est arrete : `session/cancel` est une notification sans reponse, et
l'agent rend silencieusement pour une session qu'il ne connait plus. Un
booleen d'emission, jamais une interruption constatee.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]


class _FauxProc:
    def __init__(self, returncode=None):
        self.returncode = returncode
        self.ecrits: list = []
        self.stdin = self

    def write(self, data):
        self.ecrits.append(data.decode("utf-8", "replace"))

    async def drain(self):
        return None


def _client(session_id="sess-1", proc=None, sans_session=False):
    from backend.ral.adapters.hermes_agent_acp import HermesAgentACP, SessionAgent

    c = HermesAgentACP()
    if sans_session:
        c._session = None  # noqa: SLF001
        return c, None
    s = SessionAgent()
    s.session_id = session_id
    s.proc = proc if proc is not None else _FauxProc()
    c._session = s  # noqa: SLF001
    return c, s


# ── L'ordre part, et il porte le bon identifiant ──────────────────────

@pytest.mark.asyncio
async def test_l_annulation_porte_l_identifiant_de_la_session():
    """Mesure : un identifiant errone laisse le tour aller au bout (195 s
    contre 12 s). L'ordre doit donc porter celui de la session visee."""
    import json

    c, s = _client(session_id="la-bonne")
    assert await c.annuler() is True
    envoye = json.loads(s.proc.ecrits[0])
    assert envoye["method"] == "session/cancel"
    assert envoye["params"]["sessionId"] == "la-bonne"
    assert "id" not in envoye, (
        "`session/cancel` est une notification : lui donner un identifiant "
        "ferait attendre une reponse qui ne vient jamais")


@pytest.mark.asyncio
async def test_sans_session_vivante_on_n_annule_rien():
    """Le faux controle que G-23 a mesure sur le Gateway n'a pas a renaitre
    ici : sans session, `False`, jamais un succes de facade."""
    c, _ = _client(sans_session=True)
    assert await c.annuler() is False


@pytest.mark.asyncio
async def test_un_processus_mort_n_est_pas_une_annulation():
    c, s = _client(proc=_FauxProc(returncode=0))
    assert await c.annuler() is False
    assert s.proc.ecrits == []


@pytest.mark.asyncio
async def test_une_session_sans_identifiant_n_annule_rien():
    c, s = _client(session_id="")
    assert await c.annuler() is False
    assert s.proc.ecrits == []


@pytest.mark.asyncio
async def test_une_ecriture_impossible_ne_leve_pas():
    """Une annulation qui echoue ne doit pas faire echouer la requete : on
    rend `False`, et l'appelant n'affirme rien."""
    class _Casse(_FauxProc):
        def write(self, data):
            raise OSError("tuyau ferme")

    c, _ = _client(proc=_Casse())
    assert await c.annuler() is False


# ── Le registre adresse la bonne cle ──────────────────────────────────

@pytest.mark.asyncio
async def test_le_registre_n_interrompt_que_la_cle_demandee():
    from backend.ral.adapters.sessions_de_mission import SessionsDeMission

    appels: list = []

    class _Client:
        def __init__(self, nom):
            self.nom = nom

        async def annuler(self):
            appels.append(self.nom)
            return True

    r = SessionsDeMission()
    from backend.ral.adapters.sessions_de_mission import _Entree

    r._entrees["projet:a"] = _Entree(client=_Client("a"), workspace="wa")  # noqa: SLF001
    r._entrees["projet:b"] = _Entree(client=_Client("b"), workspace="wb")  # noqa: SLF001
    assert await r.interrompre("projet:b") is True
    assert appels == ["b"], "une autre session a ete interrompue"


@pytest.mark.asyncio
async def test_une_cle_inconnue_ne_dit_pas_avoir_interrompu():
    from backend.ral.adapters.sessions_de_mission import SessionsDeMission

    assert await SessionsDeMission().interrompre("projet:fantome") is False


# ── L'architecture : ACP pour un tour, jamais le Gateway ──────────────

def test_l_annulation_n_emprunte_pas_le_gateway():
    """G-23 a mesure que `session.interrupt` du Gateway rend un succes en
    agissant sur une autre session. Le chemin d'annulation ne doit donc
    jamais passer par la."""
    for module in ("backend/ral/adapters/sessions_de_mission.py",
                   "backend/conversation/routes.py"):
        source = (RACINE / module).read_text(encoding="utf-8")
        arbre = ast.parse(source)
        litteraux = {n.value for n in ast.walk(arbre)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        for interdit in ("session.interrupt", "session.steer"):
            assert interdit not in litteraux, (
                f"{module} appelle `{interdit}` : c'est le Gateway, il "
                "n'atteint pas le tour ACP et rend un succes quand meme.")


def test_la_route_de_cancel_rend_compte_du_tour():
    """Elle rendait `status: cancelled` sans toucher le tour. Le champ qui
    dit ce qui a ete fait a l'agent doit exister."""
    source = (RACINE / "backend" / "conversation"
              / "routes.py").read_text(encoding="utf-8")
    assert "tour_interrompu" in source
    assert "registre().interrompre" in source


def test_le_bouton_stop_arrete_le_tour_pas_seulement_la_lecture():
    """`abort()` seul coupait le `fetch` pendant que l'agent continuait
    d'ecrire. Le garde tient les deux gestes ensemble."""
    source = (RACINE / "frontend" / "src" / "features" / "conversation"
              / "conversation-center.tsx").read_text(encoding="utf-8")
    debut = source.index("const stop = useCallback")
    corps = source[debut:debut + 700]
    assert "abortRef.current?.abort()" in corps
    assert "conversationClient.cancel" in corps, (
        "`stop` n'annule que la lecture : l'agent continue son tour")
