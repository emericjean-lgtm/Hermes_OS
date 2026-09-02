"""Ce que douze jalons ont produit, enfin lisible (HOS-234).

## Mesuré avant d'écrire

**Aucune route** n'exposait le registre des runs (J5), le contrat, les
points de reprise (J7), la portée des approbations (J8), les causes
d'échec (J9), le pare-feu (J11), le courtier (J12), le relais (J13), la
boucle (J14) ni la mise à jour (J16). Douze jalons de travail, invisibles
à toute interface.

Et `GET /api/v1/version` rendait `"0.1.0"` en dur, avec une liste de
modules arrêtée à HOS-028 — une version qui ne désignait rien, deux cents
jalons après.

## Ce qui existait et qu'il ne fallait pas refaire

`MissionControlService` (1 242 lignes) et son `MissionControlAPI`, avec
un WebSocket d'événements. Les routes de ce jalon s'y branchent.

## Ce que le frontend faisait déjà bien

Contrairement à ce qu'on pouvait craindre, il ne fabrique plus de
compteurs : les `Math.random()` restants sont des identifiants, un germe
de studio, ou des **commentaires documentant des fabrications retirées**.
`telemetry-trace.tsx` dit ce qu'on en a retenu — « `Math.random()` would
have made a prettier picture and a dishonest one ».
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services import vue_operations


@pytest.fixture
def client() -> TestClient:
    from backend.api.router import MissionControlAPI

    api = MissionControlAPI(MagicMock())
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    return TestClient(app)


# ═══ Les douze jalons sont enfin atteignables ════════════════════════

@pytest.mark.parametrize("chemin", [
    "/api/v1/operations",
    "/api/v1/operations/checkpoints",
    "/api/v1/operations/fournisseurs",
    "/api/v1/operations/approbations",
    "/api/v1/operations/installation",
])
def test_chaque_vue_repond(client, chemin):
    reponse = client.get(chemin)
    assert reponse.status_code == 200


def test_la_vue_d_ensemble_couvre_les_cinq_sections(client):
    donnees = client.get("/api/v1/operations").json()
    assert set(donnees) == {"runs", "fournisseurs", "approbations",
                            "points_de_reprise", "installation"}


def test_chaque_section_dit_d_ou_elle_vient(client):
    """Ce n'est pas de la décoration.

    Le frontend a déjà eu des compteurs fabriqués — `deployment-center`
    dormait 1 500 ms et rendait `Math.random() * 20 + 30`. Une vue qui
    nomme ses sources rend la fabrication visible au relecteur suivant.
    """
    for bloc in client.get("/api/v1/operations").json().values():
        assert bloc["source"].startswith("backend."), bloc


# ═══ Une vue, jamais un second runtime ═══════════════════════════════

def test_toutes_les_routes_d_operations_sont_en_lecture(client):
    """Une vue qui écrit devient un second chemin vers l'état.

    Et deux chemins vers l'état, c'est la question « lequel fait foi ? »
    à chaque incident.
    """
    from backend.api.router import MissionControlAPI

    api = MissionControlAPI(MagicMock())
    for route in api.router.routes:
        chemin = getattr(route, "path", "")
        if "/operations" in chemin:
            assert set(getattr(route, "methods", set())) <= {"GET", "HEAD"}, chemin


def test_le_modele_de_lecture_n_ecrit_rien():
    """Garde sur l'arbre syntaxique, pas sur le texte.

    Quatrième fois sur ce chantier qu'une recherche de sous-chaîne s'est
    accrochée à un commentaire ; celle-ci regarde les appels.
    """
    import ast
    import inspect

    source = inspect.getsource(vue_operations)
    appels = {ast.unparse(n.func) for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call)}
    ecritures = [a for a in appels if any(
        a.endswith(v) for v in ("ouvrir", "terminer", "demarrer", "reprendre",
                                "enregistrer", "prendre", "restaurer",
                                "appliquer", "supprimer", "decide",
                                "signaler_echec", "signaler_succes"))]
    assert not ecritures, (
        f"le modèle de lecture appelle {ecritures} — Mission Control est "
        "une vue du runtime, jamais un second runtime")


def test_aucun_magasin_nouveau():
    """Rien ne s'écrit ailleurs : les données viennent des systèmes réels."""
    import ast
    import inspect

    arbre = ast.parse(inspect.getsource(vue_operations))
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("sqlite" in m or "storage" in m for m in modules), modules


# ═══ Ce qui est absent est dit absent ════════════════════════════════

def test_une_section_indisponible_ne_rend_pas_un_zero(monkeypatch):
    """Un zéro se lit « rien ne s'est passé » ; une indisponibilité se
    lit « on ne sait pas ».

    C'est la règle tri-état de HOS-222 appliquée à l'affichage — et c'est
    là qu'elle compte le plus, parce que c'est là qu'un humain décide.
    """
    import backend.ral.courtier as module_courtier

    def casse():
        raise RuntimeError("courtier indisponible")

    monkeypatch.setattr(module_courtier, "courtier", casse)
    bloc = vue_operations.fournisseurs()
    assert bloc["disponible"] is False
    assert bloc["donnees"] is None
    assert "courtier indisponible" in bloc["raison"]


def test_une_section_qui_leve_ne_fait_pas_tomber_la_vue(monkeypatch):
    """Les autres sections sont justement ce qu'on regarde quand une
    chose va mal."""
    import backend.ral.courtier as module_courtier

    monkeypatch.setattr(module_courtier, "courtier",
                        lambda: (_ for _ in ()).throw(RuntimeError("non")))
    vue = vue_operations.vue_d_ensemble()
    assert vue["fournisseurs"]["disponible"] is False
    assert vue["installation"]["disponible"] is True


def test_aucun_fournisseur_configure_est_un_etat_normal():
    """Aucune clé n'est posée par défaut.

    Le dire évite de le lire comme une panne.
    """
    donnees = vue_operations.fournisseurs()["donnees"]
    assert "aucun_configure" in donnees


# ═══ Le vocabulaire des jalons est préservé ══════════════════════════

def test_une_cause_non_demontree_reste_nulle(tmp_path):
    """`None` et non « inconnue » : une colonne vide se lit « on ne sait
    pas », une étiquette se lit comme un diagnostic posé (HOS-225)."""
    from backend.config.config_models import DatabaseConfig
    from backend.runs.registre import Registre, Statut
    from backend.storage.database_manager import DatabaseManager

    registre = Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "r"))))
    run = registre.ouvrir(mission="m", objectif="o")
    registre.terminer(run.identifiant, Statut.ECHOUE, raison="KeyError")

    rendu = vue_operations._run_en_dict(registre.lire(run.identifiant))
    assert rendu["cause"] is None
    assert rendu["raison"] == "KeyError"


def test_le_contrat_separe_les_inverifiables_des_echoues():
    """Les fondre ferait lire une ignorance comme un constat (HOS-222)."""
    import inspect

    source = inspect.getsource(vue_operations.contrat_du_run)
    assert "inverifiables" in source
    assert "violes" in source


def test_un_point_de_reprise_dit_s_il_porte_l_etat():
    """Un point de reprise sans état de mission ne ramène que la moitié
    (HOS-223)."""
    import inspect

    assert "avec_etat" in inspect.getsource(vue_operations.points_de_reprise)


def test_les_portees_vivantes_sont_separees_des_accords_exacts():
    """Une ligne qui autorise un dossier entier ne se lit pas comme une
    qui autorise une action (HOS-224)."""
    donnees = vue_operations.approbations()["donnees"]
    assert "portees_vivantes" in donnees
    assert "en_attente" in donnees


# ═══ La version cesse d'être fabriquée ═══════════════════════════════

def test_la_version_n_est_plus_ecrite_en_dur(client):
    """Rendait `"0.1.0"` et une liste de modules arrêtée à HOS-028."""
    from backend.maj.version import VERSION

    donnees = client.get("/api/v1/version").json()
    assert donnees["version"] == VERSION
    assert "modules" not in donnees


def test_la_version_du_code_et_l_installee_sont_distinctes(client):
    """Elles peuvent différer, et c'est ce qu'on veut voir après une mise
    à jour dont le marquage n'a pas eu lieu.

    Les confondre masquerait exactement l'écart qu'on cherche.
    """
    donnees = client.get("/api/v1/version").json()
    assert "version_installee" in donnees
    assert "a_jour" in donnees


# ═══ Le frontend ne fabrique pas ═════════════════════════════════════

def test_le_frontend_ne_fabrique_pas_de_compteurs():
    """Vérifié plutôt que supposé.

    Les `Math.random()` restants sont des identifiants, un germe de
    studio, ou des commentaires documentant des fabrications retirées.
    """
    import io
    import re
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2] / "frontend" / "src"
    if not racine.is_dir():  # pragma: no cover - dépôt sans frontend
        pytest.skip("pas de frontend")

    suspects: list[str] = []
    # Un nombre fabriqué : `Math.random()` multiplié ou additionné, hors
    # génération d'identifiant (`toString(36)`) et hors commentaire.
    motif = re.compile(r"Math\.random\(\)\s*[*+]")
    # Un aléa **légitime** : une graine de génération. Le studio en tire
    # une pour LTX, et c'est le contraire d'une fabrication — c'est de
    # l'aléa demandé, pas une mesure inventée. Nommée plutôt que devinée :
    # la distinction est dans l'intention, et l'intention est dans le nom.
    legitimes = ("graine", "seed")
    for fichier in list(racine.rglob("*.ts")) + list(racine.rglob("*.tsx")):
        for numero, ligne in enumerate(
                io.open(fichier, encoding="utf-8", errors="replace"), 1):
            nue = ligne.strip()
            if nue.startswith(("//", "*", "/*")):
                continue
            if any(mot in ligne for mot in legitimes):
                continue
            if motif.search(ligne) and "toString(36)" not in ligne:
                suspects.append(f"{fichier.name}:{numero}")
    assert not suspects, (
        f"nombre(s) fabriqué(s) côté frontend : {suspects} — les données "
        "doivent venir des systèmes réels")
