# Studio Center — cahier des charges

> Génération d'images, de plans vidéo et de voix, pilotée par Hermes Agent.
> HOS-190. Écrit le 2026-08-27, mesures à l'appui.

## Ce que ce document n'est pas

Ce n'est pas une proposition de fonctionnalités. Chaque décision ci-dessous
est attachée à un chiffre relevé sur cette machine, ou dit explicitement
qu'elle ne l'est pas encore. Le projet a une règle sur ce point et elle
s'applique ici comme ailleurs : une fiche technique ne décide de rien.

## Le problème, et pourquoi ce n'est pas le confort

L'objectif est de déléguer la production vidéo à Hermes. Encastrer
l'interface de ComfyUI dans le Cockpit ne l'atteint pas : on obtiendrait le
même éditeur de graphe dans la même fenêtre, c'est-à-dire du changement
d'application sans le changement de fenêtre. L'agent ne manipule pas un
graphe de nœuds, il appelle une API.

La vraie raison d'intégrer est ailleurs, et elle est mesurée.

**Les 16 Gio de la RX 6800 sont indivisibles.** Ollama tenant gpt-oss-20b
occupe 13,21 Gio — mesuré, et non les 9,55 que `/api/ps` annonce. LTX-2.5 en
Q3_K_M en réclame 10,73 pour ses seuls poids. Ils ne peuvent pas coexister.

Aujourd'hui, lancer un rendu pendant qu'une mission tourne ne produit
**aucune erreur** : ROCm complète en mémoire système et l'un des deux
devient dix-sept fois plus lent. Mesuré le 27 août, attention à 16 384
jetons : 3 226 ms en débordement contre 187 ms sur la carte.

Le seul composant qui voit les deux runtimes, c'est Hermes OS. C'est ça,
l'argument.

## Ce qui a été mesuré sur cette machine

### Le socle est sain

| Mesure | Valeur |
|---|---|
| PyTorch | 2.13.0+rocm10.1.0a20260822, HIP 7.16 |
| GPU vu par torch | AMD Radeon RX 6800, 15,98 Gio |
| matmul fp16 8192² | **29,2 TFLOPS** — ~90 % du plafond théorique |

Ce n'est pas une installation dégradée. Ni DirectML, ni ZLUDA, ni CPU :
ROCm natif sous Windows, avec un débit conforme au silicium.

### Le mur d'attention n'existe que pour PyTorch

`gfx1030` n'a ni Flash ni Memory-Efficient SDP — les deux noyaux refusent de
se charger, avec le message « not compiled for current AMD GPU
architecture ». Seul le backend MATH répond, qui matérialise la matrice
entière.

Mesuré à 16 384 jetons, l'ordre de grandeur d'un plan de 5 s en 512p :

| Implémentation | Temps | Pic VRAM | Verdict |
|---|---|---|---|
| `attention_pytorch` | 3 226 ms | 20,16 Gio | **déborde** en RAM système |
| `attention_basic` | 1 707 ms | 16,22 Gio | déborde |
| `attention_split` | **187 ms** | 8,25 Gio | tient |
| `attention_sub_quad` | 307 ms | **4,15 Gio** | tient |

À 32 768 et 49 152 jetons, `split` et `sub_quad` tiennent encore — 920 ms et
3 657 ms pour `split`, sous 10 Gio. **Le format YouTube est atteignable ; ce
qui décidait n'était pas la carte mais le choix d'implémentation.**

### Pourquoi `sub_quad` et non `split`

`split` est 60 % plus rapide. Il n'est pourtant pas retenu :

    poids Q3_K_M            10,73 Gio
    + pic split à 16k        8,25 Gio
    = 18,98 Gio                        sur 15,98 disponibles → débordement

    poids Q3_K_M            10,73 Gio
    + pic sub_quad à 16k     4,15 Gio
    = 14,88 Gio                        tient

60 % plus lent en restant sur la carte vaut mieux que 17× plus lent en
passant par la RAM. Le drapeau est `--use-quad-cross-attention`, figé dans
`hermes-ltx.bat` avec cette raison écrite à côté — sans quoi quelqu'un le
« corrigera » un jour vers `split`.

## Architecture

### 1. ComfyUI est un runtime, pas une application voisine

La couche RAL (`backend/ral/`) porte déjà `RuntimeInterface` —
`capabilities()`, `status()`, `start()`, `stop()`, `get(capability)` — un
registre, une fabrique et un sélecteur. ComfyUI s'y enregistre comme Ollama
et ktransformers.

Il apporte une capacité nouvelle, `GenerationCapability`, à côté de Chat,
Tools, Memory, Vision : synthèse d'image et de plan vidéo.

**C'est cet enregistrement qui donne à Hermes OS le droit d'arbitrer.**
Décharger le modèle de langage avant un rendu, le recharger après. Sans
lui, les deux runtimes se disputent la carte en silence.

### 2. La politique de VRAM est explicite et mesurée

Un seul locataire lourd à la fois. La règle existe déjà pour les modèles de
langage — `OLLAMA_MAX_LOADED_MODELS=1` — et s'étend ici :

* Un rendu demande le verrou. S'il est tenu par une mission, il attend, et
  l'opérateur passe en `decision` : quelque chose attend vraiment.
* Avant un rendu, Ollama décharge (`/runtime/resources/unload` existe).
* Après, le modèle de mission remonte.
* Le pic mesuré du rendu est comparé au budget. S'il dépasse 98,5 % de la
  VRAM, l'événement `runtime.overloaded` part et l'opérateur passe en
  `debordement` — ce qui rend visible ce qui, sinon, ne se lit que comme
  « c'est lent aujourd'hui ».

### 3. La délégation passe par des outils MCP

`studio_state`, `studio_models`, `studio_render`, `studio_queue` et
`studio_outputs` rejoignent les 71 outils que l'agent appelait déjà — 76
désormais. L'agent compose le
graphe et le soumet, comme il écrit un fichier avec `files_apply`.

Les rendus vont dans `E:\YouTube\Generations`, à côté de `Archives`,
`Assets`, `Episodes`, `Exports` et `Shorts` — jamais dedans. La génération
produit surtout des rebuts : dix plans pour un bon. Les mélanger aux
dossiers humains rendrait le tri impossible.

### 4. Le Studio Center est natif, l'éditeur de graphe est l'échappatoire

Le Center est en SODIUM comme le reste : on décrit le plan, on voit la
file, la VRAM, les rendus. L'opérateur y prend tout son sens —
`chargement` pendant que les 10,73 Gio montent, `écriture` pendant le
débruitage, `debordement` si le calcul était optimiste.

L'interface de ComfyUI vit dans **un onglet** de ce Center, en cadre. Elle
ne pose ni `X-Frame-Options` ni `frame-ancestors` : l'encastrement
fonctionne. C'est l'atelier pour bricoler un graphe à la main, pas le
tableau de bord.

## Les types de modèles

Neuf. État au 2026-08-27 : la colonne de droite dit ce qui est **installé
et mesuré**, pas ce qui serait souhaitable.

| # | Type | Rôle | État |
|---|---|---|---|
| 1 | LLM texte | script, titres, description | déjà là |
| 2 | LLM extraction | découpage en plans | déjà là — qwen3.5-9b, 100/100 |
| 3 | T2I diffusion | miniatures, plans-clés | **SDXL 1.0** — 35 s en 1344 × 768 |
| 4 | I2V / T2V | animation | **LTX-2.5 Q5_K_M** — 5 min de calcul par seconde |
| 5 | TTS narration | voix off | Piper et Kokoro mesurés, **le choix reste à faire à l'oreille** |
| 6 | ASR mot-à-mot | sous-titres | **faster-whisper**, bornes par mot vérifiées |
| 7 | T2M | musique | rien — YuE et Stable Audio présélectionnés sur licence, jamais testés |
| 8 | Upscale | haute résolution | modèle sur le disque, **jamais essayé** |
| 9 | VLM | relire ce qui a été généré | **qwen3.5-2b-relecteur** — 4 refus sur 4 |

Le son d'ambiance ne figure plus au septième rang : LTX-2.5 le produit
lui-même, synchronisé à l'image, ce qu'aucun modèle de musique ne peut
faire. La ligne 7 ne concerne donc plus que la musique proprement dite.

Le neuvième mérite qu'on s'y arrête. Un modèle qui *regarde* l'image
produite et dit si elle correspond à la consigne, c'est la règle de la
maison appliquée à la génération : un rendu qui se termine sans erreur
n'est pas un rendu réussi.

## Le verdict, mesuré

Trois rendus réels, LTX-2.5 Q3_K_M, 8 étapes, `res_multistep`, décodage par
tuiles. Fichiers vérifiés sur le disque — en-tête `ftyp`, pas seulement un
succès annoncé.

| Format | Images | Durée | Pic VRAM | Débordement |
|---|---|---|---|---|
| 512 × 288 | 49 (2 s) | **170 s** | 7,98 Gio (50 %) | non |
| 768 × 432 | 49 (2 s) | **251 s** | 7,59 Gio (47 %) | non |
| 704 × 1280 | 97 (4 s) | **1 218 s** (20,3 min) | 7,04 Gio (44 %) | non |

Deux choses ressortent, et aucune n'était devinable.

**La VRAM n'est pas la contrainte.** Elle reste autour de 7 à 8 Gio quelle
que soit la résolution : le décodage par tuiles la plafonne, et le pic
*baisse* même à mesure que le format grandit, parce que les tuiles restent
de taille fixe pendant que le reste se répartit. Sur les 15,98 Gio, la
moitié dort.

**Le temps est la contrainte, et il est sévère.** Vingt minutes pour quatre
secondes de vertical, soit **environ cinq minutes de calcul par seconde de
vidéo finie**.

### La quantification : monter est presque gratuit

Même format, même graphe, seule la quantification change.

| Quantification | Fichier | Durée | Pic VRAM |
|---|---|---|---|
| Q3_K_M | 10,73 Go | 251 s | 7,59 Gio |
| **Q5_K_M** | 15,66 Go | **281 s** (+12 %) | 7,61 Gio |
| Q6_K | 17,38 Go | 336 s (+34 %) | 7,59 Gio |

**Le pic de VRAM ne bouge pas.** 7,59, 7,61, 7,59 — à deux centièmes près,
sur trois fichiers dont le plus gros dépasse la carte de 1,4 Gio. C'est la
preuve définitive que ComfyUI diffuse les couches depuis la RAM au lieu de
les résider : `--cache-none` et `--disable-smart-memory`, les réglages que
la distribution avait choisis pour ce matériel, font exactement cela.

Le compromis n'est donc pas mémoire contre qualité, mais **temps contre
qualité** — et il est bon marché jusqu'à Q5.

**Q5_K_M est retenu.** Quarante-six pour cent de bits en plus pour douze
pour cent de temps. Q6_K coûte encore vingt pour cent de plus pour un écart
de quantification bien moindre : le rendement s'effondre là.

À noter pour la mémoire du projet : Q3_K_M était **sous** le plancher que
ce dépôt s'était fixé ailleurs — « jamais sous Q4 ». La mesure confirme la
règle, et cette fois elle est gratuite.

### Ce que cela permet, et ce que cela interdit

* **Un short de 30 s** : sept à huit plans de 4 s, soit **2 h 30 à 3 h de
  rendu**. Faisable la nuit, jamais en interaction.
* **Une vidéo longue** : hors de portée localement. Une minute de montage
  coûterait cinq heures.
* **Les images fixes** : négligeables à côté — le même modèle rend une image
  en quelques secondes.

La production locale est donc un **atelier de nuit**, pas un outil de
tâtonnement. C'est exactement le régime qu'une mission Hermes sait tenir :
on décrit, on lance, on relit au matin. L'API garde son rôle pour ce qui
doit sortir tout de suite, ou en long format.

### Le décodage par tuiles n'est pas un réglage, c'est la condition

Le premier rendu a échoué à `VAEDecode`, qui a réclamé **14,58 Gio d'un
seul bloc** pour 49 images en 512 × 288 — sur une carte qui en a 15,98 dont
10,73 déjà pris par le transformeur. Le débruitage, lui, avait tourné 267 s
sans incident : le goulot n'était pas le modèle mais la sortie du VAE, qui
matérialise toutes les images à la fois.

`VAEDecodeTiled` avec `temporal_size` à 16 — et non les 64 par défaut,
parce que c'est la dimension temporelle qui explose sur une vidéo — ramène
le pic à 7,98 Gio. Le même rendu passe alors en 170 s au lieu d'échouer
après 267.

### Deux erreurs commises en chemin, et ce qu'elles apprennent

**L'encodeur.** J'ai d'abord téléchargé 8,6 Go d'un GGUF nommé
`LTX-2.5-gemma4-12b-text-encoder-Q4_K_M` — le nom correspondait, l'usage
non : son dépôt indique qu'il sert le moteur `engine25` du greffon
Nz-Videomni pour **AviUtl2**, et qu'il est « incompatible avec le Gemma 4
générique ». ComfyUI-GGUF le refuse, `ltxv` n'étant pas dans sa
`TXT_ARCH_LIST`. Le bon fichier porte `comfy` dans son nom, se charge par
le nœud natif `CLIPLoader` en type `ltxv`, et pèse 14,32 Go.

**Le schéma des échantillonneurs.** `sampler_disponible()` lisait
`champ[0]`, obtenait la chaîne `"COMBO"` du schéma V3, et en rendait la
première lettre. ComfyUI a refusé le graphe avec « sampler_name: 'C' not in
(list of length 44) » — un message assez précis pour trouver la faute en une
lecture, ce qui n'est pas toujours le cas.

Les deux ont la même forme : un nom plausible pris pour une garantie.

---

## Le relecteur (HOS-191)

Un plan vidéo **se termine toujours**. ComfyUI rend un MP4 valide quel que
soit le contenu, et à cinq minutes de calcul par seconde de vidéo finie,
s'en apercevoir au montage coûte une nuit. C'est la règle centrale de ce
dépôt appliquée à la génération : `success = true` n'est pas une preuve.

Le relecteur extrait des images du plan et les confronte à la consigne qui
devait le produire. `backend/studio/relecteur.py`.

### Le piège qu'il a failli devenir

Interrogé une première fois, le modèle a répondu « matches: true,
confidence: 98 » en énumérant comme présents les trois éléments de la
consigne — dont de la vapeur que l'œil ne trouvait pas. Un relecteur qui
approuve tout ne mesure rien : il **fabrique** de la confiance, ce qui est
pire que de n'en fabriquer aucune.

La qualification passe donc par le cas négatif : la même image, quatre
consignes fausses, graduées de l'absurde (un chiot en studio) au proche
(une rue de nuit en néons bleus sous la pluie — même ambiance, autre
sujet). Mesuré le 2026-08-27 sur `qwen3.5-2b-relecteur`, trois images par
plan : **4 refus sur 4**, consigne vraie acceptée. Le cas « proche mais
faux » est refusé à 95 %.

### Trois défauts trouvés, dont deux invisibles

**La fenêtre bornée.** `num_predict` à 300 rendait `done_reason=length` et
une réponse **vide** : ce modèle dépense son budget en raisonnement avant
de conclure. Le prendre pour un refus aurait disqualifié un modèle qui
fonctionne. C'est le défaut que ce dépôt documente sous « ni un échec sur
parole », rencontré une fois de plus.

**Le contexte de 256k.** Le tag d'origine portait `num_ctx 262144` pour
juger une image de 768 × 416 avec une consigne de cent vingt jetons. Le
cache KV inutilisé faisait dépasser **300 s au chargement à froid** — ce
qui s'est lu comme un relecteur en panne, `TimeoutError`, verdict `None`.
Le module a réagi correctement (il a dit « je n'ai pas pu regarder », pas
« ça ne correspond pas »), mais la mesure était fausse. Un tag à 16384 :

| | 256k | 16k |
|---|---|---|
| Résident | 6,29 Gio | **2,41 Gio** |
| À froid | > 300 s (délai dépassé) | **9,9 s** |
| À chaud | 21,7 s | **5,0 s** |

**Trois images qui n'en étaient qu'une.** `extraire()` documentait qu'elle
rendait trois images réparties dans le plan — « prendre seulement la
première, c'est relire la couverture d'un livre ». Elle en rendait **une**.
Le filtre `thumbnail` choisit une image représentative par lot de cent, et
un plan LTX en compte quarante-neuf. Le lot réduit à la longueur du plan
n'a pas corrigé le défaut : les trois fichiers sortaient alors *octet pour
octet identiques*. Les tailles se ressemblaient assez pour ne pas alerter ;
seule une empreinte SHA l'a montré. On demande désormais chaque image à un
instant précis — 15 %, 50 %, 85 % de la durée — une par appel.

Aucun des trois n'a été trouvé en relisant du code.

### Une règle de verdict, parce que son absence en était une

Sur le même plan réel, deux réglages du **même** modèle ont vu exactement
la même chose — rue étroite, nuit, sodium, asphalte mouillé, pas de vapeur
— et rendu des verdicts opposés. Ce n'était pas une divergence de
perception mais un blanc dans la question : la consigne disait « sois
strict » sans dire ce que « correspond » signifie quand un élément
secondaire manque.

La règle est maintenant explicite : le plan correspond quand le **sujet,
le décor, le moment et la lumière** sont ceux de la consigne ; un détail
absent va dans `missing` et ne suffit pas à rejeter. À ce prix de rendu, un
plan correct rejeté pour une vapeur manquante coûte autant qu'un plan faux
accepté. L'assouplissement a été re-qualifié : toujours 4 refus sur 4.

Le verdict reste **conjonctif** entre les images : une seule qui ne
correspond pas condamne le plan, parce qu'un plan dont le dernier tiers
dérive n'est pas utilisable et qu'une moyenne le ferait passer.

---

## La file de nuit (HOS-191)

`backend/studio/file_de_nuit.py`. Un short de trente secondes demande sept
à huit plans, soit près de trois heures de calcul : la production est un
atelier de nuit, pas un outil de tâtonnement.

Trois refus la définissent :

- **Elle ne compte pas un plan comme réussi parce qu'il s'est terminé.**
  Un plan rendu mais non relu est `indetermine` — jamais `retenu`. Les
  sept états sont distincts jusque dans l'écran, parce que « le fichier
  existe » et « le fichier est bon » sont deux faits différents.
- **Elle ne lance rien sans la carte**, par `arbitrage.carte_reservee`. La
  réservation couvre le rendu et s'arrête là : la relecture charge 2,41 Gio
  à côté des 7,61 que ComfyUI garde, ce qui tient, et tenir le verrou plus
  longtemps empêcherait une mission de reprendre la main entre deux plans.
- **Elle s'arrête après trois échecs consécutifs.** Au-delà ce n'est plus
  un aléa, et continuer coûterait huit heures pour confirmer ce que le
  troisième échec disait déjà.

Le journal est réécrit **après chaque plan**, pas à la fin : une nuit
coupée à la sixième heure doit laisser lisibles les cinq premières.

Toutes les dépendances sont injectées — `derouler()` s'éprouve sans GPU,
sans ComfyUI et sans Ollama. Une file qui ne se testerait que par des nuits
entières ne serait jamais testée. `atelier()` est le seul point qui
connaisse les trois à la fois.

### Surfaces

| | |
|---|---|
| `POST /studio/night` | dépose des plans, rend la main aussitôt |
| `GET /studio/night` | le rapport, relu du journal sur disque |
| `studio_night` (MCP) | ce que Hermes Agent appelle pour déléguer une nuit |
| `studio_night_report` (MCP) | ce qu'elle a réellement produit |
| Studio Center → onglet **Nuit** | le rapport du matin, par état |

Comme `/studio/render`, aucune de ces surfaces ne compose de graphe : il
vient de l'appelant. La règle qui prime sur tout réserve cette décision à
Hermes Agent, et un « service qui construit le bon workflow » serait
exactement la seconde boucle qu'elle interdit.

---

## Le montage (HOS-191)

`backend/studio/montage.py`. Le dernier maillon : des plans retenus, une
narration, des sous-titres, un fichier fini — et la preuve que ce fichier
est bien ce qu'on a demandé.

### Trois façons dont `ffmpeg` rend 0 sans faire ce qu'on croit

- **Une entrée manquante** : la vidéo sort plus courte, code 0. Le module
  refuse donc d'assembler dès qu'un plan manque, plutôt que de livrer un
  montage amputé qui ne se verrait qu'au visionnage — après la nuit qui a
  payé les autres plans.
- **Un SRT incohérent** (fin avant début) : accepté, et le sous-titre ne
  disparaît jamais. `ecrire_srt()` écarte ces segments et renumérote sans
  trou, un rang manquant faisant ignorer la suite par certains lecteurs.
- **libass absent** : la vidéo sort sans texte. `sous_titres` n'est mis à
  vrai qu'après vérification du filtre ; sinon le montage aboutit avec un
  avertissement, sans promettre ce qu'il n'a pas produit.

La vérification finale est une relecture de la durée du fichier obtenu,
comparée à la somme des plans, à une demi-seconde près. `duree_conforme`
est faux aussi quand la durée n'a pas pu être lue : non mesuré n'est pas
conforme.

### Le décalage voix / image est rapporté, jamais corrigé

Une narration plus longue que les plans est le cas normal — on écrit le
texte avant de savoir combien de plans on gardera. Étirer changerait la
voix, couper perdrait la fin ; l'appelant est le seul à savoir lequel il
préfère. Le module pose `-shortest` (l'image commande, sinon la vidéo
gagnerait un écran noir) et **le dit** dans `avertissements`.

### Mesuré le 2026-08-27

Trois plans de 2,04 s → 6,12 s vérifiées, 1 s d'encodage en x264 CRF 18.
Narration Piper de 9,96 s sur 6,12 s d'image : écart `+3,84 s` rapporté.
Transcription `faster-whisper small` en 4 s, deux segments, deux
sous-titres écrits. Incrustation constatée en comparant l'empreinte SHA
d'une image du montage à la même image du montage sans sous-titres —
`5227…` contre `a01f…`, et le texte lisible à l'œil.

La build ffmpeg de cette machine (Gyan 8.1.2) porte `--enable-libass`,
`--enable-fontconfig` et `--enable-libfreetype`.

### Surfaces

| | |
|---|---|
| `studio_assemble` (MCP) | joindre des plans, poser voix et sous-titres, vérifier |
| `studio_subtitles` (MCP) | transcrire une narration et écrire le SRT |

Comme partout ailleurs dans le Studio, l'ordre des plans, le texte et le
rythme viennent de l'appelant. Ce module assemble et vérifie ; il ne
monte pas à la place de qui décide.

---

## La délégation à Hermes Agent (HOS-192)

C'était le but déclaré du projet, et il n'avait jamais été éprouvé. Deux
blocages, tous deux silencieux, l'en empêchaient — et aucun n'était dans
le code de Hermes OS.

**`mcp_servers.hermes-ollama.tools.include` est une liste blanche.**
Enregistrer neuf outils sur le serveur MCP ne les donne pas à l'agent : il
faut les y nommer. Sans cela l'agent ne voit rien, ne dit rien, et répond
de mémoire. C'est exactement la forme du défaut que l'EventHub avait
présenté en avalant trente-cinq topics.

**`cache/mcp_schema_cache.json` gardait les seize anciens outils.** Même
la liste corrigée n'aurait rien changé tant que le cache tenait.

Une fois les deux levés, l'agent a été interrogé sur deux faits qu'il ne
pouvait pas deviner — l'état du runtime et le rapport de la dernière file.
Douze appels d'outils en 54 s, et surtout :

> « none are in a successful "kept" state — they are all in the
> "indetermine" state »

La distinction entre « le fichier existe » et « le fichier est bon » a
survécu jusqu'à une réponse en langage naturel. C'est le seul test qui
comptait : un agent qui aurait lu `indetermine` et écrit « 3 plans
réussis » aurait rendu toute la chaîne inutile.

Le mot « déléguer » n'apparaît pas dans l'invite, et ce n'est pas un
hasard : ce dépôt a mesuré que le mentionner suffit à faire cesser les
appels d'outils du modèle local.

---

## Les images fixes (HOS-192)

Avant de télécharger douze gigaoctets : LTX-2.5 avec `length: 1` rend une
image. Mesuré le 2026-08-27, même graphe qu'un plan à une image près.

| | temps | pic VRAM | |
|---|---|---|---|
| 768 × 432 | 169 s | 6,86 Gio | ✓ |
| 1024 × 1024 | 219 s | 14,57 Gio | **CUDA OOM** sur `VAEDecode` |
| 1280 × 720 | 220 s | 14,58 Gio | ✓ de justesse |

### Une hypothèse que la mesure a démentie

J'ai conclu de l'OOM qu'il fallait tuiler le décodage, comme pour la vidéo,
et je l'ai écrit avant de le vérifier. La mesure ne le confirme pas : avec
`VAEDecodeTiled`, le 1024 × 1024 tournait encore après **455 s** sans avoir
abouti, épinglé à 14,65 Gio, et j'ai fini par l'interrompre.

Ce que cela dit, prudemment : le pic de ~14,6 Gio est atteint quel que soit
le mode de décodage, donc il ne vient pas du décodage seul. L'OOM tombait
sur `VAEDecode` parce que celui-ci demandait 2,67 Gio **de plus** sur une
carte déjà pleine — la pression était là avant lui.

Ce que cela ne dit pas : je n'ai pas isolé la cause, et j'ai interrompu le
1280 × 720 tuilé à 150 s, soit **avant** les 220 s qu'avait mis le non
tuilé. Il n'est donc pas établi que le tuilage soit plus lent ici ; je l'ai
coupé trop tôt pour le savoir.

La conclusion utilisable est étroite : **au-delà de ~0,9 mégapixel, LTX est
à la limite de cette carte pour une image fixe**, et le rendre confortable
demanderait une mesure que je n'ai pas faite.

### Une piste non explorée, et elle est déjà sur le disque

`ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` — 0,93 Go, jamais
utilisé — et le nœud `LTXVLatentUpsampler` existe dans cette installation.

Le chemin évident serait donc : rendre en 768 × 432, qui tient
confortablement à 6,86 Gio, puis agrandir le **latent** avant de décoder.
On obtiendrait du 1536 × 864 sans jamais approcher la falaise de VRAM.

Non mesuré. C'est écrit ici parce que le modèle et le nœud sont là, pas
parce que ça marche : la distinction est tout l'objet de ce document.

### Ce que LTX vaut comme modèle d'image

Bon pour l'ambiance — lumière, matière, composition, profondeur de champ.
Il a respecté la lumière latérale demandée. Faible sur l'objet précis :
demandé un sextant, il rend des compas et une règle parallèle, et le détail
fin est mou.

### SDXL, mesuré côte à côte

Même consigne, même graine, modèle entraîné pour l'image fixe.

| | temps | pic VRAM | poids |
|---|---|---|---|
| SDXL 1024 × 1024 | **45 s** | 13,46 Gio | 1,73 Mo |
| SDXL 1344 × 768 | **35 s** | 13,23 Gio | 1,70 Mo |

Cinq fois plus rapide, à une résolution que LTX n'atteignait pas. L'objet
est net, les graduations lisibles, la matière crédible. En revanche SDXL a
ignoré la lumière latérale et rendu une composition à plat, là où LTX
l'avait respectée.

**Ils sont complémentaires, et c'est le résultat le plus utile :** SDXL
pour une vignette dont le sujet doit se reconnaître, LTX pour un plan
d'ambiance ou une image qui doit se raccorder à de la vidéo.

Installé sous `C:/AI/Models/Images`, cartographié par une entrée `images:`
dans `extra_model_paths.yaml`. Licence CreativeML Open RAIL++-M : usage
commercial permis — le filtre décisif, celui qui a écarté Flux.1-dev
(non commercial). Flux.1-schnell est pourtant Apache 2.0, mais il demande
en plus un encodeur T5 de cinq à dix gigaoctets sur une carte déjà partagée
avec LTX.

Le VAE corrigé (`sdxl_vae.safetensors`) est chargé séparément : celui
embarqué dans le checkpoint produit des artefacts en fp16.

## L'audio natif de LTX-2.5 (HOS-192)

`ltx-2.5-audio-vae-bf16.safetensors` était sur le disque depuis le début et
n'était référencé nulle part. La raison est une seule ligne :
`LTXVAudioVAELoader` lit dans **`checkpoints`** et non dans `vae` — vérifié
dans `comfy_extras/nodes_lt_audio.py`. Le fichier existait, le nœud
affichait une liste vide, et rien ne reliait les deux.

Corrigé par une entrée `checkpoints: vae/` dans `extra_model_paths.yaml`,
plutôt qu'en copiant le fichier : ce document pose déjà qu'un modèle
partagé n'a pas à exister en double.

### Deux vérifications avant le premier rendu

Le modèle distillé qu'on possède est-il seulement audio-capable ? Cela ne
se supposait pas. Deux lectures, sans allumer le GPU :

- le VAE porte bien les préfixes `audio_vae.` et `vocoder.` que le nœud
  remplace — 348 Mio, stéréo, sortie 48 kHz par extension de bande ;
- le GGUF déclare `_class_name: AVTransformer3DModel` et
  `use_audio_video_cross_attention: true`, avec 32 têtes d'attention audio
  et 128 canaux de sortie.

### Mesuré le 2026-08-27

Les deux latents partent **dans le même échantillonnage** —
`LTXVConcatAVLatent` avant, `LTXVSeparateAVLatent` après — ce qui est la
raison d'être de la chose : le son est synchrone, pas juxtaposé.

| | |
|---|---|
| Durée du rendu | 339 s pour 2,04 s (contre 281 s en vidéo seule, **+21 %**) |
| Pic VRAM | 11,07 Gio (contre 7,75 en vidéo seule) |
| Piste produite | AAC 48 kHz stéréo, 2,01 s |
| Niveau réel | moyenne −7,9 dB, crête 0,0 dB |

Le niveau a été relevé, et non déduit de la présence d'une piste : un MP4
porte volontiers une piste audio **silencieuse** et se termine avec le
code 0. La crête à 0,0 dB dit d'ailleurs que le signal sature — il faudra
l'atténuer avant montage.

### Ce que cela change

La narration posée par Piper devient un **choix** et non une nécessité.
Surtout, LTX produit ce qu'aucun TTS ne peut poser après coup : des pas
qui tombent sur l'image, une porte qui claque au bon quart de seconde, une
pluie qui suit le plan. Pour vingt et un pour cent de temps en plus, sur
une chaîne où le son d'ambiance est la moitié du travail.

Reste à mesurer : la qualité sur de la parole, et la tenue sur des plans
plus longs que deux secondes.

### Licence

Le VAE audio porte la même LTX-2.x Community License que le reste : usage
commercial autorisé **en dessous de 10 M$ de revenus annuels**, licence
payante au-delà. C'est le même filtre qui avait écarté F5-TTS, XTTS,
MusicGen et MiniMax H3 — celui-ci passe.
