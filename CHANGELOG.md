## HOS-190 (suite) — Le verdict : vingt minutes pour quatre secondes (2026-08-27)

### Trois rendus reels

LTX-2.5 Q3_K_M, 8 etapes, `res_multistep`, decodage par tuiles. Fichiers
verifies sur le disque — en-tete `ftyp`, pas seulement un succes annonce.

    512 x 288    49 images (2 s)     170 s    pic 7,98 Gio (50 %)
    768 x 432    49 images (2 s)     251 s    pic 7,59 Gio (47 %)
    704 x 1280   97 images (4 s)   1 218 s    pic 7,04 Gio (44 %)

**La VRAM n'est pas la contrainte.** Elle reste autour de 7 a 8 Gio quelle
que soit la resolution, et le pic *baisse* meme quand le format grandit :
les tuiles restent de taille fixe pendant que le reste se repartit. Sur les
15,98 Gio, la moitie dort.

**Le temps l'est, et severement.** Environ **cinq minutes de calcul par
seconde de video finie**. Un short de 30 s demande sept a huit plans, soit
deux heures et demie a trois heures. Une video longue est hors de portee :
une minute de montage couterait cinq heures.

La production locale est donc un atelier de nuit, pas un outil de
tatonnement — exactement le regime qu'une mission Hermes sait tenir.

### Le decodage par tuiles n'est pas un reglage, c'est la condition

Le premier rendu a echoue a `VAEDecode`, qui a reclame **14,58 Gio d'un seul
bloc** pour 49 images en 512 x 288, sur une carte de 15,98 dont 10,73 deja
pris par le transformeur. Le debruitage, lui, avait tourne 267 s sans
incident : le goulot n'etait pas le modele mais la sortie du VAE, qui
materialise toutes les images a la fois.

`VAEDecodeTiled` avec `temporal_size` a 16 — et non les 64 par defaut,
parce que c'est la dimension temporelle qui explose sur une video — ramene
le pic a 7,98 Gio. Le meme rendu passe alors en 170 s au lieu d'echouer
apres 267.

L'echantillonneur de VRAM a signale ce premier echec correctement : pic
15,81 Gio, soit 98,9 %, `deborde: true`. Le seuil a 98,5 % a fait son
travail.

### Deux erreurs commises en chemin

**L'encodeur.** 8,6 Go telecharges pour rien : le GGUF
`LTX-2.5-gemma4-12b-text-encoder-Q4_K_M` porte le bon nom mais sert le
moteur `engine25` du greffon Nz-Videomni pour **AviUtl2**, et son depot
precise qu'il est « incompatible avec le Gemma 4 generique ». ComfyUI-GGUF
le refuse : `general.architecture = ltxv` n'est pas dans sa `TXT_ARCH_LIST`.
Le bon fichier porte `comfy` dans son nom et se charge par le noeud natif
`CLIPLoader` en type `ltxv`.

**Le schema des echantillonneurs.** `sampler_disponible()` lisait
`champ[0]`, obtenait la chaine `"COMBO"` du schema V3, et en rendait la
premiere lettre. ComfyUI a refuse le graphe avec « sampler_name: 'C' not in
(list of length 44) ».

Les deux ont la meme forme : un nom plausible pris pour une garantie.

### Le telechargement, mesure aussi

En flux unique, le debit s'est degrade de 52 a 1,5 Mo/s avec une rupture a
51 %. Une seconde connexion ouverte au meme moment rendait **6,5 Mo/s** :
l'etranglement porte sur la connexion. Reecrit en six tranches paralleles
par `Range`, le debit est monte a **85 Mo/s** — les 14,32 Go de l'encodeur
sont passes en trois minutes.

### Verified

Suites : backend **2 083 passes, 2 ignores** ; frontend **110 passes** ;
`tsc --noEmit` propre. Trois MP4 valides sous `E:\YouTube\Generations`.

---

