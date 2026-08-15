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

> **Révisé le 2026-08-15 (HOS-113).** Le diagnostic ci-dessous plaçait la
> faute dans le protocole d'approbation. **La mesure le réfute** : la
> permission fonctionne, et le blocage est ailleurs. Conservé pour montrer
> comment l'erreur s'est produite ; la section suivante fait foi.

Après avoir accordé la permission (`AllowedOutcome(outcome='selected',
option_id='allow_once')`), **l'agent ne poursuit pas**. Aucun appel
`write_text_file` ne suit, aucune erreur n'est levée, le `prompt` ne rend
jamais la main — testé jusqu'à 900 s.

## Ce que la mesure du 2026-08-15 établit

**Un défaut de configuration masquait tout le reste.** Le modèle par
défaut de l'agent (`~/.hermes/config.yaml` → `model.default`) valait
`lfm2.5-2.6b-128k`, renommé `-125k` pendant la refonte du catalogue
(HOS-104 à HOS-109). L'agent répondait
`API call failed after 3 retries: HTTP 404: model not found` **à chaque
tour** — et le handler `session_update` du spike ne gardait que le *nom de
type* de chaque message, jetant précisément le texte qui le disait. Les
dix-huit modèles de la section `custom_providers` étaient morts eux aussi.
Config réalignée sur les onze tags réellement servis.

**La permission n'est pas le blocage.** Une fois le modèle corrigé, le
handler répond `RequestPermissionResponse` **en 0 ms**, bien formée. Et
l'agent *reçoit* cette réponse : en la refusant
(`ACP_SPIKE_DENY=1` → `DeniedOutcome`), les mises à jour passent de 53 à
**183**, l'agent raisonne à nouveau et tente un autre outil. L'aller-retour
fonctionne dans les deux sens.

**Le blocage est l'exécution d'outil, pas l'approbation.** Le second outil
tenté après le refus — `terminal: ls -la ACP_SPIKE.md` — s'est figé lui
aussi, **sans qu'aucune permission ne soit demandée** (`permissions=1` au
total sur toute la session). Le motif commun est donc : l'agent émet
`ToolCallStart`, puis n'exécute jamais l'outil et n'appelle jamais le
client. La permission n'était que la dernière chose visible avant l'arrêt
— une coïncidence de position, prise pour une cause.

**Le témoin sans outil aboutit.** Un tour qui demande un seul mot rend
`stop_reason=end_turn` avec 0 appel d'outil, systématiquement. La boucle
de tour, le modèle, le streaming et le retour de `prompt` fonctionnent
donc tous. Ce témoin est désormais exécuté à chaque passage du spike :
sans lui on ne sait pas ce qu'on mesure.

### Écarté par la mesure

| Hypothèse | Réfutée par |
|---|---|
| Le protocole d'approbation | Réponse en 0 ms, bien formée ; un refus fait passer les updates de 53 à 183 et l'agent enchaîne sur un autre outil |
| Le serveur MCP injoignable | Backend relancé, `/mcp/` répond `200` en 0,07 s, l'agent s'y connecte (`200`/`202` côté backend) — blocage identique |
| Le client auxiliaire en panne | Ses échecs concernent la *génération de titre* et se rabattent sur le modèle local ; ils précèdent l'appel d'outil et n'y touchent pas |
| Le modèle | Le témoin sans outil répond normalement avec le même modèle |

### Ce qui reste, et pourquoi c'est l'adaptateur ACP

**Le même agent exécute des outils tous les jours par le CLI** : HOS-084
et HOS-085 ont vérifié sur disque des missions qui écrivent réellement des
fichiers. Son moteur d'outils fonctionne donc. Ce qui échoue est
spécifique au chemin ACP.

L'agent émet `ToolCallStart`, puis **ne journalise plus rien** jusqu'au
délai — ni côté agent, ni côté client. Le motif est identique pour un
outil `edit` (après approbation) et pour un outil `execute` (sans aucune
approbation demandée).

À explorer ensuite : élever la verbosité côté `hermes-acp` pour voir ce
qu'il fait de l'approbation ; vérifier si le client doit accuser réception
par un `ToolCallProgress`/`ToolCallEnd` que le spike n'envoie pas ; et
comparer la négociation de capacités `fs` avec ce que l'agent attend
réellement avant d'appeler `write_text_file`.

## Une affirmation de ce document est devenue fausse

Le paquet `acp` **n'est plus** dans le venv de Hermes OS : HOS-103 a
séparé les deux environnements, et il ne reste que côté agent. L'adopter
demandera donc bien de le déclarer dans `requirements.txt` — contrairement
à ce qu'annonce la section « Pourquoi ACP plutôt que le CLI ».

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
