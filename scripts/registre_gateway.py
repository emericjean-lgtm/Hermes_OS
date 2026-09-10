"""Releve le registre REEL des methodes du gateway Hermes Agent (G-19).

    .venv/Scripts/python.exe scripts/registre_gateway.py

## Pourquoi cet outil existe

HOS-265 a conclu « le fork n'a pas de RPC » parce que `session.fork` ne
repondait pas. Le fork existe : il s'appelle `session.branch`. La
negociation mesurait juste ; c'est la **liste des noms a sonder** qui etait
ecrite de memoire, et une liste de memoire ne vaut pas mieux qu'une
specification de memoire.

Le runtime, lui, sait exactement ce qu'il expose : `tui_gateway.server`
tient un dictionnaire `_methods`. Ce script le vide, avec **l'interpreteur
de l'agent** — le notre n'a aucune de ses dependances — et l'ecrit sous la
racine d'etat, dans `db/`, comme le magasin de sondes et pour la meme
raison : `preserve_set()` enumere des dossiers.

Mesure du 2026-09-09 sur v0.21.0 : **206 methodes**, la ou le pont en
sondait 62.

## Le releve porte l'empreinte du runtime

Meme lecon que G-15 : un releve qui survit a ce qu'il decrit ment. Il porte
donc la version et le commit de l'agent, et la garde de conformite refuse
un releve dont l'empreinte ne correspond plus a l'agent installe — plutot
que de valider des noms contre un inventaire perime.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: Ce que l'interpreteur de l'agent execute pour se decrire.
#:
#: `tui_gateway.entry` est importe pour son **effet de bord** : c'est lui
#: qui charge tous les modules `methods_*`, donc qui remplit `_methods`.
#: Sans cet import le releve est silencieusement partiel — une premiere
#: version par analyse syntaxique n'en voyait que 110 sur 206, faute de
#: connaitre les decorateurs `_room_method`, `_rpc` et leurs pareils.
#:
#: Le resultat passe par un **fichier** et non par la sortie standard :
#: `hermes_bootstrap` detourne `stdout`, qui est le canal JSON-RPC du
#: gateway. Mesure : `stdout` vide, la liste entiere ressortie sur
#: `stderr`. Dependre d'un flux qu'un autre programme possede, c'est
#: dependre de son implementation.
_PROGRAMME = """
import json, sys
import hermes_bootstrap
hermes_bootstrap.harden_import_path()
from tui_gateway import server
import tui_gateway.entry  # noqa: F401 - remplit server._methods
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(sorted(server._methods), f)
"""


def chemin_releve() -> Path:
    """Le relevé versionné, celui que `test_matrice_capacites` relit.

    Il visait `etat.racine()/db/` — l'état d'exécution — alors que le test
    lit `config/gateway_registre.json`. Suivre le message du test («
    relancez `scripts/registre_gateway.py` ») laissait donc le test rouge :
    le script écrivait un fichier que personne ne relisait, et le fichier
    relu vieillissait tout seul. Trouvé quand le patch de l'agent a changé
    son empreinte (G-33).

    Le relevé est une **mesure datée**, pas de l'état : sa place est dans le
    dépôt, à côté du test qui la compare au runtime installé.
    """
    return Path(__file__).resolve().parents[1] / "config" / "gateway_registre.json"


def relever() -> dict:
    from backend.bridge import HermesAgentBridge
    from backend.ral.adapters.hermes_agent_cli import HermesAgentCliConfig

    cfg = HermesAgentCliConfig()
    racine = Path(cfg.hermes_home) / "hermes-agent"
    empreinte, version, commit = HermesAgentBridge().empreinte_runtime()

    tampon = Path(tempfile.mkdtemp(prefix="hermes_registre_")) / "m.json"
    sortie = subprocess.run(
        [cfg.python_exe, "-c", _PROGRAMME, str(tampon)], cwd=str(racine),
        env={**os.environ, "HERMES_HOME": cfg.hermes_home, "PYTHONUTF8": "1"},
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)
    if not tampon.exists():
        raise RuntimeError(
            f"releve impossible (exit {sortie.returncode}) : "
            f"{(sortie.stderr or '')[-400:]}")
    return {"empreinte": empreinte, "version": version, "commit": commit,
            "methodes": json.loads(tampon.read_text(encoding="utf-8"))}


def main() -> int:
    releve = relever()
    chemin = chemin_releve()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(releve, indent=2), encoding="utf-8")
    print(f"{len(releve['methodes'])} methodes relevees pour "
          f"{releve['empreinte']}")
    print(f"-> {chemin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
