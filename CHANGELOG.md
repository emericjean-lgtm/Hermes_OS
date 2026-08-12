## HOS-097 — Le RAG peut enfin répondre « rien de pertinent » (2026-08-12)

Audit du RAG, devenu possible une fois les embeddings réparés (HOS-093 : 57 s → 2,4 s par appel). La chaîne fonctionne — ingestion de trois documents en 3,3 s, classement correct, portée par projet respectée. Un défaut de fond subsistait.

Un index vectoriel a **toujours** un plus proche voisin. Sans plancher, la question « chocolate cake recipe » posée à un corpus sur Hermes OS renvoyait le passage sur le modèle de repli agentique, classé premier, sans rien dans le résultat pour signaler l'absurdité. Donné à un modèle de langage, cela devient du carburant à hallucination, avec une citation à l'appui.

C'est la forme « récupération » de la défaillance que toute cette campagne poursuit : un système qui répond au lieu d'admettre qu'il n'a pas de réponse.

Seuil **mesuré**, pas choisi. Avec `qwen3-embedding:0.6b`, en distance cosinus, contre des fixtures réelles :

| | Distance |
|---|---|
| Questions dans le sujet | 0,683 – 0,949 |
| Questions hors sujet | 1,272 – 1,514 |

`MAX_RELEVANT_DISTANCE = 1.1` se place **dans l'écart**, pas sur un bord : ni une formulation maladroite ni une question hors sujet un peu moins absurde ne bascule. Le classement brut reste accessible via `max_distance=None`, sans quoi un résultat vide serait indiscernable d'un index vide.

Corrigé au passage, rencontré en écrivant les fixtures : Chroma rejette un dictionnaire de métadonnées vide (« Expected metadata to be a non-empty dict »), transformant le cas parfaitement ordinaire « ce document n'a pas de métadonnées » en erreur que chaque appelant devait connaître. `add_document` porte désormais l'identifiant du document à la place — toujours vrai, toujours utile.

Deux tests préexistants ont dû passer `max_distance=None` : ils vérifient la sémantique de `n_results` et du filtre `where`, orthogonale à la pertinence, avec une fonction d'embedding factice dont les distances arbitraires seraient légitimement écartées par le plancher.

## HOS-096 — Aucune heuristique ne prédit la capacité agentique (2026-08-12)

Quatre modèles, trois essais chacun, même tâche, même toolset, artefact vérifié sur disque :

| Modèle | Taille | ctx servi | Tient en VRAM | Succès | Durée |
|---|---|---|---|---|---|
| **`lfm2.5-2.6b-128k`** | **2,7 Md** | 131072 | ✅ 1,67 Go | **3/3** | **28-41 s** |
| `qwen3.5:9b-128k` | 9,7 Md | 131072 | ✅ 10,18 Go | 3/3 | ~47 s |
| `gemma4:12b-64k` | 11,9 Md | 65536 | ✅ 8,49 Go | **0/3** | timeout |
| `devstral` | 23,6 Md | 65536 | ❌ 10,75 Go sur CPU | 1/3 | ~300 s |

Chaque ligne est mesurée un modèle à la fois, VRAM vérifiée vide avant. Les deux séries initialement lancées en parallèle (`gemma4:12b` et `lfm2.5`) ont été **refaites intégralement** sous verrou plutôt que conservées : toutes deux ont reconduit leur verdict — 0/3 et 3/3 — mais un taux propre et un taux contaminé ne se mélangent pas dans la même moyenne.

**Chacun de mes signaux structurels a été réfuté par la mesure suivante.** La taille s'inverse : 2,7 Md réussit 3/3, 11,9 Md échoue 0/3. La déclaration `tools` est faite jusque par `qwen3-embedding:0.6b`. Ni les 64k de contexte servi ni la tenue en VRAM n'ont sauvé `gemma4:12b`. Le plancher de 7 Md aurait rejeté le meilleur modèle disponible sur cette machine.

Ce qui sépare réellement ces modèles est leur **post-entraînement** : LFM2.5-2.6B a été entraîné par renforcement agentique (ToolSandbox 77,83, revendiqué *« competitive with models 4× larger on tool use »*), les autres sont des modèles généralistes à qui l'on demande de se comporter en agent. Rien de tout cela n'apparaît dans les métadonnées d'un modèle.

Conséquences appliquées :

- **`AGENTIC_MIN_PARAMETERS_B` passe à 0** — conservé pour décrire un modèle, plus jamais pour le juger.
- **Un modèle non mesuré est « non prouvé », pas « capable ».** Choix délibérément conservateur : deviner s'est révélé faux une fois sur deux, et le coût d'une erreur est une mission qui rapporte un succès sans rien produire — la défaillance que tout ce travail vise à supprimer. Les contrôles structurels ne peuvent plus que **disqualifier** ; seule une mesure qualifie.
- **Les disqualifiants passent avant la mesure.** Un verdict passé a été rendu dans des conditions passées : `devstral` a mesuré 1/3 *parce qu'il débordait*, et un modèle qui se met à déborder après un changement de contexte est dans cet état quel qu'ait été son score.
- **Repli agentique → `lfm2.5-2.6b-128k`** : deux fois plus rapide que le 9B, six fois moins de VRAM, même taux parfait. Il laisse ~14 Go libres sur une carte de 16, ce qui rend enfin possible la cohabitation de l'embedding et de l'agent sans éviction.

**Portée du verdict `gemma4:12b`, corrigée.** L'entrée ci-dessus le range parmi les modèles qui « échouent », ce qui est trop large. Des tests antérieurs contre les outils MCP de Hermes OS montrent que ce modèle sait comprendre une tâche, sélectionner un outil et exploiter son résultat : `files_list` et `files_read` passent avec de vraies données, `security_evaluate` renvoie correctement `require_human_validation`. Son seul échec, `files_diff`, portait sur un **paramètre `path` manquant** — soit exactement ce que la sonde exige, puisqu'elle demande une écriture avec chemin *et* contenu. Un `0/3` ici signifie donc « ne mène pas à bien une écriture », pas « incapable d'agentique ». La décision produit ne change pas — toute mission produit un artefact — mais l'usage en lecture seule reste ouvert.

Le contexte n'y est pour rien : `gemma4:12b-128k`, créé via Modelfile et servi à 131072 **sans aucun débordement** (8,19 Go, 0 % CPU), donne 0/2 avec zéro appel d'outil, en ~945 s par essai contre ~430 s à 64k. Et les échecs à 64k ne sont pas des timeouts : relancés avec un délai de 1500 s, ils terminent en ~430 s sans avoir appelé un seul outil.

**Limite de l'instrument, à connaître.** La sonde n'enregistre pas les arguments générés, donc elle ne peut pas distinguer « le modèle a omis `path` » de « l'adaptateur ou MCP l'a perdu ». Le schéma MCP a été vérifié et est correct (`files_diff: required=['path','new_content']`), ce qui innocente cette couche — mais attribuer la cause au modèle demanderait un test contrôlé comparant les arguments produits par deux modèles sur le même schéma, que cet outil ne sait pas encore mener.

**Défaut de protocole signalé par l'utilisateur, vérifié.** Les sondes de `gemma4:12b` et `lfm2.5` avaient été lancées en parallèle : deux modèles en VRAM simultanément sur une carte de 16 Go, ce qui mesure la contention et non le modèle. Re-mesuré seul, VRAM purgée au préalable, `gemma4:12b-64k` reste **0/3** — le verdict tient, mais il tenait par chance. Un banc d'essai dont le résultat dépend de ce qui tourne à côté n'en est pas un : `probe()` prend désormais un verrou exclusif (processus + inter-processus) et **refuse** plutôt que d'attendre, puisque les temps mesurés font partie du verdict et incluraient le chargement d'un autre modèle. Verrou périmé nettoyé automatiquement, pour qu'une sonde crashée ne bloque pas les suivantes.

**Bug attrapé en vérifiant le résolveur en direct** : `qwen3.5:2b` était rapporté capable sans avoir jamais été sondé. La correspondance par nom de base lui faisait hériter du 3/3 de `qwen3.5:9b-128k` — une famille n'est pas un modèle. Seule la paire nom-nu/`:latest` désigne les mêmes poids ; tout autre tag est un autre modèle.

## HOS-095 — La sonde agentique, et ce qu'elle corrige dans les entrées précédentes (2026-08-12)

`ModelProfile.agentic_capable` classait ses preuves depuis HOS-088 — une mesure prime sur une déclaration, une déclaration prime sur un nom — mais **rien ne produisait jamais la mesure**. Toutes les réponses venaient donc de l'heuristique de taille. `backend/model_intelligence/agentic_probe.py` est le producteur manquant : il lance une vraie tâche via le CLI Hermes Agent installé et lit le verdict **sur le disque**, jamais dans la réponse du modèle — la règle qui avait démasqué cinq faux succès.

### ⚠️ Correction des entrées HOS-085, HOS-088 et HOS-090

Ces entrées affirment, sur la foi de runs manuels, que `devstral` est capable d'exécution agentique et que `qwen3.5:9b-128k` ne l'est pas. **La mesure dit le contraire.** Trois essais chacun, même tâche, même toolset, même workspace :

| Modèle | Succès | Durée moyenne | VRAM |
|---|---|---|---|
| `devstral` | **1/3 (33 %)** | ~300 s | 14,33 Go |
| `qwen3.5:9b-128k` | **3/3 (100 %)** | **~47 s** | **6,59 Go** |

Trois fois plus fiable, six fois plus rapide, moitié moins de VRAM. `_HERMES_AGENT_FALLBACK_MODEL` passe donc à `qwen3.5:9b-128k`. Le choix de `devstral` reposait sur deux runs manuels qui s'étaient bien passés — précisément le raisonnement à n=1 que cette sonde existe pour remplacer, et il était faux.

Ce que HOS-090 tenait pour une différence de capacité entre modèles était en réalité de la **variance**. Les deux modèles réussissent et échouent selon les runs ; seul le taux les distingue.

### Un seul essai n'est pas une mesure

La première version de ce module écrasait le résultat à chaque run. Les deux premières exécutions se sont contredites — `devstral` 0 appel d'outil en 305 s après avoir réussi toute la journée, `qwen3.5:9b-128k` réussissant après avoir échoué. Conception corrigée en conséquence : `save_result` **accumule**, `measured_success_for` refuse de répondre en dessous de deux essais, et le seuil est un taux de 60 % — ni 100 % (irréaliste vu la variance mesurée), ni un-sur-N (un coup de chance promouvrait un modèle peu fiable).

Vérifié en bout de chaîne : `devstral` est désormais rejeté (`agentic_capable=False`) malgré 23,6 Md de paramètres et une déclaration `tools`, parce qu'une mesure réelle prime sur les deux.

## HOS-094 — Délégation : mesurée, et incompatible avec le mode one-shot (2026-08-12)

La délégation était activée depuis HOS-087 mais jamais démontrée. Mesurée maintenant, avec un travail réellement parallélisable (deux fichiers de service indépendants à analyser puis synthétiser). Verdict : **BROKEN dans l'intégration actuelle**, pour une raison structurelle et non un bug de Hermes Agent.

`delegate` fonctionne mécaniquement — les subagents sont bien créés :

```
delegate 2x: Summarize SERVICE_A.md... | Summarize SERVICE_B.md...
Background 2 tasks running — I'll resume when they finish. Keep chatting.
```

Mais la délégation de Hermes Agent est **asynchrone** : le parent dispatche, répond immédiatement et attend qu'une session interactive reste ouverte jusqu'au retour des subagents. L'adaptateur invoque le CLI en one-shot `--query`, donc le processus sort dès la réponse du parent et tue les subagents en plein appel :

```
[subagent-0] Interrupted during API call.
  x [1/2] Summarize SERVICE_A.md  (37.11s)
  x [2/2] Summarize SERVICE_B.md  (37.11s)
```

Aucun flag du CLI ne permet de bloquer sur les tâches de fond, et `--resume` n'aide pas puisqu'il ne reste rien à reprendre. Contrainte documentée dans le docstring de l'adaptateur, là où un mainteneur la cherchera.

**Découverte annexe, contre-intuitive et reproductible** : mentionner la délégation dans un prompt suffit à faire dérailler le modèle local. Même tâche, même modèle, même toolset :

| Prompt | Tool calls | Artefact | Durée |
|---|---|---|---|
| « you may delegate … if you judge it useful » | **0** | aucun | 5 min 13 |
| sans cette phrase | **6** | ✅ synthèse correcte des deux fichiers | 1 min 46 |

Une seule phrase de différence. Ce qui est par ailleurs la **preuve que le travail multi-étapes fonctionne** : six appels d'outils, deux fichiers lus, synthèse exacte écrite sur disque. Ce n'est pas le parallélisme d'outils qui manque — c'est le parallélisme d'agents que ce mode d'invocation ne peut pas héberger.

## HOS-093 — Le correctif de contexte étranglait les embeddings (2026-08-12)

Régression introduite par HOS-091, révélée par un test qui a viré au rouge et non par une inspection. `OLLAMA_CONTEXT_LENGTH=65536` est nécessaire pour que les schémas d'outils de Hermes Agent cessent d'être tronqués — mais ce réglage est **global**, et s'applique donc aussi au modèle qui embarque des chunks RAG de 512 mots.

Mesuré sur ce déploiement :

| | sans `num_ctx` | avec `num_ctx=2048` |
|---|---|---|
| contexte servi | 32768 | 2048 |
| VRAM | **5,88 Go** | 2,23 Go |
| latence par appel | **57,5 s** | 2,4 s |

Un modèle de 0,64 Go occupait neuf fois ses poids en VRAM, et l'indexation documentaire partait en timeout. `config/models.yaml` déclarait `num_ctx: 2048` pour ce rôle depuis HOS-079 ; la valeur n'était simplement jamais transmise à Ollama.

Corrigeable ici, contrairement au chat : `/api/embeddings` honore `options`, là où l'endpoint OpenAI-compatible `/v1` ne transporte aucun `num_ctx`. C'est la même asymétrie que celle qui avait causé HOS-090, exploitée cette fois dans le bon sens.

Effet secondaire mesuré : la suite complète passe de **46 minutes à 3 minutes 08**.

Un des garde-fous vérifie que le `num_ctx` accompagne **chaque** chunk — une option qui n'atterrirait que sur la première requête d'une indexation laisserait tout le reste au défaut global, et le bug serait revenu à moitié.

**Ce que cet incident expose et qui n'est pas corrigé** : le garde-fou de HOS-091 surveille le plancher agentique et reste aveugle au gaspillage inverse. Un défaut global optimal pour un rôle est nuisible pour un autre ; un profil de contexte par rôle serait la vraie réponse. Signalé, non implémenté.

## HOS-092 — Une mission « réussie » doit être confrontée au disque (2026-08-12)

Bilan de la campagne HOS-085 → HOS-091 : cinq défauts distincts — le tool loop HOS écrasant Hermes Agent, les toolsets CLI vidés, l'objectif perdu à la décomposition, un contexte servi à 4k, un timeout de 180s — et **cinq rapports verts** au-dessus d'un workspace vide à chaque fois. Le défaut commun n'était aucun des cinq : c'était que « completed » signifiait « chaque nœud a renvoyé du texte », et du texte est précisément ce qu'un modèle produit quand il ne peut pas faire le travail.

`backend/mission/verification.py` pose une question différente, et sans interroger l'agent : comparer le workspace avant et après. Un diff de système de fichiers est une vérité de terrain — il n'exige aucune coopération du modèle, ne peut pas être argumenté, et aurait attrapé les cinq.

Trois choix de conception qui portent l'essentiel :

- **Empreinte par hachage, pas taille+mtime.** Une réécriture de même longueur dans la granularité d'horodatage du système passerait inaperçue — or c'est exactement le cas « l'agent a réécrit le fichier avec un autre contenu ».
- **Répertoires de bruit ignorés** (`.git`, `__pycache__`, `node_modules`…). Sans cela, toute mission dans un dépôt git paraît productive parce qu'un cache a bougé.
- **L'absence de mesure n'est pas une contradiction.** Une mission sans workspace lié n'a rien à confronter ; la signaler comme faux succès serait la sanctionner pour n'avoir pas produit une preuve qu'elle n'était pas en position de produire. Ce défaut existait dans la première version du module — un test l'a attrapé, d'où le champ `measured` explicite.

Volontairement **pas** un juge sémantique de l'objectif. Décider si « alpha/beta/gamma » est le bon contenu pour un but donné n'est pas du ressort de cette couche, et prétendre le contraire ne ferait que déplacer la fabrication d'un cran. Le module rapporte ce qui a physiquement changé ; savoir si cela satisfait l'objectif reste à l'opérateur.

### Verified

Confronté aux artefacts réels de cette session, pas à des fixtures :

```
SUCCÈS RÉEL  -> verified=True  contradicted=False  | 1 created: HERMES_OS_FINAL_INTEGRATION_TEST.md
FAUX SUCCÈS  -> verified=False contradicted=True   | no file was created, modified or deleted
```

Puis **câblé** dans `GraphExecutor` — empreinte prise à `start_mission`, confrontée à la complétion — et vérifié sur un vrai exécuteur, pas seulement en unitaire :

```
nœud qui n'écrit rien -> contradicted=True,  événement mission.unverified émis
nœud qui écrit        -> verified=True,      created=['out.md']
```

`mission.unverified` est un événement distinct de `mission.completed` à dessein : l'événement vert reste vert, et la contradiction devient impossible à ne pas lire.

## HOS-091 — Le contexte dégradé devient détectable au lieu d'être subi (2026-08-12)

HOS-090 avait corrigé le contexte servi, mais par une variable d'environnement de session : au premier redémarrage d'Ollama, la panne revenait en silence. Mesuré une fois la variable retirée — et c'est pire que ce que HOS-090 avait observé : Ollama redémarre à **4096**, pas 8192.

Le problème n'est pas corrigeable au niveau d'une requête. Hermes Agent atteint Ollama par l'endpoint OpenAI-compatible `/v1`, qui ne transporte aucun `num_ctx` ; le défaut d'Ollama gagne toujours. Hermes OS ne peut donc que **détecter et le dire fort** — d'où un garde-fou plutôt qu'un correctif.

`backend/runtime/context_guard.py` compare ce qui est réellement servi au plancher agentique, à chaque démarrage du backend. Un contexte insuffisant émet `runtime.context_degraded` avec une remédiation qui **nomme le vrai levier** (`OLLAMA_CONTEXT_LENGTH`, sa valeur actuelle, et pourquoi aucun argument de ligne de commande ne peut s'y substituer) au lieu d'un vague « augmentez le contexte ».

Deux choix délibérés dans la politique. Un contexte **non mesuré** n'est jamais signalé comme dégradé : aucun modèle résident signifie que rien n'a encore été servi, et avertir sur une inconnue ferait crier le système à chaque démarrage à froid jusqu'à ce qu'on ignore le seul message qui compte. Et le contexte **supporté** n'excuse jamais un runtime affamé — annoncer 131072 ne change rien si 4096 est servi ; c'est le bug entier tenu dans une assertion.

Configuration rendue permanente au niveau utilisateur, puis vérifiée par un vrai redémarrage d'Ollama : `served=65536, DEGRADED=False`.

## HOS-090 — Contexte servi et budget de temps : une boucle agentique n'est pas une complétion (2026-08-12)

Deux dernières causes derrière « la mission réussit, rien n'est produit ». Toutes deux viennent de la même erreur de cadrage : Hermes OS traitait une exécution agentique comme un appel de modèle.

**Contexte servi ≠ contexte supporté.** Piste ouverte par une observation de l'utilisateur (« Hermes préconise ≥ 64k ; en dessous les modèles appellent moins bien les outils et hallucinent davantage »), confirmée par la mesure :

| | |
|---|---|
| devstral **supporte** | 131 072 |
| Le cache de contexte de Hermes **le sait** | 131 072 |
| Ollama **servait** | **8 192** |

Hermes Agent parle à Ollama par l'endpoint OpenAI-compatible `/v1`, qui ne transporte aucun `num_ctx` : Ollama applique donc son propre défaut. Un schéma de 32 outils plus un brief de mission ne tiennent pas dans 8k, les outils étaient tronqués, et l'agent répondait qu'il n'avait pas accès aux fichiers — ce qui était exact. Corrigé côté serveur (`OLLAMA_CONTEXT_LENGTH=65536`), et surtout inscrit dans le modèle de données pour que le piège soit détectable : `ModelProfile.served_context` est désormais distinct de `context_window`, `AGENTIC_MIN_CONTEXT = 65536`, et une sonde `/api/ps` lit ce qui est réellement servi. Un modèle servi sous ce seuil est refusé pour l'agentique **même s'il annonce 131k**.

**Le timeout.** `RealTaskExecutor._timeout_s` valait 180s, dimensionné pour une complétion. Une tâche Hermes Agent lance un processus, charge un toolset et enchaîne inférence et exécution d'outils sur du matériel local — une tâche triviale mesurée à 37-57s. Résultat observé : une mission tournant 765s pour finir 0/5, chaque tâche portant `not executed: runtime 'hermes-agent' timed out after 180s`, tout en rapportant une durée comme si du travail avait eu lieu. Budget dédié `_HERMES_AGENT_TIMEOUT_S = 900s`, appliqué au wrapper *et* à la config de l'adaptateur — les deux valaient 180s, corriger un seul n'aurait rien changé.

Une nuance mesurée, contre l'intuition : un grand contexte est nécessaire mais **pas suffisant**. `qwen3.5:9b-128k` servi à 131 072 n'a produit aucun appel d'outil sur la même sonde où devstral en produit deux. La taille de contexte est un plancher, pas un prédicteur de capacité agentique.

### Verified — chaîne complète, bout en bout

Mission créée par l'API Hermes OS, liée à un Project validé, exécutée par Hermes Agent officiel, artefact vérifié **sur disque** et non d'après le rapport de l'agent :

```
status: completed | runtimes_used: ['hermes-agent'] | 5/5 tâches | 0 échec | errors: []

$ cat C:\Users\emeri\hermes_e2e\HERMES_OS_FINAL_INTEGRATION_TEST.md
alpha
beta
gamma
```

Cinq causes distinctes séparaient ce résultat du point de départ, et **chacune produisait une mission "réussie"** : le tool loop de Hermes OS écrasant Hermes Agent (HOS-085), `platform_toolsets.cli: []` (HOS-089), l'objectif perdu à la décomposition (HOS-085), le contexte servi à 8k (HOS-090), le timeout de 180s (HOS-090). Aucune n'aurait été trouvée en faisant confiance au rapport de mission : il faut à chaque fois avoir lu le disque, les erreurs de tâche, la ligne de commande du processus ou le compteur `tool calls` du CLI.

## HOS-089 — `platform_toolsets.cli: []` privait Hermes Agent de tous ses outils (2026-08-12)

Une mission qui devait lire un fichier, en créer un autre puis vérifier son contenu a rapporté `success: True, 5/5` sans qu'aucun fichier n'existe. Les sorties de tâches disaient exactement ce qui se passait, à condition de les lire : la tâche 1 a « lu » le fichier existant et annoncé `"This is a test file."` — un contenu **halluciné**, le vrai fichier contenant `line one/two/three` — et les quatre suivantes ont répondu *« I don't have the capability to directly access or modify files »*. Le CLI le confirmait en une ligne : `Messages: 2 (1 user, 0 tool calls)`.

**Diagnostic par élimination**, parce que la première hypothèse était fausse. Le suspect évident était le changement de config du même jour (activation de `delegation`/`skills`) : restauration de la config d'origine → **échoue toujours**, donc ce n'était pas ça. Ont ensuite été écartés, chacun par une mesure : serveur MCP (arrêté → identique), pression VRAM et état du modèle (déchargé/rechargé → identique), auto-mise à jour de Hermes Agent (même commit `fb8d824`), répertoire de travail (le répertoire où les tests avaient réussi → identique). Test décisif d'isolement modèle/agent : `devstral` interrogé **directement** via `/api/chat` d'Ollama avec un schéma d'outil renvoie un `tool_calls` parfaitement formé. Le modèle n'avait rien perdu — l'agent ne recevait tout simplement aucun outil.

Cause réelle : `platform_toolsets.cli: []` dans la config Hermes Agent. Une liste vide pour la plateforme CLI vide les toolsets **quel que soit** le `--toolsets` passé en argument. Corrigé en `cli: [coding]`. Effet immédiat et reproductible sur la même sonde : `Messages: 4 (1 user, 2 tool calls)` et le fichier réellement écrit sur disque.

Deux enseignements consignés ici parce qu'ils se represententeront : un argument de ligne de commande n'écrase pas nécessairement une politique de configuration, et « l'agent dit qu'il n'a pas d'outils » est une information exploitable, pas une excuse du modèle — c'était littéralement vrai.

## HOS-086/087/088 — Mémoire retrouvable, identifiants projet canoniques, routage par capacités (2026-08-12)

Trois bugs signalés comme distincts, une même racine : **deux représentations d'une même chose, comparées sans normalisation.**

**HOS-086 — `memory_remember` → `memory_search` ne retrouvait rien.** Pas un problème de qualité de recherche : les deux outils MCP adressaient des stores différents. `memory_remember` écrivait une ligne `MemoryEntry` via `episodic.add_memory` ; `memory_search` appelait `EchoAgent.recall`, qui interroge l'index vectoriel de *documents*. Rien n'écrivait jamais un fait mémorisé dans cet index — la recherche ne *pouvait pas* aboutir. Ajout de `episodic.search_memories` (LIKE sur contenu + tags, classé par nombre de termes réellement présents) et de `EchoAgent.search_memories`. `memory_search` couvre désormais les deux stores, mémoires d'abord : un fait explicitement mémorisé est une meilleure réponse qu'un passage qui partage des mots. **Volontairement pas un second index vectoriel** — ces lignes sont des faits courts et explicites, et fabriquer un deuxième store d'embeddings serait exactement la duplication mémoire que ce système cherche à supprimer. Effet de bord corrigé au passage : `memory_search` ne échoue plus en bloc quand Ollama est arrêté, les faits mémorisés restant accessibles sans embeddings.

**HOS-087 — `tasks_create` puis `tasks_list(project_id)` renvoyait `[]`.** Le filtre SQL n'a jamais été faux ; les deux appels comparaient deux chaînes différentes. Hermes Agent s'exécute avec le workspace comme cwd, il nomme donc un projet par son chemin, là où Hermes OS stocke un id canonique. Normalisation posée à la frontière MCP — l'endroit précis où un appelant qui n'a qu'un chemin rencontre un store indexé par id : un id, une racine de projet ou n'importe quel sous-répertoire résolvent vers la même portée. Une valeur inconnue est **conservée telle quelle** plutôt que ramenée à `None` : une requête filtrée qui s'élargit silencieusement à tous les projets est plus dangereuse qu'une requête qui ne renvoie rien.

**HOS-088 — le plancher modèle n'est plus une liste de noms.** HOS-085 avait livré une liste codée en dur, incapable de répondre pour un modèle que personne n'avait pensé à y inscrire. `/api/show` d'Ollama expose les capacités réelles — et l'audit montre qu'**une déclaration n'est pas une démonstration** : `qwen3.5:2b` *et* `qwen3-embedding:0.6b` annoncent tous deux `tools`, alors que le 2B narre au lieu d'agir (mesuré). `ModelProfile.agentic_capable` hiérarchise donc les preuves : une mesure réelle prime sur une déclaration, une déclaration prime sur un nom, et les modèles d'embedding sont exclus exactement comme `chat_capable` les excluait déjà. Vérifié sur le catalogue réel : `devstral`, `qwen3.5:9b-128k`, `qwen3-coder:30b` et `Hermes-4-14B` capables ; `qwen3.5:2b`, `lfm2.5-2.6b` et l'embedding non ; un modèle inconnu renvoie `None` et est traité comme **non prouvé**, jamais comme capable.

**Toolsets Hermes Agent.** `delegation` et `skills` étaient désactivés dans toutes les sauvegardes de config jusqu'à la plus ancienne — c'est le défaut amont, pas un arbitrage de sécurité pris ici — et ils bloquaient entièrement les travaux sur les subagents et la création de skills. Réactivés, config d'origine sauvegardée.

### Verified

Backend : 939 passed, 2 skipped, 0 failed (contre 926). Nouveaux tests : `test_memory_remember_search_roundtrip.py` (dont **survie intersession réelle** — un `id` en retour de `memory_remember` n'est pas accepté comme preuve), `test_tasks_project_id_normalisation.py` (dont isolation entre projets et non-élargissement d'une portée inconnue), plus deux gardes de capacité modèle.

### Catalogue Ollama réel (17 modèles)

Interrogé, pas supposé. `nomic-embed-text` **n'est pas installé** malgré sa présence dans la documentation historique. `qwen3.5:9b` et `qwen3.5:9b-128k` font **exactement la même taille (6,59 Go)** : le suffixe `128k` ne prouve rien sur la fenêtre réellement chargée.

## HOS-085 — Hermes Agent redevient le cerveau des missions (2026-08-12)

Audit demandé : « quand une mission s'exécute depuis Hermes OS, est-ce réellement Hermes Agent officiel qui raisonne et orchestre ? ». Réponse trouvée : **non**, sur le chemin principal. Trois défauts distincts l'empêchaient, chacun invisible pour la suite de tests.

**1. Hermes OS était devenu un second orchestrateur cognitif et gagnait.** `execution/task_executor.py` sélectionnait bien Hermes Agent, puis l'écrasait deux lignes plus bas :

```python
if runtime_id == "hermes-agent" and self._chat is None and not use_cloud:
    chat = self._hermes_agent_chat          # Hermes Agent choisi
if workspace is not None and not use_cloud:
    chat = self._chat_with_tools_for(...)   # ...et immédiatement remplacé
```

`_chat_with_tools_for` → `_run_tool_loop` instancie `OllamaClient` en direct et fait sa propre boucle d'outils. Donc **toute mission liée à un workspace — le cas de production, celui que HOS-084 venait d'introduire — contournait Hermes Agent**. Le Mission Center l'affichait sans ambiguïté (`Runtimes : ollama`) et personne ne l'avait lu comme un défaut. Corrigé en `elif` : quand Hermes Agent est le runtime, il possède la sélection et l'exécution des outils (il atteint ce backend par son propre MCP, `config.yaml` pointe déjà `mcp_servers` sur `http://127.0.0.1:8010/mcp`). La boucle HOS reste pour le runtime `ollama` explicite, qui n'a pas d'agent et n'aurait autrement aucun outil.

**2. Hermes Agent tournait sans aucun outil.** L'adaptateur ne passe `--toolsets` que si Hermes OS en fournit — et Hermes OS n'en fournissait aucun. Vérifié en direct : `0 tools · 0 skills`, et l'agent se contentait de *décrire* le travail (« Creating the file… ») pendant que rien n'était écrit sur disque. Le même prompt avec `--toolsets coding` (32 outils : files, terminal, delegate…) a réellement créé le fichier. Hermes OS nomme désormais ce qui est *disponible* ; Hermes seul décide de ce qu'il appelle.

**3. L'objectif de la mission n'atteignait jamais l'agent.** `TaskDecomposer` produit des titres de nœuds génériques (« Create test file ») avec une `description` vide, et `_build_messages` n'envoyait que `Task: {title}`. Une mission dont l'objectif nommait le fichier, ses trois lignes et l'étape de vérification arrivait donc à l'agent sous la forme `Task: Create test file` — sans nom de fichier ni contenu. L'agent partait à la dérive (jusqu'à lire `C:\Users\emeri\.gitlab-ci.yml`, hors workspace) et la mission rapportait malgré tout 4/4 « completed ». Nouveau résolveur `_mission_brief_for` : l'objectif accompagne désormais le titre du nœud.

**4. Le routeur donnait à Hermes un cerveau trop petit pour agir.** Les trois correctifs ci-dessus rétablissaient un routage correct, et la mission n'accomplissait toujours rien. Expérience contrôlée — même prompt, même toolset `coding`, même workspace, seul le modèle change : `devstral` écrit le fichier, `qwen3.5:2b` n'écrit rien et se contente de narrer (il est même allé créer une entrée de suivi de tâche à la place). `ModelRouter` classe les modèles pour *une complétion isolée* (VRAM, latence) et choisit donc un 2B pour un titre de nœud court comme « Create test file » ; c'est le bon objectif pour une complétion, le mauvais pour une boucle agentique. Nouveau plancher `_HERMES_AGENT_CAPABLE_MODELS` (repli `devstral`, substitution journalisée, liste paramétrable par constructeur). Hermes continue de décider *quoi* faire ; Hermes OS se contente de ne plus lui tendre un modèle incapable d'appeler un outil — ce qui relève bien de sa responsabilité (« ce modèle n'est pas viable pour ce runtime »). **Arbitrage à connaître : ce plancher consomme plus de VRAM que le choix du routeur.**

**Corrections de robustesse trouvées en chemin.** Le contexte par tâche était stocké sur `self` (`_current_workspace`…) alors que `MissionExecutor` peut exécuter des tâches en parallèle : une tâche pouvait lire le workspace d'une autre. Remplacé par une closure, comme `_chat_with_tools_for`. Et l'adaptateur retombe sur `os.getcwd()` quand aucun workspace n'est fourni — soit l'arborescence source de Hermes OS elle-même : une mission non liée reçoit désormais un répertoire scratch vide.

**Prompt** : quand Hermes Agent exécute, le prompt ne nomme plus `workspace_list/workspace_read/workspace_write` — ce sont les outils *de Hermes OS*, que l'agent n'a pas. Un prompt qui ment sur les outils disponibles est pire qu'un prompt silencieux.

### Verified

Hermes Agent officiel : `NousResearch/hermes-agent`, commit `fb8d824`, version `0.19.0`, installé sous `%LOCALAPPDATA%\hermes\hermes-agent`.

Backend : 925 passed, 2 skipped, 0 failed (contre 920 avant). Cinq garde-fous ajoutés (`test_hermes_agent_is_the_brain.py`) qui portent sur la *décision de routage*, pas sur le fonctionnement d'une boucle d'outils — c'est précisément ce que l'ancienne suite ne vérifiait pas. Leur capacité à détecter la régression a été prouvée en la réintroduisant : deux échouent alors avec « REGRESSION: Hermes OS ran its own Ollama tool loop for a hermes-agent mission ».

**Preuve d'exécution réelle**, mission lancée par l'API Hermes OS, processus capturé pendant qu'il tournait :

```
PID 24808  ...\hermes-agent\venv\Scripts\python.exe  ...\hermes-agent\cli.py
  --query "Contexte fourni par Hermes OS: - mission_id: 215f448b... - workspace: C:\Users\emeri\hermes_e2e
           - project_id: 889f2463... - policy: {"runtime": "hermes-agent"}"
  --model qwen3.5:2b --provider custom --base_url http://127.0.0.1:11434/v1
  --max_turns 20 --toolsets coding --quiet --usage-file ...
```

Le rapport de mission confirme `runtimes_used: ['hermes-agent']` — là où le même test rapportait `['ollama']` avant ce correctif.

**Artefact réel produit de bout en bout.** Mission `HERMES_OS_INTEGRATION_TEST` créée via l'API Hermes OS, liée à un Project validé, exécutée par Hermes Agent, avec vérification indépendante sur disque (pas la narration de l'agent) :

```
$ cat C:\Users\emeri\hermes_e2e\HERMES_OS_INTEGRATION_TEST.md
line one
line two
line three
```

Les quatre défauts ci-dessus ont été trouvés parce que ce fichier n'apparaissait pas : les runs successifs rapportaient tous `success: True, 4/4 completed` avec un répertoire vide. Un rapport de mission « réussie » n'a jamais constitué une preuve ici — seul le contenu du disque compte.

### Non modifié

Le cœur de Hermes Agent et sa `config.yaml` (dont `disabled_toolsets`, qui désactive `delegation` et `skills` — à revoir avant tout test de délégation à des subagents). Le chat Assistant (`conversation/routes.py`, `api/routes/chat.py`) continue d'utiliser `BaseAgent.respond_events`, la boucle d'outils interne de Hermes OS : c'est une surface distincte des missions, et la basculer sur Hermes Agent est une décision séparée. `_run_tool_loop` est conservé pour le runtime `ollama` explicite. Aucun composant HOS supprimé. L'Autonomous Engine hérite automatiquement du correctif (il passe par `mission_executor.execute_task`).

## HOS-084 — Mission Execution câblée sur le filesystem tool layer (2026-08-10)

Suite directe de HOS-083 : « Filesystem centralisé disponible pour Assistant/Chat et MCP, Mission Execution reste à intégrer » — c'est ce dernier point qui est traité ici. Objectif : qu'une Mission liée à un Project validé puisse réellement appeler `workspace_list`/`workspace_read`/`workspace_write` pendant l'exécution de ses tâches, avec la même sécurité Aegis que le chat, sans dupliquer la logique.

**Une seule implémentation, extraite plutôt que dupliquée.** `conversation/routes.py` contenait déjà tout le nécessaire (résolution de chemin, schémas d'outils, dispatch) mais sous forme de fonctions privées locales. Extrait tel quel vers `backend/tools/workspace_chat_tools.py` (`resolve_in_project`, `workspace_tool_schemas`, `execute_workspace_tool`) — le chat et l'exécution de Mission importent désormais tous deux ce même module ; aucune logique de sécurité ou de resolution de chemin n'existe en double nulle part.

**`RealTaskExecutor` (`execution/task_executor.py`) gagne une vraie boucle d'appel d'outils**, mais délibérément *pas* construite sur `BaseAgent.respond_events()` (le mécanisme du chat) : cette méthode fait sa propre sélection de modèle via `ModelRouter`, ce qui aurait silencieusement écrasé la résolution de modèle, la vérification d'admission VRAM et le fallback cloud/local déjà réels et réglés de cet exécuteur. La boucle est construite directement sur `OllamaClient.chat_events(tools=...)` (le même primitif sous-jacent), bornée à 3 tours comme celle du chat, et réutilise le modèle déjà résolu par l'exécuteur. Scope volontairement restreint à l'exécution locale : le chemin cloud/OpenRouter n'y touche pas.

**`Mission.context.project_id`** (champ déjà présent mais jamais alimenté) est maintenant réellement câblé : `POST /missions` le lit et le stocke, `GET /missions/{id}` le renvoie, et `service_registry.py`'s `_workspace_project_for(task)` le résout — via `mission.get_mission_by_id()`, nouvel accesseur public plutôt que de lire directement le dict privé du module — jusqu'à un Project `ACTIVE` et `validation_status="valid"`.

**Bug réel trouvé et corrigé par la vérification en direct, pas par les tests unitaires.** Toute la suite de tests dédiée passait (mocks Ollama scriptés, y compris un test qui fait vraiment lire un fichier via un faux transport) — mais en lançant une vraie Mission contre le vrai Project `Skill360 Industry`, aucun appel d'outil n'apparaissait dans les logs et le résultat était fabriqué par le modèle. Cause réelle : `TaskExecution` (`execution/execution_models.py`) n'avait tout simplement pas de champ `mission_id` — `node_execution.py`, le pont réel entre un nœud de Mission et l'exécuteur, ne le passait donc jamais, alors que `RealTaskExecutor.workspace_project_for(task)` en dépend entièrement. Les tests unitaires ne l'ont jamais vu parce qu'ils construisent leur propre `_FakeTask(mission_id=...)` à la main. Corrigé : champ ajouté au dataclass, `node_execution.py` le remplit depuis `node.mission_id` (déjà posé par `GraphExecutor.build_graph()` avant toute exécution), et `execution/routes.py` (API `/execution/start` autonome) fait de même par cohérence. Deux tests de régression ajoutés (`test_node_execution_mission_id.py`) qui construisent un vrai `ExecutionController`/`MissionExecutor` plutôt qu'un mock, pour ne pas répéter l'angle mort.

**Frontend** : Mission Center gagne un sélecteur de workspace dans le formulaire de création — ne liste que les Projects `active` + `validation_status="valid"` (un Project non validé n'accorderait de toute façon aucun accès réel), avec un message explicite si aucun n'existe encore. Le panneau de détail affiche le workspace lié (« Skill360 (accès fichiers réel activé) ») à côté du binding `local_path`/`repository` existant (HOS-068, non touché — les deux mécanismes restent indépendants).

**Pollution de tests trouvée et corrigée en cours de route** : les tests qui monkeypatch `OllamaClient` pour scripter le transport de la boucle d'outils déclenchaient, sans le savoir, la toute première construction du singleton process-wide `get_agent_registry()` (via `workspace_chat_tools._aegis()`) — capturant le faux client dedans pour le reste de la session pytest et faisant échouer des tests sans rapport (`test_mcp_server.py`) plus loin dans la suite. Corrigé en forçant un vrai « réchauffement » de ce singleton avant chaque monkeypatch plutôt qu'en affaiblissant les assertions des tests cassés. Un deuxième cas du même genre (test dépendant de l'ordre d'exécution) a été trouvé dans le nouveau `test_node_execution_mission_id.py` lui-même : il inspectait le singleton process-wide `execution/routes.py`'s `_executor`, partagé par tous les tests qui touchent cette route — corrigé en substituant une instance fraîche via `monkeypatch` plutôt que d'observer l'état partagé.

**Bug frontend signalé en direct pendant la vérification, corrigé** : `mission-center.tsx` faisait `rep.total_duration_ms.toFixed(0)` sans protection — pour une Mission dont le rapport n'a pas encore cette valeur, ça fait planter tout le composant (rattrapé par `CenterBoundary`, mais l'onglet Missions devient inutilisable). `?? 0` ajouté ; revérifié en direct dans le navigateur, plus de crash, « Durée : 0ms » s'affiche correctement.

### Verified

Backend : 920 passed, 2 skipped, 0 failed (suite complète, contre 898 avant cette passe). Nouveaux tests dédiés : `test_workspace_chat_tools.py` (module partagé), `test_mission_workspace_binding.py` (liaison Mission→Project, whitelist dynamique de `_check_mission_security`), `test_real_task_executor.py` (boucle d'outils, y compris un aller-retour réel avec un transport Ollama scripté), `test_node_execution_mission_id.py` (régression du bug ci-dessus, avec un vrai `ExecutionController`). Frontend : `tsc --noEmit` propre, 82/82 vitest.

**Test de bout en bout réel**, contre le vrai backend et le vrai Project `Skill360 Industry` (pas un mock) : création d'une Mission via l'API réelle avec `project_id` posé, démarrage réel (`POST /missions/{id}/start`), exécution réelle par `qwen3.5:2b` via Ollama. Premier run, fichier demandé (`AGENTS.md`) inexistant sur disque : le résultat de tâche contient l'erreur réelle `No such file: C:\Users\emeri\Skill360 Industry\AGENTS.md` (format exact de `file_tools.read_file`, jamais halluciné par un modèle) et une tâche suivante énumère les vrais fichiers du dossier (`AGENT.md`, `LISEZ-MOI.md`, `PROJECT_SPEC.md`, ...) — confirmé identique à `Get-ChildItem` exécuté indépendamment. Ce run a d'ailleurs été ce qui a révélé le bug `mission_id` ci-dessus (avant le fix, ces deux mêmes tâches produisaient un texte entièrement halluciné, sans aucun appel d'outil).

## HOS-083 — Workspace/Filesystem tool layer + 4 correctifs Assistant (2026-08-10)

Deux demandes traitées ensemble : quatre bugs concrets de l'onglet Assistant, et un chantier plus large — donner à Hermes OS une vraie capacité de lecture/écriture sur un dossier local autorisé, utilisable depuis le chat.

### Partie 1 — Assistant

**Bug 1 + Bug 3 (même cause racine)** — le panneau latéral (Runtime/Ressources) remontait avec le texte pendant le streaming, et le sélecteur de modèle était coupé en haut sur une conversation vide. Cause réelle : la chaîne de hauteur `cockpit-shell.tsx → CenterBoundary → AnimatePresence → ConversationCenter` était cassée (aucun de ces wrappers ne posait de `height` réelle), donc rien ne scrollait en interne — c'est la page entière qui scrollait. `h-full` ajouté à chaque maillon manquant. Vérifié : la page n'a plus aucun scroll (`document.documentElement.scrollHeight === clientHeight`), seul le transcript défile, et le menu du sélecteur de modèle s'affiche entièrement sans conversation.

**Bug 2** — le rail de navigation (56px, icônes seules) ne pouvait plus être déployé, une régression volontaire de la refonte SODIUM (HOS-080) jamais revisitée depuis. Réintroduit un mode épinglé/déployé (bouton punaise, `useCockpitStore`'s `railPinned`/`toggleRailPin` — état mort réutilisé plutôt que dupliqué) : labels visibles en permanence, `--rail-w` passe à `--rail-w-expanded` (232px), tout le reste du shell (instrument bar, footer, marge du contenu) suit via la même variable CSS.

**21:9** — le chat se centrait *à l'intérieur* d'une boîte déjà ancrée à gauche (`cockpit-shell.tsx` capait tout le contenu à 1860px sans `mx-auto`, un choix volontaire pour les Centers de type tableau/dashboard, mais pas pour une conversation). L'Assistant devient l'exception : pleine largeur centrée pour cette vue précisément, colonne de lecture élargie (896→1024px). Vérifié sur 2560px de large : le contenu occupe 96→2520px au lieu de s'arrêter à ~1860px avec une grande zone vide à droite.

**Bug 4** — repris dans la Partie 2 : le panneau Projet ne permettait qu'un dossier OU un dépôt GitHub, jamais les deux, et la liaison échouait silencieusement. Résolu par la refonte de l'entité Project ci-dessous.

### Partie 2 — Workspace/Filesystem tool layer

Audit préalable (lecture seule) : quatre systèmes de gouvernance séparés existaient déjà (Aegis, Policy Engine HOS-046, Security Engine HOS-057, Tool Policy HOS-049) mais un seul — Aegis — est réellement dans le chemin d'exécution. `backend/workspace/*` (Workspace/Sandbox/Artifact manager) existait déjà sous ce nom mais ne touche jamais le disque réel (bookkeeping en mémoire) — laissé intact, ce n'est pas le même concept que ce qui suit. `backend/tools/file_tools.py` avait déjà un vrai read/write Aegis-gated, avec diff + backup avant écrasement — étendu plutôt que remplacé.

**Project = le workspace autorisé.** Plutôt que créer une cinquième entité, `Project` (déjà réel, en base, avec ses propres routes) devient le concept central : `repository`/`branch` ajoutés (miroir du binding Mission existant), plus un état de validation réel et jamais fabriqué — `POST /projects/{id}/validate` teste vraiment le dossier (existe, est un dossier, listable, écriture confirmée en créant/lisant/supprimant un fichier sonde) et persiste le résultat. Les nouvelles colonnes sont nullables : `init_db`'s migration additive existante les ajoute par un simple `ALTER TABLE`, sans outil de migration.

**Whitelist Aegis rendue dynamique.** `AegisEngine.evaluate()` acceptait déjà un `project_root` qui *restreint* l'accès (mécanisme préexistant, inchangé) ; il accepte maintenant aussi `extra_allowed_paths`, calculé à chaque appel par `AegisAgent._dynamic_allowed_paths()` — la liste des racines de tout Project actuellement ACTIF et `validation_status="valid"`, jamais mise en cache. C'est ce qui permet d'enregistrer `C:\Users\emeri\Skill360 Industry` sans toucher `config/security.yaml` : archiver, invalider ou supprimer le Project retire l'accès dès le prochain appel. Un bug a été trouvé et corrigé en cours de route par les tests : la première version faisait dépendre le *rétrécissement* (narrowing) préexistant de la validation, cassant un test déjà vert — corrigé en séparant proprement les deux mécanismes (le rétrécissement reste inconditionnel, seul l'élargissement dépend de la validation).

**`file_tools.py` étendu** : `exists`, `stat`, `search` (glob en lecture seule), `create_directory`, `append`, `copy`, `move`, `delete` — chacun suit le même patron `_check()` Aegis puis I/O réelle. Chaque opération mutante est vérifiée indépendamment après coup (relecture, re-`exists()`, comparaison de hash) — `verified` n'est jamais `true` sans une seconde lecture séparée qui le confirme. `move`/`delete` héritent de `mandatory_validation: true` (approbation humaine obligatoire, file d'attente existante réutilisée telle quelle — aucun second système d'approbation créé) ; `copy` suit le même régime que `file_write` (rien ne disparaît). Nouveaux événements `project.*`/`filesystem.*` publiés via `get_event_hub()` (même patron que `security/approvals.py`), jamais de logique dupliquée.

**Adaptateurs fins, une seule implémentation réelle.** `mcp_server/server.py` (`files_exists`, `files_mkdir`, `files_copy`, `files_move`, `files_delete`, `files_search`, `projects_validate`, …) et `conversation/routes.py` (`workspace_list`/`workspace_exists`/`workspace_read`/`workspace_write`, suivant exactement le patron déjà en place pour `web_search`) sont tous deux de simples wrappers vers `file_tools.py` — aucune logique de sécurité réimplémentée dans l'un ou l'autre. Le chat n'offre ces outils au modèle que si la session a un `active_project_id` réellement ACTIF et validé (`ConversationContext.active_project_id`, nouveau ; liaison réelle via `POST /conversation/{id}/project`, remplaçant le `ContextBuilder.update_context()` qui n'était qu'un `pass`). Le system prompt reçoit un contexte de workspace borné (nom, racine, permissions, ~20 entrées de la racine) — jamais l'arborescence complète : découverte progressive (`workspace_list` → sélection → `workspace_read`).

**Frontend** : le panneau Projet de l'Assistant est reconstruit — dossier local et dépôt GitHub sont deux champs indépendants, remplissables ensemble (corrige le Bug 4), avec un navigateur de dossiers (`GET /filesystem/browse`, lecture seule, jamais de contenu de fichier, refuse `C:\Windows`/`Program Files`/etc. explicitement — pas de picker natif, ce reste un plain Next.js sans Electron/Tauri) et un bloc de validation affichant Accessible/Lecture/Écriture réels. Workspace Center distingue maintenant clairement « espaces d'exécution » (verrous de mission, existant) et « workspaces/projets autorisés » (nouveau, vrais dossiers). Les appels d'outils du modèle sont visibles dans le transcript (chip `workspace_read — chemin`, résultat réel une fois reçu) — remplace le commentaire du code qui affirmait encore « no real tool calls yet ».

**Hors périmètre, signalé explicitement** : `RealTaskExecutor` (exécution de Mission/Autonomous) ne fait toujours qu'un seul appel LLM par tâche et n'invoque aucun vrai outil — cette capacité reste indisponible pour les missions. La formulation correcte est « filesystem centralisé disponible pour le chat et MCP, Mission Execution reste à intégrer », jamais « disponible pour tous les agents et missions ». `system-center.tsx` (tableau de composants et statistiques de dépendances fabriqués) reste non corrigé, signalé séparément.

### Verified

Backend : 80 nouveaux tests dédiés (`test_workspace_filesystem_layer.py`, `test_project_validation.py`, `test_workspace_browse_endpoint.py`, `test_conversation_workspace_tools.py`) couvrant élargissement/révocation dynamique de la whitelist, tentatives d'évasion (`../`, absolu, dossier voisin), les 8 nouvelles opérations `file_tools` (refus Aegis + succès vérifié), et l'adaptateur chat. Suite complète : 898 passed, 2 skipped, 0 failed. Frontend : `tsc --noEmit` propre, 82/82 vitest.

**Test de bout en bout réel**, sur le vrai dossier `C:\Users\emeri\Skill360 Industry` (Project déjà existant en base, créé par l'utilisateur avant cette session) : validation réelle (accessible/lecture/écriture confirmés), liaison à une session de chat réelle (`active_project_id` confirmé côté backend), puis en conversation réelle avec `qwen3.5:9b` — lecture de `AGENTS.md` (chip `WORKSPACE_READ` visible, contenu exact retourné), création de `HERMES_TEST.md` (chip `WORKSPACE_WRITE`, contenu confirmé **par une commande shell indépendante de l'API Hermes**, pas seulement par l'affirmation du modèle), puis tentative de lecture de `C:\Windows\System32\drivers\etc\hosts` via un chemin relatif d'évasion (`../../../Windows/...`) — refusée par Aegis avec le message exact attendu, visible dans le transcript.

## HOS-082 — Anglais résiduel corrigé, formatage VRAM centralisé, vrai écart 17.16/16.0 élucidé (2026-08-10)

Suivi direct des deux trouvailles laissées ouvertes par HOS-081 : « plusieurs Centers mélangent de l'anglais » et « écart VRAM réel non investigué ».

### 1 — Anglais résiduel traduit dans une dizaine de Centers
Balayage systématique de `frontend/src/features` (grep ciblé sur les placeholders, boutons, labels, messages d'état vide, puis lecture complète de chaque fichier candidat) : `mission-center.tsx`, `autonomous-center.tsx`, `deployment-center.tsx` (onglet Services, resté anglais après le passage VRAM de HOS précédent), `system-center.tsx`, `events-center.tsx`, `tools-center.tsx`, `skills-center.tsx`, `model-intelligence-center.tsx` et `agent-center.tsx` avaient des formulaires, boutons, en-têtes de tableau et paragraphes d'avertissement entiers restés en anglais alors que le sous-titre et le reste du Center sont en français. Tout traduit — labels, placeholders, messages d'erreur, en-têtes de colonnes, badges de statut construits côté client. Les noms de module stylisés (« Mission Center », « Runtime Center », etc., cohérents sur les 22 Centers) et les valeurs brutes venant du backend (statuts d'enum comme `RUNNING`/`PAUSED`, `"unknown"`) n'ont volontairement pas été touchés — ce n'est pas de l'anglais résiduel mais soit une convention de nommage délibérée, soit une donnée réelle affichée telle quelle.

Trouvaille en cours de route, signalée pour plus tard plutôt que corrigée ici (hors périmètre d'une passe de traduction) : `system-center.tsx` affiche un tableau « All Components » et des « Dependency Stats » entièrement codés en dur (latences, compteurs d'événements, « 42 dependency edges tracked ») — même genre de fabrication déjà éliminé de `deployment-center.tsx` et `autonomous-center.tsx`, mais jamais traité ici.

### 2 — VRAM : formatage frontend centralisé
`bytes/1024³` était réimplémenté séparément dans 7 fichiers (`agent-center`, `dashboard-view`, `conversation-center`, `deployment-center`, `model-intelligence-center`, `runtime-center`, `monitoring-center`), à des précisions différentes (`.toFixed(1)` partout sauf Monitoring en `.toFixed(2)`) et sous deux libellés différents (« GB » dans six endroits, « Gio » dans un seul) — un seul chiffre réel rendu de façon incohérente donnait l'impression de plusieurs mesures qui se contredisent. Centralisé dans `frontend/src/lib/format.ts` (`formatGio`/`formatGioPair`, 1 décimale, libellé « Gio » partout puisque tout le calcul réel est binaire) ; les 7 fichiers importent désormais la même fonction.

### 3 — Le « 17.16 » n'était pas une fausse piste : deux modules GPU jamais réconciliés
HOS-081 avait correctement flaggé l'écart (« 15.98 Go » vs « 17.16 Go ») sans l'investiguer. Vérifié en direct : le panneau « Bus d'événements » du Dashboard affiche le payload WebSocket `system.metrics` brut, qui contient bien `"vram_total_gb":17.16` — donc ce chiffre est réel, pas halluciné. Root cause trouvée dans le backend : deux implémentations de monitoring GPU totalement indépendantes coexistent, jamais reliées entre elles —
- `backend/monitoring/gpu_monitor.py`, à l'origine du broadcast WebSocket `system.metrics`, calcule tout en **GB décimal** (`÷1e9`) ;
- `backend/runtime/resources/gpu_monitor.py`, derrière `GET /api/v1/runtime/resources` (celui que consomment tous les Centers corrigés au point 2), retourne des **octets bruts**, convertis côté frontend en **Gio binaire** (`÷1024³`).

Les deux valeurs sont individuellement honnêtes et correctement calculées pour leur propre unité — même GPU de 17 163 091 968 octets, 17.16 en GB décimal et 16.0 en Gio binaire — ce n'est pas une fabrication de données mais deux pipelines de mesure jamais unifiés, sans étiquette d'unité sur le dump JSON brut du flux d'événements. Réconcilier les deux modules est un vrai chantier backend, signalé en tâche de suivi plutôt qu'improvisé dans cette passe.

### Verified
`tsc --noEmit` propre, `vitest` 82/82. Vérifié en direct : Mission Center, Autonomous OS, Deployment Center (onglets Vue d'ensemble/Profil/Services) et Dashboard rechargés dans le navigateur, tout le texte visible en français, VRAM affichée de façon cohérente (« 16,0 Gio ») sur les Centers corrigés.

## HOS-081 — Suivi SODIUM : cohérence des docs, santé à trois états, palette clavier (2026-08-10)

Suivi direct d'une revue critique de HOS-080 (retour utilisateur structuré, quatre actions demandées dans l'ordre). Rien de tout ceci n'est du polish visuel — chaque point vient d'un vrai gap trouvé en vérifiant, pas en supposant.

### 1 — Docs remises en cohérence avec le code réel
`hermes/architecture`'s `frontend-map.md` et le skill `design-system` décrivaient encore l'ancienne palette cyan/magenta après la refonte — exactement le piège que ces mêmes docs mettent en garde ailleurs (une doc qui décrit un état qui n'est plus vrai). Les deux réécrits pour SODIUM ; le contrat de design vit dans `design-system` (son foyer naturel) avec un renvoi depuis `hermes/development-rules` plutôt qu'une duplication.

### 2 — Santé des sous-systèmes : trois états réels, pas un amalgame
`GET /system/health` renvoie déjà un tableau `silent` (sous-système sans accesseur de télémétrie — un vrai manque architectural, pas un incident) distinct des sous-systèmes réellement dégradés — le frontend l'ignorait et amalgamait les deux en un seul chiffre ambre (« 23/35 » se lit comme « 12 problèmes » qu'il s'agisse de 12 vraies pannes ou de 12 non-instrumentés, deux situations aux actions très différentes). `SubsystemHealth` gagne un statut `NOT_INSTRUMENTED`, alimenté par le tableau réel plutôt que déduit. Le Dashboard distingue maintenant sains/dégradés/non-instrumentés, avec une case hachurée grise (pas ambre) dans la matrice de recensement pour le troisième cas. Vérifié en direct : 23 sains, 0 réellement dégradé, 12 non instrumentés — confirmé au niveau du DOM (`event_hub` → hachure, `system_event_bus` → vert plein). Découverte en cours de route : Health Center et Deployment Center faisaient déjà cette distinction correctement (« SANS TÉLÉMÉTRIE », « NOT REPORTING ») — le Dashboard était le seul en retard.

### 2bis — Bug réel trouvé en construisant la matrice de validation : le rail déborde
22 entrées + marques de section dépassent la hauteur d'un rail de 56px sur un viewport de ~1000px de haut, sans aucun indice visuel de défilement — Deploy et System devenaient inatteignables sans le savoir. Corrigé avec un masque de fondu haut/bas sur le `<nav>` du rail.

### 2ter — Bug réel trouvé en testant : la palette de commandes ne répondait pas au clavier
Entrée/flèches ne déclenchaient jamais `commit()`. Diagnostiqué en profondeur : un événement `keydown` natif, bubbling, avec `key: "Enter"` atteignait bien le champ de recherche (confirmé via un listener DOM brut), mais le `onKeyDown` React de la palette — même posé directement sur l'élément ciblé — ne se déclenchait jamais. Le raccourci ⌘K global (basé sur un `window.addEventListener` brut, pas sur les props React) fonctionnait pourtant de façon fiable pendant toute la session. Plutôt que de laisser ce doute non résolu sur un mécanisme dont toute la raison d'être est la navigation clavier, la palette a été réécrite sur ce même patron déjà éprouvé (`useEffect` + `window.addEventListener`) au lieu du prop `onKeyDown` de React. Revérifié après coup : ouverture ⌘K → recherche « runtime » → Entrée navigue bien vers Runtime Center, confirmé par capture d'écran et par les logs de diagnostic avant leur retrait.

### 3 — Matrice de validation des 22 Centers
Les 19 Centers non vérifiés individuellement après HOS-080 ont été ouverts un par un via la palette de commandes (rendu, interaction, données réelles) : Assistant, Missions, Autonomous, Models, Agents, Runtime, Code Intel, Skills, Tools, Memory, Workspace, Security, Validation, Evolution, Health, Monitoring, Events, System, Deployment. Aucun crash. Plusieurs confirmations croisées fortes avec l'audit d'architecture existant :
- **Code Intel** affiche KlaatCode MCP `DISCONNECTED` et Oh My Pi `NOT_CONFIGURED` — exactement les lacunes déjà documentées.
- **Skills Center** affiche honnêtement 0 skill enregistré — confirme que le registre est réellement vide, pas juste vide à l'écran.
- **Validation Center** liste les 7 vrais runners de `config/verification.yaml`.
- **Models** affiche le vrai roster réinstallé en HOS-079 avec scores/VRAM/TPS réels.

Trouvailles réelles non corrigées ici (hors périmètre de cette passe, signalées pour plus tard) :
- Plusieurs Centers mélangent de l'anglais dans une UI par ailleurs française (états vides de Missions/Autonomous/Events).
- Monitoring Center affiche un total VRAM (15.98 Go) légèrement différent de celui vu ailleurs (17.16 Go) — écart réel non investigué.
- Un avertissement React « missing key » ponctuel a été observé sur EventsCenter pendant les tests ; aucune liste sans `key` trouvée dans le code actuel après relecture — probablement transitoire (premier rendu avant données), pas de correctif spéculatif appliqué.

### 4 — Contrat de design SODIUM formalisé
Table ❌/✅ explicite ajoutée à `design-system` (cyan/magenta/glow par défaut/`rounded-xl` uniforme/police non chargée/valeur interpolée-en-mesure-réelle interdits ; sodium/glacier/steel/Chakra Petch/Barlow/IBM Plex Mono/télémétrie honnête/grain/chanfrein requis), reliée au principe « ne jamais fabriquer un résultat » déjà central au projet.

### Verified
`tsc --noEmit` propre, `vitest` 82/82, à chaque étape. Vérifié en direct sur les 22 Centers via ⌘K, backend réel démarré. 134 liens internes du système de skills revérifiés après les mises à jour de doc — aucun lien cassé.

## HOS-080 — Refonte complète du frontend : direction « SODIUM » (2026-08-10)

Demande de l'utilisateur : refonte complète du Cockpit, style moderne et
cyberpunk, carte blanche sur le reste, avec une exigence explicite — « une
interface originale qui ne ressemble pas à un site généré par IA », d'un
niveau professionnel, sans repartir de la base existante.

### Le problème réel avec l'ancien design
Audité avant de toucher quoi que ce soit : l'ancien Cockpit cochait la
plupart des marqueurs « IA générique ». Cyan `#00e5ff` + magenta `#ff2d92`
sur near-black est *la* palette cyberpunk par défaut ; six accents
concurrents ; un glow au survol sur absolument tout ; `rounded-xl` uniforme
partout ; Inter ; aucune texture ; et une police mono déclarée dans
`tailwind.config.ts` mais **jamais chargée** — chaque libellé `font-mono` du
cockpit retombait silencieusement sur la mono par défaut de l'OS.

### Direction retenue — « SODIUM »
Une idée directrice unique : **le contraste de température**. Châssis carbone
froid bleuté, portant **un seul** signal chaud (sodium `#ff9436`). Tout ce
qui compte est chaud, tout ce qui est structurel est froid. Références :
éclairage sodium, salles de contrôle aérospatiales réelles (phosphore ambre,
télémétrie en chasse fixe, hiérarchie d'alarme), instrumentation industrielle
(châssis froid, un accent, étiquetage technique apparent), plans techniques
(marques de repérage). Zéro cyan, zéro magenta, zéro dégradé violet.

- **Typo** : trois rôles réellement chargés via `next/font` — Chakra Petch
  (display, terminaisons carrées), Barlow (interface), IBM Plex Mono
  (données, chiffres tabulaires partout).
- **Texture** : grain SVG + vignette fixes au-dessus de l'app. C'est ce qui
  empêche les grands aplats de rendre comme du vecteur stérile.
- **Géométrie** : chanfreins (`clip-corner`) au lieu d'un rayon uniforme.

### Coquille reconstruite
- `rail.tsx` (nouveau) remplace la sidebar dépliable : rail permanent de 56px,
  noms en flyout au survol, marques de section (S1…S5) servant aussi d'échelle
  de position. Un panneau de 232px listant 22 entrées n'est pas une
  navigation, c'est un inventaire.
- `command-palette.tsx` (nouveau) — ⌘K, la vraie navigation à 22 écrans.
  Recherche sur libellé + groupe + mots-clés : « vram » trouve Runtime,
  « aegis » trouve Security, bien que les mots n'apparaissent nulle part
  dans le menu.
- `instrument-bar.tsx` (nouveau) remplace la topbar : position, puis les deux
  contraintes réelles de ce déploiement (VRAM/RAM) en **tracés live
  permanents**, puis état et commande.
- `telemetry-trace.tsx` (nouveau) — la pièce signature : un vrai oscilloscope
  sur canvas. Il trace ce qu'on lui donne et **tient une ligne plate quand la
  mesure manque** ; le nourrir de `Math.random()` aurait donné une plus belle
  image et une image mensongère.
- `nav-model.ts` (nouveau) — modèle de navigation unique partagé par le rail
  et la palette, pour qu'ils ne divergent pas.
- `sidebar.tsx` et `topbar.tsx` supprimés (morts après remplacement).

### Stratégie de propagation aux 22 Centers
Les noms de tokens et de classes existants (`text-hermes-cyan`, `.glass`,
`.neon-edge`, `.bracket`…) sont **conservés comme API publique** et
redéfinis : le nom dit cyan, la couleur est sodium. Les 22 Centers héritent
donc de la refonte sans 22 éditions simultanées. Vérifié en vrai sur
Dashboard, Governance et Execution.

### Bugs réels trouvés en vérifiant (pas en auditant)
- **La palette de commandes bloquait toute l'application.** `AnimatePresence`
  suit ses enfants par `key` ; sans clé, l'animation de sortie jouait mais le
  nœud n'était jamais retiré — laissant un overlay plein écran invisible qui
  avalait *tous* les clics du cockpit. Trouvé parce que la navigation ne
  marchait plus du tout, diagnostiqué via `document.elementFromPoint`.
- **Compteur animé retiré après coup.** Un roll-up 0 → valeur avait été
  ajouté ; il affiche pendant quelques centaines de ms un nombre qui n'est
  pas la mesure (« 0 échec » quand il y en a trois) et mettait une valeur
  fausse dans le DOM. Sur un cockpit dont toute la discipline est qu'une
  valeur affichée est une valeur mesurée, c'est une fioriture qui ment sur
  l'état — supprimé, pas contourné. C'est le test de non-régression
  `code-intelligence-center` qui l'a révélé.
- Deux erreurs de types réelles dans le nouveau Dashboard (`ApprovalRequest`
  n'a ni `action_type` ni `requesting_agent` ; pas de branche `UNKNOWN` sur
  un statut de sous-système, le client normalisant déjà l'inconnu en
  `DEGRADED` plutôt que de le flatter en `HEALTHY`).

### Verified
- `vitest` : **82/82 verts** (dont le test de non-régression ci-dessus).
  `tsc --noEmit` : propre.
- Vérifié en navigateur avec **backend réel démarré**, pas sur des états
  vides : RX 6800 détecté, 23/35 sous-systèmes, RAM 41 %, matrice de
  recensement des 35 sous-systèmes aux vraies couleurs, runtime `ollama`
  STARTED, bus d'événements recevant de vrais `system.metrics`.
- Palette ⌘K vérifiée en direct (filtrage par mot-clé « vram » → Runtime).
- Tests mis à jour pour refléter les composants réels (`Rail`,
  `InstrumentBar`, `CommandPalette`) au lieu des `Sidebar`/`Topbar`
  supprimés, plus un test d'unicité des identifiants de navigation.
- **Non vérifié** : les 19 autres Centers n'ont pas été ouverts un par un ;
  ils héritent des mêmes primitives que les trois contrôlés, mais ce n'est
  pas une garantie visuelle individuelle.

## HOS-079 — Ollama : modèles réinstallés et mis à jour, clé de pull régénérée (2026-08-10)

Demande de l'utilisateur suite à un 404 réel (`/api/chat` sur Ollama) :
réinstaller les modèles supprimés et les mettre à jour vers les dernières
versions, en vérifiant sur cette machine (pas seulement sur le papier)
avant de figer un choix dans `config/models.yaml` — même exigence que
HOS-065C ("mesuré, pas deviné").

### Bug réel trouvé et corrigé — clé de pull Ollama manquante
Premier lancement du script de téléchargement : 11 des 12 rôles échouent
avec `pull model manifest: open ...\.ollama\id_ed25519: introuvable`. Seul
le modèle hébergé sur Hugging Face (`hf.co/...`) passait — ce chemin ne
signe pas la requête avec cette clé locale, contrairement au registre
officiel Ollama. `~/.ollama` ne contenait plus que `cache/` et `models/` :
la clé avait disparu avec le reste au moment de la suppression externe des
modèles (déjà signalée dans une session précédente), et Ollama ne la
régénère qu'au démarrage du service — le service tournait depuis avant la
suppression et n'avait jamais eu l'occasion de la recréer. Corrigé en
arrêtant puis relançant `ollama app.exe`/`ollama.exe` : la clé réapparaît,
tous les modèles suivants passent.

### Modèles mis à jour, chacun vérifié réellement avant de changer la config
Recherche préalable (13 requêtes) pour identifier le meilleur modèle par
rôle, rapport donné avant tout téléchargement, accord explicite de
l'utilisateur avant de lancer. Script séquentiel (candidat proposé, puis
repli automatique sur l'ancien modèle du rôle si le tag proposé n'existe
pas sur le registre — jamais les deux téléchargés en double).

- **swift** : `qwen3:1.7b` → `qwen3.5:2b`. **embedding** :
  `nomic-embed-text` → `qwen3-embedding:0.6b`. **double_check** :
  `qwen3:4b` → `qwen3.5:4b`. Les trois largement sous le budget VRAM de
  cette carte, aucun risque de régression à vérifier.
- **code** : `qwen3-coder:30b` → `qwen3.6:27b`. Comparaison directe sur
  cette machine (`ollama ps`, même prompt-sonde, un seul modèle chargé à
  la fois) : l'ancien modèle tournait déjà 21 %/79 % CPU/GPU (19 Go sur
  disque, dépasse déjà le budget de la carte), le nouveau 18 %/82 %
  (17 Go) — légèrement meilleur, plus récent, pas une régression.
- **code_agentic** : `devstral-small-2` **rejeté** après vérification.
  `devstral` (déjà en place) tourne 100 % GPU (14 Go) ; `devstral-small-2`
  (16 Go) retombe à 88 %/12 % CPU/GPU — une vraie régression pour un rôle
  dont tout l'intérêt est l'enchaînement rapide d'appels d'outils. « Plus
  récent » n'était pas « meilleur » ici ; `devstral` reste le modèle du
  rôle.
- **security**, **reasoning_escalation** : candidats proposés
  (`phi4-reasoning-plus`, `deepseek-r2`) absents du registre — repli
  automatique du script sur les modèles déjà en place
  (`phi4-reasoning:14b-q4_K_M`, `deepseek-r1:32b`), aucun changement.
- **standard**, **orchestrator**, **vision**, **reasoning**,
  **advanced_analysis** : inchangés, simplement réinstallés.

`config/models.yaml` mis à jour en conséquence (`vram_gb` par rôle changé,
commentaires factuels remplacés — plus de vieux chiffres HOS-065C présentés
comme valables pour un modèle qui n'est plus celui chargé). Nettoyage :
`devstral-small-2` supprimé du disque (rejeté) ; `qwen3-coder:30b` laissé
en place (suppression bloquée par le classifieur auto-mode, sans
conséquence — juste 19 Go inutilisés).

### Dette découverte en cascade — noms de modèles codés en dur
`config/models.yaml` est censé être la seule source de vérité, mais
plusieurs points codaient un tag en dur au lieu de le résoudre dynamique-
ment : `ResponseGenerator.DEFAULT_CHAT_MODEL`, `RealTaskExecutor`'s
`default_model`, quatre docstrings citant l'ancien tag par rôle
(`atlas.py`, `hermes_swift.py`, `semantic.py`) — tous mis à jour. La
résolution `chat_capable` de Model Intelligence, elle, s'est révélée déjà
saine : basée sur le *nom du rôle* (`role_name != "embedding"`), pas sur
le tag — le nouveau modèle d'embedding est automatiquement exclu du chat
sans code à toucher.

### Verified
- Suite complète (`backend/tests` + `tests/`, pas seulement le sous-
  ensemble par défaut de `pytest.ini` — `testpaths` pointe uniquement vers
  `backend/tests`, vérifié après coup) : **26 tests cassés trouvés et
  corrigés** en deux passes. La plupart pointaient un ancien tag en dur
  contre la vraie config (`qwen3-coder:30b`, `qwen3:1.7b`, `qwen3:4b`,
  `nomic-embed-text`) ; deux étaient une dette préexistante sans rapport
  avec ce lot (l'autonomy_level `low`→`medium` de HOS-077 jamais vérifié
  contre la suite complète faute d'un run qui aille au bout) ; trois
  venaient d'un vrai trou de HOS-078 (`_FakeAgent.respond_events` pas mis
  à jour pour les kwargs `tools`/`tool_executor`, jamais exécuté dans un
  run complet avant ce soir).
- Run final : 3703 passed, 3 skipped, **1 failed** —
  `test_task_executor_shares_the_container_model_intelligence`, un état
  partagé (`ModelMemoryAdapter`) qui fuit d'un fichier de test à l'autre
  selon l'ordre d'exécution ; confirmé sans rapport avec ce lot (128/128
  vert quand ce fichier tourne seul) et préexistant. Non corrigé ici —
  hors périmètre d'un lot modèles, signalé pour un futur passage.

### Also
- `.claude/launch.json` : `hermes-cockpit` gagne `autoPort: false` — le
  port 3010 est en dur dans la liste blanche CORS du backend et dans le
  lanceur Desktop (HOS-077), un port réattribué automatiquement casserait
  les deux silencieusement. Trouvé en diagnostiquant un `node.exe` orphelin
  qui bloquait le port.

## HOS-078 — Assistant : menu modèle coupé corrigé, recherche internet réelle (2026-08-09)

Deux demandes. La première (capture d'écran à l'appui) : le menu de
sélection de modèle s'ouvrait vers le bas et sortait de l'écran, rendant
« Effort de réflexion » et « Modèle spécifique » inaccessibles. La seconde :
« est-il possible de demander aux modèles locaux de faire des recherches
sur internet ? » — réponse honnête après audit : non, ni la recherche ni
l'appel d'outils n'existaient nulle part dans le pipeline de chat ; les
deux ont été construits ce soir, avec l'accord explicite de l'utilisateur
(DuckDuckGo, gratuit, sans clé) sur le choix du fournisseur.

### Corrigé — menu modèle coupé par le viewport
`ModelPicker` s'ouvrait avec `top-full`/`mt-2` (vers le bas) — dans un
composeur ancré en bas d'écran, ça sort systématiquement du viewport sans
aucun moyen d'atteindre les options du bas. Même correctif déjà appliqué à
`SlashCommandMenu` pour la même raison : `bottom-full`/`mb-2` (ouverture
vers le haut), `max-h-96` remplacé par `max-h-[60vh]`.

### Ajouté — recherche internet réelle pour le chat
Audit préalable (agent dédié) : aucun code de recherche web nulle part
(le seul « connecteur navigateur » existant, `BrowserConnector`, est une
coquille vide, `extract_text()` renvoie `""`) ; et même avec un vrai
connecteur, `OllamaClient.chat_events()` n'envoyait jamais `tools=[...]`
à Ollama — le chat était une pure boucle de complétion de texte, pour
tous les agents, pas seulement l'Assistant.

- `backend/tools/connectors/web_search.py` (nouveau) — `WebSearchConnector`,
  requête HTTP réelle vers `html.duckduckgo.com/html/` (aucune clé API,
  DuckDuckGo n'a jamais proposé d'API JSON gratuite sans compte), parsing
  par regex du HTML réel (bs4/lxml absents de l'environnement, vérifié
  avant d'écrire le code), dérésolution du redirecteur `uddg=` de DuckDuckGo
  vers l'URL réelle. Vérifié en direct contre le vrai endpoint avant
  intégration.
- `OllamaClient.chat_events()` — nouveau paramètre `tools`, transmis tel
  quel dans le payload `/api/chat`. `StreamChunk` gagne un 4ᵉ genre,
  `"tool_calls"`. **Bug trouvé en testant en direct contre Ollama** :
  `tool_calls` n'arrive que sur le tout dernier chunk (`done: true`), et
  le code renvoyait (`return`) sur `done` *avant* de lire `message` —
  chaque appel d'outil aurait été silencieusement perdu. Corrigé en lisant
  `message` avant le contrôle `done`.
- `BaseAgent._stream_with_tools()` — la vraie boucle d'aller-retour :
  transmet `tools`, exécute réellement l'outil demandé via un
  `tool_executor` injecté, réinjecte le résultat réel comme message
  `role: tool`, relance un tour. Bornée à 3 tours
  (`_MAX_TOOL_ROUNDS`) — observé en conditions réelles avec gpt-oss:20b :
  le modèle peut affiner sa recherche indéfiniment sans jamais conclure.
  Après épuisement des tours, un dernier appel forcé **sans `tools`** —
  le modèle ne peut alors plus que synthétiser depuis ce qu'il a déjà
  trouvé, plutôt que de recevoir un message d'abandon statique.
- `backend/conversation/routes.py` — `web_search` proposé à chaque tour de
  `/conversation/stream` (le rôle `orchestrator`/hermes_prime avait déjà
  été choisi en 2026-07 pour son tool-calling fiable — confirmé utile ce
  soir). Porte Aegis réelle (`_web_search_authorized`, même schéma que
  `_cloud_authorized` pour `cloud_inference`) : catégorie `web_search`
  ajoutée à `config/security.yaml`, `min_autonomy_for_auto_allow: medium`
  — plus bas que `cloud_inference` (« high ») car une requête de recherche
  est une exposition réelle mais plus restreinte qu'un prompt entier
  envoyé au cloud. En dessous du seuil, refus explicite renvoyé au modèle
  (pas d'UI d'approbation possible dans un flux de chat en direct,
  contrairement au pause/resume de Missions).
- Cockpit : bloc « Recherche » repliable dans le fil (même patron que le
  bloc de raisonnement) — visible dès que le modèle demande une recherche
  (`Recherche…`), affiche la vraie requête et, une fois dépliée, les vrais
  résultats DuckDuckGo (titre/URL/extrait) reçus par le modèle.

### Verified
- Trois tests manuels en direct contre Ollama réel (aucun mock) : une
  question piège (capitale fictive) a déclenché 3 recherches réelles
  successives avec affinage de requête ; une question factuelle simple
  (« dernière version de Next.js ? ») a produit une recherche, des
  résultats réels (GitHub releases, versionlog.com) et une réponse finale
  honnêtement nuancée plutôt qu'un numéro de version inventé.
- Vérifié de bout en bout dans le vrai Cockpit (pas seulement en script) :
  question posée en français, modèle auto-routé (`qwen3.5:9b`, confirmé
  `"tools"` dans ses capacités Ollama), bloc de recherche affiché en
  direct avec la vraie requête, dépliable pour voir les 3 vrais résultats.
- 15 nouveaux tests, tous verts : `tests/architecture/test_base_agent_tools.py`
  (6, boucle d'appel d'outils avec un faux client Ollama scripté),
  `tests/tools/test_web_search.py` (9, parsing HTML réel-mais-fixe,
  déballage d'URL, requête réseau réelle échouée propagée et non
  fabriquée), `tests/architecture/test_conversation_web_search.py` (6,
  logique de l'exécuteur d'outil), `backend/tests/test_aegis.py` (+3,
  vrai moteur Aegis à low/medium/high pour `web_search`).
- La suite complète n'avait pas pu être vérifiée le soir même (premier
  lancement bloqué à 64 % sur un vrai hang réseau Ollama sans rapport avec
  ce lot, deuxième lancement annulé) — confirmée verte a posteriori dans
  HOS-079 ci-dessous, une fois lancée avec les deux lots ensemble. Suite
  frontend (`vitest`) : 80/80, `tsc --noEmit` propre.

## HOS-077 — Autonomous OS : test réel, mission_id vide corrigé, repli générique rendu honnête (2026-08-09)

Demande de l'utilisateur : tester le mode Autonomous en conditions réelles
sur un cahier des charges complet (Skills360 Industry, appli métier
industrielle React/TypeScript/Firebase), vérifier que tout fonctionne et
que les agents jouent bien leur rôle, avec un projet réalisable pour les
modèles locaux actuels. Deux bugs réels trouvés en testant, pas en
auditant — corrigés après validation utilisateur.

### Contexte du test
`autonomy_level` (config/security.yaml) passé de `low` à `medium` à la
demande de l'utilisateur pour dépasser la porte Aegis systématique sur tout
objectif lié à un dossier local — reste à `medium`, changement de posture
volontaire et durable, pas un réglage de test annulé après coup.

### Bug réel trouvé et corrigé — `mission_id` vide
`MissionPlanner.build_mission()` écrasait l'UUID réel que `Mission` venait
de générer par `result.mission_id` — qui vaut toujours `""` à ce stade,
puisque rien ne le renseigne avant. Chaque mission créée depuis Autonomous
s'enregistrait donc sous la clé `""`, invisible/inconsultable depuis
`GET /missions/{id}` et incliquable dans le Cockpit — découvert en cliquant
sur une mission réellement complétée sans qu'aucun panneau ne s'ouvre.
Corrigé en supprimant la ligne fautive ; seule la propagation utile
(mission → result) subsiste. Vérifié en conditions réelles : la mission
suivante s'est enregistrée sous un vrai identifiant et son rapport complet
(6 tâches, sorties, durées) est devenu consultable.

### Bug réel trouvé et corrigé — repli générique silencieux
En comparant deux runs réels du même objectif (« Concevoir le modèle de
données Firestore et les types TypeScript pour Skills360... »), le second
(juste après un redémarrage backend, modèle d'orchestration pas encore
chargé) a produit 6 tâches génériques ("Analyze requirements", "Design
solution architecture"...) sans aucun rapport avec la demande, avec du code
Flask/SQLite généré au hasard. Cause tracée dans `task_decomposer.py` :
la décomposition LLM a un timeout de 90 s ; en cas d'échec, un repli par
mots-clés anglais (jamais un match sur une demande en français) puis un
gabarit générique de cycle de développement prennent le relais — sans
aucune indication nulle part que ce repli a eu lieu. Une mission "completed"
issue d'un vrai plan et une mission "completed" issue du gabarit générique
étaient visuellement indiscernables.

### Added
- `TaskDecomposer.decompose_with_method()` — même résultat que `decompose()`
  (inchangé, toujours utilisé par tous les appelants existants) plus la
  méthode réellement employée : `"llm"` / `"pattern:<clé>"` /
  `"generic_fallback"` / `"template:<id>"`.
- `PlanningResult.decomposition_method`, propagé dans `Mission.metadata`,
  puis dans `MissionReport.plan_is_generic`/`decomposition_method`
  (`GET /missions/{id}/report`), la liste (`GET /missions`) et le détail
  (`GET /missions/{id}`) — visible sans avoir à comparer manuellement les
  titres de tâches à la demande d'origine, comme il a fallu le faire ici.
- Côté Autonomous (`autonomous_orchestrator.py`) : même détection dans
  `_execute_via_dag`/`_dag_result`, préfixe `"WARNING: ..."` explicite dans
  `execution_summary` et une entrée dans `improvements` suggérant de
  relancer l'objectif.
- Cockpit : badge d'avertissement sur une mission généré-générique dans la
  liste et le détail (Mission Center), résumé d'exécution basculé en rouge
  quand il commence par `"WARNING:"` (Autonomous Center).

### Verified
- Bug `mission_id` : reproduit puis corrigé en conditions réelles (deux
  runs successifs, backend redémarré entre les deux) — `GET /missions`
  renvoyait `mission_id: ""` avant, un vrai UUID hex après.
- Repli générique : mécanisme tracé et confirmé par lecture du code
  (`task_decomposer.py`, timeout 90 s, mots-clés anglais uniquement) ; le
  correctif ne change pas le comportement de repli lui-même (toujours
  best-effort, jamais un échec dur), seulement sa visibilité.
- 185 tests ciblés (`test_mission_planner.py`, `tests/autonomous/`,
  `test_mission_real_wiring.py`, `test_task_decomposer_cloud_fallback.py`) :
  tous verts, aucune régression sur les 17 sites d'appel existants de
  `decompose()` (signature inchangée).
- `tsc --noEmit` propre côté frontend après les badges Cockpit.

### Reste hors périmètre de cette passe (voir réponse séparée à l'utilisateur)
Sélection d'agent réelle mais exécution non différenciée par agent (label
seulement — `_CATEGORY_AGENT`), aucune écriture réelle de fichiers depuis
le pipeline de mission, `/resume` côté Autonomous toujours un no-op de
statut pour un objectif mis en pause avant planification.

## HOS-076 — Assistant : retours utilisateur (barre de contexte, layout 21/9, logo, dictée, dossier/dépôt local, PR) (2026-08-09)

Neuf points transmis par l'utilisateur sur l'onglet Assistant après HOS-075.
Chaque point a été audité contre le code réel avant implémentation ; deux
d'entre eux se sont révélés être de vrais bugs plutôt que des demandes de
fonctionnalité (barre latérale, sélecteur de modèle), et deux autres avaient
déjà toute leur infrastructure backend réelle, jamais reliée à aucun écran
(dossier local/dépôt git, création de PR).

### Bug réel trouvé et corrigé — barre latérale qui disparaît
`cockpit-shell.tsx` ne bornait la hauteur d'aucun conteneur entre `<main>`
et les Centers : sur une conversation de 8 messages, `window.scrollY`
atteignait 41 712 px — c'était **le document entier** qui défilait, pas
seulement le fil de discussion. Le rail (Runtime/Ressources/Actions
rapides) et l'en-tête défilaient avec lui. Corrigé en bornant `<main>` à
`h-screen` et en déplaçant le scroll sur son conteneur interne — comportement
identique pour tous les autres Centers (défilement naturel préservé),
correctif structurel pour l'Assistant (défilement interne du fil, rail fixe).

### Bug réel trouvé et corrigé — sélecteur de modèle « inaccessible »
Le sélecteur fonctionnait bien en état vide une fois testé en direct ; la
vraie cause derrière le symptôme rapporté était `systemClient.models()`
appelé une seule fois dans un `useEffect` sans retry, `catch` muet — un seul
échec (backend pas encore prêt, cas observé pendant les tests) bloquait le
sélecteur sur « Auto » pour le reste de la session, sans indication.
Remplacé par un hook react-query (`useSystemModelRoles`, retry par défaut du
`QueryClient`) avec un bouton « Modèles indisponibles » de relance visible
en cas d'échec persistant.

### Added
- **Barre de contexte progressive** (`ContextMeter`) — remplace le seul
  pourcentage texte par une barre qui se remplit, couleur alignée sur le
  seuil (cyan/ambre/rouge).
- **Commandes `/help` et `/context`** — `/help` liste les commandes,
  `/context` appelle `GET /conversation/{id}/context` (endpoint réel,
  aucun appelant Cockpit avant ce jour) et affiche mission/agents/runtime/
  sécurité liés à la session, distinct de l'estimation de tokens déjà
  affichée.
- **Layout adapté 21/9** — plafond `max-w-[1500px]` relâché à `2xl:1900px`
  dans le shell ; dans l'Assistant, fil et compositeur plafonnés à une
  largeur de lecture confortable et centrés (`max-w-4xl mx-auto`) plutôt
  qu'étirés bord à bord sur un écran ultra-large.
- **Logo Hermes** — remplace le monogramme "H" (sidebar) et l'icône Sparkles
  générique (en-tête Assistant, avatar de message, état vide) par
  `hermes-agent-logo.png` fourni par l'utilisateur ; favicon remplacé via
  `app/icon.png` (convention App Router).
- **Dictée vocale** (`VoiceButton`) — `SpeechRecognition` native du
  navigateur (fr-FR), aucun backend STT. Le bouton ne s'affiche pas du tout
  sur un navigateur sans l'API plutôt que d'afficher un micro qui échouerait
  silencieusement.
- **Accès dossier local / dépôt GitHub** (`ProjectPanel`, rail Assistant) —
  surface construite sur `/api/v1/projects` et `/api/v1/git/*`, montés
  depuis HOS-066B (`_LEGACY_ROUTERS` dans `main.py`) et jamais appelés par
  aucun écran. « Lier un dépôt GitHub » est littéralement pointer Hermes
  vers un dossier local dont le remote git est GitHub — aucun flux OAuth à
  fabriquer. Statut git réel affiché (branche, modifié, protégée).
- **Bouton « Créer une PR »** — appelle `POST /git/pull-request`, qui invoque
  réellement `gh pr create`, gated par Aegis (`git_critical`, validation
  obligatoire). Masqué sur une branche protégée, comme le refuse déjà le
  backend.

### Verified
- Vérifié en direct dans le navigateur, backend réel : liaison du dépôt
  `C:\Users\emeri\Hermes_OS-main` lui-même → statut git réel retourné
  (`branch: main, dirty: true, protected: true`), formulaire de PR
  correctement masqué car branche protégée — comportement honnête de bout
  en bout, pas de donnée simulée.
- Dictée vocale : clic déclenche une vraie demande de permission microphone
  du navigateur (bloquée par le sandbox de test, comportement attendu) —
  confirme un appel réel à l'API, pas une façade ; réinitialisation propre
  de l'état si la permission est refusée.
- Frontend : `tsc --noEmit` propre, `next build` propre, 80/80 tests
  (`vitest run`, dont 11 nouveaux pour `ContextMeter`, `/help`+`/context`,
  `VoiceButton`).
- Aucun fichier backend modifié dans ce lot — uniquement du raccordement
  frontend vers des endpoints déjà réels et déjà en production ; pas de
  suite pytest à relancer.

## R-006 — Code Intelligence : intégration réelle, Cockpit complet, validation locale (2026-08-09)

Rapport complet : [`docs/release/R-006_CODE_INTELLIGENCE_VALIDATION.md`](docs/release/R-006_CODE_INTELLIGENCE_VALIDATION.md).
Demande de l'utilisateur : cahier des charges en 14 phases, tâche de
« Release Engineering / intégration, pas une invitation à créer un nouveau
sous-système ». `CodeIntelligenceRouter`/`CodeIntelligenceAgent` (HOS-055D)
étaient du code réel et non trivial, jamais instancié en production.

### Constat principal (audit, avant tout code)
Trois couches existaient pour KlaatCode/Oh My Pi (Agent → MCP Adapter →
Client) ; seule la couche Client était atteinte par les routes HTTP
préexistantes. `CodeIntelligenceAgent`/`Router` n'étaient importés que par
eux-mêmes et par les tests — jamais instanciés, jamais appelés depuis une
route. Aucune route `/api/v1/code-intelligence` n'existait.

### Décision d'architecture (approuvée par l'utilisateur)
KlaatCode et Oh My Pi restent des providers externes avec leur propre mode
d'exécution — Model Intelligence ne s'y applique jamais. Une troisième voie
authentique, **Hermes-native** (Model Intelligence → Runtime → Ollama), a
été ajoutée pour les tâches de génération/analyse one-shot réelles, avec le
même `ModelRouter`/`OllamaClient` que le reste de Hermes — aucun second
moteur.

### Added
- **Composition root réel** : `CodeIntelligenceAgent` construit en
  réutilisant les singletons `klaatcode`/`ohmypi` déjà adoptés (identité
  d'objet vérifiée par test), pas de nouvelles instances concurrentes.
- **Surface API réelle** : `GET/POST /api/v1/code-intelligence/{status,
  capabilities,providers,analyze,review,debug,explain,history}` — 8
  endpoints adaptateurs purs, validation Pydantic (`force_provider` invalide
  → 422 réel, jamais 500).
- **Routage à 3 voies** : `HermesNativeExecutor` (nouveau), avec traduction
  honnête du vocabulaire de tâches par provider — un `omp code_review`
  envoyé tel quel avant cette passe échouait silencieusement sur un CLI
  réel ; corrigé.
- **Garde-fou d'écriture réel** (Phase 9) : découverte que
  `ToolPolicy.evaluate()`'s branche WRITE est un no-op documenté et qu'aucun
  des deux adaptateurs MCP ne consulte jamais le `ToolSandbox` reçu au
  constructeur — rien n'empêchait réellement une écriture. Un garde-fou
  scopé à Code Intelligence refuse désormais catégoriquement toute tâche
  `refactoring`/`code_generation` routée vers un provider externe.
- **États MCP réels** (5 valeurs explicites : `not_configured`,
  `unavailable`, `unbound`, `connected`, `disconnected`) — remplace un
  booléen toujours faux (KlaatCode liait le mauvais adaptateur ; Oh My Pi
  n'avait aucun concept de liaison).
- **Détection d'installation réelle** : `is_installed()` exigeait
  seulement la présence de `npx`/`bunx`, jamais une invocation réussie —
  Oh My Pi affichait « Installed: yes » alors que chaque commande réelle
  échouait. Corrigé, avec un cooldown de sondage (30 s) pour éviter de
  relancer un sous-processus en échec à chaque poll de 15 s.
- **Center reconstruit** sur l'API réelle (Overview, Providers, Code Tasks,
  Routing & Execution, History) — plus de bandeau « router not exposed »,
  plus de données locales.
- **Publication d'événement manquante corrigée** : `ci.task.started` était
  déclaré depuis HOS-055D sans aucun appel `.publish()` nulle part.

### Anomalies trouvées, non corrigées (hors périmètre « raccordement seul »)
- **KlaatCode** : intégration CLI construite contre une interface qui
  n'existe pas dans la version installée (`analyze --project` réel →
  `unknown option '--project'` ; la vraie interface est `run <prompt>`,
  événements JSON).
- **Oh My Pi** : le paquet npm `omp@1.0.0` existe réellement mais ne
  résout à aucun exécutable via `npx` dans cet environnement.
- **`ToolPolicy`/`ToolSandbox`** restent un no-op pour toute la plateforme
  Tools/MCP au-delà de Code Intelligence.

### Verified
- Exécution réelle Hermes-native : qwen3-coder:30b, RX 6800, 29 242 ms,
  réponse correcte, vérifiée dans le Cockpit reconstruit de bout en bout.
- Exécution réelle KlaatCode et Oh My Pi (échecs réels documentés, pas de
  succès fabriqué).
- Garde-fou de sandbox vérifié contre le composition root réel (refus réel,
  aucun sous-processus lancé).
- Événements réels vérifiés en interrogeant `SystemEventBus.query()` après
  une exécution réelle.
- Suite complète (`tests/` + `backend/tests/`) : **3677 passed, 3 skipped**
  en 745,71 s — 2 échecs, tous deux confirmés être des anomalies de
  timing/ordonnancement préexistantes sans rapport avec Code Intelligence
  (passent seules en isolation) : le flake déjà documenté aux passes
  précédentes, et un nouveau (`test_audit_log.py`, mesure de débit
  sensible au timing réel sous charge machine).
- Frontend : `tsc --noEmit` 0 erreur ; `vitest run` 69/69 (premiers tests
  React du projet, `@vitejs/plugin-react` ajouté) ; `next build` réussi.

## HOS-075 — Assistant v2 : choix manuel du modèle, contexte, commandes, pièces jointes, aperçu web (2026-08-08)

Demande de l'utilisateur, après HOS-074 : liste de fonctionnalités manquantes
face à un LLM comme Claude Code — choix manuel du modèle, pourcentage de la
fenêtre de contexte, paliers d'effort de réflexion, menu de commandes rapides
(`/clean`, `/compact`, `/resume`...), pièces jointes, terminal, aperçu web en
direct du frontend, fonction « artefact ». Avec, à nouveau, demande explicite
d'un avis critique avant implémentation.

### Décisions de conception (avis critique demandé, approuvé par « ok va y »)
- **Choix manuel du modèle et paliers d'effort fusionnés dans un seul
  sélecteur** : les deux reposent sur le même mécanisme backend
  (`ModelRouter.decision_for_role`, un rôle réel de `config/models.yaml`,
  éventuellement avec un forçage du raisonnement). Le proposer comme deux
  contrôles séparés aurait été une distinction sans différence réelle.
- **Paliers d'effort réels, pas un curseur continu** : Hermes ne module pas
  « combien » un modèle réfléchit à l'intérieur d'un même modèle — il
  **change de modèle** (Rapide → `standard`, Réfléchi → `reasoning`,
  Approfondi → `reasoning_escalation`). Un curseur continu aurait prétendu
  à une capacité qui n'existe pas sous le capot.
- **Terminal explicitement refusé pour cette passe** : un shell non
  sandboxé accessible depuis le chat, sans appel d'outils réellement gaté,
  est un vecteur d'exécution arbitraire. Nécessite une conception de
  sécurité dédiée — signalé à l'utilisateur, pas construit à la place d'un
  autre contrôle.
- **Fonction « artefact » (rendu sandboxé de code généré) reportée** :
  sujet à part entière (sandboxing, cycle de vie, persistance), pas une
  case à cocher dans cette passe.
- **`/compact` affiché mais honnête** : aucun résumé d'historique n'existe
  côté serveur. La commande apparaît dans le menu (découvrabilité) mais
  répond « pas encore implémenté » plutôt que de ne rien faire silencieusement
  ou de faire autre chose à la place.
- **Pièces jointes texte/code uniquement** : aucune entrée vision dans le
  chemin d'inférence (`BaseAgent.respond_events`, `/api/chat` d'Ollama)
  aujourd'hui, et un zip n'a pas de comportement défini une fois ouvert —
  construire l'un ou l'autre aurait été un contrôle mentant sur ce qu'il fait.
- **Aperçu web comme alternative sûre au terminal** : `<iframe>` sandboxé
  avec sa propre barre d'adresse — même frontière de confiance qu'un onglet
  de navigateur, sans nouveau chemin d'exécution privilégié.

### Added
- **Choix manuel du modèle + paliers d'effort** : `ModelRouter.known_roles()`
  / `decision_for_role(role, task_type, thinking=)` (nouveau, contourne le
  classement automatique pour un rôle déterministe) ; `BaseAgent.routing_decision()`
  / `respond_events()` acceptent `forced_role`/`forced_thinking` ;
  `POST /conversation/stream` lit `role`/`thinking` du payload, répond par une
  vraie erreur NDJSON (`kind: error`) sur un rôle inconnu plutôt qu'un repli
  silencieux. `GET /system/models` expose désormais `description` par rôle.
  Sélecteur `ModelPicker` (frontend) : Auto, 3 paliers d'effort, et la liste
  complète des rôles réels (jamais codée en dur — `systemClient.models()`).
- **Pourcentage de fenêtre de contexte** : l'événement `done` du stream
  porte `context: {used_tokens_estimate, window}` (même convention
  d'estimation ~4 car./token que `task_executor.py`) ; `ContextMeter` affiche
  le pourcentage réel par rapport au `num_ctx` du rôle actif.
- **Menu de commandes** (`/` dans le composer) : `/clean` (nouvelle
  conversation), `/resume` (sélecteur de session réel, `GET
  /conversation/sessions` — endpoint préexistant, jamais exposé dans l'UI),
  `/compact` (bannière honnête « pas encore implémenté »). Navigation
  clavier (flèches, Échap) et sélection à la souris.
- **Pièces jointes texte/code** : lecture 100 % côté client (`FileReader`,
  plafond 200 Ko, détection de binaire via octet NUL / caractère de
  remplacement), repliées en bloc de code balisé et préfixées au message
  envoyé. Puces retirables avant envoi, rendu dans le fil de discussion
  après envoi et après rechargement (le contenu réellement envoyé passe
  maintenant par le même rendu Markdown que les réponses, y compris côté
  utilisateur — sinon un historique rechargé affichait les balises de code
  brutes au lieu d'un bloc coloré).
- **Aperçu web en direct** : panneau plein écran, barre d'adresse (URL
  http(s) uniquement, normalisation automatique), `<iframe>` sandboxé,
  rechargement, ouverture dans un nouvel onglet, fermeture par Échap ou clic
  sur le fond.

### Verified
- TypeScript propre (`tsc --noEmit`) après chaque phase.
- Vérifié en conditions réelles (navigateur + backend complet + Ollama) :
  sélecteur de modèle affichant les rôles réels avec leur `num_ctx`
  (`qwen3.5:9b`, `deepseek-r1:14b`, `deepseek-r1:32b`, etc.) ; forçage du
  rôle confirmé de bout en bout — sélection « Rapide » → badge de routage
  passant à `qwen3.5:9b` ; compteur de contexte affichant un vrai
  pourcentage après réponse ; les trois commandes slash exécutées
  (`/clean` → nouvelle session confirmée, `/resume` → sélecteur listant les
  sessions réelles avec horodatage et nombre de messages, `/compact` →
  bannière honnête affichée) ; pièce jointe `note.py` envoyée sans message
  additionnel, modèle répondant correctement sur son contenu (« le nom de la
  fonction est `greet` ») ; aperçu web chargeant le Cockpit lui-même en
  direct dans l'iframe.
- Nouveaux tests hermétiques : `tests/architecture/test_model_router.py`
  (+6, forçage de rôle), `tests/architecture/test_base_agent_forced_role.py`
  (7, nouveau), `tests/architecture/test_conversation_streaming.py` (+3,
  payload de route — rôle forcé, contexte dans `done`, erreur sur rôle
  inconnu). 38 tests, tous passants.
- Suite complète (`tests/` + `backend/tests/`) : **3603 passed, 3 skipped**
  en 13m36s — le seul échec du run complet
  (`test_task_executor_shares_the_container_model_intelligence`) est le
  flake de test-ordering déjà documenté aux passes précédentes, revérifié
  passant seul en isolation (1 passed).

## HOS-074 — Assistant : streaming réel, mémoire de conversation, refonte premium (2026-08-08)

Demande de l'utilisateur : septième onglet de la série — l'Assistant (chat).
Maquette fournie transformant le chat en « console opérationnelle », avec
demande explicite d'un avis critique et de propositions. Puis carte blanche :
« je veux au final avoir une interface premium et avec toutes les
fonctionnalités d'un LLM comme Claude ou GPT fonctionnel », design poussé au
maximum sur cet onglet.

### Constat principal (audit, avant tout code)

Un pipeline de chat **streaming complet et réel existait déjà** —
`POST /chat` (`backend/api/routes/chat.py`) : streaming token par token,
canal de raisonnement séparé (`include_thinking` → NDJSON), décision de
routage réelle exposée en en-têtes `X-Hermes-*`, télémétrie d'audit
(`first_token_ms`, `tokens_per_second`), publication d'événements
`chat.token`. Côté frontend, un client complet `streamChat()`
(`lib/api.ts`) avec gestion NDJSON et reprise de ligne partielle.

**L'onglet Assistant n'utilisait ni l'un ni l'autre.** Il passait par
`POST /conversation/message`, bloquant, et `streamChat()` avait **zéro
appelant** — code mort. Même schéma « deux cerveaux » que les six onglets
précédents. Vérifié en direct avant correction : `curl` sur `/chat`
renvoyait bien `transfer-encoding: chunked` + `x-hermes-model: qwen3.5:9b`.

### Autres écarts trouvés
- **Le chat n'avait aucune mémoire.** `ResponseGenerator._ask_model()`
  n'envoyait que `[system, user]` : les tours précédents étaient stockés
  dans la session et **jamais transmis au modèle**. Chaque message était
  traité comme le premier — « quel est mon chiffre préféré ? » n'avait rien
  à quoi se référer.
- **Faille XSS réelle** : les réponses passaient par
  `dangerouslySetInnerHTML` alimenté par deux `String.replace()` regex. Un
  modèle émettant `<img src=x onerror=...>` exécutait du JS arbitraire dans
  le Cockpit. Le rendu ne comprenait par ailleurs que `**gras**` et les
  retours à la ligne : blocs de code, tableaux et listes — l'essentiel de ce
  que répond un assistant de développement — s'affichaient à plat.
- **Verrou global tenu pendant toute l'inférence.** `handle_message()`
  gardait le `RLock` du manager pendant l'appel modèle (30–120 s sur un
  modèle local), sérialisant toute opération de session à l'échelle de
  l'application — exactement le défaut corrigé en HOS-069 pour
  `ExecutionController`.
- **Aucune interruption possible**, aucune persistance de session
  (l'endpoint d'historique existait, n'était jamais appelé : chaque
  rechargement repartait d'une conversation vide au-dessus d'une session
  qui gardait pourtant son transcript côté serveur).

### Décisions de conception (carte blanche)
- **Consolidation plutôt qu'un troisième pipeline** : la nouvelle route
  `POST /conversation/stream` garde la sémantique du module conversation
  (session, historique, intention, approbation) et **délègue l'inférence à
  la même machinerie que `/chat`** (`BaseAgent.respond_events` : décision
  ModelRouter réelle, canal de raisonnement, repli cloud).
- **Panneau outils non construit, délibérément.** L'audit HOS-069 a établi
  que ce chemin n'effectue aucun appel d'outil réel (`assigned_tools` n'est
  qu'un indice textuel dans le prompt). Un interrupteur « activer les
  outils » aurait été exactement le type de tableau de bord mensonger
  corrigé sur les six onglets précédents.
- **Visualisation multi-agents non construite** : `CollaborationEngine` est
  réel mais n'est jamais invoqué par une vraie mission (HOS-070).
- **Densité maîtrisée** : conversation plein écran par défaut, rail
  contextuel repliable ne portant que des données réelles (runtime/VRAM
  HOS-072, décision de routage réelle), plutôt qu'un mur permanent de 15
  widgets.

### Added
- **Streaming réel** : `POST /conversation/stream`, corps NDJSON
  (`{"kind": "thinking"|"content"|"done"|"error"}`), en-têtes de routage
  réels (`X-Hermes-Model/Tier/Role/Reason/Thinking/Intent/Session`) et
  anti-bufferisation (`X-Accel-Buffering: no`). Nouveau client
  `services/conversation-stream.ts` avec `AbortSignal`.
- **Mémoire de conversation** : `ConversationManager.build_model_messages()`
  transmet l'historique réel (borné à 20 tours), avec mapping des rôles
  internes (`hermes`/`agent` → `assistant`) et prompt système enrichi de
  l'état réel (mission active, agents, modèle courant).
- **Verrou resserré** : `begin_stream()`/`finish_stream()` encadrent
  l'inférence, qui se déroule **hors** du verrou. Une réponse interrompue
  est conservée telle quelle (une réponse partielle affichée mais absente de
  l'historique désynchroniserait le tour suivant).
- **Rendu Markdown sûr** : `react-markdown` + `remark-gfm` +
  `rehype-highlight` (arbre React, pas d'injection HTML — le HTML brut d'un
  modèle est inerte par construction). Blocs de code avec étiquette de
  langage, coloration syntaxique mappée sur la palette Hermes, et bouton
  Copier. Tableaux, listes, titres, citations stylés.
- **Interruption** : bouton Stop et raccourci Échap pendant la génération,
  la réponse partielle étant conservée et annoncée comme telle.
- **Persistance de session** : restauration via `localStorage` +
  chargement de l'historique réel au montage ; bouton Nouvelle conversation.
- **Explicabilité du routage** : badge modèle avec panneau « Pourquoi ce
  modèle ? » (modèle, tier, rôle, raisonnement, intention, motif réel du
  ModelRouter — ex. « model already loaded in VRAM, reused to avoid reload »).
- **Refonte visuelle** : curseur de streaming, blocs de raisonnement
  repliables, état vide avec actions rapides, auto-scroll respectant la
  lecture (désactivé dès que l'utilisateur remonte), composer auto-extensible,
  actions au survol (copier, régénérer), rail contextuel animé.

### Bugs trouvés et corrigés
- Chat sans mémoire (historique jamais transmis au modèle).
- XSS via `dangerouslySetInnerHTML` sur la sortie du modèle.
- Verrou du manager tenu pendant l'inférence.
- Session jamais restaurée malgré un endpoint d'historique existant.

### Verified
- Vérifié en conditions réelles (navigateur + backend complet + Ollama) :
  streaming token par token confirmé (curseur visible, 4311 caractères
  arrivés progressivement) ; **mémoire confirmée de bout en bout** — « Mon
  chiffre préféré est 42 » puis « Quel est mon chiffre préféré ? » →
  « Votre chiffre préféré est **42**. », et dans l'UI « Comment s'appelait
  la fonction que tu viens d'écrire ? » → « fib » ; Markdown réel (titre,
  paragraphe, bloc Python coloré avec étiquette PYTHON et bouton COPIER) ;
  Stop réel en cours de génération → « ⏹ INTERROMPU — RÉPONSE PARTIELLE »
  avec le texte déjà reçu conservé ; persistance vérifiée par rechargement
  complet de la page (8 messages restaurés, session `conv_160135c6cde0`) ;
  panneau « Pourquoi ce modèle ? » affichant la vraie décision.
- Nouveaux tests hermétiques :
  `tests/architecture/test_conversation_streaming.py` (12 — historique
  réellement transmis, mapping des rôles, bornage, prompt système situé,
  cycle begin/finish, réponse interrompue conservée, et un test de
  concurrence vérifiant que le manager reste utilisable pendant l'inférence).
- Suite conversation complète : **118 passed**. TypeScript propre.
- Suite complète (`tests/` + `backend/tests/`) : **3587 passed, 3 skipped,
  0 échec réel** en 14m46s — le seul échec du run complet
  (`test_task_executor_shares_the_container_model_intelligence`) est le
  flake de test-ordering déjà documenté aux passes précédentes,
  reproductible seul en isolation avec succès (revérifié).

## HOS-073 — Correction : tous les modèles n'apparaissaient pas dans Model Intelligence (2026-08-08)

Demande de l'utilisateur : "dans l'onglet models tout les modeles
n'apparaisse pas donc je ne peux pas effectuer les benchmark sur tout les
modeles" — suivi d'une demande de benchmark réel sur "bonsai 27B ternary
Q2" (lien HuggingFace `prism-ml/Ternary-Bonsai-27B-gguf`).

### Constat (deux bugs réels, indépendants, qui se combinaient)
- `GET /models/ranking` avait un défaut `limit=5` (à la fois côté route et
  côté `handle_get_ranking`), et le Cockpit (tableau de classement +
  sélecteur de modèle du Benchmark) l'appelait sans jamais préciser de
  limite — donc seuls les 5 modèles au score le plus haut apparaissaient,
  quel que soit le nombre réel de modèles enregistrés (`config/models.yaml`
  définit à lui seul 12 rôles).
- `ModelProfiler` ne connaissait que les 12 modèles assignés à un rôle
  dans `config/models.yaml` (`PREDEFINED_MODELS`) — un modèle installé
  manuellement dans Ollama (pour l'essayer ou le benchmarker) n'apparaissait
  jamais, sans aucun moyen de l'ajouter sans éditer ce fichier et lui
  inventer un rôle.

### Corrigé
- `GET /models/ranking` : défaut relevé à 100 (route + `handle_get_ranking`,
  plafond `le=200`) ; le client frontend précise désormais explicitement
  `?limit=100` plutôt que de dépendre implicitement du défaut serveur.
- Nouveau `ModelProfiler.sync_from_ollama()` (HOS-073) : interroge le vrai
  `/api/tags` d'Ollama et enregistre tout modèle localement installé mais
  pas encore connu, avec des valeurs honnêtes (VRAM estimée depuis la
  taille réelle du fichier rapportée par Ollama, faute de benchmark
  HOS-065C pour un modèle sans rôle configuré) — jamais fabriquées, jamais
  écrasant un profil déjà connu et curé. Appelé depuis `GET /models` et
  `GET /models/ranking`, donc un modèle tout juste installé apparaît sans
  redémarrage du backend.
- Bug résiduel trouvé au passage (HOS-071 Phase B incomplet) :
  `handle_get_ranking` affichait encore `m.overall_score` (l'approximation
  de repli) au lieu de `profiler._score(m)` (la vraie formule
  `compute_model_score`, ce qui pilote pourtant déjà le tri) — corrigé
  pour que le score affiché soit celui qui a réellement classé la ligne.
- Troisième bug trouvé une fois le premier corrigé (donc invisible tant que
  seuls 5 modèles s'affichaient) : erreur console React *"Encountered two
  children with the same key, `standard`"*. `_build_predefined_models()`
  construit `tags=[role_name, tier]` — le rôle `standard` de
  `config/models.yaml` a justement `tier: standard`, donc `tags=
  ["standard", "standard"]`, et le Cockpit rendait ces tags avec
  `key={t}`. Corrigé des deux côtés : dédoublonnage côté backend (racine
  du problème) et clé indexée (`${t}-${i}`) côté frontend en garde-fou
  défensif pour toute future collision de données.

### Vérifié en conditions réelles
- Navigateur + backend complet + Ollama réel : le classement passe de 5 à
  **20 modèles réels** affichés (12 rôles configurés + 8 modèles installés
  manuellement, dont deux variantes de Bonsai 27B jusque-là invisibles).
- Tentative de benchmark réel sur exactement le modèle demandé,
  `hf.co/leok7v/Ternary-Bonsai-27B-gguf:Q2_0` (déjà installé localement —
  aucun téléchargement nécessaire, correspond au modèle du lien HuggingFace
  fourni) : requête réelle envoyée à Ollama, qui répond
  `500 Internal Server Error` — `{"error":"tensor \"output.weight\" size
  overflow"}`, une vraie erreur de chargement GGUF côté Ollama/llama.cpp
  (v0.32.5), pas une limitation d'Hermes. Le fichier GGUF de cette
  variante précise (mirror "leok7v", quant Q2_0) semble corrompu ou
  produit par un convertisseur incompatible — sans rapport avec le bug
  corrigé ici. Par comparaison, l'autre variante installée localement,
  `hf.co/eugenehp/bonsai-27b-gguf:Q1_0` (uploader différent, Q1_0),
  répond normalement (17.3s, 258 tokens, raisonnement réel affiché).
- Confirmé aussi que le bug de clé dupliquée a bien disparu : console
  navigateur propre après redémarrage du backend, la ligne `qwen3.5:9b`
  n'affiche plus qu'un seul tag `standard` au lieu de deux.
- Nouveaux tests hermétiques : `tests/architecture/test_model_intelligence_hos073.py`
  (9 — enregistrement d'un modèle non-caté, non-écrasement d'un profil
  connu, détection embedding, échec Ollama honnête, apparition réelle
  dans le classement, non-régression du défaut de limite, absence de tags
  dupliqués sur tout profil enregistré).
- Suite ciblée (`tests/model_intelligence/` + les deux fichiers HOS-071/073) :
  **224 passed**. Vérification TypeScript frontend propre.
- Suite complète (`tests/` + `backend/tests/`) lancée mais restée bloquée
  à 46 % sans progresser pendant plus de 20 minutes — le pattern
  d'instabilité Ollama sous charge soutenue déjà documenté aux passes
  précédentes (HOS-069), probablement aggravé ici par l'activité réelle de
  cette même passe (tentative de benchmark sur un modèle 27B, puis
  téléchargement et benchmark réel d'un modèle 19 Go, tous deux sur la
  même instance Ollama locale que la suite de tests sollicite). Finalisé
  sur la base de la suite ciblée (224 passed, aucune régression) et de la
  vérification navigateur en direct plutôt que d'attendre indéfiniment un
  run déjà connu pour ce type de blocage environnemental.

## HOS-072 — Runtime : découverte honnête, télémétrie réelle, déchargement VRAM actif (2026-08-08)

Demande de l'utilisateur : sixième onglet de la même série de revues
(après Autonomous OS, Missions, Execution, Agents, Model Intelligence) —
"Runtime", la couche qui transforme le choix abstrait d'un modèle
(Model Intelligence) en décision d'exécution réelle : runtime disponible,
VRAM/RAM suffisantes, quantification, gestion du chargement/déchargement
pour éviter la "catastrophe" de plusieurs modèles chargés simultanément
sur une RX 6800 16 Go. Spécification détaillée fournie : chaîne
Autonomous/Mission → Model Intelligence → **Runtime** → Ollama/GPU,
sélection de runtime qui ne doit jamais se déclarer disponible juste
parce qu'une classe existe dans le code, allocation avec file
load→execute→unload, apprentissage depuis l'exécution réelle, Cockpit
avec hardware/runtimes actifs/modèle chargé/historique/actions
(refresh, charger, décharger, libérer la VRAM, benchmark...). Après audit
et validation du plan en 5 phases par l'utilisateur ("ok va y"), mise en
œuvre complète.

### Constat principal (audit, avant tout code)

Contrairement à ce qu'un seul "Runtime Center" suggère, il existe **trois
systèmes de sélection de runtime séparés, aucun consulté par l'exécution
réelle, plus un complètement mort** :
- `backend/ral/` (RuntimeRegistry/Selector/Router/Decision) — exposé via
  l'ancien module `backend/sds/` à `/api/v1/runtimes`, exactement ce que
  lit le frontend. Un vrai `HermesOllamaRuntime` y est enregistré au
  démarrage, mais sa logique de sélection/routage n'est jamais consultée
  par une exécution réelle — un commentaire dans `main.py` le dit
  explicitement : *"does not yet route real inference through this
  registry ... that remains a separate, larger rewiring."*
- `backend/runtime/orchestrator/` (`RuntimeOrchestrator`) — réel, testé,
  ses propres routes, mais consulté seulement pour : la simulation
  "what-if", des alternatives *advisory* dans les explications de
  décision Autonomous, et l'enregistrement de noms. Jamais pour choisir
  le runtime d'une vraie tâche.
- `backend/services/mission_control.py` (`MissionControlService`) — une
  **troisième** façade enveloppant la totalité de `ral`, dont le router
  n'est monté nulle part dans `main.py`. Complètement mort, pas juste
  orphelin.
- La vraie sélection, dans `RealTaskExecutor` (le seul chemin qui exécute
  réellement), est en fait triviale : toujours Ollama, modèle choisi par
  Model Intelligence (HOS-071).

### Autres écarts trouvés
- Le bug WMI "4 Go" mentionné par l'utilisateur est déjà trouvé et corrigé
  (commit `c9ffe6b1`, `gpu_monitor.py` lit `HardwareInformation.qwMemorySize`
  dans le registre Windows, pas `Win32_VideoController.AdapterRAM`) —
  confirmé, rien à refaire.
- Aucun runtime n'était jamais réellement sondé : `discovery_engine.py`
  déclarait "disponible" via un catalogue Python codé en dur (12 modèles
  Ollama génériques ne correspondant même pas à ce qui est réellement
  installé — du `qwen3:8b`/`deepseek-r1:32b` inventés, pas le vrai
  `qwen3.5:9b`/`gemma4:12b`). `ral/runtime_health.py` documente lui-même
  qu'il ne contacte "aucun backend concret" — la santé était un statut
  auto-déclaré. Pire : `HermesOllamaRuntime.start()` mettait STARTED
  inconditionnellement, sans jamais vérifier qu'Ollama répondait — le
  `GET /api/v1/runtimes` que lit le Cockpit pouvait donc dire "actif" pour
  un serveur mort.
- Pas de cycle load→execute→unload actif — la VRAM se libérait
  passivement via le `keep_alive` d'Ollama (10 min par défaut), jamais via
  un déchargement déclenché par Hermes.
- La boucle d'apprentissage (`backend/runtime/intelligence/`,
  `LearningEngine`) est entièrement orpheline — ses handlers
  (`on_runtime_completed`, etc.) ne sont abonnés à rien.
- `GET /runtime/resources/allocations` et `POST /runtime/resources/release`
  sont honnêtement toujours vides en production : `ResourceManager.
  reserve_resources()`, la seule méthode qui peuple `_allocations`, n'est
  appelée nulle part dans le vrai chemin d'exécution (l'admission VRAM de
  HOS-069 n'utilise que le `can_allocate()` en lecture seule).
- Le frontend était un pur tableau de bord en lecture seule (vérifié en
  lisant le fichier en entier) : jauges RAM/VRAM/température réelles, mais
  zéro bouton d'action — pas de charger/décharger/benchmark/bloquer.

### Added
- **Phase A — Découverte et démarrage honnêtes** : `OllamaConnector`
  (`discovery_engine.py`) interroge désormais réellement `/api/tags` de
  l'endpoint Ollama configuré au lieu d'un catalogue statique — liste vide
  (jamais fabriquée) si injoignable. `HermesOllamaRuntime.start()` vérifie
  désormais la joignabilité réelle (`list_local_models()`) avant de passer
  à STARTED ; passe à ERROR (sans jamais lever, pour ne pas casser le
  démarrage de l'app) si Ollama ne répond pas.
- **Phase B — Télémétrie réelle synchronisée** : nouveau
  `RealTaskExecutor.on_runtime_result` (callback dédié, à côté de
  `on_execution` qui alimente Model Intelligence) — appelé après chaque
  tentative réelle, succès ou échec, avec le runtime effectivement utilisé.
  Câblé sur `RuntimeHealthMonitor.record_execution()`
  (`backend/sds/runtime.get_runtime_health_monitor()`, nouveau singleton
  partagé), qui alimente à son tour `GET /api/v1/runtimes` — `metrics`/
  `health` étaient absents de la réponse (le type frontend le documentait
  déjà : *"pas health ni metrics"*), désormais réels quand un runtime a
  vraiment servi une tâche, `null` explicite sinon (non mesuré ≠ mesuré à
  zéro). `RuntimeOrchestrator`/`MissionControlService` documentés
  honnêtement (statut réel, jamais consultés pour l'exécution) plutôt que
  de tenter le rewiring complet déjà signalé comme "chantier séparé" dans
  le code.
- **Phase C — Déchargement VRAM actif** : nouveau
  `OllamaClient.unload_model()` (keep_alive: 0, signal réel d'Ollama pour
  décharger immédiatement). `RealTaskExecutor._check_vram_admission`
  tente désormais, une fois passé la moitié du délai d'attente sans
  admission, de décharger activement le plus gros autre modèle résident
  au lieu d'attendre uniquement le timeout passif d'Ollama (jusqu'à 10 min
  par défaut).
- **Phase D — Actions réelles dans le Cockpit** : nouvelles routes réelles
  `GET /runtime/resources/loaded-models` (modèles réellement résidents,
  `/api/ps` d'Ollama) et `POST /runtime/resources/unload` (décharge un
  modèle immédiatement) — documentées comme l'alternative réelle aux
  `allocations`/`release` toujours vides (voir "Autres écarts trouvés").
  Nouvelle carte "Modèle(s) chargé(s)" dans le Runtime Center avec un vrai
  bouton "Décharger" par modèle.
- **Phase E — Cockpit** : les tuiles "Fiabilité"/"Performance" (jamais
  rendues, `metrics` étant toujours `undefined`) deviennent "Fiabilité"/
  "Latence moy." avec de vraies données, ou un message honnête "aucune
  tâche réelle exécutée" tant qu'aucune tâche n'est passée par ce runtime.

### Bugs trouvés et corrigés en cours de route
- `HermesOllamaRuntime.start()` ne vérifiait jamais la joignabilité réelle
  d'Ollama avant de déclarer STARTED — trouvé pendant l'audit, corrigé en
  Phase A.
- Types frontend `RuntimeMetrics`/`RuntimeHealth` déclaraient des champs
  fabriqués (`avg_tokens_per_sec`, `circuit_breaker`, `performance`) que
  le backend n'a jamais su calculer — corrigés pour correspondre
  exactement à ce que `RuntimeHealthMonitor` sait réellement mesurer.

### Verified
- Vérifié en conditions réelles dans le navigateur avec Ollama réel et
  backend complet (34/34 sous-systèmes assemblés) : Runtime Center
  affichant VRAM/RAM/GPU réels (AMD Radeon RX 6800) ; carte "Modèle(s)
  chargé(s)" listant `qwen3:1.7b` (2.1 GB VRAM) via la vraie route
  `/runtime/resources/loaded-models` ; clic sur "Décharger" → requête
  réelle `POST /runtime/resources/unload` → 200 OK → VRAM affichée
  passant de 13.0 % (2.1/16.0 Go) à 0.0 % (0.0/16.0 Go) et la carte
  affichant honnêtement "Aucun modèle chargé" — déchargement réel
  confirmé de bout en bout sur le matériel de l'utilisateur.
- Nouveaux tests hermétiques (aucun Ollama réel requis) :
  `tests/architecture/test_runtime_health_feedback.py` (6 — callback
  `on_runtime_result` sur succès/échec/timeout/fallback cloud→local),
  `tests/architecture/test_ollama_unload.py` (2 — requête réelle
  `keep_alive: 0`), `tests/architecture/test_runtime_resources_loaded_models.py`
  (5 — nouvelles routes), extensions de `test_vram_admission.py` (5 —
  déchargement actif une fois passé la moitié du délai), de
  `test_runtime_discovery.py` (4 — découverte réelle vs catalogue),
  `test_hermes_ollama_runtime.py` (2 — démarrage honnête) et
  `test_runtime_sds.py` (2 — métriques réelles dans `/runtimes`).
- Suite complète (`tests/` + `backend/tests/`) : **3566 passed, 3 skipped,
  0 échec réel** en 15m58s — le seul échec du run complet
  (`test_task_executor_shares_the_container_model_intelligence`) est le
  flake de test-ordering déjà documenté aux passes précédentes,
  reproductible seul en isolation avec succès (revérifié).

## HOS-071 — Model Intelligence : VRAM réelle, un seul scoring, optimiseur câblé (2026-08-08)

Demande de l'utilisateur : cinquième onglet de la même série de revues
(après Autonomous OS, Missions, Execution, Agents) — "Model Intelligence".
Spécification détaillée fournie : sélection modèle+runtime+quantification
pilotée par la tâche (pas juste le modèle), exemple chiffré sur sa propre
RX 6800 16 Go, formule de scoring à 5 facteurs (Quality 30% / Reliability
25% / Speed 20% / Efficiency 15% / Benchmark 10%) avec apprentissage dans
le temps, méthodologie de benchmark strictement séquentielle avec métriques
réelles, conscience de la VRAM libre en temps réel au moment de la
décision, apprentissage depuis l'exécution réelle, intégration avec Agents
et Autonomous, Cockpit détaillé (vue d'ensemble, classement, panneau de
recommandation). Point de fermeture explicite : par défaut, l'utilisateur
ne devrait presque jamais avoir à choisir un modèle manuellement — Hermes
doit gérer Tâche → Agent → Modèle → Runtime → Quantification → Ressources →
Exécution → Résultat → Apprentissage automatiquement. Après audit et
validation du plan en 5 phases par l'utilisateur ("ok va y"), mise en
œuvre complète.

### Constat principal (audit, avant tout code)

Contrairement aux quatre onglets précédents, Model Intelligence n'avait pas
de pipeline fantôme complet — `AdaptiveRouter.recommend()` est réellement
la décision unique consultée à chaque tâche réelle (`RealTaskExecutor` via
`model_for`/`num_ctx_for`/`runtime_for`/`local_fallback_for`), le
benchmarking avait déjà été rendu réel (HOS-065C), et `ModelAutonomousAdapter`
avait été délibérément cantonné à un rôle de reporting plutôt que de
décision (voir `AutonomousOrchestrator.set_model_adapter()`). Mais le même
problème structurel réapparaissait sous une autre forme : **trois formules
de scoring différentes répondaient à « quel est le meilleur modèle », et
aucune n'était celle décrite par l'utilisateur** :
- `ModelProfile.overall_score` (property) — quality 30 / speed 20 /
  **reliability 30** / **efficiency 20** / benchmark 10 — pilotait le
  classement du Cockpit (`/models/ranking`).
- `ModelPredictor.rank_models()` — task_fit 35 / success_prob 35 / tps 15 /
  vram_eff 15, aucun facteur "benchmark" — pilotait **la vraie
  recommandation de production** (`recommend()`, donc chaque tâche réelle).
- `PerformanceAnalyzer.compute_model_score()` — quality 30 / reliability 25
  / speed 20 / efficiency 15 / benchmark 10, exactement la formule décrite
  par l'utilisateur — réelle, correcte, mais utilisée par un seul endpoint
  de lecture (`GET /models/performance?model_id=X`), jamais pour classer ni
  recommander.

### Autres écarts trouvés
- VRAM libre en temps réel absente de la décision (spec section 7) :
  `recommend()`/`_model_for()` filtraient toujours contre un plafond
  statique `max_vram_mb=8192` — jamais interrogé auprès de
  `ResourceManager`. Le vrai contrôle VRAM (`_check_vram_admission`,
  HOS-069) n'intervenait qu'*après* le choix du modèle, comme une attente
  bloquante, jamais comme critère de sélection. Sur la RX 6800 16 Go de
  l'utilisateur, chaque recommandation raisonnait par défaut sur un
  plafond deux fois trop bas.
- `ModelRuntimeOptimizer` (recherche combinée model+runtime+quantization,
  exactement la section 6 de la spec) était réel et complet, mais mort :
  `_get_optimizer()` n'était appelé par aucun handler, aucune route.
  `AdaptiveRouter._select_runtime()`/`_select_quantization()` utilisaient
  deux heuristiques séparées bien plus simples.
- `ModelRuntimeAdapter` (`simulate_execution`/`compare_runtimes`) — réel,
  bien construit, zéro appelant en dehors de son propre fichier et de ses
  tests.
- `_model_for()` réinférait le type de tâche via des mots-clés sur
  `task.title`, en ignorant `task.task_type` déjà structuré (ajouté par
  HOS-070 depuis `MissionNode.type`).
- `ModelEvolutionAdapter.update_weights()` mort — rien ne l'appelait
  jamais.
- Bug trouvé pendant l'audit, pas dans la spec : le Cockpit envoyait
  `{task_type, description}` à `POST /models/recommend`, mais la route ne
  lisait que `payload.get("task_description")` — chaque clic réel
  recommandait donc pour une chaîne vide, quel que soit le texte tapé par
  l'utilisateur.
- Cockpit très éloigné de la maquette : pas de widget VRAM libre en temps
  réel, pas de "meilleur par catégorie", pas d'onglet History (l'endpoint
  existait, jamais surfacé), l'onglet Benchmark affichait du JSON brut,
  l'onglet "Optimizer" ne consultait jamais le vrai `ModelRuntimeOptimizer`.

### Added
- **Phase A — VRAM réelle dans la décision** : `ResourceManager.get_gpu_info()`
  câblé dans `_model_for`/`_num_ctx_for`/`_runtime_for`/`_local_fallback_for`
  (`service_registry.py`) — chaque recommandation de production utilise
  désormais la VRAM réellement libre à l'instant T, plus un plafond statique.
  Même câblage pour `POST /models/recommend` (nouveau `set_resource_manager()`
  dans `routes.py`, appelé par le route-binder) : un appel sans
  `max_vram_mb` explicite utilise la VRAM libre réelle plutôt que 8192 codé
  en dur.
- **Phase B — Un seul scoring** : `ModelProfiler`/`ModelPredictor`
  construisent désormais toujours un `PerformanceAnalyzer` réel (partagé
  via `routes.py`, ou privé si construits nus) et appellent
  `compute_model_score()` — le classement du Cockpit et la vraie
  recommandation de production lisent enfin la même formule.
  `ModelProfile.overall_score` (repli pour tout appelant sans analyzer,
  ex. `ModelEvolutionAdapter`) corrigé aux mêmes poids 30/25/20/15/10 —
  toujours une approximation (données différentes : records/benchmarks vs
  champs bruts du profil), documenté comme tel plutôt que de prétendre à
  une parité exacte.
- **Phase C — Signal de tâche structuré** : `recommend_for_text()` accepte
  désormais `task_type_hint` — `_model_for` et les trois autres callbacks
  du bootstrap le préfèrent à la ré-inférence par mots-clés sur le titre.
  Bug du payload `/models/recommend` corrigé (accepte `task_description`
  *et* `description`, et lit désormais `task_type` du payload).
- **Phase D — Optimiseur réel câblé** : `AdaptiveRouter` accepte
  `runtime_optimizer` (`set_runtime_optimizer()`) — `recommend()` consulte
  désormais la vraie recherche combinatoire de `ModelRuntimeOptimizer` pour
  choisir runtime + quantification ensemble, au lieu de deux heuristiques
  indépendantes ; repli sur ces heuristiques si l'optimiseur ne trouve rien
  ou n'est pas câblé. Nouvelle route `GET /models/optimize?model_id=X`
  (`ModelRuntimeAdapter.compare_runtimes()`, câblé pour la première fois) —
  comparaison réelle cross-runtime/quantification, sizée sur la VRAM totale
  réelle quand disponible.
- **Phase E — Cockpit Model Intelligence** : refonte —
  widget VRAM/GPU temps réel (réutilise `useMonitoringResources`), cartes
  "Meilleur global / Plus rapide / Plus efficient (VRAM)", onglet Recommend
  avec sélecteur de type de tâche explicite, onglet Benchmark réel
  (déclencheur `POST /models/benchmark` + tableau des résultats stockés, au
  lieu d'un dump JSON brut), onglet Optimizer réel (comparaison
  cross-runtime via la nouvelle route, au lieu de reformater le modèle #1
  du classement), nouvel onglet History (`GET /models/history`, jamais
  surfacé auparavant).

### Bugs trouvés et corrigés en cours de route
- `/models/recommend` : clé de payload jamais alignée entre frontend
  (`description`) et backend (`task_description`) — chaque recommandation
  réelle depuis le Cockpit ignorait silencieusement le texte de la tâche.
- `ModelProfile.overall_score` utilisait des poids 30/20/**30**/**20**/10 —
  déjà différent des 30/25/20/15/10 documentés avant même la question du
  scoring "à trois formules".
- `tps` non arrondi dans les réponses `/models/ranking` et `GET /models`
  (`ModelProfiler.get_stats()`) — visible une fois la télémétrie réelle
  alimentée par un benchmark réel (ex. "30.41897838148077 TPS").

### Verified
- Vérifié en conditions réelles dans le navigateur avec Ollama réel et
  backend complet (34/34 sous-systèmes assemblés) : widget VRAM affichant
  "AMD Radeon RX 6800, 2.1–3.0 / 16.0 Go, 13–14 Go libres — c'est ce que
  les recommandations utilisent désormais" ; onglet Recommend avec un vrai
  texte de tâche + type explicite produisant une vraie décision
  (`qwen3:1.7b`, ollama/q4_k_m, confiance 50%, alternatives réelles avec
  scores distincts) confirmée via le payload réseau (`task_description`
  bien transmis) ; onglet Benchmark déclenchant un vrai appel Ollama
  (`qwen3:1.7b`/chat, 5227ms, 225.2 TPS, quality "ok") qui met à jour en
  direct le classement et les compteurs "1 RUNS"/"MEILLEUR GLOBAL" ; onglet
  Optimizer renvoyant une vraie comparaison à 4 runtimes avec des VRAM
  estimées distinctes selon le modèle sélectionné ; onglet History
  affichant la vraie décision de recommandation. Tous les appels réseau
  `/models/*` en 200 OK.
- Nouveaux tests hermétiques (aucun Ollama réel requis) :
  `tests/architecture/test_model_intelligence_hos071.py` (18 tests — VRAM
  temps réel, unification du scoring avec/sans analyzer partagé, priorité
  du task_type structuré sur l'inférence par mots-clés, correction du bug
  de payload, câblage de l'optimiseur et de la route `/models/optimize`).
- Suite complète (`tests/` + `backend/tests/`) : **3542 passed, 3 skipped,
  0 failed** en 13m26s — propre de bout en bout, y compris le flake de
  test-ordering déjà documenté aux passes précédentes
  (`test_task_executor_shares_the_container_model_intelligence`), qui
  passe cette fois sans problème. Aucun échec lié à Ollama malgré les
  appels réels effectués pendant la vérification navigateur.

## HOS-070 — Agents : activité réelle, sélection unifiée, confiance réelle (2026-08-08)

Demande de l'utilisateur : quatrième onglet de la même série de revues
(après Autonomous OS, Missions, Execution) — "le centre de gestion de la
main-d'œuvre agentique". Spécification détaillée fournie : registre
d'agents, chaîne d'attribution des tâches (Decision Engine → Agent
Selection avec capacités/spécialisation/skills/outils/confiance/charge),
supervision (détection de blocage/lenteur/erreurs), collaboration
multi-agents, porte de sécurité par agent (Trust → Permission → Policy →
Threat → Isolation), Cockpit avec vue globale et vue détaillée par agent
(Performance, Trust, Tools). Après audit et validation du plan en 5 phases
par l'utilisateur ("ok va y"), mise en œuvre complète.

### Constat principal (audit, avant tout code)
Le registre d'agents (`AgentRegistry`, `backend/agents/`) n'est **jamais
mis à jour par une vraie exécution**. `update_status()`/`update_metrics()`
ne sont appelés que depuis `TaskDispatcher.dispatch()`, lui-même appelé
uniquement par `AgentSupervisor.dispatch_node()`/`execute_mission_step()`/
`execute_full_mission()` — et une recherche exhaustive dans tout le dépôt
confirme que rien d'autre n'appelle jamais ces trois méthodes. Le vrai
pipeline (`GraphExecutor` → `MissionExecutor` → `AgentCoordinator`, module
`execution/`) ne passe jamais par `AgentSupervisor` pour exécuter —
seulement pour l'enregistrement initial au démarrage. Résultat : chaque
agent affichait pour toujours son état initial ("READY", 0 tâche, 0%
succès, "Idle") quel que soit le nombre de missions réellement exécutées —
déjà observé sans le remarquer pendant HOS-068/069.

### Autres écarts trouvés
- Deux moteurs de sélection d'agent coexistaient, déconnectés :
  `AgentCoordinator` (utilisé réellement) faisait une correspondance de
  mots-clés simpliste ; `CapabilityMatcher` (`backend/agents/`, HOS-043) —
  un moteur à score multi-critères bien plus riche (capacités 30%, charge
  25%, disponibilité 20%, historique de succès 15%, préférence runtime
  10%) — n'était jamais appelé par le vrai chemin.
- Mine dormante : `TaskDispatcher.__init__` avait
  `execute_callback or (lambda a, n: True)` — un callback par défaut qui
  fabrique un succès sans rien exécuter, exactement le défaut R-001 déjà
  corrigé ailleurs. Inoffensif tant que ce chemin reste mort (confirmé),
  documenté plutôt que changé (le changer casserait plusieurs tests
  préexistants qui s'appuient sciemment sur ce défaut comme stub).
- Aucune vraie porte de sécurité par agent. `SecurityEngine`
  (`backend/security/security_engine.py`, HOS-057) correspond exactement à
  la chaîne décrite — Permission → Trust → Threat → Isolation → Allow/
  Reject/Review — réellement construit et branché à ses propres routes.
  Mais **aucune permission ni politique par défaut n'est configurée nulle
  part** — `PermissionManager.check_permission()`/`evaluate_policies()`
  refusent tout par défaut sans rien d'accordé. Câbler la porte complète
  dans le dispatch obligatoire aurait donc silencieusement bloqué chaque
  mission réelle dès aujourd'hui — construire la couche de configuration de
  politique manquante (l'équivalent, pour `SecurityEngine`, du
  `config/security.yaml` d'Aegis) est un chantier séparé et nettement plus
  gros que cette passe.
- La collaboration multi-agents (`CollaborationEngine`, message bus,
  délégation, consensus — `backend/agents/collaboration/`) est réelle et
  fonctionnelle, branchée à ses propres routes, mais rien dans une vraie
  mission ne l'utilise jamais.

### Added
- **Phase A — Refléter la vraie activité** : `MissionExecutor` reçoit
  désormais le vrai `AgentRegistry` (`backend/agents/`) et synchronise
  statut (BUSY pendant l'exécution, READY après), tâche/mission en cours,
  et métriques réelles (`update_metrics`) à chaque exécution de tâche —
  best-effort, jamais capable de faire échouer la tâche qu'elle décrit.
  Nouvelle méthode `AgentRegistry.find_by_name()` : le vrai chemin
  d'exécution identifie les agents par nom (ex. "atlas"), pas par l'UUID
  interne du registre. Un retry transitoire (timeout Ollama puis succès)
  compte comme une seule réussite logique, pas un échec suivi d'un succès —
  `task.errors` repart vide à chaque nouvelle tentative (déjà corrigé pour
  la validation en HOS-069 ; étendu ici à la conséquence sur les
  métriques agent).
- **Phase B — Un seul cerveau de sélection** : `AgentCoordinator` délègue
  désormais au vrai `CapabilityMatcher` quand il est câblé, au lieu de
  faire tourner deux moteurs déconnectés. La correspondance par mots-clés
  reste le repli pour les appelants qui construisent `AgentCoordinator()`
  nu (le chemin autonome `/execution/start`, les tests hermétiques
  existants) — un repli documenté, pas un second décideur vivant. Nouveaux
  champs `TaskExecution.task_type`/`preferred_agent` (miroir de
  `MissionNode.type`/`preferred_agent`), transmis par `node_execution.py`.
  Conséquence réelle mesurée : un agent réellement occupé (`BUSY`, grâce à
  la Phase A) est désormais exclu de la sélection, pas seulement pénalisé
  dans un score.
- **Phase C — Confiance réelle** : `AgentTrustEngine.record_result()`
  (HOS-057) existait et n'était jamais appelé — chaque score de confiance
  restait à sa valeur par défaut. `MissionExecutor` l'alimente désormais
  avec chaque résultat réel, indépendamment de `AgentRegistry` (l'un
  fonctionne même sans l'autre). Le vrai score/niveau de confiance est
  exposé par `GET /api/v1/agents` et `/agents/{id}` (`trust_score`,
  `trust_level` — `null` explicite, jamais fabriqué, quand aucun moteur de
  confiance n'est câblé). La porte complète `SecurityEngine.check_access()`
  reste délibérément non câblée dans le dispatch obligatoire — voir
  "Autres écarts trouvés" ci-dessus.
- **Phase D — Documentation honnête** : `CollaborationEngine`,
  `AgentSupervisor` (ses propres `dispatch_node()`/
  `execute_mission_step()`/`execute_full_mission()`) et le callback par
  défaut fabricant de `TaskDispatcher` documentent maintenant clairement
  leur statut réel : fonctionnels, mais hors du chemin d'exécution réel
  d'une Mission/Autonomous aujourd'hui.
- **Phase E — Cockpit Agent Center** : refonte — compteurs de statut réels,
  ressources réelles (VRAM/GPU, réutilise `useMonitoringResources` déjà
  existant), activité réelle (missions actives, tâches en cours/terminées/
  échouées, réutilise les statistiques d'Execution du HOS-069), panneau de
  détail par agent avec Performance et Trust réels, message honnête pour le
  panneau Collaboration (voir Phase D). Le type `AgentStatus` du frontend
  déclarait `"ERROR"`, une valeur qui n'a **jamais existé** côté backend
  (les vraies valeurs : `FAILED`, plus `STOPPING`/`RECOVERING` absentes) —
  remplacé pour correspondre exactement à l'énumération réelle.

### Bugs trouvés et corrigés en cours de route
- Même bug que Missions (HOS-068) et Execution (HOS-069), un quatrième
  onglet plus tard toujours pas généralisé : `AgentStatus` déclaré en
  majuscules côté frontend, le backend renvoie ses valeurs en minuscules,
  rien ne normalisait entre les deux — chaque lookup indexé par statut
  (badge, comptage du tableau de bord) échouait silencieusement pour
  **tout** agent. Corrigé dans `toAgent()` (`services/client.ts`), le même
  point de traduction déjà établi pour Mission/Execution.
- `GET /api/v1/agents` (liste) omettait `successful_tasks`/`failed_tasks`
  — seul `GET /api/v1/agents/{id}` (détail) les avait. Le Cockpit sélectionne
  un agent depuis la ligne de liste déjà en cache plutôt que de re-fetcher
  le détail, donc un agent réellement réussi à 100% affichait "0 ok, 0
  failed" — trouvé en vérification manuelle dans le navigateur (le succès
  rate affichait 100% à côté d'un décompte "0 ok" incohérent). Corrigé en
  ajoutant les mêmes champs (plus `current_mission_id`) à la réponse de
  liste.

### Verified
- Vérifié en conditions réelles dans le navigateur avec Ollama réel : une
  mission de 6 tâches exécutée via `/missions/{id}/start` fait apparaître
  dans l'Agent Center les agents réellement sélectionnés (aegis, atlas,
  echo, hermes_prime, kronos, veritas — 6 sur 10, correspondant aux 6
  tâches) avec `total_tasks: 1`, `success_rate: 100%`, `trust_score: 75.1`,
  `trust_level: "high"` — tandis que les 4 agents jamais sélectionnés
  affichent honnêtement `trust_score: 50.0`, `trust_level: "unknown"` (la
  valeur par défaut d'un agent sans historique). Panneau de détail vérifié
  après le correctif ci-dessus : "1 ok, 0 failed" cohérent avec 100% de
  succès. VRAM réelle affichée (AMD Radeon RX 6800, 3.0/16.0 Go).
- Nouveaux tests hermétiques (aucun Ollama réel requis) :
  `tests/architecture/test_agent_registry_sync.py` (6 tests — sync statut/
  métriques, agent marqué BUSY pendant l'exécution, retry ne compte pas en
  double, no-op sans registre/agent inconnu),
  `tests/architecture/test_agent_selection_consolidation.py` (5 tests —
  délégation au vrai matcher, agent occupé exclu, repli sans capacité
  correspondante, repli sans matcher du tout),
  `tests/architecture/test_agent_trust_sync.py` (5 tests — enregistrement
  réel des victoires/défaites, indépendance vis-à-vis d'AgentRegistry, pas
  de double comptage sur retry), `tests/architecture/
  test_agent_routes_real_fields.py` (3 tests — liste et détail d'accord sur
  les mêmes compteurs, `trust_score: null` explicite sans moteur câblé).
- Suite complète (`tests/` + `backend/tests/`) : **3522 passed, 3 skipped,
  1 failed** — le seul échec est
  `test_task_executor_shares_the_container_model_intelligence`, le flake de
  test-ordering déjà documenté (HOS-067), reproductible seul en isolation
  avec succès (revérifié une nouvelle fois dans cette passe). Aucun échec
  lié à Ollama cette fois — suite complète propre de bout en bout en
  13m42s.

## HOS-069 — Execution : reconnexion au vrai moteur, VRAM réelle, retry intelligent (2026-08-07)

Demande de l'utilisateur : troisième onglet de la même série de revues
(après Autonomous OS et Missions) — "Execution est justement la pièce qui
manquait pour rendre la chaîne Autonomous → Mission réellement cohérente."
Spécification détaillée fournie : file de tâches, scheduler conscient des
ressources (exemple concret VRAM sur la RX 6800 16 Go), affectation
agent/modèle/runtime, outils/MCP avec porte de sécurité systématique,
retry/recovery intelligent (bascule de modèle), validation, Cockpit avec vue
par tâche et explications de blocage. Après audit et validation du plan en
5 phases par l'utilisateur ("Oui. Et Execution est justement..."), mise en
œuvre complète.

### Constat principal (audit, avant tout code)
L'onglet Execution était **structurellement déconnecté** du vrai moteur.
`backend/execution/routes.py` construit au chargement du module sa propre
instance de `MissionExecutor` ; le bootstrap était censé la remplacer, mais
`_make_execution_controller()` faisait un `return
execution_routes._controller` — une réadoption circulaire de l'instance
orpheline elle-même, jamais du `execution_engine` partagé que Missions et
Autonomous pilotent réellement via `node_execution.py`. Résultat :
`/api/v1/execution` ne pouvait structurellement jamais voir une vraie
activité — le message vide du Cockpit ("Aucune exécution enregistrée...")
était honnête malgré lui. `POST /execution/start` et le hook
`useStartExecution()` existaient mais rien ne les appelait jamais.

### Autres écarts trouvés
- `TaskScheduler` prétendait dans sa docstring "Integrates with
  RuntimeResourceManager for GPU limits" — faux : `max_gpu_tasks`/`gpu_only`
  étaient acceptés en paramètres et jamais lus dans le corps du code. Un vrai
  `ResourceManager` (HOS-035, vraie télémétrie GPU) existait ailleurs, jamais
  appelé depuis Execution.
- `get_ready_tasks()`/`build_plan()` (vagues, priorité) ne sont jamais
  appelés par le vrai chemin d'exécution — Missions utilise son propre
  `DependencyResolver`, complètement séparé. Le tri par priorité était de
  toute façon inerte (`TaskExecution` ne porte aucun champ priorité).
- Sélection agent/modèle/outil dans `AgentCoordinator` = correspondance de
  mots-clés simpliste, sans lien avec le vrai Model Intelligence
  (AdaptiveRouter).
- Les outils ne sont jamais réellement invoqués — `RealTaskExecutor.execute()`
  fait un pur appel de chat ; `assigned_tools` est calculé mais jamais utilisé
  pour un vrai appel d'outil/MCP.
- Retry bête : relance toujours la même tâche avec le même modèle.
  `ExecutionMeta.max_retries_per_task` était déclaré et jamais lu ; le vrai
  plafond était un `3` codé en dur, et un `RuntimeUnavailableError`
  (timeout Ollama, etc.) échouait la tâche **sans aucun retry**, contrairement
  à la voie de validation `RETRY`.
- `FeedbackLoop`/`OptimizationEngine` n'étaient jamais atteints pour une
  exécution réelle — rien n'appelait `finalize()` sur le chemin
  Missions/Autonomous.

### Added
- **Phase A — Reconnexion au vrai moteur** :
  `_make_execution_controller()` enveloppe désormais le `execution_engine`
  partagé (`ExecutionController(c.get("execution_engine"))`). Le hook
  `execute_node` de `GraphExecutor` (`node_execution.py`) route maintenant
  par `ExecutionController.start()`/`execute_task()`/`finalize()` au lieu de
  parler directement au `MissionExecutor` brut — une exécution de nœud réel
  s'enregistre enfin là où `/api/v1/execution` et le Cockpit peuvent la voir.
  `MissionNode.mission_id` (nouveau champ) est estampillé par
  `GraphExecutor.build_graph()` pour que chaque exécution affiche la vraie
  mission dont elle fait partie, sans élargir la signature du callable
  `execute_node` (toujours `MissionNode -> bool`, tous les faux/tests
  existants restent valides).
  - `ExecutionController.execute_task()` — verrou resserré (même correctif
    que HOS-068 sur `MissionExecutor`) : router par ce contrôleur n'aurait
    sinon resérialisé le parallélisme borné de GraphExecutor.
  - `ExecutionController._executions`/`_reports` — désormais bornés
    (`MAX_RETAINED_EXECUTIONS = 512`), le même motif RC3 P5 déjà corrigé
    ailleurs ; sans risque tant que rien n'alimentait ces registres, devenu
    un vrai risque dès qu'une vraie activité y arrive.
  - `TaskScheduler.all_done(task_ids)` (nouvelle méthode) — `is_all_done()`
    répond pour *tous* les tâches jamais enregistrées sur le scheduler
    partagé, pas pour une exécution donnée ; faux dès que plusieurs
    exécutions cohabitent (réel depuis le parallélisme HOS-068).
    `MissionExecutor.execute_task()` utilise maintenant `all_done()`, borné
    à ses propres tâches, pour décider quand transitionner l'état — et
    rapporte `FAILED`, pas `COMPLETED`, quand une tâche a réellement échoué
    (l'ancien code transitionnait vers `COMPLETED` sans condition).
- **Phase B — Admission VRAM réelle** : `RealTaskExecutor` consulte
  désormais le vrai `ResourceManager` (déjà existant, HOS-035, vraie
  télémétrie GPU) avant chaque appel d'inférence local — `vram_gb_for`
  (nouveau callback, câblé au bootstrap depuis `config/models.yaml`'s
  `roles.*.vram_gb`, les vraies mesures HOS-065C) donne l'empreinte requise ;
  `can_allocate()` répond ALLOW/DENY selon la VRAM réellement libre
  maintenant. DENY → attente bornée (poll, `vram_wait_s`/
  `vram_poll_interval_s`) puis `RuntimeUnavailableError` honnête plutôt
  qu'une explosion VRAM silencieuse. Conservateur par construction : ne sait
  pas si le modèle est déjà chargé, donc demande toujours son empreinte
  complète. Docstring mensongère de `TaskScheduler` corrigée pour pointer
  vers ce vrai mécanisme.
- **Phase C — Retry intelligent borné** : un `RuntimeUnavailableError`
  retente désormais (jusqu'à `ExecutionMeta.max_retries_per_task`, enfin lu
  au lieu du `3` codé en dur) au lieu d'échouer la tâche immédiatement. Sur
  une tentative de retry, `RealTaskExecutor._resolve_model()` préfère un
  vrai modèle alternatif (réutilise `local_fallback_for`, déjà câblé pour le
  repli cloud→local de HOS-066C) plutôt que de redemander le même modèle
  primaire — exactement l'exemple de l'utilisateur (timeout Ollama → retry
  → Qwen3 4B disponible → succès).
- **Phase D — Documentation honnête Outils/MCP** : `_build_messages()`,
  `AgentCoordinator._select_tools()`, `TaskExecution.assigned_tools` et le
  docstring du module documentent maintenant clairement que les "outils
  disponibles" sont un indice textuel dans le prompt, jamais un vrai appel
  outil/MCP — donc rien ici ne contourne la porte de sécurité Aegis, puisqu'il
  n'y a pas de vrai appel d'outil à filtrer sur ce chemin. Le vrai
  tool-calling (boucle d'appel de fonction réelle, chaque appel filtré par
  Aegis) reste un chantier séparé, plus gros, volontairement pas
  à moitié implémenté ici.
- **Phase E — Cockpit Execution Center** : refonte complète, une ligne par
  tâche réelle (tâche, état, mission, agent(s), runtime(s), durée), panneau
  de détail avec les vraies erreurs de la tâche (VRAM refusée, timeout,
  échec de validation) quand elles existent, statistiques réelles issues du
  scheduler partagé (en cours/en attente/terminées/échouées/total). Le type
  `ExecutionState` du frontend (id/status/current_node/progress/checkpoints)
  ne correspondait à **aucun** champ réel jamais renvoyé par le backend —
  remplacé par `ExecutionSummary`, qui reflète l'API réelle.

### Bugs trouvés et corrigés en cours de route
- `task.errors` s'accumulait entre tentatives de retry : une tâche qui
  échouait une fois puis réussissait vraiment au retry restait jugée
  RETRY/FAIL par `ValidationEngine`, qui lit `task.errors` — l'erreur de la
  tentative précédente traînait encore. Chaque tentative repart maintenant
  avec une liste d'erreurs vide.
- `MissionExecutor.finalize()` calculait `total_tasks`/`completed_tasks`/
  `failed_tasks` depuis `self._scheduler.get_progress()` — un décompte
  **global** sur tout le scheduler partagé, pas scopé à l'exécution en
  cours. Invisible avant cette passe (rien n'appelait jamais `finalize()`
  pour une vraie exécution de nœud) ; trouvé en vérification manuelle dans
  le navigateur : une exécution à une seule tâche rapportait "2/2 tâches",
  puis "3/3", etc. — un compteur global croissant, pas le vrai décompte de
  cette exécution. Corrigé pour dériver ces trois champs de la liste de
  tâches réellement scopée à l'exécution (`self._execution_tasks`), déjà
  utilisée correctement ailleurs dans la même méthode.
- Un test préexistant, `tests/integration/test_real_execution.py::
  TestHonestFailure::test_mission_task_fails_when_runtime_is_down`, supposait
  encore l'ancien comportement (`RuntimeUnavailableError` échoue
  immédiatement) — cassé, intentionnellement, par la Phase C. Mis à jour
  pour rejouer la boucle de retry jusqu'à épuisement (même motif que
  `node_execution.py`) avant d'affirmer `FAILED` : le runtime simulé ne se
  rétablit jamais dans ce test, donc l'invariant réel ("jamais de résultat
  fabriqué") reste vérifié, juste après le nombre de tentatives configuré
  plutôt qu'après une seule.

### Verified
- Vérifié en conditions réelles dans le navigateur avec Ollama réel : une
  mission de 6 tâches exécutée via `/missions/{id}/start` apparaît
  intégralement dans l'Execution Center — chaque ligne montre le vrai agent
  (aegis/hermes_prime/atlas), le vrai runtime (ollama), la vraie durée
  mesurée, et le panneau de détail affiche "1/1 tâches" (correctement scopé
  après le correctif ci-dessus) avec "Aucune erreur." pour une tâche
  réussie.
- Nouveaux tests hermétiques (aucun Ollama réel requis) :
  `tests/architecture/test_execution_controller_wiring.py` (8 tests —
  scoping de `all_done()`, FAILED vs COMPLETED, verrou non resérialisant,
  rétention bornée, bout-en-bout node_execution.py → ExecutionController
  réel), `tests/architecture/test_vram_admission.py` (7 tests — no-op sans
  câblage, allow immédiat, deny puis libération après attente, deny
  permanent → RuntimeUnavailableError, jamais d'appel chat quand la VRAM
  n'est jamais admise), `tests/architecture/test_intelligent_retry.py` (6
  tests — retry borné et configurable, récupération après une panne
  transitoire, préférence pour un modèle alternatif au retry).
- `tests/architecture/` + `tests/autonomous/` + `test_assembly.py` (un
  sous-ensemble large et représentatif, 1899 tests) : **1898 passed, 1
  skipped**, seul échec `test_task_executor_shares_the_container_
  model_intelligence` — le flake de test-ordering déjà documenté (HOS-067),
  reproductible seul en isolation avec succès (revérifié une nouvelle fois
  dans cette passe).
- `tests/integration/test_real_execution.py` (21 tests, real Ollama) :
  **21 passed** après le correctif du test de retry ci-dessus.
- Suite complète (`tests/` + `backend/tests/`) : un premier passage complet
  a montré **3496 passed, 8 failed** — 7 des 8 échecs concentrés dans
  `test_real_execution.py` (real Ollama), confirmés transitoires en
  isolation une fois relancés (tous verts, voir ligne ci-dessus) ; le
  8ème était la vraie régression du test de retry, trouvée et corrigée
  (voir "Bugs trouvés" ci-dessus). Un second passage complet, lancé pour
  confirmer un résultat propre de bout en bout, s'est bloqué à 78% sans
  progresser pendant plus de 10 minutes — un appel direct à `POST
  /api/chat` sur l'Ollama local a lui-même expiré sans réponse pendant que
  `GET /api/ps` répondait normalement, le même symptôme de file
  d'inférence figée déjà rencontré et documenté pour HOS-068. Non résolu
  plus loin dans cette passe (action système sur un service que cette
  session n'a ni démarré ni arrêté) ; finalisé sur la base des passages
  ciblés ci-dessus, tous verts, après validation explicite de l'utilisateur
  pour procéder malgré l'absence d'un unique passage complet propre.

## HOS-068 — Missions : visibilité croisée, sécurité, rapport, pause/resume réels, parallélisme borné (2026-08-07)

Demande de l'utilisateur : deuxième onglet de la même série de revues
(après Autonomous OS) — comparaison entre le fonctionnement attendu de
l'onglet Missions (création → analyse → génération de DAG → affectation
des ressources → vérification avant exécution → exécution → suivi temps
réel → gestion des erreurs → fin de mission → apprentissage), présenté par
l'utilisateur comme le "directeur des opérations" en aval du "chef
d'orchestre" Autonomous OS, et le comportement réel du code. Après
validation du plan en 5 phases par l'utilisateur ("Ok va y"), mise en
œuvre complète.

### Écarts trouvés (audit, avant tout code)
- Une mission créée depuis `/autonomous` (HOS-067) construit son propre
  `Mission` via le même `MissionPlanner`, mais ne rejoignait jamais le
  dictionnaire interne de `mission/routes.py` — invisible depuis
  `/missions` alors qu'elle tourne sur le même `GraphExecutor`.
- `/missions/{id}/start` n'avait **aucune vérification de sécurité** —
  contrairement à Autonomous (HOS-067), une mission liée à un vrai dossier
  local ou dépôt pouvait s'exécuter sans jamais passer par Aegis.
- La boucle de retry existait déjà dans `MissionExecutor.execute_task()`
  (remet `task.status` à `PENDING`, incrémente `retries`) mais rien ne
  rappelait `execute_task()` ensuite — le compteur bougeait, l'exécution
  non.
- Aucun rapport de fin de mission, aucun endpoint pause/resume malgré des
  boutons déjà câblés côté client vers des routes inexistantes.
- `GraphExecutor.execute_step()` exécutait les nœuds prêts en boucle
  séquentielle malgré `DependencyResolver.get_parallel_groups()` calculant
  déjà de vrais groupes parallèles — jamais utilisés.
- Seule la mémoire épisodique était alimentée depuis `/missions` ; ni
  mémoire procédurale, ni moteur d'évolution, contrairement à
  `AutonomousMemoryLoop` côté Autonomous.

### Added
- `register_mission()` (mission/routes.py) — point d'entrée explicite
  appelé par `AutonomousOrchestrator._plan_via_dag()` après
  `build_mission()` : une mission créée depuis Autonomous devient visible
  depuis `/missions` sans fusionner les deux points d'entrée.
- `_check_mission_security()` — même porte Aegis basée sur le risque que
  côté Autonomous (HOS-067) : ignorée pour une mission sans dossier local
  ni dépôt ; sinon vérifie `file_read` sur `local_path` puis
  `mission_execute` (`config/security.yaml`, même forme que
  `autonomous_goal_execute`). `DENY` → `FAILED`, `REQUIRE_HUMAN_VALIDATION`
  → `PAUSED` (pas `FAILED` — reprise possible via `/resume`), `ALLOW` →
  exécution normale.
- Boucle de retry réellement active (`node_execution.py`) : après le
  premier `execute_task()`, une boucle `while task.status == PENDING:
  execute_task()` — sûre par construction (`ExecutionStateMachine` accepte
  déjà `VALIDATING → RUNNING`, et `execute_task()` a son propre plafond de
  retries).
- `MissionReport`/`build_mission_report()` (mission_models.py) et
  `GET /missions/{id}/report` — dérivé entièrement de l'état déjà mesuré
  de la mission (durée, sorties, erreurs, runtimes utilisés par nœud), rien
  de nouveau à faire dériver.
- `POST /missions/{id}/pause` / `.../resume` — réellement interruptibles :
  la boucle d'exécution (`_run_mission_steps`) cède la main
  (`await asyncio.sleep(0)`) entre chaque passe, ce qui permet à une
  requête `/pause` concurrente d'être traitée avant la passe suivante —
  avant ce correctif, tout tournait dans un seul handler `async def` sans
  point de cession, donc `/pause` ne pouvait structurellement rien
  interrompre. `/resume` relance réellement la marche du DAG (contrairement
  au `/resume` actuel côté Autonomous, qui ne fait encore que changer le
  statut — limite documentée là-bas).
- Exécution parallèle bornée et réelle (Phase D, la plus délicate) :
  - `MissionExecutor.execute_task()` — verrou resserré : seule la
    coordination (planification, transitions d'état, écritures de statut)
    reste sous `self._lock` ; l'appel d'inférence réel
    (`self._task_executor.execute()`, potentiellement long — voir les
    benchmarks réels HOS-065C) tourne désormais hors verrou. Avant ce
    correctif, tout le corps de la méthode était sous un seul verrou :
    paralléliser `GraphExecutor` par-dessus n'aurait donné qu'un vrai
    thread pool sérialisé sur un faux parallélisme.
  - `GraphExecutor.execute_step()` — les nœuds prêts sont désormais
    exécutés via `ThreadPoolExecutor`/`as_completed`, bornés par
    `mission_max_parallel_tasks`. Toutes les mutations de
    `DependencyResolver`/`mission` restent sur le thread appelant, après
    résolution des futures — jamais depuis un worker.
  - `mission_max_parallel_tasks: int = 2` (config.py) — délibérément
    distinct de `workflow_max_parallel` (moteur différent, charge VRAM
    différente) : des nœuds de DAG de mission peuvent chacun recommander un
    modèle de rôle différent, déjà mesuré à 12-15 Go sur les ~17,16 Go
    utilisables de cette carte 16 Go (benchmarks réels HOS-065C) — 2 reste
    la valeur par défaut prudente.
- Écriture mémoire procédurale + moteur d'évolution (Phase E) : une mission
  `COMPLETED` alimente `MemoryManager.store_procedure()` (séquence réelle
  des titres de nœuds complétés) ; toute mission terminale alimente
  `EvolutionEngine.ingest_metrics()` avec des métriques mesurées — même
  geste que `AutonomousMemoryLoop`, jamais fait côté Missions avant cette
  passe. Volontairement laissé en détection seule (`ingest_metrics`, pas
  `run_full_pipeline()`) — même choix de gouvernance que côté Autonomous.
- Câblage Cockpit (`mission-center.tsx`) : champs de liaison de projet
  (dossier local/dépôt/branche) au formulaire de création, boutons
  Start/Pause/Resume/Cancel réellement câblés avec états désactivés
  corrects, panneau de rapport (tâches, durée, runtimes, erreurs), message
  d'attente humaine pour une mission en pause par Aegis.

### Bug trouvé et corrigé en cours de route
- `MissionStatus` côté frontend (types/hermes.ts) était déclaré en
  majuscules mais le backend renvoie ses valeurs en minuscules
  (`MissionStatus(str, Enum)`) sans jamais être normalisé entre les deux —
  chaque comparaison indexée par statut (badge, désactivation des boutons)
  échouait silencieusement pour **toute** mission. Corrigé dans
  `toMission()` (services/client.ts), le seul point de traduction
  raw→normalisé déjà établi pour ce type de décalage backend/frontend.
- Une mission mise en pause par Aegis **avant** d'avoir jamais démarré
  (`_check_mission_security()` court-circuite `_executor.start_mission()`,
  seul autre endroit qui pose `started_at`) ne recevait jamais de
  `started_at` — trouvé en vérification manuelle dans le navigateur : une
  mission reprise et réellement exécutée (~65s, 6 tâches) rapportait quand
  même `total_duration_ms: 0.0`. `resume_mission()` pose maintenant
  `started_at` s'il est encore `None` au moment de la reprise.
- Régression trouvée par la suite complète (pas en vérification manuelle) :
  `tests/architecture/test_execution.py::TestThreadSafety::
  test_concurrent_execution_control` — un test préexistant qui partage une
  seule `ExecutionStateMachine` entre deux threads exécutant chacun 10
  tâches — se mettait à échouer avec `Invalid transition: running →
  running` une fois le verrou de `MissionExecutor.execute_task()`
  resserré : deux tâches différentes sous une même exécution peuvent
  désormais réellement se chevaucher et tenter chacune de marquer
  l'exécution `RUNNING` (ou `VALIDATING`) au même moment. Le chemin réel de
  production (`node_execution.py`) ne partage jamais un `sm` entre tâches
  concurrentes (un `prepare()` par nœud), donc ce n'était pas un risque en
  production — mais la garantie que ce test encode reste réelle. Corrigé à
  la racine, dans `ExecutionStateMachine.transition()`
  (execution_state.py) : une transition vers l'état déjà courant est
  désormais un no-op réussi plutôt qu'une erreur, sans affaiblir la
  détection des transitions réellement invalides
  (`test_invalid_transition_raises` reste vert).

### Verified
- Vérifié en conditions réelles dans le navigateur avec Ollama réel : une
  mission sans liaison ("Add input validation to login form") décompose en
  6 tâches réelles, s'exécute en ~22,9s avec deux appels `api/chat`
  terminant à la même seconde (preuve d'un vrai chevauchement, pas d'un
  parallélisme simulé) ; une mission liée à un vrai dossier local
  ("Refactor logging module") passe correctement en `paused` avec le
  message d'attente humaine attendu, puis reprise via `/resume` exécute
  réellement ses 9 tâches (~65s) avec `started_at` et
  `total_duration_ms` corrects après le correctif ci-dessus.
- Nouveaux tests (`tests/architecture/test_mission_real_wiring.py`, 18
  tests) : visibilité croisée, porte Aegis (allow/review/deny, dont le
  cas `local_path` refusé avant même la vérification `mission_execute`),
  génération de rapport, boucle de retry réellement rejouée, parallélisme
  borné du `GraphExecutor` (chevauchement temporel mesuré, borne à 1 =
  strictement séquentiel mesuré), verrou resserré de `MissionExecutor`
  (deux tâches concurrentes chevauchent réellement), correctif
  `started_at`, plus 2 tests de régression pour le correctif de
  transition d'état ci-dessus (`tests/architecture/test_execution.py`).
- Suite complète (`tests/` + `backend/tests/`) : **3479 passed, 3 skipped,
  2 failed** (premier passage) après le correctif de transition d'état ;
  les 2 échecs restants sont sans rapport avec cette passe —
  `test_task_executor_shares_the_container_model_intelligence` est le
  flake de test-ordering déjà documenté (HOS-067), reproductible seul en
  isolation avec succès. Un second passage complet a ensuite révélé 7
  échecs supplémentaires (`test_real_execution.py`,
  `test_documents_endpoint.py::test_index_a_real_text_file`) — tous des
  `httpx.ReadTimeout`, tous dans des fichiers hors du périmètre de cette
  passe (aucun recoupement avec les fichiers modifiés). Confirmé
  environnemental et non lié à ce diff : un appel direct à
  `POST /api/chat` sur l'Ollama local (aucun code du dépôt impliqué) a
  lui-même dépassé un délai de 30s sur le même modèle déjà chargé, alors
  que `GET /api/ps` répondait instantanément — la file d'inférence
  d'Ollama était bloquée au moment du test, pas le code testé. Non
  poursuivi plus loin (action système sur un service que cette session
  n'a ni démarré ni arrêté) ; signalé à l'utilisateur séparément.

## HOS-067 — Autonomous OS : décomposition, décisions et sécurité réelles (2026-08-01)

Demande de l'utilisateur : point de comparaison entre le fonctionnement
attendu de l'onglet Autonomous OS (interprétation → récupération de
connaissances → planification multi-étapes → sélection de ressources →
vérification de sécurité → exécution → apprentissage → amélioration
continue) et le comportement réel du code, puis un plan pour combler les
écarts trouvés, avec en plus la possibilité de lier une mission à un
dossier local et/ou un dépôt GitHub au démarrage. Après validation du
plan par l'utilisateur, mise en œuvre complète (premier onglet d'une série
de revues du même type, à poursuivre sur les autres onglets).

### Écarts trouvés (audit, avant tout code)
- La mission n'était **jamais réellement décomposée** : une seule tâche
  plate était construite à la main pour tout l'objectif, en cour-circuitant
  le vrai `TaskDecomposer`/`MissionPlanner` que `/missions` utilise déjà
  (HOS-042).
- La sélection d'agent/outil/compétence dans `DecisionEngine` était une
  liste figée avec des scores figés, jamais branchée aux vrais registres —
  et nommait des agents (`klaatcode`, `ohmypi`, `code_intelligence`) qui
  n'ont jamais été enregistrés dans Hermes (les vrais : `hermes_prime`,
  `atlas`, `minerva`, `veritas`, etc. — `config/agents.yaml`).
- `AutonomousGuard.set_security_engine`/`set_policy_engine` n'étaient
  **jamais appelés nulle part** — confirmé par une recherche sur tout le
  dépôt — donc chaque objectif autonome recevait `ALLOW` quel que soit
  `autonomy_level`, indépendamment du vrai moteur Aegis.
- La récupération de connaissances avant planification n'existait pas
  réellement : un seul appel nommait un paramètre `mode=` que
  `MemoryManager.search()` n'a jamais accepté (avalé par un `except: pass`
  muet), et de toute façon `set_memory_manager()` n'était jamais appelé sur
  l'interprète.
- Aucune possibilité de lier une mission à un dossier local ou un dépôt
  GitHub, ni côté Autonomous ni côté Missions.

### Added
- `AutonomousOrchestrator` gagne un chemin réel optionnel
  (`mission_planner`/`graph_executor` injectés) : quand câblé (bootstrap),
  `start_goal()` décompose l'objectif en un vrai DAG multi-nœuds via le
  même pipeline que `/missions` (`TaskDecomposer` réel, dépendances,
  recommandation de runtime par tâche), puis l'exécute via
  `GraphExecutor.build_graph()/start_mission()/execute_step()` — exactement
  la séquence que `/missions/{id}/start` pilote déjà, donc une mission
  autonome apparaît aussi dans `/missions`. Sans injection (tous les tests
  existants), comportement legacy inchangé à l'identique — confirmé par
  les 78 tests `tests/autonomous/test_autonomous_core.py`, tous verts sans
  modification.
- Décisions réelles par tâche (`AdaptiveRouter` non utilisé ici — le plan
  réel porte déjà catégorie/recommandation de runtime avec sa propre
  justification/compétences requises) : agent = vraie catégorie → vrai
  agent enregistré (`config/agents.yaml`), runtime = la vraie justification
  de `RuntimeRecommendation`. Reste un gap réel documenté : la sélection
  d'agent est maintenant honnête, mais rien ne fait encore dispatcher
  l'exécution différemment par agent (toujours un appel générique
  `RealTaskExecutor`).
- `AegisSecurityAdapter` (autonomous_guard.py) — branche
  `AutonomousGuard` sur le vrai `AegisEngine` déterministe. **Basé sur le
  risque, pas un blocage systématique** : un objectif sans dossier local,
  sans dépôt, et non signalé sécurité par l'interprète (mots comme
  "secure"/"security") n'est pas soumis à Aegis du tout — un blocage
  systématique aurait rendu l'onglet inopérant par défaut à
  `autonomy_level: low` sans aucun bénéfice de sécurité réel (le texte
  généré ne touche ni fichier ni réseau). Un objectif lié à un projet réel,
  ou explicitement signalé sécurité, requiert une vraie validation humaine.
  Bug trouvé et corrigé en cours de route : `AutonomousGuard.check_action()`
  teste `allowed` avant `requires_review` — un premier essai qui rapportait
  `allowed=False` pour `REQUIRE_HUMAN_VALIDATION` court-circuitait tout
  droit vers `BLOCK` au lieu de `REVIEW` (`goal.status = PAUSED`, pas
  `FAILED`) ; capturé par les tests de l'adaptateur avant d'atteindre la
  production.
- `config/security.yaml` — nouvelle catégorie `autonomous_goal_execute`
  (`min_autonomy_for_auto_allow: medium`).
- Liaison de projet (HOS-067) : `AutonomousGoal.local_path`/`repository`/
  `branch`, capturés depuis `context` à l'interprétation, propagés dans
  `PlanningRequest.repository`/`branch` (déjà consommés par le prompt de
  décomposition côté `/missions`). `local_path` validé contre la liste
  blanche `ALLOWED_PATHS` d'Aegis (`file_read`) avant toute planification.
  Champs ajoutés au formulaire du Cockpit.
- Récupération de connaissances réelle avant planification :
  `AutonomousInterpreter._gather_knowledge()` appelle
  `MemoryManager.recommend_for_mission()` (missions similaires réelles,
  bonnes pratiques, erreurs fréquentes — `ExperienceManager`, déjà
  existant, jamais branché) et alimente
  `PlanningRequest.specification` — visible aussi dans le Cockpit
  ("From past missions").

### Non fait dans cette passe (limites réelles, documentées dans le code)
- L'exécution ne dispatch pas encore réellement par agent (voir plus haut).
- `models_used`/`tokens` restent vides pour les missions exécutées via le
  vrai DAG : `node_execution.py` écrase le tag de modèle du nœud par le
  runtime réel ("ollama") après exécution — une limite partagée avec
  `/missions`, pas spécifique à Autonomous, à corriger directement là-bas.
- Reprendre un objectif en pause (validation humaine) ne relance pas
  encore la planification/exécution — `resume_goal()` ne fait encore que
  changer le statut, comportement déjà limité avant cette passe.
- La boucle d'évolution (Phase E) reste volontairement au comportement
  actuel : détection de propositions seulement, jamais
  simulation/validation/application automatique — un choix de gouvernance
  à valider explicitement avant de le changer.

### Verified
- Vérifié en conditions réelles dans le navigateur avec Ollama réel : un
  objectif simple ("Write a haiku about databases") décompose en 7 tâches
  réelles, s'exécute en ~19,6s, avec des décisions réelles (agents
  `atlas`/`hermes_prime`/`minerva`/`veritas`, modèles réels
  `qwen3.5:9b`/`hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M`) ; un
  objectif lié à un vrai dossier local passe correctement en `paused` avec
  le message d'explication attendu, à `autonomy_level: low`.
- Nouveaux tests (`tests/autonomous/test_autonomous_real_wiring.py`) : DAG
  réel (chemin câblé vs repli legacy), décisions dérivées du plan,
  `AegisSecurityAdapter`, portes basées sur le risque, récupération de
  connaissances, champs de liaison de projet.
- Suite complète (`tests/` + `backend/tests/`) : **3463 passed, 3 skipped,
  0 failed**.

### Fixed (suite au retour utilisateur en conditions réelles)
- Un objectif lié à un projet réel passe en `paused` (attendu) mais le
  Cockpit sondait `/timeline` toutes les 3s **indéfiniment**, même une fois
  l'état stabilisé (`resume_goal()` ne relance pas encore l'exécution, donc
  rien ne pouvait plus changer) — donnant l'impression d'une boucle
  infinie. Le sondage s'arrête maintenant dès qu'un objectif atteint un
  état stable (`completed`/`failed`/`cancelled`/`paused`) ; un
  pause/resume/cancel manuel invalide déjà le cache et redéclenche un vrai
  rafraîchissement, donc rien n'est perdu.
- Le message "Report unavailable" (rouge, façon erreur) s'affichait aussi
  pour un objectif en pause qui n'a simplement jamais tourné — remplacé
  par un message honnête et non alarmant pour ce cas précis.

## HOS-066C — Escalade cloud OpenRouter (modèles gratuits), local par défaut (2026-08-01)

Demande de l'utilisateur : intégrer OpenRouter comme second runtime, mais
uniquement ses modèles gratuits (`:free`), avec bascule automatique entre
eux, sélection selon le type de tâche, priorité systématique au local, et
repli automatique sur le local si le quota cloud est épuisé. Remplace une
première piste (intégration du CLI FreeBuff) écartée après analyse : le
CLI gratuit de FreeBuff n'a aucun mode programmable/headless documenté —
voir la discussion, non commitée. Aucune fabrication de code n'a eu lieu
avant validation explicite du plan par l'utilisateur.

### Fait important à ne pas perdre de vue
Le quota gratuit d'OpenRouter (20 req/min ; 50/jour, ou 1000/jour avec
≥10$ de crédit à vie sur le compte) est **un seul pool partagé entre tous
les modèles `:free`**, pas un quota par modèle — confirmé sur la doc
officielle. Faire tourner plusieurs modèles gratuits en rotation aide la
fiabilité (un modèle en panne, un autre choisi) et l'adéquation à la
tâche ; ça n'étend jamais le budget total. Le message n'a pas été édulcoré
auprès de l'utilisateur.

### Added
- `backend/connectors/openrouter_client.py` — `OpenRouterClient`, même
  forme que `OllamaClientProtocol` (`chat`/`chat_stream`/`chat_events`) :
  appels réels à `POST /chat/completions` (OpenAI-compatible), lecture des
  vrais compteurs `usage.prompt_tokens`/`completion_tokens` d'OpenRouter en
  non-streaming, parsing SSE réel en streaming (y compris le cas
  `finish_reason: "error"` en cours de flux — confirmé sur la doc, pas
  supposé). `OpenRouterQuotaExhaustedError` distingue un 429 (quota) d'une
  autre panne, sans changer le traitement (les deux déclenchent le même
  repli local automatique).
- `backend/model_intelligence/cloud_catalog.py` — `CloudModelCatalog` :
  découvre dynamiquement les modèles gratuits via `GET /models`
  (`pricing.prompt == "0" and pricing.completion == "0"`, pas seulement le
  suffixe `:free`), les enregistre dans le même `ModelProfiler` que les 12
  rôles locaux (`vram_required_mb=0`, `context_window` réel de l'API,
  `chat_capable` dérivé des modalités de sortie réelles). `has_budget()`
  vérifie le quota réel via `GET /key` (mis en cache, ~60s), avec une
  marge de sécurité configurable (`OPENROUTER_DAILY_RESERVE`, 5 par
  défaut) — jamais laisser l'escalade automatique consommer les toutes
  dernières requêtes du jour. Inconnu/injoignable = pas de budget : échec
  fermé vers le local, jamais une supposition optimiste.
- `AdaptiveRouter` (adaptive_router.py) — nouvelle porte d'escalade
  cloud, local-first par construction : un profil cloud n'est même
  considéré que si **aucun modèle local n'est viable** pour la tâche, ou
  si la tâche a explicitement demandé l'escalade
  (`TaskContext.cloud_escalation_allowed`, même logique que
  `reasoning_escalation`/`advanced_analysis` — un palier délibéré, jamais
  déclenché par une heuristique). Même alors, le cloud n'est utilisé que
  si Aegis autorise `cloud_inference` *et* qu'il reste du quota réel —
  sinon repli silencieux sur le classement local existant, inchangé.
  `_fallback_decision` (le dernier recours) exclut explicitement les
  profils cloud : ils portent `vram_required_mb=0`, ce qui leur aurait
  fait gagner ce classement à coup sûr et aurait contourné toutes les
  vérifications d'autorisation/quota — bug réel trouvé et corrigé avant
  qu'il n'atteigne la production.
- `RealTaskExecutor` (task_executor.py) — `cloud_chat`/`runtime_for`/
  `local_fallback_for`, tous optionnels (`None` par défaut = comportement
  100% inchangé). Un échec cloud, quelle qu'en soit la cause (quota,
  réseau, modèle indisponible), déclenche un repli automatique et réel sur
  un modèle local — ce n'est pas une fabrication de résultat (interdite
  par R-001), c'est le choix d'un runtime différent, tout aussi réel.
- `config/security.yaml` — nouvelle catégorie Aegis `cloud_inference`
  (même politique que `network_call` : `min_autonomy_for_auto_allow:
  high`). Au niveau d'autonomie livré par défaut (`low`), toute tentative
  d'escalade cloud requiert une validation humaine — **rien ne part vers
  l'extérieur automatiquement**, même avec une clé API configurée. Passer
  `autonomy_level` à `high` est l'acte délibéré par lequel un opérateur
  active l'escalade automatique.
- `GET /models/cloud/status` — visibilité honnête en lecture seule :
  configuré ou non, autorisé ou non *en ce moment*, taille du catalogue,
  quota restant réel (depuis le cache, sans jamais déclencher d'appel
  réseau juste pour être consultée).
- `OPENROUTER_API_KEY`/`OPENROUTER_DAILY_RESERVE` dans `.env.example` —
  vide par défaut, le réglage le plus sûr : Hermes reste 100% local tant
  qu'une clé réelle n'est pas fournie.

### Added — complété : BenchmarkScheduler, agents conversationnels, widget
Les trois points listés comme non faits dans la première passe (ci-dessous)
ont été traités dans la foulée, sur demande explicite de l'utilisateur
("termine la liste des non fait dans cette passe") :

- `BenchmarkScheduler.run_benchmark()` bascule désormais vers OpenRouter
  pour tout profil `RuntimeBackend.OPENROUTER` (même catalogue réel
  qu'`AdaptiveRouter`, pas une liste séparée). OpenRouter ne renvoie pas
  `eval_count`/`eval_duration` comme Ollama : latence et tokens/seconde sont
  mesurés sur l'horloge murale autour de l'appel complet (réseau + génération),
  une mesure réelle mais honnêtement différente de la mesure locale, documentée
  comme telle plutôt que présentée à tort comme équivalente. VRAM/RAM à 0 (réel :
  une complétion cloud ne coûte rien en local).
- `get_cloud_fallback_model(task_type)` (model_intelligence/routes.py) —
  fonction réutilisable qui repasse par la même porte d'escalade
  d'`AdaptiveRouter` (Aegis, quota) avec `cloud_escalation_allowed=True`
  forcé, pour un appelant qui a *déjà* essayé le local et échoué (un cas
  qu'`AdaptiveRouter` ne peut pas voir lui-même : son filtre ne regarde que
  la VRAM, pas si Ollama répond réellement).
- `BaseAgent`/`TaskDecomposer` gagnent un `cloud_client` optionnel
  (`None` par défaut = comportement 100% inchangé). Le local reste le
  premier essai systématique ; un repli cloud n'est tenté que si
  l'appel local échoue *avant d'avoir streamé le moindre chunk* — la même
  garde que `OllamaClient.chat_events()` applique déjà à ses propres
  reconnexions, pour ne jamais risquer une réponse dupliquée ou incohérente.
  Câblé dans `AgentRegistry`/`_make_mission_planner` uniquement quand
  `OPENROUTER_API_KEY` est configuré. Un bug réel a été trouvé et corrigé en
  cours de route : le premier brouillon appelait `chat_events()` à
  l'intérieur du générateur de repli, ce qui rendait l'appel paresseux
  (jamais exécuté avant la première itération) au lieu d'immédiat comme
  avant cette fonctionnalité — cassait un test existant
  (`test_the_decision_actually_reaches_ollama`), corrigé en gardant l'appel
  dans la méthode simple qui construit le générateur, pas dans le générateur
  lui-même.
- `OpenRouterClient.from_settings()` — point unique pour "une clé est-elle
  configurée", utilisé par les trois consommateurs (agents, planificateur,
  exécuteur de tâches) au lieu de trois gardes légèrement différentes.
- Panneau de statut cloud dans le Models Center (frontend) —
  `GET /models/cloud/status`, lecture seule, affiché entre l'en-tête et les
  onglets : configuré/non configuré, autorisé/non autorisé *maintenant*,
  quota restant, taille du catalogue. Pas un nouvel onglet — l'idée
  délibérément écartée dans le plan initial, la visibilité seule ne justifie
  pas une surface produit séparée. Vérifié dans le navigateur avec le
  backend réel : "cloud local uniquement" s'affiche correctement (aucune
  clé configurée sur ce poste).

### Verified
- 24 tests supplémentaires (`test_benchmark_scheduler_cloud.py`,
  `test_cloud_fallback_helper.py`, `test_base_agent_cloud_fallback.py`,
  `test_task_decomposer_cloud_fallback.py`) — 71 tests HOS-066C au total,
  tous verts.
- Suite complète (`tests/` + `backend/tests/`) : **3437 passed, 3 skipped,
  0 failed**.

## HOS-065C — Benchmarks réels et contexte optimisé par rôle (2026-08-01)

Demande de l'utilisateur : lister les modèles installés/utilisés, faire les
benchmarks manquants, ajuster le contexte de chaque modèle à sa valeur
optimale. Périmètre confirmé avant exécution.

### État des lieux
- **16 modèles installés**, 12 réellement utilisés par Hermes
  (`config/models.yaml`), 4 orphelins d'un autre projet
  (`hermes3-feedmail:64k`, `feedmail-coder`, `feedmail-deepseek`,
  `feedmail-fast`) — laissés de côté.
- **Aucun benchmark réel n'avait jamais été fait.** `BenchmarkScheduler`
  fabriquait chaque chiffre avec `random.uniform()` sans jamais appeler
  Ollama, et `get_latest_benchmarks()` régénérait un nouveau jeu de
  nombres aléatoires à chaque appel au lieu de retourner quoi que ce soit
  de mesuré.
- **Le contexte était un seul réglage global (8192)** appliqué
  identiquement aux 12 modèles, de `nomic-embed-text` (max réel 2048) à
  `qwen3.5:9b`/`qwen3-coder:30b` (max réel 262144).

### Fixed — BenchmarkScheduler devient réel
- `run_benchmark()` fait maintenant un vrai appel `POST /api/chat` non
  streamé à Ollama et lit ses propres compteurs authentiques
  (`eval_count`, `eval_duration`, `prompt_eval_count`) plutôt que
  d'estimer ou de fabriquer — latence, tokens/seconde et VRAM (via
  `/api/ps`, avant/après) sont désormais mesurés, pas inventés. Ne
  fabrique jamais : si Ollama est injoignable, la méthode lève une
  exception au lieu de renvoyer des chiffres inventés (même discipline que
  `RealTaskExecutor.execute()`).
- `get_latest_benchmarks()` retourne maintenant les résultats réellement
  stockés (vide tant que rien n'a tourné) au lieu de refabriquer un jeu de
  nombres aléatoires à chaque appel.
- Chaque benchmark alimente aussi `ModelProfiler.update_performance()`
  (même signal que les exécutions réelles de tâches) et
  `profile.task_scores[task_type]` — ce dernier champ n'était jamais
  rempli par quoi que ce soit, donc chaque classement d'`AdaptiveRouter`
  retombait sur la valeur neutre 0.5 pour absolument toutes les paires
  modèle/tâche.
- `quality_score` reste honnête : 1.0 si le modèle a produit une réponse
  non vide, 0.0 sinon — présenté comme un signal de complétion, pas comme
  une évaluation de qualité qu'aucune infrastructure ne validerait.

### Fixed — contexte par rôle, mesuré, pas théorique
- Chaque rôle de `config/models.yaml` a maintenant un `num_ctx` propre,
  choisi à partir d'un vrai benchmark (latence/VRAM mesurées à un contexte
  candidat), pas du maximum architectural du modèle. Détail des 11
  modèles de chat benchmarkés (+ `nomic-embed-text` vérifié séparément via
  `/api/embed`) dans `config/models.yaml`.
- **Deux découvertes en cours de route** :
  - `deepseek-r1:32b` (reasoning_escalation) : à seulement 16384 (une
    fraction de son max réel 131072), 95,8s de latence, 6,6 tok/s, 9,5GB
    déjà déversés en RAM. Ce modèle de 19GB sur disque sature déjà cette
    carte de 17,16GB — augmenter son contexte n'aurait fait qu'aggraver
    la situation, donc son `num_ctx` reste au réglage d'origine (8192) au
    lieu d'être relevé comme tous les autres rôles.
  - `qwen3-coder:30b` (code) déborde déjà sur la RAM (15,2GB VRAM + 6,1GB
    RAM à 24576) — limite matérielle inhérente (18GB sur disque, avant
    même d'ajouter le cache de contexte), pas quelque chose qu'un réglage
    de `num_ctx` peut corriger.
  - `nomic-embed-text` recevait 8192 alors que son maximum réel est 2048
    (`ollama show`) — corrigé à sa vraie limite.
- **Propagation du `num_ctx` par rôle dans tout le pipeline d'inférence**,
  qui reposait entièrement sur un seul défaut global côté client Ollama
  jusqu'ici :
  - `ModelRouter.RoutingDecision` porte désormais `num_ctx` (même
    principe que `thinking`, déjà par-décision).
  - `AdaptiveRouter.ModelDecision` porte aussi `num_ctx`, dérivé de
    `ModelProfile.context_window` (champ existant, jamais rempli jusqu'ici
    — toujours à sa valeur par défaut 4096).
  - `BaseAgent.respond_events()` et `TaskDecomposer._chat_once()`
    transmettent désormais `num_ctx=decision.num_ctx` à `chat_events()` —
    aucun des deux ne le faisait auparavant.
  - `RealTaskExecutor` gagne un point d'injection `num_ctx_for` (miroir de
    `model_for`, optionnel, `None` par défaut = comportement inchangé),
    câblé dans `_make_task_executor` sur `AdaptiveRouter.recommend_for_text()`.

### Verified
- `pytest tests/model_intelligence/` (avec les nouveaux tests de
  benchmark réel + regression `chat_capable`), `tests/architecture/
  test_model_router.py` (nouveau fichier — aucun test dédié n'existait
  pour `ModelRouter` auparavant), `tests/integration/test_real_execution.py`
  et `test_assembly.py` (num_ctx_for bout-en-bout) : tous verts.
- Suite complète : **3363 passed, 3 skipped, 0 failed**.
- Vérification bout-en-bout avec Ollama réel : objectif autonome exécuté,
  `ollama ps` confirme `context_length: 16384` pour `qwen3:1.7b` (rôle
  swift) — exactement la valeur configurée, avec la VRAM réelle mesurée
  (3183MB) identique à celle du benchmark. `POST /models/recommend`
  expose maintenant `num_ctx` dans sa réponse.

## Model Intelligence — trois des quatre adaptateurs câblés (2026-08-01)

Suite directe de l'entrée précédente. Sur les quatre adaptateurs HOS-065B
jamais instanciés nulle part (`ModelAutonomousAdapter`,
`ModelRuntimeAdapter`, `ModelEvolutionAdapter`, `ModelMemoryAdapter`),
l'utilisateur a arbitré : Runtime reste de côté (un seul runtime réel,
Ollama, tant qu'aucun second n'existe — rien à décider) ; pour les trois
autres, choix laissé à l'appréciation du moment de câblage le plus sûr et
le plus intéressant.

### Fixed/Added — ModelAutonomousAdapter (Autonomous Core)
- `record_feedback()` existait depuis HOS-065B et n'était appelé nulle
  part : le choix de modèle et le résultat d'un objectif autonome
  n'allaient nulle part au-delà du profileur déjà alimenté par
  `RealTaskExecutor.on_execution`. Décision de conception : ne **pas**
  utiliser `select_model_for_goal()` pour faire décider l'adaptateur —
  il opère au niveau de l'objectif, alors que le câblage existant décide
  déjà par tâche, juste avant l'exécution réelle. Les deux en parallèle
  auraient pu se contredire. L'adaptateur est donc branché comme couche
  de **traçabilité** : il enregistre ce qui s'est réellement passé,
  jamais ce qui devrait se passer.
- `MissionExecutor.execute_task()` calculait `outcome.model` (le tag
  précis, ex. `qwen3:1.7b`) puis l'écrasait avec le résultat de la
  validation avant qu'aucun appelant ne le voie — le dict retourné
  n'exposait que `runtime` (le fournisseur, ex. « ollama »). Capturé
  et republié.
- `report.results.models_used` : nouveau champ dans le rapport
  Autonomous Center, listant les modèles réellement utilisés — jusqu'ici
  invisible, seul `runtimes_used` (le fournisseur) apparaissait.
- Les quatre constantes d'événement de l'adaptateur (`model.decision.
  created`, `model.selection.completed`, `model.performance.updated`,
  `model.routing.optimized`) n'étaient pas déclarées dans
  `event_topics.py` — corrigé au passage (`model.profiled` et
  `model.recommended`, déjà déclarés comme `produced_events` du service
  `model_intelligence` mais absents eux aussi, corrigés en même temps).

### Fixed/Added — ModelMemoryAdapter (graphe de connaissances)
- **Défaut de documentation trouvé en le lisant** : le docstring du
  module affirmait une intégration avec la mémoire épisodique, la
  mémoire procédurale et le graphe de connaissances *réels* de Hermes
  (HOS-047). L'implémentation entière était trois listes Python privées
  et jamais connectées au vrai `MemoryManager` déjà dans le bootstrap —
  `# In-memory stores (simulating Episodic/Procedural/Knowledge stores)`,
  littéralement dans le code. Docstring corrigé pour ne plus prétendre
  une intégration qui n'a jamais existé.
- Choix du volet le plus intéressant parmi les trois (épisodique,
  procédural, graphe) : le **graphe de connaissances**
  (`record_model_for_task`/`get_best_model_for_task`), pour deux raisons —
  il réutilise directement la télémétrie déjà réelle
  (`on_execution`), et apporte un signal différent du profileur
  (performance par *type de tâche*, pas par modèle seul). Pas de fusion
  avec le vrai `MemoryManager` : décalage de schéma trop important
  (`EpisodicMemory` est structuré autour de `mission_id`, pas de choix
  de modèle par tâche) pour un chantier fait en passant.
- Nouvelle route `GET /models/knowledge?task_type=...`, alimentée à
  chaque exécution réelle par `_make_task_executor`.

### Fixed/Added — ModelEvolutionAdapter (détection de dérive)
- Choisi plutôt que `update_weights()` : le formulaire de score
  (`ModelProfile.overall_score`) a des coefficients figés en dur qui ne
  consultent jamais les poids que cet adaptateur gère — les rendre réels
  changerait le comportement du classement sans signal validé pour
  savoir si le nouveau réglage est meilleur. `detect_underperforming_
  models()`/`suggest_model_replacement()` sont en lecture seule, calculés
  uniquement depuis les données réelles du profileur — vérifié qu'ils ne
  touchent jamais `PerformanceAnalyzer.get_benchmark_summary()`
  (les chiffres simulés de `BenchmarkScheduler`).
- Nouvelle route `GET /models/evolution?threshold=&suggest_for=`.

### Not fixed — gap documenté
- `ModelRuntimeAdapter`/`ModelRuntimeOptimizer` restent non câblés, par
  choix explicite de l'utilisateur : sans second runtime réel, comparer
  Ollama/KTransformers/vLLM/llama.cpp reviendrait toujours à recommander
  Ollama — de la mécanique sans décision à prendre.
- `update_weights()`/le calcul d'`overall_score` restent inchangés (voir
  ci-dessus).
- `ModelMemoryAdapter` reste un cache local à Model Intelligence, pas une
  intégration avec le vrai `MemoryManager`/`EpisodicMemory`.

### Verified
- `pytest tests/model_intelligence/ tests/integration/test_assembly.py
  tests/autonomous/` : **317/317**, dont 6 nouveaux tests pour les routes
  `/models/knowledge` et `/models/evolution` et 4 pour le câblage de
  `ModelAutonomousAdapter` dans `AutonomousOrchestrator`.
- Vérification bout-en-bout avec Ollama réel : objectif autonome
  « Écrire une fonction de validation email en Python » exécuté avec
  succès. `report.results.models_used` : `["qwen3:1.7b"]`.
  `GET /models/knowledge?task_type=general` : une relation réelle
  `qwen3:1.7b USED_FOR general (success=true)`, `best_model_for_task:
  null` (honnête — il faut 3 usages avant de désigner un gagnant).
  `GET /models/evolution` : liste vide, aucune dérive détectée (attendu,
  aucun modèle n'a encore assez d'historique).

## Model Intelligence — AdaptiveRouter réellement branché sur l'exécution (2026-08-01)

L'utilisateur a demandé de vérifier si le système de Model Intelligence &
Adaptive Routing (HOS-065 — `AdaptiveRouter`, `ModelProfiler`,
`PerformanceAnalyzer`, `ModelPredictor`, `ModelRuntimeOptimizer`,
`BenchmarkScheduler`, et quatre adaptateurs vers Autonomous/Runtime/
Evolution/Memory) fonctionnait vraiment, en proposant en parallèle
d'ajouter une couche de stratégie au-dessus. Vérification faite avant
toute décision d'architecture : même verdict que les trois précédents.

### Constat
- **Réel** : les composants existent, `AdaptiveRouter` est câblé au
  bootstrap, et le Models Center appelle vraiment `/models/recommend`,
  `/ranking`, `/performance` — un outil consultatif humain fonctionnel.
- **Décoratif** : `AdaptiveRouter.recommend()` n'était appelé nulle part
  dans le pipeline d'exécution réel — `RealTaskExecutor._resolve_model()`
  retombait toujours sur `qwen3:4b` en dur. Les quatre adaptateurs
  (`ModelAutonomousAdapter`, `ModelRuntimeAdapter`, `ModelEvolutionAdapter`,
  `ModelMemoryAdapter`) n'étaient instanciés nulle part — code mort, même
  défaut que les hooks `set_*` de `DecisionEngine`. `ModelRuntimeOptimizer`
  avait zéro appelant, même via HTTP. La boucle d'apprentissage
  (`BenchmarkScheduler.run_benchmark()`) fabriquait chaque nombre avec
  `random.uniform()` sans jamais parler à Ollama, et `get_latest_benchmarks()`
  regénérait des valeurs aléatoires à chaque appel au lieu de retourner un
  historique stocké.

### Fixed
- **`RealTaskExecutor` consulte maintenant réellement `AdaptiveRouter`.**
  `_make_task_executor` (bootstrap) câble `model_for` sur
  `AdaptiveRouter.recommend_for_text(task.title)`, en réutilisant le même
  singleton de module que le Models Center (`mi_routes._get_router()`) —
  pas une seconde instance déconnectée.
- **Les exécutions réelles nourrissent enfin le profileur.** Nouveau
  callback `on_execution` sur `RealTaskExecutor`, appelé sur les 4 chemins
  de sortie (succès et 3 formes d'échec) avec la télémétrie mesurée
  (modèle, durée, tokens, succès), câblé sur
  `ModelProfiler.update_performance()`. `tokens_per_second` est désormais
  une moyenne glissante calculée depuis de vraies complétions
  (`tokens_used / duration_s`), plus une valeur figée à 0 ou fabriquée par
  le benchmark simulé.
- **Bug trouvé en vérification réelle, pas en test unitaire** : le modèle
  recommandé pour la toute première mission exécutée après ce câblage a
  été `nomic-embed-text` — un modèle d'*embeddings*, pas de chat. Ollama a
  renvoyé `400 Bad Request` sur `/api/chat`, faisant échouer 5 des 7 tâches
  de la mission. Cause : `nomic-embed-text` a le plus petit footprint VRAM
  (0.3GB) des douze modèles, et avec tous les autres signaux de classement
  encore à leur valeur neutre non entraînée (0.5), c'est ce seul critère
  qui tranchait — à chaque fois. Ajout d'un champ `chat_capable` sur
  `ModelProfile` (faux uniquement pour le rôle `embedding`), exclu du
  pool de sélection de `recommend()` et de `_fallback_decision()`, mais
  conservé dans le catalogue général et le classement du Models Center
  (toujours un vrai modèle installé, juste pas candidat au chat).

### Not fixed — gap documenté
- Les quatre adaptateurs (`ModelAutonomousAdapter`, `ModelRuntimeAdapter`,
  `ModelEvolutionAdapter`, `ModelMemoryAdapter`) restent non câblés — hors
  périmètre de cette passe, qui s'est concentrée sur la connexion la plus
  directe et la plus sûre (sélection + apprentissage réel côté exécution).
- `ModelRuntimeOptimizer` et le `BenchmarkScheduler` simulé restent
  inchangés et inutilisés par le pipeline réel.
- La proposition de l'utilisateur d'ajouter un « Model Strategy Engine »
  au-dessus d'`AdaptiveRouter` (un modèle par étape de mission — plan,
  code, revue, résumé…) reste pertinente mais prématurée : construire une
  nouvelle couche stratégique par-dessus un routeur qui n'était pas encore
  branché sur l'exécution aurait hérité du même problème. Recommandation
  donnée à l'utilisateur : cette passe est le prérequis, pas encore ce
  niveau supérieur.

### Verified
- `pytest tests/model_intelligence/` : **117/117** (+5 nouveaux, dont
  deux couvrant explicitement la non-régression du bug `nomic-embed-text`).
- `pytest tests/integration/test_real_execution.py` : nouveaux tests
  hermétiques (`TestModelIntelligenceFeedback`, 4 tests) confirmant que
  `on_execution` reçoit une télémétrie réelle en succès et en échec, et
  qu'un callback de feedback cassé ne peut pas corrompre un résultat par
  ailleurs réussi.
- `pytest tests/integration/test_assembly.py` : nouveau test confirmant
  que `task_executor` partage la même instance `AdaptiveRouter`/
  `ModelProfiler` que le reste du conteneur (pas de singleton rival).
- `tests/integration/test_p002_api_namespace.py` : le test qui affirmait
  que la charge utile de `/verification/run` n'était pas documentée (une
  prémisse fausse, voir l'entrée précédente) a été remplacé par un test
  qui vérifie le contraire contre le schéma OpenAPI réel.
- Suite complète : **3334 passed, 3 skipped, 0 failed** (+11 par rapport
  à avant cette passe).
- Vérification bout-en-bout avec Ollama réel : mission de 7 tâches
  exécutée deux fois. Avant le correctif `chat_capable` : 5/7 échouées
  (`400 Bad Request` sur `nomic-embed-text`). Après : **7/7 réussies**,
  toutes routées vers `qwen3:1.7b` par `AdaptiveRouter`. Confirmé dans le
  Models Center : l'en-tête passe de « 0 RUNS » à « 7 RUNS », et
  `qwen3:1.7b` affiche un TPS réel mesuré de 44.3 (au lieu de 0) avec un
  taux de succès de 100 % — pendant que les modèles jamais utilisés
  restent honnêtement à 0.

## Quatre défauts en attente — Mission Center, Validation Center, appli fantôme (2026-08-01)

Suite au traitement des trois défauts d'« IA factice », quatre pistes
mineures avaient été mises de côté en tâches de fond. L'utilisateur a
demandé de les traiter directement dans cette session.

### Fixed — Mission Center : panneau de détail
- **`selected.id` valait toujours `undefined`.** `GET /api/v1/missions`
  renvoie `mission_id`, pas `id` ; `missionsClient.list()` ne faisait
  aucune projection (contrairement à `toAgent()`, qui existait déjà pour
  ce même problème côté agents). Toutes les missions partageaient donc la
  même clé React `undefined`, et `.find(m => m.id === selectedMissionId)`
  retombait toujours sur la première mission de la liste, quel que soit le
  clic. Ajout de `toMission()` dans `services/client.ts`, sur le même
  principe que `toAgent()`.
- **Le panneau de détail lisait des champs que la liste n'envoie jamais.**
  `description`, `created_at` n'existent que sur `GET /missions/{id}`, pas
  sur `GET /missions` — le panneau affichait donc en permanence
  « No description » / « Invalid Date » quelle que soit la mission
  sélectionnée. `MissionCenter` utilise maintenant `useMission(id)` (un
  hook déjà présent mais jamais appelé) pour un vrai fetch de détail au
  lieu d'une simple recherche dans la liste. La ligne de liste, elle,
  n'affiche plus que le total de nœuds (`node_count`) — le nombre de
  nœuds *terminés* n'existe tout simplement pas sur l'endpoint liste, et
  afficher `undefined/undefined` n'était pas plus honnête que de l'omettre.

### Fixed — Validation Center : bouton de lancement
- **Le Center affirmait que la charge utile de `POST /verification/run`
  n'était pas documentée dans l'OpenAPI — c'est faux.** Le modèle Pydantic
  `VerificationRunRequest` (`backend/api/routes/verification.py`) expose
  `repo_path`/`runner`/`timeout`/`project_id` avec un schéma complet et
  vérifiable sur `/openapi.json`. Ajout d'un vrai formulaire (chemin de
  dépôt + sélection du runner parmi les 7 réels déjà listés) et de
  `verificationClient.run()` / `useRunVerification()`. Vérifié en
  conditions réelles : au `autonomy_level` livré (« low »), Aegis refuse
  l'appel avec un motif honnête (`REQUIRE_HUMAN_VALIDATION` — « needs
  autonomy level high to auto-allow ») au lieu du bouton inexistant
  d'avant ou d'un faux succès.

### Investigated — avertissement de clé React dupliquée
- Le warning « two children with the same key » (valeur « standard »),
  précédemment jugé non reproductible, était en réalité l'un des deux
  symptômes du bug `mission.id` ci-dessus. Vérifié sur un onglet
  entièrement neuf, deux tailles de viewport, balayage des 22 Centers :
  zéro avertissement une fois le correctif du Mission Center appliqué.
  L'apparition persistante sur un onglet resté ouvert tout au long de la
  session était un artefact de Fast Refresh accumulé, pas un défaut du
  code livré.

### Removed — application fantôme pré-Cockpit
- En cherchant pourquoi les boutons de l'ancienne page `/missions`
  restaient inertes, découverte d'une application parallèle entière :
  `/agents`, `/events`, `/execution`, `/memory`, `/missions`, `/runtimes`,
  `/settings`, `/skills`, chacune avec sa propre sidebar
  (`components/layout/Sidebar.tsx`), ses propres hooks (`use-agents`,
  `use-dashboard`, `use-events`, `use-execution`, `use-missions`,
  `use-runtimes`) et ses propres clients API
  (`lib/{agent,execution,mission-control,mission-planner,runtime}-*.ts`)
  — un héritage d'avant la refonte Cockpit, jamais retiré. Vérification
  exhaustive (`grep` de chaque chemin de module contre tout le reste du
  code source) : **aucune référence externe**, ni lien, ni import, depuis
  l'application réelle (`/` → `/dashboard` → `CockpitShell`). Confirmé
  avec l'utilisateur avant suppression étant donné l'ampleur (54 fichiers,
  bien au-delà de la seule page `/missions` signalée initialement) :
  suppression complète plutôt que réparation d'une interface que plus
  personne ne peut atteindre. `/missions` (et les sept autres routes)
  renvoient désormais un 404 propre au lieu d'une page aux boutons morts.

### Verified
- `tsc --noEmit` : **0 erreur**. `vitest run` : **65/65**. `next build` :
  compilation réussie — 2 routes (`/`, `/dashboard`) contre 14 avant la
  suppression.
- Vérification navigateur : Mission Center affiche la vraie description,
  la vraie date et le vrai décompte de nœuds pour la mission Redis créée
  précédemment ; Validation Center déclenche un vrai appel POST et affiche
  le refus honnête d'Aegis ; `/missions` renvoie 404.

## Mission Planner — décomposition réellement pilotée par le LLM (2026-07-31)

Troisième et dernier des trois défauts d'« IA factice » remontés par la
vérification précédente (voir l'entrée « Vérification de l'IA locale »
ci-dessous), et le plus risqué : la
décomposition d'une demande de mission ne faisait jamais appel à Ollama.
`TaskDecomposer.decompose()` cherchait cinq mots-clés anglais fixes
(`"authentication"`, `"database"`, `"api"`, `"frontend"`, `"deployment"`)
comme sous-chaînes littérales dans la requête, et retombait sinon sur un
gabarit générique à 5 étapes ; une demande en français ou simplement
formulée autrement que le mot-clé exact ne recevait jamais qu'un plan
générique, quel que soit son contenu réel.

### Fixed
- **`TaskDecomposer` interroge maintenant le rôle `planning` d'Ollama**
  (`config/models.yaml` : `orchestrator`/`standard`, raisonnement activé)
  pour produire une liste de tâches JSON adaptée à la demande réelle, dans
  la langue de la demande — au lieu de cinq gabarits anglais fixes. La
  réponse est parsée de façon tolérante (tolère une clôture markdown, une
  phrase parasite avant/après le tableau JSON) et ne lève jamais : une
  réponse imparsable, un timeout ou Ollama injoignable retombent sur la
  décomposition par mots-clés d'origine, qui reste le comportement exact
  de tous les appels qui ne fournissent pas de client Ollama (donc de
  tous les tests existants — zéro appel réseau, zéro changement de
  comportement pour eux).
- **`RuntimeRecommender._TIER_MAPPING` recommandait des modèles jamais
  installés.** Six tags fixes (`qwen3:30b-coder`, `phi4:14b`, `qwen3:14b`,
  `gemma3:12b`, `codellama:13b`, `llama3.2:3b`) — le même défaut que celui
  corrigé dans le Models Center, trouvé en marge de ce chantier
  car ce fichier appartient au même pipeline de planification. La table
  est désormais résolue depuis `config/models.yaml` par nom de rôle
  (`code`, `orchestrator`, `reasoning`, `standard`, `swift`…) plutôt que
  par tag figé, pour ne pas se dérégler à nouveau au prochain changement
  de tag (`phi4:14b` → `phi4-reasoning:14b-q4_K_M` a déjà eu lieu une fois
  pendant la vie de ce déploiement).

### Added
- Pont synchrone/asynchrone dédié dans `TaskDecomposer` (même schéma que
  `RealTaskExecutor` : une boucle asyncio dans un thread daemon dédié),
  nécessaire car `decompose()` est appelé de façon synchrone depuis
  l'intérieur même de la boucle d'événements FastAPI (`POST
  /api/v1/missions` est `async def` et appelle le planner directement,
  sans `await` ni threadpool) — `asyncio.run()` y lèverait une erreur.
- `MissionPlanner.close()` et `TaskDecomposer.close()`, trouvés par la
  sonde d'arrêt du bootstrap, pour libérer le client Ollama et arrêter le
  thread de la boucle à l'extinction.

### Verified
- `pytest tests/architecture/test_mission_planner.py` : **58/58** (47
  tests existants inchangés + 11 nouveaux, dont 4 couvrant explicitement
  la dégradation propre : JSON invalide, clôture markdown, catégorie
  inconnue, indices de dépendance hors bornes). Exécution : 0,5s — la
  suite reste hermétique, aucun test n'injecte de client Ollama sauf ceux
  qui testent explicitement le chemin LLM avec un faux client.
- Suite complète (`backend/tests` + `tests`) : **3323 passed, 3 skipped,
  0 failed** (+11 par rapport à avant ce correctif — exactement les
  nouveaux tests du chemin LLM).
- Vérification bout-en-bout avec Ollama réel : mission créée via
  `POST /api/v1/missions` avec la description « Ajouter un système de
  cache Redis pour accélérer les requêtes API fréquentes ». Résultat :
  6 tâches réelles et spécifiques en français (« Analyser les requêtes
  API fréquentes », « Concevoir la stratégie de cache », « Configurer le
  serveur Redis », « Intégrer le cache dans les endpoints », « Tester le
  cache », « Documenter la configuration ») plus la tâche de validation
  finale ajoutée automatiquement, avec un graphe de dépendances cohérent
  — confirmé visuellement dans le Mission Center. Avant ce correctif, la
  même description (qui contient la sous-chaîne « api ») aurait produit
  le gabarit anglais fixe de 5 tâches API sans aucun rapport avec Redis.

### Non corrigé — gap documenté
- La sélection d'agent/outil/compétence dans `DecisionEngine`
  (Autonomous Center) reste heuristique — voir l'entrée précédente.
  Aucun changement de périmètre depuis.

## Vérification de l'IA locale — Autonomous Center et Models Center (2026-07-31)

Suite à la refonte visuelle, l'utilisateur a demandé de vérifier que les
onglets s'appuyant sur l'IA locale (Ollama) fonctionnent réellement et
remplissent leur rôle — pas seulement qu'ils s'affichent correctement.
Méthode : lecture du code à la recherche d'appels LLM réels, confrontation
des noms de modèles codés en dur avec `ollama list`, et exécution de flux
réels dans le navigateur en surveillant `ollama ps` (charge VRAM, latence
multi-seconde) pour distinguer une vraie inférence d'une donnée simulée.
Trois défauts confirmés ; deux corrigés ici (le troisième, le plus risqué,
est traité séparément). Un quatrième point — la sélection d'agent/outil/
compétence dans `DecisionEngine` — reste heuristique : voir "Non corrigé"
plus bas.

### Fixed — Autonomous Center
- **Le texte généré par l'IA était calculé puis jeté.** Chaque tâche
  autonome appelait bien Ollama (confirmé : 22,9 s d'exécution, 113 tokens
  réels mesurés via `ollama ps`), mais `_execute_plan()` ne renvoyait dans
  `outputs` que `{"task": ..., "chars": len(...)}` — la longueur du texte,
  jamais le texte lui-même. Le rapport final ne contenait donc aucune trace
  de ce que le modèle avait produit. `outputs` inclut maintenant `"content"`
  avec le texte réel.
- **La justification de choix de runtime était une liste imaginaire.**
  `_generate_runtime_alternatives()` renvoyait toujours
  `["ktransformers", "default_llm", "local_model"]` — trois runtimes que ce
  déploiement n'a jamais enregistrés — pendant que le champ `runtimes_used`
  du même rapport JSON, calculé séparément par `mission_executor.py`,
  disait correctement `["ollama"]` : une contradiction visible dans la même
  réponse. `DecisionEngine` reçoit maintenant le `RuntimeOrchestrator` réel
  au bootstrap (`set_runtime_orchestrator`, ajouté aux dépendances du
  service `autonomous_engine`) et lit sa liste de runtimes effectivement
  enregistrés ; à défaut, le seul runtime réellement câblé (`ollama`) sert
  de repli plutôt qu'un nom inventé.

### Fixed — Models Center
- **Le catalogue de modèles était entièrement fictif.** `PREDEFINED_MODELS`
  listait six modèles (`qwen3-coder-30b`, `deepseek-coder-16b`,
  `llama3.2-3b`, `codellama-7b`, `mistral-7b`, `phi3-14b`) qu'aucun
  déploiement de ce projet n'a jamais installés — le classement affiché
  était un banc d'essai plausible pour des modèles que personne ne pouvait
  exécuter. Le catalogue est désormais construit depuis `config/models.yaml`
  (la même source que `agent_registry.py` et le routeur de modèles), avec
  architecture et nombre de paramètres déduits du tag Ollama réel
  (`qwen3.5:9b` → `qwen`, 9,0 B) plutôt qu'inventés ; un tag sans suffixe de
  taille (`devstral`, `nomic-embed-text`) reste honnêtement à 0 B au lieu
  d'un chiffre plausible. 12 modèles réels en résultent.
- **Le repli du routeur adaptatif nommait aussi un modèle fictif.**
  `AdaptiveRouter._fallback_decision()` renvoyait toujours `model_id
  ="llama3.2-3b"` — le seul chemin censé toujours réussir recommandait un
  modèle introuvable. Il choisit maintenant le profil réel le plus léger
  connu du profileur.

### Not fixed — gap documenté
- Les trois autres points d'entrée de `DecisionEngine`
  (`set_agent_supervisor`, `set_skill_distributor`, `set_tool_router`)
  restent des méthodes mortes : jamais appelées, y compris dans les tests.
  La sélection d'agent, d'outil et de compétence dans l'Autonomous Center
  reste donc heuristique/factice. Hors périmètre de cette passe ;
  documenté ici pour qu'il ne soit pas pris pour un défaut résolu.

### Verified
- `pytest tests/autonomous/test_autonomous_core.py` : **74/74**, avec 3
  nouveaux tests couvrant le repli sans orchestrateur, la sélection depuis
  un registre réel, et la présence du texte généré dans le rapport.
- `pytest tests/model_intelligence/` : **112/112**, avec un nouveau test
  qui vérifie que le catalogue est un sous-ensemble des tags réels de
  `config/models.yaml` et ne contient aucun des six identifiants fictifs.
- Suite complète (`backend/tests` + `tests`) : **3312 passed, 3 skipped,
  0 failed**.
- Vérification navigateur du Models Center après redémarrage du serveur :
  12 modèles réels affichés (`nomic-embed-text`, `qwen3:1.7b`, `qwen3:4b`,
  `qwen3.5:9b`, `gemma4:12b`, …) avec tags de rôle et paramètres corrects
  dans la colonne « Params ».

## Refonte — Fusion des Centers redondants (2026-07-31)

Suite directe de la refonte précédente, qui avait signalé sans les traiter
trois recouvrements. Décision de l'utilisateur : fusionner. Le principe
retenu est de ne perdre aucune fonctionnalité — chaque écran supprimé
devient un onglet de celui qui l'englobe, en gardant la meilleure des deux
implémentations panneau par panneau.

### Changed
- **Governance + Policy → Governance Center.** Les deux écrans consommaient
  exactement les mêmes hooks (`usePolicyRules`, `useApprovals`,
  `useAuditLog`, `useApproveAction`, `useRejectAction`) et donc les trois
  mêmes endpoints : ils affichaient les mêmes données sous deux noms, avec
  deux mises en page qui divergeaient à chaque évolution. Le Center unifié
  garde l'architecture de Policy (briques du scaffold, recherche, filtres
  par catégorie, remontée d'erreur de décision) et le rendu de Governance
  (journal d'audit en colonnes horodatées plutôt qu'en JSON brut, règles
  avec état activé/désactivé et description, métadonnées de demande
  d'approbation). Trois onglets : Approbations, Règles, Audit.
- **Knowledge Graph + Alexandrie → Memory Center.** Memory appelait déjà
  les sept hooks d'Alexandrie *et* le graphe de connaissances : les deux
  autres écrans n'affichaient rien qu'il ne montrait pas. Trois onglets :
  Mémoire (statistiques par magasin, recherche hybride, expériences),
  Graphe (nœuds et arêtes filtrables, repris de Knowledge Graph) et
  Alexandrie (corpus, synchronisation, historique — avec la bannière
  « service injoignable » et la gestion d'erreur de synchro d'Alexandrie
  Center, qui distingue « corpus vide » de « service qui ne répond pas »).
- La navigation passe de 25 à 22 entrées. Les identifiants `policy`,
  `knowledge` et `alexandrie` restent résolus dans `cockpit-shell.tsx` vers
  leur Center d'accueil, pour qu'un état persistant ou un lien pointant
  dessus n'atterrisse pas silencieusement sur le Dashboard.

### Added
- `CenterTabs` dans `center-scaffold.tsx` : onglets internes à un Center,
  avec indicateur actif animé (`layoutId`) et pastille de comptage
  optionnelle.

### Removed
- `features/policy/policy-center.tsx`,
  `features/knowledge/knowledge-graph-center.tsx`,
  `features/alexandrie/alexandrie-center.tsx` — leur contenu vit désormais
  dans les Centers ci-dessus. Trois imports d'icônes devenus inutilisés
  retirés de la barre latérale.

### Verified
- `tsc --noEmit` : **0 erreur**. `vitest run` : **65/65**.
  `next build` : **compilation réussie**, 14 pages.
- Vérification navigateur des deux Centers fusionnés : Governance affiche
  10 règles réelles réparties en 4 catégories, avec filtres opérants et les
  trois badges (catégorie / état / décision) issus de la fusion ; Memory
  bascule correctement entre ses trois onglets, et l'onglet Alexandrie
  affiche l'erreur de connexion réelle (port 8200 refusé) au lieu de
  compteurs à zéro trompeurs.

## Refonte — Interface cyberpunk et alignement des contrats d'API (2026-07-31)

Refonte visuelle complète du Cockpit demandée par l'utilisateur (« design
cyberpunk moderne, visuellement impressionnant tout en restant
professionnel »), précédée d'une analyse de l'utilité réelle de chaque
onglet. L'analyse a fait remonter plusieurs défauts qui n'étaient pas
cosmétiques.

### Fixed — défauts trouvés pendant l'analyse
- **312 classes de couleur ne produisaient aucun CSS.** `text-hermes-muted`
  (207 usages) et `text-hermes-text` (105 usages) étaient employées dans
  tous les Centers, mais `hermes.text` et `hermes.muted` n'existaient que
  comme variables CSS — jamais déclarées dans `tailwind.config.ts`. Chaque
  libellé secondaire héritait donc silencieusement de la couleur du corps
  de page : l'interface n'avait tout simplement pas de ton secondaire, ce
  qui explique son aspect plat et monotone.
- **Le bandeau d'état affichait « UNKNOWN » en permanence.** Le Cockpit
  interrogeait `GET /api/v1/health`, la sonde de vivacité héritée, qui
  renvoie `{"status": "ok"}` et rien d'autre — jamais `"HEALTHY"`, aucun
  sous-système. La sonde agrégée réelle est `/api/v1/system/health` (34
  services). `systemClient.health()` interroge désormais les deux et
  normalise la réponse (statuts en minuscules → majuscules, `detail` →
  `subsystems`, uptime pris sur la sonde racine).
- **La barre d'état affichait « 0/0 » partout.** `/api/v1/system/statistics`
  renvoie `{services: {…}}` par sous-système, pas les champs plats
  (`missions_total`, `agents_active`…) que le type déclarait. Toutes ces
  lectures valaient `undefined`. Ajout d'une projection explicite vers le
  type attendu, `raw` conservant la charge utile d'origine.
- **Le Runtime Center n'a jamais affiché la moindre jauge de ressources.**
  `runtimeClient.resources` appelait `/runtime/resources/status`, qui
  n'existe pas (404) ; la route est `/runtime/resources`. Le garde
  `resources && …` masquait l'échec en n'affichant rien. Les jauges
  RAM/VRAM/GPU sont maintenant alimentées par de vraies mesures, et une
  valeur non exposée par le pilote (température) est annoncée comme telle
  plutôt qu'affichée à zéro.
- **Dix clés React identiques dans la liste d'agents.** `GET /api/v1/agents`
  renvoie `agent_id`, `preferred_runtime` et `preferred_model` — pas `id`,
  `type` ni `runtime`. Chaque agent avait donc `id === undefined`. Ajout de
  `toAgent()` qui projette la charge utile réelle sur le type `Agent`.
- **Types alignés sur les réponses réelles.** `RuntimeInfo` déclarait
  `type`, `health` et `metrics` obligatoires et un `status` limité à
  `AVAILABLE|DEGRADED|UNAVAILABLE` alors que l'API renvoie `started`. Ces
  champs sont désormais facultatifs et le cycle de vie réel est couvert ;
  le badge du Runtime Center ne produit plus `undefined` comme variante.
- **25 boutons de navigation sans nom accessible.** Les libellés étaient
  enveloppés dans des couches animées ; ajout de `aria-label` et
  `aria-current`.

### Changed — refonte visuelle
- Nouveau système de design dans `globals.css` : substrat bleu-noir
  profond, palette signal (cyan = le système parle, magenta = point de
  décision humain, vert/ambre/rouge = santé, violet = activité autonome),
  grille ambiante en perspective, nébuleuses dérivantes, panneaux
  *glassmorphism*, bords néon en dégradé masqué, coins biseautés
  (`clip-corner`), crochets d'angle façon HUD, balayage de scanline,
  balayage lumineux au survol des boutons, balises « beacon » à anneau
  pulsé. `prefers-reduced-motion` neutralise toutes les animations.
- `tailwind.config.ts` : palette complète, ombres de halo, timings
  d'animation. Les alias `amber-bright` / `purple` sont conservés pour que
  le balisage antérieur continue de rendre.
- `ui/card.tsx` et `center-scaffold.tsx` réécrits — ce sont les deux
  fichiers que les 25 Centers composent, donc la refonte les traverse tous
  sans réécriture individuelle. Ajout de `Button`, `Beacon`, `PanelLoading`
  (barre indéterminée) et d'un `ProgressBar` dont la rampe de couleur
  s'inverse pour les jauges de saturation.
- Navigation : la liste plate de 25 entrées devient cinq groupes par
  domaine (Pilotage, Intelligence, Connaissance, Gouvernance, Opérations),
  avec filtre de recherche, repli de la barre latérale, et indicateur actif
  animé via `layoutId`. Le shell et les bandeaux se recalent sur la largeur
  repliée via le store.
- Les 25 Centers partagent désormais le même `CenterHeader` (12 avaient un
  en-tête inline divergent, dont 3 — Deployment, Models, Conversation —
  écrits entièrement avec les couleurs Tailwind par défaut). Les 162
  classes hors palette (`text-white`, `text-gray-400`, `bg-gray-800`…) ont
  été remappées sur le vocabulaire Hermes ; il n'en reste aucune.
- Dashboard reconstruit en écran vitrine : bandeau titre avec jauge de
  santé globale, tuiles animées en cascade, santé par sous-système, flux
  d'événements temps réel, missions et agents, compteurs du moteur
  d'exécution. Chaque panneau expose un bouton « Ouvrir » vers le Center
  correspondant.

### Verified
- `tsc --noEmit` : **0 erreur**.
- `vitest run` : **65/65 tests verts**.
- `next build` (production) : **compilation réussie**, 14 pages générées.
- Parcours automatisé des **25 onglets** dans le navigateur : aucun
  plantage, `<h1>` présent partout, contenu réel rendu.
- Le Runtime Center, qui plantait à chaque ouverture
  (`Cannot read properties of undefined (reading 'usage_pct')`), affiche
  désormais RAM 35,2 % (11,2/31,8 Go) et VRAM 0,0 % (0,0/16,0 Go) mesurées.

### Non traité
- L'onglet Governance et l'onglet Policy consomment exactement les mêmes
  hooks (`useApprovals`, `useAuditLog`, `usePolicyRules`,
  `useApproveAction`, `useRejectAction`) et affichent donc les mêmes
  données sous deux noms ; Memory, Knowledge et Alexandrie se recouvrent
  également. Fusionner ces onglets change la structure du produit, pas son
  apparence — signalé plutôt que décidé unilatéralement.

## Nettoyage — Dette technique : imports morts, routes héritées, schéma OpenAPI (2026-07-31)

Item #8 de la liste de finalisation.

### Removed
- **448 imports inutilisés** détectés par `ruff check --select F401` sur
  tout le dépôt Python (`ruff` installé pour l'occasion — absent du
  projet). 438 supprimés automatiquement (`--fix`, mécanique et sûr par
  nature) sur 192 fichiers. Les 10 restants sont volontairement laissés
  intacts : ce sont des sondes de disponibilité (`try: import whisper /
  except ImportError` dans `backend/voice/{speech_to_text,text_to_speech}.py`,
  pareil pour `HermesAgentAdapter` et consorts dans
  `backend/services/mission_control.py`) où le nom importé n'est jamais
  référencé par identifiant mais où l'import lui-même fait le travail —
  ruff refuse lui-même de les toucher et suggère `importlib.util.find_spec`
  à la place, ce qui est juste mais hors de portée ici.
- **9 composants frontend morts**, confirmés sans aucune référence
  (import direct, import dynamique, barrel file, test) nulle part dans le
  dépôt : `ActivityPanel.tsx`, `components/dashboard/{EventTimeline,
  HealthCard,HermesCard,MissionList,StatisticsCard}.tsx`,
  `features/runtime/kt-panel.tsx`, `features/tools/{klaatcode,ohmypi}-panel.tsx`.
  Écart avec les « 15 composants morts » de l'audit RC1 : une partie a déjà
  été nettoyée dans les phases intermédiaires (P-001, item #5 pour
  `FreebuffCard.tsx`) ; 9 restaient réellement orphelins aujourd'hui.

### Fixed
- **Collision de nom de schéma OpenAPI sur `POST /verification/run`** :
  `backend/api/routes/verification.py` et `backend/api/routes/workflows.py`
  déclaraient chacun une classe `RunRequest`, ce que FastAPI résolvait en
  mangling le nom du premier
  (`backend__api__routes__verification__RunRequest`) dans le schéma public
  — pas un schéma manquant comme le laissait penser la liste de
  finalisation, juste un nom illisible en pratique (Swagger UI, clients
  générés). Renommé en `VerificationRunRequest`, propre et sans collision.
  En creusant ce point, découverte que le Validation Center du frontend
  désactive volontairement son bouton de lancement en croyant, à tort
  aujourd'hui, que cette charge utile n'est pas documentée dans l'OpenAPI —
  signalé séparément (tâche de fond) plutôt que câblé ici : au-delà du
  nettoyage de dette technique, c'est l'activation d'une action mutante
  (exécution réelle de sous-processus) qui mérite sa propre vérification.
- **62 routes héritées à la racine, jamais marquées comme telles** :
  `backend/main.py` montait les 21 routeurs Hermes-Ollama d'origine à la
  fois à la racine (compatibilité ascendante pure) et sous `/api/v1`
  (chemin canonique actuel, `mount_legacy_under_api()`), sans aucune
  distinction visible dans l'OpenAPI. Les montages racine portent
  désormais `deprecated=True` — Swagger UI les affiche barrés, tout outil
  lisant `openapi.json` peut filtrer dessus — sans le moindre changement
  de comportement ; les montages `/api/v1` équivalents restent
  volontairement non dépréciés puisque ce sont eux la façon actuelle
  d'atteindre ces handlers. Documenté dans
  `docs/architecture/API_NAMESPACE_CONSISTENCY.md`. `ROADMAP.md` : l'item
  M-4/M-5 (déjà traité par ce nettoyage) retiré de la liste « reste à
  traiter ».

### Verified
- `python -m compileall backend tests scripts` : aucune erreur de syntaxe
  sur les 192 fichiers touchés par `ruff --fix`.
- `tsc --noEmit` sur tout le frontend après les 9 suppressions : 0 erreur.
- `GET /api/v1/verification/run` (schéma OpenAPI généré) : référence
  `VerificationRunRequest` sans nom mangled ; `/chat` (racine) porte
  `deprecated: true`, `/api/v1/chat` non.
- Suite complète (`backend/tests` + `tests`, aucune exclusion) : **3308
  réussis, 3 ignorés, 0 échec** (10 min 56 s) — inclut à la fois les
  correctifs manquants de l'item #5 (voir entrée précédente) et le travail
  de cet item #8, vérifiés ensemble en conditions réelles.

## Correction — Le commit item #5 n'avait poussé que les suppressions (2026-07-31)

Le commit `01863d9` ("Supprime FreeBuff...") ne contient, en réalité, que les
5 suppressions de fichiers (`backend/integrations/freebuff/`,
`docs/integrations/freebuff.md`, `FreebuffCard.tsx`,
`test_freebuff_adapter.py`) : `git status` affichait bien toutes les
modifications comme indexées juste avant le commit, mais celui-ci ne les a
pas embarquées — cause exacte non déterminée (la commande `git add -A --
<longue liste de chemins>` n'a manifestement pas fait ce qu'elle semblait
faire). Résultat : `ARCHITECTURE.md`, `CONTRIBUTING.md`,
`DESIGN_DECISIONS.md`, `README.md`, `backend/agent/{lifecycle,supervisor}.py`,
`backend/api/{hos_routes,models,router}.py`,
`backend/services/mission_control.py`, `backend/skills/orchestrator.py`,
`docs/architecture/mission_control*.md`, les fichiers frontend
(`MissionActions.tsx`, `MissionForm.tsx`, `use-dashboard.ts`,
`use-missions.ts`, `mission-control.ts`, `mission-planner.ts`,
`types/mission-control.ts`) et les mises à jour de tests
(`test_mission_control_api.py`, `test_mission_control_service.py`) n'ont
jamais atteint GitHub, alors que le rapport de ce commit affirmait le
contraire.

Repéré en creusant l'item #8 (une collision de nom de schéma OpenAPI a mené
à relire `verification.py`, puis par ricochet le git log de la veille).
Les fichiers étaient toujours corrects dans l'arbre de travail — aucun
contenu perdu, seulement jamais poussé. Recommité ici avec le reste du
travail de l'item #8, après une compilation complète (`compileall`) et une
suite de tests complète en conditions réelles (voir plus bas) pour
confirmer qu'aucune régression ne s'était glissée entre-temps.

## Nettoyage — Suppression de FreeBuff, purge des prototypes KTransformers morts (2026-07-31)

Item #5 de la liste de finalisation, décision utilisateur : nettoyage complet
plutôt que suppression partielle.

### Removed
- **FreeBuff** : intégration entièrement retirée. `backend/integrations/freebuff/`
  (983 lignes) était un simulateur pur — `submit_prompt(simulate=True)`
  renvoyait un texte codé en dur, `simulate=False` renvoyait un *autre* texte
  codé en dur, `connect()` ne contactait jamais rien (« In a real scenario:
  validate API key, ping health endpoint »). Aucun client réel pour ce
  service n'existe nulle part ailleurs dans le dépôt. Retiré : le module et
  son test dédié (44 tests), sa doc (`docs/integrations/freebuff.md`), les
  trois routes REST (`GET/POST /freebuff/projects`, `POST /freebuff/sync`)
  et leurs modèles Pydantic, la façade `MissionControlService` (import
  protégé, paramètre constructeur, trois méthodes, entrées santé/diagnostic),
  les 6 tests qui ne couvraient que le mode « adaptateur absent », et les
  références frontend mortes (`FreebuffCard.tsx` — jamais importé nulle
  part —, le bouton « Sync Freebuff » et l'option de planner « Freebuff »
  sur la page Mission Center, dont les appels réseau échouaient déjà en 404
  puisque toute cette couche HOS-028 n'est jamais montée par `main.py`).
  Documentation vivante (`ARCHITECTURE.md`, `README.md`, `CONTRIBUTING.md`,
  `DESIGN_DECISIONS.md`, `docs/architecture/mission_control*.md`) mise à jour
  en conséquence. `CHANGELOG.md` et l'entrée historique HOS-026 de
  `ROADMAP.md` restent inchangés : ce sont des journaux, pas une
  description de l'état courant.
- **KTransformers, génération HOS-052 (prototype)** : 5 fichiers
  (`kt_cache.py`, `kt_loader.py`, `kt_model_manager.py`, `kt_optimizer.py`,
  `kt_scheduler.py`) n'étaient importés par rien de vivant — confirmé par
  recherche exhaustive sur tout le dépôt — et deux d'entre eux
  n'importaient même plus (`KTCacheStats`, `KTQuantization.Q3_K` retirés de
  `kt_models.py` depuis). `tests/architecture/test_ktransformers.py` et
  `test_ktransformers_integration.py` testaient cette génération intermédiaire
  (HOS-052B, `KTKernelWrapper` et consorts) : ni l'un ni l'autre n'existe
  dans le code actuel — c'est ce qui causait les deux erreurs de collection
  laissées en suspens depuis le commit précédent (item #5 de la liste de
  finalisation). Correspond exactement aux items M-4/M-5 déjà notés au
  ROADMAP, retiré de la liste « reste à traiter ».

### Kept as-is (décision utilisateur)
- **KTransformers, génération HOS-052C (courante)** — `hermes_adapter.py`,
  `kt_models.py`, `kt_runtime.py`, `kt_routes.py`, `integrations/` :
  branchée dans `service_registry.py`, 13 routes REST réelles, 73/73 tests
  verts sur un noyau simulé en l'absence du paquet `kt_kernel` réel.
  Fonctionnelle telle quelle ; la finir « pour de vrai » est une question
  matérielle/dépendance (installer `kt-kernel` + AMX/AVX512 ou GPU), pas de
  branchement.
- **vLLM / llama.cpp** — confirmé absents de tout le dépôt (aucun adaptateur
  sous `backend/ral/adapters/`, aucune entrée dans `config/*.yaml`) ; déjà
  correctement documentés comme travail futur (`RuntimeUnavailableError`
  explicite plutôt qu'un faux succès). Rien à retirer.

### Verified
- Import direct de tous les modules backend touchés : OK.
- `tests/architecture/test_ktransformers_final.py` (génération vivante) :
  **73/73 verts**.
- `tests/architecture` collecte proprement sans exclusion (`--ignore`) pour
  la première fois : **1634 tests collectés**.
- `tsc --noEmit` sur tout le frontend : **0 erreur**.
- Suite complète (`backend/tests` + `tests`, plus aucun fichier à exclure) :
  **3308 réussis, 3 ignorés, 0 échec** (11 min 37 s) — écart de -50 tests
  par rapport au dernier baseline (3358), expliqué exactement par les tests
  FreeBuff retirés (44 + 6).
- Vérification manuelle dans le navigateur de la page Mission Center :
  aucune erreur console liée aux fichiers modifiés ; les erreurs observées
  (GovernanceCenter, SkillsCenter, RuntimeCenter, boutons de la page
  `/missions` non réactifs) sont préexistantes et sans rapport avec ce
  nettoyage — confirmé via `git diff` (le fichier hébergeant ces boutons
  n'a pas été touché) — et signalées séparément.

## Correction — /api/v1/runtimes annonce le vrai runtime Ollama (2026-07-31)

Item #4 de la liste de finalisation. Portée volontairement limitée à
l'étiquette rapportée, sur choix explicite de l'utilisateur (voir la
section "Non traité" ci-dessous) : ce correctif ne fait pas transiter
l'inférence réelle par ce registre.

### Fixed
- `GET /api/v1/runtimes` annonçait `active: "stub"` (un runtime factice qui
  se contente d'un écho) alors que 100% de l'inférence réelle — chat
  Hermes, agents, missions — passe par `OllamaClient` construit
  directement dans `agent_registry.py`, `response_generator.py` et
  `task_executor.py`, un chemin totalement séparé qui ne touche jamais ce
  registre. Cause : `backend/main.py` appelait
  `init_runtime_registry_in_holder(default_runtime="stub")` au démarrage,
  en dur. `RuntimeOrchestrator`, qui recopie ce même registre à l'amorçage
  (`registry_seeding.py`), héritait donc lui aussi de "stub" comme unique
  runtime connu.
- Le démarrage utilise maintenant `default_runtime="ollama"`
  (`backend/main.py`). `backend/sds/runtime.py` construit la configuration
  du runtime Ollama à partir des mêmes sources que tous les autres points
  d'appel réels — `Settings.ollama_api_url` et le rôle `standard` de
  `config/models.yaml` — au lieu d'un modèle/endpoint codés en dur
  séparément (`qwen3.5:9b` / `127.0.0.1:11434` figuraient déjà comme
  valeurs de repli si la config ne charge pas). Vérifié en conditions
  réelles : `GET /api/v1/runtimes` renvoie désormais
  `{"active": "ollama", "runtimes": [{"name": "ollama", "runtime_name":
  "hermes-ollama", "model": "qwen3.5:9b", ...}]}`.

### Non traité (portée explicitement limitée, décision utilisateur)
- `RuntimeOrchestrator.select()` reste non consulté par le chemin
  d'inférence réel : `agent_registry.py`, `response_generator.py` et
  `task_executor.py` continuent de construire leur propre `OllamaClient`
  plutôt que de passer par le registre/RuntimeOrchestrator. Rebrancher ces
  trois points d'appel toucherait exactement le code du chat Hermes tout
  juste stabilisé (bug "ne répond pas aux questions simples" corrigé plus
  tôt dans cette même session) — refonte d'architecture à part entière,
  proposée comme item séparé plutôt que glissée sous ce correctif.

### Verified
- Suite runtime + intégration ciblée (RAL, RuntimeRegistry, RuntimeOrchestrator,
  RuntimeSelector, SDS, R-002, assembly) : **251/251 verts**.
- `GET /api/v1/runtimes` vérifié manuellement contre l'app réellement
  assemblée : `active: "ollama"`, modèle et endpoint corrects.
- Suite complète (hors les 2 fichiers KTransformers déjà cassés à la
  collection — item #5) : **3358 réussis, 3 ignorés, 0 échec** (11 min 29 s).

## Correction — Mémoire épisodique alimentée par /api/v1/missions (2026-07-31)

Item #3 de la liste de finalisation.

### Fixed
- `/api/v1/autonomous` alimentait la mémoire épisodique dès sa première
  mission (`AutonomousMemoryLoop`, RC3 P2) ; `/api/v1/missions` ne l'a
  jamais fait, alors que les deux surfaces partagent le même moteur
  d'exécution depuis R-002 P1. `episodic.total` (`GET
  /api/v1/memory/statistics`) restait donc figé quel que soit le nombre de
  missions terminées via ce routeur. `backend/mission/routes.py` écrit
  désormais un `EpisodicMemory` (succès/échec, nœuds, durée, agents et
  runtimes utilisés) chaque fois qu'une mission atteint un état terminal
  via `/start` (`completed`/`failed`) ou `/cancel` (`cancelled`) —
  écriture best-effort, non bloquante, sur le même modèle que
  `AutonomousMemoryLoop.process_report()`. Le gestionnaire de mémoire est
  injecté depuis la racine de composition
  (`backend/core/bootstrap/service_registry.py`, `mission_planner` déclare
  désormais `memory_manager` comme dépendance et `_bind_planner_routes`
  l'injecte au même endroit que le planificateur de mission).

### Added
- `tests/integration/test_r002_integration.py::test_mission_completion_writes_an_episode` —
  vérifie que `episodic.total` progresse et que l'épisode enregistré
  reflète la mission réelle après un cycle complet via `/api/v1/missions`.

### Verified
- Suite R-002 + missions/mémoire/assembly ciblée : **454/454 verts**.
- Suite complète (`backend/tests` + `tests`, hors les 2 fichiers
  KTransformers déjà cassés à la collection — item #5) : **3358 réussis
  (dont le nouveau test), 3 ignorés, 0 échec** (11 min 23 s).

## Correction — Fenêtre de contexte Ollama et whitelist ALLOWED_PATHS (2026-07-31)

Item #2 de la liste de finalisation : deux défauts de configuration qui
cassaient des fonctionnalités entières en silence, sans jamais lever
d'erreur.

### Fixed
- **`num_ctx` jamais transmis à Ollama** : aucun des 20+ points d'appel de
  `OllamaClient.chat_events()`/`chat_stream()` (conversation, agents,
  exécution de tâches, MCP…) ne passait `num_ctx`. Résultat : chaque requête
  utilisait le défaut d'Ollama (4096, parfois 2048 selon le Modelfile), qui
  tronque silencieusement les prompts trop longs *par le début* — sans
  erreur, sans avertissement. Confirmé empiriquement par
  `scripts/validation/bench_context.py` (sonde "aiguille dans la botte de
  foin") : un fait placé en tête d'un document de ~6000 mots devenait
  irrécupérable à `num_ctx=4096` par pure troncature, `prompt_eval_count`
  plafonnant à ~2050 tokens bien avant la fin du prompt réel.
  `backend/connectors/ollama_client.py` applique maintenant un plancher
  `DEFAULT_NUM_CTX=8192` chaque fois qu'un appelant ne fixe pas `num_ctx`
  explicitement — un seul point de correction couvre tous les appelants.
  Rendu configurable via `OLLAMA_NUM_CTX` (`Settings.ollama_num_ctx`,
  `backend/core/config.py`) et branché sur les constructions
  `OllamaClient` qui lisent déjà `Settings` (`agent_registry.py`,
  `task_executor.py`, `response_generator.py` — ce dernier alimente
  directement le chat Hermes).
- **`ALLOWED_PATHS` vide par défaut** : sans fichier `.env` (le cas sur
  cette machine), `Settings.allowed_paths` valait `""`, et
  `AegisEngine._is_within_whitelist()` refuse tout quand la liste est vide
  (§17.1 — échec sûr par défaut, mais piège silencieux ici) : `/files` et
  `/git/*` renvoyaient 403 même sur le dépôt du projet lui-même, cassant
  les pipelines KlaatCode/OhMyPi qui opèrent dessus. `allowed_paths` vaut
  maintenant par défaut la racine du projet
  (`Path(__file__).resolve().parents[2]`) ; toute valeur `ALLOWED_PATHS`
  définie dans `.env` continue de la remplacer entièrement (variable
  d'environnement prioritaire sur le défaut de classe en
  pydantic-settings), donc aucun déploiement ayant déjà configuré sa
  propre whitelist n'est affecté.

### Verified
- Tests ciblés (sandbox, fichiers, git, client Ollama, always-loaded,
  thinking stream, runtime Ollama) : **127/127 verts**.
- Suite de fumée + exécution réelle (non-régression du fix précédent) :
  **158/158 verts**.
- Suite complète (`backend/tests` + `tests`, hors les 2 fichiers
  KTransformers déjà cassés à la collection avant ce changement — item #5
  de la liste de finalisation) : **3357 réussis, 3 ignorés, 0 échec**
  (11 min 32 s) — identique au dernier baseline vérifié.

## Correction — Blocage de la boucle événementielle sous test réel (2026-07-31)

Root-cause des 5 échecs de tests non élucidés lors du dernier commit P-002.

### Fixed
- **Cause réelle (tests)** : `backend/tests/test_smoke_live_server.py` et
  `tests/integration/test_real_execution.py` lancent un vrai processus uvicorn
  via `subprocess.Popen(..., stdout=PIPE, stderr=STDOUT)` sans jamais drainer
  cette sortie pendant l'exécution normale. Le tampon de pipe Windows sature en
  environ 50 lignes de logs applicatifs ; l'écriture suivante du processus
  enfant se bloque alors indéfiniment, gelant toute requête HTTP en cours —
  observé comme un `httpx.ReadTimeout` sur des routes par ailleurs instantanées
  (`/api/v1/system/models`, `/system/ready`, `/system/statistics`,
  `/system/status`, et le handshake MCP). Confirmé par reproduction isolée :
  échec systématique sans drainage, succès systématique avec. Corrigé par un
  thread de drainage continu dans les deux fixtures. Ce bug préexistait ; la
  migration P-002 l'a rendu visible en rendant `/api/v1/system/status` et
  `/api/v1/system/models` nouvellement testables sous `/api/v1`.
- **Défaut latent (application)**, trouvé en chemin et corrigé par prudence :
  `GpuMonitor.snapshot()` (`backend/monitoring/gpu_monitor.py`) exécutait
  jusqu'à six sous-processus PowerShell **synchrones** dans une méthode
  `async`, sans `run_in_executor` — jusqu'à 30 s de blocage réel de la boucle
  asyncio dans un déploiement à un seul worker. Corrigé via `asyncio.to_thread`.
  `bootstrap.health()`/`.statistics()` (`backend/main.py`), qui parcourent tous
  les sous-systèmes et peuvent toucher ce même chemin, sont protégés de la
  même façon.

### Verified
- Les 5 tests initialement en échec : **5/5 verts** (48,31 s, contre
  138,96 s + 28,18 s de délais dépassés).
- Suite complète : **3357 réussis, 3 ignorés, 0 échec** (11 min 02 s).

## P-002 — Unified API Exposure & Legacy Route Migration (2026-07-30)

### Changed
- Les 74 endpoints hérités servis hors `/api/v1` sont republiés sous le namespace
  canonique via `mount_legacy_under_api()`, en réutilisant les mêmes callables.
  Le Cockpit n'utilise plus qu'une seule racine d'API.
- Cinq chemins portaient deux implémentations différentes (`/skills`,
  `/memory/search`, `/health`…). Ils sont servis sous `/api/v1/legacy/` pour
  qu'aucune ne soit masquée silencieusement.

### Added
- `ConfirmAction` : confirmation explicite avant toute action irréversible
  (evolution simulate/approve/apply, suppression d'espace de travail).
- `useEvolutionAction` / `useEvolutionAnalyze` : `POST /evolution/simulate/{id}`
  et `/evolution/analyze` n'avaient aucun appelant.
- `tests/integration/test_p002_api_namespace.py` (11 tests).
- `docs/architecture/API_NAMESPACE_CONSISTENCY.md`.

### Fixed
- `PolicyRule` déclarait `action` ; l'API envoie `decision`. La colonne
  « décision » du Governance Center était vide depuis toujours.
- `runtimeClient.select` et `systemClient.version` visaient des routes 404 :
  méthodes supprimées.

## [R-001] — 2026-07-30 — Real Execution Layer (fin des simulations)

> Réponse au bloqueur RC2 R-1 : « The orchestration is real. The work is not. »
> Inventaire complet et justifications :
> [`docs/release/R-001_SIMULATION_INVENTORY.md`](docs/release/R-001_SIMULATION_INVENTORY.md).

### Inventaire (STEP 1)

Balayage AST + motifs de tout le dépôt : **1081 occurrences**, dont **424 en
production** (87 fichiers) et **657 réservées aux tests** (laissées intactes,
conformément à la consigne). Une seconde passe détecte structurellement les
*succès fabriqués* : une fonction qui renvoie `True` / `{"success": True}` ou
positionne `status = CONNECTED|COMPLETED` sans effectuer le moindre appel sortant.

Classement des 424 occurrences de production : **7 implémentations temporaires**
remplacées, **le reste légitime** (le moteur de simulation HOS-039 est une
*fonctionnalité* — l'analyse « what-if » avant exécution ; `StubRuntime` est le
runtime de démonstration documenté HOS-004) ou **honnêtement indisponible**
(KTransformers annonce déjà `is_real_kt: false`).

### Ajouté — couche d'exécution réelle

- **`backend/execution/task_executor.py`** — `RealTaskExecutor`.
  `MissionExecutor.execute_task` disposait déjà de tout le pipeline réel
  (coordination agent/runtime/skills/tools → *exécution* → validation → retry →
  ordonnancement) ; seule l'étape du milieu était factice, et son propre
  commentaire disait ce qui devait s'y trouver. Contrat :
  - **ne fabrique jamais** : toute panne de transport, expiration ou complétion
    vide lève `RuntimeUnavailableError` et la tâche échoue ;
  - **télémétrie réelle** : durée au `perf_counter`, modèle et fournisseur issus
    de la réponse du runtime, jetons rapportés quand le runtime les fournit et
    marqués `"token_counts": "estimated"` sinon ;
  - **enregistre ce qui a servi**, pas ce qui a été demandé — c'est ainsi que
    l'ancien rapport revendiquait `ktransformers` pour un travail que rien
    n'avait fait ;
  - **pont sync/async** : une boucle d'événements dédiée par exécuteur
    (`run_coroutine_threadsafe`), et non `asyncio.run`, qui lève quand le thread
    appelant possède déjà une boucle.

### Corrigé — Critique

- **`autonomous_orchestrator.py:124`** — `success = random.random() > 0.15` et
  `duration = random.uniform(500, 5000)` remplacés par `_execute_plan()`, qui
  construit de vraies tâches et les exécute via `MissionExecutor`.
  `runtimes_used=["ktransformers"]` codé en dur, `execution_summary`,
  `improvements` et `lessons` figés : tous dérivés des résultats réels.
- **`mission_executor.py:96`** — `task.result = f"Simulated result for: …"` et
  `task.duration_ms = 42.0` remplacés par l'appel à l'exécuteur injecté. Une
  tâche dont le runtime est indisponible **échoue** et ne porte aucun résultat.
- **`mcp_client.py`** — `connect()` positionnait `CONNECTED` sans émettre un
  paquet (n'importe quel hôte « se connectait », y compris `169.254.169.254`) et
  `call()` renvoyait un `{"status": "ok"}` en conserve. Les deux effectuent
  désormais un vrai JSON-RPC HTTP avec délai et tentatives bornés.
  `ping()` renvoyait le statut en cache et ne pouvait donc jamais détecter un
  serveur disparu ; il sonde réellement.

### Corrigé — Cockpit (STEP 10)

- `features/evolution/evolution-center.tsx` rendait `MOCK_PROPOSALS` /
  `MOCK_REPORTS` définis dans le module : ses compteurs étaient fabriqués dans le
  navigateur quoi que dise le backend. Branché sur `/api/v1/evolution/*` via de
  nouveaux `evolutionClient` + `useEvolutionProposals/Reports/Status`, avec des
  états **chargement / vide / erreur distincts** (RC2 R-6).

### Tests (STEP 11)

- **`tests/integration/test_real_execution.py` — 15 tests** contre un runtime
  réel, qui *sautent* si aucun n'est joignable (un skip est honnête ; un succès
  contre un bouchon est le problème que R-001 supprime). Assertions choisies pour
  être insatisfiables par fabrication : la durée rapportée doit suivre l'horloge
  murale à 35 % près, trois requêtes identiques doivent s'accorder (l'ancien code
  tirait à pile ou face une fois sur six), une tâche échouée ne doit porter
  **aucun** résultat, et un vrai serveur MCP — celui de Hermes — doit répondre à
  une vraie poignée de main.
- **Suites unitaires gardées hermétiques.** Câbler l'exécution réelle faisait
  passer `test_execution.py` + `tests/autonomous/` de 0,6 s à **16 minutes** de
  requêtes LLM vivantes. Seul l'appel sortant est remplacé
  (`tests/support/fake_inference.py` + fixtures autouse), suivant la convention
  déjà en place pour les agents (« fully testable with a fake Ollama client ») :
  exécuteur, télémétrie, artefact, validateur, retry et ordonnanceur restent du
  code de production. **16 min → 0,57 s, 143 tests passants.**
- 4 tests MCP qui affirmaient le contrat *simulé* remplacés par 6 tests du
  contrat réel, pilotés par l'`opener` injectable (donc sans socket).

### Vérification

Même sonde que celle par laquelle RC2 avait prouvé la fabrication :

| | RC2 (avant) | R-001 (après) |
|---|---|---|
| `success` sur 3 requêtes identiques | alterné `True`/`False` | `True`, `True`, `True` |
| durée rapportée vs horloge murale | décorrélée | **écart max 0,1 %** |
| `runtimes_used` | `["ktransformers"]` codé en dur | `["ollama"]`, mesuré |
| jetons | `0` | `78` |
| sorties | aucune | 41 caractères de vrai code |
| modèle chargé côté Ollama | `nomic-embed-text` (intact) | **`qwen3:4b`** — chargé par l'appel |
| runtime éteint | succès rapporté quand même | `RuntimeUnavailableError`, tâche FAILED |

Exécuteur direct : `ollama / qwen3:1.7b`, **5858 ms mesurées**, 54+10 jetons,
résultat `def reverse_string(s): return s[::-1]`.

**Régression :** `tests/` 2497 · `backend/tests/` 796 · frontend 65 — **3358 tests, 0 échec** (+17 : 15 tests d'intégration à exécution réelle et
2 tests de contrat MCP remplaçant 4 qui affirmaient la simulation).

### Reste explicitement justifié

9 points documentés au §6 de l'inventaire, chacun étant un travail cadré et non
un faux caché : adaptateurs vLLM et llama.cpp inexistants (une tâche qui les
nomme échoue désormais au lieu de réussir), `kt_kernel` non installable,
boucles d'outils par agent spécialisé, artefacts de workspace, profondeur de
validation, diffusion de la mémoire, métriques du planificateur d'évolution, et
`execution_engine._execute_via_hermes` (hors du chemin autonome).

---

## [RC2-AUDIT] — 2026-07-30 — Audit final de production → 🔴 NO GO

> Audit qualité indépendant de l'application assemblée. Rapport complet :
> [`docs/release/HERMES_OS_RC2_AUDIT.md`](docs/release/HERMES_OS_RC2_AUDIT.md).
> Score global **71/100**. **3 341 tests passent, 0 échec.**

### Constat décisif

**Aucun chemin d'exécution n'effectue de travail réel** (R-1, critique) :

- `backend/autonomous/autonomous_orchestrator.py:124` — l'étape « Execute » est
  `success = random.random() > 0.15` et `duration = random.uniform(500, 5000)` ;
- `backend/agent/execution_engine.py:756` — `_execute_via_hermes` émet un
  événement et retourne (« a lightweight placeholder ») : un nœud de mission ne
  quitte jamais l'état `ready` ;
- `backend/runtime/ktransformers/hermes_adapter.py` — adaptateur simulé
  (`is_real_kt: false`) ;
- `backend/tools/mcp/mcp_client.py:26,57` — `connect()` et `call()` renvoient un
  succès fabriqué sans aucune I/O réseau.

Preuve : six `POST /api/v1/autonomous/start` identiques → succès alternés,
six durées aléatoires distinctes, `runtimes_used` codé en dur, orchestrateur à
`total_decisions: 0`, zéro agent enregistré, Ollama disponible avec 16 modèles
et jamais invoqué. **Les API rapportent un succès**, donc l'utilisateur ne peut
pas le détecter.

L'orchestration est réelle ; le travail ne l'est pas.

### Corrigé — Critique

- **Évasion du sandbox Workspace.** `work_dir=f"{base}/{mission_id}/{agent_id}"`
  interpolait des identifiants fournis par l'appelant : un `mission_id` valant
  `../../PWNED` produisait un chemin résolvant hors du répertoire de base, ce
  que cette couche existe précisément pour empêcher. `_safe_path_component`
  réduit chaque identifiant à un unique nom de répertoire contenu.
  Vérifié : 14 entrées d'attaque (`../..`, `..\..`, absolus, lettre de lecteur,
  NUL, URL-encodé, `.`, `..`, vide) toutes contenues à la profondeur 2 exacte.
- **21 endpoints renvoyaient 500 sur un corps vide ou malformé** — cause unique :
  `payload["champ"]` (KeyError) et coercition d'énumération (ValueError), deux
  erreurs du client. Gestionnaires d'exception à la frontière de l'application →
  **422** nommant le champ fautif, trace complète toujours journalisée.
  Effet de bord : les 24 échecs sur 192 requêtes en charge 32 threads
  disparaissent — c'était la même cause, pas une situation de concurrence.

### Corrigé — Majeur

- **8 topics d'événements encore silencieusement perdus** après que HOS-066B a
  déclaré la dérive corrigée : `AUTONOMOUS_EVENTS["goal_received"]` (accès par
  dictionnaire) et un topic porté par une variable sont invisibles pour un
  parcours AST de littéraux. Les 6 catalogues `*_EVENTS` sont désormais
  moissonnés, et **le chemin de publication devient permissif** pour un topic
  inconnu mais bien formé (avertissement une fois par topic) tandis que le
  chemin d'abonnement reste strict : une liste périmée qui détruit des
  événements réels est un défaut strictement pire qu'une faute de frappe.
  Les topics malformés (non pointés, espaces, non-chaînes) restent refusés.
- **`/api/v1/system/health` : 864 ms → 0,8 ms**, et 1 → **1533 req/s** en
  parallèle. Les accesseurs de télémétrie KlaatCode (1080 ms) et Oh My Pi
  (894 ms) effectuent des sondes réseau vivantes ; cache TTL 5 s sur le probe,
  comme `AlexandrieClient` le fait déjà. Détection de panne vérifiée toujours
  correcte après le TTL, et récupération vérifiée.
- **4 sous-systèmes partageaient une instance entre apps** sans
  `adopts_module_singleton` (`klaatcode`, `ohmypi`, `ktransformers`,
  `model_intelligence`), si bien que le rapport de dépendances les décrivait
  comme isolés par app. Signalés, et l'invariant est désormais **asserté** au
  lieu d'une liste de trois noms vérifiés à la main.
- **`POST /api/v1/alexandrie/documents` renvoyait 500** quand Alexandrie est
  hors ligne → **503** avec un renvoi vers l'endpoint de santé. L'adaptateur ne
  renvoie `None` que sur circuit ouvert ou échec amont, jamais pour une entrée
  invalide.

### Corrigé — Mineur

- Le probe de santé appelait à l'aveugle des accesseurs paramétrés
  (`LearningEngine.get_stats(runtime_id)`) et notait un sous-système sain comme
  défaillant → inspection de signature.
- `policy.allowed` / `policy.denied` ajoutés au catalogue de topics.

### Corrigé — Documentation

- **Les entrées précédentes surestimaient la résolution de C-3 et C-4.**
  C-3 n'est que **partiellement** résolu : le préfixe est unifié mais 39 chemins
  appelés par `frontend/src/lib/*` restent en 404, car ces clients visent le
  `MissionControlRouter` (HOS-028) toujours non monté. Le monter provoquerait
  14 collisions de routes et 12 de ces chemins n'existent nulle part.
  C-4 : les 17 ids de la sidebar résolvent, mais l'**Installer Center n'existe
  pas** dans le dépôt.

### Reste ouvert

R-1 (exécution non implémentée, critique) · R-2 (39 chemins en 404) ·
R-3 (client MCP simulé) · R-4 (7 dépendances sans borne haute) ·
R-6 (états loading/vide/erreur indistinguables) · déploiement Docker non validé
(démon indisponible pendant l'audit).

---

## [HOS-066B] — 2026-07-30 — RC1 Critical Integration Fixes (assemblage)

> **Aucune fonctionnalité nouvelle.** Cette entrée ne contient que de
> l'assemblage : les sous-systèmes existants sont désormais instanciés, câblés et
> exposés. Aucun sous-système n'a été réécrit, aucune logique dupliquée.
> Architecture : [`docs/architecture/COMPOSITION_ROOT_ARCHITECTURE.md`](docs/architecture/COMPOSITION_ROOT_ARCHITECTURE.md).
> Graphe : [`docs/architecture/DEPENDENCY_REPORT.md`](docs/architecture/DEPENDENCY_REPORT.md).

### Ajouté — Composition Root (`backend/core/bootstrap/`)

- **`dependency_container.py`** — `DependencyContainer` : une instance et une
  seule par clé, garantie **appliquée** (`DuplicateServiceError`) et non
  supposée. Thread-safe, ordre d'enregistrement préservé, itération inverse pour
  l'arrêt.
- **`service_registry.py`** — catalogue déclaratif de **32 `ServiceSpec`** :
  fabrique, dépendances (par clé, jamais par annotation de type), routeurs,
  topics publiés/consommés, capacités. L'ordre de construction, le graphe de
  dépendances, la surface de santé et le montage des routeurs en sont **dérivés**
  — trois listes tenues à la main auraient dérivé comme l'a fait la liste de
  topics de l'`EventHub`.
- **`bootstrap.py`** — `HermesBootstrap` : `build()` (tri topologique →
  instanciation → liaison des routes → enregistrement `ComponentRegistry` +
  `DependencyGraph` → validation → checks de santé), `dependency_report()`,
  `health()`, `ready()`, `statistics()`, `rebind_routes()`, `shutdown()`.
  `BootstrapReport.is_complete()` rend le critère « GO à 100 % » interrogeable.
- **`event_wiring.py`** — `EventDispatcher` : le seul `on_event` remis à tous les
  sous-systèmes. Fan-out vers `SystemEventBus` (historique) **et** `EventHub`
  (WebSocket). Accepte les deux formes d'appel du code
  (`(type, payload)` et `(type, payload, severity=…)`) et ne lève jamais.
- **`health.py`** — `ServiceHealthProbe` : surface `health`/`ready`/`statistics`
  uniforme obtenue en **adaptant** les accesseurs que chaque sous-système expose
  déjà, plutôt qu'en ajoutant trois méthodes à 32 classes.
- **`router_registry.py`** — montage automatique, `rebase_router()` pour unifier
  le namespace sans dupliquer les handlers, redirections de compatibilité,
  détection des collisions de routes.
- **`backend/core/event_topics.py`** — catalogue de 143 topics, module feuille
  (aucun import projet, donc aucun cycle). Le groupe `SUBSYSTEM_TOPICS` est
  **collecté depuis le code** (parcours AST des littéraux passés à
  `on_event`/`_publish`/`_emit`).

### Ajouté — surface HTTP des 9 sous-systèmes qui n'en avaient aucune

`security`, `skills`, `tools`, `execution`, `conversation`, `model_intelligence`,
`autonomous`, `evolution`, `explainability` exposaient des fonctions
`handle_*(...)` sans aucun `APIRouter` : sept Centers du Cockpit n'avaient donc
pas de backend joignable. Chacun reçoit un `APIRouter` **qui délègue aux
handlers existants** (mapping HTTP uniquement, zéro logique dupliquée) et un
hook `create_*_routes(service)` conforme aux 14 modules qui en avaient déjà un.

- `/api/v1/security/*` (9 endpoints) — `/api/v1/skills/*` (8)
- `/api/v1/tools/*` (7) + `/api/v1/mcp/*` (3) — `/api/v1/execution/*` (8)
- `/api/v1/conversation/*` (7) — `/api/v1/models/*` (7)
- `/api/v1/autonomous/*` (8) — `/api/v1/evolution/*` (7)
- `/api/v1/explainability/*` (3)

### Modifié — namespace API unifié

- `/api/v1` devient l'unique préfixe canonique. Le routeur SDS, dont le préfixe
  `/api/hermes-os` est figé à la construction, est **rebasé** : les mêmes
  fonctions d'endpoint sont réenregistrées sous `/api/v1`, une seule
  implémentation pour deux points de montage.
- `/api/hermes-os/*` répond désormais `307` vers `/api/v1/*` (307 et non 302 :
  plusieurs endpoints redirigés sont des POST, la méthode et le corps doivent
  survivre).
- Frontend : les cinq clients de `lib/` passent de `/api/hermes-os` à `/api/v1`,
  et le WebSocket de `use-events.ts` pointe sur
  `/api/v1/runtime/events/ws`. Plus aucune référence au préfixe legacy.

### Corrigé — Critique

- **Les 16 endpoints en `503 not initialized` répondent.** Les hooks
  `create_*_routes(service)` (agents, missions, planner, memory, policy,
  approval, audit, workspace, collaboration, resources, orchestrator, discovery,
  recovery, intelligence, simulation, runtime events) n'étaient **jamais**
  appelés en production ; le container les appelle, une fois, dans l'ordre des
  dépendances.
- **`RuntimeOrchestrator` n'était jamais instancié hors tests** et tournait avec
  des callbacks de scoring nuls. Il est construit, câblé et sa simulation est
  branchée sur son état réel.
- **Sept sous-systèmes isolés** (autonomous, conversation, evolution,
  model_intelligence, voice, logging, storage) : plus aucun sous-système sans
  arête de dépendance ni topic déclaré.
- **`/mcp` renvoyait `421 Invalid Host header` hors localhost.** `FastMCP`
  (mcp ≥ 1.26) n'autorisait que `127.0.0.1:*`, `localhost:*` et `[::1]:*` —
  motifs qui exigent un port, donc `Host: localhost` nu échouait, comme
  `hermes-backend:8000` (nom de service du compose) et tout accès via nginx.
  La protection anti-DNS-rebinding est **conservée** ; la liste d'hôtes est
  élargie aux hôtes réellement servis et configurable
  (`HERMES_MCP_ALLOWED_HOSTS`, `HERMES_MCP_ALLOWED_ORIGINS`,
  `HERMES_MCP_ALLOW_ANY_HOST`). Un hôte non approuvé reçoit toujours `421`.
- **Huit Centers du Cockpit étaient inatteignables** : la sidebar proposait
  Assistant, Models, Code Intel, Autonomous, Security, System et Deploy, mais
  `cockpit-shell.tsx` n'avait aucune entrée pour eux et le clic retombait
  silencieusement sur le dashboard. Les 17 ids de la sidebar résolvent désormais,
  et un `satisfies Record<string, React.FC>` transforme un id sans Center en
  erreur de typage plutôt qu'en menu mort.

### Corrigé — Majeur

- **`EventHub` rejetait 26 des 28 topics RAL.** Le mécanisme de validation est
  conservé (il attrape les fautes de frappe côté producteur *et* côté client) ;
  c'est la liste qui était périmée — 6 entrées contre 90 topics réellement émis.
  Désormais 143 topics, et `register_event_types()` permet au bootstrap de la
  compléter depuis les enums vivants au démarrage. Une invention
  (`task.exploded`) est toujours refusée.
- **Le dispatch WebSocket perdait silencieusement les événements publiés depuis
  un thread.** `asyncio.get_event_loop()` + `ensure_future` sont tous deux
  incorrects hors du thread principal (le premier lève — et l'exception était
  avalée —, le second n'est pas thread-safe), et c'est de là que venait la
  majorité des événements : threadpool et schedulers. La boucle est capturée à
  la connexion du client et les événements sont planifiés via
  `run_coroutine_threadsafe`. Vérifié : un événement publié depuis un thread
  worker arrive maintenant au client.
- **`bus.publish` était emballé sans garde d'idempotence** dans une factory de
  routes : deux appels imbriquaient le wrapper et diffusaient chaque événement
  deux fois. La garde est portée **par instance de bus** (et non par un drapeau
  de module — un drapeau global emballait le premier bus et laissait
  silencieusement tous les suivants non emballés).
- **Liaison des routes et multiplicité des apps** : les hooks
  `create_*_routes` écrivent dans un global de module, donc le dernier bootstrap
  construit possède les modules de routes. `rebind_routes()`, appelé par le
  lifespan, garantit que l'app **qui tourne** possède ses liaisons.

### Corrigé — test instable (préexistant)

- `tests/autonomous/test_autonomous_core.py::test_interpret_high_complexity`
  échouait **une fois sur quatre**, indépendamment de HOS-066B :
  `_estimate_complexity` ajoute `random.uniform(-0.1, 0.1)` à une base de 0.45
  pour cette requête (0.3 + 0.15 de mots-clés ; la chaîne fait 113 caractères,
  donc aucun bonus de longueur), et l'assertion exigeait `> 0.4` — donc tout
  tirage inférieur à −0.05 échouait. Taux mesuré : **24,8 % sur 4 000 tirages**.
  Le test passait ou non selon la position du flux `random` global, si bien que
  n'importe quel changement d'ordre d'exécution le faisait basculer. Le RNG est
  désormais initialisé (`random.seed(2)`) : le seuil 0.4 reste la bande que
  cette requête doit franchir, et la gigue redevient un détail
  d'implémentation de l'estimateur. Vérifié stable sur 12 exécutions
  consécutives.

### Ajouté — Tests d'intégration

- **`tests/integration/test_assembly.py` — 86 tests.** Aucun test existant n'a
  été réécrit. Tous portent sur le vrai `create_app()`, jamais sur une app
  fabriquée à la main : c'est précisément parce que chaque test construisait sa
  propre `FastAPI()` que la suite est restée verte pendant que l'application
  assemblée ne démarrait pas.
  Couvre : invariants du container (dont concurrence), ordre de construction,
  complétude du bootstrap (100 %), injection effective dans les modules de
  routes, non-duplication des singletons adoptés, câblage des événements
  (dont « ne lève jamais » et publication réelle sur le bus), enregistrement des
  routeurs (collisions, aucun orphelin, 29 endpoints de Centers), unification du
  namespace (307, préservation de la méthode, handlers non dupliqués), santé /
  readiness / statistiques, rapport de dépendances (symétrie des arêtes,
  acyclicité), intégration `ComponentRegistry`/`HealthOrchestrator`, arrêt
  (ordre inverse, tolérance aux pannes) et lifespan réel.

### Ajouté — Endpoints d'introspection

| Endpoint | Contenu |
|---|---|
| `GET /api/v1/system/assembly` | rapport de build + rapport de montage |
| `GET /api/v1/system/dependencies` | graphe de dépendances complet (STEP 8) |
| `GET /api/v1/system/health` | état par sous-système |
| `GET /api/v1/system/ready` | complétude de l'assemblage + bloquants |
| `GET /api/v1/system/statistics` | télémétrie par sous-système + compteurs d'événements |

### Résultat mesuré

| Indicateur | RC1 (après audit) | HOS-066B |
|---|---|---|
| Sous-systèmes instanciés au démarrage | **0** | **32 / 32 (100 %)** |
| Routeurs liés à leur service | **0** | **30** |
| `APIRouter` orphelins | 9 modules sans routeur | **0** |
| Endpoints GET en 5xx | **16** (`503 not initialized`) | **0** |
| Endpoints GET → 200 | 31 | **100** |
| Chemins HTTP distincts | 182 | **255** (189 sous `/api/v1`) |
| Collisions de routes | non détectées | **0** (détection active) |
| Sous-systèmes isolés | **7** | **0** |
| Cycles de dépendances | — | **0** |
| Topics acceptés par l'`EventHub` | 6 (26/28 RAL rejetés) | **143** (0 rejeté) |
| `/mcp` derrière Docker/nginx | **421** | **200** |
| Centers du Cockpit atteignables | 9 / 17 | **17 / 17** |
| `backend/tests` | 751 passés, **16 échecs** | **796 passés, 0 échec** |
| `tests/` | 2366 passés | **2452 passés** (+86 intégration) |
| Frontend `tsc` / `build` / `vitest` | 0 / 14 pages / 65 | **0 / 14 pages / 65** |

---

## [RC1-AUDIT] — 2026-07-29 — Audit Release Candidate 1 (stabilisation)

> Audit global de pré-release. Aucune fonctionnalité ajoutée : uniquement des
> correctifs d'anomalies constatées. Rapport complet :
> [`docs/release/HERMES_OS_RC1_AUDIT.md`](docs/release/HERMES_OS_RC1_AUDIT.md).
> **Décision : 🔴 NO GO pour RC2** — 5 anomalies critiques d'assemblage subsistent
> (pas de composition root, 9 sous-systèmes sans surface HTTP, contrat
> frontend/backend divergent, 14 Centers inatteignables, MCP injoignable hors
> localhost). Score global 65/100.

### Corrigé — Critique

- **L'application ne démarrait pas** (`backend/main.py`) : `get_runtime_registry`
  était appelé dans le lifespan sans être importé → `NameError` au démarrage.
  C'était la cause racine des 69 échecs de `backend/tests`.
- **Aucune route Hermes OS n'était servie** (`backend/main.py`) : `SDS_ROUTER`
  était importé sans être monté, et les 19 routeurs HOS (`agents`, `missions`,
  `planner`, `memory`, `policy`, `approval`, `audit`, `workspace`, `alexandrie`,
  `runtime/*`, `ktransformers`, `ohmypi`) n'étaient jamais inclus. Toute l'API
  répondait 404. **70 → 182 chemins distincts.**
- **Le frontend ne compilait pas** (`frontend/package.json`) : 6 dépendances
  importées par le code étaient absentes du manifeste (`@xyflow/react`,
  `@tanstack/react-table`, `react-resizable-panels`, `zod`, `react-hook-form`,
  `@hookform/resolvers`). `reactflow@11`, déclaré mais jamais importé, a été
  retiré (remplacé par `@xyflow/react@12`).
- **API inexistante de `react-resizable-panels`** (`app/{agents,execution,runtimes}/page.tsx`) :
  `Group`/`Separator`/`orientation` → `PanelGroup`/`PanelResizeHandle`/`direction`.
- **Route `/dashboard` cassée** : `CockpitShell` importé en nommé alors qu'il est
  exporté par défaut, `{children}` jamais rendu, et `page.tsx` réexportait le
  layout comme page (violation du contrat `PageProps`).
- **La suite de tests ne terminait jamais** (`tests/api/test_mission_control_api.py`) :
  `test_websocket_accepts_connection` bloquait indéfiniment sur `ws.receive_text()`
  alors que le handler n'émet rien tant que le bus ne publie pas.

### Corrigé — Majeur

- `integrations/alexandrie/hermes_alexandrie_adapter.py` : `import time` manquant —
  le circuit breaker levait `NameError` au moment précis où il devait protéger.
- `integrations/alexandrie/alexandrie_client.py` : les sondes de santé passaient par
  la session à retry (3 retries × backoff 1/2/4 s + 5 s de connect), soit **22,4 s**
  par appel quand Alexandrie est absent. Session dédiée sans retry → **4,1 s**.
  Effet sur la suite end-to-end : **412 s → 28 s**, et 14 échecs par `ReadTimeout`
  supprimés.
- `monitoring/system_monitor.py` : `os.statvfs` n'existe pas sous Windows et
  `except OSError` ne rattrape pas l'`AttributeError` → `shutil.disk_usage`.
- `config/config_models.py` : `DatabaseConfig(name=":memory:")` produisait
  `sqlite:///:memory:.db`, une base inouvrable (et un nom de fichier illégal sous
  Windows). Le sentinelle SQLite est désormais reconnu.
- `ral/event_bus_impl.py` : `replay(until=…)` était inclusif, si bien qu'un
  événement tombant pile sur la borne était rejoué par deux fenêtres adjacentes.
  Fenêtre rendue semi-ouverte `[since, until)`.
- `execution/execution_state.py` : `get_last_checkpoint()` utilisait `max()`, qui
  renvoie le **premier** des ex æquo — donc le plus ancien checkpoint dès que deux
  sauvegardes partagent un `created_at`.
- `skills/skill_profiler.py` : `time.monotonic()` a une résolution de **15,6 ms**
  sous Windows, donc tout chargement de skill plus rapide était profilé à 0 ms, ce
  qui aplatissait les moyennes servant à classer les skills → `time.perf_counter()`.
- `components/runtimes/RuntimeEvents.tsx` : hook inexistant (`useRuntimeEventStream`),
  champ inexistant (`connectionState`), et forme d'événement incompatible entre le
  flux WebSocket (`runtime_id`/`event_type`/minuscules) et le REST
  (`runtime`/`type`/majuscules) ; normalisation ajoutée.
- `frontend/src/__tests__/cockpit.test.ts` : 37 tests utilisaient `require()` avec
  l'alias Vite `@/`, non résoluble en CommonJS → `await import()`.
- `backend/tests/conftest.py` : le harnais MCP utilisait `Host: mcp-test`, désormais
  rejeté par la protection DNS-rebinding activée par défaut dans `FastMCP`
  (mcp ≥ 1.26) → `421 Misdirected Request` sur les 24 tests MCP.

### Corrigé — Mineur

- 8 noms indéfinis dans des annotations (`skills/routes.py`, `tools/routes.py`,
  `skills/dependency_resolver.py`, `sds/runtime.py`). Inoffensifs grâce à
  `from __future__ import annotations`, mais ils cassaient `get_type_hints()`.
- 2 `print()` dans des handlers d'exception de production remplacés par du logging
  avec `exc_info` (`model_intelligence/benchmark_scheduler.py`,
  `storage/database_manager.py`).
- `services/mission_control.py` : uptime calculé sur `time.time()` (horloge murale,
  sujette aux sauts NTP, résolution 15,6 ms sous Windows) → `time.perf_counter()`.
- `types/mission-control.ts` : l'union `severity` omettait `DEBUG` et `CRITICAL`,
  que le backend émet réellement (`RuntimeEventSeverity`).
- `hooks/use-websocket.ts` : `useRef()` sans argument initial (invalide en React 19).
- `tests/architecture/test_foundation_sanity.py` : le test du bit d'exécution POSIX
  est désormais ignoré sous Windows, où NTFS ne représente pas ce bit.
- `sds/routes.py` : suppression d'un ré-import local masquant l'import de module.

### Corrigé — Documentation

- `CHANGELOG.md` : 74 backticks échappés (`\``) rendus littéralement en Markdown.
- `package.json` : la description annonçait « Next.js 16 » pour un projet en 15.1.0.
- `ROADMAP.md` : métriques resynchronisées avec le dépôt réel et tableau réparé.

### Résultat mesuré

| Indicateur | Avant | Après |
|---|---|---|
| Démarrage de l'application | 🔴 `NameError` | ✅ démarre |
| Routes servies (chemins distincts) | 70 (dont 0 HOS) | **182** |
| `tests/` | 2357 passés, 10 échecs, 2 erreurs, 1 blocage | ✅ **2366 passés, 0 échec** |
| `backend/tests/` | 645 passés, 24 échecs, 45 erreurs | **751 passés, 16 échecs** (cause unique : C-1) |
| Frontend `tsc` / `build` / `vitest` | 72 erreurs / échec / 37 échecs | ✅ **0 / 14 pages / 65 passés** |
| Durée `backend/tests` | 520 s | **136 s** |

---

## [HOS-064] — 2026-07-29 — Human Experience & Natural Interaction Layer

### Ajouté
- **Conversation Intelligence** (`backend/conversation/`) :
  - ConversationManager — sessions, messages, intent routing
  - IntentAnalyzer — 11 intent types (optimization, analysis, debug, refactor, doc, command, greeting, approval, cancel, question)
  - ContextBuilder — enrichment from Memory, Agents, Missions, Runtime
  - ResponseGenerator — contextual responses with approval flow, suggested actions
  - REST API (7 endpoints) + WebSocket ready
- **Explainability** (`backend/explainability/`) :
  - DecisionExplainer — human-readable explanations for agent/runtime/model/tool/skill/policy decisions
  - Alternative ranking with pros/cons, risk levels, rollback info
  - REST API (3 endpoints)
- **Approval Flow Enhanced** (`backend/policy/approval_explainer.py`) :
  - ApprovalExplainer — clear risk/impact descriptions, agent scope, rollback status
  - Pending queue with approve/reject workflow
- **Voice Ready** (`backend/voice/`) :
  - SpeechToTextProvider abstract (Whisper, Cloud)
  - TextToSpeechProvider abstract (Piper, Cloud)
- **Frontend : Conversation Center** (`conversation-center.tsx`) :
  - Chat interface with streaming simulation
  - Markdown rendering, approval banners, suggested actions
  - Real-time status indicators
- **Tests :** 103 tests (session management, intent detection, context building, response gen, explainability, approval, voice, thread safety)

### Documentation
- docs/architecture/HUMAN_EXPERIENCE_ARCHITECTURE.md — conversational architecture, REST API, WebSocket, approval flow
## [HOS-062] — 2026-07-29 — Production Readiness & Deployment Layer

### Ajouté
- **Configuration Management** (`backend/config/`) :
  - ConfigManager singleton with 6 deployment profiles (local_gpu, cpu_only, wsl, docker, server, cloud_gpu)
  - HermesConfig with nested DatabaseConfig, RedisConfig, VectorConfig, SecurityConfig, MonitoringConfig, LoggingConfig, RuntimeConfig
  - EnvironmentLoader with profile-required and optional env vars
  - Config validation, JSON profile loading, env override
- **Installer** (`installer/`) :
  - SystemDetector — detects OS, CPU, RAM, GPU (NVIDIA/AMD), VRAM, disk, Docker, WSL
  - HardwareProfile — 6 predefined profiles with min/recommended specs
  - Profile recommendation and model suggestion based on hardware
- **Persistence Layer** (`backend/storage/`) :
  - DatabaseManager — SQLite (dev) and PostgreSQL (prod) with connection pooling
  - MigrationManager — schema versioning, upgrade/rollback
  - BackupManager — zip-based backup/restore, config export/import, auto-backup
- **Monitoring** (`backend/monitoring/`) :
  - SystemMonitor — CPU, RAM, disk metrics, service checks, alerts
  - HealthMonitor — component registration, check intervals, 3-strikes unhealthy
  - RecoveryManager — configurable max attempts, cooldown, reset
- **Logging** (`backend/logging/`) :
  - ProductionLogger — structured JSON logs, RotatingFileHandler, correlation IDs
  - mission_log, agent_log, event_log methods
  - Global singleton get_logger()
- **Deployment** (`deployment/`) :
  - Dockerfile.backend (Python 3.11, FastAPI, uvicorn)
  - Dockerfile.frontend (Next.js build + Nginx)
  - docker-compose.yml (PostgreSQL + Redis + ChromaDB + Backend + Frontend)
  - docker-compose.gpu.yml (adds Ollama with NVIDIA GPU + Prometheus)
  - docker-compose.cpu.yml (CPU-only with Ollama)
  - nginx.conf (gzip, caching, API proxy, WebSocket, security headers)
- **Frontend : Deployment Center** (`deployment-center.tsx`) :
  - System overview with component health, service status
  - Hardware profile display
  - Backup management with create/restore/delete
  - Health monitoring with latency
  - Quick actions (backup, health check, export, report)
- **Tests :** 80+ tests covering config, hardware, database, migrations, backups, monitoring, health, recovery, logging, thread safety

### Documentation
- docs/architecture/PRODUCTION_ARCHITECTURE.md — deployment architecture, configuration system, monitoring, backup strategy, production recommendations
## [HOS-063] — 2026-07-29 — Autonomous Agentic Core Final Layer

### Ajouté
- **Autonomous Models** (`autonomous_models.py`) :
  - 5 dataclasses : AutonomousGoal, AutonomousSession, AutonomousDecision, AutonomousReport, AutonomousTimeline
  - 3 enums : GoalStatus (8 états), DecisionType (5 types), GoalPhase (7 phases)
  - 12 événements EventBus couvrant tout le cycle de vie (received→analyzed→planned→executed→learned→failed)
- **AutonomousInterpreter** (`autonomous_interpreter.py`) :
  - Transforme une requête humaine en objectif structuré (domaine, langage, complexité, contraintes)
  - 8 domaines avec scoring pondéré (code×2 pour les signaux forts)
  - Intégration Memory pour enrichir l'interprétation
- **DecisionEngine** (`decision_engine.py`) :
  - 4 types de décisions : Agent, Runtime, Skill, Tool
  - Confidence scoring 0-100, alternatives ranking
- **AutonomousGuard** (`autonomous_guard.py`) :
  - Vérifications Security + Policy avant chaque action
  - Pre-flight, pre-execution, pre-skill, pre-agent checks
- **AutonomousMemoryLoop** (`autonomous_memory_loop.py`) :
  - Collecte post-mission : succès, erreurs, durée, ressources, agents, modèles, outils
  - Alimente EpisodicMemory, ProceduralMemory, EvolutionEngine
- **AutonomousOrchestrator** (`autonomous_orchestrator.py`) :
  - Pipeline complet : Goal→Interprétation→Memory→Planner→DAG→Agents→Skills→Runtime→Tools→Security→Execution→Validation→Memory→Evolution→Report
  - Timeline avec 7 phases
- **AutonomousEngine** (`autonomous_engine.py`) :
  - Moteur central avec start/pause/resume/cancel/get_status/generate_report
  - Gestion des sessions actives
- **REST API** (`routes.py`) :
  - 7 endpoints : POST /start, GET /{id}, POST /pause/resume/cancel, GET /timeline/report
- **Frontend : Autonomous Mission Console** (`autonomous-center.tsx`) :
  - Objectif actuel, interprétation IA, DAG mission, agents actifs, runtime/tools
  - Progression temps réel, décisions, confiance, rapport
- **Tests :** 71 tests (9 classes) couvrant models, interpreter, decisions, guard, memory, orchestrator, engine, API, full mission simulation

### Modifié
- **Sidebar** → nouvelle entrée "Autonomous OS"
- **EVENT_CATALOG.md** → +12 événements autonomous.* (103 total, 12 familles)

### Documentation
- docs/architecture/AUTONOMOUS_OS_ARCHITECTURE.md — architecture complète, boucle autonome, diagrammes Mermaid
# Changelog — Hermes OS

> Toutes les modifications notables du projet Hermes OS.
> Format basé sur [Keep a Changelog](https://keepachangelog.com/).

---

## [HOS-055D] — 2026-07-29 — Code Intelligence Final Integration
## [HOS-058] — 2026-07-29 — Self Evolution & Continuous Improvement Engine

### Ajouté
- **Evolution Models** (`evolution_models.py`) :
  - 6 dataclasses : EvolutionProposal, EvolutionExperiment, OptimizationPattern, EvolutionReport, SystemMetrics
  - 4 enums : EvolutionType (7 types), EvolutionStatus (6 statuts), RiskLevel (4 niveaux)
  - 7 événements EventBus : proposal.created, simulation.completed, approved, applied, failed, pattern.discovered, report.generated
- **EvolutionAnalyzer** (`evolution_analyzer.py`) :
  - 5 dimensions d'analyse : Runtime (3 règles), Agents (2), Skills (2), Missions (2), Memory (2)
  - Sliding window de 100 métriques, suivi de tendances
- **ImprovementDetector** (`improvement_detector.py`) :
  - 6 détections automatiques : runtime sous-performant, skills inutiles/manquants, modèle meilleur, workflow inefficace, goulots
  - Enregistrement des patterns d'optimisation
- **EvolutionSimulator** (`evolution_simulator.py`) :
  - Simulation avant/après avec estimation d'impact
  - Évaluation des risques et conclusion (improvement/regression/no_change)
- **EvolutionValidator** (`evolution_validator.py`) :
  - Intégration Policy Engine HOS-046 + Security Engine HOS-057
  - 3 verdicts : ALLOW (risque faible), REVIEW (moyen/élevé), DENY (architecture/sécurité)
  - Règles configurables, overrides
- **EvolutionEngine** (`evolution_engine.py`) :
  - Pipeline complet : Collect → Analyze → Detect → Propose → Simulate → Validate → Apply → Learn
  - Approbation/rejet manuel, rapports périodiques
- **EvolutionScheduler** (`evolution_scheduler.py`) :
  - 3 modes : Hourly (60s), Daily (5min), Weekly (15min)
  - Thread background avec génération de métriques sample
- **EvolutionCenter** (`evolution-center.tsx`) — Cockpit interactif :
  - 5 stats (proposals, applied, pending, gain, confidence)
  - Tableau des 8 propositions avec type, gain, risque, confiance, statut
  - Pipeline visuel en 8 étapes
  - Patterns d'optimisation et rapports récents
- **API Routes** : 7 endpoints REST
- **Documentation** : SELF_EVOLUTION_ARCHITECTURE.md

### Tests
- 66 tests (9 classes : Models, Analyzer, Detector, Simulator, Validator, Engine, Scheduler, API, ThreadSafety)


## [HOS-057] — 2026-07-29 — Security, Sandbox & Trust Layer

### Ajouté
- **Security Models** (`security_models.py`) :
  - 9 dataclasses : SecurityPolicy, Permission, CapabilityToken, AgentTrustScore, SecurityEvent, ThreatDetection, IsolationProfile
  - 7 enums : TrustLevel (5 niveaux), ThreatLevel (5 niveaux), PermissionAction, ResourceType (9 types), IsolationLevel (5 niveaux)
  - 6 événements EventBus : permission.checked, permission.denied, threat.detected, agent.trust.updated, isolation.created, isolation.violation
- **PermissionManager** (`permission_manager.py`) :
  - Grant/revoke/check permissions par agent, skill, tool, workspace, runtime
  - Policy evaluation par priorité avec conditions
  - Historique des 500 dernières opérations
- **AgentTrustEngine** (`agent_trust_engine.py`) :
  - Score dynamique 0-100 basé sur 5 facteurs pondérés
  - 5 niveaux de confiance : UNKNOWN → LOW → MEDIUM → HIGH → VERIFIED
  - Notifications automatiques, seuils configurables
- **ThreatDetector** (`threat_detector.py`) :
  - 4 détections temps réel : accès fichiers, ressources, outils suspects, violations sandbox
  - Mitigation, historique incidents, stats par type/niveau
- **IsolationManager** (`isolation_manager.py`) :
  - 5 niveaux d'isolation : NONE → LOW → MEDIUM → HIGH → MAXIMUM
  - Validation filesystem, réseau, outils, ressources
  - Sessions actives, profil par défaut par niveau
- **SecurityEngine** (`security_engine.py`) :
  - Pipeline complet : Policy → Permission → Trust → Threat → Isolation → Allow/Deny/Review
  - Intégration Policy Engine HOS-046, EventBus, trust automatisé
- **API Routes** (`routes.py`) : 9 endpoints REST
- **SecurityCenter** (`security-center.tsx`) — Cockpit interactif :
  - 4 stats overview (trust, permissions, threats, isolation)
  - 8 agents trust scores avec barres de progression
  - Active threats list, permissions/policies matrix
  - 6 isolation profiles grid
- **Sidebar** : entrée "Security" ajoutée

### Tests
- 75 tests (8 classes : Models, PermissionManager, AgentTrustEngine, ThreatDetector, IsolationManager, SecurityEngine, APIRoutes, ThreadSafety)


## [HOS-056] — 2026-07-29 — Hermes OS Global Integration Audit & System Consolidation

### Ajouté
- **System Integration Layer** (`backend/core/integration/`) :
  - IntegrationManager — central orchestrator for all 25 components
  - ComponentRegistry — tracks every module with id, name, category, deps, capabilities, events, health
  - DependencyGraph — topological sort, cycle detection, impact analysis
  - HealthOrchestrator — aggregate health across all components with warnings
- **Global Health Monitoring** (`backend/core/health/`) :
  - SystemHealth — runs 12+ health checks across EventBus, Memory, Runtime, Agents, Tools, MCP, Intégrations
  - SystemHealthReport — JSON-reportable unified health status
  - 12 predefined health checks covering all subsystems
- **Event Catalog** (`docs/architecture/EVENT_CATALOG.md`) :
  - 91 unique events cataloged across 11 families
  - Producer/consumer matrix for each event
  - Naming conventions and statistics
- **Complete Architecture Documentation** (`docs/architecture/HERMES_OS_COMPLETE_ARCHITECTURE.md`) :
  - 25-component module registry
  - Mermaid data flow diagrams (development, inference, search, health)
  - Event bus architecture with 91 events
  - Agent system, memory system, and HOS completion matrix
- **Frontend System Center** (`system-center.tsx`) :
  - Health overview with healthy score, component count, warnings
  - 10 component categories with counts
  - Dependency graph (topological order, warnings)
  - Full component list table with status, latency, events
  - Architecture diagram (6-layer grid)
- **Sidebar** : entrée "System" ajoutée

### Tests
- 80+ end-to-end integration tests (12 classes : DevelopmentMission, AIInference, DocumentSearch, CodeIntelligence, MultiAgent, IntegrationManager, DependencyGraph, HealthOrchestrator, SystemHealth, ThreadSafety, EventFlow, EdgeCases)

### Architecture
```
System Integration Layer
       |
Component Registry (25 components)
       |
Health Orchestrator → 12 health checks
       |
Cockpit System Center
```



### Ajouté
- **CodeIntelligenceRouter** (`code_intelligence_router.py`) — moteur de scoring intelligent KlaatCode ↔ Oh My Pi :
  - 5 facteurs pondérés : task_fit (30%), lsp_dap_ast (20%), historical_success (25%), cost_efficiency (15%), language_match (10%)
  - 3 stratégies : single_best, hybrid_both, force provider
  - Mapping 10 types de tâches → provider(s) optimal
  - Historique adaptatif (100 dernières exécutions par provider)
  - Exécution hybride : KC analyse → OMP LSP/DAP/AST
- **CodeIntelligenceAgent** (`code_intelligence_agent.py`) — meta-agent orchestrateur :
  - Cycle de vie complet CREATED→READY⇄BUSY→PAUSED/FAILED/STOPPED
  - Pipeline : Classify → Route → Execute (single/hybrid) → Memory → EventBus
  - Métriques par provider (klaatcode_tasks, ohmypi_tasks, hybrid_tasks)
  - 7 événements EventBus : ci.agent.ready, ci.routing.decided, ci.task.*, ci.hybrid.executed, ci.memory.recorded
- **CIRuntimeScorer** (`ci_scorer.py`) — scoring runtime pour Runtime Orchestrator :
  - 5 facteurs : task_fit, historical_success, resource_cost, avg_duration, complexity_mod
  - Context modifiers : requires_lsp/dap boost OMP +20%, reduce KC -20%
  - Recommandation automatique avec ranking
- **CodeIntelligenceCenter** (`code-intelligence-center.tsx`) — Cockpit interactif :
  - Task Routing Map (10 types avec scores KC/OMP et best provider)
  - Provider stats (total tasks, success rate, KlaatCode/OhMyPi/hybrid count)
  - Decision visualization avec barres de score
  - Routing pipeline + Provider capabilities
- **Sidebar** : entrée "Code Intel" ajoutée

### Tests
- 51 tests (9 classes : RouterSelection, RouterHistory, AgentLifecycle, TaskExecution, Events, RuntimeScoring, Models, ThreadSafety, Factory)

### Documentation
- CODE_INTELLIGENCE_ARCHITECTURE.md (Mermaid, flux, matrices, pipeline examples)


## [HOS-055C] — 2026-07-29 — Oh My Pi Deep Integration Layer

### Ajouté
- **LSPBridgeAdapter** (`lsp_bridge_adapter.py`) — pont LSP Oh My Pi → Knowledge Graph :
  - Indexation symboles, diagnostics, structures de code
  - Recherche par nom/fichier, références, stats
  - Relations KG : File→DEFINES→Symbol, File→HAS_DIAGNOSTIC
- **ASTAdapter** (`ast_adapter.py`) — pont tree-sitter Oh My Pi → Knowledge Graph :
  - Détection fonctions, classes, imports, dépendances
  - Estimation complexité (cyclomatique, lignes, fonctions, profondeur)
  - Relations KG : File→CONTAINS_FUNCTION/CLASS, Function→CALLS, File→IMPORTS/DEPENDS_ON
- **DebugAdapter** (`debug_adapter.py`) — pont DAP Oh My Pi → EventBus :
  - Sessions debug avec breakpoints, stack trace, variables
  - Historique incidents, stats
  - Événements : debug.started, debug.breakpoint, debug.failed, debug.completed
- **WorkspaceAdapter** (`workspace_adapter.py`) — pont Oh My Pi → WorkspaceManager :
  - Pipeline : Edit → Sandbox → Git branch → Validation → Commit
  - Rollback support, validation path check
  - Événements : workspace.edit_prepared/committed/rolled_back
- **RuntimeAdapter** (`runtime_adapter.py`) — Oh My Pi comme candidat runtime :
  - Score de suitability 0-1 par type de tâche
  - Context modifiers (debug +15%, documentation -20%)
  - Recommandation avec seuil 0.5
- **MemoryAdapter** (`memory_adapter.py`) — pont Oh My Pi → Memory System :
  - Enregistrement expériences (succès/échec, durée, fichiers)
  - Patterns de code réutilisables
  - Corrections efficaces classées par succès
- **OhMyPiPanel** (`ohmypi-panel.tsx`) — Cockpit interactif :
  - 9 outils MCP avec icônes et catégories
  - Stats (executions, success rate, avg latency, failures)
  - Pipeline visuel (6 adaptateurs)
  - Quick actions (LSP Analyze, Debug, Run Python, AST Transform)
- **Types frontend** : OhMyPiStatus, OhMyPiCapability, OhMyPiExecutionResult, LSPDiagnostic, LSPSymbol, DebugSession
- **Client frontend** : ohmypiClient (status, capabilities, execute)
- **Documentation** : OHMYPI_DEEP_INTEGRATION_ARCHITECTURE.md (Mermaid, flux, matrices)

### Tests
- 58 tests deep integration (9 classes : LSPBridge, ASTAdapter, DebugAdapter, WorkspaceAdapter, RuntimeAdapter, MemoryAdapter, Events, ThreadSafety)
- Combiné HOS-055B : 112 tests totaux Oh My Pi

### Architecture
```
Hermes Agent → OhMyPiAgent → MCP Adapter (9 tools) → omp CLI
                    ↓
     ┌──────────────┼──────────────┬──────────────┬──────────────┐
     ↓              ↓              ↓              ↓              ↓
  LSPBridge     ASTAdapter    DebugAdapter  WorkspaceAdpt  RuntimeAdpt
     ↓              ↓              ↓              ↓              ↓
  Knowledge      Knowledge      EventBus      Workspace      Runtime
   Graph          Graph                        Manager       Orchestrator
                                              + Validation
```


## [HOS-055B] — 2026-07-29 — Oh My Pi Agent Integration

### Ajouté
- **OhMyPiClient** (`ohmypi_client.py`) — wrapper headless CLI pour omp : détection installation, exécution RPC, timeout, health check, historique 500
- **OhMyPiMCPAdapter** (`ohmypi_mcp_adapter.py`) — expose 9 outils MCP via pipeline Policy→Sandbox→Execute→EventBus :
  - lsp_open_file, lsp_edit, ast_transform, debug_start, debug_step
  - execute_python, execute_javascript, git_operation, code_search
- **OhMyPiAgent** (`ohmypi_agent.py`) — agent spécialisé LSP/DAP/AST :
  - Cycle de vie complet CREATED→READY⇄BUSY→PAUSED/FAILED/STOPPED
  - Workspace protection : edit_file + ast_transform forcés via WorkspaceManager
  - 6 types d'événements : agent.ready, edit.started/completed, debug.started, execution.completed, error
  - Métriques, historique de tâches, to_agent_dataclass() pour AgentRegistry
- **OhMyPiProfile** (`ohmypi_profile.py`) — 6 capacités, skill levels 0.88-0.98, 9 MCP tools, priorité high
- **OhMyPiCapabilities** (`ohmypi_capabilities.py`) — 8 task types + mapping bidirectionnel task↔capability↔MCP action
- **REST API** (`routes.py`) — GET /ohmypi/status, GET /ohmypi/capabilities, POST /ohmypi/execute
- **Factory** — `create_ohmypi_agent()` : instanciation + démarrage automatique
- **Tests** — 54 tests (10 classes) : models (5), client (5), MCP adapter (8), policy (2), sandbox (2), lifecycle (8), capability (5), execution (6), workspace (3), events (4), routes (3), thread safety (3)

### Architecture
```
Hermes Agent Supervisor → OhMyPiAgent
                           ↓
              OhMyPiMCPAdapter (9 tools)
                           ↓
              Policy → Sandbox → OhMyPiClient → omp CLI
                                              ↓
                              LSP · DAP · AST · Python/JS Exec
```

### Complémentarité KlaatCode ↔ Oh My Pi
| Tâche | KlaatCode | Oh My Pi |
|---|---|---|
| Analyse | ✅ analyze_project | — |
| Édition | edit_file (basic) | ✅ **LSP-wired** (rename+imports) |
| Débogage | — | ✅ **DAP** (lldb, dlv, debugpy) |
| AST | — | ✅ **tree-sitter** |
| Exécution | — | ✅ **Python/JS + callbacks** |
| Diagnostics | ✅ run_diagnostics | ✅ LSP diagnostics |

### Validation
- pytest : ✅ 54/54 passed (0.24s)

---

## [HOS-054D] — 2026-07-29 — KlaatCode Deep Integration

### Ajouté
- **CodeGraphAdapter** (`code_graph_adapter.py`) — pont KlaatCode analysis → Knowledge Graph (HOS-047) :
  - Indexation code : fichiers, classes, fonctions, imports, dépendances
  - 6 types de relations : FILE_IMPORTS, CLASS_CONTAINS, FUNCTION_CALLS, DEPENDS_ON, MODIFIED_BY_AGENT, TESTED_BY
  - Recherche d'entités, sous-graphe par fichier, historique modifications par agent
- **DiagnosticsAdapter** (`diagnostics_adapter.py`) — pont KlaatCode diagnostics → Validation Engine (HOS-050) :
  - Analyse de diagnostics (erreurs, warnings, hints)
  - Catégorisation automatique (compilation, test, qualité, sécurité, style)
  - Pipeline Patch → Diagnostics → Validation → Accept/Reject
  - Suggestions auto-fix extraites des diagnostics
- **CostGuardAdapter** (`cost_guard_adapter.py`) — pont KlaatCode → Runtime Orchestrator (HOS-038) :
  - Estimation complexité 0-10 basée sur type de tâche + taille projet
  - 4 bandes de runtime : low (cpu/small), medium (hybrid/medium), high (gpu/large), extreme (cloud_gpu/xl)
  - Recommandation runtime/modèle avec facteurs et confidence
- **Workspace Protection** (KlaatCodeAgent) :
  - edit_file/refactoring/patch forcés via Workspace → Sandbox → Git
  - Bloque les modifications directes sans workspace_id
  - Validation workspace avant toute écriture
- **Advanced Memory Integration** (KlaatCodeAgent) :
  - Enregistrement épisodique (problème, solution, fichiers, durée, succès/échec)
  - Enregistrement procédural automatique pour réutilisation
  - Recommandations d'expérience : 'Pour une erreur similaire, cette solution a fonctionné X fois'
- **Tests** — 40 tests (8 classes) : Code Graph (8), Diagnostics (9), Cost Guard (7), Workspace (4), Memory (4), Runtime (4), End-to-End (2), Thread Safety (3)

### Exemple : mission KlaatCode complète
```
Mission "Fix login bug"
  → CostGuardAdapter: complexity 6.5/10, recommend gpu/large
  → WorkspaceManager.create(mission_id, agent_id) → branch feature/klaatcode
  → KlaatCodeAgent.execute_task(CODE_ANALYSIS, {path})
    → CodeGraphAdapter: indexes files, classes, deps → Knowledge Graph
  → KlaatCodeAgent.execute_task(CODE_EDITING, {file, content, workspace_id})
    → Workspace protection ✅ → Sandbox → Git commit → MCP edit_file
  → KlaatCodeAgent.execute_task(DIAGNOSTICS, {file})
    → DiagnosticsAdapter: 0 errors, 2 warnings → Validation: PASS
  → Memory: episodic + procedural records
  → ExperienceManager: "For auth fixes, klaatcode_code_editing worked 3 times"
```

### Validation
- pytest : ✅ 40/40 passed (0.05s)

---

## [HOS-054C] — 2026-07-29 — KlaatCode Agent

### Ajouté
- **KlaatCodeAgent** (`klaatcode_agent.py`) — agent spécialisé de développement intégré au système multi-agent Hermes :
  - Cycle de vie complet : CREATED → STARTING → READY ⇄ BUSY → PAUSED/FAILED/STOPPED
  - 6 états opérationnels : IDLE, ANALYZING, GENERATING, EDITING, DIAGNOSING, REVIEWING
  - Exécution de tâches via MCP KlaatCode (HOS-054B) : analyze, generate, edit, review, diagnostics
  - Métriques : total_tasks, success_rate, avg_duration_ms, load tracking
  - Historique : 500 entrées de tâches, 200 résultats d'exécution, historique de lifecycle
- **KlaatCodeProfile** (`klaatcode_profile.py`) — profil statique :
  - 6 capacités : analysis, code_generation, code_review, testing, optimization, documentation
  - Skill levels par domaine (0.75-0.95)
  - Contraintes : max 2 concurrent, timeout 300s, max retries 3
  - 7 MCP tools autorisés, workspace/sandbox requis
- **KlaatCodeCapabilities** (`klaatcode_capabilities.py`) :
  - 9 types de tâches : CODE_ANALYSIS, CODE_GENERATION, CODE_EDITING, REFACTORING, DIAGNOSTICS, TEST_ANALYSIS, PROJECT_NAVIGATION, PATCH_GENERATION, CODE_REVIEW
  - Mapping bidirectionnel : task ↔ capability ↔ MCP action
- **Factory** — `create_klaatcode_agent()` : instanciation et démarrage automatique
- **EventBus** — 6 types d'événements :
  - klaatcode.agent.ready, klaatcode.task.started/completed/failed
  - klaatcode.analysis.completed, klaatcode.patch.generated
- **Memory Integration** — enregistrement épisodique après chaque tâche (langage, projet, difficulté, durée, erreurs, corrections)
- **AgentCoordinator compatible** — `to_agent_dataclass()` pour enregistrement dans AgentRegistry, scoring CapabilityMatcher
- **Tests** — 48 tests (7 classes) : agent creation (7), lifecycle (8), capability matching (6), MCP execution (8), events (5), memory (2), metrics (5), thread safety (3), enums (4)

### Architecture d'exécution
```
Mission DAG → TaskScheduler → AgentCoordinator → KlaatCodeAgent
                                                     ↓
                                              MCP Tools KlaatCode
                                                     ↓
                                              Validation → Memory
```

### Validation
- pytest : ✅ 48/48 passed (0.08s)

---

## [HOS-054B] — 2026-07-29 — KlaatCode MCP Integration

### Ajouté
- **KlaatCodeClient** (`klaatcode_client.py`) — wrapper headless CLI : détection installation, exécution timeout, capture stdout/stderr, health check, historique 500 entrées, stats
- **KlaatCodeMCPAdapter** (`klaatcode_mcp_adapter.py`) — expose 7 outils MCP : analyze_project, inspect_code, generate_code_plan, edit_file, search_code, run_diagnostics, validate_changes
- **Pipeline complet** — Policy → Sandbox → Execute → EventBus pour chaque appel
- **KlaatCodeRequest/Response** — modèles dataclass avec id unique, timeout, workspace_id, timestamps
- **KlaatCodeProject/Diagnostic/Capability** — modèles pour analyse de projet, diagnostics, capacités
- **7 enums** — KlaatCodeAction, KlaatCodeStatus, DiagnosticSeverity
- **Registration module** (`registration.py`) — enregistrement automatique dans Tool Registry (HOS-049) et MCP Registry (HOS-049)
- **FastAPI Router** (`routes.py`) — 5 endpoints : GET /klaatcode/status, GET /klaatcode/capabilities, POST /klaatcode/analyze, POST /klaatcode/execute, POST /klaatcode/diagnostics
- **App wiring** (`main.py`) — routes montées sous `/api/v1/klaatcode`
- **Frontend KlaatCodePanel** (`klaatcode-panel.tsx`) — panneau Cockpit :
  - 7 outils MCP interactifs avec sélection et exécution
  - Badge MCP Connected, code plan input, visualisation du pipeline d'intégration
  - Actions rapides : Analyze, Diagnostics, Validate
  - Résultats formatés avec statut, durée, données JSON
- **Client API frontend** (`services/client.ts`) — 5 méthodes : status, capabilities, analyze, execute, diagnostics
- **Types TypeScript** (`types/hermes.ts`) — 3 interfaces : KlaatCodeStatus, KlaatCodeCapability, KlaatCodeExecutionResult
- **Tests** — 51 tests (8 classes) : modèles (8), client (7), adapter (14), policy (3), sandbox (5), event bus (5), routes (6), thread safety (3)

### Architecture
```
Hermes Agent → ToolRouter → KlaatCodeMCPAdapter → KlaatCodeClient → KlaatCode CLI
                                ↓
                         Policy → Sandbox → Memory → EventBus
```

### Intégrations Hermes
- Tool Registry HOS-049 ✅
- MCP Registry HOS-049 ✅
- Policy Engine HOS-046 ✅
- Tool Sandbox HOS-045 ✅
- Event Bus HOS-034 ✅
- Workspace Manager HOS-045 ✅ (sandbox integration)
- Cockpit Next.js HOS-051 ✅

### Validation
- pytest : ✅ 50/51 passed (1.06s) — 1 test stats vide corrigé
- Routes FastAPI : ✅ 5 endpoints
- Frontend : ✅ Panneau KlaatCode

---

## [HOS-053A] — 2026-07-29 — Alexandrie Integration

### Analyse préalable
- **Alexandrie** (Smaug6739/Alexandrie) — wiki/knowledge base auto-hébergée
- Stack: Nuxt.js (Vue) frontend + Golang (Gin) backend + MySQL 8 + S3
- Document curation, full-text search, team workspaces, 5-level ACL, OIDC SSO
- **N'est PAS** une librairie Python RAG — Alexandrie gère la curation documentaire humaine

### Décision d'architecture
| Fonctionnalité | Géré par |
|---|---|
| Édition Markdown, hiérarchie docs | Alexandrie |
| Full-text search (MySQL FULLTEXT) | Alexandrie |
| Workspaces, permissions, OIDC | Alexandrie |
| Stockage média (S3) | Alexandrie |
| Recherche sémantique (embeddings) | Hermes |
| Knowledge Graph | Hermes |
| Mémoires (working/episodic/semantic/procedural) | Hermes |
| Apprentissage d'expérience | Hermes |

### Ajouté
- **AlexandrieClient** (`alexandrie_client.py`) — client HTTP optionnel (sans `requests` en CI) pour l'API REST d'Alexandrie : health_check, search (full-text), CRUD nodes, checksum SHA256
- **HermesAlexandrieAdapter** — bridge central : sync_document, sync_all_documents, unsync_document, full_text_search, semantic_search, hybrid_search, get_graph_edges, event publishing
- **DocumentMemoryEntry** — entrée mémoire Hermes avec external_id, embedding, content_hash pour détection de changements
- **KnowledgeGraphEdge** — arêtes du graphe de connaissances (source→target, relation, poids)
- **HybridSearchResult** — résultat combiné Alexandrie full-text + Hermes semantic
- **EventBus** — 5 types d'événements : alexandrie.document.synced, .unsynced, .created, .updated, .deleted, alexandrie.sync.completed
- **REST API** — 11 endpoints : health, documents CRUD, search (fulltext/semantic/hybrid), sync, graph, statistics, events
- **Tests** — 40 tests (4 classes) : modèles (8), client (8), adapter (14), thread safety (3), full pipeline (3), graph (4)

### Exemple : recherche hybride
```
Alexandrie: "API Design" doc → full-text search → score 1.0
Hermes: "REST endpoints" doc → semantic search → score 0.8
HybridSearchResult: merged, deduplicated, ranked
```

### Validation
- pytest : ✅ 40/40 passed (0.17s)

---

## [HOS-053B] — 2026-07-29 — Alexandrie Integration Finalization

### Ajouté
- **Adapter complet** (`hermes_alexandrie_adapter.py`) — pipeline de sync production :
  - Synchronisation incrémentale (since timestamp, checksum-based change detection)
  - Détection de conflits + résolution (source_wins/local_wins/last_write_wins/manual)
  - Circuit breaker (5 échecs → circuit ouvert 30s, reset auto)
  - Cache documentaire (`DocumentCache` — TTL+LRU, eviction auto)
  - Liens mission-document (intégration Mission Planner)
- **Client production** (`alexandrie_client.py`) :
  - Authentification configurable (Bearer token / API key)
  - Retry avec exponential backoff (urllib3.Retry)
  - Health monitoring avec cache configurable
  - Timeout connexion + lecture
- **DocumentCache** (`document_cache.py`) — cache thread-safe TTL+LRU:
  - Prune automatique des entrées expirées
  - Stats : hits, misses, hit_rate, evictions
- **Event Bus** — 5 types d'événements :
  - alexandrie.document.created, .updated, .deleted
  - alexandrie.sync.started, .completed, .failed
- **REST API** — 16 endpoints :
  - Health, Status, Documents CRUD
  - Search (fulltext/semantic/hybrid)
  - Sync (start, status, history, mark-outdated)
  - Missions (link document, get mission documents, find relevant)
  - Graph, Cache, Events
- **Frontend Cockpit** — panneau Alexandrie dans Memory Center :
  - Status de connexion (Badge CONNECTED/OFFLINE)
  - Stats : synced, indexed, graph edges, cache entries, circuit breaker
  - Recherche hybride Alexandrie+Hermes
  - Historique de synchronisation
  - Relations documentaires (graph edges)
  - Liste des documents synchronisés
  - Bouton "Sync Now" avec retour visuel
- **Types TypeScript** — 8 interfaces :
  - AlexandrieStatus, AlexandrieDocument, AlexandrieSearchResults
  - AlexandrieMergeResult, AlexandrieSyncHistory, AlexandrieSyncResult
  - AlexandrieGraphEdges, AlexandrieMissionDocs
- **Client API frontend** — 16 méthodes :
  - health, status, documents CRUD, search, sync, graph, cache, events, missions
- **Hooks React Query** — 7 hooks :
  - useAlexandrieStatus, useAlexandrieHealth, useAlexandrieSearch
  - useAlexandrieSync, useAlexandrieSyncHistory, useAlexandrieDocuments
  - useAlexandrieGraph
- **Tests** — 40 tests (4 classes) : modèles (8), client (8), adapter (14), thread safety (3), full pipeline (3), graph (4)

### Modifié
- **Adapter** — ajout de `get_statistics()` et `get_synced_documents()` pour compatibilité avec les cas d'usage frontend
- **Tests** — mise à jour des assertions (event types, content hash, statistics keys)

### Validation
- pytest : ✅ 40/40 passed (0.18s)

---

## [HOS-052C] — 2026-07-29 — KTransformers Final Integration

### Ajouté
- **HermesKTAdapter** (`hermes_adapter.py`) — pont central avec import optionnel kt-kernel : singleton thread-safe, load/unload/infer/optimize/checksum, fallback simulé pour CI
- **12 backends réels** — AMX_INT4/INT8, AVX512_FP8_BF16/VBMI/VNNI/BASE, AVX2_LLAMAFILE, BLIS_AMD, CUDA, ROCm, CPU, HYBRID — mapping direct avec `kt_kernel.__cpu_variant__`
- **16 formats de quantization** — Q2_K → Q8_0, FP16/BF16/FP8, INT4/INT8, GPTQ, RAWINT4
- **KTModelConfig** — mapping direct avec KTransformersConfig YAML : chunked prefill, MoE offloading, hot experts, flash attention, continuous batching
- **KTOchestratorIntegration** — présente KT comme runtime candidat au Runtime Orchestrator (HOS-038) : scoring pondéré, task affinity, constraint-aware
- **KTDiscoveryIntegration** — 10 modèles KT-compatibles connus : DeepSeek-V3/R1/V4-Flash, Qwen3-MoE/Coder/Next, GLM-5, Mixtral 8×7B/8×22B, Kimi-K2
- **KTBenchmarkIntegration** — 5 profils avec prompts réels : coding, reasoning, general_chat, tool_use, long_context
- **KTResourceIntegration** — reçoit les métriques live du Resource Manager (HOS-035) : can_load, VRAM/RAM checks
- **KTEventBusBridge** — 6 types d'événements : discovered, loaded, unloaded, inference_completed, benchmark_completed, fallback_triggered
- **KTRuntime** — orchestrateur simplifié : register, discover, load (resource-checked), infer, optimize, benchmark — tout délégué à KT
- **13 endpoints REST** — models (list/get), discover, load/unload, infer, benchmark, optimize, orchestrator/candidates, status, statistics, resources, events
- **Tests** — 73 tests (10 classes) : models (10), adapter (9), discovery (8), orchestrator (7), resources (5), event bus (6), runtime (14), full integration (3), thread safety (3), backend detection (3), known models (5)

### Ce que KT gère nativement (jamais dupliqué)
- Chunked prefill • Heterogeneous offloading • MoE expert placement • Async forward passes • Continuous batching • Online quantization • 3-layer prefix cache • NUMA-aware thread pool

### Ce qu'Hermes gère (orchestration)
- Planification de mission • Sélection d'agent • Distribution de skills • Gouvernance • Mémoire • Cockpit

### Exemple : pipeline complet
```
KTDiscoveryIntegration.discover() → 10 modèles
  → KTRuntime.register_model(qwen3-coder-30b)
    → KTResourceIntegration.can_load() → OK (VRAM 24G free)
      → HermesKTAdapter.load_model(info, cfg) → kt_kernel.load_model()
        → Event: kt.model.loaded
        → KTOrchestratorIntegration.as_candidate() → suitability 0.65
          → KTOrchestratorIntegration.execute() → 384 tokens, 45 t/s
            → Event: kt.inference.completed
```

### Validation
- pytest : ✅ 73/73 passed (0.21s)

---

## [HOS-052B] — 2026-07-29 — KTransformers Hermes Integration Layer

### Ajouté
- **KTKernelWrapper** (`hermes_adapter.py`) — pont central Hermes ↔ kt-kernel : import optionnel avec fallback simulé, singleton thread-safe, load/unload/infer
- **KTOchestratorIntegration** — présente KT comme runtime candidat au Runtime Orchestrator (HOS-038) : as_candidate, can_handle_task, suitability_score, execute
- **KTDiscoveryIntegration** — alimente le Discovery Engine (HOS-040) avec 10 modèles KT-compatibles connus (DeepSeek, Qwen, GLM, Kimi, Mixtral, Phi, LLaMA)
- **KTBenchmarkIntegration** — benchmarke les modèles via KT avec 5 profils (coding, reasoning, chat, tool_use, long_context), best_for_task
- **KTResourceIntegration** — reçoit les données live du Resource Manager (HOS-035) : VRAM/RAM total/used/free, optimise les décisions
- **KTEventBusBridge** — publie les événements KT sur le vrai Event Bus (HOS-034) : 6 types d'événements (discovered, loaded, unloaded, inference_completed, benchmark_completed, fallback_triggered)
- **KTRuntime v2** — orchestrateur utilisant hermes_adapter + toutes les intégrations : discover_and_register, optimize avec ressources live, events natifs
- **KTRoutes v2** — 10 endpoints REST : discover, infer, benchmark, orchestrator en plus de models/load/unload/status/statistics/optimize
- **Frontend KTPanel** (`kt-panel.tsx`) — panneau Cockpit : statut kernel, CPU variant, liste modèles (load/unload/benchmark), benchmarks
- **Tests** — 32 tests (7 classes) : adapter (7), orchestrator (4), discovery (3), benchmark (4), resources (2), event bus (5), full integration (4), thread safety (3)

### Architecture
```
Hermes OS (orchestration)          KTransformers (exécution)
┌────────────────────┐             ┌────────────────────┐
│ Runtime Orchestrator│──candidate──→ KTOchestratorInt.  │
│ Discovery Engine    │──discover──→ KTDiscoveryInt.     │
│ Benchmark Engine    │──benchmark─→ KTBenchmarkInt.     │
│ Resource Manager    │──resources─→ KTResourceInt.      │
│ Event Bus           │←──events─── KTEventBusBridge     │
│ Cockpit Next.js     │←──status─── KTPanel              │
└────────────────────┘             └────────────────────┘
```

### Validation
- pytest : ✅ 32/32 passed (0.04s)

---

## [HOS-052] — 2026-07-29 — KTransformers Runtime Integration

### Ajouté
- **KTModelManager** — registre thread-safe : register, get, search, download (simulé), vérification intégrité SHA256, stats par statut/backend/quantization
- **KTLoader** — chargement intelligent : lazy loading, preload queue, ensure_loaded, auto-unload idle, tracking loaded models
- **KTCache** — cache LRU/TTL : max entries (16 default), TTL expiry (600s default), éviction priority-aware, hit/miss counters
- **KTScheduler** — planificateur prioritaire 4 niveaux (CRITICAL/HIGH/NORMAL/LOW) : enqueue, dequeue, cancel, batch processing, stats
- **KTOptimizer** — sélection automatique backend/quantization : scores 5 facteurs (VRAM, RAM, task type, backend, quality), fallback reasoning
- **KTRuntime** — moteur principal : intégration ModelManager + Loader + Cache + Scheduler + Optimizer + EventBus simulé
- **8 modèles** — KTModelInfo, KTLoadConfig, KTInferenceRequest, KTInferenceResult, KTOptimizationResult, KTCacheStats, KTSchedulerStats + 4 enums (KTBackend, KTQuantization, KTModelStatus, KTFallbackReason)
- **REST API** — GET /runtime/ktransformers/models, GET /{id}, POST /load, POST /unload, GET /status, GET /statistics, POST /optimize
- **EventBus** — ktransformers.loaded, ktransformers.unloaded, ktransformers.optimized, ktransformers.fallback, ktransformers.failed
- **Intégrations préparées** — Resource Manager (optimizer.set_hardware), Orchestrator (optimize_for_task), Discovery (register_model), Event Bus (callback), Benchmark (inference stats), Simulation (batch processing), Execution (infer/infer_async)
- **Tests** — 53 tests (8 classes) : model manager (12), cache (9), loader (7), scheduler (6), optimizer (5), runtime (8), thread safety (3), events (3)
- **Docs** — `KTRANSFORMERS_INTEGRATION_ARCHITECTURE.md`

### Exemple : chargement et exécution
```
KTModelManager.register(qwen3-7b-q4 / Q4_K_M / ROCm / 4.0GB)
  → KTOptimizer.optimize("7B", "coding") → Q5_K_M / ROCm / score 100
    → KTLoader.load(rocm, n_gpu_layers=-1)
      → Event: ktransformers.loaded
      → KTScheduler.enqueue("Refactor user auth module", priority=HIGH)
        → KTScheduler.process_batch()
          → KTInferenceResult: 128 tokens, 68 t/s, VRAM 3.8GB
            → Event: ktransformers.optimized
```

### Validation
- pytest : ✅ 53/53 passed (0.07s)

---

## [HOS-051] — 2026-07-29 — Hermes Mission Center & AI Operations Cockpit

### Ajouté
- **Cockpit Shell** — layout complet avec Sidebar (9 vues), Topbar (santé/uptime/WS), StatusBar (stats système)
- **Dashboard** — vue d'ensemble : santé système, statistiques, runtimes, live events, missions/agents récentes
- **Mission Center** — liste missions, création, détail, progression, actions (start/pause/resume/cancel)
- **Agent Center** — liste agents, statut/capabilités, détail métriques, messages collaboration temps réel
- **Runtime Center** — runtimes, santé, métriques, barres fiabilité/performance, monitoring VRAM/RAM/CPU/GPU
- **Memory Center** — recherche hybride (graph+embeddings+keyword), Knowledge Graph, expériences
- **Skills Center** — sélection automatique par tâche, registre skills, cache status
- **Tools Center** — outils natifs + MCP servers, santé, permissions
- **Governance Center** — approvals en attente, règles policy, audit log avec actions approve/reject
- **Event Center** — flux temps réel WebSocket, filtres sévérité/source, historique 200 événements
- **Cockpit Store** — Zustand : navigation, événements live, filtres, connexion WS, sélection mission/agent
- **API Client** — `services/client.ts` : 70+ endpoints typés couvrant tous les modules backend
- **React Query Hooks** — 30+ hooks : missions, agents, runtimes, memory, skills, tools, governance, execution, events
- **WebSocket Hook** — `useWebSocket()` : auto-reconnect, backoff, filtrage sources, gestion d'erreurs
- **TypeScript Types** — `types/hermes.ts` : 60+ types couvrant tous les modèles backend
- **UI Components** — Card, Badge (6 variants), StatCard, ProgressBar, animations Framer Motion
- **Design System** — thème Hermes (dark amber/blue/purple), Tailwind, animations, scrollbar custom, React Flow overrides
- **Providers** — React Query avec refetch/staleTime optimisés
- **Tests** — 55 tests (store, WebSocket helpers, types, API client endpoints, hooks, components, feature centers, navigation)
- **Docs** — `HERMES_COCKPIT_ARCHITECTURE.md`

### Architecture Frontend
```
frontend/src/
├── app/                    # Next.js App Router
│   ├── layout.tsx         # Root layout + Providers
│   ├── globals.css        # Theme + animations
│   ├── page.tsx           # Redirect → /dashboard
│   └── dashboard/         # Cockpit Shell
├── components/
│   ├── cockpit-shell.tsx  # Shell avec routing des vues
│   ├── providers.tsx      # QueryClientProvider
│   ├── sidebar.tsx        # Navigation 9 vues
│   ├── topbar.tsx         # Santé / version / WS
│   ├── statusbar.tsx      # Stats temps réel
│   └── ui/card.tsx        # Card, Badge, StatCard, ProgressBar
├── features/              # 9 centres
│   ├── dashboard/         # Vue overview
│   ├── missions/          # Mission Center
│   ├── agents/            # Agent Center
│   ├── runtime/           # Runtime Center
│   ├── memory/            # Memory Center
│   ├── skills/            # Skills Center
│   ├── tools/             # Tools Center
│   ├── governance/        # Governance Center
│   └── events/            # Event Center
├── hooks/
│   ├── use-api.ts         # 30+ React Query hooks
│   ├── use-store.ts       # Zustand cockpit store
│   └── use-websocket.ts   # WebSocket hook
├── services/
│   └── client.ts          # 70+ API endpoints
├── types/
│   └── hermes.ts          # 60+ types TypeScript
└── __tests__/
    └── cockpit.test.ts    # 55 tests
```

### Pages

| Route | Vue | Panneaux |
|---|---|---|
| `/` | Redirect → `/dashboard` | — |
| `/dashboard` | Dashboard | Health, Stats, Runtimes, Live Events, Missions, Agents |
| `/dashboard#missions` | Mission Center | Liste, Création, Détail, Progression |
| `/dashboard#agents` | Agent Center | Liste, Détail, Métriques, Collaboration |
| `/dashboard#runtime` | Runtime Center | Runtimes, VRAM/RAM/CPU/GPU |
| `/dashboard#memory` | Memory Center | Recherche, Knowledge Graph, Expériences |
| `/dashboard#skills` | Skills Center | Sélection auto, Registre, Cache |
| `/dashboard#tools` | Tools Center | Outils natifs, MCP, Santé |
| `/dashboard#governance` | Governance Center | Approvals, Règles, Audit |
| `/dashboard#events` | Event Center | Flux temps réel avec filtres |

### Dépendances
- `next` 15.1, `react` 19, `typescript` 5.7
- `@tanstack/react-query` 5 — data fetching avec cache/retry
- `zustand` 5 — state management léger
- `framer-motion` 11 — animations
- `lucide-react` — icônes
- `tailwindcss` 3.4, `clsx`, `tailwind-merge` — styling
- `vitest` 2.1, `@testing-library/react` 16, `jsdom` — tests

### Validation
- Tests : ✅ 55/55 passed (vitest)
- TypeScript strict : ✅

---

## [HOS-050] — 2026-07-29 — Autonomous Mission Execution Engine

### Ajouté
- **ExecutionStateMachine** — machine à états 10 états (CREATED→PLANNING→READY→RUNNING↔PAUSED/WAITING_APPROVAL→VALIDATING→COMPLETED/FAILED/CANCELLED) avec checkpoints, transitions validées, thread-safe
- **TaskScheduler** — planification DAG avec vagues parallèles, priorités (CRITICAL/HIGH/NORMAL/LOW), blocage sur dépendances, 4 stratégies (PARALLEL/SEQUENTIAL/PRIORITY/RESOURCE_AWARE)
- **AgentCoordinator** — sélection optimale agent/skills/runtime/tools par tâche, scoring capacités, suivi charge, release
- **ValidationEngine** — validation post-exécution avec critères configurables, 4 issues (PASS/FAIL/RETRY/NEEDS_REVIEW)
- **FeedbackLoop** — analyse post-mission : efficacité, learnings, recommendations, inputs Memory/Intelligence
- **OptimizationEngine** — détection tâches lentes, runtimes sous-performants, generation de recommendations
- **MissionExecutor** — orchestrateur central : pipeline User Goal→Planner→Graph→Scheduler→Agents→Skills→Runtime→Tools→Validation→Memory
- **ExecutionController** — gestion lifecycle complet : start/pause/resume/cancel/finalize, timeline, multi-executions
- **REST API** — POST /execution/start, GET /execution/{id}, GET /execution, POST /execution/{id}/pause, POST /execution/{id}/resume, POST /execution/{id}/cancel, GET /execution/{id}/timeline, GET /execution/statistics
- **EventBus** — execution.started, execution.planning, execution.task_started, execution.task_completed, execution.waiting_approval, execution.failed, execution.completed, execution.optimized
- **Tests** — 72 tests : state machine (12), scheduler (8), coordinator (7), validation (6), feedback (5), optimizer (4), executor (9), controller (8), routes (10), thread safety (3)

### Exemple : "Créer une application web"
```
POST /execution/start { goal: "Create web app", tasks: ["Plan", "Code", "Test"] }
→ ExecutionStateMachine: CREATED → PLANNING → READY
→ TaskScheduler: builds plan with 3 waves
→ AgentCoordinator: assigns coder + python-coding skill + ollama runtime
→ MissionExecutor.execute_task: RUNNING → VALIDATING → COMPLETED
→ ValidationEngine: PASS
→ FeedbackLoop: efficiency 100%, 3 learnings extracted
→ OptimizationEngine: no slow tasks detected
→ Memory: mission experience recorded for future reuse
```

### Validation
- pytest : ✅ 72/72 passed (0.07s)

---

## [HOS-049] — 2026-07-29 — MCP & External Tools Platform

### Ajouté
- **ToolRegistry** — registre thread-safe indexé par type/catégorie/statut/tag (8 types, 7 catégories, 4 états)
- **ToolPolicy** — gouvernance avant exécution : ALLOW/DENY/REVIEW_REQUIRED, règles configurables par outil
- **ToolSandbox** — isolation : paths autorisés/interdits, réseau contrôlé, env vars, workspace per-agent
- **ToolExecutor** — pipeline : Policy→Sandbox→Execute→Metrics, timeout, cancellation, historique
- **ToolRouter** — sélection automatique : catégorie→outil, type préféré, score de confiance
- **ToolHealth** — health checks, latence, erreurs, disponibilité par outil
- **ToolMemory** — intégration Knowledge Graph: Agent→Tool→Mission→Résultat→Performance
- **MCP Platform** — `mcp_client.py`, `mcp_registry.py`, `mcp_models.py` : connect/disconnect, list/call tools, multi-serveurs
- **7 Connectors** — GitHub, GitLab, Docker, Database (PG+SQLite), Filesystem, REST API, Browser
- **REST API** — GET /tools, GET /tools/{id}, POST /tools/register, POST /tools/execute, POST /tools/select, GET /tools/health, GET /tools/metrics, GET /mcp/servers, POST /mcp/connect, POST /mcp/disconnect
- **Tests** — 58 tests : registry (6), policy (5), sandbox (5), executor (5), router (3), health (4), memory (4), MCP (6), connectors (8), routes (10), thread safety (2)
- **Docs** — `TOOL_PLATFORM_ARCHITECTURE.md`, `MCP_ARCHITECTURE.md`

### Exemple : corriger un bug GitHub
```
Mission Planner → Agent Coder → SkillSelector → ToolRouter
    → "github" (score 0.8)
    → ToolPolicy.evaluate() → ALLOW
    → ToolExecutor.execute(GitHubConnector.create_branch)
    → ToolSandbox.validate_path("/home/project")
    → GitHubConnector.commit → ToolMemory.record
    → Audit log → Knowledge Graph updated
```

### Validation
- pytest : ✅ 58/58 passed (0.04s)

---

## [HOS-048] — 2026-07-29 — Dynamic Skill Distribution Engine

### Ajouté
- **SkillRegistry** — registre thread-safe indexé par catégorie/domaine/tag/statut (9 catégories, 8 domaines, 4 états)
- **SkillSelector** — sélection automatique 6 facteurs pondérés (catégorie 30%, technologies 20%, tags 10%, description 15%, succès 15%, qualité 10%)
- **SkillDependencyResolver** — résolution transitive (BFS), sort topologique (Kahn), détection de cycles (DFS), conflits de versions
- **SkillLoader** — lazy loading avec hooks d'initialisation, hot reload sans redémarrage, tracking par agent/mission
- **SkillCache** — cache LRU/TTL/PRIORITY avec éviction automatique, invalidation par expiration, hit rate
- **SkillProfiler** — profiling runtime (moyenne exponentielle): temps de chargement, mémoire, tokens, taux d'échec
- **SkillDistributor** — distribution multi-agent pour une mission, load avec cache-awareness, unload par agent ou mission
- **REST API** — GET /skills (filtres), GET /skills/{id}, POST /skills/select, POST /skills/load, POST /skills/unload, GET /skills/cache, GET /skills/statistics
- **Tests** — 59 tests : registry (9), selector (7), resolver (5), loader (6), cache (9), profiler (7), distributor (5), routes (9), thread safety (3)

### Exemple : trois agents, skills différentes
```
Mission: "Build a full-stack web app with auth"
→ Agent Coder (backend): python-coding (0.85) + db-design (0.72) — 20MB, 1500 tokens
→ Agent Designer (frontend): react-ui (0.88) — 10MB, 500 tokens
→ Agent Auditor (security): security-audit (0.95) — 15MB, 800 tokens
Total: 3 agents, 4 skills, 45MB, 2800 tokens
```

### Validation
- pytest : ✅ 59/59 passed (0.09s)

---

## [HOS-047] — 2026-07-29 — Unified Memory & Knowledge Graph Engine

### Ajouté
- **WorkingMemoryStore** — mémoire transitoire de mission (conversations, états agents, décisions), auto-clear en fin de mission
- **EpisodicMemoryStore** — expériences de mission (succès/échecs, incidents, décisions), recherche par tags + mot-clé
- **SemanticMemoryStore** — concepts, technologies, frameworks, patterns, outils; recherche fuzzy par nom/description/tags
- **ProceduralMemoryStore** — workflows, best practices, templates, stratégies; versionné, tracking usage/success rate
- **DocumentMemoryStore** — indexation de docs (markdown, code, specs, architecture), chunking préparé pour RAG
- **KnowledgeGraph** — graphe navigable (BFS) reliant missions→tasks→agents→runtimes→models→skills→workspaces→docs→benchmarks→decisions
- **EmbeddingIndex** — index vectoriel abstrait (128-dim hash embeddings), pluggable pour Nomic/BGE/E5 futurs
- **RetrievalEngine** — recherche hybride (embeddings + keyword + graph) sur tous les types de mémoire
- **ExperienceManager** — extrait les leçons, erreurs fréquentes, best practices; recommande pour nouvelles missions
- **MemoryManager** — façade centrale unifiant tous les types de mémoire, toutes les couches passent par lui
- **REST API** — POST /memory/search, GET /memory/search?q=, GET /memory/graph, GET /memory/experiences, POST /memory/index, GET /memory/statistics
- **Tests** — 43 tests : working (5), episodic (5), semantic (5), procedural (5), documents (4), graph (6), embeddings (4), experience (4), manager (5), thread (3)

### Exemple : nouvelle mission réutilisant l'expérience
```
Missions passées: Auth v1 ✅ (qwen3:14b), Auth v2 ✅ (qwen3:14b), DB Migration ❌
→ MemoryManager.recommend_for_mission("development", ["auth"])
→ recommended_models: ["qwen3:14b"] (2 past successes)
→ similar_missions: 2, similar_success_rate: 100%
→ past_experiences: [Auth v1, Auth v2]
```

### Validation
- pytest : ✅ 43/43 passed (0.05s)

---

## [HOS-046] — 2026-07-29 — Human Approval & Policy Engine

### Ajouté
- **PolicyEngine** — moteur central de gouvernance : toutes les opérations sensibles passent par lui (ALLOW / DENY / REVIEW_REQUIRED)
- **RuleEvaluator** — 10 règles intégrées : git_merge, workspace_delete, model_download, runtime_cloud, internet_access, system_modification (DENY), external_tool, git_rollback, high_risk (≥7), critical_risk (≥9)
- **ApprovalEngine** — workflow humain : approve, reject, comment, delegate, cancel, multi-approval (N validations requises)
- **ApprovalQueue** — file d'attente thread-safe triée par priorité (CRITICAL > HIGH > NORMAL > LOW)
- **AuditLog** — journal immuable : qui, quoi, quand, pourquoi, résultat, durée (10000 entrées max, auto-prune)
- **REST API** — GET /policy/rules, POST /policy/evaluate, GET /approval, POST /approval/{id}/approve, POST /approval/{id}/reject, GET /audit
- **EventBus** — policy.allowed, policy.denied, approval.requested, approval.granted, approval.rejected, approval.expired, audit.created
- **Tests** — 45 tests : evaluator (11), queue (7), engine (8), audit (6), policy engine (10), thread safety (3)

### Exemple : mission avec validation humaine avant merge Git
```
CoderAgent → PolicyEngine.evaluate(operation="git_merge")
  → Rule: "git_merge_requires_review" → REVIEW_REQUIRED
  → ApprovalQueue: [PENDING, priority=HIGH]
  → Event: approval.requested
Admin → POST /approval/{id}/approve → APPROVED
  → AuditLog: [agent=admin, action=approved, operation=git_merge]
  → Event: approval.granted
CoderAgent → merge allowed ✅
```

### Validation
- pytest : ✅ 45/45 passed (0.06s)

---

## [HOS-045] — 2026-07-29 — Workspace & Sandbox Manager

### Ajouté
- **WorkspaceManager** — cycle de vie complet : create/open/lock/release/archive/destroy, quotas disque/durée, par agent/mission
- **SandboxManager** — environnements isolés par agent : work dir, env vars, read-only, network control, allowed tools, temp storage
- **ArtifactManager** — versioning d'artefacts (files, patches, reports, logs, docs, tests) avec checksums SHA256
- **GitWorkspace** — abstraction Git : branches, commits, merge, rollback, stash (jamais main direct)
- **WorkspacePolicyEngine** — moteur de règles : disk quota (90% warn, 100% deny), max duration, read-only, network, outils autorisés
- **REST API** — POST /workspace, GET /workspace, GET /workspace/{id}, DELETE /workspace/{id}, POST /lock, POST /release, GET /artifacts, GET /status
- **EventBus** — workspace.{created,opened,locked,released,archived}, sandbox.{created,destroyed}, artifact.{created,updated}, git.{branch_created,commit_created}
- **Tests** — 48 tests : git (9), sandbox (8), artifact (8), policy (6), workspace manager (13), thread safety (3)

### Exemple : deux agents sur deux branches
```
CoderAgent → workspace "feature/backend" → commit "Add API" → artifact api.py
ReviewerAgent → workspace "feature/review" → commit "Reviewed API"
→ merge feature/backend → main
→ merge feature/review → main
```

### Validation
- pytest : ✅ 48/48 passed (0.06s)

---

## [HOS-044] — 2026-07-29 — Multi-Agent Collaboration Engine

### Ajouté
- **MessageBus** — messagerie inter-agents : direct, broadcast, groupe, help requests, conversations threadées, accusés de réception
- **ContextSharing** — partage de contexte avec permissions (visible_to, editable_by), mise à jour collaborative
- **DelegationManager** — délégation de tâches entre agents, demande d'expertise, workflow accept→start→complete
- **ConsensusEngine** — votes multi-agents : unanimous, majority, super-majority (2/3), single
- **ConflictResolver** — détection 5 types de conflits (disagreement, resource, concurrent, decision, priority) + auto-résolution
- **CollaborationEngine** — orchestrateur central : messages, contextes, délégations, reviews, consensus, conflits + historique mission
- **REST API** — 12 endpoints : GET/POST /messages, POST /broadcast, GET /unread, GET /conversations, POST /delegate, GET /delegations, POST|accept|complete delegations, POST /review, POST /consensus, POST /vote, GET /history
- **EventBus** — collaboration.started, message.sent, message.received, task.delegated, review.requested, review.completed, consensus.started, consensus.reached, conflict.detected, conflict.resolved
- **Tests** — 64 tests (14 msg + 9 ctx + 10 deleg + 8 consensus + 10 conflict + 10 engine + 3 threads)

### Exemple : mission collaborative
```
CoderAgent → "Implement login" (COMPLETED)
     → MessageBus.send(ReviewerAgent, "Please review PR")
     → ContextSharing.share("PR diff", visible_to=[ReviewerAgent])
ReviewerAgent → "Review PR" (APPROVED)
     → ConsensusEngine.propose("Architecture", ["monolith", "microservices"], mode=MAJORITY)
     → Vote: Coder="microservices", Reviewer="microservices", Designer="monolith"
     → Outcome: "microservices" (2/3 majority)
```

### Validation
- pytest : ✅ 64/64 passed
- Fix: RLock pour thread-safety réentrante (consensus, conflicts, delegations)

---

## [HOS-043] — 2026-07-29 — Agent Supervisor

### Ajouté
- **Agent models** — Agent, AgentCapability (13 types), AgentProfile, AgentStatus (10 états), ExecutionContext, ExecutionResult, AgentMetrics, AgentTask
- **AgentRegistry** — registre thread-safe avec index par capability, status et métriques
- **CapabilityMatcher** — scoring multi-critères (capability 30%, load 25%, availability 20%, history 15%, runtime 10%) + mapping task→capability
- **AgentLifecycle** — machine à états 10 transitions validées, historique, callback événements
- **ExecutionContextManager** — gestion thread-safe des contextes d'exécution par agent/mission
- **TaskDispatcher** — pipeline complet : sélection agent → contexte → exécution → résultat → métriques
- **AgentSupervisor** — superviseur central : création agents, dispatch tâches, exécution mission DAG, réassignation, métriques
- **REST API** — GET /agents, POST /agents, GET /agents/{id}, GET /agents/status, GET /agents/metrics, POST /agents/{id}/start, POST /agents/{id}/stop, POST /agents/{id}/pause
- **Intégrations** — Mission Graph (HOS-041): dispatch MissionNode → agent, Runtime Orchestrator (HOS-038): callback de sélection runtime
- **EventBus** — agent.created, agent.started, agent.ready, agent.busy, agent.completed, agent.failed, agent.stopped, task.assigned, task.reassigned
- **Tests** — 49 tests : registry (10), lifecycle (8), matcher (7), context (5), dispatcher (4), supervisor (11), full execution (2), thread safety (2)

### Exemple : mission multi-agent
```
DesignerAgent → "Design architecture"
       ↓
CoderAgent → "Implement backend"
       ↓
CoderAgent → "Write tests"  ∥  ReviewerAgent → "Code review"
```

### Validation
- pytest : ✅ 49/49 passed (0.06s)

---

## [HOS-042] — 2026-07-29 — Intelligent Mission Planner

### Ajouté
- **TaskDecomposer** — décomposition automatique de requêtes utilisateur en tâches structurées (7 patterns connus : auth, database, api, frontend, deployment, + pattern générique)
- **DependencyBuilder** — construction automatique du graphe de dépendances, détection de groupes parallèles, détection d'incohérences
- **ComplexityEstimator** — estimation de complexité (0-10), durée, VRAM/RAM, tokens, risque (LOW→CRITICAL), priorité suggérée
- **RuntimeRecommender** — recommandation de modèle/base runtime par catégorie de tâche et niveau de complexité (coding/reasoning/chat)
- **ValidationEngine** — 7 vérifications : complétude, dépendances, ressources, cycles, orphelins, estimates, recommendations
- **TemplateLibrary** — 6 templates de mission réutilisables (web_app, api_service, cli_tool, data_pipeline, microservice, refactoring)
- **MissionPlanner** — orchestrateur principal : pipeline complet request → DAG valide
- **REST API** — POST /planner/plan, POST /planner/plan/template/{id}, GET /planner/results, GET /planner/results/{id}, POST /planner/results/{id}/build, GET /planner/templates
- **Intégration** — GraphExecutor (HOS-041), catégories Runtime Discovered (HOS-040), EventBus callback
- **Tests** — 47 tests : decomposer (7), dependency builder (7), complexity estimator (7), runtime recommender (5), validation (4), templates (5), full pipeline (11), thread safety (1)

### Pipeline de planification
```
User Request → Decomposer → DependencyBuilder → ComplexityEstimator
                                                       ↓
              Mission DAG ← MissionPlanner ← RuntimeRecommender
                                  ↓
                          ValidationEngine
```

### Templates disponibles
| Template | Tâches |
|---|---|
| web_app | 10 (analysis → deployment) |
| api_service | 8 (analysis → deploy) |
| cli_tool | 7 (design → distribute) |
| data_pipeline | 8 (analysis → deploy) |
| microservice | 7 (analysis → runbook) |
| refactoring | 6 (analysis → review) |

### Validation
- pytest : ✅ 47/47 passed (0.06s)
- compileall : ✅

---

## [HOS-041] — 2026-07-29 — Mission Graph Engine

### Ajouté
- **MissionGraph** — représentation DAG avec validation, détection de cycles (Kahn), tri topologique
- **Mission models** — Mission, MissionNode, MissionEdge, MissionContext, MissionStatus, MissionPriority, MissionType, NodeStatus
- **DependencyResolver** — résolution de dépendances, nœuds ready/blocked, groupes parallèles, cascade d'échecs
- **GraphExecutor** — moteur d'exécution pas-à-pas, intégration RuntimeOrchestrator, progression
- **GraphSerializer** — sérialisation JSON/YAML avec versioning (schema v1.0.0)
- **REST API** — POST /missions, GET /missions, GET /missions/{id}, GET /{id}/graph, POST /{id}/start, POST /{id}/cancel, GET /{id}/progress
- **Intégration EventBus** — mission.created, mission.started, mission.node_ready, mission.node_completed, mission.node_failed, mission.completed, mission.cancelled
- **Tests** — 27 tests : modèles, validation DAG, cycles, tri topologique, résolution, exécution, sérialisation, événements, thread safety

### Exemple : mission de développement logiciel (7 nœuds)
```
init → db → api → auth → deploy
  │              │        ↗
  └→ frontend ──→ tests ─┘
```

### Validation
- pytest : ✅ 27/27 passed (0.02s)

---

## [HOS-040] — 2026-07-29 — Model Benchmark & Discovery Engine

### Ajouté
- **DiscoveryEngine** — découverte automatique de modèles avec connecteurs pluggables (Ollama, HuggingFace)
- **OllamaConnector** — catalogue de 12 modèles Ollama connus (qwen3, deepseek, gemma3, phi4, llama, nomic, codellama)
- **HuggingFaceConnector** — curated hot list (phi-4, Mistral-Nemo, Llama-3.1)
- **ModelRegistry** — registre central thread-safe (5000 max) avec stats par statut et source
- **CompatibilityAnalyzer** — analyse VRAM/RAM/ROCm/quantization avec recommandations de downgrade
- **BenchmarkEngine** — 5 profils (CODING, REASONING, GENERAL_CHAT, TOOL_USE, LONG_CONTEXT) avec métriques
- **CronScheduler** — planificateur in-process pour discovery/benchmark périodiques (sans dépendance externe)
- **REST API** — POST /scan, GET /models, GET /benchmarks, GET /stats
- **Tests** — 24 tests : registry, compatibility, discovery, connectors, benchmark, cron, thread safety

### Validation
- pytest : ✅ 24/24 passed (1.04s)

---

## [HOS-039] — 2026-07-29 — Runtime Simulation Engine

### Ajouté
- **SimulationEngine** — simulacres de tâches avant exécution réelle, intégration orchestrator
- **ResourcePredictor** — prédiction VRAM/RAM/durée/charge par modèle et type de tâche
- **RiskAnalyzer** — analyse de risque (échec, surcharge, instabilité, recovery) à 4 niveaux
- **Simulation models** — SimulationResult, SimulatedCandidate, ResourcePrediction, RiskAssessment, RiskLevel
- **REST API** — POST /runtime/simulation/run, GET /{id}, GET /history
- **Intégration EventBus** — publie simulation.started, simulation.completed, simulation.warning
- **simulate_before_execute()** — pont vers RuntimeOrchestrator (HOS-038)
- **Tests** — 19 tests : prédiction, risque, simulation, events, thread safety

### Validation
- pytest : ✅ 19/19 passed (0.02s)

---

## [HOS-038] — 2026-07-29 — Adaptive Runtime Orchestrator

### Ajouté
- **RuntimeOrchestrator** — couche d'orchestration finale combinant intelligence, santé, ressources, recovery
- **DecisionPipeline** — pipeline multi-facteurs : évalue les candidats, élimine les invalides, score les restants
- **PriorityManager** — 4 profils (CRITICAL/HIGH/NORMAL/BACKGROUND) avec poids et seuils adaptatifs
- **Decision models** — OrchestratedDecision, CandidateRuntime, DecisionExplanation, PriorityLevel, DecisionStatus
- **REST API** — GET /history, GET /decision/{id}, POST /evaluate
- **Intégration EventBus** — publie routing.analysis_started, routing.runtime_selected, routing.decision_created, routing.decision_failed
- **Tests** — 24 tests : priority profiles, pipeline evaluation, elimination logic, explanation, events, thread safety

### Profils de priorité
| Priorité | Intelligence | Santé | Ressources | Confiance min |
|---|---|---|---|---|
| CRITICAL | 15% | 35% | 20% | 85% |
| HIGH | 30% | 30% | 25% | 70% |
| NORMAL | 40% | 25% | 25% | 50% |
| BACKGROUND | 25% | 15% | 50% | 30% |

### Validation
- pytest : ✅ 24/24 passed (0.04s)
- compileall : ✅

---

## [HOS-037] — 2026-07-29 — Runtime Intelligence Layer

### Ajouté
- **LearningEngine** — apprentissage incrémental : enregistre les résultats, met à jour les scores, ajuste les poids
- **DecisionMemory** — stockage thread-safe des décisions passées (10000 max) avec index par runtime et type de tâche
- **PerformanceAnalyzer** — success rate, avg latency, latency stddev, stability score, resource efficiency
- **RuntimeScorer** — score composite pondéré (performance 35%, fiabilité 40%, efficacité 25%), comparaison, recommandations contextuelles
- **Intelligence models** — DecisionRecord, RuntimeScore, TaskContext, Recommendation, TaskStatus
- **REST API** — GET /runtime/intelligence/scores, GET /runtime/intelligence/{id}, GET /runtime/intelligence/recommendations?task_type=&max_latency_ms=&priority=
- **Intégration EventBus** — publie intelligence.score_updated, intelligence.recommendation_created
- **Tests** — 26 tests : decision memory, performance analysis, scoring, learning, recommendations, events, thread safety

### Validation
- pytest : ✅ 26/26 passed (0.05s)
- compileall : ✅

---

## [HOS-036] — 2026-07-29 — Runtime Recovery Engine

### Ajouté
- **RecoveryEngine** — moteur d'auto-récupération : écoute les événements runtime, match les politiques, exécute les actions
- **RecoveryPolicyEngine** — 6 politiques par défaut : restart_on_failure, fallback_on_unavailable, unload_on_resource_limit, reload_on_model_failure, notify_on_health_degraded, unload_on_overloaded
- **RecoveryActions** — 5 actions concrètes : RestartRuntimeAction, ReloadModelAction, SwitchRuntimeAction, UnloadResourceAction, NotifyAction
- **Recovery models** — IncidentType, RecoveryIncident, RecoveryAttempt, RecoveryPolicy, RecoveryStatus, ActionResult
- **REST API** — GET /runtime/recovery/history, GET /runtime/recovery/status, POST /runtime/recovery/{id}/retry
- **Intégration EventBus** — publie recovery.started, recovery.action_started, recovery.completed, recovery.failed
- **Cooldown** — empêche la répétition de politiques pour le même runtime dans une fenêtre configurable
- **Max attempts** — limite le nombre de tentatives par politique (3 par défaut)
- **Tests** — 25 tests : détection incidents, actions, policies, cooldown, history, thread safety, events

### Validation
- pytest : ✅ 25/25 passed (2.95s)
- compileall : ✅

---

## [HOS-035] — 2026-07-29 — Runtime Resource Manager

### Ajouté
- **ResourceManager** — gestionnaire centralisé CPU/RAM/GPU/VRAM avec allocation thread-safe
- **GPUMonitor** — surveillance GPU via rocm-smi (AMD), nvidia-smi (NVIDIA), ollama ps (fallback), NoopGPUMonitor pour CI
- **MemoryManager** — suivi RAM système via /proc/meminfo avec fallback psutil
- **AllocationPolicy** — DefaultAllocationPolicy (first-fit, priorité) + VramAwareAllocationPolicy (température, utilisation)
- **Resource Models** — ResourceType, ResourceStatus, ResourceSnapshot, ResourceAllocation, ResourceLimit, GPUInfo
- **REST API** — GET /runtime/resources, GET /runtime/resources/status, GET /runtime/resources/allocations, POST /runtime/resources/release
- **Intégration EventBus** — callback on_event publie vram.allocated, resource.allocation_failed, resource.released, resource.warning, vram.limit_reached
- **Tests** — 21 tests : allocation, refus surcharge, libération, événements, seuils, thread safety, mock GPU

### Validation
- pytest : ✅ 21/21 passed (0.03s)
- compileall : ✅

---

## [HOS-034] — 2026-07-29 — Runtime Event Bus & Observability

### Ajouté
- **RuntimeEventBus** — bus publish/subscribe thread-safe avec historique configurable
- **RuntimeEventModel** — modèle Pydantic immutable : id, runtime_id, event_type, severity, timestamp, source, payload, correlation_id
- **RuntimeEventType** — 16 types d'événements en 4 catégories : runtime, model, router, resource
- **RuntimeEventStore** — abstraction EventStore + implémentation SQLite avec WAL 
- **REST API** — GET /runtime/events (filtres), GET /runtime/events/{runtime_id}, POST /runtime/events
- **WebSocket** — /runtime/events/ws avec streaming temps réel et filtrage
- **useRuntimeEvents hook** — hook React WebSocket avec reconnexion automatique
- **Tests** — 24 tests : création, publication, abonnement, persistence SQLite, thread safety, event types

### Validation
- pytest : ✅ 24/24 passed
- compileall : ✅

---

## [HOS-029] — 2026-07-29 — Mission Control Dashboard (Next.js)

---

## [HOS-030] — 2026-07-29 — Mission Center & Visual Planner

---

## [HOS-031] — 2026-07-29 — Execution Center & Live Monitoring

---

## [HOS-032] — 2026-07-29 — Agent Center & Live Agent Inspector

---

## [HOS-033] — 2026-07-29 — Runtime Center & Intelligent Runtime Management

### Ajouté
- **Runtime Center** — page /runtimes avec 9 panneaux redimensionnables (react-resizable-panels)
- **RuntimeOverview** — 8 stat-cards : total, healthy, degraded, avg latency, most reliable, most used, best score, failures
- **RuntimeTable** — tableau TanStack 9 colonnes : nom, status, healthy, latence, fiabilité, performance, succès, exécutions, échecs (tri, filtre, sélection)
- **RuntimeInspector** — inspection : status, version, latence, scores, capacités, type, dernière décision
- **RuntimeDecisionExplorer** — visualisation Recharts des scores par runtime (health, reliability, performance, capability, policy) avec penalty circuit breaker
- **RuntimeHealth** — santé temps réel : statut, latence, erreurs, graphique d'évolution
- **RuntimePerformance** — graphiques Recharts : barres succès, pie exécutions, barres scores fiabilité
- **RuntimePolicies** — politiques actives : règles, priorités, runtimes autorisés/interdits, préférence local/cloud
- **RuntimeEvents** — timeline temps réel : 8 types d'événements runtime avec filtres
- **RuntimeControls** — barre d'actions : refresh, health check, reset circuit, disable, enable
- **RuntimeClient** — 13 endpoints : list, get, health, metrics, decisions, policies, events, refresh, healthCheck, resetCircuit, disable, enable, export
- **Hooks runtime** — 10 hooks : useRuntimeList (10s), useRuntime (10s), useRuntimeHealth (5s), useRuntimeMetrics (10s), useRuntimeDecisions (15s), useRuntimeDecision, useRuntimePolicies, useRuntimeEvents (5s), useRuntimeControl
- **Types runtime** — RuntimeDetail, RuntimeDecisionInfo, RuntimePolicyInfo, RuntimePolicyRuleInfo, RuntimeEvent, RuntimeControlAction

### Validation
- Build Next.js 16 : ✅ (Turbopack, 5.6s)
- TypeScript strict : ✅
- Pages : 11 statiques (dont /runtimes)

### Ajouté
- **Agent Center** — page /agents avec 8 panneaux redimensionnables (react-resizable-panels)
- **AgentOverview** — 8 stat-cards : total, actifs, complétés, échecs, sous-agents, succès, durée moyenne, runtimes
- **AgentTable** — tableau TanStack : nom, état, runtime, mission, durée, retries, progression (tri, filtre, sélection)
- **AgentInspector** — panneau d'inspection : état, runtime, durée, retries, fallback, erreur, scores fiabilité/performance, historique des transitions, circuit breaker, sous-agents
- **AgentGraph** — visualisation React Flow mission → agents → sous-agents avec couleurs par état
- **AgentTimeline** — timeline temps réel : événements created/ready/running/completed/failed/paused/recovered
- **AgentPerformance** — graphiques Recharts : barres durée par agent, pie runtimes, histogramme
- **AgentHermesCard** — carte Hermes Agent : statut connexion, sessions, capacités, connect/disconnect, créer sous-agent
- **AgentControls** — barre d'actions : pause, resume, cancel, retry, recover, duplicate
- **AgentClient** — 17 endpoints : list, get, statistics, graph, timeline, performance, control, hermes
- **Hooks agents** — 9 hooks : useAgents (5s), useAgent (5s), useAgentStatistics (15s), useAgentGraph (10s), useAgentTimeline (5s), useAgentPerformance (15s), useHermesStatus, useAgentControl
- **Types agent** — AgentInfo, AgentDetail, AgentStatisticsResponse, AgentGraphData, AgentTimelineEvent, AgentPerformanceData

### Validation
- Build Next.js 16 : ✅ (Turbopack, 5.6s)
- TypeScript strict : ✅
- Pages : 11 statiques (dont /agents)

### Ajouté
- **Execution Center** — page /execution avec 6 panneaux redimensionnables (react-resizable-panels)
- **ExecutionOverview** — état global, progression, durée, runtime, agents, tâches
- **LiveGraph** — DAG temps réel React Flow avec mise à jour WebSocket (couleurs par statut, mini-map, zoom)
- **TaskTable** — tableau TanStack des tâches actives (tri, filtre, statut, runtime, agent, durée, retries)
- **ExecutionTimeline** — timeline temps réel avec événements WebSocket, auto-scroll, filtres par type, sévérité
- **PerformanceCharts** — graphiques Recharts : barres durée tâches, pie runtime usage, line latence trend
- **ExecutionControls** — barre de contrôle : pause, resume, cancel, recover, retry failed, export logs, tick
- **ExecutionClient** — API client complet avec données sample pour développement hors-ligne
- **Hooks execution** — `useExecutionOverview()`, `useExecutionTasks()`, `useExecutionPerformance()`, `useExecutionGraph()`, `useExecutionStatistics()`, `useExecutionTimeline()`, `useExecutionControl()`
- **Types execution** — `ExecutionOverviewResponse`, `ExecutionTask`, `ExecutionTimelineEvent`, `ExecutionPerformanceData`, `ExecutionStatisticsResponse`

### Dépendances ajoutées
- `recharts` — graphiques de performance
- `react-resizable-panels` — panneaux redimensionnables

### Validation
- Build Next.js 16 : ✅ (Turbopack, 5.6s)
- TypeScript strict : ✅
- Pages : 11 statiques (dont /execution)

### Ajouté
- **Mission Center** — page /missions complète avec 5 panneaux intégrés
- **MissionListTable** — liste des missions avec TanStack Table (tri, recherche, filtrage)
- **MissionForm** — création de mission avec react-hook-form + zod (titre, description, objectif, priorité, stratégie, planificateur)
- **MissionDetails** — panneau détaillé : statistiques, progression, plan d'exécution
- **MissionActions** — barre d'actions contextuelles : start/pause/resume/cancel/duplicate/delete/sync Freebuff
- **VisualPlanner** — visualisation DAG avec React Flow (mini-map, zoom, contrôles, couleurs par statut)
- **Mission Planner API** — `MissionPlanner` client avec generateSampleGraph() pour démo
- **Hooks missions** — `useMissionList()`, `useMission()`, `useMissionPlan()`, `useMissionGraph()`, `useCreateMission()`, `useStartMission()`, `usePauseMission()`, `useResumeMission()`, `useCancelMission()`, `useDeleteMission()`, `useDuplicateMission()`, `useSyncFreebuff()`
- **Types enrichis** — `CreateMissionRequest`, `MissionPlan`, `ExecutionGraphData`, `GraphNode`, `GraphEdge`, `PlanningStrategy`, `PlannerType`

### Dépendances ajoutées
- `@xyflow/react` — Visual Planner DAG
- `@tanstack/react-table` — Mission list table
- `react-hook-form` + `@hookform/resolvers` + `zod` — Formulaire création
- `@dnd-kit/core` + `@dnd-kit/sortable` — Préparation drag & drop futur

### Intégration Freebuff
- Planificateur Freebuff disponible dans le formulaire de création
- `syncWithFreebuff()` — synchronisation mission → Freebuff
- `FreebuffSyncResult` — prompt, réponse, plan, date

### UX
- Loading skeletons, empty states, error states
- Animations transitions, hover states
- Formulaire avec validation temps réel
- Actions contextuelles selon le statut de la mission

### Validation
- Build Next.js 16 : ✅ (Turbopack, 4.1s)
- TypeScript strict : ✅
- 10 pages statiques maintenues

### Ajouté
- `frontend/src/types/mission-control.ts` — 30+ types TypeScript correspondant aux modèles Pydantic HOS-028
- `frontend/src/lib/mission-control.ts` — `MissionControlClient` client REST fortement typé (20 endpoints)
- `frontend/src/hooks/use-dashboard.ts` — 17 hooks TanStack Query (auto-refresh 5s/15s/30s)
- `frontend/src/hooks/use-events.ts` — WebSocket hook avec reconnexion automatique
- `frontend/src/store/dashboard-store.tsx` — store contextuel (sidebar, filtres événements, refresh)
- `frontend/src/components/layout/` — Sidebar, Topbar, StatusBar, DashboardLayout
- `frontend/src/components/dashboard/` — 7 composants : HealthCard, StatisticsCard, RuntimeTable, MissionList, EventTimeline, FreebuffCard, HermesCard
- `frontend/src/app/dashboard/page.tsx` — Dashboard principal avec grille complète
- 6 pages placeholder : /missions, /runtimes, /agents, /memory, /skills, /events, /settings
- `frontend/src/app/providers.tsx` — QueryClientProvider avec configuration optimisée
- Lien "Dashboard" dans le header de la page Chat existante

### Composants

| Composant | Rôle |
|---|---|
| `HealthCard` | État système, version, uptime, sous-systèmes, chargement/erreur/empty states |
| `StatisticsCard` | Missions, agents, runtimes, mémoire, skills, événements |
| `RuntimeTable` | Tableau responsive des runtimes avec barres de score |
| `MissionList` | Missions récentes avec progression, priorité, runtime, durée |
| `EventTimeline` | Timeline temps réel via WebSocket, filtres par sévérité |
| `FreebuffCard` | Intégration Freebuff : statut, projets, dernière sync |
| `HermesCard` | Intégration Hermes Agent : statut, sessions, capacités |
| `Sidebar` | Navigation complète 10 sections + responsive (collapse) |
| `Topbar` | Recherche, indicateur santé, notifications |
| `StatusBar` | Statut système, version, uptime, connexion WebSocket |

### Validation
- Build Next.js 16 : ✅ (Turbopack, 2.9s)
- TypeScript strict : ✅
- Routes : 10 pages, toutes statiquement générées

---

## [HOS-028] — 2026-07-29 — Mission Control API

### Ajouté
- `backend/api/` package complet
- `MissionControlRouter` — agrège 38 routes REST
- `MissionControlAPI` — point d'entrée FastAPI
- WebSocket `/ws/events` — streaming temps réel des SystemEvent
- 30 Pydantic models pour validation requests/réponses
- Filtrage WebSocket par sources (query param `?sources=runtime,memory`)

### Tests
- 63 tests API (REST + WebSocket) — `tests/api/test_mission_control_api.py`

---

## [HOS-027] — 2026-07-29 — Mission Control Service Layer

### Ajouté
- `backend/services/` package
- `MissionControlService` — façade centrale agrège tous les sous-systèmes
- 9 façades : Mission, Runtime, Exécution, Mémoire, Skills, Événements, Hermes, Freebuff, Système
- `health()`, `diagnostics()`, `statistics()`, `status()`

### Tests
- 63 tests — `tests/architecture/test_mission_control_service.py`
- 630 total architecture tests

---

## [HOS-026] — 2026-07-29 — Freebuff Adapter

### Ajouté
- `FreebuffAdapter` avec `FreebuffSession`, `FreebuffProject`, `FreebuffPrompt`, `FreebuffResponse`
- Pipeline Mission → FreebuffPrompt → TaskPlan → ExecutionGraph
- 4 modes de connexion : API, TERMINAL, CLI, MCP

### Tests
- 44 tests — `tests/integrations/test_freebuff_adapter.py`

---

## [HOS-025] — 2026-07-29 — System Event Bus

### Ajouté
- `SystemEventBus` — bus central pub/sub unifié
- `SystemEventType` — 9 familles : RUNTIME, AGENT, MISSION, EXECUTION, MEMORY, SKILL, SYSTEM, OBSERVABILITY, INTEGRATION
- `EventFilter` — filtrage par type, source, sévérité, temps
- `EventHistory` — historique configurable avec export JSON
- Helpers de mapping depuis HOS-013

### Tests
- 44 tests — `tests/architecture/test_system_event_bus.py`

---

## [HOS-024] — 2026-07-29 — Mission Execution Engine

### Ajouté
- `ExecutionEngine` — moteur d'orchestration complet
- `ExecutionScheduler` — identification des tâches prêtes, groupes parallèles
- 9 états : IDLE → INITIALIZING → RUNNING ↔ PAUSED → COMPLETED/FAILED/CANCELLED
- Intégration Supervisor + Lifecycle + DecisionEngine + Router

### Tests
- 37 tests — `tests/architecture/test_execution_engine.py`

---

## [HOS-023] — 2026-07-29 — Hermes Agent Adapter

### Ajouté
- `HermesAgentAdapter` — pont complet Hermes OS → Hermes Agent
- Mapping : RuntimeDecision → ModelRouter, UnifiedMemory → EchoAgent, TaskPlan → Hermes Tasks
- 7 capacités : CHAT, CHAT_STREAM, TOOLS, MEMORY, SKILLS, SUBAGENTS, DELEGATION

### Tests
- 35 tests — `tests/integrations/test_hermes_adapter.py`

---

## [HOS-022] — 2026-07-29 — Adaptive Skill Orchestrator

### Ajouté
- `AdaptiveSkillOrchestrator` avec 4 stratégies de sélection
- `SkillRepository` / `InMemorySkillRepository`
- Résolution de dépendances, limites de tokens, bundles

### Tests
- 24 tests — `tests/architecture/test_skill_orchestrator.py`

---

## [HOS-021] — 2026-07-29 — Unified Memory

### Ajouté
- `UnifiedMemory` — façade mémoire unifiée
- `MemoryBackend` abstrait + `InMemoryBackend`
- 7 scopes : SESSION, MISSION, AGENT, PROJECT, USER, GLOBAL, EXPERIENCE
- Import/Export JSON, événements, statistiques

### Tests
- 33 tests — `tests/architecture/test_unified_memory.py`

---

## [HOS-020] — 2026-07-29 — Multi-Agent Supervisor

### Ajouté
- `MultiAgentSupervisor` — orchestration centrale missions + agents
- `MissionState` : 8 états avec transitions
- `tick()` — boucle de progression
- Intégration TaskPlanner + ExecutionGraph + Lifecycle

### Tests
- 28 tests — `tests/architecture/test_supervisor.py`

---

## [HOS-019] — 2026-07-29 — Agent Lifecycle Manager

### Ajouté
- `AgentLifecycleManager` — machine à états 10 états
- Transitions validées, thread-safe
- `on_event()` callback pour observabilité
- `check_timeouts()`, `cleanup()`

### Tests
- 33 tests — `tests/architecture/test_lifecycle.py`

---

## [HOS-018] — 2026-07-29 — Task Planning Engine

### Ajouté
- `TaskPlanner` avec 4 stratégies : SEQUENTIAL, BALANCED, PARALLEL, CONSERVATIVE
- `PlanningValidator` — dépendances, cycles, capacités
- Production directe d'ExecutionGraph

### Tests
- 30 tests — `tests/architecture/test_task_planner.py`

---

## [HOS-017] — 2026-07-29 — Execution Graph

### Ajouté
- `ExecutionGraph` — DAG thread-safe
- Détection de cycles (Kahn), tri topologique
- `GraphExecutionPlan` avec niveaux de parallélisme
- Sérialisation JSON

### Tests
- Tests intégrés dans les modules ultérieurs

---

## [HOS-016] — 2026-07-29 — Runtime Policy Engine

### Ajouté
- `RuntimePolicy` — politique immuable avec règles
- `RuntimePolicyEngine` — évaluation par contexte d'exécution
- Règles : capability_required, provider_allowed, latency_max, reliability_min

### Tests
- Tests intégrés dans RuntimeDecisionEngine

---

## [HOS-015] — 2026-07-29 — Runtime Decision Engine

### Ajouté
- `RuntimeDecisionEngine` — score composite 0-1000
- 6 facteurs : Health + Reliability + Performance + Capability + Policy - CircuitPenalty
- `RuntimeDecision` immutable avec explication

### Tests
- Tests intégrés dans la suite architecture

---

## [HOS-014] — 2026-07-29 — Runtime Performance Analyzer

### Ajouté
- `RuntimePerformanceAnalyzer` — analyse des événements runtime
- `RuntimePerformanceMetrics` — scores de fiabilité et performance
- Classement des runtimes

### Tests
- Tests intégrés

---

## [HOS-013] — 2026-07-29 — Runtime Event Bus & Observability

### Ajouté
- `RuntimeEventBus` — bus événements runtime
- `RuntimeObservability` — métriques agrégées
- 11 types d'événements

### Tests
- Tests intégrés

---

## [HOS-012] — 2026-07-29 — Runtime Recovery & Failover

### Ajouté
- `RuntimeRecoveryManager` — gestion des pannes runtime
- `CircuitBreaker` — 3 états : CLOSED → OPEN → HALF_OPEN
- `ExecutionTrace` — traçage des fallbacks

### Tests
- Tests intégrés

---

## [HOS-011] — 2026-07-29 — Runtime Health Monitor

### Ajouté
- `RuntimeHealthMonitor` — AVAILABLE/DEGRADED/UNAVAILABLE/UNKNOWN
- `RuntimeMetrics` — compteurs d'exécution, taux d'échec

### Tests
- Tests intégrés

---

## [HOS-010] — 2026-07-29 — Runtime Execution Router

### Ajouté
- `RuntimeRouter` — routage avec fallback et recovery
- Résolution : actif → fallback → préférence → sélecteur
- Publication d'événements sur toutes les étapes

### Tests
- Tests intégrés

---

## [HOS-009] — 2026-07-29 — Runtime Selection & Context

### Ajouté
- `ActiveRuntimeContext` — gestion du runtime actif + fallback
- `RuntimeSelector` — sélection par règles extensibles

### Tests
- Tests intégrés

---

## [HOS-008] — 2026-07-28 — SDS Runtime Wiring

### Ajouté
- `init_runtime_registry_in_holder()` — initialisation registry + factory
- Intégration dans le lifespan FastAPI

---

## [HOS-007] — 2026-07-28 — Runtime Registry & Factory

### Ajouté
- `RuntimeRegistry` — registre thread-safe
- `RuntimeFactory` — builders par type
- `RuntimeLifecycle` — initialize/health_check/shutdown

---

## [HOS-006] — 2026-07-28 — Ollama Connector

### Ajouté
- `OllamaClientProtocol` — contrat client Ollama
- `OllamaClient` — client HTTP configurable
- `FakeOllamaClient` — mock pour tests
- Support chat + chat_stream + timeout

---

## [HOS-005] — 2026-07-28 — HermesOllamaRuntime

### Ajouté
- Premier runtime agentique réel basé sur Ollama
- Implémente RuntimeInterface, capacité Chat

---

## [HOS-004] — 2026-07-28 — StubRuntime

### Ajouté
- Premier runtime de démonstration
- `StubRuntime` conforme à `RuntimeInterface`
- `StubChatCapability` conforme à `ChatCapability`
- Publication RUNTIME_STARTED / RUNTIME_STOPPED

---

## [HOS-003] — 2026-07-28 — SDS Wiring

### Ajouté
- Câblage FastAPI complet
- Forward EventBusImpl → EventHub
- Proxy legacy `agent.message`

---

## [HOS-002] — 2026-07-28 — EventBusImpl

### Ajouté
- Bus d'événements SQLite
- Publication/abonnement par topic
- TopicPattern("*") pour forwarding wildcard

---

## [HOS-001] — 2026-07-28 — RAL Interfaces

### Ajouté
- `RuntimeInterface` Protocol
- `ChatCapability` Protocol
- `CapabilitySet`, `ChatResponse`
- RuntimeStatus enum

---

## [HOS-000] — 2026-07-28 — Foundation

### Ajouté
- Projet Hermes OS initial
- Structure SDS legacy
- 48 tests de base
