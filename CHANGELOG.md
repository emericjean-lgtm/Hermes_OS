## HOS-186 — Revue des controles : un appel dans le vide, un projet indelebile (2026-08-26)

### Ce que la revue a mesure

Releve statique de tous les controles interactifs du Cockpit :

    97 boutons, 111 gestionnaires onClick, 38 champs, 51 onChange
    0 gestionnaire vide, 0 controle desactive en dur, 1 bouton sans onClick
      (un submit dans un formulaire — legitime)

Aucun bouton mort. Mais un bouton branche peut appeler une route qui
n'existe pas, et ce releve-la ne le voit pas. Confrontation des **139
appels** de `client.ts` aux **338 routes** du contrat OpenAPI :

    missionsClient.timeline  ->  GET /missions/{id}/timeline  ABSENTE

Le backend sert onze routes de mission ; celle-la n'en fait pas partie. Le
hook `useMissionTimeline` n'avait **aucun consommateur** : le defaut n'a
donc jamais ete visible.

### Le test qui aurait du le voir en prouvait le contraire

    expect(typeof missionsClient.timeline).toBe("function");

Il verifiait qu'un objet que nous avions ecrit contenait bien ce que nous y
avions mis. C'est la tautologie que `backend/mission/tests_tautologiques.py`
traque dans le code livre, arrivee cette fois dans notre propre suite.

Remplace par `test_les_appels_du_cockpit_visent_de_vraies_routes.py`, qui
compare les chemins ecrits au schema construit depuis l'application. Il
n'appelle rien : les verbes destructeurs sont verifies comme les autres.

Deux pieges rencontres en l'ecrivant, tous deux consignes dans le fichier :
retirer toute interpolation finale transformait `/autonomous/${goalId}` en
`/autonomous`, qui n'existe pas — un faux negatif pour neuf faux positifs ;
et `/code-intelligence/${kind}` n'est pas une route parametree mais un choix
dans une union fermee de quatre. Le garde developpe l'union plutot que de
l'exempter, et verifie donc les quatre.

### Un projet mal saisi ne pouvait plus etre retire

Le panneau Workspace savait creer et **delier** — delier n'agit que sur le
`localStorage`. La fiche restait en base, et la liste de selection accumulait
les essais rates, alors que `DELETE /projects/{id}` existe et que
`useRemoveProject` etait ecrit, expose, appele par personne.

Suppression ajoutee, en deux temps : un clic arme, le second efface. Une
suppression a un clic dans une colonne dense se declenche par accident, et
celle-ci est irreversible cote serveur.

### Inventaire restant

**21 hooks sur 108** n'ont aucun consommateur. Deux natures : du code mort
(`useStartConversation`, `useSendConversationMessage` — l'Assistant passe
par le client de flux) et des **capacites absentes de l'ecran**
(`useUpdateProject`, `useCreateAgent`, `useStartExecution`). Les seconds ne
sont pas a supprimer mais a brancher, et ce choix appartient a l'operateur.

Retires ici : `useMissionTimeline` (route inexistante) et `useExecuteTool`
(aucun executeur cote serveur, cf. HOS-185).

### Verified

Suites : backend **2 054 passes, 2 ignores** ; frontend **107 passes** ;
`tsc --noEmit` propre.

---

