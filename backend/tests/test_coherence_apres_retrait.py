# -*- coding: utf-8 -*-
"""La coherence du depot apres le retrait de Policy (G-39, HOS-288).

G-38 a supprime `backend/policy/`. Ces gardes tiennent ce que le retrait
laisse derriere lui, et elles sont volontairement plus larges que Policy :
la classe de defaut qu'elles ferment n'a rien de propre a ce module.

## Ce que G-39 a trouve en verifiant

- **Aucun import** de `backend.policy` ne subsiste. Les deux references en
  code non-test sont des commentaires qui documentent le retrait.
- **Aucun client frontend** n'appelle une route absente — 131 chemins
  litteraux confrontes aux 338 routes montees.
- **Aucune entree d'orphelin** ne designe une route disparue : 118 entrees,
  0 fantome.
- Mais **trois tableaux fabriques** vivaient encore dans le Security
  Center : quatre menaces inventees (« Unauthorized file access ·
  agent.unknown_dev · 3 occurrences »), six politiques
  (« tool.exec: allow (Safety First) ») et six profils d'isolation. Les
  routes reelles rendent `[]`, `[]` et `total_profiles: 0`.

  `useSecurityThreats()` etait meme deja appele et sa donnee **liee puis
  jetee**. Un commentaire du fichier dit qu'une passe anterieure avait
  retire les mocks — elle avait retire les mocks NOMMES (`MOCK_STATUS`,
  `MOCK_TRUST_SCORES`) et laisse les tableaux litteraux inlines dans le
  JSX. On cherche `MOCK_` ; on ne cherche pas un tableau d'objets.

- Et **le document de reference se trompait** :
  `security-systems.md` affirmait que `PolicyEngine` avait « de vrais
  appelants » dans `recovery_engine`, `workspace_manager` et
  `runtime_decision`. Aucun des trois n'importait `backend.policy` : ils
  ont leurs propres moteurs (`RecoveryPolicyEngine`,
  `WorkspacePolicyEngine`, celui de HOS-016). Le document ecrit pour
  empecher la confusion entre quatre objets nommes « PolicyEngine » en
  etait lui-meme victime.
"""
from __future__ import annotations

import ast
import json
import re
import warnings
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
FRONT = RACINE / "frontend" / "src"


def _routes_montees() -> set[str]:
    """Les chemins `/api/v1/...` que l'application monte reellement.

    Construits depuis l'app, pas depuis une liste ecrite a la main : une
    liste gelee vieillirait et cesserait de mesurer quoi que ce soit.
    """
    from backend.main import app

    return {r.path[len("/api/v1"):] for r in app.routes
            if getattr(r, "path", "").startswith("/api/v1")}


# ── Le module retire ne revient pas ───────────────────────────────────

def test_aucun_import_de_backend_policy():
    """La garde la plus simple, et celle qui compte : un import suffirait a
    reintroduire la dependance qu'on vient de retirer."""
    coupables = []
    for fichier in RACINE.rglob("*.py"):
        if "__pycache__" in fichier.parts or ".venv" in fichier.parts:
            continue
        source = fichier.read_text(encoding="utf-8", errors="replace")
        # Analyser tout le depot fait remonter les avertissements des
        # fichiers ANALYSES, pas du notre : trois portent une sequence
        # d'echappement invalide — `test_garde_workspace.py`,
        # `test_livrables_vides.py` et `test_thinking_stream.py`. C'est
        # une trouvaille reelle, mais elle n'appartient pas a cette
        # garde : la faire crier ici salirait la sortie de la suite
        # sans rien garder de plus.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            arbre = ast.parse(source)
        for noeud in ast.walk(arbre):
            noms = []
            if isinstance(noeud, ast.Import):
                noms = [a.name for a in noeud.names]
            elif isinstance(noeud, ast.ImportFrom) and noeud.module:
                noms = [noeud.module]
            if any(n == "backend.policy" or n.startswith("backend.policy.")
                   for n in noms):
                coupables.append(str(fichier.relative_to(RACINE)))
    assert not coupables, (
        "`backend.policy` est de nouveau importe par " + ", ".join(coupables))


# ── Aucun client ne parle a une route qui n'existe pas ────────────────

def test_aucun_client_frontend_ne_vise_une_route_absente():
    """Le garde-fou que le brief de G-39 nomme : « un client frontend
    branche sur une source inexistante ».

    C'est la moitie manquante de `test_pas_de_backend_orphelin`, qui
    cherche des routes SANS appelant. Celle-ci cherche des appelants SANS
    route — le defaut inverse, et le plus silencieux des deux : une route
    orpheline ne casse rien, un appel vers le vide rend un 404 que
    l'interface affiche comme une panne.
    """
    client = (FRONT / "services" / "client.ts").read_text(encoding="utf-8")
    # Les chemins litteraux, gabarits compris ; la partie variable d'un
    # gabarit est coupee au premier `$`.
    appels = set(re.findall(r'fetchJSON<[^>]*>\(\s*[`"]([^`"$?]+)', client))
    montees = _routes_montees()
    prefixes = tuple(m.split("{")[0] for m in montees if "{" in m)
    manquants = sorted(
        a for a in appels
        if a.rstrip("/") not in montees
        and not a.startswith(prefixes)
        and not any(m.startswith(a) for m in montees))
    assert not manquants, (
        "le client appelle des routes qui ne sont pas montees : " +
        ", ".join(manquants))


def test_aucune_entree_d_orphelin_ne_designe_une_route_absente():
    """Une dette qui nomme une route disparue ne garde rien, et laisse
    croire a un travail restant qui n'existe plus. Mesure du 2026-09-11 :
    118 entrees, 0 fantome."""
    source = (RACINE / "backend" / "tests"
              / "test_pas_de_backend_orphelin.py").read_text(encoding="utf-8")
    debut = source.index("ORPHELINS_CONNUS")
    bloc = source[debut:source.index("})", debut)]
    connus = set(re.findall(r'"([^"]+)"', bloc))
    montees = _routes_montees()
    fantomes = sorted(c for c in connus if c not in montees)
    assert not fantomes, (
        "des entrees de dette designent des routes absentes : " +
        ", ".join(fantomes))


# ── Aucun ecran n'invente de donnee de securite ───────────────────────

#: Les ecrans ou une donnee fabriquee est un mensonge, pas une maquette.
_ECRANS_SENSIBLES = (
    "features/security/security-center.tsx",
    "features/governance/governance-center.tsx",
)

#: Un tableau d'objets pose directement dans le JSX, sur lequel on `.map()`.
#: Un mock NOMME se trouve en cherchant `MOCK_` ; celui-ci, non — et c'est
#: exactement pour cela que le nettoyage precedent du Security Center l'a
#: manque.
_TABLEAU_INLINE = re.compile(r"\{\[\s*\n(.*?)\n\s*\]\.map\(", re.DOTALL)

#: Les chaines sont retirees AVANT de chercher une reference vivante. Sans
#: cela, `"agent.unknown_dev"` et `"tool.exec"` passent pour des acces de
#: propriete, et la garde laisse filer deux des trois blocs fabriques —
#: mesure. Une garde qui lit une chaine comme du code se fait tromper par
#: son contenu.
_CHAINES = re.compile(r'"[^"]*"|\'[^\']*\'')

#: Ce qui distingue un descripteur de presentation d'une donnee inventee :
#: le premier REFERENCE quelque chose — l'etat (`s.trust.average_score`),
#: une interpolation, du JSX, une fonction de rendu. Le second n'a que des
#: litteraux. Les colonnes d'un `DataTable`, les onglets d'un Center et les
#: tuiles d'un `StatGrid` sont donc legitimes, et le restent.
_REFERENCE_VIVANTE = re.compile(
    r"\$\{|<[A-Za-z]|=>|\b[A-Za-z_$][\w$]*\s*\.\s*[A-Za-z_$]")


@pytest.mark.parametrize("ecran", _ECRANS_SENSIBLES)
def test_aucun_ecran_de_securite_ne_rend_un_tableau_fabrique(ecran):
    """Mesure du 2026-09-11 : le Security Center rendait quatre menaces
    inventees, six politiques et six profils d'isolation, pendant que les
    routes reelles rendaient `[]`, `[]` et `total_profiles: 0`. Une menace
    inventee affichee avec un badge « high » est indiscernable d'une
    detection.

    Ce que la garde autorise : un tableau litteral de LIBELLES (des
    en-tetes, des onglets). Ce qu'elle refuse : un tableau d'objets rendu
    comme de la donnee mesuree.
    """
    source = (FRONT / ecran).read_text(encoding="utf-8")
    fabriques = []
    for m in _TABLEAU_INLINE.finditer(source):
        corps = _CHAINES.sub('""', m.group(1))
        if not _REFERENCE_VIVANTE.search(corps):
            fabriques.append("ligne %d : %s"
                             % (source[:m.start()].count("\n") + 1,
                                m.group(1).strip()[:60]))
    assert not fabriques, (
        f"{ecran} rend un tableau de litteraux ecrit en dur — " +
        " | ".join(fabriques) +
        " — et une donnee de securite fabriquee est indiscernable d'une "
        "donnee mesuree")


def test_le_security_center_consomme_ce_qu_il_demande():
    """`useSecurityThreats()` etait appele, sa donnee liee a une variable —
    et jetee. Recuperer une donnee puis afficher autre chose est pire que
    ne pas la recuperer : le reseau montre un appel qui reussit."""
    source = (FRONT / "features" / "security"
              / "security-center.tsx").read_text(encoding="utf-8")
    for variable in ("threats", "policies"):
        assert f"{{{variable}.map(" in source or f"{{{variable}.length" in source, (
            f"`{variable}` est calcule et jamais rendu")


# ── Aucune documentation n'affirme une capacite retiree ───────────────

def test_aucune_doc_ne_decrit_backend_policy_comme_existant():
    """« Une documentation affirmant qu'une capacite existe alors qu'elle
    n'est plus presente » — le brief de G-39.

    Les mentions historiques sont legitimes : le CHANGELOG et la roadmap
    RACONTENT le retrait, et une entree corrigee par une mesure ulterieure
    s'amende, ne se reecrit pas. Ce qui est interdit est un document de
    REFERENCE qui decrit le module au present.
    """
    # La regle n'est pas « ne jamais nommer le module » : un document de
    # reference qui RACONTE le retrait est exactement ce qu'on veut, et
    # cette garde a commence par rougir sur sa propre correction. Ce qui
    # est interdit est de le nommer SANS dire qu'il est parti — c'est-a-dire
    # de le decrire comme existant.
    marqueurs = ("removed", "retir", "supprim", "G-38", "HOS-287")
    coupables = []
    for doc in (list(RACINE.glob("*.md"))
                + list((RACINE / "docs").rglob("*.md"))
                + list((RACINE / ".claude").rglob("*.md"))):
        texte = doc.read_text(encoding="utf-8", errors="replace")
        if "backend/policy/" not in texte and "backend.policy" not in texte:
            continue
        if not any(m in texte for m in marqueurs):
            coupables.append(str(doc.relative_to(RACINE)))
    assert not coupables, (
        "ces documents nomment `backend/policy/` sans dire qu'il a ete "
        "retire, donc le decrivent comme existant : " + ", ".join(coupables))
