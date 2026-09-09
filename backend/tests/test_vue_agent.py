# -*- coding: utf-8 -*-
"""La vue du cerveau lit, et ne devient jamais une autorite (HOS-266).

Le pont (HOS-265) savait negocier — dire ce que le runtime *peut* faire —
et rien d'autre. Les capacites etaient donc visibles et inertes : le
cockpit affichait « sessions : complete » sans pouvoir montrer une seule
session. Ce module les transforme en surfaces produit.

Deux proprietes le gardent :

- **une panne n'est pas un vide.** `disponible` porte la difference, comme
  `NegociationRuntime.negociee` la porte pour la negociation. Sans elle, un
  gateway injoignable se lirait « aucune session », ce qui est faux et
  rassurant — la pire combinaison ;
- **la vue n'ecrit rien.** Garde sur l'arbre syntaxique, comme
  `vue_operations` en porte une depuis HOS-235 : une vue qui se met a
  ecrire devient une seconde autorite sans que personne ne l'ait decide.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.services import vue_agent

RACINE = Path(__file__).resolve().parents[2]


class _FauxPont:
    """Un pont qui rend ce qu'on lui dit, ou tombe."""

    def __init__(self, reponses=None, leve=None):
        self.reponses = reponses or {}
        self.leve = leve
        self.appels: list = []
        self.appels_params: list = []

    def appeler(self, methode, params=None, timeout=None):
        self.appels.append(methode)
        self.appels_params.append(params)
        if self.leve is not None:
            raise self.leve
        return self.reponses.get(
            methode, {"error": {"code": -32601, "message": "unknown method"}})


@pytest.fixture
def pont(monkeypatch):
    faux = _FauxPont()
    monkeypatch.setattr(vue_agent, "_pont", lambda: faux)
    return faux


# ── Une panne n'est pas un vide ───────────────────────────────────────

def test_un_gateway_injoignable_ne_se_lit_pas_comme_aucune_session(monkeypatch):
    """« 0 session » et « on n'a pas pu demander » sont deux faits
    differents, et un seul des deux est rassurant a tort."""
    monkeypatch.setattr(vue_agent, "_pont",
                        lambda: _FauxPont(leve=OSError("gateway mort")))
    vue = vue_agent.sessions()
    assert vue["disponible"] is False
    assert vue["elements"] == [] and vue["total"] == 0
    assert vue["erreur"] and "gateway mort" in vue["erreur"]


def test_une_erreur_applicative_est_aussi_une_indisponibilite(pont):
    """`-32601 unknown method` : la surface n'existe pas dans ce runtime.
    Ce n'est pas une liste vide."""
    vue = vue_agent.sessions()
    assert vue["disponible"] is False
    assert "-32601" in (vue["erreur"] or "")


def test_une_liste_reelle_est_servie(pont):
    pont.reponses["session.list"] = {
        "result": {"sessions": [{"id": "a"}, {"id": "b"}]}}
    vue = vue_agent.sessions()
    assert vue["disponible"] is True
    assert vue["total"] == 2 and len(vue["elements"]) == 2


# ── Un chiffre exact peut mentir ──────────────────────────────────────

def test_une_page_pleine_annonce_qu_il_en_reste(pont):
    """HOS-266 affichait « 100 servis sur 200 » — or 200 est le **plafond**
    de `session.list`, pas un decompte. Un chiffre exact qui trompe, ce que
    cette vue existe pour eviter.

    On demande donc une page de plus : ce que le runtime rend en trop
    prouve qu'il en reste, et c'est tout ce qu'on peut honnetement dire.
    """
    pont.reponses["session.list"] = {
        "result": {"sessions": [{"id": str(i)} for i in range(101)]}}
    vue = vue_agent.sessions(limite=100)
    assert vue["total"] == 100
    assert vue["tronque"] is True
    assert len(vue["elements"]) == 100


def test_une_page_incomplete_ne_pretend_pas_qu_il_en_reste(pont):
    pont.reponses["session.list"] = {
        "result": {"sessions": [{"id": str(i)} for i in range(7)]}}
    vue = vue_agent.sessions(limite=100)
    assert vue["total"] == 7 and vue["tronque"] is False


def test_la_page_demandee_depasse_d_un_ce_qu_on_affiche(pont):
    """C'est le `+1` qui rend `tronque` mesurable plutot que devine."""
    vue_agent.sessions(limite=50)
    assert pont.appels_params[-1] == {"limit": 51}


def test_une_charge_utile_inattendue_ne_fait_pas_tomber_la_vue(pont):
    """Le gateway peut changer de forme d'une version a l'autre — c'est
    tout l'objet de la negociation. Une vue qui leverait la-dessus rendrait
    un ecran de cockpit illisible pour un champ renomme."""
    pont.reponses["session.list"] = {"result": {"sessions": "pas une liste"}}
    vue = vue_agent.sessions()
    assert vue["disponible"] is True and vue["elements"] == []


# ── La delegation dit ce que le runtime borne ─────────────────────────

def test_la_delegation_rend_les_bornes_du_runtime(pont):
    pont.reponses["delegation.status"] = {
        "result": {"active": [], "paused": False,
                   "max_spawn_depth": 1, "max_concurrent_children": 10}}
    vue = vue_agent.delegation()
    assert vue["disponible"] is True
    assert vue["profondeur_max"] == 1 and vue["enfants_max"] == 10
    assert vue["en_pause"] is False


def test_une_delegation_indisponible_ne_prend_pas_zero_pour_une_borne(monkeypatch):
    """`profondeur_max = 0` dirait « aucune delegation permise ». `None`
    dit « on ne sait pas ». Meme discipline tri-etat que partout ailleurs
    dans ce depot."""
    monkeypatch.setattr(vue_agent, "_pont",
                        lambda: _FauxPont(leve=OSError("mort")))
    vue = vue_agent.delegation()
    assert vue["disponible"] is False
    assert vue["profondeur_max"] is None and vue["enfants_max"] is None
    assert vue["en_pause"] is None


# ── Une seule ouverture de gateway ────────────────────────────────────

def test_la_vue_d_ensemble_ne_demande_chaque_surface_qu_une_fois(pont):
    """Le gateway coute ~6 s a froid. Cinq routes frontend le rouvriraient
    cinq fois ; une route et cinq appels sur la meme connexion, non."""
    vue_agent.vue_d_ensemble()
    assert sorted(pont.appels) == sorted(set(pont.appels)), (
        "une surface a ete demandee deux fois")
    assert set(pont.appels) == {
        "session.list", "tools.list", "profiles.list",
        "delegation.status", "cron.manage"}


# ── L'architecture : une vue, pas une autorite ────────────────────────

def test_la_vue_agent_n_ecrit_rien():
    """Garde sur l'arbre syntaxique, comme `vue_operations` en porte une.

    Une vue qui se met a ecrire devient une seconde autorite sur l'etat de
    l'agent sans que personne ne l'ait decide — et c'est precisement la
    question que cette passe a laissee ouverte plutot que de la trancher
    par un bouton.
    """
    source = (RACINE / "backend" / "services"
              / "vue_agent.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    appels = {
        n.func.attr for n in ast.walk(arbre)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    interdits = {"write_text", "write", "mkdir", "unlink", "rmtree",
                 "execute", "executemany", "commit", "post", "put", "delete"}
    touches = sorted(appels & interdits)
    assert touches == [], (
        f"la vue du cerveau ecrit : {touches}. Elle doit rester une lecture.")


#: Les seules cles de parametre qu'une **vue** peut passer : elles bornent
#: une lecture et ne declenchent rien. `skills.manage` et `cron.manage`
#: savent aussi ecrire selon l'`action` recue — c'est cette cle-la, et ses
#: pareilles, qui n'ont rien a faire dans une vue.
CLES_DE_LECTURE = {"limit", "include_hidden", "title"}


def test_la_vue_ne_passe_que_des_parametres_de_lecture():
    """La premiere version interdisait **tout** parametre, ce qui a cesse
    d'etre tenable des que la pagination honnete a exige un `limit`.

    Interdire la forme (« aucun parametre ») plutot que la propriete
    (« aucun parametre qui ecrive ») aurait force a supprimer la garde au
    premier besoin legitime. On nomme donc ce qui est permis.
    """
    source = (RACINE / "backend" / "services"
              / "vue_agent.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    for n in ast.walk(arbre):
        if not (isinstance(n, ast.Dict) and n.keys):
            continue
        cles = {k.value for k in n.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        # Un dict de parametres se reconnait a ce qu'il ne contient que des
        # cles courtes ; on ne vise que ceux qui portent une cle d'action.
        interdites = cles & {"action", "op", "command", "delete", "set"}
        assert not interdites, (
            f"la vue construit un parametre d'action : {sorted(interdites)}. "
            "Une action appartient a `mutations_agent`, pas a une vue.")
