# Intégration ACP — ce qui est prouvé, ce qui bloque

Relevé le 2026-08-13, spike de faisabilité avant la refonte de l'adaptateur
Hermes Agent. Consigné parce que le débogage a été coûteux et que rien de
tout cela n'est écrit ailleurs.

## Pourquoi ACP plutôt que le CLI

L'adaptateur actuel lance `cli.py --query` en **one-shot** : le processus
meurt dès que le parent a répondu. C'est ce qui rend la délégation
inutilisable (HOS-094) — les subagents sont tués en plein appel API.

`hermes-acp` expose Hermes Agent via l'**Agent Client Protocol**, un serveur
stdio persistant. Capacités déclarées par le serveur : `load_session`,
`fork`, `list`, `resume`. Cela adresse d'un coup la délégation, la reprise de
mission, l'approbation humaine et l'observabilité.

Le paquet `acp` (v0.9.0) et l'exécutable `hermes-acp.exe` sont installés dans
le venv que **le backend Hermes OS utilise déjà** — aucune dépendance à
ajouter.

## Prouvé par le spike

1. **Handshake** — `initialize` répond, capacités négociées.
2. **Session** — `new_session(cwd=…)` crée une session liée à un workspace.
3. **Modèles** — la session énumère les modèles locaux servis par Ollama
   (`custom:lfm2.5-2.6b-128k`, `custom:gemma4:12b-128k`, …) et
   `set_session_model` les sélectionne. Aucune configuration à dupliquer.
4. **Streaming** — l'agent émet des dizaines de `session_update` pendant son
   travail : c'est la matière du fil conversationnel réclamé pour Autonomous.
5. **Approbation humaine** — l'agent appelle réellement `request_permission`
   avant d'éditer, avec des options typées
   (`allow_once` / `reject_once`, libellé « Allow edit »). Le §22
   human-in-the-loop n'est donc pas à construire, seulement à brancher.

## Bloqué

Après avoir accordé la permission (`AllowedOutcome(outcome='selected',
option_id='allow_once')`), **l'agent ne poursuit pas**. Aucun appel
`write_text_file` ne suit, aucune erreur n'est levée, le `prompt` ne rend
jamais la main — testé jusqu'à 900 s.

Hypothèses déjà écartées par la mesure :

- modèle distant qui attendrait des identifiants → non, la session utilise
  `custom:lfm2.5-2.6b-128k`, un modèle local ;
- capacité terminal manquante → non, `terminal=True` ne change rien ;
- signatures de handlers effacées par un décorateur → corrigé avec
  `functools.wraps`, sans effet.

Reste à explorer : la forme exacte attendue de la réponse sur le fil (le
schéma Pydantic est accepté, mais peut-être pas la sérialisation), un
éventuel second aller-retour attendu par l'agent, ou une réentrance dans le
dispatcher du client.

## Piège de débogage à connaître

**ACP écrase l'exception d'un handler client en `RequestError: Internal
error`**, sans trace ni nom de méthode. Quatre erreurs successives de noms de
types (`SelectedOutcome` → `SelectedPermissionOutcome` → `AllowedOutcome`
avec discriminant `outcome='selected'`) ont toutes produit ce même message
opaque.

**Tout handler ACP doit donc journaliser sa propre exception avant de la
laisser remonter.** Sans cela, la moindre erreur d'intégration est
indébogable. À intégrer dans l'adaptateur définitif, pas seulement dans un
spike.

## Types utiles, vérifiés

```python
from acp.schema import (
    AllowedOutcome,          # outcome='selected', option_id=…
    DeniedOutcome,           # outcome='cancelled'
    ClientCapabilities, FileSystemCapabilities, Implementation,
    TextContentBlock, WriteTextFileResponse, ReadTextFileResponse,
)
acp.PROTOCOL_VERSION  # 1
acp.spawn_agent_process(client, exe, env=…, cwd=…)  # -> (conn, process)
```

`new_session` accepte `mcp_servers` **par session** : Hermes OS pourra
n'exposer que les outils pertinents pour une mission donnée, de façon
déterministe et sans coût modèle — préférable à un agent distributeur
d'outils, qui ajouterait un appel de modèle avant chaque tâche.
