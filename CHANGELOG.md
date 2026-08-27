## HOS-190 — Le Studio, et la carte qu'on ne peut pas partager (2026-08-27)

### Ce que la mesure a renverse

Le premier avis etait qu'une RX 6800 de 16 Gio ne ferait pas de video : le
paquet officiel de LTX-2.5 annonce « 16 Gio minimum » pour du NVFP4 sur
Blackwell, et `gfx1030` n'a ni Flash ni Memory-Efficient SDP.

Les deux moities de ce raisonnement etaient fausses, et de facons
differentes.

**La VRAM.** Les GGUF communautaires descendent le transformeur de 39 Go
bf16 a 8-22 Go. Le « minimum » officiel ne decrivait que l'emballage de
Lightricks.

**L'attention.** Le manque de Flash est reel — les deux noyaux refusent de
se charger, « not compiled for current AMD GPU architecture ». Mais ComfyUI
porte ses propres implementations, et c'est le choix d'implementation, non
la carte, qui decidait. Mesure du 27 aout a 16 384 jetons, l'ordre de
grandeur d'un plan de 5 s en 512p :

    attention_pytorch    3 226 ms   pic 20,16 Gio   deborde
    attention_basic      1 707 ms   pic 16,22 Gio   deborde
    attention_split        187 ms   pic  8,25 Gio   tient
    attention_sub_quad     307 ms   pic  4,15 Gio   tient

A 32 768 et 49 152 jetons, `split` et `sub_quad` tiennent encore, sous
10 Gio. Le format YouTube est atteignable.

Le socle, lui, etait sain depuis le debut : ROCm 10.1 natif, HIP 7.16,
**29,2 TFLOPS** en fp16 sur un matmul 8192² — environ 90 % du plafond de la
carte. Ni DirectML, ni ZLUDA, ni CPU.

### Le drapeau qui decide, et pourquoi ce n'est pas le plus rapide

`split` est 60 % plus rapide que `sub_quad`. C'est pourtant `sub_quad` qui
est retenu :

    poids Q3_K_M 10,73 + pic split    8,25 = 18,98 Gio  sur 15,98 → deborde
    poids Q3_K_M 10,73 + pic sub_quad 4,15 = 14,88 Gio  sur 15,98 → tient

Soixante pour cent plus lent en restant sur la carte vaut mieux que
dix-sept fois plus lent en passant par la RAM. Le drapeau est fige dans
`hermes-ltx.bat` avec cette raison ecrite a cote — sans quoi quelqu'un le
« corrigera » un jour vers `split`.

### Pourquoi integrer, et ce que ce n'est pas

Encastrer l'interface de ComfyUI n'atteint pas l'objectif : ce serait le
meme editeur de graphe dans la meme fenetre, du changement d'application
sans le changement de fenetre. L'agent ne manipule pas un graphe, il appelle
une API.

La vraie raison est mesuree : **les 16 Gio sont indivisibles**. Ollama tenant
gpt-oss occupe 13,21 Gio ; LTX-2.5 en Q3_K_M en reclame 10,73. Ils ne
peuvent pas coexister, et rien ne le dit — ROCm complete en memoire systeme
sans lever d'erreur. Un rendu lance pendant qu'une mission tourne ne produit
pas un echec : il produit une lenteur que personne n'attribue a la bonne
cause.

Hermes OS est le seul composant qui voit les deux runtimes.

### Ce qui a ete pose

`backend/studio/comfyui.py` — un client HTTP, et rien d'autre. Il ne compose
aucun graphe : c'est le travail de l'agent, et la regle qui prime sur tout
interdit qu'une seconde boucle s'installe.

`backend/studio/arbitrage.py` — un verrou, un dechargement, **et une
verification**. Le troisieme est le seul qui compte : Ollama rend
`success: true` des que la requete aboutit, pas quand la memoire est rendue.
Un dechargement sans effet est signale (`liberation_douteuse`) et le rendu
refuse plutot que lance.

Cinq outils MCP — `studio_state`, `studio_models`, `studio_render`,
`studio_queue`, `studio_outputs`. **76 outils au lieu de 71.**

Un Studio Center en SODIUM, avec l'onglet Graphe qui encastre ComfyUI —
il ne pose ni `X-Frame-Options` ni `frame-ancestors`.

### Trois defauts trouves en construisant

`Occupation.libere_octets` soustrayait a l'envers : les champs portent la
VRAM **libre**, qui augmente quand on decharge. Il rendait donc toujours
zero — un chiffre qui n'aurait alerte personne, puisqu'il ressemble a « rien
n'a ete libere », un etat plausible. Trouve par le test du chemin nominal.

L'unite manquait sur l'affichage de la VRAM : « 0.1 / 16.0 » sans « Gio ».
`formatGioPair` existe pour cela et tous les autres Centers l'emploient.

Et une decision annulee : supprimer le registre d'outils HOS-049. **Dix
modules en dependent**, dont `base_agent.py` et le serveur MCP. Le rayon
etait trop large pour un gain incertain.

### Le telechargement, et ce qu'il a appris

Vingt-deux gigaoctets en flux unique : 52 Mo/s au depart, puis 26, 19, 15,
12, 8, 1,5 — et une rupture a 51 %. Le profil d'un etranglement, pas d'une
panne.

Mesure : pendant que la premiere connexion rendait 1,5 Mo/s, une seconde
ouverte au meme moment rendait **6,5 Mo/s**. La limite porte sur la
connexion. Reecrit en six tranches paralleles par `Range` : **60 Mo/s**,
quarante fois mieux.

Aussi : `Lightricks/LTX-2.5` est un depot sous licence acceptee — trois des
cinq fichiers y etaient. `comfyicu/LTX-2.5` sert les memes, sans
restriction.

### Verified

Suites : backend **2 083 passes, 2 ignores** ; frontend **110 passes** ;
`tsc --noEmit` propre. Les quatre routes `/studio/*` repondent sur le
serveur en marche, et le Studio Center affiche l'etat reel de ComfyUI.

Le temps de mur d'un rendu complet reste a mesurer — le dernier fichier de
poids descend encore.

---

