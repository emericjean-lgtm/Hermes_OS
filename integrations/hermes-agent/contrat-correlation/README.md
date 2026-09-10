# Contrat de corrélation Run ↔ Skill — implémenté et démontré (G-30 → G-31)

**Rien ici n'est implémenté *dans Hermes OS*, et rien ne doit l'être.** La
modification vit chez Hermes Agent : `turn-id.patch`, à côté de ce fichier,
en est la provenance exacte.

---

## La décision

| objet | verdict |
|---|---|
| le transport d'une métadonnée opaque, côté ACP | **ADOPT** — natif, mesuré (G-30) |
| la restitution dans `on_skill_lifecycle` | **ADOPT** — implémentée et démontrée (G-31) |
| la même chose côté Gateway | **REJECT** — canal privilégié, infranchissable |
| un registre de corrélation propre à Hermes OS | **REJECT** — seconde vérité |

G-30 avait classé la restitution **ADAPT** : trois lignes à trois coutures
existantes, que Hermes OS ne pouvait pas écrire. G-31 les a écrites chez
l'agent et a mesuré la chaîne complète. Le verdict passe donc à **ADOPT**,
avec une limite qui n'est pas cosmétique — voir « La provenance » plus bas :
le patch vit dans un checkout local, et `hermes update` le met au mieux en
autostash.

---

## 1. La surface amont réellement exploitable

`PromptRequest` d'ACP v0.11.2 (`PROTOCOL_VERSION = 1`) porte quatre champs :

    field_meta   alias "_meta"   réservé aux extensions
    message_id   alias "messageId"   **UNSTABLE**
    prompt
    session_id

Le commentaire du schéma est explicite : *« The `_meta` property is reserved
by ACP to allow clients and agents to attach additional metadata to their
interactions. Implementations MUST NOT make assumptions about values at
these keys. »* C'est exactement un canal opaque fourni par le client.

**Et il arrive déjà.** Le routeur ACP déplie `_meta` en arguments nommés :

```python
params = {k: getattr(model_obj, k) for k in model.model_fields if k != "field_meta"}
if meta := getattr(model_obj, "field_meta", None):
    params.update(meta)
return await func(**params)
```

Mesure du 2026-09-10, sur le runtime installé, en envoyant
`_meta: {"hermes": {"turnId": "run-42#tour-3"}}` :

    handler a recu :
      session_id : sess-1
      blocs      : 1
      kwargs     : {"message_id": null, "hermes": {"turnId": "run-42#tour-3"}}

La signature de l'agent est
`async def prompt(self, prompt, session_id, **kwargs)` : la métadonnée
**arrive**, et l'agent l'ignore. Le transport est donc acquis ; il manque
la restitution.

L'espace de noms `hermes` n'est pas inventé non plus : `acp_adapter/provenance.py`
décrit déjà une *« additive Hermes extension under ACP `_meta.hermes` »*,
dans le sens sortant. La proposition ne fait qu'emprunter le même chemin
en sens inverse.

### Les options écartées, et pourquoi

**`messageId`** est marqué **UNSTABLE** — *« not part of the spec yet, and
may be removed or changed at any point »* — et l'agent devrait l'échoer dans
la `PromptResponse`, pas dans les événements Skill. Il répondrait à « ce
message a-t-il été enregistré », pas à « quel Run a produit cette Skill ».

**`_hosted_task` du Gateway** est le précédent le plus proche : `prompt.submit`
accepte déjà une enveloppe cliente portant `turn_id`, `task_id`, `room_id`.
Mais `_hosted_submit_error` exige `session["source"] == "bot_room"` **et** un
`_hosted_terminal_callback` **appelable** — un objet Python qui ne traverse
pas JSON-RPC. Le canal est interne au processus, pas ouvert à un client.

**Un registre de corrélation propre à Hermes OS** — associer par le temps,
par la session unique ou par le dernier Run — est la fausse corrélation que
G-29 a REJETÉE, et des tests l'interdisent.

---

## 2. Le contrat minimal

    Hermes OS Run
        └─ frappe un turnId opaque, unique, qu'il seul émet
             └─ session/prompt  _meta: {"hermes": {"turnId": "<opaque>"}}
                  └─ le tour de l'agent le porte
                       └─ on_skill_lifecycle le restitue tel quel
                            └─ Hermes OS le reconnaît, ou refuse

**Trois règles, et elles suffisent.**

1. Le `turnId` est **opaque pour l'agent**. Il ne l'interprète pas, ne le
   valide pas, ne le complète pas. Il le transporte et le rend.
2. **Absent reste absent.** Un événement sans `turnId` n'en reçoit pas un.
   L'agent n'invente pas, Hermes OS n'associe pas.
3. **Hermes OS ne reconnaît que ce qu'il a frappé.** Un `turnId` qu'il n'a
   pas émis est étranger : il est ignoré, pas associé « au mieux ».

## 3. Le propriétaire de chaque identité

| identité | propriétaire | ce qu'elle désigne |
|---|---|---|
| `task_id` de l'agent | Hermes Agent | sur ACP, **c'est le `session_id`** — mesuré : `run_conversation(..., task_id=session_id)` |
| `session_id` de l'agent | Hermes Agent | une session, qui couvre plusieurs missions (G-29) |
| `turnId` | **Hermes OS** | un tour, et un seul |
| `run_id` | Hermes OS | une tentative d'exécution |
| `mission_id` | Hermes OS | l'objectif |

Aucune de ces cinq n'est dérivable d'une autre, et le contrat n'en dérive
aucune : il en **transporte** une sixième, que Hermes OS frappe et
reconnaît. C'est ce qui l'empêche de créer une autorité.

Note mesurée qui compte pour la suite : sur le chemin ACP, le `task_id` de
l'agent **est** son `session_id`. Un événement Skill de chat ou de mission
porte donc aujourd'hui deux fois la même valeur, et aucune n'est granulaire
au tour.

## 4. Le chemin de propagation, et les trois points amont

Trois coutures, toutes déjà existantes. **G-30 en avait mal nommé une**, et
la mesure l'a corrigée :

1. **`acp_adapter/server.py`, `_client_turn_id()` + `prompt()`** — lire
   `kwargs["hermes"]["turnId"]`. Il arrive déjà ; il suffit de ne plus le
   jeter.
2. **`acp_adapter/server.py`, `_run_agent_turn()`** — et non
   `agent/turn_context.py`, comme G-30 le supposait. `_run_agent_turn` est
   le *« Executor-thread body of one turn, run inside
   `contextvars.copy_context()` so ContextVar writes are isolated from
   concurrent sessions »* : l'isolation entre tours concurrents y est déjà
   architecturale, et la fonction porte un `ExitStack` où les autres
   contextes de tour sont liés. Lier ailleurs aurait été lier sur le thread
   de la boucle, hors du contexte copié.
3. **`tools/skill_provenance.py`** — le `ContextVar` lui-même, à côté de
   `_write_origin` qui existe pour la même sorte de portée.
4. **`tools/skill_usage.py`, `_emit_skill_lifecycle`** — ajouter le champ à
   la charge utile, **absent quand il est absent**.

Rien à changer dans le protocole, rien à ajouter au schéma, aucune méthode
nouvelle. 83 lignes, trois fichiers.

## 4 bis. La démonstration (G-31)

Chaîne réelle à chaque maillon sauf un : le corps du tour, où le modèle
déciderait d'appeler `skill_manage`, remplacé par une mutation déterministe.
C'est la *décision* du modèle qu'on substitue, pas le mécanisme mesuré.

    _meta → MessageRouter réel → HermesACPAgent.prompt() réel
          → _run_agent_turn réel (copy_context + ExitStack)
          → skill_manage réel → _emit_skill_lifecycle réel → plugin réel

Relevé :

    g31-a              action=created  turn='A'
    g31-b              action=created  turn='B'
    g31-c1             action=created  turn='C'
    g31-c2             action=created  turn='C'
    g31-sans           action=created  turn=None
    g31-meta-vide      action=created  turn=None      _meta sans `hermes`
    g31-hermes-vide    action=created  turn=None      `hermes` sans `turnId`
    g31-hors-tour      action=created  turn=None      hors de tout tour
    g31-x              action=created  turn='X'   ┐ deux tours
    g31-y              action=created  turn='Y'   ┘ concurrents

    clé absente quand aucun turnId : g31-sans, g31-meta-vide,
                                     g31-hermes-vide, g31-hors-tour

Après redémarrage, un tour **sans** `turnId` n'hérite d'aucune identité
précédente : `client_turn_id` absent, alors que `A B C X Y` étaient sur le
disque. Et `.usage.json` ne porte **aucun** champ de tour : rien n'est
persisté *pour* la corrélation.

La suite de l'agent est restée à son état d'avant — 42 passés, 1 échec
préexistant (`test_acp_resource_link_file_is_inlined_as_text`), identique
avant et après le patch.

## 4 ter. La provenance, et sa limite

`turn-id.patch`, à côté de ce fichier, est le `git diff` exact contre le
checkout de l'agent à **`693641aa8b`** (v0.21.0).

**Le patch vit dans un checkout local.** `hermes update` fait un `git pull`
avec autostash (`_stash_local_changes_if_needed` /
`_restore_stashed_changes`) : le patch est mis de côté puis réappliqué, au
mieux, et un changement amont conflictuel l'échouerait en laissant un
autostash orphelin. Ce n'est pas une base durable — c'est pourquoi le patch
est versionné ici, et pourquoi la seule fin correcte est son adoption
amont.

## 5. Les limites de persistance

**Le contrat n'en demande aucune.** Le `turnId` voyage **dans l'événement**,
pas dans une table partagée : il n'y a donc rien à garder entre l'émission
et la lecture, et rien à perdre au redémarrage.

C'est la propriété qui distingue cette proposition de tout ce que G-29 a
écarté. `SessionsDeMission._identifiants` était une table en mémoire ; le
Ledger n'a pas de colonne de session ; `audit_log` a six lignes. Un contrat
qui dépend d'un état partagé hérite de toutes ces fragilités. Celui-ci n'en
dépend pas.

Hermes OS doit en revanche savoir **quels `turnId` il a frappés** pour
reconnaître les siens — et cela, il le persiste chez lui, dans son Ledger,
sur une identité dont il est propriétaire. G-18 a établi que l'histoire de
ses propres requêtes lui appartient.

## 6. Compatibilité runtime

| surface | verdict |
|---|---|
| ACP | le canal existe et arrive (mesuré) ; la restitution manque |
| Gateway | **aucun canal ouvert** — `_hosted_task` est privilégié et intraversable |

Le contrat serait donc **ACP seulement**. Le mode jetable
(`hermes_agent_cli`) n'a pas de canal non plus : ses huit drapeaux ne
comportent aucun identifiant, et en ajouter un serait une évolution
distincte de celle-ci.

## 7. L'échéance du 2026-09-14

`plugin_compat.COMPAT_REMOVAL_DATE = 2026-09-14` retire la couche qui fait
vivre les imports internes **des plugins**. Ce contrat-ci ne dépend d'aucun
import interne : il passe par le protocole ACP, servi par un paquet externe
versionné (`PROTOCOL_VERSION = 1`, schéma `refs/tags/v0.11.2`). L'échéance
ne le touche pas.

Elle touche en revanche l'observateur de G-28, qui reste non installé — et
qui, sans ce contrat, n'aurait de toute façon rien à corréler.

## 8. Les neuf cas de falsification

| cas | ce que le contrat répond |
|---|---|
| deux Runs dans la même session | chaque tour porte le `turnId` de son Run ; la session n'entre pas dans l'association |
| plusieurs Skills dans un même Run | tous les événements du tour portent le même `turnId` — c'est le résultat voulu, pas une ambiguïté |
| deux tâches Agent simultanées | `_meta` est par requête ; deux tours concurrents portent deux `turnId` |
| événement Skill sans `turnId` | aucune association. Pas de repli, pas d'approximation |
| Run sans événement Skill | rien à associer ; l'absence n'est pas une anomalie |
| redémarrage entre les étapes | l'identité est **dans** l'événement : rien à retrouver |
| `turnId` inconnu ou étranger | Hermes OS ne reconnaît que ce qu'il a frappé ; sinon il ignore |
| session reprise | le `turnId` est par tour, la reprise ne le touche pas |
| runtime sans support | les événements arrivent sans le champ → cas 4 → aucune association |

Le fil commun : **aucune association n'est acceptée si le `turnId` attendu
n'est pas explicitement présent.** Il n'y a pas de cas « au mieux ».

## 9. La demande à formuler amont

> Sur `session/prompt`, lire `_meta.hermes.turnId` — une chaîne opaque —
> le lier au contexte du tour, et le restituer inchangé dans chaque
> `on_skill_lifecycle` de ce tour, sous une clef distincte de `task_id` et
> de `session_id`. Absent en entrée, absent en sortie. Aucune
> interprétation, aucune validation, aucune valeur par défaut.

Trois fichiers, trois coutures existantes, zéro changement de protocole.
**`turn-id.patch` est cette demande, écrite et mesurée** — il ne reste qu'à
la proposer.

---

## Ce que Hermes OS ne fait pas en attendant

Il n'envoie toujours pas de `_meta`, et la raison a changé. G-30 disait :
l'agent ne restitue pas. Ce n'est plus vrai sur un agent patché. La raison
est maintenant double, et aucune des deux n'est levée :

- **le patch est local.** Un agent réinstallé ou mis à jour peut ne plus le
  porter, et un client qui poserait le champ n'aurait aucun moyen de savoir
  si le silence vient de « pas de mutation » ou de « pas de restitution » ;
- **rien ne lit la relation.** C'est le préalable que G-28 avait posé pour
  l'observateur, et il tient pour le client comme pour lui.

Un test garde cette abstention.
