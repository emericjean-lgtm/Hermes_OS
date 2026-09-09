# -*- coding: utf-8 -*-
"""Le pont negocie ce que le runtime sert, et ne decide rien (HOS-265).

Deux proprietes, et elles sont de nature differente.

La premiere est une mesure : `-32601` est le **seul** code qui prouve une
absence de methode. Une erreur applicative — `4001 session not found` — dit
que la methode existe et a examine ses arguments. Confondre les deux
rendrait la moitie du gateway invisible : mesure le 2026-09-06 sur v0.21.0,
54 methodes presentes repondent, et la plupart repondent par une erreur.

La seconde est architecturale : le pont n'est pas une autorite. Hermes OS
garde Mission, le Run Ledger, Aegis, `ResourceManager`, `AdaptiveRouter` et
le RAL ; le pont rapporte et relaie. C'est la seule raison pour laquelle
l'ajouter ne viole pas la regle qui prime sur tout.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.bridge import hermes_agent_bridge as pont
from backend.bridge.hermes_agent_bridge import (
    CODE_METHODE_INCONNUE,
    HermesAgentBridge,
)

RACINE = Path(__file__).resolve().parents[2]


class _Cfg:
    hermes_home = r"C:\\ailleurs"
    python_exe = "python"


@pytest.fixture
def magasin(tmp_path, monkeypatch):
    chemin = tmp_path / "db" / "bridge_negociation.json"
    monkeypatch.setattr(pont, "_magasin", lambda: chemin)
    return chemin


def _pont(monkeypatch, reponses, empreinte=("0.21.0+abc", "0.21.0", "abc")):
    p = HermesAgentBridge(config=_Cfg(), lanceur=lambda methodes: reponses)
    monkeypatch.setattr(p, "empreinte_runtime", lambda: empreinte)
    return p


# ── La mesure : ce qui prouve une absence ─────────────────────────────

def test_une_erreur_applicative_prouve_la_presence():
    """`4001 session not found` : la methode existe et a lu ses arguments.

    C'est le cas majoritaire du vrai gateway — le confondre avec une
    absence effacerait la plupart des capacites.
    """
    assert HermesAgentBridge._presente(
        {"id": 1, "error": {"code": 4001, "message": "session not found"}})


def test_seul_32601_prouve_une_absence():
    assert not HermesAgentBridge._presente(
        {"id": 1, "error": {"code": CODE_METHODE_INCONNUE,
                            "message": "unknown method: x"}})


def test_un_resultat_prouve_la_presence():
    assert HermesAgentBridge._presente({"id": 1, "result": {"toolsets": []}})


def test_une_absence_de_reponse_ne_s_arrondit_pas_vers_le_haut():
    """« On ne sait pas » n'est pas « oui ». Meme discipline tri-etat que le
    verdict agentique (HOS-263) et que l'occupation GPU (A-15)."""
    assert not HermesAgentBridge._presente(None)


# ── Ce que la negociation en fait ─────────────────────────────────────

#: Une surface de test, posee exprès plutot que prise dans la vraie
#: matrice : ces deux tests portent sur la **propriete** « partielle n'est
#: pas complete », pas sur la surface qui se trouve etre partielle
#: aujourd'hui. Les coupler a la matrice reelle les a fait rougir en G-19
#: quand elle a ete corrigee — ils mesuraient une donnee, pas une regle.
_SURFACE_ESSAI = ("a.une", "a.deux", "a.trois")


@pytest.fixture
def matrice_d_essai(monkeypatch):
    monkeypatch.setitem(pont.METHODES_PAR_CAPACITE, "essai", _SURFACE_ESSAI)
    return _SURFACE_ESSAI


def test_une_capacite_partielle_ne_se_declare_pas_complete(
        monkeypatch, magasin, matrice_d_essai):
    """Piloter sans pouvoir lancer, c'est une capacite partielle.

    L'annoncer « disponible » sans plus serait un mensonge d'interface : le
    cockpit proposerait une action que le runtime ne sert pas.
    """
    reponses = {m: True for groupe in pont.METHODES_PAR_CAPACITE.values()
                for m in groupe}
    reponses["a.trois"] = False
    capacite = _pont(monkeypatch, reponses).negocier().capacite("essai")
    assert capacite is not None
    assert capacite.disponible is True
    assert capacite.complete is False
    assert "a.trois" in capacite.methodes_absentes


def test_une_capacite_entierement_absente_n_est_pas_disponible(
        monkeypatch, magasin, matrice_d_essai):
    reponses = {m: True for groupe in pont.METHODES_PAR_CAPACITE.values()
                for m in groupe}
    for m in _SURFACE_ESSAI:
        reponses[m] = False
    capacite = _pont(monkeypatch, reponses).negocier().capacite("essai")
    assert capacite is not None and capacite.disponible is False


def test_une_panne_de_gateway_n_est_pas_un_runtime_sans_capacite(monkeypatch,
                                                                 magasin):
    """Sans ce partage, un gateway injoignable se lirait exactement comme un
    runtime nu — l'un est une panne, l'autre un fait."""
    def tombe(_methodes):
        raise OSError("gateway injoignable")

    p = HermesAgentBridge(config=_Cfg(), lanceur=tombe)
    monkeypatch.setattr(p, "empreinte_runtime", lambda: ("v", "v", "c"))
    resultat = p.negocier()
    assert resultat.negociee is False
    assert resultat.erreur and "gateway injoignable" in resultat.erreur
    assert not magasin.exists(), "une panne ne doit pas ecraser une mesure"


# ── La fraicheur : une negociation est une mesure datee ───────────────

def test_le_cache_ne_sert_que_pour_la_meme_empreinte(monkeypatch, magasin):
    """Mettre l'agent a jour doit perimer la negociation toute seule.

    C'est exactement ce qui manquait au magasin de sondes (G-15) : une
    mesure qui survit a ce qu'elle decrivait.
    """
    appels = []

    def lanceur(methodes):
        appels.append(1)
        return {m: True for m in methodes}

    p = HermesAgentBridge(config=_Cfg(), lanceur=lanceur)
    monkeypatch.setattr(p, "empreinte_runtime", lambda: ("0.21.0+aaa", "0.21.0", "aaa"))
    p.negocier()
    p.negocier()
    assert len(appels) == 1, "la seconde lecture devait venir du cache"

    monkeypatch.setattr(p, "empreinte_runtime", lambda: ("0.22.0+bbb", "0.22.0", "bbb"))
    p.negocier()
    assert len(appels) == 2, "un runtime different devait etre remesure"


def test_forcer_remesure_meme_empreinte_identique(monkeypatch, magasin):
    """La configuration de l'agent peut changer sans que sa version bouge —
    un serveur MCP ajoute, un toolset active."""
    appels = []
    p = HermesAgentBridge(config=_Cfg(),
                          lanceur=lambda m: (appels.append(1) or {x: True for x in m}))
    monkeypatch.setattr(p, "empreinte_runtime", lambda: ("v", "v", "c"))
    p.negocier()
    p.negocier(forcer=True)
    assert len(appels) == 2


def test_la_negociation_survit_au_processus(tmp_path):
    """Ecrite par un interprete, relue par un autre — c'est ce que le pont
    et un backend deja lance sont l'un pour l'autre."""
    env = {**dict(__import__("os").environ), "HERMES_DATA_DIR": str(tmp_path)}
    ecrire = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from backend.bridge.hermes_agent_bridge import HermesAgentBridge\n"
        "class C:\n"
        "    hermes_home = 'x'\n"
        "    python_exe = 'y'\n"
        "p = HermesAgentBridge(config=C(), lanceur=lambda m: {x: True for x in m})\n"
        "p.empreinte_runtime = lambda: ('1.0+zz', '1.0', 'zz')\n"
        "p.negocier()\n"
    ) % RACINE
    lire = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from backend.bridge.hermes_agent_bridge import _magasin\n"
        "import json; print(json.loads(_magasin().read_text(encoding='utf-8'))['empreinte'])\n"
    ) % RACINE
    a = subprocess.run([sys.executable, "-c", ecrire], env=env,
                       capture_output=True, text=True, timeout=180)
    assert a.returncode == 0, a.stderr
    b = subprocess.run([sys.executable, "-c", lire], env=env,
                       capture_output=True, text=True, timeout=180)
    assert b.returncode == 0, b.stderr
    assert b.stdout.strip() == "1.0+zz"


def test_le_magasin_vit_sous_un_dossier_preserve(monkeypatch, tmp_path):
    """Meme piege que le magasin de sondes (HOS-264) : `preserve_set()`
    enumere des dossiers, et un fichier pose a la racine serait efface."""
    from backend.core import etat

    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    preserves = {p.resolve() for p in etat.preserve_set()}
    assert pont._magasin().parent.resolve() in preserves


def test_un_cache_illisible_ne_fait_pas_tomber_la_negociation(monkeypatch,
                                                              magasin):
    magasin.parent.mkdir(parents=True, exist_ok=True)
    magasin.write_text("{ ceci n'est pas du json", encoding="utf-8")
    resultat = _pont(monkeypatch, {m: True for groupe
                                   in pont.METHODES_PAR_CAPACITE.values()
                                   for m in groupe}).negocier()
    assert resultat.negociee is True


# ── L'architecture : aucune autorite nouvelle ─────────────────────────

def test_le_pont_ne_choisit_ni_modele_ni_admission():
    """La regle qui prime sur tout : Hermes Agent est le cerveau, Hermes OS
    son systeme d'exploitation. Le pont rapporte et relaie.

    Garde sur l'**arbre syntaxique**, pas sur le texte : la premiere version
    de ce test cherchait les noms interdits dans la source entiere et
    rougissait sur le docstring du pont, qui les cite precisement pour dire
    qu'il n'y touche pas. Une assertion ecrite sur une forme ne garde pas ce
    qu'on croit — c'est le septieme cas de cette serie, et le premier ou la
    prose elle-meme declenchait le faux positif.
    """
    import ast

    source = (RACINE / "backend" / "bridge"
              / "hermes_agent_bridge.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    identifiants = {
        n.id for n in ast.walk(arbre) if isinstance(n, ast.Name)
    } | {
        n.attr for n in ast.walk(arbre) if isinstance(n, ast.Attribute)
    } | {
        alias.asname or alias.name
        for n in ast.walk(arbre)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for alias in n.names
    }
    interdits = {"AdaptiveRouter", "ResourceManager", "ModelRouter",
                 "GraphExecutor", "can_allocate", "places_disponibles"}
    touches = sorted(identifiants & interdits)
    assert touches == [], (
        f"le pont touche a {touches} — ce sont des autorites de Hermes OS, "
        "et le pont n'en est pas une")


def test_la_negociation_est_serialisable(monkeypatch, magasin):
    """Ce que le pont rend doit traverser l'API sans traduction manuelle."""
    resultat = _pont(monkeypatch, {m: True for groupe
                                   in pont.METHODES_PAR_CAPACITE.values()
                                   for m in groupe}).negocier()
    charge = json.loads(json.dumps(resultat.as_dict()))
    assert charge["negociee"] is True
    assert {c["nom"] for c in charge["capacites"]} == set(
        pont.METHODES_PAR_CAPACITE)


# ── La surveillance de flux : le pont lance un vrai agent ─────────────

def test_le_pont_pose_un_temoin_et_examine_la_sortie(monkeypatch):
    """Le pont est le **troisieme** lanceur d'agent du depot, et il passe
    `os.environ.copy()` a un sous-processus — donc tous les secrets de la
    machine. C'est A-2/HOS-218 un cran plus loin.

    `test_tout_lancement_d_agent_passe_par_l_adaptateur_surveille` l'a
    attrape au premier essai. L'inscrire dans sa liste d'autorises ne vaut
    que si le fait garde est le **comportement** : ce test verifie que le
    temoin est reellement pose dans l'environnement du gateway, et qu'une
    sortie qui le recrache fait echouer la negociation.
    """
    from backend.security import surveillance_flux

    vus = {}

    # Un temoin connu : chercher « le premier nom qui ressemble a un
    # jeton » ramassait un `*_TOKEN` deja present dans l'environnement
    # reel, et le faux gateway recrachait alors autre chose que le
    # canari — la fuite n'etait pas detectee et le test attendait le
    # delai complet au lieu de rougir.
    TEMOIN = "hermes-canary-de-test-0123456789abcdef"
    monkeypatch.setattr(surveillance_flux, "fabriquer_canary",
                        lambda: TEMOIN)

    class _FauxProcessus:
        def __init__(self, *a, **k):
            vus["env"] = k.get("env") or {}
            # Le gateway « fuit » : il recrache le temoin sur sa sortie.
            self.stdout = iter([TEMOIN + chr(10)])
            self.stdin = self
            self.returncode = 0

        def write(self, _s):
            return None

        def flush(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(pont.subprocess, "Popen", _FauxProcessus)
    p = HermesAgentBridge(config=_Cfg())
    with pytest.raises(RuntimeError, match="fuite detectee"):
        p._lancer_gateway(["toolsets.list"])

    # Et le temoin doit vraiment avoir ete pose dans l'environnement du
    # gateway : sans cela, la detection ci-dessus prouverait seulement
    # que `SurveillanceFlux` reconnait une chaine qu'on lui a donnee.
    assert TEMOIN in vus["env"].values(), (
        "le temoin n'est pas pose dans l'environnement du gateway")
