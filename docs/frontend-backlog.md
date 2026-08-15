# Frontend — points remontés, à traiter après ACP

Relevé le 2026-08-13, après la refonte visuelle SODIUM. Ces points n'avaient
jamais été poussés jusqu'au bout ; ils sont consignés ici pour ne pas se
perdre entre deux chantiers backend.

**Moment choisi : après la refonte ACP.** ACP change ce qu'il y a à
afficher — pensées de l'agent en streaming, demandes d'approbation,
sessions reprises. Refaire l'UI avant reviendrait à la refaire deux fois.

> **Statut revu le 2026-08-15.** Quatre points ont été traités depuis le
> relevé ; ils sont marqués ✅ ci-dessous et **conservés** plutôt que
> supprimés — savoir qu'un point a été soulevé *et* réglé vaut mieux
> qu'une liste qui ne garde que ce qui reste. Le reste est repris dans
> `ROADMAP.md` §C.

## ~~Bug transverse, prioritaire~~ — ✅ HOS-102

**Une tâche lancée disparaît en changeant d'onglet.** On lance une exécution
dans un Center, on navigue ailleurs, on revient : la page est vierge comme si
rien n'avait été lancé. Le travail continue côté backend — c'est l'état
client qui est perdu.

La piste était la bonne : l'état vivait dans le composant et mourait à son
démontage. Il vient désormais d'une requête sur l'état serveur réel, ce qui
rend aussi l'affichage correct après un rechargement de page ou un
redémarrage du backend.

## Assistant

- ✅ **Persistance des conversations** — HOS-101. `ConversationManager`
  gardait les sessions dans un `dict` en mémoire ; elles survivent
  maintenant au redémarrage, sur le modèle de `UnifiedMemory` (HOS-098).
- ✅ **Retrouver une conversation passée** — HOS-101 : `/resume` les liste,
  titrées et supprimables.
- ⬜ **Sélection automatique du modèle à revoir.** Les rôles ont changé depuis
  les mesures du 2026-08-12 : `devstral` s'est révélé incapable de mener une
  écriture sur cette machine, `lfm2.5-2.6b-128k` est devenu le repli
  agentique, de nouveaux modèles ont été installés. La sélection doit
  s'appuyer sur les mesures réelles (`agentic_probe`) et non sur des rôles
  figés dans la configuration.

  *Avancé, pas fini :* le catalogue mesuré existe (HOS-108, sept axes, dix
  modèles) et le routeur ne dégrade plus la qualité en réutilisant un
  résident (HOS-109). Mais **l'Assistant n'a pas de mode automatique** : le
  classifieur n'a aucun appelant. À câbler — ou à retirer.

## Assistant — « pas accès aux outils » (remonté le 2026-08-15)

Symptôme rapporté : l'onglet Assistant se comporte comme si Hermes n'était
pas relié. **Deux causes candidates, à départager avant de coder quoi que
ce soit** — l'une n'est pas un problème de frontend du tout.

1. **Le backend était mort.** Constaté le 2026-08-15 : rien n'écoutait sur
   le port 8010, alors que l'agent y attend ses seize outils MCP
   (`~/.hermes/config.yaml` → `mcp_servers.hermes-ollama`). Ses journaux le
   disaient : « *Background MCP discovery completed with zero connected
   servers* ». Relancé depuis. **À revérifier d'abord : le symptôme
   persiste-t-il backend allumé ?**
2. **Aucun projet lié à la conversation.** Par construction, les outils de
   fichiers ne sont offerts que si la session porte un projet *actif et
   validé* (`_conversation_tools`, gate `project_root`). Sans lui, seule la
   recherche web est proposée — et c'est voulu, c'est la garantie de
   sécurité de ce chemin. Deux projets valides existent (`HermesE2E`,
   `Skill360`) et `project-panel.tsx` sait les lier.

Si c'est la seconde, le défaut n'est pas l'absence d'outils mais le fait
que **rien ne le dit** : un assistant qui n'a pas ses outils devrait
l'annoncer et indiquer quoi faire, plutôt que de se comporter comme s'il
n'avait jamais été relié. C'est le même principe que partout ailleurs ici —
un état dégradé silencieux est indiscernable d'une panne.

## Mission Center

- ⬜ **Voir la décomposition réelle.** « 0/7 tâches » ne dit pas *quelles*
  tâches. Il faut la liste des nœuds, leur état, leurs dépendances — le DAG
  est déjà construit côté backend, il n'est simplement pas exposé.
  *Revérifié le 2026-08-15 : `mission-center.tsx` affiche toujours le seul
  compteur `Nœuds : X/Y`.*
- ⬜ **Résultats plus poussés.** Le panneau de rapport existe (tabs Résumé /
  Résultats / Erreurs) mais gagnerait à montrer les artefacts vérifiés, les
  outils réellement appelés et le verdict de `MissionVerification` — la
  distinction entre « rapporté réussi » et « vérifié sur disque » est
  précisément ce qui différencie ce produit.

## Autonomous Center

- ⬜ **Audit complet requis** — jamais retesté depuis la refonte.
- ⬜ **Ajouter un fil conversationnel** comme dans Assistant : que l'agent
  explique ce qu'il fait et où il en est, au lieu d'un compteur muet. ACP
  fournit exactement la matière (`AgentThoughtChunk` en streaming).

## Transverse

- ✅ **Optimiser le contexte par modèle selon son usage réel.** Un modèle
  d'embedding n'a pas besoin du contexte d'un agent — leçon coûteuse de
  HOS-093, où un réglage global a fait passer un modèle de 0,64 Go à 5,88 Go
  de VRAM. Réglé par la voie propre : un Modelfile par usage
  (`PARAMETER num_ctx`), pas `OLLAMA_CONTEXT_LENGTH`. Chaque modèle du
  catalogue sert désormais un contexte déclaré et mesuré.

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
