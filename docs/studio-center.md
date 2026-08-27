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

`studio_image`, `studio_video`, `studio_file_attente`, `studio_rendus`
rejoignent les 71 outils que l'agent appelle déjà. L'agent compose le
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
| 4 | I2V / T2V | animation | **à trancher par la mesure** |
| 5 | TTS narration | voix off | oui — Piper trop robotique pour narrer |
| 6 | ASR mot-à-mot | sous-titres | faster-whisper présent, horodatage par mot à ajouter |
| 7 | T2M | musique, ambiance | oui, optionnel |
| 8 | Upscale + interpolation | 1080p, fluidité | oui, peu coûteux |
| 9 | VLM | relire ce qui a été généré | oui — axe `vision` déjà mesuré |

Le neuvième mérite qu'on s'y arrête. Un modèle qui *regarde* l'image
produite et dit si elle correspond à la consigne, c'est la règle de la
maison appliquée à la génération : un rendu qui se termine sans erreur
n'est pas un rendu réussi.

## Ce qui reste à mesurer

Le temps de mur d'un plan réel. Le socle et l'attention sont établis ; ce
qui ne l'est pas, c'est le produit `couches × étapes de débruitage`. Un
ordre de grandeur se calcule — une cinquantaine de blocs à 307 ms font
15 s par étape, soit quelques minutes pour huit étapes — mais ce projet ne
conclut pas sur un calcul.

*(Section complétée après le premier rendu.)*
