## HOS-260 — Ce qu'un run a coute a la machine (2026-09-05)

R-6, le dernier defaut MUST HAVE de l'audit §6.1. Le registre portait les
jetons et le cout monetaire d'un run depuis HOS-221, et rien de physique :
« cette mission a-t-elle sature la carte ? » n'avait pas de reponse
conservee, alors que la telemetrie existait depuis A-15 — elle n'etait
rattachee a aucun run.

### La question qui decide de tout : que sait-on vraiment attribuer ?

La source canonique somme `GPU Process Memory` sur **tous** les
processus, et le modele vit dans le serveur Ollama, qui sert tous les runs
a la fois. Deux runs simultanes partagent le meme processus : aucun
compteur ne dit lequel a pris quoi. Le chemin agentique n'aide pas — le
sous-processus de Hermes Agent ne detient presque pas de VRAM, c'est
Ollama qui la detient pour lui.

**L'attribution exacte est donc impossible ici.** Le systeme ne pretend
pas le contraire : c'est le point de cette passe, plus que les colonnes.

### Quatre grandeurs qui ne se confondent pas

| grandeur | ce que c'est | ou |
|---|---|---|
| capacite | ce que la carte porte au total | `ResourceManager` |
| besoin declare | l'empreinte du modele, `config/models.yaml` | estimation |
| **reservation** | ce que **ce run** a fait retenir | `vram_reservee_octets` |
| **occupation observee** | ce que la **machine** portait | `vram_machine_*` |

Une reservation est une promesse, pas une mesure. Une occupation machine
est une mesure, mais pas celle du run. `exclusif` dit si l'ecart entre le
debut et le pic est attribuable — et sans lui, il ne l'est pas.

### Mesure sur la vraie carte

    run 1, succes                debut 1,148 Gio  pic 8,231 Gio  exclusif=True
    run 2, echec du runtime      debut 8,231 Gio  pic 8,231 Gio  exclusif=True
    runs 3 et 4, en meme temps                    pic 8,231 Gio  exclusif=False

Les deux runs concurrents voient le meme 8,231 Gio et **aucun des deux**
ne se le voit attribuer. C'est tout l'objet de `exclusif`, et c'est la
difference entre une donnee moins precise mais honnete et une donnee
precise et fausse.

### Ou la mesure est prise, et pourquoi seulement la

Deux points : avant l'admission — donc avant que ce run ne pousse quoi que
ce soit — et dans le `finally` d'`execute`, avant la liberation. Aucun fil
de sondage n'est ouvert pour R-6.

Consequence assumee et ecrite dans le nom : `vram_machine_pic_octets` est
le plus haut des relevés **reellement pris**, donc un **minorant** du vrai
pic. Le nommer `vram_peak_bytes` aurait laisse croire l'inverse.

Le releve final est dans le `finally` parce que c'est le seul endroit que
succes, exception, delai depasse, annulation et repli cloud traversent
tous — et un run en echec est justement celui dont on veut savoir ce que
la carte portait. `resources_used` ne convenait pas : `mission_executor`
ne l'ecrit qu'au retour normal, et le chemin `RuntimeUnavailableError`
sort avant.

### Comptabilite passive

`consommation.py` lit `ResourceManager` et ne lui demande rien : ni
`can_allocate`, ni `reserve_resources`, ni `release_resources`. Et
reciproquement, aucun module d'admission n'importe le registre. Deux
gardes structurelles tiennent les deux sens : refermer cette boucle
ferait de la trace une entree de decision, ce que R-6 s'interdit.

### Persistance

Quatre colonnes nullables sur la table `runs` existante, par le mecanisme
additif de HOS-240 — `CREATE TABLE IF NOT EXISTS` ne fait rien sur une
base deja la, et l'`INSERT` nomme d'`ouvrir()` y echouerait : plus aucun
run ne s'ouvrirait. Une correction d'observabilite aurait casse
l'execution ; c'est deja arrive.

`NULL` se lit « non mesure », jamais « zero consomme ». `mesurer()` est
separee de `constater()` pour cette raison precise : `constater` filtre
ses valeurs sur `if v` et ferait disparaitre un `0` octet — une carte au
repos — et un `exclusif=False`, qui est un fait.

L'unite est dans le nom de chaque colonne. « memory » ou « GiB » sans
definition est la maniere habituelle de perdre un facteur 1024 trois mois
plus tard.

### Deux tests a moi qui ne prouvaient pas ce qu'ils annoncaient

**Le test de concurrence etait instable** — rouge une fois sur six,
mesure. Il exigeait que les deux taches se declarent non exclusives ; or
le releve final precede la liberation, et si l'autre a deja libere, une
tache ne voit plus personne et se declare seule — ce qui est exact pour
l'instant ou elle a regarde. Exiger `False` des deux, c'est exiger une
coincidence, pas une propriete. Reecrit avec une barriere **dans** le
`chat` (donc apres l'admission) et des tenues asymetriques : la tache
courte releve forcement pendant que la longue detient sa reservation.
Dix executions, dix vertes.

**Le test d'annulation testait autre chose que son nom.** Il affirmait
qu'une `CancelledError` descend de `BaseException` et n'est retenue que
par le `finally`. Mesure : sur ce chemin, elle ressort d'`execute` en
`RuntimeUnavailableError` — elle est convertie avant. La mutation « plus
de capture sur annulation » ne faisait donc rougir aucun test, parce
qu'il n'y avait rien de distinct a retirer. Le contrat de conversion est
desormais ecrit et verifie, et un second test leve une `KeyboardInterrupt`
— une vraie `BaseException` qui traverse tous les gestionnaires — pour
prouver ce que le `finally` retient et qu'un `except Exception` perdrait.

### Les mutations

Dix, dix rouges : enregistrement supprime (9), mesure prise sur `/api/ps`
(14), gibioctets sous un nom d'octets (13), « non mesure » devenu zero
(1), le run s'attribuant toute la carte (5), persistance supprimee (7),
admission consultant le registre (1), capture retiree sur exception (5),
capture quittant le `finally` pour un `except Exception` (1), seconde
autorite de mesure (1).

### Un defaut trouve par la mesure, laisse ouvert

R-6 a rendu visible ce qu'il devait rendre visible. Carte videe entre
chaque, un modele a la fois :

    modele                 declare   occupation   ratio
    lfm2.5-2.6b-125k      2,05 Gio     4,33 Gio    2,1x
    gemma4-12b-256k      12,24 Gio    12,24 Gio    1,0x

L'empreinte declaree de `config/models.yaml` est exacte pour l'un et
**deux fois trop basse** pour l'autre. C'est la table que R-3 utilise pour
deriver la capacite : si la sous-declaration touche aussi les roles
lourds, `places_disponibles` sur-estime. Deux points ne suffisent pas a
l'affirmer. Consigne **A-18**, non corrige.

### Un second, expose et non cree

Le couple `test_runs_perdus.py` + `test_registre_missions.py` lance a la
main devient rouge avec cette passe et etait vert en `28a7ad7` — verifie
dans un worktree, pas deduit.

Mecanisme trace : `_RegistreMissions.__len__` **hydrate le cache depuis le
magasin durable au milieu du test**, et
`test_au_dela_la_plus_ancienne_terminee_quitte_le_cache` affirme ensuite
le contenu de ce cache. Or les missions ecrites par le test precedent du
meme fichier portent toutes le **meme `created_at` a la microseconde
pres** : leur ordre de relecture est une egalite tranchee par SQLite. Le
test dependait donc d'un ordre que rien ne garantit ; cette passe a
deplace le tirage, elle ne l'a pas cree.

Les commandes du projet restent vertes — `pytest -q` et `pytest -m lent`,
avant comme apres. Le defaut n'apparait que dans un ordre de fichiers
compose a la main. Consigne **A-19**, non corrige : reparer ce test
demande de decider si `__len__` a le droit d'hydrater, ce qui est une
question sur `_RegistreMissions` et non sur R-6.

## HOS-259 — Combien de taches, et qui le sait (2026-09-05)

R-3 et R-4, les deux derniers defauts MUST HAVE de l'audit §6.1 hors R-6.
Meme defaut vu de deux cotes : la concurrence etait decidee sans regarder
la machine, et decidee deux fois.

### R-3 — une constante n'est pas une capacite

`mission_max_parallel_tasks = 2` ne dit pas « la machine porte deux
taches » : il dit « quelqu'un a ecrit 2 ». Mesure : la meme constante
valait pour une carte pleine (0 place reelle) et pour une carte de 48 Gio
(7 places). Elle ne suivait rien.

Avec l'empreinte **relevee** du role `reasoning` — 13,68 Gio,
`config/models.yaml`, la meme table que l'admission utilise deja sous le
nom `_vram_gb_for` — la carte de 15,98 Gio en tient **une**. Le graphe en
lancait deux. §6.2 empechait bien la carte d'etre sur-engagee ; ce qui
restait, mesure, etait ceci :

    t1   4.2 s  REFUSEE : no VRAM admission for 'qwen3.6-35b-128k'
    t2   4.2 s  REFUSEE : no VRAM admission for 'qwen3.6-35b-128k'

Le second noeud occupait un fil, brulait son attente d'admission, puis
echouait. Le degat n'etait pas la VRAM — elle etait protegee — mais des
noeuds echoues pour une raison qui n'a rien a voir avec leur travail.

`GraphExecutor` demande desormais la borne a `ResourceManager`
(`places_disponibles`), a chaque etape, et ne la met pas en cache : une
capacite lue une fois au demarrage serait une constante de plus. Mesure
apres correction, empreinte 13,68 Gio :

    carte 15,98 Gio, 0,0 occupes -> 1 place
    carte 15,98 Gio, 0,9 occupes -> 0 place
    carte 48,00 Gio              -> 3 places
    carte 80,00 Gio              -> 5 places
    occupation non mesuree       -> 0 place   (A-15 traverse)

`places_disponibles` ne refait aucun calcul de capacite : la politique
etant lineaire en octets demandes, elle pose a `can_allocate` la question
« n taches tiennent-elles » en demandant `n x octets`. Une seule verite,
interrogee autrement — et les reservations actives comptent, comme en
§6.2.

**Jamais moins d'une place.** Une capacite nulle ne doit pas figer la
machine : c'est l'admission de `RealTaskExecutor` qui refuse alors la
tache, avec sa raison, la ou la taille reelle du modele est connue. Le
portillon ne refuse rien.

### R-4 — la borne etait celle d'un appel

`execute_step` ouvrait un `ThreadPoolExecutor` par appel. Le conteneur
n'a pourtant qu'**un** `GraphExecutor`. Deux missions concurrentes,
mesure avant correction :

    _max_parallel par mission : 2
    pic de noeuds simultanes  : 4

Quatre noeuds pour une borne de deux, sans qu'aucune ligne ne soit
fausse : chaque mission respectait sa limite, et les limites
s'additionnaient.

Le portillon est porte par l'instance de `GraphExecutor`, donc partage
par toutes les missions. C'est ce partage, et lui seul, qui empeche deux
decisions locales de s'additionner. Il enveloppe **les deux** chemins
d'`execute_step` — le pool et l'execution directe : n'en garder qu'un
laisserait deux missions a un seul noeud chacune tourner cote a cote sans
que rien ne les compte, ce qui est R-4 avec un noeud de moins.

### Ce que le portillon n'est pas

Il ne connait aucune capacite et n'en calcule aucune : la limite lui est
**passee**. Il ne classe pas, ne priorise pas, ne prempte pas, ne
reordonne pas. Il n'autorise rien non plus : le franchir ne donne aucun
droit sur la carte ; la reservation reste seule a en donner (§6.2), et
elle peut refuser apres.

Un ordonnanceur decide *qui* passe et *quand*. Celui-ci decide seulement
*combien a la fois*, sur un chiffre qu'il ne possede pas. Aucune
autorite nouvelle : le RAL choisit, `ResourceManager` sait, le graphe
repartit, `Mission` borne le temps, `QuotaBroker` le fournisseur.

### Un ecart de semantique trouve en chemin

Les deux chemins d'`execute_step` traitaient differemment un
`execute_node` qui **leve** : le pool recueillait l'exception dans
`future.result()` et notait le noeud en echec, le chemin sequentiel la
laissait remonter et emportait la marche du graphe. Deux semantiques
d'echec pour le meme rappel, selon un nombre de places — c'est-a-dire
selon la VRAM libre. Homogeneisees ici, parce que le portillon passe
desormais par les deux.

### Une mutation qui a demasque le compteur de mutations

La mutation « ne jamais rendre la place » a d'abord ete rapportee
**verte**. Elle ne l'etait pas : les tests attendaient le delai du
portillon — 1200 s par defaut — et le delai de garde de pytest tuait la
session sans imprimer de resume, que le compteur lisait « 0 rouge ».

Deux corrections : les tests bornent explicitement ce delai a 3 s, et une
garde directe verifie le compteur de places sans aucune attente — sortie
normale, sortie par exception, entree refusee. Elle echoue desormais en
3,2 s avec un message. Une garde qui pend n'est pas une garde (HOS-112).

C'est le quatrieme garde-fou de cette serie de passes dont une mutation
revele qu'il ne gardait pas ce qu'on croyait ; cette fois, c'est
l'instrument de mesure lui-meme qui mentait.

### Ce qui reste ouvert

R-6 (comptabilite VRAM/CPU par Run) et A-17. `Mission.priority` reste lu
par personne (A-14) : le portillon ne l'utilise pas, et c'est
deliberement hors perimetre — la priorite est du ressort d'un
ordonnanceur, que cette passe s'interdit d'introduire.

## HOS-258 — Ce que mesure la source d'admission (2026-09-05)

A-15, decouvert en fermant §6.2. `GPUMonitor` essayait `rocm-smi`, puis
`nvidia-smi`, puis **retombait sur `/api/ps`**. Sur cette machine —
Windows, AMD RX 6800 — les deux premiers n'existent pas : le repli etait
le chemin **normal** de l'admission, et il repondait sans erreur.

Or les deux ne repondent pas a la meme question. `rocm-smi` dit ce qui
est occupe sur la carte ; `/api/ps` dit ce que **pesent les modeles
residents d'Ollama** — sans cache KV, sans tampons de calcul, sans un
octet de ce que tient un autre processus.

### La mesure, trois etats de charge, meme carte de 15,984 Gio

    etat                     /api/ps    occupation reelle    ecart
    aucun modele              0,000            1,314        +1,314
    qwen3.6-35b resident     12,737           14,954        +2,216
    meme modele, cache KV    12,737           15,115        +2,377

L'ecart va toujours dans le meme sens et il **grandit** : `/api/ps` est
reste fige a 12,737 pendant que l'occupation montait de 161 Mio — ce qui
montait etait le cache KV, qu'il ne voit pas. Une marge forfaitaire
n'aurait donc pas suffi.

### Ce que cela donnait sur le vrai chemin

Rejoue sur `ResourceManager.can_allocate`, a l'etat 3, ou il restait
0,870 Gio :

    demande            /api/ps    occupation reelle
    1,0 Gio             ADMIS          refuse
    1,5 Gio             ADMIS          refuse
    2,0 Gio            refuse          refuse

Le modele de 1,5 Gio admis se serait charge sur 0,87 Gio libres : il
aurait deborde en memoire systeme, repondu dix fois plus lentement, et
**sans erreur**. C'est exactement la classe de defaut que `CLAUDE.md`
decrit — un succes qui n'en est pas un.

### La decision

Source canonique de l'admission : l'**occupation physique de la
machine**, definie une seule fois dans
`backend/runtime/resources/vram_physique.py` — somme de
`\GPU Process Memory(*)\Dedicated Usage` sur tous les processus. Meme
semantique que `rocm-smi`, qui reste prioritaire la ou il existe.

`/api/ps` garde son role : dire quels modeles sont residents et ce qu'ils
pesent. Il n'est plus une source de VRAM physique nulle part.

Quand aucune sonde ne repond, le moniteur ne rend plus de chiffre. Il
distingue deux etats que `available=False, total=0` confondait :

- **pas de carte** — aucune contrainte VRAM a faire respecter, admission
  inchangee, ce qui est correct sur une machine sans GPU ;
- **carte presente, occupation illisible** — `occupation_mesuree=False`,
  et la politique **refuse**. Aucune politique nouvelle : le refus
  emprunte le mecanisme existant, `_check_vram_admission` attend
  `vram_wait_s` puis leve `RuntimeUnavailableError`, et une sonde qui
  revient pendant l'attente debloque la tache d'elle-meme.

### Le drapeau devait remonter, sinon il deplacait la confusion

Une carte non mesuree porte `vram_used_bytes: 0`. Sans rien de plus, le
Cockpit l'aurait affichee « 0,0 / 16,0 Gio, 0 % » — soit une carte au
repos, la meme erreur un etage plus haut. `occupation_mesuree` entre donc
dans `get_status()`, dans le type du frontend, et dans trois aides
partagees (`vramOccupee`, `vramLibre`, `vramPourcent`) que les huit
surfaces d'affichage appellent. `formatGio(null)` rendait deja « — ».

`check_thresholds` recevait le meme zero et concluait « 0 %, sain ». Une
surveillance qui rassure sans avoir regarde est pire que pas de
surveillance : les seuils sont sautes quand l'occupation n'est pas
mesuree.

### Une affirmation de §6.2 qui ne se reproduit pas

§6.2 chiffrait la sous-declaration du compteur **par adaptateur** a un
facteur trois : 3,99 contre 12,70 Gio. **Remesure pendant A-15, carte
portant un modele de 12,74 Gio, sur trois releves espaces et stables :**

    GPU Adapter Memory\Dedicated Usage  -> 14,669 Gio
    GPU Process Memory\Dedicated Usage  -> 15,115 Gio

Soit 0,445 Gio, 2,9 %. La sonde qui avait produit le 3,99 n'a pas ete
conservee et n'est plus auditable ; le chiffre est donc **retire** du
CHANGELOG, du code et des tests plutot que repete. Ce qui reste mesure :
l'ecart existe, il va toujours dans le meme sens, et le choix du compteur
par processus ne change pas. Son ampleur annoncee, si.

### Ce que cela coute

1,60 s par mesure reelle contre 0,02 s pour `/api/ps` — PowerShell est
demarre a chaque fois. Le cache de 2 s du moniteur absorbe les appels
rapproches : cinq `poll()` de suite coutent 1,60 s au total. Une tache
vit entre 60 et 900 s ; c'est le bon echange.

### Ce qui n'est pas ferme

Sur Linux sans `rocm-smi`, aucune sonde ne repond et le registre Windows
n'existe pas : l'etat est « pas de carte detectable », donc admission
sans contrainte. Le kernel AMD publie pourtant
`/sys/class/drm/card*/device/mem_info_vram_used`, de meme semantique.
Rien ici ne permet de l'exercer, et ecrire une sonde non mesuree serait
reproduire la faute que cette passe corrige. Consigne **A-16**.

### Un rouge qui ne vient pas d'ici

La suite complete (`pytest -m ""`) n'est pas verte, et ne l'etait pas non
plus avant. `tests/integration/test_assembly.py::TestEventWiring::
test_no_real_subsystem_event_is_dropped` lance un objectif autonome reel
et attend qu'un noeud engage se termine ; le delai de garde global est de
60 s (`pytest.ini`, HOS-112).

Mesure, GPU au repos, aucun modele resident, meme test lance seul :
il depasse le delai **au commit `03f4f96` comme apres A-15**, avec des
piles identiques ligne pour ligne — le fil est bloque dans `_run_coro`
sur une inference, pas dans l'admission. Un worktree sur `03f4f96` a servi
a le verifier plutot qu'une deduction.

Le rapport §6.2 annoncait « suite complete 5979 passed » : c'etait vrai ce
jour-la, et ca ne se reproduit pas — ce test depend de quel modele le
routeur choisit et de sa vitesse. Consigne **A-17**, hors perimetre.

Ce qui est vert : boucle courte 5740 / 0, et suite lente 267 / 0 en
mettant ce seul test de cote.

### Les mutations

Huit, huit rouges : `/api/ps` remis en source (4), fail-closed supprime
(3), priorite inversee (2), carte non lue presentee comme mesuree (2),
`ResourceManager` contourne par l'agent (3), deuxieme autorite de mesure
(1), compteur par adaptateur (4), source canonique restreinte a un
processus (1).

Deux tests de §6.2 affirmaient l'ancien contrat — « le fichier
`monitoring/gpu_monitor.py` contient la chaine `GPU Process Memory(*)` ».
La requete ayant demenage dans la source canonique, ils sont **reecrits
sur la propriete** — quel compteur est interroge, et par combien de
definitions — dans la passe meme qui change le contrat, parce que la
reecriture est verifiable independamment : la meme propriete est gardee
deux fois, dans deux fichiers, et les mutations G et H la font rougir.

## HOS-257 — Verifier n'est pas reserver (2026-09-04)

§6.2. Trois defauts MUST HAVE de l'audit §6.1, fermes ensemble parce
qu'ils sont le meme defaut vu de trois cotes : une decision de ressource
prise sur une mesure incomplete.

### R-1 — le chemin le plus lourd etait le seul non controle

`task_executor` portait `if not use_cloud and runtime_id !=
"hermes-agent"`. L'exception visait precisement le consommateur le plus
lourd : un processus complet qui charge un modele et enchaine jusqu'a
douze tours sur la meme carte. Une simple completion avait une admission,
un agent n'en avait pas — et l'agent est le chemin **normal** d'une
mission liee a un workspace.

La porte est posee la ou les deux harnais convergent :
`_hermes_agent_chat_for` rend une fermeture qui couvre le jetable
(`hermes_agent_cli`) comme le persistant (ACP). Une porte par adaptateur
en aurait fait deux, et le troisieme serait ne sans.

### R-2 / A-13 — le verrou n'etait pas le probleme

`reserve_resources` existait sans appelant hors d'une route HTTP. Le
brancher tel quel n'aurait **rien regle** : la decision ignorait
`self._allocations`. Mesure avant correction, carte simulee de 16 Gio
dont 2 deja pris :

    reserve(8 Gio) -> True
    reserve(8 Gio) -> True        18 Gio promis sur 16

Le verrou serialisait bien deux decisions — mais chacune lisait un
compteur physique que la premiere n'avait pas fait bouger, un modele
reserve n'occupant la VRAM qu'une fois **charge**. Le compte des
reservations est donc entre dans la decision, au meme endroit qu'elle.

Consequence assumee : une fois le modele charge, sa consommation est
comptee deux fois — compteur physique **et** reservation — jusqu'a la
liberation. On refuse parfois une allocation qui aurait tenu, jamais
l'inverse. Meme prudence que `_check_vram_admission` : « occasionally
waiting when the model was already loaded, never the other way around ».

La liberation est dans un `finally` : succes, exception, delai depasse,
annulation, repli cloud. Une reservation qui survit a sa tache condamne
la capacite, et rien ne viendrait la reprendre — le gestionnaire n'a pas
d'expiration.

### A-12 — et le rapport §6.1 avait la conclusion a l'envers

L'audit §6.1 affirmait que l'admission lisait la bonne source et le
Cockpit la mauvaise. **C'etait l'inverse de ce que la mesure dit**, et je
l'avais deduit du fait que l'admission refusait, sans verifier ce que
chacune lisait.

Mesure, meme instant, meme carte, un modele de 11,9 Gio resident :

    GPU Adapter Memory\Dedicated Usage   ->  3,99 Gio   <- le Cockpit
    GPU Process Memory\Dedicated Usage   -> 12,70 Gio   <- la verite
    /api/ps (somme size_vram)            -> 12,80 Gio   <- l'admission

> **Amendement du 2026-09-05 (HOS-258).** Le releve par adaptateur ne se
> reproduit pas. Remesure trois fois pendant A-15, carte portant un modele
> de 12,74 Gio : adaptateur 14,669 Gio, processus 15,115 — 0,445 Gio, soit
> 2,9 %, et non un facteur trois. La sonde d'origine n'a pas ete conservee
> et n'est plus auditable. Le choix du compteur par processus reste juste ;
> le chiffre qui le justifiait ici est faux et ne doit pas etre repris.

Le compteur **par adaptateur** sous-declarait d'un facteur trois, dans le
sens dangereux — celui qui fait croire qu'il reste de la place. Le
compteur **par processus** est celui que `model_bench.gpu_dedicated_bytes`
utilise deja et que `CLAUDE.md` designe comme la seule occupation reelle.
Le moniteur systeme le lit desormais : la carte affiche 14,08 / 17,16 Gio
la ou elle annoncait 4,28.

`/api/ps` reste ce qu'il est — les poids des modeles residents, sans le
cache KV ni les tampons — et garde son role d'information sur les modeles
charges. Il n'est pas presente comme une mesure de la VRAM physique.

### Ce qui n'est pas ferme

La source de l'**admission** reste `/api/ps` quand `rocm-smi` est absent,
ce qui est le cas sur cette machine. C'est une mesure des poids seuls :
elle sous-estime par construction. Canoniser une source demande de
decider ce que `ResourceManager` lit quand `rocm-smi` manque, et cette
decision n'a pas ete prise ici. Consigne **A-15**.

### Les mutations, dont une qui a demasque une assertion morte

Cinq mutations, cinq rouges. La premiere n'a d'abord fait rougir que deux
tests sur trois : la garde structurelle cherchait
`runtime_id != "hermes-agent"` avec des guillemets doubles dans un texte
produit par `ast.unparse`, **qui les normalise en simples**. L'assertion
ne pouvait donc jamais correspondre. Corrigee, la mutation la fait rougir.

C'est le troisieme garde-fou de cette serie de passes dont une mutation
revele qu'il ne gardait rien. Le motif est constant : une assertion
ecrite sur une **forme** plutot que sur une propriete.

## HOS-256 — Deux protections declarees, jamais appelees (2026-09-04)

Fermeture de A-2, second defaut P1 de l'audit global J25.

### Le constat, retrace de bout en bout

`security/derive_workspace.py` (HOS-217) et
`security/surveillance_flux.py` (HOS-218) etaient implementes, testes, et
declares ✅ **Fait** au ROADMAP. Tracage complet — imports absolus et
relatifs, instanciations, appels, decorateurs, chaines de caracteres,
`getattr`, imports dynamiques, hooks de demarrage, injections, routes,
scripts d'operateur : **zero reference de production**. Chaque module
n'etait cite que par son propre fichier de test.

Les quelques occurrences de production que le premier tracage remontait —
`comparer`, `resume`, `enregistrer`, `relire`, `Ecart`, `Etat`, `REPORT` —
sont toutes des **homonymes** : `git_ref.py` definit son propre `Ecart`,
`maj/sante.py` son propre `Etat`, `workspace_models.py` a `REPORT` comme
membre d'enumeration. Aucun n'importe les modules de securite. Verifie un
par un plutot que suppose.

Ce n'etaient pas des protections. C'etait du code.

### Ce que la mesure a montre de pire

**HOS-218.** `hermes_agent_cli` lance le sous-processus avec
`os.environ.copy()` — **tout** l'environnement du parent, chaque secret de
la machine — plus un `OPENAI_API_KEY` explicite. Sa sortie etait decodee
et analysee pour en extraire un identifiant de session, et rien n'y
cherchait de secret. L'exposition que le canary devait detecter etait donc
maximale, et la detection absente.

**HOS-217.** Ni Aegis ni `file_tools` ne traitent specialement les dix
fichiers gouvernants. La liste blanche d'Aegis accorde la racine du
projet, et `CLAUDE.md`, `.mcp.json`, `.claude/hooks/` sont dedans.
`_est_protege` lit `.hermes/proteges.txt` — une liste **declarative**, qui
vit dans le workspace, qu'un agent peut donc reecrire, et dont la
docstring dit elle-meme qu'elle « evite une perte » et « n'est pas une
frontiere de securite ».

Les deux invariants etaient donc reels **et** non couverts. Cas A des
deux cotes : on branche.

### Ou chaque controle vit, et pourquoi la

**HOS-218 → les lanceurs d'agent.** Le temoin est plante dans
l'environnement du sous-processus et la sortie est examinee au retour.
Poser cela plus haut — dans l'executeur de tache — laisserait sans
surveillance un lanceur ajoute demain.

Le garde-fou structurel a d'ailleurs trouve **un second lanceur** avant
qu'on declare quoi que ce soit : le harnais persistant de HOS-137
(`hermes_agent_acp`) lance le meme agent, garde ouvert entre les taches,
avec `{**os.environ}`. Il porte desormais la meme surveillance — une par
session, pour que le report de 512 caracteres traverse les tours et
attrape un secret coupe en deux entre deux lignes.

La surveillance ne tue rien : le module l'a toujours dit, il rapporte et
l'appelant tranche. Ce qu'on empeche est que le resultat **serve** — un
secret recrache entrerait sinon dans le Run Ledger, dans le relais de
contexte et dans le prompt suivant. La fuite se propagerait par les
mecanismes memes qui servent a tracer.

**HOS-217 → la couture d'instantane de mission.** `_snapshot_workspace`
prend deja une empreinte au demarrage et `_verify_workspace` la confronte
a l'arrivee. La derive de gouvernance est la meme question posee sur une
autre liste de fichiers ; la poser ailleurs aurait cree un second moment
de mesure la ou il en existe un.

**Aucune politique n'est inventee.** Le resultat entre dans le verdict de
verification, qui a deja ses consommateurs — `mission.metadata`,
`mission.unverified`, `_suggest_retry`. Le module demandait exactement
cela : mesurer, et laisser quelqu'un d'autre trancher.

Un `None` signifie « non mesure », un `derive: false` signifie « mesure,
rien n'a bouge ». Confondre les deux ferait passer une absence de mesure
pour une absence de derive — la regle tri-etat de HOS-222 appliquee ici.

### Deux mutations qui n'ont pas rougi, et ce qu'elles ont appris

Six mutations posees. Deux sont d'abord restees vertes, et c'etaient les
tests qui avaient tort :

* retirer l'examen de la sortie en gardant `alerte = None` conservait la
  **forme** que le test verifiait — un `if` sur `alerte` avec un `raise`.
  La forme sans l'appel ne prouve rien ;
* retirer le releve de la ligne de base laissait tout vert parce que les
  tests appelaient `_relever_les_gouvernants` eux-memes au lieu de passer
  par `start_mission`. Un test qui appelle le garde-fou a la place du
  produit ne prouve pas que le produit l'appelle.

Les deux tests ont ete renforces, pas les assertions affaiblies. Apres
correction, les six mutations rougissent.

### Statut documentaire

Le ROADMAP disait ✅ **Fait** pour les deux depuis leur ecriture. C'etait
vrai du code et faux du systeme. Les entrees portent desormais la date de
branchement et l'endroit ou le controle vit, parce que « fait » sans « et
appele » est precisement ce que A-2 a coute.

## HOS-255 — Le goulet cloud n'etait pas le seul passage (2026-09-04)

Fermeture de A-1, le premier des deux defauts P1 de l'audit global J25.

### Ce que le commentaire affirmait, et ce que la mesure a dit

`_make_cloud_chat` examine bien avant d'envoyer, et son commentaire
disait : « c'est le seul passage par lequel un prompt part chez un
tiers ». Faux, mesure :

    base_agent.py:279        self._cloud_client.chat_events(model, messages, …)
    task_decomposer.py:489   self._cloud_client.chat_events(model, messages, …)
    grep -c pare_feu  ->  0  dans les deux fichiers

HOS-066C a livre un repli de resilience — tente quand le flux local
echoue avant d'avoir rendu un seul morceau — et il precede HOS-227
d'assez loin pour n'avoir jamais ete route a travers lui. Le declencheur
est une panne d'Ollama : sur ce materiel, une condition de routine. La
fuite que HOS-227 decrit dans sa propre docstring — le chemin absolu du
workspace, donc le nom de l'utilisateur et celui de son client —
repartait par la, non filtree.

### La cartographie avant de corriger

L'audit signalait deux lignes. Les tracer toutes en a montre **quatre**
fichiers qui parlent a OpenRouter :

| fichier | ce qu'il envoie | verdict |
|---|---|---|
| `connectors/openrouter_client.py` | tout | le seul wrapper |
| `ral/adapters/openrouter.py` | construit ce meme client | couvert |
| `model_intelligence/benchmark_scheduler.py` | ses propres prompts **constants** | rien a examiner |
| `model_intelligence/cloud_catalog.py` | `GET /models`, credits | n'envoie aucun message |

Corriger les deux lignes signalees aurait laisse la question ouverte pour
la suivante.

### Pourquoi la garde est dans le client

Router les deux replis vers `_make_cloud_chat` etait le premier reflexe.
Il ne tient pas : **ce goulet est non-streaming** et rend une reponse
complete, alors que `BaseAgent` diffuse. L'y forcer aurait fait arriver
chaque reponse d'un bloc — une regression fonctionnelle pour fermer un
trou de securite.

La garde vit donc la ou est la socket : `OpenRouterClient.chat` et
`chat_events`, les deux seules sorties de la seule classe qui parle a
OpenRouter. `chat_stream` delegue a `chat_events` et en herite. Tout
appelant present et futur y passe **par construction**, sans avoir a le
savoir.

**Aucun second pare-feu** : c'est le meme `pare_feu.examiner`, la meme et
unique autorite. Le goulet garde son role entier — publication de la
decision, courtier, quota, disjoncteur — et rien de la logique de quota
n'a bouge. Le double examen est mesure idempotent : un texte deja
caviarde rend `AUTORISE`, sans constat et sans modification.

Un refus leve `OpenRouterUnavailableError`, deja comprise par tous les
appelants comme « replie-toi sur le local ». C'est exactement ce qu'il
faut faire quand le pare-feu refuse : le travail se fait, rien ne sort.

### Le garde-fou, structurel

Deux tests « le pare-feu a ete appele » n'auraient pas attrape A-1 : le
defaut etait un **troisieme chemin** que personne n'avait pense a tester.
La garde est donc une liste blanche de fichiers autorises a parler a
OpenRouter, chacun avec sa raison ecrite. Un nouveau chemin la fait
rougir tant qu'il n'y est pas ajoute delibarement.

Mutations : filtre retire de `chat_events` -> 5 rouges ; retire de
`chat()` -> 6 rouges ; un appel direct rouvert dans `base_agent` -> la
garde structurelle rougit en nommant le fichier.

### Un defaut de detection, trouve en chemin et **non corrige**

Le pare-feu reconnait `sk-…` comme secret et **ignore `sk-or-v1-…`**, le
format de cle d'OpenRouter lui-meme :

    cle openrouter  -> autorise   aucun constat
    cle openai      -> refuse     secret
    chemin windows  -> caviarde   interne

C'est un defaut de **detection**, distinct de A-1 qui etait un defaut de
**routage**. Le fermer demande de toucher aux motifs, ce qui peut
produire des faux positifs bloquant des envois legitimes : cela merite sa
propre passe. Consigne comme A-10. Fermer A-1 ne signifie donc pas que le
pare-feu voit tout — seulement qu'on ne peut plus le contourner.

## HOS-254 — Deux evenements que le Cockpit ne pouvait pas filtrer (2026-09-04)

Passe 24, fermeture des ecarts releves par l'audit de consolidation.

### Le defaut, et pourquoi le test de la passe 20 l'avait manque

`execution.retry` et `execution.budget_depasse` sont publies par
`mission_executor` et n'etaient dans aucun catalogue. Depuis HOS-066B le
hub delivre un topic inconnu en avertissant plutot que de le jeter : rien
n'etait perdu, mais **tout abonne qui filtre par type ne les voyait
jamais** — precisement les deux signaux qu'un operateur cherche quand une
mission se comporte mal, la reprise et le budget atteint.

Le test de cablage de HOS-252 aurait du les trouver. Il ne visitait que la
**trace nominale** : ces deux topics ne se produisent que sur des chemins
d'exception. Un test de cablage qui ne visite qu'un chemin ne cable qu'un
chemin.

La verification de declaration est donc parametree sur quatre chemins
reels — nominal, echec/reprise, annulation, budget — et la liste `CHEMINS`
est desormais la vraie assertion : y ajouter un chemin qui publie un topic
non catalogue rend le test rouge sans qu'on ait a le prevoir.

Le chemin du budget passe par `MissionExecutor.prepare/execute_task`,
c'est-a-dire le chemin de production de `POST /execution/start` ; la seule
chose de test est la **valeur** du budget. Rien n'est publie
artificiellement : c'est `_refuser_pour_budget` qui emet.

Un second test garde le garde : si l'un des deux topics cessait d'etre
emis, le test parametre resterait vert — il ne verifie que la declaration
de ce qu'il voit.

### Mutations

- `execution.retry` retire du catalogue → 1 rouge, sur le chemin echec ;
- `execution.budget_depasse` retire → 1 rouge, sur le chemin budget ;
- les chemins d'exception retires de `CHEMINS`, **et** les deux topics
  retires du catalogue → **8 verts**. C'est l'angle mort de la passe 20,
  reproduit a la demande.

### Un commentaire qui contredisait son propre fichier

`mission/routes.py` affirmait encore que « la persistance reste a faire :
au redemarrage la liste est vide », douze lignes au-dessus d'une docstring
disant que `MagasinMissions` est la source de verite. HOS-245 avait rendu
durable l'existence d'une mission, HOS-252 son etat. Le premier des deux
textes est celui qu'un lecteur rencontre — et c'est ce genre d'ecart qui a
fait batir une passe entiere sur un constat faux en passe 18.

### `_memory_.db`

Retire du depot, apres avoir etabli les faits plutot que de les supposer :

- ajoute par `d5f4794`, avant HOS-215 ;
- **deja migre** : le fichier identique (meme sha256, 45 056 octets) vit
  dans la racine d'etat, sous `memoire/` ;
- aucune table metier n'a de ligne — `goals`, `sessions`, `events`,
  `metrics` sont vides ; il reste une table nommee `test` ;
- aucun test n'en depend, aucune fixture ne le charge ;
- la documentation ne le cite qu'au passe, comme exemple de ce qui vivait
  dans le depot ;
- `scripts/migrer_etat.py` le nomme dans sa table de demenagement et
  **saute une source absente** — verifie en le relancant.

L'entree du script reste : elle sert aux copies de travail anterieures a
HOS-215, qui portent encore le fichier.

En passe 23 j'avais ecrit « aucun code ne le nomme ». C'etait faux : je
n'avais cherche que dans `backend/` et `frontend/src`. Le script de
migration le nommait.

### Ce qui n'a pas ete touche

`data/db/hermes.db`, 17,7 Mio, non suivi et ignore par git, vestige
d'avant HOS-215 : ce sont des donnees d'utilisateur, et leur sort est une
decision separee.

## HOS-253 — Une mission peut disparaitre ; ce qu'elle a fait, non (2026-09-04)

Passe 22, implementation de T-21. La plus petite de la serie, et
volontairement : **aucun code de production nouveau**.

### La question, et sa reponse mesuree

La passe 19 a supprime deux missions de diagnostic. Leurs huit runs sont
restes, dont un `en_cours` : un journal dont le sujet a disparu. Que
signifie un run dont la mission n'existe plus ?

La passe 21 a trace les appels reels plutot que de lire des noms, et la
reponse etait que le contrat etait **deja tenu par la conception** :

- aucune cle etrangere entre `runs.mission` et `missions.mission_id` ;
- `MagasinMissions.supprimer` ne touche que la table `missions` ;
- `Registre` n'expose aucune suppression, et le gel terminal vit dans le
  SQL, sur chaque colonne ;
- `de_la_mission`, `reprendre` et `reconcilier` ne consultent **jamais**
  le magasin des missions — verifie sur l'arbre syntaxique de chacune ;
- le run porte son propre instantane depuis HOS-219 : objectif, modele,
  runtime, fournisseur, workspace, projet, tentative, contrat.

Il n'y avait donc rien a construire. Ce qui manquait etait que personne
ne l'ecrive et que rien ne le prouve.

### Le fait qui reformule le sujet

**Il n'existe aucune fonctionnalite de suppression de mission.** Zero
appelant de production pour `_RegistreMissions.__delitem__` : pas de
route, pas de service, pas de politique. Les huit orphelins ne viennent
pas d'un trou de conception mais d'un geste d'operateur qui a employe une
primitive de test comme outil.

D'ou la seule modification de production de cette passe : le contrat,
ecrit sur `__delitem__`. La suppression emporte la mission et son entree
de cache, **jamais ses runs** ; aucune cascade ne doit y etre ajoutee ; et
cette primitive n'est pas une fonctionnalite produit — ajouter un
`DELETE /missions/{id}` demanderait d'abord de decider d'une politique de
retention.

### Ce que la mission absente n'est pas

Ni une `Cause`, ni une condition de reconciliation, ni une raison de
transformer `EN_COURS` en `PERDU`. La reconciliation continue de decider
sur la seule preuve qui vaut : le processus porteur existe-t-il encore.
Un test le montre par symetrie — meme scenario avec et sans la mission,
resultat identique — et la raison inscrite nomme le processus disparu,
jamais la mission.

Deux chemins de reprise restent distincts et le restent : une mission
absente fait refuser explicitement la reprise de mission, tandis que
`Registre.reprendre()` continue de fonctionner par lignee du run parent,
sans qu'aucune mission soit reconstruite.

### Les gardes mordent, mesure

Trois mutations posees puis retirees :

- cascade reelle `DELETE FROM runs` dans `MagasinMissions.supprimer` →
  **14 rouges**, dont le redemarrage a deux processus ;
- reconciliation consultant le magasin des missions → **3 rouges** ;
- `Cause.MISSION_ABSENTE` ajoutee → **1 rouge**.

Une premiere version de la premiere mutation n'a fait rougir que la garde
AST : elle ouvrait un `Registre()` par defaut, donc une autre base que
celle du test. Refaite sur la vraie base partagee, elle a fait rouge le
comportement. La lecon vaut d'etre notee : une mutation qui ne rougit pas
peut accuser la mutation autant que le test.

### Les huit runs

Inchanges, et c'est verifie avant et apres : memes identifiants, memes
statuts, aucune cause inventee. `dbde3e7cbf` reste `en_cours` — son
processus porteur est mort, et la reconciliation existante le fermera au
prochain demarrage du backend, en `PERDU` / `Cause.PROCESSUS`, sans
qu'une ligne nouvelle soit necessaire. Aucun nettoyage, aucun SQL direct.

## HOS-252 — Ce qu'un test de cablage mesurait vraiment (2026-09-04)

Passe 20, implementation des quatre decisions de la passe 19. Quatre
sujets, une meme forme : la primitive existait deja et n'etait pas
branchee, ou existait et n'etait pas verifiee.

### T-17 — un test de cablage qui mesurait une mission autonome

`test_no_real_subsystem_event_is_dropped` prouvait que l'EventHub ne jette
rien, en lancant un objectif autonome complet. Mesure en passe 18 : deux
reproductions de 608 s et 531 s **sans terminer**, pour une couverture de
topics acquise a 187 s, avec un plafond de conception de ~4 800 s — budget
de mission 3 600 s, verifie entre deux taches seulement, plus le plafond
d'un noeud engage.

La preuve du cablage vit desormais dans
`backend/tests/test_cablage_des_evenements.py` : **0,4 s**, sur la vraie
chaine `GraphExecutor -> MissionExecutor -> EventDispatcher -> EventHub`.
Rien n'est simule de la publication ; la seule couture est l'exécuteur de
tache, un parametre du constructeur de `MissionExecutor` depuis toujours
et prevu pour cela. Consequence assumee : `execution.task_completed` est
attendu du cote lent, parce que c'est `RealTaskExecutor` qui le publie —
l'affirmer du cote rapide reviendrait a verifier un evenement que le test
aurait lui-meme emis.

Les topics sont **nommes un par un**, pas comptes : un `len(events) >= 26`
reste vert quand un topic disparait pendant qu'un autre apparait, ce qui
est exactement la derive surveillee.

Le test long reste, reste `lent`, et garde ce que lui seul prouve — le
chemin autonome reel, avec ses familles `autonomous.*` et `planning.*`. Il
se termine maintenant : des sa propriete demontree, il annule l'objectif
par la route de production, et l'attente restante est bornee par
`plafond_du_noeud()`. Depasser cette borne n'est pas un delai de confort,
c'est le graphe qui a franchi son propre dernier recours, et le test le
dit.

**Une derive vivante trouvee au passage.** `mission.completed` etait publie
par `graph_executor` et absent de `EVENT_TYPES`. Le commentaire du
catalogue affirmait qu'« un ancien jet nommait des topics qu'aucun
emetteur n'utilise (mission.completed) » : vrai du scan, faux du code — le
topic y passe par une variable, invisible a la collecte AST des litteraux.
Le hub le delivrait avec un avertissement, mais tout abonne qui filtre par
type — le Cockpit — ne voyait jamais la fin d'une mission. C'est
exactement le mode de defaillance decrit par HOS-066B, retrouve par le
nouveau test.

### T-18 — une annulation qui n'annulait rien

`cancel_goal` posait `goal.status = CANCELLED` et s'arretait la. **Personne
ne lisait ce champ** hors des compteurs de `get_status` : la marche du
graphe s'arrete sur `mission.status`. HOS-102 avait corrige
l'*accessibilite* de cet appel — le verrou tenu pendant toute l'inference
le rendait injoignable — pas son *effet*.

Aucune primitive nouvelle : `graph_executor.cancel_mission` existait, elle
etait effective, et c'est elle qu'on appelle. Aucun mecanisme de
terminaison de processus non plus — l'invariant « un noeud engage n'est
pas interrompu » est celui du budget missionnel (HOS-247) et il tient ici
aussi, prouve par un test qui lance un noeud, annule pendant qu'il
travaille, et verifie qu'il termine.

La reponse de la route porte desormais sa semantique : « aucune tache
nouvelle ne sera engagee ; un noeud deja engage termine son travail ». Un
operateur qui lit `success: true` ne doit pas comprendre « arrete
maintenant ».

Verifie aussi : une seule route `/missions/{id}/cancel` est reellement
montee, celle de `mission/routes.py`, qui vise `Mission`. Celle de
`api/router.py`, qui vise `MissionInstance`, n'est montee nulle part —
`mission_control.py` le documentait deja depuis HOS-072. Pas de collision.

### T-19 — le journal survivait, son sujet non

`MagasinMissions` n'etait ecrit que par `__setitem__`, c'est-a-dire une
seule fois, a l'enregistrement, avant tout demarrage. Mesure : une mission
ayant tourne 531 s et reussi six noeuds sur sept se relisait sur disque
`READY / started_at=None / tous PENDING`.

Consequence directe sur HOS-248 : `started_at` est le **t0 canonique du
budget**, et il ne franchissait pas la frontiere du processus. Une mission
reprise apres redemarrage repartait avec 3 600 s entieres. C'est le
pendant exact de HOS-245, qui avait rendu durable l'*existence* d'une
mission : ici c'est son *etat*.

Aucun second stockage. Le persisteur est un appelable injecte dans
`GraphExecutor`, de la meme forme que `on_event` et `execute_node` qui y
etaient deja, et le bootstrap y branche le magasin M-8. Points d'ecriture :
demarrage, noeud terminal, mission terminale, annulation.

`_RegistreMissions.persister()` ecrit le disque **d'abord** et le cache
seulement s'il a accepte, en laissant l'erreur remonter. `__setitem__`
garde sa tolerance pour la creation — « une correction de persistance qui
empecherait de creer une mission serait un recul » — mais il mettait le
cache a jour meme en cas d'echec : la memoire affirmait une durabilite qui
n'existait pas. Prouve par un magasin qui refuse d'ecrire.

La preuve de survie se fait dans **deux processus** : l'un ecrit, l'autre
relit, et seul le disque parle.

### T-20 — l'isolation existait, sa verification non

La passe 18 avait conclu que la suite lente ecrivait dans
`AppData/Local/HermesOS`, sur la foi de deux missions bien reelles
trouvees la. Elles venaient de sondes autonomes, qui ne chargent aucun
`conftest` ; la suite est isolee depuis HOS-215. Une passe entiere avait
ete batie sur ce constat faux.

`conftest.py` verifie desormais ce qu'il pose : chemins canonicalises des
deux cotes — `resolve()` suit liens et jonctions, `normcase` gele casse et
separateurs — et l'imbrication compte autant que l'egalite. La suite
s'arrete avant le premier test plutot que d'ecrire. Elle ne supprime rien
et ne touche a aucun reglage : ce serait pire que le probleme.

### Ce qui reste ouvert

Huit runs des deux missions de diagnostic restent en base apres la
suppression de leurs missions en passe 19. `Registre` n'expose aucune
suppression, et supprimer des lignes SQL a la main contournerait la seule
autorite du Ledger. L'incoherence est symetrique de celle que HOS-245
avait fermee — le journal survit, son sujet a disparu — et attend une
decision dediee (T-21).

## HOS-251 — Deux tests qui affirmaient le contrat d'avant (2026-09-04)

Passe 17. HOS-249/250 avaient change deux contrats ; deux tests les
affirmaient encore, laisses rouges et nommes dans le commit precedent au
titre de l'exception de `CLAUDE.md`. Ils adoptent ici les nouveaux.

### Ce qui ne devait surtout pas arriver

Les rendre verts par le symptome. `assert hits` en `assert hits == []`
aurait suffi a faire taire les deux, sans qu'aucune ligne ne demontre
*pourquoi* la reponse est vide — et une reponse vide est exactement ce
que produit une regression du filtre, un projet mal resolu, ou une base
qu'on n'a pas ouverte. Un vert obtenu ainsi aurait couvert les trois.

### T-16 — l'incident de HOS-086 tient, la premisse a change

`test_memory_search_answers_without_the_document_index` protegeait un
vrai defaut : `memory_search` interroge deux magasins independants, et la
panne de l'un ne doit pas vider ce que l'autre sait. Ce qu'il faisait
d'obsolete etait d'ecrire **sans provenance** — donc `INCONNUE`, donc en
quarantaine.

Il ecrit desormais deux memoires dans la meme seconde, par les deux
chemins reels : le chemin humain, qui pose `HUMAIN`, et l'outil MCP, qui
pose `AGENT` lui-meme. L'index documentaire tombe, une seule revient. Et
ce qui les separe est relu en base : `origine` et l'etat de quarantaine,
pas le contenu ni la fraicheur. L'ecriture de l'agent porte
`confidence=1.0` et les tags `verified`, `trusted`, `human-approved` —
verifies presents dans la ligne, donc l'assertion n'est pas creuse — et
n'obtient rien. Une promotion humaine nommee la rend visible par le meme
appel.

Une matrice a cinq origines complete au niveau de l'entree durable ce que
`test_memoire_quarantaine.py` verifiait sur l'objet `Provenance` seul.

### T-13 — l'identite vient du registre

`test_project_id_filters_tasks_memory_and_messages` passait `"proj-1"` et
`"proj-2"`. Le filtrage marchait, et c'est ce qui posait probleme : deux
orthographes du meme projet ne se voyaient pas, et un identifiant invente
rendait une liste vide — qui se lit « ce projet n'a rien memorise » — au
lieu d'un refus.

Les identifiants viennent maintenant de `projects_create`, comme en
production. Deux tests s'ajoutent : un UUID bien forme mais jamais
enregistre est refuse **et rien ne s'ecrit** — un refus qui laisserait une
ligne orpheline serait pire que pas de refus du tout — et la recherche
depuis A rend A et le permanent, jamais B, apres promotion.

### Les assertions mordent, mesure

Trois mutations posees et retirees, chacune sur le mecanisme que les
tests pretendent demontrer :

- filtre de quarantaine retire → **4 rouges** (dont `agent`, `web` et
  l'origine absente ; `humain` et `systeme` restent verts, donc la
  matrice discrimine) ;
- resolution de projet neutralisee → **1 rouge**, celui du refus ;
- portee neutralisee → **1 rouge**, celui de l'isolation A/B.

### Aucun code de production modifie

Le nouveau contrat etait deja implemente et deja garde ; il manquait des
tests qui l'affirment. Le seul autre changement est un commentaire
d'en-tete devenu faux : `memory_search` n'a plus besoin d'Ollama pour
etre teste, puisque repondre sans l'index est precisement son contrat.

## HOS-249, HOS-250 — La memoire de l'agent etait un fait des qu'il l'ecrivait (2026-09-04)

Passes 15 et 16. Le jalon 2 (HOS-216) avait pose la quarantaine ; elle
protegeait la memoire de travail et pas celle qui survit au redemarrage.

### Le defaut, mesure

`memory_remember` — l'outil MCP que l'agent appelle — ecrivait dans
`memory_long` **sans provenance**, et `memory_search` relisait la table
sans filtre. Une phrase lue sur une page web devenait donc, en un
aller-retour, un fait que l'agent citait comme le sien. C'est le chemin
exact par lequel une injection de prompt voyage, et il etait ouvert.

Rien n'a eu besoin d'etre invente pour le fermer : `Provenance.depuis()`
appliquait deja la regle, `filtrer()` existait, `ORIGINES_DE_CONFIANCE`
excluait deja `AGENT` et `WEB`. Le travail a consiste a **appliquer ces
politiques la ou elles manquaient**, pas a en ecrire de nouvelles.

### `promouvoir()` annoncait un succes sans rien ecrire

Trace ligne a ligne : `souvenir.provenance = promue` levait
`AttributeError` (propriete calculee), le repli cherchait un `metadata`
que `MemoryEntry` n'a pas, rien n'etait ecrit — et `memory.promoted`
etait publie. Une promotion qui ne promeut pas est pire qu'une absence de
promotion : on la croit. La facade leve desormais ; le seul chemin qui
persiste est `episodic.promouvoir()`, qui commit, relit, et refuse le
succes si la memoire est encore en quarantaine apres ecriture.

Chemins de promotion persistante : **0 → 1**. Outils MCP d'elevation :
**0 → 0**, et une garde AST le tient — `promu_par` n'est assigne qu'en un
seul endroit du depot.

### Ce que la promotion ne fait pas

Elle ne change pas l'origine. Une memoire ecrite par l'agent reste
`agent` pour toujours : `Provenance` separait deja « d'ou ca vient » de
« ce qu'on en fait », donc `promu_par` renseigne suffit a basculer la
seconde en laissant la premiere intacte. Sans quoi on ne saurait plus
repondre, apres coup, a « d'ou venait cette information ? ».

`promu_par` est **obligatoire et non vide**, et c'est une trace d'audit,
pas une preuve : Hermes OS n'a aucun mecanisme d'identite humaine — son
conventionnel d'accord humain existant, `POST /security/approvals/{id}`,
n'en porte pas non plus. Ce qui fait foi est le **canal** : la route est
servie par l'API locale et n'existe pas comme outil MCP. Aucune identite
n'a ete inventee pour l'occasion.

### Identite de projet

`project_id` etait une chaine libre. Il est desormais l'identifiant
canonique d'un projet enregistre ; un identifiant qui ne resout vers rien
leve `ProjetInconnu` au lieu de rendre une liste vide — une liste vide se
lit « ce projet n'a rien memorise », un refus se lit « ce projet n'existe
pas ». Meme contrat qu'Aegis sur le meme parametre.

Les lignes historiques sont migrees chemin → identifiant au demarrage,
par jointure sur `root_path`. La migration ne devine rien : une ligne qui
ne resout pas reste telle quelle avec un avertissement, et **aucune
provenance inconnue n'est transformee en provenance connue**.

### Deux tests historiques laisses rouges, delibere

`test_memory_search_answers_without_the_document_index` et
`test_mcp_server::test_project_id_filters_tasks_memory_and_messages`
affirment les contrats d'avant — « une memoire ecrite par l'agent est
relisible par l'agent » et « `project_id` est une chaine libre ». Ils ne
sont pas casses : ils sont **perimes**. Ils sont laisses intacts et
rouges, et une passe dediee les reecrira sur les contrats T-13 et T-16.
Voir l'exception nommee dans `CLAUDE.md`.

## HOS-248 — Un budget que chaque noeud remettait a zero (2026-09-03)

Passe 10. HOS-247 avait rendu le budget effectif ; il restait sans effet
la ou il comptait.

### Le defaut, decouvert par HOS-247 en s'implementant

Sa premisse — `ExecutionMeta` est l'objet d'execution *de la mission* —
etait vraie sur un chemin et fausse sur l'autre. `execution/routes.py` en
construit **un** pour toute l'execution ; `mission/node_execution.py` en
construit **un par noeud** du DAG. Sur le chemin autonome, le budget
repartait donc de zero a chaque etape et ne pouvait jamais se declencher,
un noeud etant deja plafonne a 1 200 s. Le champ etait effectif et sans
effet.

### Ce que la mesure a elimine

Trois objets etaient candidats ; deux le sont par le code lui-meme.
`ExecutionMeta` est fragmente, mesure. **`Run` l'est aussi** :
`_ouvrir_le_run` part de `prepare(meta, …)`, donc une fois par noeud — le
journal ne pouvait pas porter le budget, et le lui confier en aurait fait
un decideur.

Reste `Mission` : le seul objet mesure comme unique par mission, deja
persiste par M-8 — dont le serialiseur parcourt `fields()`, si bien qu'un
champ nouveau traverse un redemarrage **sans migration ni schema**. Et
`Mission.started_at` existait deja, pose une seule fois par tentative et
reinitialise par une reprise : le t0 n'avait pas a etre invente, et la
regle « une reprise repart avec un budget entier » est vraie sans qu'une
ligne ne la decide.

### La precedence, explicite

    mission enregistree  ->  budget de la Mission
    sinon                ->  budget de l'ExecutionMeta

Le chemin direct garde donc son budget local, ou il est legitime : un
seul `ExecutionMeta` y couvre toutes les taches. Une garde lit l'ordre
des deux lectures dans `budget_s` : les inverser rendrait tous les tests
verts sur un chemin et faux sur l'autre.

### L'horloge : un seul terme civil, lu une seule fois

Une premiere version mesurait `now() - started_at` a chaque appel. La
garde monotone de HOS-247 l'a immediatement refusee — et elle avait
raison. La mesure est donc :

    deja consomme avant cette machine   (civil, lu UNE fois a la naissance)
  + ecoule depuis sa construction       (monotone, perf_counter)

Le premier terme ne peut pas etre monotone : il traverse la frontiere du
processus, et une horloge monotone ne mesure que depuis un demarrage. Le
limiter a une lecture est ce qui met la mesure d'un noeud **en cours** a
l'abri d'un saut d'horloge — heure d'hiver, NTP. Sans registre global :
l'offset tient sur la machine d'etat elle-meme.

Effet de bord heureux : `budget_consomme_s`, la propriete la plus lue,
n'interroge plus rien du tout.

### La chaine, mesuree de bout en bout

    mission bf6fcc85, budget 10 s
      n0   consomme  0/10  ->  engage
      n1   consomme  4/10  ->  engage
      n2   consomme  8/10  ->  engage
      n3   consomme 12/10  ->  REFUSE (budget)   cause : budget

Trois `ExecutionMeta` distincts, un seul compteur. Avant ce jalon, les
quatre lisaient 0 s.

### Mesures

| | passees | ignorees | deselectionnees |
|---|---|---|---|
| standard | **5 536** | 3 | 274 |

Frontend : 126 vertes, typecheck propre. 18 gardes ajoutees, aucun test
existant modifie.


## HOS-247 — Un budget qui se declarait et que personne ne lisait (2026-09-03)

Passe 8. La decision verrouillee en passes 7 et 7.1 est implementee — et
l'une de ses premisses s'est revelee fausse en chemin.

### Le defaut

`ExecutionMeta.max_duration_seconds = 3600.0` existait depuis longtemps.
Compte sur l'arbre syntaxique : **zero lecteur** en production, quand son
voisin de dataclass `max_retries_per_task` en avait deux. Le seul plafond
reel etait `MAX_EXECUTION_PASSES x plafond_du_noeud()`, soit **33 heures**
— trente-trois fois le budget declare. Ce n'est pas un budget, c'est un
garde-boucle.

Troisieme occurrence du meme motif sur ce chantier, apres `Statut.PERDU`
declare et jamais pose (HOS-240) et `modele`/`fournisseur` servis et
jamais ecrits (HOS-241).

### Pourquoi 3 600 s, et pas un chiffre rond

`docs/essai-skills360.md` porte quatre executions reelles du meme
objectif : 566 s, 878 s, 1 084 s et **2 186 s**. La derniere est un
**succes**, 7 taches sur 7, 12 fichiers produits. Un budget de 1 800 s
l'aurait tuee a 82 % de son travail.

3 600 s, c'est 1,65 fois ce pire cas reussi, et exactement trois plafonds
de noeud. Une garde tient cette justification, pour qu'elle ne redevienne
pas un souvenir.

### Ce que ce budget n'est pas

Il ne coupe rien. Il refuse d'**engager** la tache suivante ; une tache
deja lancee va au bout de son propre plafond — 900 s pour l'agent,
1 200 s pour le noeud. C'est ce qui le distingue d'un timeout.

Et un budget atteint n'est **jamais** `PERDU` : perdu veut dire « on ne
sait pas ce qui s'est passe », ici on le sait exactement, et c'est
l'operateur qui l'a decide. `Cause.BUDGET` est ajoutee, distincte de
`QUOTA` (une limite du fournisseur) et de `RESSOURCE` (une limite de la
machine) : celle-ci est une limite qu'on tient, pas qu'on subit. Son
remede porte `reessayer=False` — reprendre consommerait immediatement le
meme budget une seconde fois.

### L'horloge

`perf_counter`, pas `datetime.now()` : une horloge civile recule a
l'heure d'hiver et sur une synchronisation NTP, et une mission serait
coupee ou prolongee par le reglage de la machine. Pas `monotonic` non
plus : mesure, il a ~16 ms de resolution sur Windows, et un budget de 1 ms
s'y lisait « 0 s consommee ». Sans importance a l'echelle d'un budget en
heures, mais un test de frontiere ne doit pas dependre de la granularite
de l'horloge.

### La premisse fausse, trouvee en chemin

La passe 7 supposait qu'`ExecutionMeta` etait l'objet d'execution **de la
mission**. Mesure, il l'est sur un chemin et pas sur l'autre :

- `execution/routes.py` en construit **un** pour toute l'execution, avec
  toutes ses taches — le budget y est bien missionnel ;
- `mission/node_execution.py` en construit **un par noeud** du DAG, chacun
  ouvrant sa propre machine d'etat — le budget y est un budget **de
  noeud**, et ne se declenchera donc jamais, un noeud etant deja plafonne
  a 1 200 s.

Aucun risque introduit : sur ce chemin, le champ reste sans effet comme
avant. Mais il ne protege pas la mission entiere, et le croire serait
exactement le genre d'illusion que ce jalon corrige ailleurs. Une garde
epingle la limite et echouera le jour ou elle disparaitra.

Un budget reellement missionnel sur le chemin autonome demande un t0
porte par la **mission**. C'est une decision que la passe 7 n'a pas
prise, et l'elargir ici aurait ete le « reparer par extension de
perimetre » que la passe 8 s'interdit explicitement.

### Deux faux positifs de sous-chaine, dans mes propres gardes

Dixieme : une garde d'ordre comparait deux `str.index` et trouvait
`self._task_executor.execute` dans la **docstring**, cinquante lignes
avant le code. Onzieme : une garde interdisant `PERDU` s'accrochait a la
docstring qui explique precisement que ce n'est jamais `PERDU`. Les deux
reecrites sur l'arbre syntaxique, corps sans docstring.

### Mesures

| | passees | ignorees | deselectionnees |
|---|---|---|---|
| standard | **5 517** | 3 | 274 |

Frontend : 126 vertes, typecheck propre. 22 gardes ajoutees, **aucun test
existant modifie**, aucun test supprime.


## HOS-246 — Le test n'etait pas bloque : l'agent cherchait sur tout le disque (2026-09-03)

Passe de fermeture ciblee. Trois points de la passe precedente, dont deux
diagnostics qui ont refute mes propres mesures.

### Le test « bloque » : cause racine, mesuree

`TestEventWiring::test_no_real_subsystem_event_is_dropped` n'est pas en
interblocage. Pile complete capturee sur les trois fils :

    task_executor.py:756  ->  _run_coro  ->  future.result(timeout=...)

C'est une attente **bornee** : 900 s par tache pour l'agent, 1200 s par
etape de graphe. Et le test progresse reellement — un dossier de mission
apparait toutes les deux a quatre minutes, `lfm2.5-2.6b-125k` est charge
en VRAM, et les processus d'agent se succedent.

Ce qui le rend interminable a ete trouve en inspectant les petits-enfants
du processus de test :

    find.exe / -name api_spec.yaml -type f   |   head -20

L'agent, cherchant une specification d'API, a lance un `find` sur **la
racine entiere**. Huit minutes et demie plus tard il tournait encore. Le
`head -20` qui aurait du le fermer ne propage pas SIGPIPE sur Windows.

Le test est donc **legitimement non mesurable ici** : il conduit une
mission autonome complete dont le nombre de noeuds n'est pas connu
d'avance, chacun borne a 900 s. Non modifie, non desactive, non marque.

### Les processus residuels : ma mesure precedente etait fausse deux fois

J'avais rapporte « 19 processus hermes-agent, dont un ne a l'heure exacte
du lancement des tests ». Les deux moities etaient fausses.

Le filtre portait sur la **ligne de commande** et attrapait trois de mes
propres shells qui mentionnaient simplement « hermes-agent ». Huitieme
faux positif de sous-chaine de ce chantier. Mesure sur l'executable :
**12**, dont **aucun** cree le jour de la campagne. Le processus ne a
19:22 etait un shell, pas un agent.

Mesure correctement, le cycle de vie du CLI est **sain** : observe sur un
vrai deroulement, un agent apparait, travaille, disparait, un autre le
remplace, et le compte reste stable. `hermes_agent_cli` attend
`communicate()` et tue le processus des que le budget expire.

### L'ambiguite, elle, est reelle — et non tranchee

40 processus ont leur repertoire courant sous `hermes_os_scratch` : des
`bash -lic "… python app.py"` et les serveurs qu'ils lancent, ecoutant sur
le port 8000, vivants depuis 37 heures. Ce ne sont pas des agents : ce
sont les **petits-enfants** que l'agent demarre en executant le code
qu'il ecrit.

Personne ne les possede. Ni Hermes OS, qui ne possede que le processus
CLI et le libere correctement. Ni l'agent, qui sort.

**Aucun faucheur n'a ete construit.** Hermes Agent est le cerveau : il
peut legitimement demarrer un serveur de developpement, et le tuer serait
detruire le travail demande. Inventer un systeme qui tue des processus
dans le dossier de travail d'un utilisateur serait a la fois une
architecture nouvelle et un risque. La decision revient au proprietaire
du depot ; ce jalon la documente et garde ce qui est demontre.

### Une documentation qui affirmait le contraire du code

`_unsandboxed_write` decrivait `ToolPolicy.evaluate()` comme une branche
inerte et affirmait que les adaptateurs MCP ne consultaient jamais leur
`ToolSandbox`. **HOS-238 avait rendu les deux affirmations fausses**, huit
jalons plus tot.

La conclusion du garde-fou tient pourtant toujours, mais pour une autre
raison, qu'il fallait ecrire : HOS-238 a ferme une porte plus etroite —
la politique refuse une ecriture dans un sandbox *declare* en lecture
seule, mais elle n'en **provisionne** aucun. Ce n'est plus « rien ne
verifie », c'est « rien ne fournit l'isolement dont la verification aurait
besoin ». Trois gardes tiennent desormais les deux moities de cette
phrase, sur le comportement et non sur le texte.

Une documentation perimee sur une decision de securite est pire qu'une
absence : elle fait croire qu'un controle manque la ou il existe, et on
finit par en ecrire un second.

### Neuvieme faux positif, entre ma correction et ma propre garde

La note de correction **citait** l'ancienne formulation ; la garde qui
interdit cette formulation s'y est accrochee. Reecrite pour decrire au
lieu de citer.

### Mesures

| | passees | ignorees | deselectionnees |
|---|---|---|---|
| standard | **5 496** | 3 | 274 |
| lente (moins le test non mesurable) | **267** | 6 | — |
| **complete** | **5 763** | 9 | **1 non mesurable** |

Frontend : 126 vertes, typecheck propre. 7 gardes ajoutees, 0 test
supprime, 0 processus tue.


## HOS-245 — Le journal survivait, son sujet non (2026-09-03)

Passe §5.2 : déblocage de spécification, mesure de la suite lente, et la
dette M-8.

### P-4 : tranché, et le dépôt le dit enfin

`ROADMAP.md` portait encore « Consolider `ModelRouter` et
`AdaptiveRouter` — **un seul devrait décider** », alors que HOS-243/244 a
livré et gardé leur séparation. Le document contredisait l'architecture
validée. Il dit maintenant ce qui a été décidé : coexistence autorisée
tant qu'aucun chemin de production ne les utilise comme autorités
concurrentes, précédence arbitrée par `backend.ral.arbitrage`.

### « 5 472 vertes » n'était pas la suite

`pytest.ini` porte `addopts = -m "not lent"` : la commande standard
**désélectionne 273 tests**. Ils ont été exécutés.

- **271 passent**, 6 sont ignorés ;
- **2 échouaient depuis longtemps** — antérieurs à HOS-240, jamais vus ;
- **1 ne finit pas**, même avec 1 200 s de délai.

Le trou de HOS-111 s'était rouvert plus petit : `testpaths` avait été
corrigé, `addopts` rouvrait la porte à côté.

### Les deux rouges : le test affirmait ce que R-002 avait supprimé

`create_code_intelligence_agent()` était appelé **sans fournisseur**, et
les tests attendaient un succès. Or R-002 P5 avait précisément retiré le
`success=True, {"status": "simulated"}` que l'agent rendait alors — les
tests avaient survécu à la correction et exigeaient toujours le
comportement retiré.

Mesuré, l'agent a **deux refus honnêtes**, et le premier masquait le
second :

    aucun fournisseur, tâche écriture  →  « provider klaatcode is not bound »
    fournisseur lié,   tâche écriture  →  « … no sandbox — refused (R-006 Phase 9) »
    fournisseur lié,   tâche lecture   →  l'exécuteur est réellement appelé

Les deux tests lient donc un fournisseur, ce qui leur fait enfin
atteindre la branche que leur propre docstring décrit. Ils vérifient
davantage qu'avant, et une troisième garde tient le refus que tous deux
masquaient. Aucun test supprimé, aucune assertion affaiblie.

### Le test qui ne finit pas

`test_no_real_subsystem_event_is_dropped` appelle
`autonomous_engine.start_goal("Build an API")` — c'est-à-dire **une
mission autonome complète**, synchrone, dont la docstring annonce
elle-même « minutes » d'inférence locale. Bloqué dans
`graph_executor._recolter_en_parallele`, 0 seconde de CPU, il n'a pas fini
en 1 200 s. Il laisse aussi de vrais sous-processus d'agent derrière lui.

Non modifié : le corriger sans décision serait exactement le vert
artificiel que cette passe interdit. Signalé comme la seule dette
mesurée de la suite lente.

### M-8 : la mission survit enfin à son propre journal

HOS-221 avait rendu le registre des **runs** durable ; HOS-240 lui avait
ajouté une réconciliation qui pose `PERDU`. Le registre des **missions**,
lui, était un `OrderedDict` en mémoire. Un run perdu désignait donc une
mission disparue — et pas seulement après un redémarrage : au-delà de
200, le FIFO en effaçait définitivement pendant que le processus tournait.

La table `missions` vit désormais dans la **même base que les runs**, avec
un document JSON qui rend la mission *reconstructible* — DAG, contexte,
énumérations et horodatages reviennent typés — et des colonnes scalaires
pour les seules questions qu'on pose en SQL.

Vérifié sur de vrais sous-processus tués par `os._exit` :

    run     : perdu | cause : processus
    mission : 'refondre le parseur'
    lien    : run.mission résout -> True
    reprise : tentative 2 | mission liée : True

### Deux défauts que j'ai introduits, et qui m'ont été rendus

**`values()` relisait toute la base.** Le test existant
`test_lister_pendant_qu_on_enregistre_ne_leve_pas` appelle `values()` deux
mille fois pendant qu'un fil écrit sans arrêt : chaque appel désérialisait
le JSON de toutes les missions accumulées. Le fichier est passé de
quelques secondes à plus de dix minutes. C'est un test écrit pour tout
autre chose — la réentrance d'un verrou — qui a démasqué une complexité
quadratique.

Le registre est borné par construction, et c'est ce qu'il a toujours
promis. Le cache est maintenant **hydraté** depuis la base au premier
parcours : après un redémarrage la liste n'est plus vide, et toute
mission évincée reste lisible par son identifiant.

**`len()` rendait le total en base.** Il rendait l'objet incohérent —
`len(r)` et `len(r.values())` ne disaient plus la même chose — et faisait
fuir chaque test dans le suivant. `len()` décrit le plan de travail ;
`total()` compte ce qui est conservé. Les confondre était l'erreur.

### Mesures

| | passées | ignorées | désélectionnées |
|---|---|---|---|
| standard | **5 489** | 3 | 274 |
| lente (moins le test bloqué) | **267** | 6 | — |
| **complète** | **5 756** | 9 | 1 non mesurable |

Frontend : 126 vertes, typecheck propre. 20 gardes ajoutées, 2 tests
réécrits, 1 fixture d'isolation, 0 test supprimé.


## HOS-244 — Le code contredisait son propre contrat (2026-09-03)

Passe chirurgicale sur §5.1. Un défaut bloquant trouvé dans HOS-243,
livré la veille : la documentation du module d'arbitrage affirmait une
règle que son code violait douze lignes plus bas.

### La contradiction

`ral/arbitrage.py` écrivait, dans sa docstring :

> Il ne peut pas la faire redescendre : défaire une assignation
> explicite serait exactement la seconde autorité que ce module supprime.

Et, dans son corps :

    elif monte is not None and runtime == MONTEE_AUTORISEE and not cloud_joignable:
        runtime, source_runtime = defaut_runtime, "repli, cloud injoignable"

Une tâche assignée à `openrouter` sans clé configurée devenait donc
`hermes-agent` — l'annulation silencieuse que le module existait pour
supprimer. Pire : elle **réussissait**, en local, et l'opérateur qui avait
demandé le cloud ne l'apprenait que dans un journal.

Ce n'était pas un défaut de documentation. C'était un défaut de
comportement, et la documentation avait raison.

### Recommandation défaite, assignation défaite

Le dépôt distingue déjà les deux, et c'est cette distinction qu'il
fallait appliquer :

- une **recommandation** vers le cloud qui n'aboutit pas est simplement
  défaite. C'est littéralement la politique de `_make_cloud_chat` —
  « cloud entièrement injoignable, **quoi que recommande AdaptiveRouter** ».
  Elle n'engageait personne. Le repli local reste autorisé, et nommé ;
- une **assignation** vers un runtime qui ne peut pas servir n'est pas
  remplacée. `Decision.impossible` est renseignée, et l'appelant lève
  `RuntimeUnavailableError` — le type que `task_executor` porte depuis
  toujours pour « the inference layer is down », retryable et jamais la
  faute de la tâche.

L'échec honnête n'est donc pas une politique nouvelle. Le message est
écrit pour que `runs.taxonomie` le classe **sans modification** :
`FOURNISSEUR`, remède `changer_de_fournisseur`, `reessayer=True`,
`changer_de_modele=False`. La machinerie de reprise de HOS-225 prend le
relais telle quelle.

L'arbitre, lui, ne lève pas : il n'exécute rien, et une exception depuis
un module qui ne fait que ranger des avis serait une décision d'exécution
déguisée.

### Le droit de monter, attribué au lieu d'être hérité

HOS-243 cherchait la montée vers le cloud sur **toutes** les
propositions. N'importe quelle source future qui aurait nommé
`openrouter` aurait donc hérité d'une autorité que personne ne lui avait
donnée.

Le droit est maintenant porté par la proposition elle-même
(`peut_monter`), faux par défaut, et accordé au seul décideur de la
tâche — c'est lui qui détient la porte d'escalade de HOS-066C. Une garde
lit le point d'appel réel : la règle est tenue là où elle s'exerce, pas
seulement là où elle est écrite.

### La frontière des deux routeurs, prouvée sur les appelants

HOS-243 la vérifiait sur les imports de deux fichiers nommés. Mesurée
cette fois en croisant les appelants réels des deux méthodes de
décision :

    core.router.ModelRouter.select_model        3 appelants
    AdaptiveModelRouter.recommend_for_text      2 appelants
    intersection                                AUCUNE

`service_registry` construit l'un et appelle l'autre : c'est une racine
de composition, elle câble et ne décide pas.

### Les gardes, vérifiées en les cassant

Chacune a été soumise à la violation qu'elle interdit, puis l'arbre
restauré. Les quatre détectent : reconstruction d'un point d'entrée
déprécié, routeur de rôles appelé depuis l'exécuteur missionnel, second
arbitrage, droit de monter accordé à une autre source.

### Mesures

7 gardes ajoutées, 4 réécrites (aucune supprimée). Suite complète :
**5 472 vertes**, 3 ignorées. Frontend : 126 vertes, typecheck propre.


## HOS-243 — Une seule autorité tranche, et elle l'écrit (2026-09-03)

Quatrième passe de consolidation, sur §5.1 : « il existe plusieurs
décideurs concurrents de routage ».

### Le compte est passé de deux à huit, en trois mesures

HOS-242 avait rapporté deux décideurs. La mesure était fausse par
méthode : elle comptait les **constructions de classes**, et manquait
tout composant obtenu par un accesseur ou un attribut. Retracés sur les
appels de méthodes, puis sur leurs définitions, **huit** composants
décident d'un runtime, d'un modèle ou d'un fournisseur.

Chaque hausse du compte venait du même défaut : chercher des noms plutôt
que des appels, puis des appels plutôt que des définitions. C'est la
troisième fois sur ce chantier qu'une cartographie se révèle incomplète
parce qu'elle cherchait la mauvaise chose.

### Huit décideurs ne sont pas un défaut

Ils répondent à huit questions, sur des chemins différents, chacun avec
ses propres données et ses propres mesures :

- `AdaptiveModelRouter` — profils mesurés, VRAM ; chemin missionnel ;
- `autonomous.DecisionEngine` — pose `assigned_runtime` sur un but ;
- `core.router.ModelRouter` — rôles de `config/models.yaml`, dont les
  tags portent les fenêtres de contexte servies ;
- `RuntimeRecommender` — planification, avant toute exécution ;
- `ral.courtier` — quel fournisseur cloud, une fois le runtime décidé ;
- `runtime.orchestrator.DecisionPipeline` — classe des candidats pour
  l'API d'observabilité ; **rien ne s'exécute sur son classement** ;
- `RuntimeDecisionEngine` — hors production (ci-dessous) ;
- `sds/routes.py` — un opérateur bascule le runtime actif par HTTP.

Le défaut était que **deux d'entre eux tranchaient la même requête** :

    runtime_id = _runtime_demande(assignment.runtime_id
                                  or task.assigned_runtime)   # ① ou ②
    ...
    runtime_demande = self._resolve_runtime(task)             # ①
    use_cloud = self._cloud_chat is not None and runtime_demande == "openrouter"
    if use_cloud:
        runtime_id = "openrouter"

Lequel l'emportait n'était écrit nulle part. C'était une **propriété
émergente de l'ordre des lignes** — dix lignes plus loin, un `elif` et un
`and` en décidaient. Une précédence qui n'est écrite nulle part ne peut
être ni discutée, ni testée, ni conservée à travers un refactoring.

### `ral.arbitrage` : l'arbitre, pas un neuvième décideur

Il ne classe aucun modèle, n'interroge aucun profil, ne mesure aucune
VRAM, ne contacte rien — deux gardes le tiennent, dont une qui refuse
qu'il devienne asynchrone. Il ne sait pas quel modèle est bon.

Il sait qui a le dernier mot, et il l'écrit. La précédence **reproduit le
comportement d'avant** : une assignation explicite l'emporte, puis le
décideur de la tâche, puis le défaut. La changer en même temps qu'on la
rendait explicite aurait rendu impossible de dire lequel des deux avait
causé une régression.

Une seule dérogation, celle qui existait déjà : le décideur peut faire
**monter** vers le cloud, et seulement si un fournisseur répond
vraiment. Il ne peut pas faire redescendre — défaire une assignation
explicite serait exactement la seconde autorité qu'on supprime.

`cloud_joignable` est un fait **passé par l'appelant**. Un arbitre qui
interrogerait lui-même les fournisseurs pourrait conclure « joignable »
sans passer par le pare-feu de données ni par le courtier : il
deviendrait une autorité de sécurité, ce que le RAL ne doit jamais être.

### La pile RAL, mesurée deux fois de plus

HOS-242 disait `RuntimeRouter`, `RuntimeDecisionEngine` et
`RuntimeSelector` « construits nulle part ». Ils **sont** appelés — mais
leurs seuls appelants sont `ExecutionEngine` et `MissionControlAPI`, dont
aucune n'est construite hors des tests, et le rappel `runtime_selector`
du superviseur n'est passé par personne.

Hors production, donc, mais par un chemin plus long que rapporté.
**Dépréciés explicitement, pas supprimés** : ils portent leurs propres
tests, et les effacer détruirait un travail mesuré sans rien corriger.
La dépréciation est dans leur docstring, là où on la lit, et une garde
échoue si un point d'entrée déprécié est reconstruit.

### Ce que la source dit maintenant

    A. cloud demandé, pas de clé  → ollama, « assignation explicite »,
                                    repli nommé
    B. cloud demandé, clé valide  → openrouter, fournisseur DeepInfra
    C. personne ne choisit        → hermes-agent,
                                    « défaut HOS-142 — aucun runtime choisi »

Le cas C est celui qui a coûté une nuit entière : `"default"` tombait
dans la boucle d'outils de Hermes OS au lieu d'aller à l'agent.

### Mesures

29 gardes ajoutées. Suite complète : **5 465 vertes**, 3 ignorées.
Frontend : 126 vertes, typecheck propre.


## HOS-242 — Le routage, mesuré : qui décide, qui exécute, qui le sait (2026-09-03)

Troisième passe de consolidation, sur §5. La question posée était
« pourquoi 13 modules contournent-ils le RAL ? ». La mesure a donné une
autre réponse.

### Les 13, classés

13 constructions réelles de `OllamaClient` en production, dans 8
fichiers — comptées sur l'arbre syntaxique, pas sur le texte.

- **5 sont de l'infrastructure** : `/api/ps`, `list_local_models`,
  `unload_model`. Aucune décision de routage : rien à router quand on
  demande à Ollama ce qu'il détient, ou qu'on lui fait libérer une carte.
- **1 est le RAL lui-même** : `sds/runtime.py` enregistre le
  constructeur `ollama` dans sa Factory. C'est la queue du chemin
  canonique, pas un contournement.
- **7 sont sur un chemin d'inférence**, et toutes reçoivent leur modèle
  d'un décideur injecté ou de leur appelant.

Aucune n'a été « faite passer par le RAL » pour améliorer un chiffre.
La cible n'était pas *tous les appels passent par le RAL*, mais *aucun
composant ne prend silencieusement une décision qui ne lui appartient
pas*.

### Ce qui n'était pas le défaut

`RealTaskExecutor` lit le runtime servi **dans la réponse**, jamais dans
la demande. `_make_cloud_chat` passe par le pare-feu de données puis par
le courtier avant tout envoi distant. La gouvernance de HOS-227 et
HOS-228 est bien sur le chemin, et deux gardes le tiennent désormais sur
l'ordre des lignes.

### Ce qui l'était : runtime et fournisseur étaient le même mot

`metadata["provider"]` valait `"ollama"` ou `"openrouter"` — c'est-à-dire
le **runtime**. Or OpenRouter n'exécute rien : il route vers un hébergeur
amont qu'il nomme dans un champ de premier niveau de sa réponse. Trois
fournisseurs pouvaient servir le même modèle avec trois latences, et
Hermes les appelait tous « openrouter ».

Le champ est désormais lu — **au champ structuré, jamais deviné**. Aucune
clé n'étant configurée sur cette installation, il n'a pas pu être observé
sur une réponse réelle : la lecture est défensive, son absence n'invente
rien, et la garde qui la tient le dit.

`runtime = ollama, fournisseur = local, modèle = qwen3.6-35b-a3b` — trois
faits distincts, là où il y en avait deux dont un dupliqué.

### Le repli distant → local était muet

Sans clé — le défaut mesuré en J17 : « 0 fournisseur configuré » — le
routeur recommandait le cloud, `_runtime_for` rendait « hermes-agent », et
**rien ne le disait**. Le registre inscrivait le runtime demandé :
l'opérateur croyait avoir payé du cloud.

Le repli reste **autorisé** — l'interdire ferait échouer toute mission sur
une installation sans clé, ce qui est le cas normal. Mais autorisé n'est
pas silencieux. Le run porte maintenant une colonne `decision` :

    {"runtime_demande": "openrouter", "runtime_servi": "ollama",
     "modele": "qwen3.6-35b-a3b", "fournisseur": "local",
     "repli": "openrouter indisponible, servi par ollama"}

Le repli n'y est nommé que lorsqu'il est **constaté** : un routeur qui n'a
rien demandé n'a pas été défait.

### Sept replis de routage retombaient en silence

Quatre dans `service_registry`, trois encore dans `task_executor` après
HOS-241. Un `except: return None` sur un rappel de décision rend « le
routeur n'a pas d'avis » et « le routeur est en panne » strictement
indiscernables — à l'endroit exact où la distinction décide du modèle qui
va tourner. Zéro subsiste, et une garde tient les deux modules ensemble.

### Deux autorités, et une pile morte

C'est la dette que cette passe **n'a pas** résorbée, et elle est
structurelle :

- `AdaptiveModelRouter` décide sur le chemin missionnel — mesures,
  VRAM, profils ;
- `core.router.ModelRouter` décide sur le chemin agentique — rôles
  déclaratifs de `config/models.yaml`.

Les deux répondent à « quel modèle », sur deux catalogues **sans aucun
lien** : le premier ne lit pas `models.yaml`, le second ne connaît pas les
profils. Ce sont bien deux autorités concurrentes.

Et `RuntimeRouter`, `RuntimeDecisionEngine`, `RuntimeSelector` — la pile
de décision du RAL — ne sont **construits nulle part** en production, pas
plus que le contrat `ral.model_router.ModelRouterInterface`, qui n'a
aucune implémentation. Le RAL déclare une autorité qu'il n'exerce pas.

Les unifier est un jalon, pas une passe : les deux décideurs sont
justifiés séparément par des mesures, et les fusionner sans mesure
recréerait exactement le genre de choix supposé que ce dépôt poursuit.

### Un septième faux positif de sous-chaîne, dans la garde elle-même

`runtime_id = "ollama"` contient « llama ». La garde qui interdit les tags
de modèles codés en dur s'y est accrochée. Réécrite pour exiger un chiffre
— un tag porte toujours une taille ou une version, une famille non.

### Mesures

Sur les 7 fichiers du chemin d'inférence :

| | avant | après |
|---|---|---|
| constructions `OllamaClient` | 6 | 6 |
| modules distinguant le fournisseur | 2 | 6 |
| replis de routage **muets** | 4 | **0** |
| replis de routage tracés | 6 | 10 |

23 gardes ajoutées. Suite complète : **5 437 vertes**, 3 ignorées.
Frontend : 126 vertes, typecheck propre.


## HOS-240, HOS-241 — Les runs qu'on perdait, et le modèle qu'on n'inscrivait pas (2026-09-03)

Deuxième passe de consolidation : les deux dettes structurantes du
journal des runs. Chacune observée **rouge** avant correction.

### `PERDU` existait dans le vocabulaire et rien ne le posait

HOS-221 l'écrivait dans son propre CHANGELOG. Neuf jalons plus tard,
c'était toujours vrai : un processus tué — `taskkill`, coupure, ou
simplement une exception qui traverse `execute_task` sans atteindre
`finalize()` — laissait ses runs `en_cours` pour l'éternité. La console
d'opérations affichait donc des runs actifs qui ne tournaient nulle part,
et le compteur « en cours » ne redescendait jamais.

**Pas un délai.** « `en_cours` depuis plus de N minutes ⇒ perdu » est
faux dans les deux sens : une mission longue sur un modèle local lent
dépasse n'importe quel N raisonnable et se ferait déclarer perdue *en
tournant*, tandis qu'un processus tué à la seconde 3 resterait `en_cours`
pendant N. Un délai mesure l'impatience de l'observateur, pas la mort du
porteur.

La preuve retenue est le porteur lui-même. Chaque run porte désormais
l'empreinte du processus qui l'a ouvert — `pid:date_de_démarrage`, écrite
une fois, à la naissance de la ligne. Ce n'est pas un battement de cœur :
rien n'est réécrit périodiquement. La date de démarrage n'est pas
décorative — les PID se réutilisent, et sans elle un nouveau processus
héritant du PID d'un mort ferait passer ses runs pour vivants.

Trois réponses et non deux : **vivant**, **mort**, **indécidable**. Une
empreinte illisible, un `psutil` absent ou un accès refusé ne prouvent
pas un décès, et les lignes ouvertes avant ce jalon n'ont aucune preuve
attachée. Elles sont comptées à part et signalées — jamais rangées avec
les morts.

`Cause.PROCESSUS` est ajoutée plutôt que réutiliser `INCONNUE`, qui
signifie « cherchée, non trouvée ». Ici la cause est constatée.

Vérifié sur le vrai `lifespan`, avec un vrai orphelin :

    réconciliation : 1 perdus, 0 vivants, 0 indécidables
    WARNING  1 run(s) perdus au démarrage
    GET /api/v1/operations → 200, nombre_en_cours: 0

### « Quel modèle a exécuté cette mission ? » n'avait pas de réponse

Pas une mauvaise réponse : **pas de réponse**. `modele` et `fournisseur`
existent comme colonnes depuis HOS-221, `vue_operations` les sert, le
Cockpit les affiche — et personne ne les écrivait. Elles valaient la
chaîne vide pour tous les runs jamais enregistrés.

`runtime`, lui, était écrit — mais à `ouvrir()`, donc **avant**
l'exécution, depuis `assigned_runtime`. C'est l'intention du
coordinateur, pas le fait.

**L'audit a réfuté sa propre prémisse.** Il cherchait des bascules
silencieuses dans `RealTaskExecutor` ; il n'y en avait pas là. Ce module
lit le runtime qui a servi **dans la réponse**, et son commentaire dit
que faire l'inverse « réintroduirait la malhonnêteté que R-001 existe
pour supprimer ». Le maillon manquant était le dernier : cette honnêteté
ne traversait pas jusqu'au registre. La correction est donc un câblage —
`Registre.constater()`, appelée avant `terminer()` parce qu'un run
terminal est gelé — et non une réécriture.

### La bascule silencieuse qui existait vraiment

`use_cloud = self._cloud_chat is not None and … == "openrouter"`. Sans
clé OpenRouter — le cas par défaut, mesuré en J17 : « 0 fournisseur
configuré » — une tâche explicitement assignée au cloud tournait en local
**sans un seul message**, et le registre inscrivait quand même
« openrouter ».

Et **six** rappels de résolution avalaient leur échec en `logger.debug`,
invisible au niveau par défaut. Deux portaient les bascules les plus
graves : `workspace_project_for`, dont l'échec fait tourner la tâche sans
outils ni pare-feu de données, et `num_ctx_for` — le piège le plus
coûteux de ce dépôt, celui qui fait dire à l'agent qu'il n'a pas d'outils
parce que les schémas ont été tronqués.

Ma première correction n'en couvrait que quatre. C'est la garde
elle-même, écrite trop étroite puis élargie à la découverte, qui a trouvé
les deux autres — elle énumère désormais les rappels au lieu de les
lister.

### Mesures

32 gardes ajoutées. Suite complète : **5 414 vertes**, 3 ignorées.
Frontend : 126 vertes, typecheck propre. Aucune régression.


## HOS-239 — Consolidation post-audit : trois défauts, une cartographie (2026-09-03)

Première passe de la mission de consolidation. Trois défauts corrigés,
chacun **observé rouge** avant correction, et une cartographie mesurée.

### La version d'OpenAPI contredisait la version produit

`FastAPI(version="1.0.0-rc1")`, écrite en dur. Une troisième valeur, à
côté de `frontend/package.json` (`0.1.0`) et de la version produit de
HOS-232 (`1.0.0`) — et c'est celle que **tout client lit** dans
`/openapi.json`.

Elle vient maintenant de `backend.maj.version`. `package.json` garde la
sienne, et c'est légitime : elle versionne le **paquet npm**, pas le
produit. Les rôles sont distincts ; les valeurs ne doivent pas se
contredire sur ce qu'est Hermes OS. Une garde AST interdit tout littéral
de version dans `main.py`.

### La cartographie backend → frontend, mesurée

25 sujets confrontés : ce que l'application sert vraiment contre ce que
`client.ts` appelle vraiment.

- **20 réellement raccordés** ;
- **3 servis sans consommateur** : `documents`, `logs`, `snapshots` ;
- **0 orphelin côté frontend** — aucun appel vers une route absente.

**Mon propre détecteur a produit cinq faux négatifs.** Il annonçait
approbations, points de reprise, Control Rooms, fournisseurs et
installation comme « backend seul » ; ils sont consommés, mais par
`operationsClient` en appels nommés que la recherche d'expression n'a pas
vus. Vérifié avant de le rapporter comme un manque — c'est exactement
l'erreur que cette mission interdit, et je l'ai commise dans l'outil de
mesure lui-même.

### Les couches événementielles, mesurées

Six noms existent. Comptés par fichiers et par publications réelles :
`SystemEventBus` (1 publication), `EventHub` (2), et quatre —
`EventDispatcher`, `EventBusImpl`, `MessageBus`, `RuntimeEventBus` — qui
**n'appellent jamais `publish` directement** dans le code de production.

Ce n'est pas six vérités concurrentes : c'est un bus durable
(`EventBusImpl`, sous la racine d'état depuis HOS-237), un concentrateur
que le frontend écoute (`EventHub`), et des façades qui délèguent. La
phrase qui l'explique tient : **un seul journal durable, un seul point de
diffusion, et des adaptateurs qui y écrivent.** Le reste du travail —
documenter producteur et consommateur pour chacun — reste à faire.

### Mesures

2 gardes ajoutées. Suite complète : **5 382 vertes**, 3 ignorées.
Frontend : 126 vertes, typecheck propre.


## HOS-236 — Les Control Rooms, et le 100 % qui n'existait pas (2026-09-03)

J17 final. Deux causes maintenaient le 🟠 : les Control Rooms, et une
vérification en navigateur non obtenue. Les deux sont levées.

### Le défaut : un agent qui n'a rien fait était noté parfait

`GET /api/v1/agents` rend `success_rate: 100.0` avec `total_tasks: 0`.
Et le Cockpit aggravait, à deux endroits d'`agent-center.tsx` :

    {(agent.success_rate ?? 100).toFixed(0)}%
    <ProgressBar value={agent.success_rate ?? 100} />

Un agent qui n'a **jamais rien exécuté** s'affichait donc à 100 %, barre
pleine. C'est le même mensonge que douze jalons ont chassé côté serveur,
à sa toute dernière étape — et le plus coûteux de sa famille, parce
qu'un taux affiché sur rien fait choisir un agent sur une réputation
qu'il n'a pas gagnée.

Zéro tâche n'est pas cent pour cent : c'est *aucune mesure*.
`_taux_mesure` rend donc un tri-état, la vue affiche « — jamais mesuré »,
et la barre de progression disparaît plutôt que de se remplir — une
barre à 100 % est une affirmation, et il n'y a rien à affirmer.

### La source canonique, et celle qu'il ne fallait pas prendre

Deux registres d'agents existent. `core.agent_registry` ne porte que les
agents Ollama configurés ; `AgentSupervisor` est celui que
`GET /api/v1/agents` sert déjà. S'être branché sur le premier aurait
donné une **seconde vérité sur ce qu'est un agent**. Une garde le tient,
sur les imports et non sur le texte.

Une Control Room assemble donc : l'identité et l'état depuis le
superviseur, les runs depuis le registre de HOS-221, la confiance depuis
son propre moteur — relayée telle quelle, puisqu'il dit déjà « unknown »
quand il ne sait pas. Aucun magasin neuf.

### La vérification en navigateur, obtenue

Les deux serveurs bloquants étaient exactement ceux de
`.claude/launch.json` — l'uvicorn du dépôt et son Next dev, identifiés
par ligne de commande avant d'y toucher. Redémarrés proprement.

Constaté sur le navigateur, en données réelles :

- **10 routes** `/operations` dans `openapi.json`, `200` sur chacune ;
- Supervision affiche 206 approbations, 3 points de reprise, 10 contrôles
  de santé, 0 fournisseur configuré ;
- « Version installée : jamais marquée » — pas la version du code ;
- « Aucun run en cours. **Mesuré, pas supposé.** » ;
- « Aucun fournisseur distant configuré. C'est le défaut. » ;
- deux points de reprise marqués **« fichiers seuls »**, un troisième
  avec état ;
- **10 Control Rooms**, chacune « — jamais mesuré » et « non
  disponible » ;
- la source sous chaque section.

### Un cinquième faux positif de sous-chaîne

Ma garde « la Control Room ne prend pas `core.agent_registry` »
s'accrochait à la docstring qui **explique** pourquoi elle ne le prend
pas. Cinquième fois sur ce chantier. Réécrite sur les imports.

### Ce qui reste volontairement hors J17

Les **analytiques** — missions, coûts, latences, taux de bascule. Elles
figurent dans la description de J17 mais **pas dans ses critères de
sortie**, et les fabriquer maintenant pour obtenir un vert serait
exactement ce que ce jalon interdit. Elles appartiennent à la vue que
J18 rendra extensible.

### Mesures

Backend : **5 361 vertes**. Frontend : **126 vertes**, typecheck propre.
7 gardes backend et 3 frontend ajoutées.


## HOS-235 — La console d'opérations, et le routeur que rien ne servait (2026-09-03)

J17 final. L'audit du frontend a donné deux surprises, l'une bonne et
l'autre grave.

### Le défaut : les huit routes de J17 étaient injoignables

HOS-234 les avait posées sur `MissionControlAPI`. Vérifié **sur le
processus en marche** : `GET /api/v1/operations` rendait `404`, et
`/openapi.json` ne contenait pas une seule route en `/api/v1/`.

`MissionControlAPI` existe, est exportée, et **aucun appelant de
production ne l'inclut dans l'application**. Le jalon était juste dans sa
forme et inexistant dans les faits — la variante la plus coûteuse de
l'orphelin, parce que ses tests passaient : ils montaient le routeur
eux-mêmes.

Les routes vivent maintenant dans `backend/api/routes/operations.py`,
listé dans `_LEGACY_ROUTERS`, c'est-à-dire sur le seul chemin que
`backend.main` sert réellement. Une garde interroge désormais
`TestClient(backend.main:app)` — l'application, pas un routeur monté pour
l'occasion — et une autre lit l'arbre syntaxique de `main` pour vérifier
que le module est bien dans la liste de montage.

### La bonne surprise : le Cockpit était déjà mûr

`FluxEvenements` est **l'unique** souscription au bus, et pousse dans
`useCockpitStore` — HOS-182 avait déjà corrigé le défaut des sockets
multiples. Le scaffolding (`CenterHeader`, `AsyncPanel`, `StatGrid`,
`Card`, `Badge`), les hooks TanStack, la navigation typée par
`satisfies` : tout existait. Rien n'a été recréé.

Et le frontend ne fabrique plus de compteurs : les `Math.random()`
restants sont des identifiants, une graine de studio, ou des
**commentaires documentant des fabrications retirées**.

### Le tri-état, jusqu'au pixel

Quatre choses s'affichent différemment, parce qu'elles ne veulent pas
dire la même chose :

- **zéro mesuré** — « Aucun run en cours. Mesuré, pas supposé. »
- **non mesurable** — un encadré ambré portant la raison, jamais un zéro.
  Un indicateur dont la source n'a pas répondu affiche « — ».
- **cause `null`** — « cause non démontrée » ;
- **cause « inconnue »** — « cherchée · non trouvée ».

Douze jalons ont travaillé côté serveur à ce qu'un « on ne sait pas » ne
se range jamais avec un « c'est bon ». Le refaire à l'affichage
l'annulerait à la dernière étape.

Trois cas particuliers portent la même règle : un contrôle de santé
`indisponible` s'affiche « sans objet » et non en rouge — une
installation neuve n'a pas de points de reprise, et le peindre en panne
ferait chercher un défaut qui n'existe pas. « Aucun fournisseur
configuré » est présenté comme **le défaut**, pas comme une panne. Et une
version jamais marquée n'est pas remplacée par celle du code.

### Une vue, jamais une seconde autorité

Toutes les routes sont en `GET`. Le modèle de lecture n'appelle rien qui
écrive et n'ouvre aucun magasin — deux gardes sur l'arbre syntaxique. La
trace vient du store, pas d'une seconde socket.

Et elle ne fabrique aucune activité : si le runtime n'émet rien, la liste
reste vide, avec la phrase qui le dit — « pas de battement de cœur
inventé ».

### Deux orphelins évités

Une garde du dépôt — `surface-api.test.ts`, que je ne connaissais pas —
a refusé `useOperationsLignee` et `useOperationsContrat` : deux hooks sans
consommateur. Elle avait raison. Ils sont maintenant branchés sur un
panneau de détail qui déplie la lignée d'un run et son contrat, critère
par critère, avec les quatre états de HOS-221 distingués visuellement.

Un contrat absent affiche « aucun contrat déposé » plutôt qu'un contrat
vide, qui se lirait « tenu ».

### Une collision de libellés

Ma vue s'appelait « Opérations » — comme le **groupe** de navigation qui
la contient. Deux entrées du même nom dans une navigation se cherchent
l'une l'autre. Renommée « Supervision ».

### Ce qui n'est pas démontré

**La vérification en navigateur.** Les deux serveurs de développement en
marche sont antérieurs à ces changements — le backend rend encore `404`
sur `/operations`, et le Cockpit sert un paquet où la vue n'existe pas.
Les redémarrer aurait demandé d'arrêter des processus qui ne sont pas les
miens.

Ce qui **est** démontré : les huit routes servies par
`backend.main:app` avec son lifespan complet, sur les données réelles —
206 approbations en attente, 3 points de reprise, 10 contrôles de santé,
0 fournisseur configuré — et dix gardes sur la vue qui prouvent le
tri-état, les quatre états d'une cause, le nommage des sources et
l'absence de fabrication.

### Mesures

Backend : **5 353 vertes**. Frontend : **123 vertes**, typecheck propre.
13 gardes ajoutées côté backend, 10 côté frontend.


## HOS-234 — Ce que douze jalons ont produit, enfin lisible (2026-09-03)

Le jalon 17. Prémisse mesurée avant d'écrire : **aucune route n'exposait**
le registre des runs (J5), le contrat, les points de reprise (J7), la
portée des approbations (J8), les causes d'échec (J9), le pare-feu (J11),
le courtier (J12), le relais (J13), la boucle (J14) ni la mise à jour
(J16). Douze jalons de travail, invisibles à toute interface.

### Ce qui existait, et qu'il ne fallait pas refaire

`MissionControlService` — 1 242 lignes — et son `MissionControlAPI`, avec
un WebSocket d'événements. La première recherche donnait « 2 routes pour
le registre, 2 pour la boucle » : c'étaient des **commentaires**, l'un
sur le registre de sessions ACP, l'autre sur la boucle d'événements
asyncio. Encore un faux positif de sous-chaîne, et la raison pour
laquelle la mesure s'est poursuivie jusqu'à trouver la vraie surface.

Les huit routes de ce jalon s'y branchent. Aucun service neuf, aucun
magasin neuf.

### Ce que le frontend faisait déjà bien

Contrairement à ce qu'on pouvait craindre, il ne fabrique plus de
compteurs. Les `Math.random()` restants sont des identifiants, une graine
de studio, ou des **commentaires documentant des fabrications retirées** :
`deployment-center` dormait 1 500 ms et rendait `Math.random() * 20 + 30`,
`model-intelligence-center` attendait 600–1 000 ms avant de répondre. Le
commentaire de `telemetry-trace.tsx` dit ce qu'on en a retenu —
« `Math.random()` would have made a prettier picture and a dishonest
one ».

Une garde le vérifie désormais plutôt que de l'espérer, en exemptant les
graines : un aléa **demandé** est le contraire d'une mesure inventée, et
la distinction est dans l'intention, donc dans le nom.

### Une vue, jamais un second runtime

Les huit routes sont en `GET` seulement, et deux gardes sur l'arbre
syntaxique le tiennent : le modèle de lecture n'appelle rien qui écrive —
`ouvrir`, `terminer`, `prendre`, `restaurer`, `appliquer`, `decide`,
`signaler_echec` — et n'importe aucun magasin.

La raison n'est pas esthétique. Une vue qui écrit devient un second
chemin vers l'état, et deux chemins vers l'état, c'est la question
« lequel fait foi ? » à chaque incident.

### Chaque section dit d'où elle vient

`source` accompagne chaque bloc : `backend.runs.registre`,
`backend.ral.courtier`, `backend.security.approvals`,
`backend.checkpoints`, `backend.maj`. Une vue qui nomme ses sources rend
la fabrication visible au relecteur suivant.

### Ce qui est absent est dit absent

Un système indisponible rend `disponible: false` **avec sa raison**,
jamais un zéro. Un zéro se lit « rien ne s'est passé » ; une
indisponibilité se lit « on ne sait pas ». C'est la règle tri-état de
HOS-222 appliquée à l'affichage — et c'est là qu'elle compte le plus,
parce que c'est là qu'un humain décide.

Une section qui lève ne fait pas tomber la vue : les autres sont
justement ce qu'on regarde quand une chose va mal.

Et « aucun fournisseur configuré » est marqué comme un **état normal** :
aucune clé n'est posée par défaut, et le taire le ferait lire comme une
panne.

### Le vocabulaire des jalons traverse jusqu'à l'affichage

Une cause non démontrée reste `null`, jamais « inconnue » (HOS-225). Les
critères invérifiables sont **séparés** des critères violés (HOS-222). Un
point de reprise dit s'il porte l'état de mission, parce que sans lui il
ne ramène que la moitié (HOS-223). Les portées d'approbation vivantes
sont listées à part des accords exacts, parce qu'une ligne qui autorise
un dossier entier ne se lit pas comme une qui autorise une action
(HOS-224).

### Une version fabriquée, retirée

`GET /api/v1/version` rendait `"0.1.0"` en dur, avec une liste de modules
arrêtée à `HOS-028` — donc une version qui ne désignait rien et une liste
fausse depuis deux cents jalons.

Elle rend maintenant la version produit (HOS-232) **et** la version
installée (HOS-233), qui peuvent différer : c'est précisément l'écart
qu'on veut voir après une mise à jour dont le marquage n'a pas eu lieu.
Le test qui gardait `"0.1.0"` est **amendé, pas supprimé** — même
propriété, valeur réelle.

### Ce qui reste hors périmètre

Les **vues React** — Agent Control Rooms, trace d'exécution vivante,
analytiques. Elles sont une pièce en soi, et elles n'étaient pas
constructibles avant : il n'y avait rien à afficher. C'est maintenant le
cas.

### Mesures

Vérifié sur l'installation réelle : 206 approbations en attente, 3 points
de reprise, 10 contrôles de santé, 0 fournisseur configuré. 20 gardes
ajoutées, 1 amendée. Suite complète : **5 340 vertes**, 3 ignorées.


## HOS-233 — Le moteur de mise à jour, pour de bon (2026-09-03)

J16.1. HOS-232 sauvegardait l'état et le restaurait ; il ne touchait pas
au code. Le moteur n'était donc pas un moteur de mise à jour — c'était un
filet. Audit d'abord, trois défauts mesurés, puis le reste.

### Le défaut que la garde de J16 n'a pas vu

`workflows` vit sous la racine d'état **réelle** — huit dossiers sur le
disque, sept déclarés dans `SOUS_DOSSIERS`. Un résidu de la migration
HOS-215, dont la classification a été annulée depuis mais dont la copie
est restée.

La garde de HOS-232 ne l'a pas trouvé **parce qu'elle lit le code et non
le disque**. Elle cherchait `racine() / "..."` dans les sources : un
dossier créé par un chemin qui n'a plus de producteur lui est invisible.

D'où les **trois sources** du jalon :

1. la liste déclarative, `preserve_set()` ;
2. l'**observation du disque** — tout répertoire présent sous la racine
   et absent de la liste est sauvegardé quand même, et signalé ;
3. le **manifeste** de la sauvegarde, qui porte les deux et fait foi au
   retour arrière.

Perdre la donnée serait pire que la sauver sans l'avoir déclarée. Mais
le silence serait pire encore — c'est ainsi que `checkpoints` est passé,
puis `workflows`.

### Le secret de l'utilisateur vit dans l'arbre de code

Mesuré : `SettingsConfigDict(env_file=".env")` résout depuis le
répertoire courant, donc **à la racine du dépôt**. La clé OpenRouter vit
dans l'arbre que la mise à jour remplace, et un remplacement naïf
l'aurait détruite.

Elle est donc **préservée en place** : ni copiée, ni remplacée. Pas
copiée parce qu'une sauvegarde de secret est un secret de plus, en clair,
dans un dossier que personne ne surveille. Pas remplacée parce qu'elle
est à l'utilisateur. Quatre gardes négatives vérifient qu'un secret de
test ne se retrouve ni dans la sauvegarde, ni dans le manifeste, ni dans
les journaux, ni dans le rapport de santé — le **nom** `.env` y figure,
lui, pour qu'un lecteur puisse vérifier qu'il a été protégé.

### Le remplacement, et ce que Hermes doit protéger en plus

Le patron vient d'Agent OS, dont l'`UPDATE.md` le dit sans détour :
*« what an update DOES replace: the app code itself »*, avec une
sauvegarde datée de l'ancienne version à côté.

Trois choses qu'ils n'ont pas à protéger, et Hermes si :

- **le dépôt git** — leur dossier d'application n'en est pas un. Ici
  `.git` porte l'historique, la branche, l'index et le travail non
  commité. Un test avant/après vérifie que `HEAD`, la branche, l'index
  et un fichier non commité survivent à une mise à jour réussie ;
- **le `.env`**, ci-dessus ;
- **`.venv` et `node_modules`** — des gigaoctets qui se reconstruisent.
  Les sauver ferait de chaque mise à jour une copie de plusieurs minutes,
  donc une mise à jour qu'on ne lance pas.

La règle tient en une phrase : **ce qui est remplacé est sauvegardé ; ce
qui est préservé en place n'est ni sauvegardé ni remplacé.** Il n'y a pas
de troisième catégorie, et c'est ce qui rend le retour arrière exact.

### L'ordre, et ce qu'il coûte de se tromper

    paquet → compatibilité → sauvegarde état → sauvegarde code
          → remplacement → migration → self-check → marquage
                                    ↘ échec → retour arrière (code puis état)

Le **paquet est validé avant toute sauvegarde** : un paquet refusé ne
doit rien coûter, et surtout pas laisser une sauvegarde orpheline.
Mesuré : un paquet sans `hermes.json` produit zéro étape et zéro
sauvegarde.

Le retour arrière remet le **code d'abord**, l'état ensuite : restaurer
un état ancien sous un code neuf donnerait le seul état que rien ne sait
lire.

### Un défaut trouvé par un test que j'écrivais

`restaurer()` sautait les dossiers absents de la sauvegarde. Une
sauvegarde vidée restaurait donc **zéro dossier** et se déclarait
réussie : une perte de données silencieuse déguisée en retour arrière.

Le test `un_echec_de_retour_arriere_est_fatal` l'a pris en défaut avant
que quiconque s'en serve. `restaurer()` vérifie maintenant, **avant
d'écrire**, que tout ce que le manifeste annonce est présent, et lève
sinon. Un backup non restauré n'est pas une preuve de rollback.

### La compatibilité : aucune mise à jour aveugle

Quatre cas décidés. Une **installation sans version** est acceptée —
c'est le cas de toutes celles qui existent, et la refuser interdirait la
première mise à jour à tout le monde. Une version **trop ancienne** est
refusée. Un **retour en arrière** est refusé par cette porte : c'est un
`restaurer()`, pas un `appliquer()`, et cette porte n'a pas les
migrations descendantes. **Réinstaller la même version** est permis :
c'est une réparation légitime.

### Les migrations : le cas A constaté, le cas B gardé

**Le mécanisme vivant est `memory/db.py::_add_missing_columns`.** Il
tourne à chaque `init_db()`, ajoute les colonnes nullables que les
modèles déclarent, et **refuse bruyamment** les non-nullables —
« Schema drift needs a real migration ». C'est lui qui a porté les
colonnes de portée d'approbation (HOS-224) sur les bases existantes. Il
est dans le self-check, puisque celui-ci appelle `init_db`.

**`MigrationManager` reste dormant.** Il a un vrai `migrate()` et des
migrations codées en dur à la version 1, et il est orphelin depuis
HOS-221. Deux moteurs de schéma sur la même base, c'est la question
« lequel fait foi ? » à chaque incident. Un test tombe si quelqu'un le
rebranche.

Aucun troisième moteur n'est écrit : il n'y a pas de besoin réel, et en
écrire un sans besoin produirait du code que rien n'exerce.

### Le self-check touche à dix invariants

Racine d'état, registre des runs, base applicative, approbations,
configuration, bus d'événements, RAL, instantanés de mission, points de
reprise, interpréteur de Hermes Agent. Chacun **ouvre** ce qu'il vérifie.

Il rend un rapport **structuré** et non un booléen : « ça ne va pas » ne
dit ni quoi restaurer ni quoi réparer. Et chaque contrôle est tri-état —
`INDISPONIBLE` n'est pas un échec, parce qu'une installation neuve n'a
pas de points de reprise et qu'en exiger un ferait échouer la première
mise à jour de tout le monde.

Sur l'installation réelle : neuf `ok`, un `sans objet`.

### L'état opérationnel est recalculé, pas restauré

Un cooldown de fournisseur décrit **maintenant**, et un retour arrière
change ce maintenant. Le restaurer réappliquerait un écart décidé pour un
incident qui appartenait à l'installation d'avant.

Constaté sur le code plutôt que décrété : le courtier (HOS-228) est déjà
sans état persistant, et son propre commentaire le dit. Il est remis à
zéro explicitement après un retour arrière, plutôt que de compter sur un
redémarrage qui n'aura peut-être pas lieu.

### Ce qui reste hors périmètre, et pourquoi

Le **téléchargement**. `appliquer()` reçoit un chemin vers un répertoire
local déjà extrait. D'où vient ce chemin est la question du canal de
distribution, qui n'existe pas — et une archive poserait en plus la
question de ce qu'on fait d'un `..` à l'intérieur, qui est un problème de
sécurité à part entière. Un test vérifie que les trois modules n'ont
gagné ni `httpx`, ni `urllib`, ni `subprocess`, ni `socket`.

### Mesures

46 gardes ajoutées, 26 amendées ou conservées. Suite complète :
**5 320 vertes**, 3 ignorées.


## HOS-232 — Mettre à jour sans perdre ce que quinze jalons ont construit (2026-09-03)

Le jalon 16. La prémisse était juste — `installer/` fait 378 lignes et ne
contient que de la détection — mais en la vérifiant, deux choses de plus
sont apparues, dont une grave.

### Le défaut : `preserve_set()` ne couvrait pas les points de reprise

HOS-215 a écrit la liste de ce qu'une mise à jour ne doit jamais toucher.
HOS-223 a créé `checkpoints` sous la même racine **deux jalons plus
tard**, hors de la liste. Rien ne l'a signalé, pour une raison simple :
**rien ne consommait `preserve_set()`**.

Une mise à jour aurait donc effacé les points de reprise — c'est-à-dire
le seul moyen d'annuler ce qu'elle aurait cassé. Le défaut que HOS-215
avait fermé, rouvert par le jalon qui construisait le filet.

La correction n'est pas d'ajouter un nom à la liste. C'est
`test_tout_ce_qui_vit_sous_la_racine_est_preserve`, qui **lit le code** —
qui écrit où sous la racine — plutôt que de relire la liste. Aucune
relecture de la liste n'aurait trouvé ce trou : il fallait regarder
ailleurs. **Une liste que rien ne vérifie contre la réalité est une liste
qui dérive.**

### Hermes OS n'avait pas de version

Trois versions existaient dans le dépôt — `SNAPSHOT_VERSION` pour le
format des instantanés, `SCHEMA_VERSION` pour le graphe de mission,
`_KT_VERSION` pour une bibliothèque tierce — et **aucune ne désignait le
produit**.

On ne revient pas à une version qu'on n'a jamais nommée. Elle est écrite
sous la racine d'état et non dans le dépôt, parce que la question « d'où
viens-je ? » se pose au moment précis où le dépôt vient d'être remplacé.
Une version illisible vaut `0.0.0` plutôt que de lever : lever
bloquerait exactement l'installation qui vient réparer.

### La séquence, et son ordre

    sauvegarde → migration → installation → validation → marquage
                                                     ↘ échec → retour arrière

**La sauvegarde d'abord** : après elle, tout est réversible. C'est le
seul échec qui arrête avant d'avoir rien touché, et c'est celui qu'il faut
arrêter — sans sauvegarde, rien ne l'est.

**Le marquage en dernier**, après la validation. Posé avant, il ferait
croire à une mise à jour réussie qui ne l'est pas, et le retour arrière
suivant repartirait du mauvais point. Une garde sur l'arbre syntaxique
tient l'ordre — par **numéro de ligne**, une première version comparant
des positions de parcours en largeur qui ne voulaient rien dire.

Mesuré de bout en bout : une installation qui saccage la base et supprime
un point de reprise avant d'échouer laisse, après retour arrière, la base
intacte, le point de reprise revenu et la version inchangée.

### Trois choix qui rendent le retour arrière honnête

**La sauvegarde porte sa propre liste.** Un retour arrière restaure ce
qui a été **sauvé**, pas ce que la version d'aujourd'hui croit qu'il
fallait sauver — une version qui aurait ajouté un dossier ne doit pas
prétendre le restaurer depuis une copie qui ne le contient pas.

**Il retire avant de copier.** Une copie par-dessus laisserait les
fichiers que la version fautive a créés, et un état mi-ancien
mi-nouveau est pire que l'un ou l'autre.

**Un retour arrière impossible est dit fort.** L'installation a échoué
*et* le retour aussi : c'est le pire cas, et le taire laisserait un état à
mi-chemin que personne ne sait diagnostiquer.

### L'auto-vérification touche à la vraie base

Elle ouvre le registre des runs. Une auto-vérification qui ne ferait
qu'importer des modules passerait sur une base corrompue — un test sur
l'arbre syntaxique l'exige.

### Ce qui n'est délibérément pas écrit

Le **remplacement du code** : télécharger une version, échanger
l'arborescence. Cela demande un canal de distribution qui n'existe pas, et
l'écrire sans lui produirait un mécanisme non éprouvable. La fonction
d'installation est donc **injectée**, ce qui rend la séquence testable
pour de bon — avec une installation qui échoue exprès. Un test vérifie
que le module n'a gagné ni accès réseau ni lancement de processus.

### Mesures

26 gardes ajoutées. Suite complète : **5 274 vertes**, 3 ignorées.


## HOS-231 — Ne pas juger un modèle sur un échec qui n'est pas le sien (2026-09-03)

Le jalon 15. La prémisse avait déjà été corrigée : `update_performance` et
`record_feedback` **sont** branchés, via
`service_registry._record_feedback` → `RealTaskExecutor.on_execution`. Ce
qui manquait était plus précis, et mesuré :

- `ModelPerformanceRecord.error_type` existe depuis HOS-062 et **n'est
  renseigné par personne**. Deux modules le relisent ; aucun ne l'écrit.
- `update_performance` compte `success=False` dans
  `historical_success_rate` **quelle qu'en soit la raison**. Un refus
  d'admission VRAM, un quota épuisé, une coupure réseau et une mauvaise
  réponse abaissaient identiquement la note du modèle.

C'est le thème central du dépôt appliqué à sa propre télémétrie : *ni un
échec sur parole*. Sur huit défauts de mesure trouvés pendant la
construction du catalogue, **cinq produisaient de faux échecs** — et ce
mécanisme-ci les aurait tous inscrits au passif du modèle.

### La table des causes imputables tient en trois entrées

`modele`, `semantique`, `verification`. Le reste décrit la machine, le
réseau ou une décision humaine, jamais la compétence de ce qui a été
appelé.

Deux absences délibérées, et ce sont les plus importantes :

**`contexte` n'y est pas.** C'est le cas le mieux documenté du dépôt.
CLAUDE.md : « une réponse tronquée n'est pas une erreur de raisonnement
et ne doit pas se noter comme telle ». Le départage de code a coupé
qwen3.6-35b en plein milieu et l'a noté comme une faute, alors que
c'était le réglage de la fenêtre qui était en cause.

**`inconnue` n'y est pas non plus.** Attribuer au modèle ce qu'on n'a pas
su expliquer est exactement la façon dont on a déjà disqualifié des
modèles compétents.

### Vide et « inconnue » ne disent pas la même chose

Une cause **vide** signifie « personne n'a transmis de cause » — un
appelant d'avant ce jalon — et son comportement est conservé : l'échec
compte, comme avant. Une cause `inconnue` signifie qu'on a cherché sans
trouver. Seul le second état veut dire qu'on a regardé, et les confondre
aurait fait disparaître en silence toutes les notes d'échec des
producteurs non migrés.

### La trace reste complète

L'échec a eu lieu : c'est le **jugement** qui est étroit, pas la trace.
Les onze lignes de l'essai — sept non imputables, deux imputables, deux
réussites — sont toutes dans l'historique. Un historique amputé rendrait
impossible de savoir qu'un modèle tombe systématiquement sur des refus de
VRAM, ce qui est une information réelle, sur autre chose que sa
compétence.

### Le chemin, de bout en bout

`RealTaskExecutor` classe l'exception avec la taxonomie de HOS-225 aux
**cinq** sites d'échec — une garde sur l'arbre syntaxique vérifie
qu'aucun n'est oublié, un site manquant laissant passer des échecs non
classés que le profileur compterait comme avant, sans que rien le dise.

Le rappel `on_execution` reçoit la cause en argument supplémentaire, et un
appelant d'avant ce jalon qui ne l'accepte pas continue de fonctionner :
la télémétrie ne fait jamais échouer le travail qu'elle décrit.

### Ce que le Trust reste

Une donnée **décisionnelle**, pas une autorité de sécurité. Aegis reste
au-dessus, et rien ici ne décide d'autoriser quoi que ce soit.

### Mesures

20 gardes ajoutées. Suite complète : **5 248 vertes**, 3 ignorées.


## HOS-230 — La boucle, assemblée et non recréée (2026-09-03)

Le jalon 14. Prémisse mesurée : **deux pilotes de reprise existent, et
aucun ne connaît de contrat.**

- `node_execution` fait tourner un `while task.status == PENDING`. Il
  reprend les pannes de **runtime**, parce que `execute_task` remet la
  tâche en attente ; il ne sait rien de ce qui devait être vrai à la fin.
- `retry_policy.decide` travaille au niveau de la **mission**, uniquement
  sur contradiction, et `graph_executor._suggest_retry` **publie** au
  lieu de relancer — avec sa raison, qui est juste : « relaunching a
  mission graph is the caller's decision (it owns scheduling, budgets and
  the operator's consent) ».

Ce module ne contredit pas ce choix. La boucle est une **bibliothèque que
l'appelant pilote**, pas un relanceur caché : `tourner()` ne part que si
quelqu'un l'appelle, et rend ce qu'elle a constaté.

### Ce n'est pas une seconde boucle agentique

La règle qui prime sur tout dans ce dépôt a déjà été violée une fois —
`RealTaskExecutor` sélectionnait Hermes Agent puis l'écrasait deux lignes
plus bas par sa propre boucle d'outils, et
`test_hermes_agent_is_the_brain.py` en garde la trace.

Cette boucle-ci ne raisonne pas, ne choisit aucun outil et **n'appelle
aucun modèle**. Elle enchaîne deux fonctions que l'appelant lui fournit
et décide seulement de continuer ou de s'arrêter, sur des verdicts et des
causes mesurés ailleurs. Un test sur l'arbre syntaxique vérifie qu'elle
n'importe ni client, ni adaptateur, ni runtime : c'est de
l'ordonnancement, pas de la cognition.

### Six arrêts, parce qu'ils n'appellent pas la même suite

`contrat_tenu`, `budget`, `cause_non_reprenable`, `inverifiable`,
`erreur`, `sans_contrat`. Les fondre en un booléen ferait chercher un
défaut de compteur là où il y a un refus assumé — exactement l'erreur que
HOS-225 avait déjà eu à corriger dans l'abandon d'une tâche.

Trois de ces arrêts portent tout l'intérêt du jalon :

**`inverifiable` arrête sans user le budget.** On ne reprend pas sur une
ignorance, et surtout on ne la range pas du côté du succès (HOS-222).
Boucler ici dépenserait le budget à re-produire une mesure qui n'aboutit
pas.

**`cause_non_reprenable` arrête au premier tour.** Réessayer un refus de
politique inonde la file d'approbation — ce que `approvals.py` décrit
déjà. La taxonomie de HOS-225 le dit, la boucle l'applique.

**`sans_contrat` refuse de tourner.** Boucler sur rien produirait des
tours qui se déclareraient réussis parce qu'aucun critère ne les
contredit : le `success: true` au-dessus de rien, en boucle.

### Le verdict du vérificateur ne suffit pas

Un vérificateur qui dit « réussi » sur un contrat à trois critères dont
un seul est tenu ne clôt rien : la **conjonction du contrat** prime, et
c'est elle qui décide. Une vérification illisible vaut `INDISPONIBLE`,
jamais `REUSSI` par défaut d'information.

### Le point de reprise est proposé, jamais appliqué

La boucle prend un point de reprise avant le premier tour — une fois, pas
un par tour — et rend son identifiant. Elle ne restaure **jamais** d'elle
-même : l'appelant décide, et la restauration passe par Aegis (HOS-223).
Une boucle qui effacerait un workspace de son propre chef serait le geste
destructeur le moins surveillé du système. Un test sur l'arbre syntaxique
vérifie qu'aucun appel de restauration n'y figure.

### Assembler, pas recréer

Tout vient d'ailleurs, et c'est le point : le contrat et sa conjonction
(HOS-221), le verdict tri-état (HOS-222), le point de reprise (HOS-223),
la cause et son remède (HOS-225), le relais et ses phases (HOS-229). Le
budget par défaut est celui de `retry_policy`, et un test le vérifie —
deux valeurs qui divergent, c'est deux politiques de reprise.

### Mesures

20 gardes ajoutées. Suite complète : **5 228 vertes**, 3 ignorées.


## HOS-229 — Ce qui doit survivre au changement de modèle (2026-09-03)

Le jalon 13. Deux manques mesurés avant d'écrire une ligne.

**Le contrat n'arrivait jamais au modèle.** HOS-221 a créé `Contrat` —
ce qui doit être vrai à la fin — **et** la colonne `contrat` du registre
des runs. Vérifié : rien n'y écrivait, rien ne l'y relisait, et
`backend.runs.contrat` n'était importé que par `verification.py`, pour
son énumération `Verdict`. Le modèle chargé de satisfaire des critères ne
les voyait pas.

**Aucune preuve de vérification n'atteignait un prompt.** `retry_policy`
construit bien un mémoire de reprise à partir du verdict, mais au niveau
de la *mission* et seulement sur contradiction. Une tâche qui vient
d'être vérifiée ne sait pas ce que la vérification a dit.

### Un relais, et pas une session

`_upstream_results_for` portait déjà la règle dans son commentaire :
« carried as plain text on purpose: it has to survive the model being
swapped between two tasks, which anything held as KV cache or a provider
session would not ». Le relais l'applique aux **phases**.

Sur 16 Gio, Hermes ne fait pas tourner quatre modèles à la fois ; il
enchaîne — planificateur cloud, exécutant local, vérificateur cloud,
réparateur local. Entre deux flèches, le modèle change, le fournisseur
peut changer, et le processus distant n'a aucune mémoire du tour
précédent. **Ce qui n'est pas écrit dans le relais n'existe pas au tour
suivant.**

### Chaque phase reçoit ce dont elle a besoin, et pas le reste

Un relais qui donnerait tout à tout le monde serait un prompt géant, et
un prompt géant sur 16 Gio est une fenêtre qui se ferme.

- **planification** : l'objectif et les outils. **Pas le contrat** — elle
  est censée le produire, et le lui donner ferait planifier contre des
  critères qu'on lui demande d'établir.
- **exécution** : le contrat, les résultats amont, les outils. Pas
  l'échec du tour précédent : une première exécution n'a rien raté.
- **vérification** : le contrat, les artefacts, les preuves — et **pas**
  le contexte de l'exécutant. Un vérificateur à qui l'on montre
  l'intention juge l'intention : c'est exactement le défaut du
  2026-08-30, où le relecteur a accepté l'image conforme au prompt et
  rejeté la bonne.
- **réparation** : tout cela, plus **ce qui a échoué** et sa cause.

Les décisions déjà prises vont à toutes les phases : une phase qui ignore
qu'une approbation a été refusée reproposera la même action.

Et « aucun artefact » est écrit comme un constat à faire remonter, pas
comme un silence.

### Le rôle `double_check`, enfin routé

Les rôles de `config/models.yaml` existaient tous — `swift`, `standard`,
`code`, `reasoning`, `double_check`… — et étaient choisis par **type de
tâche**. Rien ne les reliait à une **phase**. `double_check` est le cas
qui le montre : configuré depuis HOS-065C, et **aucune vérification n'y
était jamais routée**.

La vérification va donc à un autre rôle que l'exécution, pour une raison
simple : un modèle qui relit sa propre sortie confirme sa propre sortie.
Un test vérifie que chaque rôle nommé existe bien dans la configuration —
un rôle absent se résoudrait en silence sur autre chose, et la phase
tournerait sur un modèle que personne n'a choisi.

### La quarantaine n'est pas contournable par le relais

Le relais porte de la mémoire, et il la passe par `confiance.filtrer`.
Un souvenir d'origine non humaine n'entre pas dans un prompt parce qu'il
transite par un chemin neuf — c'était précisément le vecteur que HOS-216
ferme, et un relais non instrumenté l'aurait rouvert. Le drapeau
`inclure_quarantaine` est nommé et faux par défaut, comme celui de
`search()`.

### Ce qui reste honnêtement vide

`prepare(contrat=None)` est le défaut, et le restera jusqu'au jalon
suivant : **rien ne dérive aujourd'hui un contrat d'un objectif en
prose**. Le chemin est complet et testé de bout en bout — déposé au
registre, relu par le résolveur, inséré dans le prompt — et il attend son
appelant plutôt que d'inventer des critères que personne n'a écrits.

### Mesures

20 gardes ajoutées. Suite complète : **5 208 vertes**, 3 ignorées.


## HOS-228 — Le courtier, et la cinquième prémisse fausse (2026-09-03)

Le jalon 12. La roadmap annonçait « le disjoncteur de `task_executor`
(`_record_failure`) et la santé de runtime sont réels et branchés » — une
ligne que j'avais **moi-même écrite** deux jalons plus tôt, en corrigeant
les précédentes. Vérifiée avant d'écrire :

- `_record_failure` incrémente `self._failures`, qui n'est **lu qu'une
  seule fois**, pour une ligne de statistiques. Rien n'ouvre de circuit.
  C'est un compteur, pas un disjoncteur.
- `RecoveryManager` a une vraie logique de cooldown et de backoff, et
  **n'est instancié nulle part** hors des tests. Cinquième orphelin,
  après `approvals`, `DatabaseManager`, `MigrationManager` et le
  `backup_path` de `propose_write`.
- `has_quota`, en revanche, **est** consommé : `AdaptiveRouter` l'appelle
  via `catalog.has_budget`. Cette partie du diagnostic était juste.

Corriger une prémisse ne garantit donc pas d'avoir mesuré la suivante.

### Pourquoi pas `RecoveryManager`

Il **exécute une reprise** sur un composant — le redémarrer. Un courtier
**s'abstient de choisir** un fournisseur pendant un temps. Deux verbes
différents : le réutiliser demanderait d'enregistrer une action de reprise
vide pour n'en garder que la comptabilité de cooldown, c'est-à-dire de le
plier jusqu'à ce qu'il ne dise plus ce qu'il dit. Un test garde ce
raisonnement et tombe si quelqu'un le rebranche.

### Le cycle, fermé

    429 → QUOTA → fournisseur B          et non
    429 → même fournisseur → 429 → …

Mesuré de bout en bout : deux appels consécutifs sur un fournisseur qui
rend 429 produisent **un seul appel HTTP réel**. Le second n'est pas
tenté.

La taxonomie de HOS-225 nomme la cause ; le courtier en tire une durée
d'écart. Elles diffèrent selon la cause, et c'est tout l'intérêt :

- **quota** — 60 s, la même valeur que `remede(QUOTA).attendre_s`, et
  pour la même raison : le pool gratuit est partagé par clé et se réarme
  à la minute ou à la journée ;
- **fournisseur** et **ressource** — 10 s ; mais trois échecs consécutifs
  disent autre chose, et le circuit s'ouvre pour deux minutes ;
- **modèle, sémantique, vérification, contexte, outil, politique,
  sécurité, inconnue** — n'écartent **personne**. Un modèle qui rend une
  sortie inutilisable ne dit rien de la santé d'OpenRouter, et l'écarter
  pour ça ferait basculer sur le local une charge que le cloud servait
  très bien.

La table des causes écartantes tient en trois entrées, et un test le
vérifie : une table qui écarterait sur tout ferait basculer au premier
ennui, pour n'importe quelle raison.

### Un succès referme

Sans ça, un disjoncteur ouvert par un incident passager tue le
fournisseur jusqu'au redémarrage — ce qui ressemble exactement à un
fournisseur en panne, et se débogue mal. Un succès remet aussi le
compteur à zéro, sans quoi il additionnerait des échecs séparés par des
réussites.

### Le tri-état, encore

Un quota **non mesurable** écarte, comme un quota épuisé : on ne dépense
pas sur une mesure qu'on n'a pas. Mais une mesure périmée n'écarte plus —
s'y fier retirerait un fournisseur dont le quota s'est réarmé entre-temps,
et le pool gratuit se réarme à la minute.

### Deux refus de conception

Le courtier **ne va pas chercher** le quota lui-même : il serait alors
synchrone sur le réseau au milieu d'une décision de routage. Il le reçoit
de qui l'a mesuré.

Et il **n'a pas d'état persistant** : un redémarrage repart avec tous les
fournisseurs disponibles. Un écart est une réaction à un incident en
cours ; le faire survivre au redémarrage écarterait un fournisseur pour
une panne d'hier.

### Trace

`cloud.fournisseur_ecarte` **et** `cloud.fournisseur_retabli` : un écart
sans rétablissement visible ressemble à une panne définitive. Déclarés
dans les deux endroits que HOS-227 a mis au jour — le catalogue à côté du
producteur, que lit `collect_known_topics()`, et `BASELINE_TOPICS`, que
lit l'`EventHub`.

### Mesures

29 gardes ajoutées. Suite complète : **5 188 vertes**, 3 ignorées.


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

