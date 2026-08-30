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

