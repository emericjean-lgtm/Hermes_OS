"""Observateur de cycle de vie des Skills, pour Hermes OS (G-28, HOS-276).

**Ce fichier n'est pas charge par Hermes OS.** C'est un plugin *Hermes
Agent*, ecrit et mesure ici, et **pas installe** : voir le README voisin
pour la decision et ses deux prealables.

## Les trois regles qui tiennent ce fichier

**Aucun import des internes de l'agent.** La couche de compatibilite des
plugins (`hermes_cli/plugin_compat.py`) est retiree le **2026-09-14**, et
tout plugin externe qui importe un module interne est alors *desactive*.
Mesure du 2026-09-10 : `scan_plugin()` sur ce repertoire rend « aucun ».
Bibliotheque standard seulement, plus le `ctx` que l'agent passe.

**Aucune autorite.** `on_skill_lifecycle` est un hook d'observation : son
retour est ignore par `_emit_skill_lifecycle`. Mesure — une callback qui
leve n'empeche ni la mutation, ni l'ecriture de l'enregistrement natif.
Ce fichier n'appelle donc jamais `skill_manage`, n'ecrit aucune Skill, et
ne touche ni `.usage.json` ni `.bundled_manifest`.

**Aucune invention.** Un fait est note tel qu'il arrive. Un `session_id`
vide reste vide — `agent/skill_commands.py` appelle `bump_use` sans lui, et
le completer serait fabriquer une correlation.

## Ce qui n'est pas note, et pourquoi

`loaded` part **a chaque invocation de Skill** ; les quatre autres actions
sont des mutations, donc rares. Noter `loaded` ferait croitre l'etat au
rythme de l'usage, et `PluginState` est borne a 10 Mio. Seules les
mutations sont retenues.
"""

from __future__ import annotations

import json
import os
import threading
import time

#: Les cinq actions que `tools/skill_usage.py` emet, mesurees le 2026-09-10.
#: Une action hors de cette liste est notee quand meme — c'est un fait, et
#: un runtime plus recent peut en emettre de nouvelles — mais elle sort
#: telle quelle, jamais traduite.
ACTIONS_DE_MUTATION = frozenset({"created", "edited", "patched", "installed"})
ACTION_D_USAGE = "loaded"

#: Le prefixe des clefs de fait. `PluginState` plafonne a 10 Mio ; un
#: consommateur qui draine regulierement garde l'etat petit, et c'est a lui
#: de le faire — un observateur ne decide pas ce qui merite d'etre oublie.
PREFIXE_FAIT = "fait-"

_CTX = {}
_COMPTEUR = [0]
_COMPTEUR_VERROU = threading.Lock()


def _serialisable(valeur):
    """La valeur si elle passe en JSON, sinon sa representation tronquee.

    Un observateur ne doit jamais lever : le hook est isole, mais une
    exception ferait perdre le fait sans que rien ne le dise.
    """
    try:
        json.dumps(valeur)
        return valeur
    except (TypeError, ValueError):
        return repr(valeur)[:200]


def _on_skill_lifecycle(**faits):
    """Note une mutation de Skill. Rend toujours `None`.

    Le retour est ignore par l'agent ; le rendre explicitement `None` dit
    que ce plugin ne pretend influencer aucune decision.

    **Une clef par fait, et c'est une correction mesuree.** La premiere
    version faisait `state.get("mutations")` puis `state.set("mutations")` :
    chaque appel est atomique, la PAIRE ne l'est pas. G-31 a fait tourner
    deux tours ACP concurrents — chacun dans son `copy_context`, sur le
    meme executeur — et **un fait sur deux a disparu** : les deux threads
    avaient lu la meme liste avant que l'un ecrive. Un observateur qui perd
    silencieusement la moitie de ce qu'il observe est pire qu'absent.
    """
    ctx = _CTX.get("ctx")
    if ctx is None:
        return None
    if faits.get("action") == ACTION_D_USAGE:
        return None
    try:
        with _COMPTEUR_VERROU:
            _COMPTEUR[0] += 1
            rang = _COMPTEUR[0]
        # L'horodatage ordonne les faits entre processus, le rang les separe
        # a l'interieur d'un meme : deux tours concurrents peuvent tomber sur
        # la meme microseconde.
        cle = "%s%d-%d-%d" % (PREFIXE_FAIT, int(time.time() * 1_000_000),
                              os.getpid(), rang)
        ctx.state.set(cle, {"observe_a": time.time(),
                            **{c: _serialisable(v) for c, v in faits.items()}})
    except Exception:  # noqa: BLE001 - un observateur casse reste silencieux
        pass
    return None


def mutations(etat: dict) -> list:
    """Les faits d'un `state.json`, du plus ancien au plus recent.

    Le lecteur vit ici plutot que chez le consommateur : la forme des clefs
    est un detail de ce plugin, et l'exposer obligerait tout lecteur a la
    connaitre — donc a se tromper le jour ou elle change.
    """
    faits = [(c, v) for c, v in etat.items() if c.startswith(PREFIXE_FAIT)]
    return [v for _, v in sorted(faits, key=lambda p: p[0])]


def register(ctx):
    """Le seul point d'entree que l'agent appelle."""
    _CTX["ctx"] = ctx
    ctx.register_hook("on_skill_lifecycle", _on_skill_lifecycle)
