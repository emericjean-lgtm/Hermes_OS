## HOS-227 — Ce qui a le droit de partir chez un tiers (2026-09-03)

Le jalon 11. Prémisse vérifiée avant d'écrire une ligne : **le pare-feu
n'existait pas**, zéro implémentation de §8.1. Ce qui existait et a été
réutilisé : `audit_log.redact()`, décrit dans son propre code comme « le
plus proche d'un `secret_scanner` que ce projet possède » (§17.1), avec
des motifs délibérément conservateurs.

### La fuite, mesurée sur le vrai prompt

`_build_messages` assemble le prompt ; quand le runtime est distant, tout
part. Construit avec le vrai assembleur, pas recopié : le chemin absolu
du workspace apparaît dans les instructions système — donc le nom de
l'utilisateur **et celui de son client**, dans chaque prompt cloud d'une
mission liée à un projet. Pas un scénario : le comportement du jour.

Six fragments partent, de sensibilités différentes — instructions système
(qui portent le chemin absolu), objectif de mission, journal de projet
relu depuis `.hermes/`, résultats amont (du texte produit par un modèle,
qui peut citer un fichier), manifeste des livrables, titre.

### Ce que « refusé par défaut » peut vouloir dire, et ce qu'il ne peut pas

Appliquée **littéralement à du texte quelconque**, la décision §8.1
refuserait tout : on ne peut pas démontrer qu'une phrase en prose n'est
pas sensible. Un pare-feu qui refuse tout est un pare-feu qu'on désarme
dans la semaine — la leçon du canary (HOS-218) et celle de la portée
d'approbation (HOS-224).

Le refus par défaut s'applique donc là où il a un sens :

- **au niveau du projet**, où `PolitiqueCloud.JAMAIS` bloque tout, quelle
  que soit la recommandation du routeur. C'est le vrai levier, à la
  granularité où quelqu'un peut réellement en décider : l'utilisateur
  sait si son dépôt client a le droit d'aller chez un tiers, le
  classificateur ne le saura jamais ;
- **au niveau du constat**, où ce qui est *démontré* sensible est
  caviardé ou refusé — jamais laissé passer parce qu'on hésite.

Et comme partout ici, un constat **nomme son indice**.

### Contexte nécessaire n'est pas contenu autorisé

C'est la distinction que le cahier demandait, et elle décide du
caviardage plutôt que du refus. Le modèle a besoin de savoir **qu'il
existe** une racine de workspace ; il n'a pas besoin de savoir chez qui.
La racine devient `<WORKSPACE>` ; le chemin relatif — `src/app.py`,
c'est-à-dire le travail — reste intact.

**Une expression régulière ne peut pas deviner où une racine s'arrête.**
Mesuré : elle la réduisait à `<WORKSPACE>` suivi du nom du projet client,
qui survivait donc au caviardage. L'appelant, lui, connaît la racine
exacte : `RealTaskExecutor` la passe désormais, et les trois écritures
sont couvertes — antislash, slash, et la forme échappée d'un `repr()`,
qui est exactement ce que le prompt contient.

### Refuser, et pas seulement retirer

Un identifiant démontré fait **refuser** l'envoi, pas caviarder. Sa
présence veut dire que le contexte assemblé contient du matériel qui
n'aurait pas dû y entrer — vraisemblablement le fichier d'où il vient.
Retirer la clé et envoyer le fichier autour serait la moitié d'une
protection.

Un secret prime aussi sur la politique « approbation » : proposer une clé
à l'accord humain ferait exister un chemin où quelqu'un de pressé la
laisse partir.

Et un envoi refusé porte **zéro message**, pour qu'un appelant distrait
qui enverrait quand même n'envoie rien.

### L'interne est caviardé, pas refusé

Adresses de courriel, adresses réseau privées : retirées, l'envoi part.
Les refuser rendrait le cloud inutilisable pour toute mission liée à un
workspace. L'adresse de boucle locale est délibérément **exclue** :
Hermes écoute dessus, elle apparaît dans des messages d'erreur normaux,
et la caviarder rendrait un diagnostic illisible sans rien protéger.

### Le contrôle est avant l'envoi

Posé dans `_make_cloud_chat`, le goulet ouvert par HOS-226 — donc vrai de
tout appelant, pas seulement de celui qu'on a pensé à instrumenter. Deux
gardes sur l'**arbre syntaxique** le tiennent : l'examen s'exécute avant
l'appel, et ce qui est envoyé est `decision.messages`, pas les messages
d'origine. La seconde vise l'erreur qui annulerait tout le module —
examiner puis envoyer l'original passerait tous les tests du
classificateur et ne protégerait de rien.

Un événement `cloud.pare_feu` est publié sur **chaque** décision, pas
seulement sur les refus : savoir que trois cents prompts sont partis
« autorisés » vaut autant que savoir que deux ont été refusés, parce que
c'est ce qui dit si le pare-feu regarde vraiment quelque chose. Son
aperçu est caviardé à la source — un rapport de fuite qui cite la valeur
serait une seconde fuite (HOS-218).

### Une asymétrie trouvée dans le garde des topics

`collect_known_topics()` assemble la liste blanche depuis des
**catalogues déclarés à côté de leurs producteurs**, et non depuis
`event_topics.BASELINE_TOPICS`. Un topic ajouté seulement au second passe
à l'exécution mais fait tomber `test_topics_publies_sont_autorises` — ce
qui est arrivé ici. `PARE_FEU_EVENTS` suit donc le patron des huit
catalogues rebranchés en HOS-181.

### Mesures

28 gardes ajoutées ; 12 faux de chat cloud mis à jour, le contrat d'un
chat **distant** portant désormais les racines. Suite complète :
**5 159 vertes**, 3 ignorées.


## HOS-226 — Un fournisseur distant est un runtime, pas une hiérarchie (2026-09-03)

Le jalon 10. Sa prémisse — « le client existe sans un seul test » —
était fausse : `OpenRouterClient` en a **neuf**, réels (compteurs
d'usage, 429 traduit en quota, SSE, échec en cours de flux, non-200 avant
le flux), dans `tests/`, l'arbre qui n'était plus collecté depuis
HOS-175. Quatrième fois que cette réparation change une conclusion.

Ce qui manquait vraiment, mesuré : `CloudProvider` n'existait **nulle
part** (zéro occurrence), **trois fichiers** codent
`https://openrouter.ai/api/v1` en dur, et `service_registry` comme
`task_executor` branchent sur la chaîne littérale `"openrouter"`.

### Une première version qui construisait un cinquième système

Elle créait un paquet `backend/cloud/` avec son protocole, son
adaptateur et son registre. C'était une arborescence parallèle : le RAL
a déjà `adapters/hermes_ollama.py`, et un fournisseur distant **est** un
runtime — il répond à `chat` comme Ollama.

Ce qu'il a en plus est une **capacité**, pas une hiérarchie :
`CloudCapability` rejoint `ChatCapability` dans
`backend/ral/capabilities.py`, et porte les trois choses qui n'existent
pas en local — un **prix**, un **quota partagé** qui s'épuise, un
catalogue qui change sans qu'on l'ait décidé.

`RuntimeOpenRouter` vit donc sous `backend/ral/adapters/`, à côté de
`hermes_ollama.py`, et suit la convention du RAL (`name`, pas
`identifiant`) plutôt que d'imposer la sienne. Un test vérifie qu'il
satisfait les deux protocoles, et qu'un paquet `backend/cloud/` n'est pas
revenu.

### Pourquoi une interface pour une seule implémentation

La règle du dépôt est contre l'abstraction spéculative. Trois faits
disent que ce n'en est pas une :

- le couplage est réel et dispersé (trois URL en dur, deux comparaisons
  littérales) ;
- le **pare-feu de données** du jalon suivant a besoin d'un goulet — la
  décision §8.1 du cahier suppose un endroit unique où « quelque chose
  part chez un tiers » se constate. Sans interface, ce contrôle serait à
  dupliquer par fournisseur, donc à oublier au second ;
- ce n'est **pas** `ChatCapability`, qui ne dit rien du prix ni du quota.

### Une correction de prix trouvée en écrivant l'adaptateur

`cloud_catalog._is_free_pricing` compare `pricing["prompt"] == "0"` — une
égalité de **chaîne**. OpenRouter rend `"0"` aujourd'hui et `"0.0"` sur
certaines entrées : celles-là s'y lisent payantes par accident. La
comparaison est ici numérique, et un prix **illisible compte comme
payant** — le sens de lecture qui ne fait pas dépenser par erreur.
`None` et `0.0` ne disent pas la même chose.

### Le tri-état, appliqué à une ressource payante

Un quota non mesurable rend `utilisable=False`. On ne dépense pas sur une
mesure qu'on n'a pas — HOS-222 appliqué à l'argent. Mais une **clé sans
plafond** n'est pas « inconnu » : la réponse a été lue, elle dit qu'il
n'y a pas de limite. Les confondre interdirait le cloud à qui en a payé
l'accès illimité.

### Ce qui n'a délibérément pas bougé

Le gate `self._cloud_chat is not None` de `task_executor` reste tel quel.
Le remplacer par une consultation du registre ferait dépendre un test
unitaire hermétique d'un état de processus — et ce champ est justement
le point d'injection que ces tests utilisent.

### Un troisième faux positif de sous-chaîne

Ma garde « la fabrique ne construit plus de client en direct »
s'accrochait à la **docstring** qui explique le changement. Réécrite sur
l'arbre syntaxique : elle regarde les imports et les noms du corps.
Troisième fois sur ce chantier — c'est un motif, pas un accident.

### Mesures

29 gardes ajoutées. Suite complète : **5 131 vertes**, 3 ignorées.


## HOS-225 — Pourquoi un run a échoué, et ce que ça change (2026-09-03)

Le jalon 9, et la dette que HOS-221 avait explicitement notée : onze
causes déclarées, aucune renseignée, avec la raison écrite dans le code —
« deviner maintenant produirait des étiquettes fausses, et une étiquette
fausse coûte plus cher qu'une case vide, parce qu'on la croit ».

La contrainte n'a pas changé. Ce qui change, c'est ce qui la porte : un
classificateur qui **enregistre son indice** peut être contredit ; une
intuition ne peut pas l'être.

### Ce que la reprise faisait, et pourquoi c'était faux

`_resolve_model` change de modèle à **toute** reprise, quelle que soit la
cause. C'est le bon remède pour exactement un cas sur onze :

- **manque de VRAM** — il faut un modèle *plus petit*, ou attendre ; un
  autre de même taille échoue pareil ;
- **fenêtre de contexte fermée** — CLAUDE.md le dit déjà : « une réponse
  tronquée n'est pas une erreur de raisonnement et ne doit pas se noter
  comme telle ». Changer de modèle ne répare rien ;
- **quota dépassé** — réessayer chez le même fournisseur échoue par
  construction ;
- **refus de politique ou de sécurité** — il ne faut **pas** reprendre.
  `approvals.py` décrivait déjà ce que produit l'autre choix : « an agent
  retrying in a loop after a refusal will re-ask », c'est-à-dire une file
  d'approbation inondée par la machine. La reprise légitime viendra de
  l'accord humain, pas de la boucle.

### La règle de classement

Trois sources, dans l'ordre de la force de preuve :
`done_reason == "length"` (le seul indice qui vienne du runtime et non
d'un message rédigé ici), puis le code HTTP (un fait, pas une
interprétation), puis les motifs de texte.

Les motifs sont écrits **depuis les messages réels du dépôt**, pas
inventés : `no VRAM admission`, `runtime 'x' timed out after Ns`,
`returned an empty completion`, `is outside ALLOWED_PATHS`,
`the local fallback also failed`. Un classificateur calibré sur des
messages imaginaires classe des messages imaginaires.

`HTTP 400 → OUTIL` vient d'un incident précis : la campagne du catalogue
comptait « 0 s par tentative », c'était un HTTP 400 jamais regardé, et il
s'était rangé sous « le modèle ne sait pas faire ».

Deux refus de classer, délibérés. Le catch-all
`runtime 'x' could not execute task y: …` enveloppe n'importe quoi et
reste `INCONNUE` : lui donner une cause donnerait une cause à toutes les
erreurs non prévues, ce qui est exactement la façon dont une taxonomie
devient du bruit. Et `KeyError: 'x'` ne démontre rien.

### `INCONNUE` ne devient jamais une étiquette

En base, une cause non démontrée reste **`NULL`**. Une colonne vide se
lit « on ne sait pas » ; une étiquette « inconnue » se lit comme un
diagnostic posé. Et l'appelant retombe alors exactement sur le
comportement d'avant ce jalon : reprendre une fois, sans rien changer
qu'on ne saurait justifier.

L'abandon distingue aussi ses deux motifs — « plafond atteint » et
« cause non reprenable ». Les confondre ferait chercher un défaut de
compteur là où il y a un refus assumé.

### Un plafond retiré parce qu'un test l'a dit

Ma première version donnait à chaque cause un plafond de tentatives, à 2
par défaut. Il **rétrécissait** silencieusement le budget que
l'opérateur avait configuré dans `max_retries_per_task` : une mission
réglée sur deux reprises n'en obtenait plus qu'une, et
`tests/architecture/test_intelligent_retry.py` l'a dit à la première
exécution de la suite complète.

Aucune mesure ne dit qu'un manque de VRAM mérite moins de tentatives
qu'un échec quelconque. L'opinion de ce module est donc binaire — on
reprend ou on ne reprend pas — et le *combien* reste au budget de la
mission, qui est le seul chiffre que quelqu'un ait décidé.

C'est le second arbre de tests qui l'a trouvé, celui qui n'était plus
collecté depuis HOS-175.

### Mesures

34 gardes ajoutées, plus le garde de HOS-221 amendé — il interdisait de
renseigner `cause` du tout ; il vérifie maintenant les deux choses qui
rendent le classement honnête : qu'il passe par la taxonomie, et qu'une
cause non démontrée reste `NULL`.

Suite complète : **5 102 vertes**, 3 ignorées.


## HOS-224 — Approuver une action, pas une phrase (2026-09-03)

Le jalon 8. La roadmap annonçait « ni hash canonique, ni portée, ni
expiration », et proposait de rebrancher `backend/policy/approval_engine.py`.
Mesuré : deux tiers de ce diagnostic étaient faux, le troisième était
juste, et la solution proposée aurait été une erreur.

`backend/security/approvals.py` **a** une expiration, **est** branché —
dans `AegisAgent._apply_human_consent`, sur le chemin réel des requêtes —
et hache bien en SHA-256. Ce qu'il n'avait pas : un hachage *canonique*,
et une portée.

### Le premier défaut : la description entrait dans l'identité

Le module le justifiait par un argument correct — « une approbation pour
*Commit on feature/x* ne doit pas autoriser *Commit on main* » — appuyé
sur une hypothèse qui n'est vraie que pour une partie de ses appelants :

> Descriptions are generated by the calling tool, not by a model.

Vrai pour `file_tools` et `git_tools`. **Faux** pour l'outil MCP
`aegis_check`, dont la description est écrite par le modèle, et pour
`POST /api/v1/security/evaluate`, où elle vient du corps de la requête.

Mesuré :

    « Write to config.json to fix the port »  ->  24aa0d0bf698
    « Write config.json (port fix) »          ->  061db3be665d

Deux empreintes pour une action. Le « oui » de l'humain ne s'appliquait
jamais, une seconde demande était déposée, et rien ne disait pourquoi.

### Le second : le chemin non plus n'était pas canonique

Quatre écritures du même fichier, quatre empreintes :

    C:/p/config.json     C:\p\config.json
    c:/p/config.json     C:/p/../p/config.json

Sur Windows ce n'est pas un cas de laboratoire. Le défaut ne va que dans
le sens sûr — il refuse au lieu d'autoriser — mais il rend la
fonctionnalité inutilisable, ce qui revient au même une fois qu'on l'a
désactivée.

### La règle retenue

L'identité d'une action est **structurée**, jamais rédigée :

    action_type + chemin canonique + discriminants triés

La description reste sur la ligne, pour que l'humain sache ce qu'il
approuve ; elle n'est plus dans l'identité. Ce qui la distinguait
légitimement devient un discriminant nommé : `git_tools` passe
`{"op": "commit", "branch": "main"}` au lieu de compter sur la phrase.
La garantie d'origine est **conservée** — commit sur `feature/x`
n'autorise ni commit sur `main`, ni push sur `main` — et elle ne dépend
plus de la formulation.

Un détail d'ordre a coûté une mesure : `os.path.normcase` reconvertit les
`/` en `\` sur Windows. Replier la casse **après** avoir uniformisé les
séparateurs rendait `c:\projet`, et la portée ne couvrait plus rien.

`ActionRequest.discriminants` est un tuple de paires, pas un dict : la
classe est `frozen=True`, donc hachable, et un dict la rendrait
inhachable pour tous ses usages présents et futurs.

### Ce qui manquait vraiment : la portée

Trente écritures dans un dossier demandaient trente approbations. Une
fonctionnalité qui exige trente clics est une fonctionnalité désactivée
— et une approbation désactivée ne protège de rien.

Une portée d'arborescence couvre un `action_type` sous une racine. Trois
bornes, et les trois sont nécessaires :

- une **racine**, sans laquelle elle couvrirait le disque — absente,
  c'est une `ValueError`, jamais un accord silencieusement plus large ;
- un **budget d'usages** plafonné à 50, sans lequel « oui pour ce
  dossier » deviendrait une permission permanente que personne n'a
  décidée ;
- une **expiration plus courte** que celle d'un accord exact (5 min
  contre 15) : elle autorise davantage, donc elle doit se périmer plus
  vite.

Et **elle ne s'obtient jamais par omission**. `decide(approved=True)`
seul donne exactement ce qu'il donnait : un accord exact, à usage unique,
quinze minutes.

Le confinement est vérifié par `empreinte.couvre`, qui canonise les deux
côtés et compare des segments de chemin : `C:/projet-bis` sous
`C:/projet` est l'évasion qu'un `startswith` laisse passer.

L'accord exact est dépensé **avant** la portée — sinon on consommerait un
budget de portée pour une action qui avait déjà son propre « oui ».

Les quatre colonnes sont nullables, et pas par commodité :
`_add_missing_columns` (`memory/db.py`) n'ajoute au démarrage que des
colonnes nullables et refuse bruyamment les autres. Une base existante
les gagne sans migration, avec `None` partout — c'est-à-dire avec le
comportement d'avant.

### Ce qui n'a délibérément pas été fait

**`backend/policy/approval_engine.py` reste débranché.** La roadmap
proposait de le rebrancher, « moins cher que de l'écrire ». Mesuré :
Aegis est la seule couche de gouvernance réellement sur le chemin des
requêtes, et `backend/policy/*` ne sert que ses propres routes. Y ajouter
une seconde porte vivante donnerait deux endroits où une action peut être
autorisée, deux files, et la question « laquelle fait foi ? » à chaque
incident. De la complexité neuve sans sécurité neuve.

Un test garde ce raisonnement et tombe si quelqu'un le rebranche — pour
qu'on relise l'argument plutôt que de le contourner.

### Un test amendé, pas supprimé

`test_a_different_action_gets_a_different_fingerprint` portait sa
troisième distinction dans la description. La propriété qu'il gardait est
juste et reste gardée ; ce qui la porte a changé.

### Mesures

37 gardes ajoutées. Suite complète : **5 068 vertes**, 3 ignorées.


## HOS-223 — Hermes sait annuler une modification (2026-09-03)

Le jalon 7. Trois constats, mesurés dans le code avant d'écrire une
ligne :

- `propose_write` déposait une sauvegarde horodatée à chaque écrasement,
  la rendait à l'appelant et la publiait dans un événement — et **rien,
  nulle part, ne la relisait**. Aucune fonction du dépôt ne restaurait
  depuis un `backup_path`. C'était un quatrième orphelin, après
  `approvals.py`, `DatabaseManager` et `MigrationManager`.
- `delete()` faisait `shutil.rmtree()` sur un répertoire sans rien
  garder du tout. `move()` non plus.
- `snapshot_manager` sauve l'état de mission et dit **explicitement**
  qu'il ne copie pas les fichiers, en déléguant à ces sauvegardes. La
  délégation pointait vers un mécanisme sans retour.

### Le chemin git, et la pièce qui détruirait du travail si elle cédait

Un point de reprise est un commit détaché sous
`refs/hermes/checkpoints/<id>`. Git fait le reste : stockage par contenu
qui déduplique, objet immuable, référence qui protège du ramasse-miettes,
et `.gitignore` honoré gratuitement — un `node_modules/` de 400 Mio
n'entre pas sans qu'on ait écrit une règle.

**Le dépôt de l'utilisateur ne sent rien.** Ni son index, ni sa branche,
ni son `HEAD`, ni son stash. Un `git add -A` sur l'index réel détruirait
le travail en cours de quelqu'un — au moment précis où il s'apprête à
lancer une mission risquée. D'où `GIT_INDEX_FILE` sur un fichier
temporaire, la pièce d'Agent OS qui vaut d'être reprise telle quelle.
Mesuré : index, `HEAD` et branche identiques avant et après.

Écart avec eux : le commit prend `HEAD` pour **parent**. Détaché sans
parent, un point de reprise n'est diffable contre rien.

Et restaurer, c'est effacer. `git checkout-index` réécrit ce qui était
là, mais ne supprime pas ce qui est apparu depuis — une restauration qui
les laisserait ne restaurerait rien, elle mélangerait deux états. Les
trois cas sont donc calculés et traités séparément.

### Le repli, pour les workspaces sans git

La production du 30 août tournait dans un dossier sans `.git`. Ne
protéger que les dépôts reviendrait à ne protéger que ce qui l'était
déjà.

Copie avec **manifeste de contenu** et vérification d'intégrité par
**re-hachage** — les deux sont d'Agent OS et les deux comptent : une
copie sans manifeste ne sait pas ce qu'elle devait contenir, un manifeste
jamais revérifié n'est qu'une déclaration. L'intégrité est vérifiée
**avant** d'écrire quoi que ce soit ; restaurer à moitié depuis une copie
abîmée laisserait un troisième état, ni l'ancien ni le nouveau.

Deux ajouts tirés de ce dépôt. Les répertoires ignorés sont ceux de
`verification.py` — une seconde liste divergerait. Et un fichier
illisible **fait échouer la prise**, il n'est pas passé sous silence :
c'est la leçon de HOS-222, un point de reprise partiel est pire
qu'absent, parce qu'on croit avoir un filet et qu'on ne l'apprend qu'en
tombant. Même raison pour le plafond de 500 Mo : lever plutôt que
dépenser silencieusement des gigaoctets à chaque mission.

### Ce que Hermes ajoute : le couple

Un checkpoint Agent OS est un état de fichiers. `snapshot_manager` sauve
l'état de mission, ce qu'ils ne font pas. Un point de reprise Hermes est
le **couple**, pris et repris ensemble.

Restaurer les fichiers sans l'état laisse une mission qui croit avoir
fini un travail que le disque ne porte plus, et qui repartira de là.
Restaurer l'état sans les fichiers fait l'inverse. L'un ou l'autre seul
fabrique une incohérence — le genre que ce dépôt met des semaines à
retrouver.

Quand l'état n'a pas pu être repris, `Restauration` le **dit** au lieu de
rendre un succès partiel : les fichiers sont déjà revenus à ce
moment-là, et lever laisserait l'appelant persuadé que rien n'a eu lieu.

### Restaurer efface, et c'est traité comme tel

Même contrat que `snapshot_manager.restore_snapshot` : un aperçu d'abord,
Aegis en `data_migration` ensuite — que `config/security.yaml` classe en
`mandatory_validation: true` à tous les niveaux d'autonomie. Et `Ecart`
garde **trois listes séparées** : fondre le destructif dans un
« 12 fichiers touchés » cacherait la seule qui détruise du travail.

### Branché, et le disant quand il ne l'est pas

`graph_executor` pose le filet avant que la mission touche au disque.
L'instantané qui existait déjà répond à « qu'est-ce qui a changé ? » ;
celui-ci répond à « comment revenir en arrière ? ».

Quand la prise échoue, la mission part quand même — l'utilisateur a
demandé un travail, pas une sauvegarde — mais `mission.sans_filet` le
dit. Un point de reprise absent en silence laisse partir avec le même
aplomb, et l'absence ne se découvre qu'en tombant. C'est la règle du
tri-état de HOS-222, appliquée à la protection plutôt qu'à la mesure.

### Deux défauts de test, dont un que j'avais déjà commis

Mes deux fixtures partageaient `tmp_path` : `depot` initialisait un dépôt
git dans le dossier que `dossier` déclarait n'en pas avoir. Et
l'assertion du `.gitignore` cherchait la sous-chaîne « ignore », que
`.gitignore` contient — **le faux positif de sous-chaîne**, exactement
celui que j'avais reproché au sondage du cahier six jours plus tôt. Elle
porte maintenant sur le chemin exact.

### Mesures

28 gardes ajoutées. Suite complète : **5 036 vertes**, 3 ignorées.


## HOS-222 — Ce qu'on n'a pas pu lire n'est ni vert ni rouge (2026-09-03)

Le jalon 6. `verification.py` était déjà exceptionnellement prudent sur
le « on ne sait pas » — `tests_echouent`, `manifeste_manque`,
`travail_deja_fait` distinguent tous soigneusement l'absence de mesure du
constat d'échec. Mais l'instrument lui-même ne savait pas dire qu'il
n'avait pas pu regarder, et deux faux verdicts en sortaient, **en sens
opposés**.

### Le faux positif : un workspace disparu passait pour du travail

`snapshot()` rendait un instantané **vide** pour un arbre illisible,
indiscernable d'un dossier réellement vide. Mesuré : un workspace de deux
fichiers devenu illisible se lisait « 2 supprimés », donc
`touched_anything`, donc **`verified: True`**.

Le module produisait exactement le faux positif qu'il existe pour
attraper. Une mission qui n'a rien fait, dans un workspace qu'on ne sait
plus lire, se déclarait vérifiée.

### Le faux négatif : deux instantanés muets devenaient une accusation

Le même défaut dans l'autre sens : deux instantanés illisibles se lisaient
« rien n'a changé », donc `contradicted: True`, donc `mission.unverified`
et une reprise suggérée — sur une mission qui avait peut-être travaillé.

C'est le jumeau de la règle centrale du dépôt. « Ne jamais croire un
succès sur parole » et « ni un échec sur parole » ont ici la même cause
et se réparent avec la même phrase : **on ne conclut pas de ce qu'on n'a
pas lu.**

### Et une empreinte constante pour tout ce qui ne se lit pas

`_fingerprint` rendait la chaîne `"unreadable"` — la même pour tous. Deux
fichiers différents comparaient donc égaux, et un fichier réécrit mais
resté illisible passait pour **inchangé**, alors qu'on ne l'avait jamais
ouvert. Elle rend `None` désormais, ce qui force l'appelant à ranger le
fichier ailleurs que dans un constat.

### Ce qui est ajouté

`WorkspaceSnapshot` porte `lisible` et `illisibles`. `WorkspaceDiff` porte
`indetermines` — une quatrième case, ni créé, ni modifié, ni supprimé.
Un fichier illisible d'un côté ou de l'autre y va : le compter comme créé,
ce que faisait la version précédente pour « illisible avant, lisible
après », donnait une preuve de travail à partir d'une permission qui
change. `touched_anything` ne les compte pas, et `summary()` ne dit plus
« rien n'a changé » quand il ne sait pas — une affirmation qu'on n'était
pas en position de faire.

`MissionVerification.verdict` nomme enfin le tri-état, et **réutilise le
vocabulaire du contrat de mission** (HOS-221) : `reussi | echoue |
indisponible`. En inventer un second aurait donné deux façons de dire
« on ne sait pas », donc une de trop, et la question « laquelle croire ? »
à chaque lecture. `verified` et `contradicted` restent à côté : les
appelants existants ne changent pas, un nouveau n'a plus à recomposer le
troisième état à partir des deux autres.

### Une alarme, et une qu'on refuse de poser

`mesure_impossible` distingue « rien à mesurer » de « ça devait être
mesurable et ça ne l'a pas été ». Seul le second émet
`mission.non_mesuree`.

Une mission sans workspace lié est le cas **normal et fréquent** ; en
faire une alarme donnerait une alarme qui sonne tout le temps, donc une
alarme débranchée dans la semaine. C'est la leçon du canary (HOS-218), et
elle vaut ici aussi. Un workspace lié qu'on n'a pas su lire, en revanche,
est un défaut d'instrument — et un instrument muet se répare.

L'événement est distinct de `mission.unverified` : celui-là dit « le
disque contredit », celui-ci dit « le disque n'a rien dit ». Les
confondre ferait passer un instrument muet pour un verdict.

### Mesures

19 gardes ajoutées ; les 48 gardes existantes de la vérification tiennent
sans modification. Suite complète : **5 008 vertes**, 3 ignorées.


## HOS-220 et HOS-221 — Le contrat, le registre, et la lignée (2026-09-03)

Le jalon 5 : « qu'est-ce qui devait être vrai à la fin ? » et « qu'est-ce
qui a été fait, avec quoi, et pourquoi le premier essai a raté ? ». Deux
questions que Hermes ne savait pas trancher, et qui ont chacune coûté
quelque chose de mesurable.

### HOS-220 — La seconde porte que HOS-215 avait laissée ouverte

`DatabaseConfig(name="hermes_os")` rendait `sqlite:///hermes_os.db` — un
chemin **relatif**, donc un fichier dans le répertoire courant, donc dans
le dépôt, que la prochaine mise à jour remplace. HOS-215 avait sorti
l'état pour `Settings` et pas pour ceci : deux défauts par défaut, un
seul traité. Un nom nu se résout maintenant sous la racine d'état ; un
chemin donné explicitement passe intact, sans quoi une base de test sur
`tmp_path` atterrirait dans l'état réel de l'utilisateur.

Le test de `tests/production` qui affirmait `sqlite:///test_db.db` est
**amendé, pas supprimé** : il gardait la bonne propriété avec la mauvaise
valeur. C'est le deuxième défaut que la remise en service de ce second
arbre de tests met au jour.

### HOS-221 — Le tri-état, et le refus de confondre une ignorance

`backend/runs/contrat.py` porte quatre états de critère et trois verdicts
de vérificateur. La règle centrale est celle qu'Agent OS met en capitales
dans `src/lib/contract.ts` : *never conflate unavailable with passed*.

Ce dépôt l'a enfreinte le 2026-08-30. `img07` était `indéterminé` — le
relecteur n'avait pas su conclure — et cet état n'avait nulle part où
aller dans une vérification qui rend `bool`. Il s'est rangé à côté des
plans jugés bons. Un contrat dont un critère est `invérifiable` n'est
maintenant **pas tenu**, et son résumé le dit en toutes lettres.

Trois refus à l'écriture, chacun visant un contrat qui serait tenu quoi
qu'il arrive : pas d'objectif, pas de critère d'acceptation, ou un
critère sans **vérificateur nommé**. Le dernier est le moins évident et
le plus utile : sans le nom du vérificateur, « invérifiable » ne dit pas
*ce qui* manque, et un rapport qui ne le dit pas ne fait pas agir.

Ce qui change par rapport à Agent OS : leurs critères s'écrivent en EARS,
une syntaxe d'exigences anglophone taillée pour un formulaire. Les
missions de Hermes viennent de l'agent. Un critère est ici un texte plus
le nom de qui doit le trancher.

### HOS-221 — Le registre, et ce qu'il aurait épargné

La nuit du 29 au 30 août, **trois fois**, la question « avec quel modèle,
et pourquoi le premier essai a raté ? » n'a pas eu de réponse sans aller
lire des fichiers JSON écrasés à chaque exécution. L'archivage du journal
a dû être écrit en pleine nuit, pendant que la production tournait.

`backend/runs/registre.py` porte le run : sa mission, son modèle, son
runtime, ses jetons, son issue, **son parent** et son rang de tentative.
`lignee()` rend la chaîne complète, et une reprise **doit dire pourquoi**
— une lignée muette ne répond pas à la question qu'on lui posera six
semaines plus tard.

L'invariant d'état est repris d'Agent OS et vit **dans le SQL**, pas en
Python : un `CASE WHEN statut IN (…terminaux…) THEN statut ELSE ? END`
qu'aucun appelant distrait ne peut contourner. Un défaut trouvé en le
mesurant : gelé sur le seul statut, un second appel réécrivait quand même
`cause` et `raison`, produisant un run figé sur `echoue` avec le motif du
mauvais appel — une trace pire que pas de trace, parce qu'elle a l'air
d'en être une. Le gel couvre maintenant **chaque colonne**.

`busy_timeout=5000` manquait à `DatabaseManager` : WAL laisse un lecteur
pendant une écriture, pas deux écrivains, et sans lui la seconde lève
« database is locked » au lieu d'attendre son tour.

### Trois choses délibérément non faites

**Pas de table `run_events`.** Hermes a déjà un bus d'événements durable,
rejouable par plage et par motif, à identifiants idempotents. Porter la
seconde table d'Agent OS créerait **deux magasins d'événements** —
l'architecture parallèle que le cahier interdit à sa propre règle 4. Le
registre porte les runs, le bus porte les événements, `run_id` les
corrèle. Un test le garde : le schéma ne contient qu'un `CREATE TABLE`.

**Pas de troisième couche SQLite.** `DatabaseManager` et
`MigrationManager` étaient orphelins — utilisés par personne hors de
`backend/storage/` — mais réels et corrects. Les doubler aurait ajouté
une couche de plus au lieu de rebrancher celle qui existait.

**La cause d'échec n'est pas devinée.** `Cause` existe et nomme onze
remèdes distincts, mais `_clore_le_run` ne la renseigne pas : classer un
échec depuis un message d'erreur demande la taxonomie qui fait l'objet de
son propre jalon. Deviner maintenant produirait des étiquettes fausses,
et une étiquette fausse coûte plus cher qu'une case vide — parce qu'on la
croit. `raison` porte l'erreur brute, qui elle est mesurée.

### Le registre est branché, et c'est le point

`approvals.py`, `DatabaseManager`, `MigrationManager` : du code réel,
correct, testé, **appelé par personne**. Un registre de runs qui finirait
comme eux ne servirait qu'à faire croire que la traçabilité existe.

`MissionExecutor.prepare()` ouvre le run, `finalize()` le clôt, et la
trace est en meilleur effort de bout en bout — une télémétrie qui casse
la mission qu'elle décrit ne vaut rien. Un test échoue si `_clore_le_run`
se met à deviner une cause ; un autre si un registre en panne fait
échouer une mission.

### Ce qui reste su et non traité

`Statut.PERDU` existe dans le vocabulaire et **rien ne le pose** : détecter
un run dont le processus a disparu demande un balayage au démarrage, qui
n'est pas construit ici. Et une exception nue levée par un exécuteur de
tâche traverse `execute_task` sans que `finalize()` soit atteint — le run
reste alors `en_cours` indéfiniment. Les deux se règlent au même endroit,
et ce n'est pas ce jalon.

### Mesures

56 gardes ajoutées. Suite complète : **4 989 vertes**, 3 ignorées.


## HOS-215 a HOS-219 - Quatre controles avant de batir quoi que ce soit (2026-09-03)

La lecture du code d'Agent OS (HOS-214) a montre que trois manques
classes « confort » sont des **controles de securite**. Ils passent donc
devant le Contract et le Run Ledger : les construire apres reviendrait a
batir la tracabilite dans un dossier effaçable, au-dessus d'une memoire
empoisonnable.

### HOS-215 — L'etat de l'utilisateur sort du depot

`data/db` 17,1 Mio, `data/eventbus` 8,2, `data/snapshots` 1,1, plus
`_memory_.db` — **tout vivait dans le repertoire de l'application**.
`.gitignore` les protegeait de git ; rien ne les protegeait d'une mise a
jour, qui remplace ce repertoire. Ce qui aurait disparu : la base, la
memoire, le bus d'evenements, et les instantanes — c'est-a-dire la
capacite de reprise elle-meme.

`backend/core/etat.py` resout une racine unique hors du depot —
`%LOCALAPPDATA%\HermesOS` sur Windows, `HERMES_DATA_DIR` primant — et
**refuse toute racine qui y retomberait**, meme demandee explicitement :
le permettre par configuration laisserait le defaut revenir par la porte
qu'on vient de fermer.

`preserve_set()` rend la liste de ce qu'une mise a jour ne doit jamais
toucher. Rendue comme une liste et non documentee en prose : un
installeur, une sauvegarde et un test peuvent la lire, et elle ne peut
pas diverger de ce que le code utilise. C'est le defaut du « preserve
set » d'Agent OS, qui vit dans un fichier Markdown.

`scripts/migrer_etat.py` a deplace **26,6 Mio**, en essai a blanc par
defaut, sans jamais ecraser un contenu different, et sans rien supprimer
avant d'avoir relu et compare.

**Une erreur de classification, trouvee par un test.** `data/workflows`
etait dans la liste des dechargements. Or ses fichiers sont **suivis par
git** : c'est du contenu livre avec l'application. Les deplacer a fait
passer `/workflows` de deux entrees a zero, et le test l'a dit
immediatement — « no workflows shipped, this test would pass vacuously ».
Le critere n'est pas « ou c'est range » mais **qui l'a ecrit** : ce que
git suit se remplace a chaque mise a jour, ce que l'utilisateur produit
doit lui survivre.

### HOS-216 — La memoire ne sert pas ce qu'elle n'a pas verifie

Ce n'est pas de la qualite de donnees, **c'est la defense contre
l'injection de prompt**. Un agent lit une page web ou un depot clone, y
trouve un texte ecrit pour lui, ce texte entre en memoire, et au tour
suivant `search()` le sert comme un fait. L'attaque n'a plus besoin de se
rejouer : elle est installee.

`backend/memory/confiance.py` pose la regle qu'Agent OS garde dans
`m8-prompt-injection` : **toute origine non humaine part en quarantaine,
quel que soit son contenu**. C'est le point le moins intuitif et le plus
important — un filtre qui cherche des formulations suspectes se contourne
en changeant de formulation. On juge la provenance.

`search()` et `search_experiences()` filtrent par defaut.
`inclure_quarantaine` est **nommé et faux** : un appelant qui veut du
contenu non verifie doit le dire, et ça se lit a la relecture. Un test
garde que le parametre reste keyword-only, parce qu'un drapeau
positionnel se passe par accident.

Une promotion **nomme qui l'a decidee**, sinon elle est refusee : sans
acteur, on ne peut plus revenir sur la decision — ce qui est precisement
ce qu'on veut pouvoir faire apres une injection reussie.

### HOS-217 — Un workspace ne reecrit pas ce qui gouverne l'agent

Deux scenarios, dont aucun n'exige un attaquant. Un depot clone arrive
avec son `.mcp.json` ou ses hooks, et l'agent herite d'outils que
personne ne lui a donnes. Ou l'agent ecrit lui-meme dans les fichiers qui
le gouvernent, et elargit ses propres permissions.

`backend/security/derive_workspace.py` releve l'empreinte de dix fichiers
et dossiers gouvernants — `CLAUDE.md`, `.mcp.json`,
`.claude/settings.json`, `.claude/hooks`, `.claude/skills`… — et compare.

Un dossier gouvernant est releve **fichier par fichier** : hacher
`.claude/hooks/` globalement dirait « quelque chose a change » sans dire
quoi, et un hook execute du code.

Il **releve et compare, il ne decide pas**. Bloquer, demander une
approbation ou seulement consigner releve de la politique, et cette
decision appartient a Aegis.

Et le tri-etat s'applique : une empreinte qu'on n'a pas pu prendre est
rapportee `INCONNU`, jamais « inchange ». On ne peut pas affirmer qu'un
fichier de gouvernance est intact quand on n'a pas su le lire.

### HOS-218 — Ce qui sort d'un agent est surveille pendant qu'il parle

Le canary est la meilleure idee du code d'Agent OS. On ne peut pas
enumerer tout ce qu'un agent ne doit pas dire, mais on peut savoir quand
il dit **une chose precise** qu'il n'aurait jamais du voir : une fausse
valeur, connue de nous seuls, plantee dans son environnement. Si elle
ressort, c'est que l'agent lit et recrache son environnement — donc que
les vrais secrets qui vivent a cote sont exposes de la meme façon. On n'a
pas besoin de savoir comment la fuite se produit.

`backend/security/surveillance_flux.py` porte aussi :

- un **report de 512 caracteres** entre deux blocs — un secret coupe par
  la fragmentation du flux passerait sinon entre les mailles ;
- une detection de **silence**, parce qu'un agent qui se tait n'echoue
  pas, il attend, et l'attente ressemble au travail. C'est la leçon du
  decodage qui a rampe quarante minutes le 2026-08-30 sans lever une
  seule erreur ;
- un plafond de **cout**.

Trois refus deliberes. Le module **ne tue pas** le processus : il
rapporte, et l'appelant decide. Un rapport de fuite **ne contient jamais
la valeur** — ce serait une seconde fuite ; il donne sa longueur. Et une
valeur de moins de huit caracteres n'est pas surveillee : « 1 », « true »
se retrouvent partout dans une sortie normale, et une alarme qui sonne
pour rien est debranchee dans la semaine.

### HOS-219 — Les deux decisions deleguees

**Le pare-feu de donnees refuse par defaut.** L'asymetrie des erreurs le
commande : classer trop haut coute une gene visible et reversible ;
classer trop bas envoie un secret chez un tiers, definitivement, sans que
personne le sache. Trois garde-fous pour que ce soit tenable — le refus
est nomme, il se contourne une fois et explicitement, et un contournement
repete propose une regle au lieu de s'installer en silence.

**La structuration se fait maintenant, l'authentification non.**
`user`, `project` et `workspace` entrent dans le modele de donnees au
moment ou le Run Ledger cree ses tables : trois colonnes coutent trois
colonnes maintenant, et une migration sur des donnees reelles plus tard.
L'authentification, non : Hermes ecoute sur `127.0.0.1` et une
authentification apporterait une surface sans proteger de rien de reel —
ce serait de la securite apparente.

La ligne a ne pas franchir est gardee par un test : tant qu'il n'y a pas
d'authentification, `user_id` ne doit jamais servir de controle d'acces.
C'est un champ de traçabilite, et un cloisonnement fonde dessus n'en
serait pas un.

### Mesures

62 gardes ajoutees sur les quatre jalons. Suite complete verte.


## HOS-214 - Le cahier des charges, confronte au code (2026-09-02)

Un cahier de 111 points a ete transmis, inspire d'Agent OS, d'OpenRouter
et d'OmniRoute. Ses 111 points ont ete sondes dans le depot, puis le code
source d'Agent OS a ete lu.

### Ce que la confrontation donne

| Etat | Compte | Part |
|---|---|---|
| existe et tient | **46** | 41 % |
| existe a moitie | **28** | 25 % |
| absent | **35** | 32 % |
| ecarte | 2 | 2 % |

Un cahier qui demande de batir ce qui existe coute autant qu'une roadmap
en retard. Six verdicts ont ete retournes dans les deux sens en relisant
les faux positifs des mots courants — `scope`, `score`, `canonical`,
`objectif`, `reserve`.

### Agent OS, ce qu'il est reellement

**Une application Next.js en TypeScript** : 369 fichiers `.ts`, 124
`.tsx`, ~67 000 lignes, contre 1 112 de Python. 86 modules dans
`src/lib`, 236 points d'API sur 47 domaines, 46 fichiers de test. Le
cahier ne le mentionnait nulle part, et **aucune ligne n'est reprenable**
— ce qui se transfere est son modele de donnees, ses invariants et son
modele de menaces.

Verifie : **zero occurrence d'OmniRoute** dans son code. Le cahier avait
raison, ce n'est pas une dependance d'Agent OS.

### La suite adverse a reordonne la roadmap

Leur lot de tests `m8` decrit des attaques que Hermes ne pare pas, et
trois manques que j'avais classes « confort » se revelent etre des
**controles** :

**La quarantaine memoire est la defense contre l'injection de prompt.**
Leurs tests gardent une seule propriete : le contenu en quarantaine
n'entre jamais dans le contexte resident ni dans une recherche sans
drapeau explicite, et l'origine non humaine est mise en quarantaine *quel
que soit son contenu*. Dans Hermes, une memoire produite par un agent
devient un fait immediatement.

**Un agent peut modifier la configuration qui le gouverne.**
`m8-hostile-config` detecte comme derive un workspace qui ajoute
`.claude/settings.json`, modifie `.claude/hooks`, ajoute un serveur MCP
dans `.mcp.json` ou modifie `CLAUDE.md`. Leur mecanisme est une table de
lignes de base comparee a chaque run. Hermes ne pare pas ça.

**L'etat utilisateur vit dans le depot.** 18 Mo de base, 8,2 de bus
d'evenements, 2,2 de snapshots. La premiere mise a jour qui remplace le
repertoire efface la base, la memoire et la capacite de reprise. Leur
reponse est un « preserve set » explicite et une base rangee hors de
l'application.

Ces quatre jalons — separation de l'etat, quarantaine, ligne de base de
configuration, canary — passent **devant** le Contract et le Run Ledger.
Les construire apres reviendrait a batir la tracabilite dans un dossier
effaçable, au-dessus d'une memoire empoisonnable.

### Trois gains caches sous un « ca existe deja »

**Hermes ne sait pas annuler une modification de fichier.**
`snapshot_manager` serialise l'etat de base ; leur checkpoint est une
reference git sur un commit detache, via un index temporaire, avec
verification d'integrite par re-hachage. Complementaires, pas redondants.

**La verification est booleenne.** Chaque controle de `verification.py`
rend `-> bool`. Ils distinguent `passed | failed | unavailable`, avec le
commentaire « never conflate unavailable with passed », et le gardent
dans leur suite de **securite**. Le cas s'est produit le 2026-08-30 :
`img07` etait `indetermine` et cet etat n'avait nulle part ou aller.

**L'approbation existe et n'est appelee nulle part.** `approval_engine`
sait `required_approvals` et `delegated_to`. Aucun chemin reel n'y passe.

### Deux points ou Hermes est devant

**Les sessions d'agent.** Ils ont mesure `hermes -z` par tour a ~28 s de
demarrage a froid et l'ont contourne par un serveur global chaud sur
`:8642`. HOS-138 tient une session ACP **par mission** — 220 Mio
mesures, tours serialises par un verrou.

**Le bus d'evenements.** Le leur est une seconde table `run_events` avec
`seq = MAX+1` sous transaction. Celui de Hermes est durable, rejouable
par plage et par motif, avec des identifiants idempotents. Le Ledger
portera les runs, pas les evenements — en porter un second creerait
l'architecture parallele que le cahier interdit a sa propre regle 4.

### Ce qui est ecarte, et pourquoi

**Le pool de comptes multiples chez un meme fournisseur.** Le cahier
demande de respecter les conditions des fournisseurs puis decrit un
mecanisme dont la finalite est d'agreger des quotas gratuits en faisant
tourner plusieurs comptes. C'est une violation des CGU de la plupart
d'entre eux.

**SEO, Leads, CRM, Music, Games.** Classes en extensions par le cahier
lui-meme, puis reintroduits dans sa liste finale. Ils n'entrent pas tant
que l'architecture de plugins n'existe pas.

### Surfaces

`docs/cahier-des-charges-hermes-2.md` — le cahier adapte, qui fait foi.
`docs/sondage-cahier-111-points.md` — les 111 points, un par un, avec la
preuve de chaque verdict. `ROADMAP.md` chapitre I — dix-neuf jalons
ordonnes.


## HOS-213 - La commande documentee etait plus etroite que la configuration (2026-09-02)

`tests/` — 2 594 tests, 53 % du depot — ne se collectait plus depuis
HOS-175. Vingt-deux jours, trente-sept jalons.

### La cause n'etait pas la configuration

`pytest.ini` declare `testpaths = backend/tests tests` depuis HOS-111,
avec un commentaire qui raconte precisement cet incident : 2 869 tests
que personne n'executait, 33 rouges dedans dont un vrai defaut
fonctionnel. La configuration etait juste.

C'est `CLAUDE.md` qui documentait `pytest backend/tests`. **Un chemin
passe en argument ecrase `testpaths`.** La commande documentee etait plus
etroite que la configuration, et l'angle mort s'est rouvert le jour ou on
l'a ecrite.

HOS-111 avait traite l'occurrence, pas la cause.

### Trois defauts dans l'arbre abandonne

**Un module qui ne s'importe plus.** `tests/conversation/test_conversation.py`
importait `WhisperProvider`, `CloudSTTProvider`, `PiperProvider` et
`CloudTTSProvider` — supprimes a HOS-175 parce que chacun se declarait
disponible sur un simple import et levait `NotImplementedError` au
premier appel. La suppression etait juste ; le test est reste sur elles.
Reecrit sur `PiperLocal` et `WhisperLocal`, les implementations reelles,
avec une garde qui refuse le retour des quatre souches.

**Une garde qui protegeait le chemin qu'on n'emprunte pas.**
`fake_inference.install()` ne patchait que `_default_chat`. Or
`execute()` choisit entre trois producteurs d'appel :

| Condition | Producteur |
|---|---|
| runtime `hermes-agent` | `_hermes_agent_chat_for` — **sous-processus** |
| mission liee a un workspace | `_chat_with_tools_for` — boucle d'outils |
| sinon | `_default_chat` — appel simple |

Le premier est le cas **par defaut** : Hermes Agent est le cerveau des
missions, et une `ExecutionMeta` sans workspace y aboutit.
`test_execute_single_task` et `test_get_goal` lançaient donc un vrai
sous-processus et bloquaient l'arbre entier. Apres correction : **0,5 s
au lieu de seize minutes**.

**Une course prise pour une regression.**
`test_sortie_de_l_agent.py::test_une_sortie_volontaire_est_nommee_comme_telle`
dormait 0,3 s puis diagnostiquait un sous-processus cense etre mort. Sur
une machine chargee, le demarrage de l'interpreteur depasse ce delai : le
diagnostic repondait — a juste titre — « le processus vit encore ». Le
test echouait sur la vitesse de la machine. Remplace par une attente
bornee de la vraie fin du processus ; stable sur trois executions.

### Ce qui garde la correction

Trois gardes, dont une qui surveille **la documentation** : elle lit les
blocs `bash` de `CLAUDE.md` et echoue si un chemin y est passe en
argument. Verifiee rouge sur le defaut, verte apres.

`tests/` passe de « ne se collecte pas » a 2 594 verts en 1 min 40.
Suite complete : **4 865 passed, 3 skipped**, 4 min 44.


## HOS-212 - Juger une voix et une image sur ce qu'elles sont, pas sur leur existence (2026-08-30)

Une premiere production reelle a servi de revelateur, comme HOS-211. Trois
instruments manquaient, et chacun a trouve un defaut des sa premiere
utilisation.

### La narration n'etait jugee que sur sa duree

Chatterbox rend un WAV valide, d'une duree plausible, **quoi qu'il ait
prononce**. Une replique ou il boucle sur un groupe de mots, ou bien ou il
ajoute un mot apres la fin du texte, ne se distingue en rien d'une bonne
replique : meme format, meme duree approximative, aucune erreur.

L'utilisateur a entendu deux defauts sur la premiere narration clonee :
« cette nuit » repete dans la premiere replique, et un « ok » ajoute a la
toute fin. `scripts/verifier_narration.py` transcrit et compare — il les
retrouve tous les deux, et en trouve un troisieme que personne n'avait
signale : **« les marais » a la place de « les marees »**. Sur une video
scientifique, ca change le sens.

La voix precedente sert de temoin, et c'est elle qui rend la mesure
utilisable : une transcription se trompe sur les homophones, et « les
marees » transcrit correctement sur la voix temoin prouve que l'ecart
vient de la voix clonee, pas du transcripteur. Deux autres ecarts —
« et »/« elle », « remarqueras »/« remarquerais » — sont du bruit de
transcription, et le temoin le montre aussi.

`faster-whisper` tourne sur processeur : la verification reste donc
possible pendant un rendu.

### Les reglages de voix ne se transposent pas d'une reference a l'autre

`exaggeration 0.3 / cfg_weight 0.3` avaient ete mesures en HOS-195 sur la
reference « Michael ». Les reprendre pour une autre voix etait une
supposition, et elle etait fausse.

Le banc, sur les trois repliques fautives :

| reference | cfg 0,3 | cfg 0,5 | cfg 0,7 |
|---|---|---|---|
| brute — finit en pleine parole | « debut » ajoute | derive complete | mot deforme |
| close — coupee sur un silence | « marais » | **propre** | « marais » |

Aucun des deux leviers ne suffit seul. La reference fournie se terminait
**en pleine parole** — mesure a -24,1 dB sur la derniere demi-seconde :
rien n'y signalait qu'un enonce s'acheve, ce qui explique un modele qui
continue apres le texte. Coupee sur un silence reel avec un fondu et
350 ms de blanc, et a `cfg_weight 0.5`, les trois defauts disparaissent.

Corriger les defauts **allonge** la parole : 30,04 s contre 26,88 s. Le
modele ne bacle plus les fins de phrase.

### Un clone se verifie a la mesure

`scripts/hauteur_voix.py` reprend la methode de HOS-195 — hauteur mediane
par autocorrelation, sur les trames voisees seulement — au lieu de la
reecrire a chaque changement de voix. La reference fournie est a 85,4 Hz ;
le clone rend 81,1 / 85,6 / 86,3 Hz. Il s'est bien deplace vers elle, et
non vers les 157 Hz de la voix par defaut du modele.

Le nombre de trames voisees compte autant que la hauteur : un clone qui
n'en produit que quatre sur une phrase entiere n'a pas une hauteur
imprecise, il n'a presque pas de voix. Releve sans conclusion : la
dispersion de hauteur de ce clone est le double de celle de « Michael »
(84-109 contre 32-43).

### La synthese sur processeur : possible, et mauvaise

`synthetiser(appareil="cpu")` existe pour narrer pendant qu'une nuit de
rendu tient les 16 Gio — l'arbitrage refuse alors la carte, a juste
titre, et attendre deux heures serait absurde. Sur processeur la synthese
ne reserve rien, puisqu'elle ne prend rien.

Mesure : **une replique en 49 minutes sur processeur, sept en 119 secondes
sur la carte.** Le repli reste juste en principe ; a ce rapport, mieux
vaut attendre. C'est ecrit ici pour que personne ne le redecouvre.

### Le relecteur ne savait pas lire une image fixe

`extraire()` demandait la duree du fichier, qui vaut zero pour un PNG, et
rendait une liste vide : « aucune image n'a pu etre extraite du plan ».
Vrai au pied de la lettre, faux sur le fond. Les sept references SDXL
d'une production finissaient `indetermine`, donc jamais confrontees a leur
consigne — alors que ce sont elles qui decident du decor de tous les plans
qui en decoulent.

Une image est son propre cadre. Des la correction, le relecteur a rejete
une reference en nommant deux ecarts reels : un sol pave annonce comme
asphalte, et une **Lune en croissant** la ou la consigne demandait une
pleine Lune. Sur une video dont le sujet est la disparition de la Lune, le
second n'est pas un detail.

Releve sans conclusion : la meme image a recu deux verdicts opposes du
meme modele a temperature 0,1. Une seule relecture ne fait donc peut-etre
pas une garde. Non verifie proprement — la carte etait prise, et sonder
pendant un rendu mesure la contention.

### Le relecteur empoisonnait le rendu suivant

Trouve en cherchant pourquoi un plan sur deux rampait. Le motif etait
net et je ne le lisais pas : **le premier rendu apres un redemarrage
passe toujours, le second tient quarante minutes sans aboutir.**

La file relit chaque plan avec un modele de vision servi par Ollama.
Ollama garde un modele **resident cinq minutes** par defaut, et le plan
suivant demarre bien avant.

| mesure | valeur |
|---|---|
| ce que le relecteur retient | **2,41 Gio de VRAM** |
| expiration par defaut | 5 minutes |
| ecart relecture de p01 / depart de p02a | **90 secondes** |

Sur 15,98 Gio dont un decodage reclame pres de 13, ces 2,41 Gio suffisent
a faire basculer le rendu entier sur la memoire partagee. Le rendu ne
debordait pas tout seul : il debordait de ce que le relecteur tenait
encore.

Trois plans perdus avant de le voir — 39 min, 40 min, puis un abandon en
cascade. `keep_alive: 0` : le relecteur rend la carte des qu'il a
repondu, verifie a `/api/ps`. Il travaille **entre** deux rendus sur une
carte qui n'en supporte qu'un ; rester charge n'avait aucun interet et
coutait le plan suivant.

Les chiffres se referment exactement :

| | |
|---|---|
| pic de VRAM d'un rendu, mesure sur `p02a` | **13,98 Gio** |
| carte | 15,98 Gio |
| marge disponible | **2,00 Gio** |
| ce que le relecteur retenait | **2,41 Gio** |

Il manquait 0,41 Gio. Le rendu ne debordait pas d'un peu : il debordait
de tres exactement ce qu'un modele de 2,41 Gio prend a une marge de 2,00.

Corrobore par le resultat : `p02a`, qui avait tenu 2 404 s sans aboutir,
passe en **1 365 s** — le meme temps que `p01` a 1 358 s. Le second plan
n'etait pas plus lourd que le premier ; il etait le premier a subir le
relecteur.

### Un montage amputé rendait `success: true`

Le defaut le plus grave de la nuit. `montage.assembler` verifie que le
resultat dure ce que les plans **qu'on lui donne** annoncaient. Il n'a
aucun moyen de savoir combien on aurait du lui en donner.

Il a donc valide une video de **4,0 secondes faite d'un plan sur dix**,
en releguant au rang d'avertissement une narration de 35,7 s posee
dessus — un ecart de +31,7 s.

C'est le `success: true` au-dessus de rien que ce depot traque depuis le
debut, passe par une porte que personne ne gardait. Le refus est pose chez
l'appelant, qui est le seul a savoir ce qu'il attendait :
`finaliser_lune.py` refuse d'assembler si un seul plan manque, et traite
un ecart voix/image au-dela de six secondes comme une erreur.

### Attendre un fichier n'est pas attendre une fin

Meme incident, plus petit : le script de finalisation guettait
l'apparition du MP4 pour enchainer. Or le fichier est ecrit **avant** la
relecture. Il a enchaine trop tot, la file suivante a ete refusee — « une
file de nuit tourne deja » — et toute la production est tombee. On attend
desormais `en_cours` a faux.

### Les consignes, reecrites sur des defauts constates

L'utilisateur, sur le premier plan rendu : une voiture garee sur le
trottoir, des passants trop nombreux, trop rapides, qui apparaissent et
disparaissent. Trois regles en sont sorties, appliquees a tous les plans :

**Nommer ce qui ne bouge pas.** LTX anime tout ce qu'on ne fige pas
explicitement.

**Dire la vitesse reelle.** Le modele comprime volontiers une action
entiere dans les quatre secondes qu'on lui donne. « Real-time speed, this
is not a time-lapse » corrige l'impression d'accelere.

**Interdire les entrees et sorties de cadre.** Un passant qui entre
pendant le plan n'a aucune histoire avant : le modele le fabrique image
par image, et il scintille.

Effet de bord mesure : cinq formulations negatives sur la voiture mal
garee suppriment la **classe d'objet entiere**. La reference corrigee n'a
plus aucun vehicule, et le relecteur a rejete l'image parce que la
consigne en demandait encore. C'etait la consigne qui etait fautive.

Backend 2263 passed, 2 skipped.


## HOS-211 - Ce qui manquait pour produire une video, et non plus des plans (2026-08-29)

Un cahier de production reel — dix plans, deux chaines de continuite, une
narration, des sous-titres — a servi de revelateur. Le Studio savait
rendre des plans ; il ne savait pas en faire une video.

### Cinq manques, dont un structurel

**La file de nuit ne savait pas enchainer.** `POST /studio/night`
composait **tous** les graphes a la soumission. Un plan dont l'image de
depart est la derniere image du plan precedent etait donc inexprimable :
ce fichier n'existe pas quand on decrit la nuit. Toute continuite
visuelle — meme decor, meme lumiere, meme personnage d'un plan au suivant
— etait hors de portee d'une nuit.

Un plan peut desormais etre decrit par `gabarit` + `parametres`, compose
**au moment de son rendu**, et declarer `depend_de`.

Le point delicat n'est pas la resolution, c'est l'echec. Un plan dont le
predecesseur n'a rien produit repartirait du bruit, rendrait un MP4
parfaitement valide, et la rupture ne se verrait qu'au montage — apres la
nuit. C'est la forme de defaut que ce depot paie le plus cher :
`success: True` au-dessus de rien. Il est donc `abandonne`, en nommant le
plan manquant, et sans compter comme un echec de rendu : trois plans
dependant d'un meme absent arreteraient sinon la file entiere alors qu'un
seul defaut est en cause.

**Rien ne transportait une image vers l'entree de LTX.** SDXL ecrit dans
`E:\YouTube\Generations` ; `LoadImage` ne lit que le `input` de ComfyUI.
`/studio/last-frame` ne savait extraire que depuis une video.
`enchainement.preparer_depart()` fait les deux et refuse une extension
inconnue plutot que de la deviner.

**Une image de rapport different aurait ete etiree, en silence.**
`LTXVImgToVideo` recoit les dimensions du plan et redimensionne **sans
recadrer**. Une reference SDXL en 768 x 1344 (rapport 0,571) donnee a un
plan en 704 x 1280 (0,550) est deformee — visible sur un visage, et rien
ne le dit. Le recadrage est centre, coute 3,8 % de champ lateral, et les
dimensions visees voyagent avec la demande.

**Aucune image fixe ne devenait une video.** Quatre plans sur dix sont des
images avec un mouvement lent. `concat` enchaine des flux video : un PNG
n'en est pas un. `montage.animer()` produit un clip au format exact des
autres — meme taille, meme cadence, meme profil — parce qu'un plan qui
differerait ferait echouer l'assemblage a la toute fin, apres deux heures
de rendu. Le `zoompan` travaille sur une image agrandie huit fois : sur
l'image a sa taille finale, le cadre saute d'un pixel entier d'une image
a l'autre et la saccade se voit.

**La narration n'avait pas de respirations.** Chatterbox lit ce qu'on lui
donne. `montage.coller_voix()` intercale des silences reels — des entrees
`lavfi` et non un `apad`, qui allongerait la derniere replique et
accumulerait le decalage sans qu'aucune duree ne le dise.

### Le defaut trouve en eprouvant le reste

`assembler` portait `-shortest` avec le commentaire « l'image commande ».
Il fait la moitie du travail : il coupe bien une narration trop longue,
mais il coupe aussi **l'image** quand la voix est plus courte. Mesure :
trois plans de 6,0 s avec une voix de 5,4 s rendaient une video de 5,4 s
— six dixiemes de seconde d'image simplement absents, sans erreur.

`apad` complete l'audio de silence et `-shortest` coupe alors sur
l'image. C'est ainsi que la phrase devient vraie dans les deux sens.

Ce defaut existait depuis HOS-191. Il n'a jamais ete vu parce qu'aucune
narration n'avait ete plus courte que l'image.

### Ce qui s'ajoute au montage

Un lit sonore mixe **sous** la voix, boucle et coupe sur la duree de
l'image ; et une mise a l'echelle en sortie. 704 x 1280 vers 1080 x 1920
est un facteur 1,53 en lanczos, sans information nouvelle : c'est ce que
demandent les plateformes, qui reencodent de toute facon. L'appeler un
upscale serait mentir sur ce qu'on livre.

Les sous-titres sont incrustes **avant** l'agrandissement : les poser sur
l'image agrandie les garde nets.

### Surfaces

`POST /studio/assemble`, `POST /studio/animate`, `POST /studio/start-frame`.
`montage.assembler` existait depuis HOS-191 mais n'etait joignable que
depuis Python : une production lancee la nuit ne pouvait donc pas se
terminer toute seule.


## HOS-210 - Le reglage du decodeur se mesure au lieu de se supposer (2026-08-29)

Trois fois de suite — HOS-205, HOS-208, HOS-209 — le defaut visible venait
de la **meme** table ecrite a la main, `PALIERS_TUILE`. Trop prudente
d'abord (elle descendait a 64 la ou 128 tenait, d'ou le quadrillage), mal
calibree ensuite. HOS-209 a rectifie un seuil ; il n'a pas rectifie le
fait qu'un seuil ecrit a la main est faux des que quelque chose bouge.

Et l'echec tombe **au decodage, apres la diffusion** : vingt minutes de
calcul pour decouvrir que la tuile ne passait pas.

### L'essai a blanc

La memoire du decodeur ne depend que des **dimensions** du latent, jamais
de son contenu. Decoder un latent vide exerce donc le meme chemin memoire
qu'un vrai plan, sans charger un seul modele de diffusion. C'est la
technique qui avait permis toute la campagne de mesure ; elle est
maintenant dans le produit, derriere un bouton.

La recherche part de ce que la table propose, puis **monte** tant que ca
passe et **descend** au premier debordement. Une descente depuis 256
coutait jusqu'a sept essais de plusieurs minutes chacun — c'est-a-dire un
reglage qu'on renonce a mesurer.

### Quatre defauts de l'instrument, trouves en le faisant tourner

Aucun en relisant le code. Tous sur un chiffre invraisemblable.

**La memoire ne se libere pas entre deux essais.** Deux essais consecutifs
ont vu **19,29 puis 25,64 Gio deja alloues** sur une carte de 15,98 : le
second debordait pour une raison etrangere a ce qu'il mesurait. Sans
remise a zero, la recherche conclut sur du bruit. `/free` avant chaque
essai.

**Un decodage qui deborde ne s'arrete pas, et rien ne l'arrete.** Il
bascule sur la memoire partagee et rampe : un essai a tenu **quarante
minutes** sans aboutir ni echouer, le processus consommant une seconde de
CPU par seconde ecoulee. `/interrupt` ne mord pas dessus — verifie deux
fois, la carte restant a 14,18 Gio apres l'appel ; il a fallu relancer
ComfyUI. L'essai qui n'aboutit pas est desormais interrompu avant de
rendre la main, ce qui suffit pour un essai qui tourne normalement mais
**pas** pour celui-la. La seule protection reelle est de ne pas l'y
laisser arriver, d'ou le plafond ci-dessous — et la reponse le dit
maintenant : « la carte peut rester occupee ».

**« Ca passe » ne veut pas dire « c'est utilisable ».** La tuile 160
decode 768x416x97 en quatre minutes ; la 192 tenait encore apres vingt,
avec 14,18 Gio de VRAM sur 15,98. Une premiere version l'aurait retenue
comme « la plus grande qui passe », et cette lenteur se serait payee a
chaque rendu — a rebours de la consigne, « de la qualite, mais dans un
temps acceptable ». La montee est bornee a deux fois et demie le cout du
premier succes.

**Un verdict incertain n'est pas un debordement.** `delai` et `erreur`
arretent la recherche au lieu de la faire continuer, et la route ne dit
plus « aucune tuile ne passe » quand elle n'a rien mesure : c'est cette
confusion entre « la carte ne peut pas » et « je n'ai pas su lire » qui a
produit trois faux resultats pendant HOS-207.

### La table de depart

Cinq entrees y ont ete versees a la creation, tirees des rendus reels de
la campagne plutot que redemandees a la carte : 768x416 a 49, 121 et 257
images (tuiles 256, 160, 128), et 1280x704 a 121 et 217 images (128 et
64). Elle vit a cote des rendus, pas dans le depot : c'est une mesure
propre a cette machine, pas un fait du code. `PALIERS_TUILE` reste le
repli, et une table illisible ne bloque jamais un rendu.

### La mesure de bout en bout, faite

768x416 sur 97 images, par la route de l'interface, sur une carte vide :
**tuile 160**, deux essais, 1500,8 s au total. La 160 decode en 296,5 s ;
la 192 tenait encore apres 1203,9 s et a ete classee `delai`, ce qui a
arrete la montee sans rien conclure sur elle.

La table ecrite a la main proposait deja 160 pour ce plan : la mesure la
**confirme** ici plutot que de la corriger. C'est le resultat attendu dans
le cas courant — l'interet n'est pas que la table soit fausse partout,
c'est de ne plus avoir a le supposer. Avec le plafond de rampe, la meme
mesure aurait coute 741 s au lieu de 1204 pour le second essai, meme
reponse.

### Ce que l'ecran dit

Sous le formulaire, une ligne par plan : soit « Decodage eprouve sur cette
machine — tuile N, mesuree le … », soit un avertissement disant d'ou vient
le reglage affiche, et un bouton pour mesurer.


## HOS-209 - Le quadrillage : HOS-208 se trompait de cause (2026-08-29)

HOS-208 attribuait le quadrillage a un **recouvrement nul** : le calcul
`min(32, tuile // 4)` donnait 16 pour une tuile de 64, et le nœud divise
cette valeur par la compression spatiale du VAE (32), donc `16 // 32` = 0.
Le raisonnement etait juste et le calcul reellement fautif.

**Ce n'etait pas la cause.**

### Comment le defaut de diagnostic a ete trouve

Le meme plan, meme graine, rendu avec un recouvrement de 16 puis de 32 :
les pixels sont **rigoureusement identiques**, ecart maximal **zero**.
Seules les metadonnees PNG different — ComfyUI y grave le graphe, qui
portait bien les deux valeurs distinctes.

Le premier indice etait la taille des deux fichiers video, identique a
l'octet pres (11 032 Ko). C'est en la trouvant invraisemblable qu'il a
fallu verifier, exactement comme pour les autres defauts de cette
campagne : aucun n'a ete trouve en relisant le code.

HOS-208 avait donc ete commite et pousse **en presentant comme solution un
correctif inoperant**. Sans la demande d'un nouveau rendu, il restait au
depot comme un fait acquis.

### La vraie cause

La **taille** de la tuile, pas son recouvrement. 64 pixels font deux
unites latentes seulement, et le VAE n'a pas assez de contexte pour
decoder un carre aussi petit. Aucun fondu ne rattrape ca.

Et la table de HOS-207 etait **trop prudente** : elle descendait a 64 des
un volume de 90, alors que la mesure montre que 128 tient a 109 — soit
precisement le cas signale, 1280 x 704 sur cinq secondes.

| volume | format et longueur | tuile | verdict |
|---|---|---|---|
| 82,1 | 768x416, 257 img | 128 | passe |
| **109,0** | **1280x704, 121 img** | **128** | **passe (437 s)** |
| 109,0 | 1280x704, 121 img | 96 | passe (245 s) |
| 195,6 | 1280x704, 217 img | 64 | passe |

Le palier 128 monte donc de 90 a 110. La tuile 64 ne subsiste qu'au-dela
de sept secondes en format lourd, ou rien d'autre ne tient.

Contre-intuitif, releve au passage : la tuile 96 decode en 245 s contre
437 s pour la 128. Une tuile plus petite est donc **plus rapide** ici, la
memoire etant moins sollicitee — le compromis n'est pas « qualite contre
vitesse » dans le sens attendu.

### Ce qui est garde de HOS-208

Le calcul du recouvrement, corrige. Il est juste sur le fond — un
recouvrement qui vaut zero apres division ne sert a rien — et il est
desormais documente comme **sans effet mesurable**, pas comme un remede.
Le garder coute une ligne ; le presenter comme une solution serait
mentir.

### Ce que cet incident apprend

Trois defauts de suite ont ete vus par l'utilisateur avant de l'etre par
la mesure : le comptage des coutures, l'infirmation du gain de
`res_multistep`, et ce quadrillage. Le point commun est que l'indicateur
de dispersion mesure le **deplacement du contenu** — il est aveugle a un
motif fixe, et il l'etait des la construction.

Le correctif de HOS-208, lui, n'a pas ete verifie **avant** d'etre
pousse : le rendu de confirmation a ete lance apres le commit. L'ordre
inverse aurait evite de publier une fausse cause.

Backend 2210 passed, 2 skipped.

## HOS-208 - Le quadrillage : un recouvrement qui valait zero (2026-08-29)

> **Amende par HOS-209 le meme jour : cette cause est fausse.** Le meme
> plan rendu avec un recouvrement de 16 puis de 32 donne des pixels
> rigoureusement identiques, ecart maximal zero. Le correctif decrit
> ci-dessous est juste sur le fond mais **sans effet** sur le defaut
> signale. La vraie cause est la taille de la tuile — voir HOS-209.

L'utilisateur, sur le premier rendu en 1280 x 704 issu de HOS-207 : « je
n'ai pas de probleme de scintillement en revanche l'image forme comme un
quadrillage ».

Le scintillement etait bien corrige. Mais le correctif en avait introduit
un autre, dans le meme nœud.

### La cause

`VAEDecodeTiled` divise `overlap` par la compression spatiale du VAE, qui
vaut 32 — exactement comme il divise `tile_size`. Mon calcul etait
`min(32, tuile // 4)`, soit **16** pour une tuile de 64. Et `16 // 32`
vaut **zero** : les carres se juxtaposaient sans le moindre fondu.

| tuile | recouvrement avant | en latentes | apres |
|---|---|---|---|
| 256 | 32 | 1 | 2 |
| 160 | 32 | 1 | 1 |
| 128 | 32 | 1 | 1 |
| **64** | **16** | **0 — quadrillage** | **1** |

Le defaut ne touchait donc que la tuile de 64, c'est-a-dire uniquement
les plans lourds ou longs. Les autres paliers tombaient deja sur une
latente de fondu, ce qui explique que le paysage n'ait jamais quadrille
et que le defaut ait passe la validation precedente.

`recouvrement_spatial()` garantit desormais au moins une unite latente,
et plafonne a la moitie de la tuile — au-dela, les carres se recouvrent
plus qu'ils ne couvrent et le decodage paie deux fois le meme pixel.

### Ce que cet incident apprend

L'indicateur de dispersion utilise pendant toute cette campagne mesure le
**deplacement du contenu**. Il est structurellement aveugle a un motif
**fixe** : une grille immobile ne deplace rien, donc il ne la voit pas.
Aucune de ces mesures n'aurait pu attraper ce defaut.

C'est la troisieme fois de la campagne que l'œil de l'utilisateur voit ce
que les chiffres ne peuvent pas voir — apres le comptage des coutures
(quinze scintillements pour quinze tuiles, correspondance exacte) et
l'infirmation du gain de `res_multistep`. La lecon vaut d'etre ecrite :
un instrument ne mesure que ce qu'il a ete construit pour mesurer, et le
defaut suivant est rarement dans cette dimension-la.

### Temps de generation, mesure

22,7 minutes pour 5 secondes en 1280 x 704, decodage compris. Dans le
meme temps, le format paysage produit environ quatre plans de 5 secondes
— vingt secondes de matiere au lieu de cinq.

Quatre gardes-fous nomment l'incident, verifies rouges sur l'ancien
calcul. Backend 2210 passed, 2 skipped.

## HOS-207 - Une seule tuile temporelle, a toute longueur (2026-08-29)

HOS-205 avait mis `temporal_size` a 64. **Ce n'etait pas assez.**
L'utilisateur a compte les coutures a l'oeil : quinze scintillements sur
un plan que le code decoupait en quinze morceaux, trois sur celui qu'il
decoupait en trois. Un par couture, sans exception.

Il en faut donc **une**, pas « moins ». 64 ne donnait un bloc unique
qu'aux plans de deux secondes ; a cinq secondes il en laissait trois.

### Le prix, et pourquoi c'est le bon echange

`temporal_size` vaut desormais 4096 — 512 images latentes par tuile,
contre 33 pour le plan le plus long du gabarit. Le bloc est unique
quelle que soit la longueur.

Ce bloc coute de la memoire, et la seule variable qui reste pour la payer
est la taille des carres **spatiaux**. L'echange est favorable : une
couture spatiale tombe au meme endroit a chaque image, donc elle ne
scintille pas. C'est toute la difference entre les deux decoupages, que
mon vocabulaire avait confondus pendant une partie de la campagne.

### La table, mesuree

Volume = `pixels x images`, en millions. Decodage en un bloc.

| volume | format et longueur | tuile | verdict |
|---|---|---|---|
| 15,7 | 768x416, 49 img | 256 | passe |
| 38,7 | 768x416, 121 img | 160 | passe |
| 44,2 | 1280x704, 49 img | 256 | **deborde** (12,81 Gio) |
| 82,1 | 768x416, 257 img | 160 | **deborde** (13,13 Gio) |
| 82,1 | 768x416, 257 img | 128 | passe |
| 195,6 | 1280x704, 217 img | 64 | passe |

`tuile_spatiale()` choisit d'apres ce volume. Les paliers sont poses
**sous** la premiere mesure qui deborde, jamais entre deux mesures : une
extrapolation optimiste transformerait un rendu mediocre en rendu absent,
ce qui est bien pire.

### Longueur maximale par format

| format | longueur max, un seul bloc | tuile |
|---|---|---|
| 768 x 416 | **10 s** (257 img) | 128 |
| 1280 x 704 | **9 s** (217 img) | 64 |
| 704 x 1280 | 9 s (meme volume, grille transposee) | 64 |

Le 257 images en format lourd n'est pas un debordement mais un
**indetermine** : trente minutes de decodage sans aboutir. Rapporte comme
tel — confondre « la carte ne peut pas » et « je n'ai pas attendu assez »
est l'erreur qui a produit trois resultats faux pendant cette campagne.

### Le cout, qu'il faut connaitre avant de choisir un format

Decodage seul, format 1280 x 704, bloc unique :

| longueur | decodage |
|---|---|
| 7 s (169 img) | 253 s |
| 9 s (217 img) | **806 s** |
| 10 s (257 img) | ne finit pas en 30 min |

Le saut entre 7 et 9 secondes est brutal. Conclusion pratique, et c'est
celle de l'utilisateur : mieux vaut cinq plans de cinq secondes en
paysage qu'un plan de neuf secondes en format lourd — meme temps total,
cinq fois plus de matiere.

### Trois instruments de mesure jetes en route

La campagne a demande trois versions de la sonde, les deux premieres
ayant rendu des verdicts faux :

1. **Delai confondu avec debordement.** Un delai de 420 s plus court que
   certaines sondes (374 s mesurees) faisait compter tout depassement
   comme un manque de memoire. Elle a annonce qu'aucune tuile ne passait
   a 97 images, la ou un vrai rendu a 121 avait abouti.
2. **Deconnexion prise pour un delai.** ComfyUI ferme parfois la
   connexion en gerant un `out of memory` ; la boucle mourait dessus et
   rendait « delai » alors que l'historique portait un debordement
   lisible.
3. La troisieme reessaie, lit l'erreur reelle, et cherche en montant
   depuis les petites tuiles — descendre depuis 256 coutait vingt-cinq
   minutes avant le moindre verdict.

Aucun de ces defauts n'a ete trouve en relisant le code. Tous l'ont ete
sur un chiffre invraisemblable.

Backend 2206 passed, 2 skipped.

## HOS-206 - La file de nuit se lance enfin depuis l'ecran (2026-08-28)

L'utilisateur : « peux-tu m'expliquer a quoi sert l'interface nuit de
l'onglet studio ? il n'y a pas de bouton accessible ou autre je ne
comprends pas son interet ou utilisation ».

Il n'y avait effectivement aucun bouton. L'onglet ne savait que **lire**
le rapport du matin ; le lancement n'existait que comme outil MCP
`studio_night`, donc uniquement accessible en le demandant a l'agent dans
le chat.

C'est le troisieme cas identique en trois jours — la voix Michael
(HOS-196), les trois parametres de rendu (HOS-199), et maintenant la file
de nuit. Le motif est toujours le meme : une capacite backend reelle,
testee, et sans aucune commande a l'ecran.

### Pourquoi l'ecran ne pouvait pas la lancer

`POST /studio/night` exigeait un `graphe` ComfyUI complet par plan. Le
frontend n'en compose aucun, et c'est deliberé : la regle qui prime sur
tout dans ce depot reserve cette decision au gabarit ou a l'agent.

La route accepte desormais `gabarit` + `parametres` par plan, exactement
comme `/render` depuis HOS-194, et compose cote serveur. La voie du
`graphe` reste intacte pour l'agent — un test l'atteste, pour qu'elle ne
regresse pas au profit de la nouvelle.

### Ce que l'ecran annonce avant le clic

Une nuit tient la carte pendant des heures. Le formulaire calcule donc le
cout total de la file — nombre de plans x cout par plan, avec le modele
de HOS-199 — et l'affiche en heures. Un delai maximal par plan est
reglable : au-dela, le plan est abandonne et la file passe au suivant,
plutot que de tenir la carte jusqu'au matin sur un rendu qui ne sort pas.

Les reglages sont communs a toute la file, seule la consigne change d'un
plan a l'autre : une nuit sert a decliner un meme plan, pas a melanger
des formats. Et la consigne n'est pas decorative — c'est elle que le
relecteur oppose au fichier produit. Sans elle le plan finit
`indetermine`, ce qui est correct mais coute un rendu pour rien.

### Tests

Cinq, dont deux qui nomment le defaut : un plan sans gabarit ni graphe
est refuse **en nommant son rang** (sur une file de dix, savoir lequel est
mal decrit evite de relire les dix), et un gabarit invalide de meme.

Backend 2200 passed, 2 skipped. Frontend tsc propre, vitest 113/113.

## HOS-205 - Le scintillement : trouve, corrige, confirme a l'oeil (2026-08-28)

Apres trois tours de mesures infructueux, la cause du scintillement est
le **decoupage temporel du decodeur VAE**. C'est l'hypothese formulee des
le premier tour, ecartee sur un indicateur que le tour suivant a invalide,
et jamais reprise depuis.

### Le calcul que je n'avais pas fait

`VAEDecodeTiled` divise `temporal_size` par la compression temporelle du
VAE, qui vaut 8 pour LTX. Le reglage de 16 ne signifiait donc pas « seize
images par tuile » mais **deux images latentes par tuile**, avec une seule
de recouvrement.

| temporal_size | 49 images | 121 images | 257 images |
|---|---|---|---|
| **16 (ancien)** | **6 tuiles** | **15 tuiles** | **32 tuiles** |
| 64 (retenu) | 1 | 3 | 5 |

Un plan de dix secondes etait reconstruit a partir de trente-deux
morceaux. La description de l'utilisateur — « comme si la video etait
creee en ajoutant des petits morceaux de 0,5 seconde les uns apres les
autres » — decrivait litteralement ce que le code faisait.

### La seule mesure propre de la campagne

A graine fixee le debruitage est deterministe : les latents sont
**identiques** et seul le decodeur change. Aucun bruit de graine possible
— celui-la meme qui avait fabrique tous les faux positifs precedents.
Plan a camera fixe, ou toute vitesse mesuree est un artefact.

| graine | derive fantome a 16 | a 64 | reduction |
|---|---|---|---|
| 777 | 0,108 | 0,035 | **-68 %** |
| 1234 | 0,110 | 0,065 | **-41 %** |

Trois signaux independants concordent, ce qu'aucun autre reglage de cette
campagne n'avait obtenu :

1. la correlation de phase ;
2. le poids des fichiers a CRF constant — **-30 %**, donc autant de
   changement inter-image en moins, mesure par un encodeur qui ne partage
   aucune hypothese avec l'instrument ;
3. **l'utilisateur, a l'oeil** : « la video est beaucoup plus stable, je
   n'ai plus la sensation de scintillement et de saccade ».

### Ce que le correctif ne fait pas

La dispersion locale ne baisse que de 2,5 %. Le decoupage ajoutait une
derive **parasite** ; l'incoherence de fond mesuree en HOS-202 — 2,4 fois
celle d'une video geometriquement parfaite — reste celle du modele. Deux
defauts coexistaient, et les trois premiers tours les ont confondus.

### Pourquoi 64 et non 4096

Le decodage non tuile echoue vraiment ici : `CUDA out of memory`, 10,51
Gio demandes d'un bloc, re-mesure ce tour-ci. Le choix d'origine de tuiler
etait donc fonde — c'est sa taille qui etait mauvaise, pas son principe.

4096 donnerait une tuile unique a toute longueur, mais sa consommation sur
les plans longs n'est pas mesuree et un debordement y transformerait un
rendu mediocre en rendu absent. 64 est meilleur a toutes les longueurs
deja testees, sans ce risque. La mesure sur 121 images est en cours et
pourra faire monter cette valeur.

### Ce que cet incident apprend

L'hypothese correcte a ete formulee au premier tour, puis ecartee sur une
mesure inadaptee — et **jamais reprise** apres que cette mesure eut ete
reconnue fausse. Invalider un instrument ne suffit pas : il faut rejouer
ce qu'il avait servi a ecarter. Deux gardes-fous nomment desormais
l'incident dans `test_studio_gabarits.py`, verifies rouges sur le reglage
d'origine avant d'etre gardes.

### Ce qui a ete essaye sans effet, ce tour-ci

Le post-traitement : `deflicker` et `atadenoise` d'ffmpeg donnent -2 % au
mieux, sur les images deja rendues. La raison est instructive — ces
filtres corrigent des variations de **luminance**, alors que le defaut est
structurel. Aucun etalonnage ne l'aurait rattrape.

## HOS-203 - La quantification n'y est pour rien, la graine pese plus que tout (2026-08-28)

Fin de la campagne sur le scintillement. Deux hypotheses restaient : la
quantification, et la formulation de la consigne. Les deux sont closes, et
un troisieme facteur, jamais regarde, s'avere dominer tous les autres.

### La quantification n'est pas la cause

Trois quantifications telechargees et rendues sur le meme plan statique,
meme graine, meme tout. Mesure sur images brutes, la seule base comparable.

| modele | vitesse | dispersion | ecart |
|---|---|---|---|
| Q5_K_M — 16,82 Go | 0,108 | 0,746 | reference |
| Q6_K — 18,66 Go | 0,138 | 0,952 | non comparable (vitesse x1,28) |
| **Q8_0 — 23,63 Go** | 0,112 | **0,763** | **+2 %** |

Le Q8_0 porte 40 % de bits de plus que le Q5 et donne le meme resultat.

Deux mesures au passage, contre le principe que j'avais suppose : le pic
VRAM reel est **12,71 Gio** et non les 7,6 du tableau de ce document — ces
chiffres ne decrivent pas la configuration actuelle. Et la contrainte est
la **RAM systeme**, pas la carte : le processus monte a 20,6 Gio, il ne
reste que 3,4 Gio libres, et le Q6_K met plus de vingt minutes la ou le Q5
en prend cinq. C'est de la pagination, pas du calcul.

### Les formules de coherence dans la consigne ne font rien

Consigne de l'utilisateur rendue telle quelle, puis privee de ses seuls
termes de coherence (« continuous coherent motion, stable architecture,
consistent lighting throughout the shot »), meme graine.

| | vitesse | dispersion |
|---|---|---|
| avec les formules | 9,70 | 30,385 |
| sans les formules | 8,94 | 30,196 |

**0,6 % d'ecart.** Le modele ne traite pas ces instructions comme des
contraintes.

### Un resultat annonce puis retire

`res_multistep` avait donne -17 % sur la graine 777, a vitesse identique.
Annonce comme « le seul gain solide de la campagne ». **Il ne se reproduit
pas** : sur la graine 1234, les deux echantillonneurs donnent 0,396,
strictement. Le -17 % etait du bruit de graine. Aucun changement de code
n'en decoule — la confirmation avait ete exigee avant de toucher au
gabarit, et elle a servi.

### La graine domine tout

Meme consigne, memes reglages, seule la graine change.

| graine | vitesse | dispersion |
|---|---|---|
| 1234 | 0,107 | **0,396** |
| 42 | 0,099 | 0,474 |
| 777 | 0,108 | **0,746** |

A vitesse quasi identique, un facteur **1,88**. Mis en regard de tout ce
qui a ete mesure :

| levier | effet sur la dispersion |
|---|---|
| quantification Q5 -> Q8 | x1,02 |
| echantillonneur | x1,00 |
| formules de coherence | x1,01 |
| etapes 8 -> 24 | x1,26, en pire |
| **graine** | **x1,88** |

La graine pese plus que tous les reglages reunis. C'est la seule action
utile trouvee, et la moins chere : un plan qui scintille se relance avec
une autre graine. Le bouton de tirage ajoute en HOS-199 prend ici sa vraie
justification.

C'est aussi l'explication retrospective des faux positifs de cette
campagne : plusieurs reglages ont semble marcher puis n'ont pas tenu a la
reproduction. Ils mesuraient du bruit de graine. **Toute mesure future sur
la coherence temporelle doit porter sur plusieurs graines**, sans quoi
elle ne mesure rien.

### Etat des six hypotheses du rapport initial

| hypothese | verdict |
|---|---|
| instabilite intrinseque de LTX-2.5 | **confirmee** — 2,4 fois la dispersion d'une video parfaite |
| quantification Q5_K_M | **ecartee** — Q8_0 identique |
| nombre d'etapes | **ecartee** — au-dela de huit, c'est pire |
| VAE au decodage | mesure faite sur images brutes : le defaut y est deja |
| type de mouvement | **non tranchee** — l'instrument ne compare pas des vitesses si differentes |
| encodage final | **ecartee** — present dans les PNG bruts |

Aucun code n'a change. Le resultat de ce tour est une mesure, et il dit
que le defaut est dans le modele.

## HOS-202 - Le defaut mesure sans encodage, deux formats qui mentaient, et 390 Mo de trop (2026-08-28)

Suite du diagnostic, avec le compte rendu de l'utilisateur comme point de
depart : textures qui changent d'une image a l'autre, feuillage qui se
redispose, zones lumineuses qui scintillent, decor qui « respire » —
surtout sur les plans presque statiques.

### Deux limites de l'instrument, trouvees avant de publier des chiffres

**L'indicateur est sensible a l'encodeur.** Le meme rendu mesure 0,621 sur
ses images brutes et 0,902 sur son mp4, alors que ce mp4 et un `libx264`
CRF 23 partant des memes images ont une erreur d'encodage **identique**
(2,98 contre 2,97 niveaux, memes tailles de fichier). L'ecart ne vient
donc pas de la qualite d'encodage. Il reste **non explique**, et il
invalidait le plancher de reference de HOS-201, mesure sur un fichier
libx264 quand les rendus venaient de ComfyUI.

**Le rapport dispersion/vitesse depend de la geometrie du mouvement.** Sur
des temoins parfaits a vitesse croissante, le rapport *monte* (3,4 → 10,1
→ 12,4) au lieu de rester constant : les bords d'un zoom se deplacent plus
que le centre. Ce rapport ne mesure donc rien des que les vitesses
different.

### La mesure refaite, sans aucun encodage

`SaveImage` ajoute au meme graphe donne les images du decodeur avant tout
h264.

| source | vitesse | dispersion |
|---|---|---|
| temoin : image figee x49 | 0,000 | **0,000** |
| temoin : travelling parfait | 0,076 | 0,257 |
| LTX-2.5 : plan statique | 0,109 | **0,621** |

Le temoin fige rend exactement zero : l'instrument n'a pas de biais. A
mouvement comparable, le modele produit **2,4 fois** la dispersion d'une
video geometriquement parfaite, et son incoherence vaut pres de six fois
son propre mouvement. C'est ce rapport qui explique que le defaut saute
aux yeux sur un plan statique.

### Sept reglages, aucun ne corrige

Meme consigne, meme graine, meme encodeur — donc comparables entre eux.

- Etapes 8 / 16 / 24 : 0,552 / 0,567 / **0,695**. Au-dela de huit, c'est
  pire. La note « un modele distille ne gagne rien au-dela de huit » vaut
  donc aussi pour la coherence, et dans le mauvais sens.
- `res_multistep` : -12 % en absolu, mais avec moins de mouvement — non
  concluant. A noter : le depot documentait `res_multistep` alors que le
  code envoyait `euler`, ecart trouve en verifiant.
- `uni_pc`, CFG 2,0, STG a l'echelle 2,0 sur les blocs 14/19, 720p :
  aucun gain.

Le plan de parallaxe a trente-quatre fois plus de mouvement que le plan
statique : les deux ne sont pas comparables avec cet instrument.
L'hypothese « un mouvement franc masque le defaut » reste **plausible et
non tranchee**.

### Deux formats qui n'ont jamais existe

`ffprobe` sur les fichiers reels :

| declare | reellement produit |
|---|---|
| `paysage` 768 x 432 | **768 x 416** |
| `paysage_large` 1280 x 720 | **1280 x 704** |

LTX ramene la hauteur au multiple de 32 inferieur, en silence. Ces tailles
faussaient le calcul de cout et le garde-fou du depart sur image, lequel
refusait `paysage` pour une hauteur de 432 qui n'existait pas. Les formats
declarent desormais leur taille reelle, et les variantes « suite » de
HOS-200 disparaissent : `paysage_large_suite` valait 1280 x 704,
c'est-a-dire ce que `paysage_large` rendait deja.

### 390 Mo commites par erreur

Un `git add -A` pendant la campagne de HOS-201 a commite **881 images**
d'analyse — les frames extraites par les scripts de mesure — soit environ
390 Mo. Elles sont retirees du suivi et `.gitignore` couvre desormais ces
motifs.

Retirer ne suffit pas a alleger le depot : les objets restent dans
l'historique. Les en sortir demanderait une reecriture d'historique et un
`push --force`, operation destructive qui n'est pas engagee sans decision
explicite.

### Le mur materiel

Lightricks documente que le scintillement se concentre sur les zones a
haute frequence — cheveux, tissus, **feuillage** — ce qui fait du plan de
test de ce projet, une foret dans la brume, a peu pres le pire sujet
possible. La recommandation officielle est le modele **Dev** avec
echantillonnage multi-etages ; il fait 22 milliards de parametres, 21,5 Go
en int8, sur une carte de 16. L'agrandisseur de latent du pipeline
multi-etages (1 Go) est dans un depot **ferme**, qui exige une
authentification et l'acceptation d'une licence.

Backend 2192 passed, 2 skipped. Frontend tsc propre.

## HOS-201 - La « micro-coupure » : bon phenomene, mauvaise mesure (2026-08-28)

L'utilisateur a corrige sa description apres avoir regarde les fichiers,
et cette correction invalide le diagnostic de HOS-200. Il ne decrit pas un
defaut de RYTHME mais de CONTENU : « comme si la video etait creee en
ajoutant des petits morceaux de 0,5 s », avec « de legeres variations sur
la disposition des plantes » et l'impression que le plan recule.

### Pourquoi la mesure precedente ne pouvait pas le voir

L'ecart de luminance entre images successives mesure **l'ampleur** d'un
changement, jamais son **sens**. Il ne peut ni voir un retour en arriere
ni un objet qui se redispose. La periode 8 qu'il revelait est reelle, mais
elle decrit autre chose que ce qui gene a l'oeil.

Mesure appropriee : correlation de phase au sous-pixel, par region.

### Le temoin, sans lequel les chiffres ne veulent rien dire

Un travelling avant mathematiquement parfait, fabrique par `zoompan` a
partir d'une seule image reelle du meme plan — meme resolution, meme
cadence, meme codec. Il donne le plancher de bruit de l'instrument.

| variante | dispersion locale | exces reel |
|---|---|---|
| temoin, zoom parfait | 0,302 px | plancher |
| 8 etapes | 0,552 px | **+0,25** |
| 16 etapes | 0,567 px | +0,27 |
| 24 etapes | 0,695 px | +0,39 |
| 8 etapes + STG 1.0 | 0,561 px | +0,26 |

Le mouvement global est **monotone** : un seul contre-sens sur 48. La
camera ne recule jamais. Mais l'incoherence locale vaut 0,25 px par image
contre 0,172 px de deplacement reel de la camera — le desordre domine le
mouvement d'un facteur 1,5. C'est ce rapport qui explique l'impression de
recul et la redisposition des plantes.

Deux conclusions de HOS-200 tombent : ce n'est **ni** le decoupage
temporel du decodeur, **ni** les huit images par latent. Aucune
periodicite ne ressort au-dessus du seuil de bruit.

### Trois leviers essayes, aucun ne corrige

Les etapes ne sont pas le levier, et au-dela de huit elles **nuisent** :
0,552 -> 0,567 -> 0,695. La note « un modele distille ne gagne rien
au-dela de huit etapes » valait pour la qualite d'image ; elle vaut aussi
pour la coherence, et dans le mauvais sens.

`LTXVSpatioTemporalGuidance` a l'echelle 1.0 ne change rien. Des echelles
plus fortes restent a mesurer.

L'interpolation ne s'y attaque pas : elle lisse la restitution, pas la
generation.

Restent non mesures et non ecartes : resolution plus haute, echelle de STG
plus forte, quantification superieure.

Aucun code n'a change : ce tour est une mesure, et son resultat est qu'il
n'y a rien a corriger dans ce depot — le defaut est dans le modele.

## HOS-200 - Les saccades mesurees, et l'enchainement de plans (2026-08-28)

Trois questions posees sur le Studio, dont une - « les saccades viennent
du modele ou d'un reglage ? » - qui ne se tranche que par la mesure.

### La saccade vient du modele, et l'hypothese de depart etait fausse

Ce que ce n'est pas : le conteneur est sain (24/1 constant, h264, nombre
d'images conforme), verifie par ffprobe sur un fichier reellement produit.

Mesure de l'ecart de luminance entre images successives, sur trois plans -
deux formats, trois contenus. L'autocorrelation culmine a **8** dans les
trois cas (+0,52 / +0,30 / +0,30), toujours le decalage le plus eleve,
alors que r(12) change de signe et ne decrit rien. Seuil de bruit ≈0,14
pour n≈50 : les valeurs sont 2 a 4 fois au-dessus. Dans chaque groupe de
huit images le mouvement est fort au debut et faible a la fin - trois
a-coups par seconde a 24 im/s.

Ce 8 est le taux de compression temporelle du VAE de LTX. Deux faits
independants le corroborent : la contrainte `8k + 1` sur le nombre
d'images, et le « Must be 8*n + 1 frames » de la documentation du noeud
`LTXVAddGuide`. Trois indices, une cause.

**L'hypothese de depart etait le decoupage temporel du decodeur**
(`temporal_size` 16, recouvrement 4, donc un pas de 12). La mesure l'a
infirmee : c'est precisement a 12 que le signal est le plus anti-correle.
Elle a ete ecartee au lieu d'etre corrigee apres coup.

### Le lissage : integre au rendu, et honnete sur ce qu'il ne fait pas

Trois modeles installes depuis `Comfy-Org/frame_interpolation`, le depot
que le gabarit officiel livre avec ComfyUI designe. Banc de comparaison
sans diffusion (la video deja rendue est rechargee), donc 6 a 26 s par
essai au lieu de minutes.

| modele | variation du pas | secousse image-a-image |
|---|---|---|
| rife_v4.26 | +26 % / +18 % | +55 % / +29 % |
| rife_v4.26_heavy | +32 % / +15 % | +58 % / +18 % |
| film_net_fp16 | +14 % / +8 % | **-18 % / -14 %** |

**Aucun ne supprime l'irregularite de fond** - attendu, puisque
l'interpolation ne peut pas inventer ce qui s'est passe entre deux groupes
de huit. FILM est le seul a reduire la secousse image-a-image ; RIFE
l'aggrave. FILM est donc le choix propose, et l'ecran ecrit ce que le
lissage ne fait pas plutot que de le laisser croire.

L'interpolation est faite **pendant** le rendu, pas en seconde passe, et
la cadence de sortie est multipliee d'autant pour que la duree ne bouge
pas - sans ce doublement, le plan deviendrait un ralenti.

### Enchainer deux plans en gardant decor et personnages

`LTXVImgToVideo` fait partir un plan d'une image au lieu du bruit ; donner
au suivant la derniere image du precedent conserve la scene.
`POST /studio/last-frame` extrait cette image dans le dossier d'entree de
ComfyUI, seule adresse que `LoadImage` sait lire.

Une contrainte que rien n'annoncait : ce noeud decoupe le latent en blocs
de 2x2 et exige des cotes **multiples de 32**. Ni 432 ni 720 ne le sont.
Constate en le lancant : le plan est accepte, occupe la carte, et echoue
**sept minutes plus tard** sur un `einops.EinopsError` illisible. Un
garde-fou refuse desormais en une milliseconde, en nommant les formats
compatibles. Deux formats compatibles ont ete ajoutes - `paysage_suite`
(768 x 448) et `paysage_large_suite` (1280 x 704, exactement le compte de
pixels du portrait deja chronometre).

Un test empeche un defaut trouve en ecrivant le code : avec le son,
`LTXVConcatAVLatent` etait cable en dur sur le latent vide. Le plan
repartait donc du bruit des qu'on demandait le son, en perdant sa
continuite, sans aucune erreur.

### La graine, et un piege corrige

La valeur par defaut etait `0` - une graine fixe, pas un tirage. Deux
lancements sans y toucher rendaient exactement le meme fichier. Un bouton
de tirage a ete ajoute, et l'aide corrigee : elle disait « 0 pour laisser
courir », ce qui etait faux.

### Verifications

Les deux nouveautes sont validees par des **rendus reels**, pas par
construction de graphe : un plan I2V + lissage en 512 x 320 rend 49 images
a 48 im/s pour 1,02 s - exactement le calcul. Le premier essai, lui, a
echoue, et c'est ce qui a fait trouver la contrainte des multiples de 32 :
`success: true` de la soumission ne valait que « accepte ».

## HOS-199 - La duree d'un plan, et trois reglages deja ecrits mais jamais offerts (2026-08-28)

« Je ne peux pas choisir la duree de la video. » C'etait vrai en pratique
et faux en theorie : le formulaire offrait un champ **Images**, qui *est*
la duree du plan, sans que rien ne le dise. Personne ne cherche « 97 »
quand il veut quatre secondes.

Le champ est desormais une duree en secondes. La conversion vit dans
`gabarits.py` avec les autres mesures, parce que LTX n'accepte que des
longueurs `8k + 1` — 49 images pour 2 s, 97 pour 4 s, les deux longueurs
effectivement rendues et chronometrees. A 24 im/s la coincidence est
exacte : 24 etant multiple de 8, toute duree entiere tombe pile sur une
longueur valide. L'ecran affiche la duree **reellement rendue** (2,04 s
pour 2 s demandees, l'image supplementaire de `8k+1`) plutot que d'arrondir
en silence.

### Trois parametres implementes depuis HOS-194, jamais offerts

Un releve de la signature des gabarits contre ce que le catalogue annonce
en a trouve trois : `negatif` (le prompt negatif), `prefixe` (le nom du
fichier de sortie) et `cadence`. Tous trois codes, testes, et invisibles
dans l'ecran — donc inaccessibles autrement qu'en passant par l'agent. Ils
sont maintenant dans le formulaire, pour les trois gabarits concernes.

Un test garde le catalogue et les fabriques d'accord : tout parametre
annonce a l'ecran doit etre accepte par `composer`. Verifie rouge sur un
parametre fantome avant d'etre garde.

### Une estimation fausse de +260 %, trouvee en la rendant visible

L'ecran annoncait « ≈ 5 min de calcul par seconde de video finie ». Cette
regle vient du **seul rendu vertical** dont elle est tiree et ne retient
que la duree, en ignorant la surface. Confrontee aux deux autres rendus du
tableau de `docs/studio-center.md`, elle surestime de **+144 %** en
768 × 432 (612 s annoncees pour 251 mesurees) et de **+260 %** en 512 × 288
(612 s pour 170).

L'erreur allait dans le sens le plus couteux a l'usage : elle decourageait
un essai bon marche en l'annoncant a vingt minutes. Le temps suit
`pixels x images`, pas la duree seule. Ajustement par moindres carres sur
les trois rendus reels, ecart maximal 11 % :

```
t ≈ 56 s + 13,27 s par million de pixels-images
```

Constantes dans `gabarits.py`, servies par `/studio/templates` plutot que
recopiees dans le frontend. L'ecran dit desormais « extrapole de trois
rendus mesures, a ±11 % » : trois points ne font pas une loi.

Verifie a l'ecran : 4 s en 704 × 1280 annonce 20 min, mesure 20,3 ; 2 s en
768 × 432 annonce 5 min, mesure 4,2 — contre 10 min annoncees avant.

`docs/studio-center.md` est **amende explicitement** a l'endroit ou la
regle etait etablie, sans reecrire la mesure d'origine : « cinq minutes par
seconde » reste juste pour le vertical, et c'est a ce titre que
`file_de_nuit.py` continue de s'en servir pour justifier l'atelier de nuit.

## HOS-198 - La bascule d'onglet, corrigee pour de bon (2026-08-27)

Le bug du Studio Center persistait apres HOS-196 : depuis un sous-onglet
(Voix, Nuit ou Graphe), changer d'onglet principal ne changeait rien a
l'ecran. Reproduit sur l'application en marche plutot que raisonne.

### Ce que HOS-196 avait rate, et pourquoi

Le correctif precedent retirait `exit` du conteneur de vue, en pariant que
sans variante de sortie a jouer, `AnimatePresence` demonterait l'ancienne
vue immediatement. **Il ne le fait pas** — framer-motion 11.18.2 sous
React 19 ne relache alors jamais l'enfant sortant. Mesure dans le DOM :
chaque navigation ajoutait un `.center-enter` de plus, tous a opacite 1,
aucun retire. Studio, puis Assistant, puis Mission Center, empiles dans le
flux. Le premier gardait le haut de la page et les suivants etaient
pousses 1 140 px plus bas, hors ecran — d'ou « ca ne fonctionne pas »,
alors que `activeView` et `aria-current` changeaient correctement. Le
correctif de HOS-196 avait donc remplace un blocage par une fuite.

### La correction

`AnimatePresence` n'avait plus de travail : la sortie est retiree pour de
bonnes raisons (une iframe ignore le fondu de ses ancetres et resterait
visible par-dessus la vue suivante), et l'entree est une animation CSS que
le remontage declenche seul. Ne restait que sa comptabilite de presence,
laquelle fuyait. Un `key` sur un element ordinaire suffit : React demonte
de facon deterministe, sans dependre d'une frame de composition, et
l'iframe s'en va avec la vue.

Verifie dans un vrai navigateur, cette fois avec un pane qui affiche :
32 combinaisons (quatre sous-onglets du Studio x huit onglets principaux),
zero echec, toujours exactement un Center en DOM. Le cas dur — quitter
Studio -> Graphe avec l'iframe ComfyUI vivante — passe de 1 iframe a 0.
Rafale de 19 onglets sans pause : maximum 1 Center a tout instant.

### Un test qui ne gardait rien, retire avant d'etre commite

Le premier garde-fou ecrit pour cet incident montait le shell et comptait
les Centers apres bascule. Verifie comme doit l'etre tout garde-fou — la
faute reintroduite exprès — il est reste **vert**. Sous JSDOM il n'y a pas
de vraies frames de composition, framer-motion y relache l'enfant sortant
immediatement, et le defaut ne peut pas s'y produire. Le garder aurait ete
pire que rien : il aurait affirme garder une regression qu'il laisse
passer.

Ce qui reste est ce qui *peut* se garder automatiquement — que la
construction fautive n'a pas ete remise — et il a ete verifie rouge sur la
faute reintroduite avant d'etre garde. Meme nature que
`test_hermes_agent_is_the_brain.py` : il ne prouve pas que la navigation
marche, il empeche le retour de la cause connue.

## HOS-197 - Ce que la maquette avait retenu, et que le code n'avait pas pris (2026-08-27)

L'utilisateur signale que le design cree en amont n'a pas ete mis en place,
« seul l'operateur ». Verifie avant d'agir, et le constat est l'inverse :
l'harmonisation sodium est complete (globals.css porte la palette, les 22
Centers en heritent par les alias), la piece ambiante existe (halo sodium,
contre-lumiere glacier, grille technique, grain, vignette), et l'operateur
va bien au-dela de la maquette — quinze postures pilotees par de vrais
evenements backend contre treize illustratives. L'ecart reel etait ailleurs,
et il tenait en quatre points.

### Le halo suit le curseur

La piece etait la, mais figee. La direction retenue
(`.design/cockpit/Main.dc.html`) en fait une source de lumiere mobile : le
halo sodium suit la souris, la contre-lumiere glacier se reflete en miroir a
travers le centre, et la grille ne se revele que la ou la lumiere tombe.
`components/room-halo.tsx` ecrit `--room-mx`/`--room-my` sur la racine — la
meme technique que `rail.tsx` pour `--rail-w`, et pour la meme raison :
plusieurs regles CSS doivent suivre une valeur sans qu'aucune ne devienne la
source de verite d'une autre. Ecriture directe de la variable, une fois par
frame au plus, plutot qu'un `setState` par mouvement de souris. Les deux
variables ont des valeurs de repli reelles dans le CSS, donc la piece se lit
correctement avant que le moindre JS ait tourne.

### Le badge d'etat dans la barre d'instruments

« Une couleur, un etat, partout ou il est lisible ». La figure de l'operateur
ne parait que sur douze Centers sur vingt-sept — elle demande de la place et
serait du bruit sur un ecran de reference. Le badge, lui, tient dans la barre
et parait partout : c'est justement sur ces ecrans-la qu'on veut encore
savoir, d'un coup d'oeil, qu'une mission travaille pendant qu'on regarde
ailleurs.

### La sante se retire au bord — Direction C, mesuree avant d'etre adoptee

Direction C affirmait que l'echelle vert/ambre/rouge remplissait les valeurs
et que, tout allant bien presque toujours, l'ecran etait vert. Verifie sur
l'application en marche plutot que sur le compte de jetons du depot :
**quarante et un elements verts contre treize sodium** sur le Dashboard,
alors que le sodium est l'accent cense porter « le systeme qui parle ».

La cause n'etait pas diffuse : `ProgressBar`, primitive partagee, remplissait
ses vingt-quatre segments de la couleur de sante. Desormais le corps de la
barre est sodium et seul le segment de tete porte la teinte de sante, halo
compris. Mesure apres : 41 -> 29 elements verts, et une barre a 49 % se lit
« onze segments sodium, un vert en tete ».

Une exception, et elle compte : le recensement des 35 sous-systemes du
Dashboard garde ses cellules colorees par la sante, parce que la sante **est**
la valeur qu'il montre — une cellule rouge dans une rangee verte est tout son
propos. Direction C vise les mesures dont le chiffre est la valeur, pas les
recensements de sante. La distinction est ecrite dans le contrat du systeme
de design plutot que laissee a la relecture suivante.

### Le bouton se remplit par la gauche, et s'enfonce sans retrecir

La planche de pieces (`.design/cockpit/Composants.dc.html`) est explicite :
« un bouton d'instrument s'enfonce, il ne retrecit pas ». Le bouton faisait
`active:scale-[0.985]` — exactement ce qu'elle recuse. Retire. Et le
remplissage entre par la gauche, dans le sens de lecture, au lieu de monter
en opacite partout a la fois (`.btn-fill` dans globals.css, une seule
mecanique pour les quatre variantes).

Verifie : tsc --noEmit propre, vitest 110/110, et le CSS mesure sur
l'application en marche (le halo suit bien, la contre-lumiere se reflete a
30%/80% quand le curseur est a 70%/20%, le masque de grille suit, le badge
porte la teinte de l'etat a 34 % de bordure et 8 % de fond, `--btn-fill` vaut
sodium avec un `::before` a `scaleX(0)`). Comme au tour precedent, aucune
capture d'ecran : le pane de test ne composite pas les frames.

## HOS-196 - Trois pannes d'interface qui n'en faisaient qu'une, et la voix Michael sur ecran (2026-08-27)

Trois bugs remontes par l'utilisateur sur l'interface : impossible de
scroller dans la plupart des Centers, la navigation qui se bloque un clic
en retard, ComfyUI (onglet Studio -> Graphe) qui reste affiche par-dessus
l'onglet suivant quand on change d'onglet. Racine commune dans
`cockpit-shell.tsx` : le conteneur de vue bornait sa hauteur
(`h-full overflow-hidden`) et `AnimatePresence` attendait la fin d'une
animation de sortie (`mode="wait"`) qui ne garantit jamais sa propre fin.

- **Scroll.** Dix-sept Centers sur vingt-sept n'ont pas de defilement
  interne et dependent entierement du debordement vers le conteneur
  parent. Mesure sur Governance a 500px de fenetre : une boite de 370px
  pour 415px de contenu reel, les 45px manquants recuperables nulle part.
  `h-full overflow-hidden` remplace par `min-h-full` pour tout Center hors
  Assistant, qui garde son comportement borne (seul Center a gerer son
  propre defilement interne).

- **Navigation bloquee.** `mode="wait"` bloque le montage de la vue
  suivante tant que la sortie de la precedente n'est pas confirmee
  terminee — une confirmation qui depend d'une frame de composition
  pouvant manquer (onglet en arriere-plan, GPU charge par un rendu
  parallele). Constate : `aria-current` changeait, `<main>` restait fige
  sur l'ancienne vue, chaque clic suivant s'empilait sans jamais aboutir.
  Retire.

- **Iframe persistante.** Les iframes ignorent le fondu CSS de leur
  conteneur et restent composees a pleine visibilite pendant la sortie —
  constate sur Studio -> Graphe, deux `.center-enter` en DOM
  simultanement (l'ancien Studio avec ComfyUI vivant, et la vue cible).
  `exit` retire du `motion.div` : sans variante de sortie a jouer,
  `AnimatePresence` demonte l'ancienne vue immediatement au lieu
  d'attendre une animation qui peut ne jamais se resoudre. Meme correctif
  applique a `web-preview.tsx`, seul autre site avec iframe (panneau
  plein ecran, ou le risque etait pire — bloquer l'application entiere).

Verifie : `tsc --noEmit` propre, vitest 110/110, balayage des 19 Centers
sans desynchronisation ni nouvelle erreur console. Aucune confirmation
visuelle par capture d'ecran n'a ete possible pendant cette revue : le
pane de navigateur de la session ne compositait pas les frames, confirme
par un timeout de 30s sur un `requestAnimationFrame` direct — verification
faite entierement par inspection DOM/etat.

### La voix Michael (HOS-195), sur ecran plutot que par le chat seul

`studio_narrate` n'existait que comme outil MCP — narrer une replique
exigeait de le decrire a l'agent en conversation. Nouvel onglet « Voix »
dans le Studio Center (`narration.tsx`), une route REST miroir de l'outil
(`POST /studio/narrate`, `backend/studio/routes.py`) qui appelle la meme
`narration.synthetiser` avec le meme arbitrage de carte — pas une seconde
implementation. Un test de route a trouve un vrai defaut avant qu'il ne
morde : une replique composee uniquement d'espaces passait le controle de
vacuite (`t` au lieu de `t.strip()`) et aurait lance une synthese sur du
texte blanc.

## HOS-195 - La voix Michael, branchee dans le pipeline (2026-08-27)

Chatterbox, clone depuis un echantillon fourni par l'utilisateur — sa
propre voix, en performance de personnage nomme « Michael », confirme
explicitement avant tout clonage. Trois references soumises et mesurees
avant de retenir la troisieme : la premiere (44,6 s, -30,7 dB) donnait un
clone a quatre trames voisees sur toute la phrase, la voix survivait a
peine. Reduite a seize secondes de parole continue et debruitee
**doucement** — le reglage fort gagnait 21 dB de silence mais faisait
chuter la confiance de transcription de -0.188 a -0.351, la voix decrochait
avec le bruit — le clone est monte a 126 trames. La troisieme etait deja
propre et n'a demande qu'une normalisation.

Verifie, pas suppose : la hauteur mediane du clone se deplace
systematiquement vers celle de la reference, de 157 Hz (voix par defaut du
modele) a 82-102 Hz selon les reglages, contre 91,2 Hz mesures sur
« Michael ».

### Un environnement separe, pour la meme raison que Hermes Agent

`chatterbox-tts` epingle `torch==2.6.0`. L'installer dans `.venv` ou dans
l'interprete embarque de ComfyUI aurait remplace le torch ROCm 2.13 par
une build CPU et casse tous les rendus. Une venv enfant herite du torch
de ComfyUI par un `.pth`, Chatterbox y est installe `--no-deps`. Verifie
apres coup : ComfyUI repond, en ROCm, GPU actif — l'isolation a tenu, deux
fois (a l'installation, puis a chaque appel reel depuis).

### Le pipeline

`backend/studio/narration.py` : un seul chargement pour plusieurs
repliques (9 a 27 s mesures par chargement, une narration en compte
plusieurs), et la carte s'arbitre comme pour un rendu — 4,38 Gio de pic
mesures, pas gratuit comme Piper. `_chatterbox_worker.py` est le seul
fichier qui tourne dans l'environnement Chatterbox ; il ne decide de
rien, tout arrive en parametre.

`studio_narrate` (MCP) rejoint la liste blanche de l'agent et son cache de
schemas a ete vide — les deux verrous silencieux qu'HOS-192 avait deja
trouves pour la delegation, retrouves une deuxieme fois sur un nouvel
outil.

### Un defaut latent corrige avant qu'il morde

Le sous-processus decodait stderr en UTF-8 strict. Un avertissement
HuggingFace accentue, imprime dans l'encodage systeme Windows, a fait
planter un thread interne pendant la verification reelle — sans faire
echouer l'appel cette fois, mais rien ne garantissait la prochaine.
Corrige avec `errors="replace"`, la meme convention deja posee pour
Hermes Agent dans ce depot pour la meme cause.

### Un redemarrage systeme, pas un bug

Pendant la verification reelle, ComfyUI, le backend et le Cockpit sont
tombes d'un coup. Diagnostic avant conclusion : `LastBootUpTime` et
l'evenement Windows 1074 confirment un **redemarrage systeme** a 21:05:30
— une mise a jour planifiee, sans rapport avec la synthese. Les trois
services relances, ComfyUI verifie sur ses bons drapeaux
(`--use-quad-cross-attention`, pas de CORS desarme).

### Verified

Synthese reelle de bout en bout : deux repliques, fichiers WAV sur disque,
16,2 s de chargement, 5,08-5,44 s de synthese chacune. Backend **2 161
passes, 2 ignores** (11 tests nouveaux pour la narration). Aucun binaire
audio n'entre dans le depot — la reference vit sous
`C:\AI\Models\Voices\michael\`, hors de git.

---

## HOS-194 - L'Atelier produit, et ComfyUI s'encastre sans rien desarmer (2026-08-27)

Trois manques constates en regardant l'ecran plutot qu'en le decrivant :
l'onglet Atelier ne lancait rien, SDXL n'y apparaissait pas, et l'iframe
de ComfyUI etait blanche.

### Un formulaire, et la frontiere qu'il ne franchit pas

`backend/studio/gabarits.py` compose trois graphes figes — plan video,
image SDXL, image LTX — a partir de parametres **explicites**. Rien n'est
infere de la consigne.

La regle qui prime sur tout interdit qu'une seconde boucle decide a la
place de l'agent, et j'avais ecrit qu'« un service qui construit le bon
workflow » serait exactement cela. La distinction tient en un mot :
**choisir**. Decider quel pipeline convient a un objectif, c'est
raisonner ; remplir un gabarit avec des parametres qu'on vous donne, c'est
un formulaire. C'est d'ailleurs ce que le cahier des charges prevoyait :
« le graphe vient de l'appelant [...] ou du Studio Center par un gabarit ».

`test_studio_gabarits.py` garde cette frontiere : le jour ou quelqu'un
ajoutera « si la consigne parle de mouvement, mettre plus d'images »,
c'est la que ca cassera.

### Le defaut qu'il a fallu regarder pour trouver

Le premier rendu lance depuis le formulaire est sorti **tuile et
deforme**. Le graphe etait correct, ComfyUI a rendu 200, le fichier
existait. Rien ne signalait quoi que ce soit — il fallait ouvrir l'image.

La cause : une liste de formats **commune aux deux moteurs**. Le rendu
SDXL est parti en 768x432, valide pour LTX et ruineux pour SDXL, qui est
entraine autour du megapixel. Les formats sont desormais separes, le
formulaire retombe sur un format valide quand on change de moteur, et deux
tests gardent la separation.

### L'iframe : un 403 selectif

`origin_only_middleware` (server.py:159) compare `Host` et `Origin` et
renvoie 403 quand ils different — protection contre un site tiers qui
ferait executer un workflow depuis le navigateur de l'utilisateur.

Le 403 etait **selectif**, ce qui l'a rendu long a voir : les feuilles de
style passaient, le navigateur n'envoyant pas d'`Origin` pour elles ; les
scripts `type="module"`, requetes CORS, echouaient. La page se chargeait,
affichait son ecran de demarrage, et n'en sortait jamais.

Ma premiere explication — « ComfyUI ne pose ni X-Frame-Options ni
frame-ancestors, donc l'encastrement fonctionne » — etait une verification
d'en-tetes prise pour un chargement de page. Exacte, et sans rapport.

**Ecarte : `--enable-cors-header`.** Une ligne, mais il **remplace** le
garde au lieu de le restreindre : verifie, une origine quelconque obtenait
alors 200. Desarmer la protection pour tout le monde afin d'en autoriser
une seule.

**Retenu : un proxy same-origin.** `next.config.ts` reecrit `/comfy/*`
cote serveur, `src/middleware.ts` retire `Origin` et `Sec-Fetch-Site`
avant de transmettre. La requete arrive comme un `curl`, sans rien a
comparer — cas que le garde laisse passer par construction. Rien n'est
desactive.

Trois details decidaient : `skipTrailingSlashRedirect`, sans quoi Next
redirige `/comfy/` et les chemins relatifs se resolvent contre `/` ; les
WebSockets, verifiees a **101 Switching Protocols** a travers la
reecriture, sans quoi l'interface se chargerait sans jamais afficher de
progression ; et un middleware limite a `/comfy/*`, l'`Origin` du Cockpit
lui-meme etant legitime.

### Rangement

`ckpt_name` manquait dans `/studio/models` : SDXL, installe et mesure la
veille, n'apparaissait nulle part. Et le mapping `checkpoints: vae/` de
HOS-192 faisait passer les deux VAE de LTX pour des checkpoints — le VAE
audio a desormais son propre dossier.

`hermes-ltx-cockpit.bat`, ecrit pour tester la piste CORS, est supprime :
le proxy le rend inutile et il desarmait un garde.

### Verified

Rendu lance **depuis le bouton** de l'ecran : soumis, carte reservee,
`image_00002_.png` sur disque, image nette et conforme a la consigne.
ComfyUI dans le cadre : 360 noeuds, 2 canvas, plus d'ecran de demarrage —
avec son garde intact.

Backend 2 150 passes, frontend 110 passes, tsc propre.

---

## HOS-193 - split mesure, et une mesure qui ne colle pas (2026-08-27)

`split` avait ete ecarte par un calcul qui additionnait le poids du
fichier a la memoire d'attention, comme si les poids residaient sur la
carte. Ils n'y resident pas. Le calcul refait donnait « ca tiendrait » —
une estimation, remplacee ici par une mesure.

Meme graphe, meme graine, 768x432 sur 49 images, les deux serveurs
demarres a froid :

    sub_quad   248 s   pic 14,42 Gio
    split      239 s   pic 14,42 Gio

**Neuf secondes, 3,6 %.** Pas les 40 % annonces.

L'ecart entre 40 % et 3,6 % est le resultat le plus instructif : les 40 %
venaient d'un banc qui chronometrait **l'attention seule**. Dans un rendu
reel elle est une petite part du travail — le reste, ce sont trente-six
gigaoctets de modele relus depuis le disque, le decodage du VAE, le
planificateur. Un micro-banc ne predit pas un pipeline.

### Aucune degradation, et c'est verifie

Les deux implementations calculent la meme attention et ne different que
par le decoupage. `sub_quad` implemente Rabe & Staats, un softmax decoupe
**exact** ; les deux chemins montent en float32 sous la meme condition —
lu dans le code, pas suppose. Restait l'associativite des flottants, qui
aurait pu deriver sur huit pas de debruitage.

    instant    ecart max   ecart moyen   PSNR        pixels touches
    15 %       0           0,000         identique   0,00 %
    50 %       0           0,000         identique   0,00 %
    85 %       0           0,000         identique   0,00 %

Les fichiers different de **deux octets** — un horodatage de conteneur —
et pas d'un pixel. Verifie sur deux paires independantes.

### Garde sub_quad quand meme

Le gain est de 3,6 %, et `split` prend bien plus de memoire d'attention
quand les jetons se multiplient. Le format 704x1280 sur 97 images — celui
des shorts — n'a pas ete teste avec lui, et c'est precisement la qu'il
pourrait deborder. `hermes-ltx-split.bat` garde la variante a cote.

### Une mesure incoherente, laissee ouverte

Ces rendus pesent 14,42 Gio au pic. Les trois plans de la nuit du **meme
jour**, meme resolution, meme modele, meme nombre d'images, avaient donne
7,61 Gio — trois fois exactement le meme chiffre.

Un rapport de deux entre deux mesures reproductibles de la meme chose.

J'ai verifie que ce n'est pas un pic manque : releve a la seconde, la
valeur haute est un plateau qui dure des minutes. Les conditions different
— la nuit passait par `carte_reservee`, qui venait de decharger Ollama —
mais je ne connais pas le mecanisme. L'hypothese la plus plausible est que
`Dedicated Usage` compte ce que l'allocateur PyTorch *reserve* et pas
seulement ce qu'il *utilise*, et qu'il en reserve d'autant plus que la
carte est libre. Non verifie, donc ecrit comme tel.

Consequence : `BESOIN_RENDU_OCTETS` vaut 9 Gio, cale sur la plus **basse**
des deux. Si c'est la haute qui decrit le besoin, la reservation est trop
courte — a trancher avant de faire tourner une nuit pendant qu'une mission
travaille.

### Verified

Quatre rendus sur disque sous `E:\YouTube\Generations\attention`,
comparaison pixel par numpy sur trois instants. Lanceur de production
restaure sur `--use-quad-cross-attention` et verifie par `/system_stats`.

---

## HOS-192 - Ce qui etait deja la, et que personne ne voyait (2026-08-27)

Trois taches, et le meme motif dans les trois : ce qu'il fallait etait
deja sur le disque, rendu invisible par une ligne de configuration.

### La delegation ne marchait pas pour une raison qui n'etait pas dans ce depot

Le but declare du projet YouTube etait que Hermes Agent conduise la
generation. Neuf outils MCP etaient enregistres et testes. L'agent n'en
voyait aucun.

`mcp_servers.hermes-ollama.tools.include` est une liste **blanche** de
seize noms. Enregistrer un outil cote serveur ne le donne pas a l'agent :
il faut l'y nommer. Et `cache/mcp_schema_cache.json` gardait les seize
anciens, ce qui aurait annule la correction sans un vidage.

Deux listes blanches silencieuses. C'est la troisieme fois dans ce projet
— l'EventHub avait avale trente-cinq topics de la meme facon.

Une fois levees : douze appels d'outils en 54 s, et la phrase qui compte,

    « none are in a successful "kept" state — they are all in the
      "indetermine" state »

La distinction entre « le fichier existe » et « le fichier est bon » a
survecu jusqu'a une reponse en langage naturel. C'etait le seul test.

### Les images fixes ne demandaient aucun telechargement

Avant de prendre douze gigaoctets de SDXL : LTX-2.5 avec `length: 1` rend
une image. Il le fait — 169 s et 6,86 Gio en 768x432.

Mais 1024x1024 est tombe en CUDA OOM a 14,57 Gio de pic, sur `VAEDecode`.

Le message le disait, et mon propre code le cachait : `Rendu.erreur`
serialisait le tableau `messages` entier et coupait a 600 caracteres — or
il commence par `execution_start` et `execution_cached`, si bien que la
coupe tombait avant `exception_message`. On lisait un horodatage la ou
ComfyUI ecrivait « CUDA out of memory ... VAEDecode ».

**Amendement, meme jour.** J'ai d'abord conclu qu'il fallait tuiler le
decodage, comme pour la video, et je l'ai ecrit avant de le verifier. La
mesure ne le confirme pas : avec `VAEDecodeTiled`, le 1024x1024 tournait
encore apres 455 s sans aboutir, epingle a 14,65 Gio. Le pic est le meme
quel que soit le mode de decodage — la pression est donc ailleurs, et
`VAEDecode` tombait parce qu'il demandait 2,67 Gio **de plus** sur une
carte deja pleine.

Je n'ai pas isole la cause, et j'ai interrompu le 1280x720 tuile a 150 s,
soit avant les 220 s du non tuile : il n'est donc pas etabli que le
tuilage soit plus lent ici. Conclusion etroite et honnete : au-dela de
~0,9 megapixel, LTX est a la limite de cette carte pour une image fixe.

### Un modele d'image, finalement

SDXL 1.0 base installe (6,94 Go + 335 Mo de VAE corrige, 86 Mo/s en six
tranches paralleles). Meme consigne, meme graine :

    LTX   1280x720    220 s   14,58 Gio   objet mou, lumiere respectee
    SDXL  1024x1024    45 s   13,46 Gio   objet net, lumiere ignoree
    SDXL  1344x768     35 s   13,23 Gio

Cinq fois plus rapide, a une resolution que LTX n'atteignait pas. Mais le
resultat le plus utile n'est pas « SDXL gagne » : les deux sont
complementaires. SDXL rend l'objet net et les graduations lisibles, et
aplatit la lumiere ; LTX est mou sur l'objet — un sextant demande, des
compas rendus — et respecte la lumiere laterale demandee.

SDXL pour une vignette dont le sujet doit se reconnaitre, LTX pour un plan
d'ambiance ou une image qui doit se raccorder a de la video.

Licence CreativeML Open RAIL++-M, usage commercial permis. Flux.1-dev
ecarte (non commercial) ; Flux.1-schnell est Apache 2.0 mais demande en
plus un encodeur T5 de cinq a dix gigaoctets sur une carte deja partagee.

### L'audio natif etait sur le disque depuis le debut

`ltx-2.5-audio-vae-bf16.safetensors` n'etait reference nulle part parce
que `LTXVAudioVAELoader` lit dans `checkpoints` et non dans `vae`. Une
ligne de `extra_model_paths.yaml`.

Deux verifications avant d'allumer le GPU : le VAE porte les prefixes
`audio_vae.` et `vocoder.` attendus, et le GGUF distille declare
`AVTransformer3DModel` avec `use_audio_video_cross_attention: true`.

    rendu        339 s pour 2,04 s  (+21 % sur la video seule)
    pic VRAM     11,07 Gio          (7,75 en video seule)
    piste        AAC 48 kHz stereo, 2,01 s
    niveau       moyenne -7,9 dB, crete 0,0 dB

Le niveau a ete **releve**, pas deduit de la presence d'une piste : un MP4
porte volontiers un canal silencieux et se termine avec le code 0. La
crete a 0,0 dB dit au passage que le signal sature.

Ce que ni Piper ni Kokoro ne peuvent poser apres coup : des pas qui
tombent sur l'image, une porte au bon quart de seconde.

### Une raison fausse propagee en quatre endroits

`BESOIN_DEFAUT` valait 11,5 Gio — le **poids du fichier** Q3_K_M — en
supposant que les poids resident sur la carte. Ils n'y resident pas :
`--cache-none` les fait diffuser depuis la RAM, et trois quantifications
de 10,7 a 17,4 Go avaient donne le meme pic a deux centiemes pres.

Reserver 11,5 quand il en faut 7,8 n'est pas prudent : c'est faux dans
l'autre sens, et la file aurait refuse des rendus qui tenaient. Le faux
echec, que ce depot traque autant que le faux succes.

La constante existait en **quatre exemplaires** — routes, file de nuit,
atelier, outil MCP. Une seule definition desormais, dans `arbitrage`.

La meme erreur justifiait le choix de l'attention dans `hermes-ltx.bat` :
« 10,73 + 8,25 depasse 15,98 ». Avec le pic reel, `split` — 40 % plus
rapide que `sub_quad` — tiendrait. Note dans le lanceur, non applique :
une hypothese n'est pas une mesure, et c'est exactement ce que cette
correction dit.

### Nettoyage

    LTX-2.5-gemma4-12b-text-encoder-Q4_K_M.gguf   8,60 Go  incompatible (AviUtl2)
    LTX-2.5-Distilled-Q3_K_M.gguf                10,73 Go  sous le plancher Q4
    LTX-2.5-Distilled-Q6_K.gguf                  17,38 Go  +34 % de temps, ecarte

70 Go -> 33 Go. Les trois etaient mesures et documentes ; a 60-85 Mo/s,
en reprendre un coute quelques minutes.

### Verified

Delegation : 12 appels d'outils en 54 s, l'agent nomme les trois plans et
rapporte `indetermine` pour chacun sans jamais parler de succes.

Audio natif : `pluie_toit_00001_.mp4`, AAC 48 kHz stereo, moyenne -7,9 dB
et crete 0,0 dB — niveau **releve**, pas deduit de la presence d'une
piste. 339 s, pic 11,07 Gio.

Images : quatre rendus sur disque, deux LTX et deux SDXL, tailles et
resolutions verifiees par ffprobe.

Disque : 70 Go -> 33 Go sur `C:/AI/Models/LTX`, plus 6,8 Go pour
`C:/AI/Models/Images`. Aucun residu `.part`.

Suites : backend **2 131 passes, 2 ignores** ; frontend **110 passes** ;
`npx tsc --noEmit` propre. Onglet Nuit verifie dans le navigateur.

---

## HOS-191 - Le relecteur, la file de nuit, et trois mesures fausses (2026-08-27)

Un plan video se termine toujours. ComfyUI rend un MP4 valide quel que soit
le contenu, et a cinq minutes de calcul par seconde de video finie, s'en
apercevoir au montage coute une nuit. Deux modules repondent a cela : un
relecteur qui regarde ce qui est sorti, et une file qui enchaine les plans
sans jamais compter un rendu acheve pour un rendu reussi.

Ce qui a coute du temps n'est pas leur ecriture. Ce sont **trois defauts de
mesure**, dont deux invisibles.

### Le relecteur a failli fabriquer de la confiance

Interroge une premiere fois, le modele a repondu « matches: true,
confidence: 98 » en enumerant comme presents les trois elements de la
consigne, dont de la vapeur que l'oeil ne trouvait pas. Un relecteur qui
approuve tout ne mesure rien.

La qualification passe donc par le cas negatif : la meme image, quatre
consignes fausses, graduees de l'absurde (un chiot en studio) au proche
(une rue de nuit en neons bleus sous la pluie — meme ambiance, autre
sujet). **4 refus sur 4**, consigne vraie acceptee, le cas proche refuse a
95 %.

### La fenetre bornee, encore

`num_predict` a 300 rendait `done_reason=length` et une reponse **vide** :
ce modele depense son budget en raisonnement avant de conclure. Le prendre
pour un refus aurait disqualifie un modele qui fonctionne. C'est le defaut
que ce depot documente deja sous « ni un echec sur parole », rencontre une
fois de plus, et il ne se reconnait pas plus facilement la deuxieme fois.

### Un cache KV de 256k pour juger une image

Le tag portait `num_ctx 262144` pour une image de 768 x 416 et cent vingt
jetons de consigne. L'allocation faisait depasser **300 s au chargement a
froid** : la premiere execution reelle est revenue en `TimeoutError`, ce
qui se lisait comme un relecteur en panne.

    residente    6,29 Gio  ->  2,41 Gio
    a froid     > 300 s    ->    9,9 s
    a chaud      21,7 s    ->    5,0 s

Le module, lui, avait raison : il a rendu `correspond: None` — « je n'ai
pas pu regarder » — et non `False`. La distinction a evite de conclure a
un plan non conforme sur une panne d'instrument.

### Trois images qui n'en etaient qu'une

`extraire()` documentait qu'elle rendait trois images reparties dans le
plan : « prendre seulement la premiere, c'est relire la couverture d'un
livre ». Elle en rendait **une**. Le filtre `thumbnail` choisit une image
representative par lot de cent, et un plan LTX en compte quarante-neuf.

Le lot reduit a la longueur du plan n'a pas corrige le defaut : les trois
fichiers sortaient alors **octet pour octet identiques**. Leurs tailles se
ressemblaient assez pour ne pas alerter — 386 Kio chacun — et seule une
empreinte SHA l'a montre. On demande desormais chaque image a un instant
precis, 15 / 50 / 85 % de la duree, une par appel.

### Un verdict qui portait sur un seuil jamais fixe

Sur le meme plan reel, deux reglages du **meme** modele ont vu exactement
la meme chose — rue etroite, nuit, sodium, asphalte mouille, pas de vapeur
— et rendu des verdicts opposes. Pas une divergence de perception : un
blanc dans la question. La consigne disait « sois strict » sans dire ce que
« correspond » signifie quand un element secondaire manque.

La regle est desormais ecrite — sujet, decor, moment et lumiere decident ;
un detail absent va dans `missing` et ne rejette pas — et l'assouplissement
a ete re-qualifie : toujours 4 refus sur 4.

### Un chemin qui ne menait nulle part

L'historique de ComfyUI decrit ses sorties par `{filename, subfolder,
type}`, dont aucun ne designe un fichier : la racine est dans les arguments
de lancement, `--output-directory E:\YouTube\Generations`. Le client ne
gardait que `filename`. Le relecteur recevait donc `rue_sodium_00001_.mp4`
et n'en tirait aucune image.

Trouve dans le rapport d'une nuit reelle, pas en relisant le code — et
seulement parce que la file avait ecrit `indetermine` au lieu de `retenu`.
Le comportement etait juste ; c'est la mesure qui manquait.

### Le montage, ou trois autres facons de rendre 0

`backend/studio/montage.py` assemble les plans retenus, pose la narration,
incruste les sous-titres — et **relit la duree du fichier obtenu**. Parce
que `ffmpeg` sort avec le code 0 dans trois cas ou le resultat n'est pas
celui qu'on croit : une entree manquante rend une video plus courte, un
SRT dont la fin precede le debut affiche un sous-titre qui ne disparait
jamais, et libass absent rend une video sans texte.

Mesure le 2026-08-27 : trois plans de 2,04 s -> 6,12 s verifiees, 1 s
d'encodage. Narration Piper de 9,96 s sur 6,12 s d'image, ecart `+3,84 s`
**rapporte et non corrige** — etirer changerait la voix, couper perdrait
la fin, et l'appelant est le seul a savoir lequel il prefere.
L'incrustation a ete constatee en comparant l'empreinte d'une image du
montage a la meme image du montage sans sous-titres.

### La file de nuit

`backend/studio/file_de_nuit.py`. Sept etats et non deux : un plan rendu
mais non relu est `indetermine`, jamais `retenu`. Elle reserve la carte
pour chaque rendu — un rendu lance pendant qu'une mission tient les 16 Gio
aboutit, dix-sept fois plus lentement, sans qu'aucune erreur ne le dise —
et la rend entre deux plans. Elle s'arrete apres trois echecs consecutifs :
au-dela, la nuit ne sert plus qu'a confirmer le meme defaut.

Le journal est reecrit apres **chaque** plan : une nuit coupee a la
sixieme heure doit laisser lisibles les cinq premieres.

Toutes ses dependances sont injectees. Une file qui ne se testerait que par
des nuits entieres ne serait jamais testee.

### Verified

Nuit reelle du 2026-08-27, file branchee sur ComfyUI + arbitrage +
relecteur : **2/2 plans retenus en 10 min**, 203 s et 212 s, pic 7,75 Gio
sur une carte de 15,98 — sur la carte, pas en memoire systeme. Chemins
absolus, relecture 3 images sur 3, confiance 100.

Discrimination verifiee sur un **second plan** que la qualification n'avait
pas servi : l'atelier est accepte pour sa consigne (3/3) et refuse pour
celle de la rue de nuit (0/3).

Une nuit precedente, avant le correctif des chemins, avait rendu 3 plans
en 309 / 294 / 309 s, tous a 7,61 Gio, tous consignes `indetermine` — la
file avait raison de ne pas les compter.

Montage final : 2 plans -> 4,08 s verifiees, h264 + aac, sous-titres
incrustes et constates a l'image.

Suites : backend **2 129 passes, 2 ignores** ; frontend **110 passes** ;
`npx tsc --noEmit` propre.

---

## HOS-190 (fin) — La quantification est presque gratuite (2026-08-27)

Meme format, meme graphe, seule la quantification change. 768 x 432,
49 images, 8 etapes.

    Q3_K_M   10,73 Go    251 s    pic 7,59 Gio
    Q5_K_M   15,66 Go    281 s    pic 7,61 Gio    +12 % de temps
    Q6_K     17,38 Go    336 s    pic 7,59 Gio    +34 % de temps

**Le pic de VRAM ne bouge pas.** 7,59 / 7,61 / 7,59 — a deux centiemes
pres, sur trois fichiers dont le plus gros depasse la carte de 1,4 Gio.

C'est la preuve definitive d'une hypothese formee en regardant les mesures
precedentes : ComfyUI **diffuse** les couches depuis la RAM au lieu de les
resider. `--cache-none` et `--disable-smart-memory` — les reglages que la
distribution patientx avait choisis pour ce materiel, et que j'avais failli
perdre en relancant le serveur avec mes propres drapeaux — font exactement
cela.

Le compromis n'est donc pas memoire contre qualite mais **temps contre
qualite**, et il est bon marche jusqu'a Q5 : quarante-six pour cent de bits
en plus pour douze pour cent de temps. Q6 demande vingt pour cent de plus
pour un ecart de quantification bien moindre.

Q5_K_M retenu, et consigne dans `hermes-ltx.bat` avec le tableau.

A noter : Q3_K_M etait **sous** le plancher que ce depot s'etait fixe
ailleurs — « jamais sous Q4 », note apres la campagne de modeles de secours.
La mesure confirme la regle, et cette fois elle ne coute presque rien.

### Verified

Cinq MP4 valides sous `E:\YouTube\Generations`, en-tete `ftyp` verifiee.
Suites inchangees : backend 2 083 passes, frontend 110 passes.

---

