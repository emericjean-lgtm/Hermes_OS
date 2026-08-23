#!/usr/bin/env python
"""Garde-fou : les commandes de l'agent ne visent pas hors du workspace.

Branché sur le hook `pre_tool_call` de Hermes Agent. Reçoit l'appel d'outil
en JSON sur l'entrée standard, rend `{"action": "block", "message": ...}`
pour le refuser, ou rien pour le laisser passer.

## L'incident qui l'a motivé

Mesuré le 2026-08-21. La frontière du client ACP a refusé **trois fois** une
écriture hors du workspace. L'agent a alors répondu, mot pour mot :

    The write was blocked by the ACP client.
    Let me try using the terminal directly.

et le fichier est apparu hors du workspace. `session/request_permission` ne
porte que sur les éditions de fichiers ; le terminal, lui, ne demande aucune
permission — il exécute. Refuser côté client détournait donc l'agent vers un
chemin non gardé, sans rien empêcher.

Ce n'est pas propre au harnais : le mode jetable donnait déjà le même
terminal à l'agent.

## Ce que ce garde-fou vaut, et ce qu'il ne vaut pas

Il **attrape les erreurs franches** : un chemin absolu qui désigne un
ailleurs, dans une commande ou dans un argument d'outil. C'est le cas réel —
un modèle qui interprète mal « le répertoire courant » et vise le profil
utilisateur.

Il **n'arrête pas qui cherche à sortir**. Une variable shell, une
substitution `$(...)`, un `cd` préalable, un chemin relatif assez long : rien
de tout cela ne se lit dans une chaîne de commande sans exécuter un
interpréteur. Prétendre le contraire donnerait une fausse assurance, ce qui
est pire que pas de garde du tout.

**La seule contrainte réelle est un backend d'exécution isolé** —
`terminal.backend: docker` dans la configuration de l'agent. Docker est
installé sur cette machine mais son démon ne tourne pas ; l'activer est une
décision d'exploitation, pas un défaut de code.

## Pourquoi il vit dans le dépôt

La configuration de l'agent n'est pas versionnée. Les recettes de modèles
avaient déjà disparu de cette façon (HOS-140), et il a fallu les reconstruire
par recherche. Ce fichier est versionné ; `config.yaml` ne fait que le
pointer.
"""
from __future__ import annotations

import io
import json
import ntpath
import os
import re
import sys

#: Le workspace confié, posé par `lanceur_agent.py` au démarrage. Absent, ce
#: garde-fou se tait : sans référence, tout chemin est également suspect, et
#: bloquer au hasard casserait le travail légitime.
VARIABLE = "HERMES_OS_WORKSPACE"

#: Les outils dont un argument peut désigner un fichier. `terminal` est le
#: seul chemin d'évasion mesuré, mais les autres exécutent aussi.
OUTILS_SURVEILLES = {"terminal", "execute_code", "run_command", "bash", "shell"}

#: `C:\...`, `C:/...`, `\\serveur\partage`, `/c/...` (Git Bash). Une seule
#: lettre pour la forme POSIX, sans quoi `/etc/passwd` passerait pour un
#: lecteur `E:`.
_ABSOLUS = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'|;&>]*)"          # C:\x ou C:/x
    r"|(?:\\\\[^\s\"'|;&>]+)"                    # \\serveur\partage
    r"|(?:/(?:cygdrive/|mnt/)?[A-Za-z]/[^\s\"'|;&>]*)"  # /c/x
)


def _en_windows(chemin: str) -> str:
    """Ramène une graphie POSIX de lecteur à sa forme Windows."""
    m = re.match(r"^/(?:(?:cygdrive|mnt)/)?([A-Za-z])(/.*)?$", chemin)
    if not m:
        return chemin
    return f"{m.group(1).upper()}:{(m.group(2) or '').replace('/', os.sep)}"


def _dedans(chemin: str, racine: str) -> bool:
    """Le chemin est-il sous la racine ?

    Comparaison en `normcase` : Windows est insensible à la casse, et une
    comparaison exacte laisserait passer une variante de casse du même
    dossier — défaut déjà payé cinq fois côté Hermes OS (HOS-129 à 133).
    """
    try:
        vise = ntpath.normcase(ntpath.abspath(_en_windows(chemin)))
        base = ntpath.normcase(ntpath.abspath(racine))
    except (OSError, ValueError):
        return False
    return vise == base or vise.startswith(base + os.sep)


def _sans_le_workspace(texte: str, racine: str) -> str:
    """Retire du texte toutes les mentions du workspace, avant analyse.

    **Un workspace peut contenir des espaces**, et une ligne de commande
    n'offre aucun moyen fiable de delimiter un chemin qui en contient. La
    premiere version de `_ABSOLUS` s'arretait donc au premier espace : le
    chemin du dossier confie etait tronque a son premier mot, qui n'est
    evidemment pas sous le workspace — donc refuse.

    Mesure du 2026-08-21, en plein deroulement d'un cahier sur un dossier
    nomme « Skill360 Nuit HOS-141 » : deux refus sur des commandes
    parfaitement legitimes, dans le dossier confie. Le garde bloquait le
    travail qu'il devait proteger, et la section a ete notee « contredite,
    aucun fichier ecrit ».

    On ote donc d'abord ce qu'on sait etre le workspace — dans ses graphies
    usuelles, casse comprise — et on analyse le reste. Ce qui subsiste ne
    peut plus etre un chemin du workspace, et les vraies sorties restent
    entieres.
    """
    reste = texte or ""
    if not racine:
        return reste
    formes = {racine, racine.replace(os.sep, "/"), racine.replace("/", os.sep)}
    # Les graphies qu'un modele produit quand le workspace contient des
    # espaces. Mesure du 2026-08-21, en pleine campagne : l'agent a vise
    # « ...\Skill360\Nuit\HOS-141/ », espaces remplaces par des
    # separateurs — refuse, alors qu'il designait le dossier confie. La
    # variante « Skill360\ Nuit », elle, vient de l'echappement shell.
    #
    # Ces formes sont ajoutees parce qu'aucune ne designe un dossier reel
    # distinct : elles sont des deformations d'un seul et meme chemin, et
    # les refuser coute un faux refus sans rien proteger.
    for base in list(formes):
        if " " in base:
            formes.add(base.replace(" ", os.sep))
            formes.add(base.replace(" ", "/"))
            formes.add(base.replace(" ", chr(92) + " "))
    if len(racine) > 2 and racine[1] == ":":
        # La graphie Git Bash du meme dossier, que l'agent produit
        # naturellement sous Windows.
        formes.add("/" + racine[0].lower() + racine[2:].replace(os.sep, "/"))
    for forme in sorted(formes, key=len, reverse=True):
        # Insensible a la casse : Windows l'est, et une variante suffirait
        # sinon a reintroduire le faux refus.
        reste = re.compile(re.escape(forme), re.IGNORECASE).sub(" ", reste)
    return reste


def chemins_suspects(texte: str, racine: str) -> list[str]:
    """Les chemins absolus de `texte` qui sortent de `racine`."""
    epure = _sans_le_workspace(texte, racine)
    return [c for c in _ABSOLUS.findall(epure) if not _dedans(c, racine)]


def _arguments(charge: dict):
    """Les arguments de l'appel, quelle que soit la cle qui les porte.

    Hermes Agent serialise la charge du hook au format Claude-Code : les
    arguments arrivent sous **`tool_input`**, pas sous `args`. Ne lire
    qu'`args` rendait systematiquement `None`, et le garde autorisait tout
    en silence.
    """
    for cle in ("tool_input", "args"):
        valeur = charge.get(cle)
        if isinstance(valeur, dict):
            return valeur
    return None


#: Les formes shell qui **ecrivent** sur un fichier nomme juste apres.
#: `cat`, `grep`, `head` n'y sont pas : lire un cahier des charges est le
#: comportement attendu, et le refuser serait le faux refus type.
_ECRITURES = re.compile(
    r"(?:>>?|\btee\b|\bsed\s+-i\b|\bmv\b|\bcp\b"
    r"|\bSet-Content\b|\bOut-File\b|\bAdd-Content\b)",
    re.IGNORECASE)


def _documents_d_entree(racine: str) -> list[str]:
    """Les noms declares dans `.hermes/proteges.txt`, ou une liste vide."""
    try:
        lignes = io.open(os.path.join(racine, ".hermes", "proteges.txt"),
                         encoding="utf-8").read().splitlines()
    except OSError:
        return []
    return [ligne.strip() for ligne in lignes
            if ligne.strip() and not ligne.strip().startswith("#")]


def ecrase_un_document_d_entree(texte: str, racine: str) -> str:
    """Le nom du cahier que cette commande ecraserait, ou "".

    ## L'incident

    Campagne du 2026-08-23 : `PROJECT_SPEC.md` faisait 1136 lignes au
    lancement, trois a l'arrivee. Vingt et une sections ont travaille sur un
    cahier vide sans que rien ne le signale.

    La liste `proteges.txt` etait posee et correcte. Elle etait appliquee
    dans `backend/tools/file_tools.py`, c'est-a-dire sur les outils de
    Hermes OS — que l'agent n'utilise pas pour ecrire. Le client ACP couvre
    desormais son `write_file` ; le terminal, lui, ne demande aucune
    permission et ne passe que par ici.

    ## Pourquoi une heuristique, et assumee comme telle

    Un hook recoit une ligne de commande, pas un chemin de destination. On
    ne peut donc pas savoir avec certitude ce qu'une commande ecrira. Le
    compromis retenu : refuser quand un document declare est nomme **et**
    qu'une forme d'ecriture apparait dans la meme commande. Lire reste
    libre — c'est meme ce qu'on attend d'un agent devant un cahier des
    charges.

    Un contournement reste possible (un script intermediaire, un chemin
    construit). Ce garde attrape la faute franche, celle qui s'est produite ;
    il ne pretend pas etre une frontiere.
    """
    if not _ECRITURES.search(texte):
        return ""
    # La **destination**, pas la source : `cp PROJECT_SPEC.md copie.md`
    # sauvegarde le cahier, il ne le detruit pas, et le refuser serait un
    # faux refus. Toutes les formes qui ecrasent nomment leur cible en
    # dernier jeton — `> cible`, `tee cible`, `sed -i ... cible`,
    # `mv source cible`. On ne regarde donc que celui-la.
    jetons = texte.replace("'", " ").replace('"', " ").split()
    if not jetons:
        return ""
    cible = ntpath.basename(jetons[-1].replace("/", os.sep))
    for document in _documents_d_entree(racine):
        if cible and cible == ntpath.basename(
                document.replace("/", os.sep)):
            return document
    return ""


def verdict(charge: dict, racine: str) -> dict | None:
    """`{"action": "block", ...}` s'il faut refuser, sinon `None`."""
    if not racine:
        return None
    if str(charge.get("tool_name") or "") not in OUTILS_SURVEILLES:
        return None

    args = _arguments(charge)
    if not isinstance(args, dict):
        return None
    # Tous les arguments texte, pas seulement `command` : les outils
    # d'exécution n'ont pas tous le même nom de paramètre, et n'en surveiller
    # qu'un laisserait les autres passer sans que rien ne le dise.
    suspects: list[str] = []
    for valeur in args.values():
        if isinstance(valeur, str):
            suspects.extend(chemins_suspects(valeur, racine))
            ecrase = ecrase_un_document_d_entree(valeur, racine)
            if ecrase:
                return {
                    "action": "block",
                    "message": (
                        f"Refuse par Hermes OS : {ecrase} definit le travail "
                        f"a faire, il n'en fait pas partie. Une campagne a "
                        f"deja remplace un cahier des charges de 1136 lignes "
                        f"par trois, et les vingt sections suivantes ont "
                        f"travaille sur du vide. Lis-le autant que tu veux ; "
                        f"ecris tes livrables ailleurs."
                    ),
                }
    if not suspects:
        return None
    return {
        "action": "block",
        "message": (
            f"Refusé par Hermes OS : cette commande vise "
            f"{', '.join(sorted(set(suspects))[:3])}, hors du workspace "
            f"confié ({racine}). Travaille dans le workspace, avec des "
            f"chemins relatifs."
        ),
    }


#: Ou le garde note ce qu'il a refuse. Un garde-fou muet ne se distingue pas
#: d'un garde-fou absent — c'est exactement ce qui a laisse le hook precedent
#: pointer six mois vers un dossier disparu sans que personne ne le voie.
JOURNAL = "garde_workspace.log"


def _noter(ligne: str) -> None:
    """Trace le refus, au mieux et sans jamais lever.

    Sous `HERMES_DATA_DIR` quand il existe — le meme dossier que le reste
    de l'etat de Hermes OS —, sinon a cote de ce script.
    """
    try:
        from datetime import datetime, timezone

        base = os.environ.get("HERMES_DATA_DIR") or os.path.dirname(
            os.path.abspath(__file__))
        horodatage = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
        with io.open(os.path.join(base, JOURNAL), "a",
                     encoding="utf-8") as sortie:
            sortie.write(f"{horodatage} {ligne}" + chr(10))
    except Exception:
        pass


def main() -> int:
    try:
        charge = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        # Un garde-fou qui plante ne doit pas bloquer l'agent : il se tait.
        # Le choix inverse — refuser par défaut — transformerait la moindre
        # anomalie de plomberie en panne totale des missions.
        return 0

    racine = os.environ.get(VARIABLE, "")
    outil = charge.get("tool_name") if isinstance(charge, dict) else None

    if not racine and outil in OUTILS_SURVEILLES:
        # Le garde est invoque mais n'a **aucune reference** : il laisse
        # tout passer. C'est le pire etat possible — une protection qui
        # parait en place et ne protege rien — donc il le dit, toujours.
        _noter(f"SANS REFERENCE outil={outil!r} : {VARIABLE} absent, "
               f"rien n'est verifie")

    if os.environ.get("HERMES_GARDE_VERBEUX", "").strip() == "1":
        # Diagnostic : sans cela, un garde qui n'est jamais invoque est
        # indiscernable d'un garde qui autorise tout.
        _noter(f"VU outil={outil!r} racine={racine!r} "
               f"args={_arguments(charge if isinstance(charge, dict) else {})!r}"[:900])

    reponse = verdict(charge if isinstance(charge, dict) else {}, racine)
    if reponse is not None:
        _noter(f"REFUS outil={charge.get('tool_name')!r} "
               f"session={charge.get('session_id')!r} :: {reponse['message']}")
        sys.stdout.write(json.dumps(reponse, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
