# Frontend — points remontés, à traiter après ACP

Relevé le 2026-08-13, après la refonte visuelle SODIUM. Ces points n'avaient
jamais été poussés jusqu'au bout ; ils sont consignés ici pour ne pas se
perdre entre deux chantiers backend.

**Moment choisi : après la refonte ACP.** ACP change ce qu'il y a à
afficher — pensées de l'agent en streaming, demandes d'approbation,
sessions reprises. Refaire l'UI avant reviendrait à la refaire deux fois.

## Bug transverse, prioritaire

**Une tâche lancée disparaît en changeant d'onglet.** On lance une exécution
dans un Center, on navigue ailleurs, on revient : la page est vierge comme si
rien n'avait été lancé. Le travail continue côté backend — c'est l'état
client qui est perdu.

Piste : l'état vit dans le composant et meurt à son démontage. Il devrait
venir d'une requête sur l'état serveur réel (mission/goal en cours), pas
d'un état local. C'est aussi ce qui rendrait l'affichage correct après un
rechargement de page ou un redémarrage du backend.

À traiter en premier : il touche les trois Centers ci-dessous et sape la
confiance dans tout le reste.

## Assistant

- **Persistance des conversations.** Aujourd'hui `ConversationManager` garde
  les sessions dans un `dict` en mémoire (`self._sessions`) : tout est perdu
  au redémarrage du backend. Il faut un stockage durable, sur le modèle de
  ce qui a été fait pour `UnifiedMemory` en HOS-098.
- **Retrouver une conversation passée**, avec un résumé pour s'y
  reconnaître. Dépend de la persistance ci-dessus.
- **Sélection automatique du modèle à revoir.** Les rôles ont changé depuis
  les mesures du 2026-08-12 : `devstral` s'est révélé incapable de mener une
  écriture sur cette machine, `lfm2.5-2.6b-128k` est devenu le repli
  agentique, de nouveaux modèles ont été installés. La sélection doit
  s'appuyer sur les mesures réelles (`agentic_probe`) et non sur des rôles
  figés dans la configuration.

## Mission Center

- **Voir la décomposition réelle.** « 0/7 tâches » ne dit pas *quelles*
  tâches. Il faut la liste des nœuds, leur état, leurs dépendances — le DAG
  est déjà construit côté backend, il n'est simplement pas exposé.
- **Résultats plus poussés.** Le panneau de rapport existe (tabs Résumé /
  Résultats / Erreurs) mais gagnerait à montrer les artefacts vérifiés, les
  outils réellement appelés et le verdict de `MissionVerification` — la
  distinction entre « rapporté réussi » et « vérifié sur disque » est
  précisément ce qui différencie ce produit.

## Autonomous Center

- **Audit complet requis** — jamais retesté depuis la refonte.
- **Ajouter un fil conversationnel** comme dans Assistant : que l'agent
  explique ce qu'il fait et où il en est, au lieu d'un compteur muet. ACP
  fournit exactement la matière (`AgentThoughtChunk` en streaming).

## Transverse

- **Optimiser le contexte par modèle selon son usage réel.** Un modèle
  d'embedding n'a pas besoin du contexte d'un agent — leçon coûteuse de
  HOS-093, où un réglage global a fait passer un modèle de 0,64 Go à 5,88 Go
  de VRAM. La voie propre est un Modelfile par usage
  (`PARAMETER num_ctx`), pas `OLLAMA_CONTEXT_LENGTH`.

## Questions à trancher avec l'utilisateur avant de coder

Posées le moment venu, pas maintenant :

1. La persistance des conversations doit-elle être infinie, ou purgée après
   N jours / N conversations ?
2. Le fil Autonomous doit-il montrer *toutes* les pensées de l'agent, ou
   seulement les décisions et les appels d'outils ? (Le premier est
   volumineux et coûte du contexte à l'affichage.)
3. Les approbations humaines (ACP `request_permission`) : bloquantes dans
   l'UI, ou file d'attente consultable ?
4. La décomposition d'une mission doit-elle être modifiable avant lancement,
   ou seulement consultable ?
