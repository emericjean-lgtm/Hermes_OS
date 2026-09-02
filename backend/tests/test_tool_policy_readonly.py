"""Une promesse de sécurité qui ne s'exécutait pas (HOS-238).

## Le défaut

`ToolPolicy.evaluate()` portait :

    self._deny_write_in_readonly_sandbox = True
    ...
    if request.permission_level == ToolPermission.WRITE and self._deny_write_in_readonly_sandbox:
        # Policy engine would check sandbox readonly status
        pass

Un drapeau nommé « refuser l'écriture dans un sandbox en lecture seule »,
un commentaire au conditionnel, et **rien**. Une écriture dans un sandbox
readonly passait.

## Pourquoi ce n'était pas inoffensif

`ToolPolicy` est sur un chemin **réel** : `KlaatCodeMCPAdapter` l'appelle
avant chaque exécution, avec `ToolPermission.WRITE` sur `EDIT_FILE`. Le
`pass` était donc traversé en production.

## Pourquoi l'option A, et pas une nouvelle autorité

`ToolSandbox.get_config(tool_id).read_only` existe depuis HOS-049 et
**est la source de vérité**. `registration.py` construisait déjà les deux
objets côte à côte — une politique et un sandbox — sans jamais les
relier. La correction consiste à les brancher, pas à créer un troisième
gardien.

Aegis reste l'autorité de gouvernance. `ToolPolicy` est une politique
d'outil : elle ne remplace ni ne double Aegis, elle refuse plus tôt ce
qu'un sandbox déclare interdit.

## Ce que la politique ne prétend plus

Sans sandbox, elle **ne peut pas** connaître l'état readonly. Elle le dit
désormais dans son verdict au lieu de laisser croire qu'elle a vérifié —
c'est le tri-état appliqué à une décision de sécurité : « autorisé » et
« pas d'avis » ne sont pas la même réponse.
"""

from __future__ import annotations

import pytest

from backend.tools.tool_policy import PolicyVerdict, ToolPolicy
from backend.tools.tool_sandbox import SandboxConfig, ToolSandbox


def _requete(permission, tool_id="t1", timeout=10.0):
    from backend.tools.tool_models import ToolRequest

    return ToolRequest(tool_id=tool_id, permission_level=permission,
                       timeout_seconds=timeout)


def _outil(tool_id="t1", statut="active"):
    from backend.tools.tool_models import ToolDefinition

    return ToolDefinition(id=tool_id, name="outil", status=statut)


@pytest.fixture
def permission():
    from backend.tools.tool_models import ToolPermission

    return ToolPermission


# ═══ Le défaut lui-même ══════════════════════════════════════════════

def test_une_ecriture_dans_un_sandbox_readonly_est_refusee(permission):
    """La garde qui a été observée **rouge** sur le `pass`.

    Avant HOS-238, cette écriture passait : le drapeau était vrai, la
    branche était prise, et le corps ne faisait rien.
    """
    sandbox = ToolSandbox()
    sandbox.configure("t1", SandboxConfig(read_only=True))
    politique = ToolPolicy(sandbox=sandbox)

    verdict, raison = politique.evaluate(_requete(permission.WRITE), _outil())
    assert verdict is PolicyVerdict.DENY
    assert "lecture seule" in raison


def test_une_lecture_dans_un_sandbox_readonly_passe(permission):
    """La réparation ne doit pas fermer ce qui doit rester ouvert."""
    sandbox = ToolSandbox()
    sandbox.configure("t1", SandboxConfig(read_only=True))
    politique = ToolPolicy(sandbox=sandbox)

    verdict, _ = politique.evaluate(_requete(permission.READ), _outil())
    assert verdict is PolicyVerdict.ALLOW


def test_une_ecriture_hors_readonly_passe(permission):
    sandbox = ToolSandbox()
    sandbox.configure("t1", SandboxConfig(read_only=False))
    politique = ToolPolicy(sandbox=sandbox)

    verdict, _ = politique.evaluate(_requete(permission.WRITE), _outil())
    assert verdict is PolicyVerdict.ALLOW


# ═══ Ce qu'elle ne prétend plus savoir ═══════════════════════════════

def test_sans_sandbox_la_politique_ne_pretend_pas_avoir_verifie(permission):
    """« Autorisé » et « pas d'avis » ne sont pas la même réponse.

    Sans sandbox, la politique **ne peut pas** connaître l'état readonly.
    Le dire vaut mieux que laisser croire qu'elle a vérifié — c'est le
    tri-état appliqué à une décision de sécurité.

    Elle n'interdit pas pour autant : refuser toute écriture dès qu'aucun
    sandbox n'est câblé casserait tous les appelants existants, et une
    protection insupportable se débranche.
    """
    politique = ToolPolicy()
    verdict, raison = politique.evaluate(_requete(permission.WRITE), _outil())
    assert verdict is PolicyVerdict.ALLOW
    assert "sans sandbox" in raison.lower()


def test_le_drapeau_peut_etre_leve(permission):
    """Une politique qui ne veut pas de cette règle doit pouvoir la
    retirer explicitement, plutôt que de compter sur un `pass`."""
    sandbox = ToolSandbox()
    sandbox.configure("t1", SandboxConfig(read_only=True))
    politique = ToolPolicy(sandbox=sandbox)
    politique._deny_write_in_readonly_sandbox = False

    verdict, _ = politique.evaluate(_requete(permission.WRITE), _outil())
    assert verdict is PolicyVerdict.ALLOW


# ═══ Le reste de la politique n'a pas bougé ══════════════════════════

def test_admin_demande_toujours_une_revue(permission):
    verdict, _ = ToolPolicy().evaluate(_requete(permission.ADMIN), _outil())
    assert verdict is PolicyVerdict.REVIEW_REQUIRED


def test_un_timeout_excessif_est_refuse(permission):
    verdict, _ = ToolPolicy().evaluate(
        _requete(permission.READ, timeout=9999.0), _outil())
    assert verdict is PolicyVerdict.DENY


def test_un_outil_desactive_est_refuse(permission):
    verdict, _ = ToolPolicy().evaluate(
        _requete(permission.READ), _outil(statut="disabled"))
    assert verdict is PolicyVerdict.DENY


def test_une_regle_explicite_de_refus_est_appliquee(permission):
    politique = ToolPolicy()
    politique.add_rule("t1", "deny: interdit ici")
    verdict, _ = politique.evaluate(_requete(permission.READ), _outil())
    assert verdict is PolicyVerdict.DENY


# ═══ Plus aucun contrôle déclaré et non exécuté ══════════════════════

def test_aucune_branche_de_politique_ne_se_termine_par_pass():
    """Un `pass` derrière une promesse de sécurité est pire qu'une
    absence de promesse : il fait croire à une protection.

    Garde sur l'arbre syntaxique — un `pass` légitime dans une classe
    d'exception ou un `except` n'est pas visé, seul le corps d'un `if`
    l'est.
    """
    import ast
    import inspect
    import textwrap

    from backend.tools import tool_policy

    source = textwrap.dedent(inspect.getsource(tool_policy.ToolPolicy.evaluate))
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.If):
            assert not all(isinstance(c, ast.Pass) for c in noeud.body), (
                f"branche vide ligne {noeud.lineno} de ToolPolicy.evaluate")


def test_la_politique_est_branchee_sur_le_sandbox_en_production():
    """`registration.py` construisait les deux objets côte à côte sans
    jamais les relier — la politique et le sandbox qu'elle aurait dû
    consulter, dans la même fonction, à deux lignes d'écart.
    """
    import ast
    import io
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2]
    chemin = racine / "backend" / "tools" / "connectors" / "klaatcode" / "registration.py"
    arbre = ast.parse(io.open(chemin, encoding="utf-8").read())

    construction = next(
        (n for n in ast.walk(arbre)
         if isinstance(n, ast.Call) and ast.unparse(n.func) == "ToolPolicy"),
        None)
    assert construction is not None, "ToolPolicy n'est plus construit ici"
    assert any(k.arg == "sandbox" for k in construction.keywords), (
        "ToolPolicy est construit sans son sandbox — la règle readonly "
        "ne pourrait rien vérifier")


def test_aegis_reste_l_autorite():
    """`ToolPolicy` refuse plus tôt ; elle ne remplace pas Aegis.

    Une politique d'outil qui se mettrait à décider seule deviendrait
    une seconde autorité de gouvernance, ce que ce dépôt interdit.
    """
    import ast
    import inspect

    from backend.tools import tool_policy

    arbre = ast.parse(inspect.getsource(tool_policy))
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("aegis" in (m or "").lower() for m in modules), (
        "ToolPolicy importe Aegis — elle deviendrait un second chemin "
        "vers la même décision")
