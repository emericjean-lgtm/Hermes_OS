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

Neuf, dont trois seulement posent une vraie question sur ce matériel.

| # | Type | Rôle | Local ? |
|---|---|---|---|
| 1 | LLM texte | script, titres, description | déjà là |
| 2 | LLM extraction | découpage en plans | déjà là — qwen3.5-9b, 100/100 |
| 3 | T2I diffusion | miniatures, plans-clés | oui |
| 4 | I2V / T2V | animation | oui — **5 min de calcul par seconde de vidéo** |
| 5 | TTS narration | voix off | oui — Piper trop robotique pour narrer |
| 6 | ASR mot-à-mot | sous-titres | faster-whisper présent, horodatage par mot à ajouter |
| 7 | T2M | musique, ambiance | oui, optionnel |
| 8 | Upscale + interpolation | 1080p, fluidité | oui, peu coûteux |
| 9 | VLM | relire ce qui a été généré | oui — axe `vision` déjà mesuré |

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
