# Cahier des charges — Hermes OS 2

> **Origine.** Un cahier de 111 points transmis le 2026-08-30, inspiré
> d'Agent OS, d'OpenRouter et d'OmniRoute. Ce document en est la version
> **confrontée au code** : les 111 points ont été sondés dans le dépôt les
> 2 et 3 septembre 2026, et le code source d'Agent OS a été lu.
>
> **Ce qu'il n'est pas.** Une liste de choses à construire. Sur 111
> points, **46 existent déjà et tiennent**, 28 n'existent qu'à moitié, 35
> manquent, 2 sont écartés. Un cahier qui demande de bâtir ce qui existe
> coûte autant qu'une roadmap en retard.

Principe directeur inchangé : **local-first · cloud-capable ·
verification-first**. Il ne remplace pas la règle qui prime dans
`CLAUDE.md` — Hermes Agent est le cerveau, Hermes OS son système
d'exploitation.

---

## 1. Ce qui a été mesuré

### 1.1 L'état des 111 points

| État | Compte | Part |
|---|---|---|
| ✅ existe et tient | 46 | 41 % |
| ⚠️ existe à moitié | 28 | 25 % |
| ❌ absent | 35 | 32 % |
| ⛔ écarté | 2 | 2 % |

Le détail point par point vit dans `ROADMAP.md`, chapitre I. Les faux
positifs des mots courants — `scope`, `score`, `canonical`, `objectif`,
`reserve` — ont été relus un par un ; six verdicts ont été retournés dans
les deux sens au passage.

### 1.2 Ce qu'Agent OS est réellement

Archive lue le 2026-09-02, version 2026-07-03.

**Une application Next.js en TypeScript** : 369 fichiers `.ts`, 124
`.tsx`, ~67 000 lignes, contre 1 112 lignes de Python. 86 modules dans
`src/lib`, **236 points d'API** sur 47 domaines, 46 fichiers de test.

**Aucune ligne n'est reprenable.** Ce qui se transfère est son modèle de
données, ses invariants et son modèle de menaces.

Sa largeur vient de ce qu'il embarque Leads, SEO, Music, Games, Video,
Thumbnails, NotebookLM. C'est exactement la largeur que le cahier
d'origine conseille lui-même de ne pas copier.

**Il intègre Hermes Agent en première classe** — `hermesMcp`,
`hermesJarvis`, `hermesWorkspace`, `hermesPhone`, `hermesGoals`.

---

## 2. Le modèle de menaces

C'est l'apport le plus important de la lecture d'Agent OS, et il ne
figurait pas dans le cahier d'origine. Leur suite `m8` est adverse ; ses
noms de tests décrivent des attaques que Hermes ne pare pas.

### 2.1 Injection par la mémoire

`m8-prompt-injection` et `m8-memory-poisoning` gardent une seule
propriété : **le contenu en quarantaine n'entre jamais dans le contexte
résident ni dans une recherche sans drapeau explicite**, et l'origine non
humaine est mise en quarantaine *quel que soit son contenu*.

Conséquence pour Hermes : la quarantaine mémoire n'est **pas** une
question de qualité de données. C'est la défense contre l'injection de
prompt. Aujourd'hui, une mémoire produite par un agent devient un fait
immédiatement — c'est un vecteur direct.

### 2.2 Dérive de configuration du workspace

`m8-hostile-config` détecte comme dérive un workspace qui **ajoute
`.claude/settings.json`, modifie `.claude/hooks`, ajoute un serveur MCP
dans `.mcp.json`, ou modifie `CLAUDE.md`**.

La menace : **un agent qui travaille sur un workspace peut modifier la
configuration qui le gouverne lui-même**. Un dépôt cloné peut planter des
hooks ou des serveurs MCP. Leur mécanisme est une table
`workspace_config_baselines` comparée à chaque run.

Hermes ne pare pas ça du tout, et le sujet touche une note déjà prise
dans ce projet : deux listes blanches hors dépôt décident de ce que
l'agent voit.

### 2.3 Fuite de secrets par le flux de sortie

`monitorChild` surveille la sortie de l'agent en temps réel :

- un **canary** — un faux secret planté dans l'environnement. S'il
  apparaît en sortie, le run est coupé et l'arbre de processus tué. On
  n'énumère pas tous les secrets, on en plante un qu'on connaît.
- un **tampon de report de 512 caractères**, pour qu'un secret coupé
  entre deux blocs soit quand même détecté.
- une détection de **silence** : plus de sortie pendant N ms → `stalled`.
- le disjoncteur reçoit aussi le **coût** à chaque tick.

Et `scanWorkspaceForSecrets` porte la discipline de ce dépôt : budget de
fichiers, plafond de taille, filtre sur la date de modification, et des
**drapeaux d'épuisement explicites** — un scan qui a manqué de budget est
rapporté comme tronqué, jamais comme propre.

### 2.4 Échappement de chemin

`m8-path-escape` : `../`, chemins absolus, et **échappement par lien
symbolique**. Aegis résout déjà avec `Path.resolve()` et
`is_relative_to()`, ce qui couvre les deux premiers ; le troisième mérite
un test qui le prouve plutôt qu'un raisonnement qui l'affirme.

### 2.5 Exfiltration par les réponses d'API

`m8-env-exfiltration` : aucune route ne rend `process.env`, aucune trace
de pile ne fuit l'environnement.

---

## 3. Ce qu'on reprend d'Agent OS, et ce qu'on change

### 3.1 Le Run Ledger — la table, pas le journal

**À reprendre.** La base vit hors de l'application. `PRAGMA
journal_mode=WAL; foreign_keys=ON; busy_timeout=5000`. Des migrations
versionnées. Et un invariant écrit dans le SQL lui-même :

```sql
UPDATE runs SET status = CASE
  WHEN status IN ('completed','failed','worker_lost') THEN status
  ELSE COALESCE(?, status) END
```

**Un état terminal ne peut pas être réécrit** — la garantie est dans la
requête, donc impossible à contourner par un chemin oublié.

**À ne pas reprendre : `run_events`.** Hermes a déjà un bus d'événements
durable, avec rejeu par plage de temps et motif de sujet, identifiants
idempotents, persistance avant notification. Porter leur seconde table
créerait **deux magasins d'événements** — l'architecture parallèle que le
cahier interdit à sa propre règle 4. Le Ledger porte les lignes de run ;
le bus porte les événements ; `run_id` corrèle.

**À améliorer.** Leur `seq = MAX+1` sous `BEGIN IMMEDIATE` sérialise les
écritures — acceptable pour un tableau de bord mono-utilisateur, à
mesurer avant de copier ici. Et leur dérivation de statut est une chaîne
de ternaires enfouie dans l'ajout d'événement : Hermes a déjà
`ExecutionStateMachine`, la table de transitions doit y vivre.

### 3.2 Le Contract — le modèle d'états, pas la syntaxe

**À reprendre.** `CriterionStatus = unmet | met | unverifiable |
violated` et `GateResult = passed | failed | unavailable`, avec leur
commentaire : *« never conflate unavailable with passed »*. Et le fait
que le tri-état soit gardé dans `m0-security` — c'est un invariant de
sécurité chez eux, pas une commodité.

**À changer.** Leurs critères s'écrivent en **EARS**, une syntaxe
d'exigences anglophone. Hermes travaille en français et ses missions
viennent de l'agent, pas d'un formulaire. On garde les états ; un critère
est un texte plus un vérificateur nommé.

### 3.3 Les checkpoints — garder les deux

**À reprendre.** `refs/agent-os/checkpoints/<id>` sur un commit détaché,
construit via un `GIT_INDEX_FILE` temporaire pour ne jamais toucher
l'index de l'utilisateur, `.gitignore` honoré, repli système de fichiers
avec manifeste de contenu et vérification d'intégrité par re-hachage.

**À améliorer.** `snapshot_manager` sauve l'**état de mission**, ce
qu'Agent OS ne fait pas. Un checkpoint Hermes devient le couple
`(état de mission, référence git)`, repris ensemble — plus que ce que
fait Agent OS.

### 3.4 La quarantaine mémoire — la contrainte, élargie

**À reprendre.** `CHECK(trust IN ('trusted','quarantined'))` avec
l'origine non humaine forcée en quarantaine et `promoted_by=null`. La
garantie est dans le schéma.

**À améliorer.** Hermes a **six tiers de mémoire** là où Agent OS en a
un. Deux valeurs suffisent pour un vault de notes ; pour une mémoire
sémantique et un graphe de connaissance, il faut aussi `last_verified_at`
et `promoted_by` — qu'ils ont déjà — plus la propagation de la confiance
le long des arêtes du graphe, qu'ils n'ont pas.

### 3.5 Le canary et le disjoncteur — à reprendre tels quels

C'est la pièce la plus directement transposable, et elle répond à deux
manques de Hermes à la fois : §14 secret broker et §22 disjoncteurs.

### 3.6 La séparation de l'état — leur réponse au §59

Un **« preserve set »** explicite, énoncé dans leur `UPDATE.md` :
`~/.agentic-os/config.json`, `~/.hermes/`, `~/.fcc/.env`, les dossiers de
credentials, le vault de notes. Une mise à jour remplace le code, garde
un **backup daté** à côté, et la règle est dite : *« mettez les réglages
dans `config.json`, pas dans le code »*.

Ils ont aussi un **updater piloté par agent** : sauvegarde d'abord,
préservation, vérification de version, application dans l'ordre,
reconstruction, **vérification que le tableau de bord s'ouvre**, rapport,
et demande avant toute étape risquée. C'est la discipline de ce dépôt
appliquée à une mise à jour.

---

## 4. Deux points où Hermes est devant

**Les sessions d'agent.** Ils ont mesuré `hermes -z` par tour à ~28 s de
démarrage à froid et l'ont contourné par un serveur global chaud sur
`:8642` (~8 s). HOS-138 a fait mieux : **une session ACP par mission**,
220 Mio mesurés par session, tours sérialisés par un verrou de session.
Pas de serveur global à surveiller.

**Le bus d'événements.** Durable, rejouable par plage et par motif,
identifiants idempotents. Leur `run_events` est un magasin de plus.

---

## 5. Ce qui est écarté, et pourquoi

**Le pool de comptes multiples chez un même fournisseur (§21).** Le
cahier demande de respecter les conditions des fournisseurs puis décrit
un mécanisme dont la finalité est d'agréger des quotas gratuits en
faisant tourner plusieurs comptes. C'est une violation des CGU de la
plupart d'entre eux. Le routage **multi-fournisseurs**, la santé, les
quotas et les disjoncteurs sont retenus ; la multiplication de comptes ne
l'est pas.

**SEO, Leads, CRM, Music, Games (§52, §54-55).** Le cahier les classe en
extensions au §86 puis les réintroduit dans sa liste finale. Ils
n'entrent pas tant que l'architecture de plugins (§87) n'existe pas :
une extension sans point d'extension est une fonctionnalité de plus dans
le noyau.

**OmniRoute comme couche.** Adaptateur derrière la même interface
qu'OpenRouter, jamais dépendance. Ses chiffres — 200+ fournisseurs,
dizaines de tiers gratuits — sont des annonces, pas des mesures. Et le
cahier avait raison sur un point vérifié : **zéro occurrence d'OmniRoute
dans le code d'Agent OS**.

**Rebâtir ce que Hermes Agent fait déjà.** L'agent embarque plus de 70
compétences et des connecteurs Telegram, Discord, Slack, WhatsApp,
Signal, e-mail. Avant toute section « connecteurs », vérifier ce que
l'agent fait — sinon c'est la violation exacte que
`test_hermes_agent_is_the_brain.py` empêche.

---

## 6. Les exigences retenues

L'ordre et le détail vivent dans `ROADMAP.md` §I.4. En résumé :

**Sécurité d'abord**, parce que trois des manques sont des contrôles et
non du confort : séparation de l'état, quarantaine mémoire, dérive de
configuration du workspace.

**Puis la traçabilité** : Contract, Run Ledger, vérification tri-état.
Sans elle, le cloud produit des heures de calcul dont on ne sait pas
rendre compte — mesuré en production dans la nuit du 29 au 30 août.

**Puis le cloud** : abstraction, pare-feu de données, quotas et santé.

**Puis les surfaces**, et enfin les plugins.

---

## 7. Ce qui restait ouvert

- Le classement `PUBLIC / INTERNAL / SENSITIVE / SECRET` d'un prompt est
  un problème ouvert. Une erreur envoie un secret chez un tiers. Le §15
  mérite son propre jalon et une décision explicite sur ce qu'on fait du
  cas ambigu — refuser par défaut, probablement.
- Le multi-utilisateur (§107) : aucune authentification n'existe et
  Hermes écoute sur `127.0.0.1`. Structurer `user → workspace → project →
  mission → run` sans construire d'authentification est faisable ; il
  faut décider si on le fait maintenant ou si on l'assume plus tard.

---

## 8. Les deux décisions, prises

Le §7 les laissait ouvertes. Elles sont tranchées ici, avec le
raisonnement, pour qu'on puisse revenir dessus en sachant pourquoi.

### 8.1 Le pare-feu de données refuse par défaut

**Décision : sur un cas ambigu, le cloud est refusé.**

Le §15 demande de classer un prompt `PUBLIC / INTERNAL / SENSITIVE /
SECRET`. Le classement automatique est un problème ouvert, et
l'asymétrie des erreurs est totale :

| erreur | conséquence |
|---|---|
| classer trop haut un contenu anodin | le cloud est indisponible, l'usager le voit et peut passer outre |
| classer trop bas un secret | il part chez un tiers, il y est **indéfiniment**, et personne ne le sait |

La première erreur est visible, réversible, et son coût est une gêne. La
seconde est invisible, irréversible, et son coût n'a pas de plafond. Un
classement qui hésite doit donc pencher du côté visible.

**Ce que ça implique, et qu'il faut assumer :** le cloud sera plus
souvent refusé qu'il ne serait strictement nécessaire, surtout au début,
avant que les règles ne soient affinées sur des cas réels. C'est le prix,
et il est payé en confort, pas en sécurité.

**Trois garde-fous pour que ce ne soit pas insupportable :**

1. **Le refus est nommé.** Jamais « indisponible » — toujours *ce qui* a
   déclenché la classification, pour que l'usager puisse juger.
2. **L'usager peut passer outre, une fois, explicitement.** Un
   contournement est une décision tracée dans le Ledger, pas un réglage
   qu'on met à « permissif » et qu'on oublie.
3. **Un contournement enseigne.** Un motif écarté à la main trois fois
   devient une proposition de règle — soumise, jamais appliquée
   d'office.

**Ce qui n'est pas décidé :** la liste des motifs de classification.
Elle se construira sur des cas réels, pas d'avance. Une liste imaginée en
chambre attrape les secrets qu'on a imaginés.

### 8.2 La structuration se fait maintenant, sans authentification

**Décision : les identifiants `user`, `project`, `workspace` entrent dans
le modèle de données dès le Run Ledger. L'authentification, non.**

Le §107 demande de structurer `user → workspace → project → mission →
run` pour ne pas verrouiller l'architecture. Deux moments possibles :
maintenant, ou quand le besoin arrive.

**Maintenant, pour une raison de coût et non de besoin.** Le jalon 5
crée les tables du Run Ledger. Y ajouter trois colonnes à ce moment-là
coûte trois colonnes. Les ajouter après coûte une migration sur des
données réelles, et une relecture de tout ce qui lit ces tables. Le
rapport est d'un contre dix, et la nuit du 29 au 30 août a montré ce que
coûte une trace qu'on n'a pas prévue : elle a été écrite en urgence, à
trois heures du matin, pendant que la production tournait.

**L'authentification, non**, et c'est délibéré. Hermes écoute sur
`127.0.0.1`, sur un poste personnel. Une authentification apporterait
une surface — gestion de jetons, de sessions, de mots de passe — sans
protéger contre rien de réel aujourd'hui. Ce serait de la sécurité
apparente, ce que ce dépôt refuse ailleurs.

`user_id` vaut donc `"local"` par défaut, `project_id` porte le projet
courant. Le jour où une seconde personne ouvre Hermes, il y aura une
colonne à remplir, pas un schéma à refaire.

**La ligne à ne pas franchir :** tant qu'il n'y a pas
d'authentification, `user_id` ne doit **jamais** servir de contrôle
d'accès. C'est un champ de traçabilité. Un test le garde, sinon la
tentation viendra d'elle-même le jour où quelqu'un cherchera à cloisonner
deux projets — et un contrôle d'accès fondé sur un champ que n'importe
qui peut poser n'est pas un contrôle d'accès.
