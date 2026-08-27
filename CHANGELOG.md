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

