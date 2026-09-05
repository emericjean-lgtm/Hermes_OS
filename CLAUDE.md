# Hermes OS — notes pour un agent

Ce fichier ne décrit pas l'architecture : `ARCHITECTURE.md`, `README.md` et
`docs/` le font déjà. Il rassemble ce qui n'est écrit nulle part et qui a
coûté du temps de débogage réel.

## La règle qui prime sur tout

**Hermes Agent (NousResearch, installé sous `%LOCALAPPDATA%\hermes\hermes-agent`)
est le cerveau des missions. Hermes OS est son système d'exploitation.**

Hermes OS fournit runtime, workspace, modèles, sécurité, persistance,
observabilité et UI. Il ne raisonne pas à la place de l'agent, ne choisit
pas ses outils et n'exécute pas de seconde boucle agentique sur le chemin
d'une mission.

Cette règle a déjà été violée une fois : `RealTaskExecutor` sélectionnait
Hermes Agent puis l'écrasait deux lignes plus bas par sa propre boucle
d'outils, si bien que toute mission liée à un workspace — le cas normal —
contournait l'agent. Le garde-fou est
`backend/tests/test_hermes_agent_is_the_brain.py`, dont l'échec porte le
message `HERMES_AGENT_BYPASS_DETECTED`. Ne le contourne pas ; s'il gêne,
c'est probablement lui qui a raison.

## Ne jamais croire un succès sur parole

La leçon centrale du projet. Cinq défauts distincts ont produit des missions
`success: True, 5/5` au-dessus d'un workspace **vide** : la boucle d'outils
concurrente, des toolsets CLI vidés, l'objectif perdu à la décomposition, un
contexte servi à 4096, et un timeout de 180 s. Chacune était invisible dans
le rapport de mission.

En pratique :

- Un artefact se vérifie **sur le disque**, jamais d'après le texte du modèle.
- `success = true` n'est pas une preuve ; `exit 0` non plus.
- `backend/mission/verification.py` compare le workspace avant/après et émet
  `mission.unverified` quand une mission réussit sans rien changer.
- Quand quelque chose échoue, lire le tableau `errors` des tâches et la
  ligne de commande du processus (`Get-CimInstance Win32_Process`), pas
  seulement le compteur de tâches.

## Ni un échec sur parole

Le symétrique de la règle précédente, et il a coûté plus cher. Sur huit
défauts de mesure trouvés pendant la construction du catalogue, **cinq
produisaient de faux échecs** : un extracteur JSON glouton notait 0/5 des
objets parfaits, `/api/generate` fusionnait raisonnement et réponse et
comptait 316 mots là où le modèle en avait écrit 7, un foin 28 % trop gros
faisait rejeter la requête avant que deux modèles ne soient interrogés, un
niveau de test affirmait une contrainte fausse, un extracteur de code
prenait le bloc encadré le plus long sans vérifier qu'il compile.

Aucun n'a été trouvé en relisant du code. Tous l'ont été sur un chiffre
invraisemblable. Deux signaux valent qu'on s'arrête :

- **Deux modèles sans rien de commun qui échouent identiquement.** C'est
  ce qui a démasqué le contexte à 4096, la fusion raisonnement/réponse et
  l'extraction de code. Un vrai plafond de compétence ne produit pas deux
  fois la même erreur.
- **Une durée absurde.** `0 s` par tentative, c'était un HTTP 400 jamais
  regardé. 439 s pour 5460 caractères, c'était une réponse tronquée.

Avant de conclure qu'un modèle ne sait pas faire quelque chose, conserver
sa réponse brute. Rejouer une campagne pour savoir qui du modèle ou de
l'instrument avait tort coûte le prix de la campagne.

## Un contexte fixe mesure le réglage, pas les modèles

`num_ctx` doit venir de ce que **chaque** modèle sert, pas d'une constante.
Fixé à 32768 pour tous, le départage de code a coupé la réponse de
qwen3.6-35b en plein milieu — son raisonnement avait rempli la fenêtre
avant que son code n'y tienne — alors que la campagne principale, qui l'a
classé `mythique`, tournait à 65536. L'épreuve de départage était donc plus
sévère que l'échelle qu'elle devait départager.

Ollama le dit : `done_reason == "length"` signifie que la fenêtre s'est
fermée sur le modèle. Une réponse tronquée n'est pas une erreur de
raisonnement et ne doit pas se noter comme telle.

## Modèles : mesurer, jamais supposer

Détail complet dans `docs/model-selection.md`. L'essentiel :

- La taille ne prédit rien — un 2,7 Md réussit là où un 11,9 Md échoue.
- La capacité `tools` annoncée par Ollama est déclarée jusque par un modèle
  d'embedding.
- Les benchmarks publiés servent à faire une liste courte, pas à décider.
- Le seul juge est `backend/model_intelligence/agentic_probe.py`, trois
  essais minimum, **un modèle à la fois** (il prend un verrou exclusif).

**Sur 16 Go, c'est l'architecture qui décide, pas le nombre de
paramètres.** Qwen3.8-27B, dense, déborde à tous les paliers dans ses deux
quantifications utiles — 12 % à 32k en Q3, 32 % en Q4 — et plafonne à
13,3 tok/s. Qwen3.6-35B-A3B a **sept milliards de paramètres de plus** et
tient 128k à 0 % de débordement, 89,3 tok/s, parce que seuls 3 Md sont
actifs par token. Un MoE plus gros passe là où un dense plus petit étouffe,
et aucune fiche technique ne le dit à votre place.

Matériel : AMD RX 6800, ~16 Go de VRAM. Un modèle qui déborde sur CPU
répond quand même, sans erreur, dix fois plus lentement et de façon
erratique — ce qui ressemble à un modèle peu fiable jusqu'à ce qu'on
regarde `size` moins `size_vram` dans `/api/ps`.

**Mais `/api/ps` ne mesure que les poids.** Ni le cache KV, ni les tampons
de calcul. Mesuré sur Muse-Glimmer-30B à 64k : `/api/ps` annonçait
9,55 Gio pendant que le processus `llama-server` en détenait 13,21. L'écart
va toujours dans le mauvais sens — il fait croire qu'il reste de la place
pour un second modèle. Pour l'occupation réelle, lire le compteur GPU :
`backend/runtime/resources/vram_physique.py` pour la machine entière —
c'est la source d'admission, et la seule définition de la requête —
`backend/model_intelligence/model_bench.py` (`gpu_dedicated_bytes`) pour
un processus nommé.

**Une seule vérité de capacité, et personne ne la recalcule** (R-3/R-4,
HOS-259). `ResourceManager` répond à « combien de tâches tiennent »
(`places_disponibles`) ; `GraphExecutor` pose la question et respecte la
réponse. Il ne lit ni la carte, ni `/api/ps`, ni un compteur — et le
portillon qui applique la borne n'autorise rien : le franchir ne donne
aucun droit sur la VRAM, seule la réservation en donne. Un second calcul
de capacité, où qu'il naisse, rend les deux divergents ; c'est le défaut
que `mission_max_parallel_tasks` incarnait, avec une constante d'un côté
et la carte de l'autre.

**Et l'admission a déjà été trompée par ce piège** (A-15, HOS-258) : sans
`rocm-smi`, ce qui est le cas ici, `ResourceManager` retombait sur
`/api/ps`. Mesuré carte chargée, il annonçait 12,74 Gio occupés sur
15,98 quand la carte en portait 15,12, et laissait admettre un modèle de
1,5 Gio sur 0,87 Gio libres. Une source qui sous-estime l'occupation ne
doit jamais servir de repli silencieux à une décision d'admission : sans
mesure, on refuse.

Et ne pas calculer un cache KV sans regarder le motif d'attention. Muse
Glimmer est en « Local, Local, Local, Global » avec fenêtre glissante de
2048 : passer de 64k à 128k lui coûte 0,43 Gio, pas les 3,25 Gio d'un
calcul qui suppose toutes les couches globales.

## Contexte Ollama : le piège le plus coûteux

L'endpoint OpenAI-compatible `/v1` qu'utilise Hermes Agent **ne transporte
pas `num_ctx`**. Trois leviers, par ordre de préférence :

1. **`PARAMETER num_ctx` dans un Modelfile** — par modèle, définitif, sans
   effet de bord. C'est ainsi que `qwen3.5:9b-128k` et `gemma4:12b-64k`
   existent. `ollama show --modelfile <tag>` pour inspecter.
2. **`options.num_ctx` dans la requête** — possible sur les endpoints
   natifs (`/api/embeddings`), pas sur `/v1`.
3. **`OLLAMA_CONTEXT_LENGTH`** — global, donc dangereux : le porter à 65536
   pour l'agent a fait passer le modèle d'embedding de 0,64 Go à 5,88 Go de
   VRAM et 57 s par appel.

En dessous de ~64k servis, les schémas d'outils sont tronqués et l'agent
répond qu'il n'a pas d'outils — ce qui est alors littéralement vrai.
`backend/runtime/context_guard.py` le détecte au démarrage.

## Environnements Python : il y en a deux, et c'est voulu

Hermes OS a son propre virtualenv, `.venv`, décrit par `requirements.txt`.
Hermes Agent a le sien, sous `%LOCALAPPDATA%\hermes\hermes-agent\venv`.

Ils étaient confondus jusqu'à HOS-103 : `python` sur le PATH était
l'interpréteur de l'agent, si bien que `hermes update` resynchronisait les
dépendances de Hermes OS sans que rien ne le dise. Le 13 août 2026, une
mise à jour a laissé `opentelemetry-exporter-otlp-proto-grpc` en 1.44.0
face à une famille en 1.39.1 et huit modules de test ont cessé de
s'importer, sans qu'une ligne de Hermes OS ait changé.

`backend/ral/adapters/hermes_agent_cli.py` pointe **en absolu** vers
l'interpréteur de l'agent. Ne jamais remplacer ce chemin par
`sys.executable` : `.venv` n'a aucune des dépendances de l'agent.

## La roadmap est un document, pas une mémoire de session

Avant tout travail de roadmap — ouvrir une section, la faire avancer, la
déclarer close :

1. lire `docs/HERMES_OS_ROADMAP_STATE.md`, qui tient en une page et dit
   quelle section est active ;
2. lire cette section dans `docs/HERMES_OS_MASTER_ROADMAP.md` ;
3. vérifier que `HEAD` correspond au `BASELINE` qu'annonce l'état, ou
   relever l'écart avant de commencer ;
4. rester dans le périmètre de la section active ;
5. mettre à jour l'état **et** le statut de la section en fin de passe.

**Une section ne passe pas 🟢 parce qu'un rapport l'affirme.** Le §0 de la
roadmap maître donne l'échelle — de `PRESENT` à `DEMONSTRATED` — et aucun
niveau ne s'infère d'un autre. Trois des défauts les plus coûteux du
projet vivaient entre « le code existe » et « quelque chose l'appelle » :
le pipeline de connecteurs, `Statut.PERDU` que rien ne posait, et deux
contrôles de sécurité livrés, testés, marqués faits, sans un seul
appelant.

## Commandes

```bash
.venv/Scripts/python.exe -m pytest -q                 # ~6 min, doit être vert
cd frontend && npx tsc --noEmit                       # typecheck
```

**Sans argument de chemin.** `pytest.ini` déclare `testpaths = backend/tests
tests` depuis HOS-111, précisément parce que le second répertoire — 2 594
tests, 53 % du dépôt — n'était exécuté par personne. Passer `backend/tests`
en argument **écrase** `testpaths` et recrée exactement l'angle mort que
HOS-111 avait fermé.

C'est ce qui s'est produit : ce fichier a documenté la commande étroite, et
`tests/` a cessé d'être lancé. Il y est resté cassé depuis HOS-175 — un
module qui ne s'importait plus, deux tests qui lançaient un vrai
sous-processus d'inférence et bloquaient la suite. Trouvé le 2026-09-02,
soit vingt-deux jours et trente-sept jalons plus tard.

Backend et frontend se lancent via `preview_start` (`.claude/launch.json`),
jamais avec un `npm run dev` détaché.

## Conventions

- Le CHANGELOG raconte le **pourquoi** et les mesures, pas la liste des
  fichiers touchés. Une entrée corrigée par une mesure ultérieure est
  amendée explicitement, jamais réécrite en silence.
- Les commentaires expliquent la raison d'être, pas le fonctionnement — une
  règle sans son pourquoi se fait supprimer au premier refactoring.
- Les tests nomment l'incident qu'ils empêchent.
- Ne jamais commiter sans que la suite complète soit verte. **Une seule
  exception**, et elle se mérite : un test qui affirme un contrat
  architectural qu'on vient de remplacer. Il n'est ni faux ni cassé — il
  est **périmé**, et le réécrire dans la passe même qui change le contrat
  reviendrait à écrire la preuve et la chose prouvée de la même main.
  Conditions cumulatives, faute de quoi la suite rouge reste interdite :
  1. chaque test toléré est **nommé dans le message de commit**, avec le
     contrat qu'il affirme et celui qui l'a remplacé ;
  2. son échec est une **assertion** sur ce contrat, mesurée — le même
     test passe au commit précédent, et échoue ici sur la ligne qu'on
     attend. Un test qui échoue autrement cache autre chose ;
  3. **aucun autre rouge**, aucune désélection nouvelle, aucune assertion
     affaiblie, aucun test supprimé ni marqué `skip`/`xfail` ;
  4. une passe dédiée, annoncée, les réécrit ensuite.
  Rien ici n'autorise une suite rouge « en attendant ». Le précédent qui
  a coûté cher est plus haut, à `testpaths` : ce fichier a déjà transformé
  une commande étroite en angle mort de vingt-deux jours. Un test toléré
  qu'aucun commit ne nomme redevient exactement ça.
