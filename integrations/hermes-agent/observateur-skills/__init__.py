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
import time

#: Les cinq actions que `tools/skill_usage.py` emet, mesurees le 2026-09-10.
#: Une action hors de cette liste est notee quand meme — c'est un fait, et
#: un runtime plus recent peut en emettre de nouvelles — mais elle sort
#: telle quelle, jamais traduite.
ACTIONS_DE_MUTATION = frozenset({"created", "edited", "patched", "installed"})
ACTION_D_USAGE = "loaded"

#: Au-dela, on jette les plus anciens. `PluginState` plafonne a 10 Mio et
#: refuse l'ecriture au-dela : un observateur qui remplirait son quota
#: cesserait d'observer sans le dire.
FAITS_MAX = 2000

_CTX = {}


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
    """
    ctx = _CTX.get("ctx")
    if ctx is None:
        return None
    if faits.get("action") == ACTION_D_USAGE:
        return None
    try:
        notes = ctx.state.get("mutations", [])
        if not isinstance(notes, list):
            notes = []
        notes.append({"observe_a": time.time(),
                      **{cle: _serialisable(v) for cle, v in faits.items()}})
        ctx.state.set("mutations", notes[-FAITS_MAX:])
    except Exception:  # noqa: BLE001 - un observateur casse reste silencieux
        pass
    return None


def register(ctx):
    """Le seul point d'entree que l'agent appelle."""
    _CTX["ctx"] = ctx
    ctx.register_hook("on_skill_lifecycle", _on_skill_lifecycle)
