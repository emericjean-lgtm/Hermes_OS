"""Le canal de protocole n'appartient qu'au protocole (HOS-138).

Ce fichier n'est pas importé par Hermes OS : il est **exécuté par
l'interpréteur de Hermes Agent**, à la place de `python -m acp_adapter`. Il
applique un invariant avant de céder la main à l'adaptateur, puis disparaît
du chemin d'exécution.

## L'invariant

    Aucun sous-processus lancé par l'agent n'hérite du canal ACP.

Sous ACP, l'entrée et la sortie standard du processus **sont** le transport
JSON-RPC. Or `subprocess.Popen`, quand on ne lui précise rien, laisse
l'enfant hériter des deux. Un enfant peut alors lire des octets destinés à
l'agent, ou écrire dans le flux que le client analyse.

## La mesure qui l'a imposé

L'agent restait bloqué indéfiniment sur le premier outil fichier de chaque
mission. Le journal s'arrêtait sur ::

    tools.file_tools: Creating new local environment for task default...

et plus rien. Trois dumps de pile successifs, à 45 s d'intervalle, ont
montré exactement le même point : `tools/environments/local.py:911`,
`_bash_starts`, bloqué dans `subprocess.communicate`. La même sonde bash
rend en **0,1 s** hors ACP.

Quatre variantes lancées *dans le processus ACP lui-même*, cinq fois de
suite, sans jamais varier :

===================================  ============
variante                             issue
===================================  ============
référence (stdin hérité)             bloque > 20 s
``stdin=DEVNULL``                    code 0, 0,1 s
sans ``creationflags`` (hérité)      bloque > 20 s
tout en ``DEVNULL``                  code 0, 0,1 s
===================================  ============

`creationflags` est donc hors de cause : **c'est l'héritage de stdin**. Et
dès que la sonde a cessé de bloquer, `note.txt` est apparu dans le
workspace — l'écriture n'avait jamais échoué, elle n'avait jamais eu lieu.

Le blocage est définitif et non borné, alors que la sonde se donne pourtant
`timeout=15`. Sur Windows, `subprocess.run` rattrape son propre délai puis
appelle `communicate()` **sans délai** pour récupérer la sortie — et ce
second appel joint des threads lecteurs qui n'atteindront jamais EOF.

## Pourquoi ici et pas dans l'arbre de l'agent

Une ligne corrigée dans `tools/environments/local.py` réglerait le cas et
serait effacée au prochain `hermes update` — sans que rien ne le signale,
exactement comme la confusion des deux environnements Python de HOS-103.
Le correctif appartient donc au harnais, qui est versionné avec Hermes OS.

## Ce que ce lanceur ne fait pas

Il ne touche pas à `stderr`. Le journal de l'agent est la seule fenêtre de
diagnostic dont dispose Hermes OS, et l'avoir jeté dans `DEVNULL` est ce
qui a rendu ce blocage invisible pendant toute une séance.
"""
from __future__ import annotations

import runpy
import subprocess
import sys

#: Ce que l'on substitue quand l'appelant n'a rien demandé. `DEVNULL` et non
#: `PIPE` : un `PIPE` que personne ne vide remplit son tampon puis bloque
#: l'enfant — on remplacerait un blocage par un autre.
_MUET = subprocess.DEVNULL


#: Rang de chaque canal dans la signature positionnelle de `Popen`
#: (`args, bufsize, executable, stdin, stdout, stderr`), `self` exclu. Un
#: appelant qui passe ses canaux en positionnel a bien exprimé un choix ; ne
#: regarder que `kwargs` l'écraserait en silence.
RANGS = {"stdin": 3, "stdout": 4}


def museler(args: tuple, kwargs: dict) -> dict:
    """Complète les canaux qu'aucun appelant n'a demandés.

    Isolée de l'enveloppe pour être vérifiable sans remplacer `Popen` dans
    le processus de test — un patch global y contaminerait tout ce que la
    suite lance par ailleurs.

    `stderr` n'y figure pas : le journal de l'agent est la seule fenêtre de
    diagnostic de Hermes OS, et l'avoir jeté est ce qui a rendu ce blocage
    invisible une séance durant.
    """
    complete = dict(kwargs)
    for canal, rang in RANGS.items():
        if len(args) > rang:
            continue  # donné en positionnel : c'est un choix explicite
        if complete.get(canal) is None:
            complete[canal] = _MUET
    return complete


def isoler_les_sous_processus() -> None:
    """Rend `stdin`/`stdout` muets pour tout enfant qui n'en demande pas.

    On enveloppe `Popen.__init__` plutôt que de rediriger le descripteur 0 :
    sur Windows, `os.dup2` sur le descripteur ne met pas à jour le handle
    Win32 correspondant, si bien que les enfants continueraient d'hériter du
    vrai tube. L'enveloppe, elle, agit là où la décision se prend.

    Un appelant qui précise `stdin=` ou `stdout=` — `PIPE`, un fichier, un
    descripteur — garde exactement ce qu'il a demandé. On ne comble qu'un
    défaut d'expression.
    """
    original = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):  # noqa: N807 - on remplace un dunder
        return original(self, *args, **museler(args, kwargs))

    subprocess.Popen.__init__ = __init__


def enregistrer_les_hooks() -> str:
    """Branche les hooks `pre_tool_call` declares dans la config de l'agent.

    Mesure du 2026-08-21 : `agent/shell_hooks.py` expose
    `register_from_config()`, et son propre commentaire annonce « so the CLI
    and gateway can both call register_from_config() safely ». **Personne ne
    l'appelle** dans la version installee — ni la CLI, ni la passerelle, ni
    l'adaptateur ACP. Les hooks declares en configuration ne sont donc jamais
    enregistres, et le blocage `pre_tool_call` reste lettre morte.

    Consequence mesuree : la frontiere du client ACP refuse une ecriture hors
    du workspace, l'agent repond « Let me try using the terminal directly »,
    et le fichier apparait — parce que le terminal, lui, n'est garde par
    rien.

    L'enregistrement se fait ici plutot que dans l'arbre de l'agent : un
    `hermes update` effacerait le correctif sans rien dire, comme la
    confusion des deux environnements Python de HOS-103.

    Ne leve jamais. Un garde-fou qui refuse de demarrer ne doit pas empecher
    l'agent de travailler — mais il rend ce qu'il a fait, pour que
    l'appelant puisse le **dire** au lieu de le supposer.
    """
    try:
        from agent.shell_hooks import register_from_config
        from hermes_cli.config import load_config

        poses = register_from_config(load_config())
        return f"{len(poses)} hook(s) shell enregistre(s)"
    except Exception as erreur:  # noqa: BLE001 - jamais bloquant
        return f"hooks shell non enregistres : {type(erreur).__name__}: {erreur}"


def main(argv: list[str] | None = None) -> None:
    """Attend la racine de l'agent en premier argument.

    Lancé par chemin (`python .../lanceur_agent.py`), `sys.path[0]` est le
    dossier de *ce* fichier — dans Hermes OS — et non l'arbre de l'agent :
    `acp_adapter` ne serait pas importable. On l'ajoute donc explicitement
    plutôt que de compter sur le répertoire courant, qu'un appelant peut
    changer sans le savoir.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        raise SystemExit("usage : lanceur_agent.py <racine-hermes-agent> [...]")
    racine, reste = arguments[0], arguments[1:]
    sys.path.insert(0, racine)

    isoler_les_sous_processus()
    # Sur la sortie d'erreur : c'est le seul canal de diagnostic du harnais,
    # et un garde-fou silencieux ne se distingue pas d'un garde-fou absent.
    sys.stderr.write(f"[lanceur] {enregistrer_les_hooks()}" + chr(10))
    sys.stderr.flush()

    # `run_module` et non un import : `acp_adapter/__main__.py` attend
    # d'être le point d'entrée, et `sys.argv[0]` sert à son analyse
    # d'arguments.
    sys.argv = ["acp_adapter", *reste]
    runpy.run_module("acp_adapter", run_name="__main__")


if __name__ == "__main__":
    main()
