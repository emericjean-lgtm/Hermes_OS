## HOS-144/187/188 — Le routeur peut enfin departager, et l'ecran montre ce que l'agent sait faire (2026-08-27)

### HOS-144, ouvert depuis le 21 aout, referme

HOS-143 avait montre que **toutes** les missions tournaient sur le plus
petit modele, y compris « ecrire les tests unitaires ». HOS-144 en avait
donne la cause sans la corriger : le routeur connait les modeles, mais
leurs profils sont vides. `AdaptiveRouter.recommend()` lit
`profile.task_scores.get(type, 0.5)` — chaque modele rendait donc le meme
neutre, et le departage tombait sur le critere suivant, la taille.

Les mesures existaient dans le magasin de bancs. Rien ne les reliait.

Mesure apres le pont, sur les modeles reellement presents :

    gpt-oss-20b-64k     code_generation 1.00
    muse-glimmer-64k    code_generation 0.94
    qwen3.6-35b-128k    code_generation 0.88
    ornith-9b-256k      code_generation 0.36
    gemma4-12b-256k     code_generation 0.36
    lfm2.5-2.6b-125k    code_generation 0.28

    60 scores verses sur 6 profils ; 4 modeles mesures sans profil
    correspondant, comptes et non avales

Deux refus valent autant que la traduction. **Un axe non mesure ne produit
pas de score** : le magasin omet deliberement les axes absents, et ecrire
`0.0` ferait passer « non mesure » pour « nul ». Sans score, le routeur
retombe sur 0,5, qui dit « je ne sais pas ». **Une note de catalogue
n'ecrase pas une course reelle** : `benchmark_scheduler` ecrit depuis
l'execution effective d'une tache, preuve plus directe qu'une epreuve
synthetique.

Un defaut trouve en chemin : `bench_store.catalogue()` rend les lignes
brutes par axe, c'est la route qui les reduit en `notes`. Le pont lisait la
forme *servie* et rendait un catalogue vide **sans rien dire** — le bilan
affichait trois zeros, dont `sans_profil: 0`, ce qui ne pouvait pas etre.

### Le registre d'outils : ni repare, ni supprime

La decision annoncee etait de le supprimer plutot que de le reparer. La
mesure l'a renversee : **dix modules en dependent**, dont `base_agent.py`,
`conversation/routes.py` et le serveur MCP. Le rayon est trop large pour un
gain incertain.

Fait a la place ce que le projet avait deja fait pour les competences
(HOS-153) : exposer ce que porte le cerveau. `GET /tools/agent` lit
`_ALL_TOOLS` — la liste que `create_mcp_server()` enregistre vraiment — et
rend **71 outils** groupes par famille : 12 de fichiers, 9 de git, 7 de
memoire, 7 de workflows, 6 de projets, 6 de competences, 5 de taches, 4 de
cliches, 2 de verification.

Le Tools Center mene desormais avec eux. Le registre declare reste, sous son
vrai nom — « Registre declare, 16 entrees, sans executeur ».

### La surface d'API, inventoriee au lieu d'etre subie

Dix-huit hooks sans consommateur au releve precedent. Quatre retires :
`useStartConversation` et `useSendConversationMessage` (le flux NDJSON a
remplace ce chemin), `useEvents` (la socket unique du shell alimente le
store depuis HOS-182), `useSkills` (le Skills Center appelle `skillsClient`
en direct). Leurs methodes client restent : elles servent ailleurs.

Un branche : `useUpdateProject`. Le panneau savait creer, delier et — depuis
hier — supprimer, mais pas **corriger**. Une faute de frappe dans un chemin
obligeait a detruire la fiche et a la refaire, en perdant son historique.

Les quatorze restants ne sont pas de meme nature, et c'est pourquoi les
supprimer serait faux : quatre sont des **capacites que le backend sert et
qu'aucun ecran n'offre** — creer un agent, approuver une action en
conversation, choisir des competences pour une tache. Les effacer effacerait
la trace d'une fonction manquante.

`src/__tests__/surface-api.test.ts` les inscrit avec leur raison. Un hook
ajoute sans consommateur fait echouer la suite ; un hook enfin branche aussi,
et il faut alors le retirer de la liste. La dette est declaree, datee, et ne
peut plus grossir en silence.

Le test a attrape deux erreurs de sa propre redaction : il se lisait lui-meme
— les quatorze noms cites y passaient pour des usages — et il a refuse trois
raisons ecrites « idem ».

### Une seconde tautologie dans notre propre suite

    it("useSkills is exported", ...)
      expect(typeof useSkills).toBe("function");

Comme `missionsClient.timeline` hier : verifier qu'une fonction que nous
avons ecrite existe bien. Retiree.

### Verified

Suites : backend **2 063 passes, 2 ignores** ; frontend **110 passes** ;
`tsc --noEmit` propre. `GET /tools/agent` rend 71 outils sur le serveur en
marche, et le Tools Center les affiche groupes par famille.

---

