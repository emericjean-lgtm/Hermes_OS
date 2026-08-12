# Hermes OS — notes pour un agent

Ce fichier ne décrit pas l'architecture : `ARCHITECTURE.md`, `README.md` et
`docs/` le font déjà. Il rassemble ce qui n'est écrit nulle part et qui a
coûté du temps de débogage réel.

## La règle qui prime sur tout

**Hermes Agent (NousResearch, installé sous `%LOCALAPPDATA%\hermes\hermes-agent`)
est le cerveau des missions. Hermes OS est son système d'exploitation.**

Hermes OS fournit runtime, workspace, modèles, sécurité, persistance,
observabilité et UI. Il ne raisonne pas à la place de l'agent, ne choisit
pas ses outils et n'exécute pas de seconde boucle agentique sur le chemin
d'une mission.

Cette règle a déjà été violée une fois : `RealTaskExecutor` sélectionnait
Hermes Agent puis l'écrasait deux lignes plus bas par sa propre boucle
d'outils, si bien que toute mission liée à un workspace — le cas normal —
contournait l'agent. Le garde-fou est
`backend/tests/test_hermes_agent_is_the_brain.py`, dont l'échec porte le
message `HERMES_AGENT_BYPASS_DETECTED`. Ne le contourne pas ; s'il gêne,
c'est probablement lui qui a raison.

## Ne jamais croire un succès sur parole

La leçon centrale du projet. Cinq défauts distincts ont produit des missions
`success: True, 5/5` au-dessus d'un workspace **vide** : la boucle d'outils
concurrente, des toolsets CLI vidés, l'objectif perdu à la décomposition, un
contexte servi à 4096, et un timeout de 180 s. Chacune était invisible dans
le rapport de mission.

En pratique :

- Un artefact se vérifie **sur le disque**, jamais d'après le texte du modèle.
- `success = true` n'est pas une preuve ; `exit 0` non plus.
- `backend/mission/verification.py` compare le workspace avant/après et émet
  `mission.unverified` quand une mission réussit sans rien changer.
- Quand quelque chose échoue, lire le tableau `errors` des tâches et la
  ligne de commande du processus (`Get-CimInstance Win32_Process`), pas
  seulement le compteur de tâches.

## Modèles : mesurer, jamais supposer

Détail complet dans `docs/model-selection.md`. L'essentiel :

- La taille ne prédit rien — un 2,7 Md réussit là où un 11,9 Md échoue.
- La capacité `tools` annoncée par Ollama est déclarée jusque par un modèle
  d'embedding.
- Les benchmarks publiés servent à faire une liste courte, pas à décider.
- Le seul juge est `backend/model_intelligence/agentic_probe.py`, trois
  essais minimum, **un modèle à la fois** (il prend un verrou exclusif).

Matériel : AMD RX 6800, ~16 Go de VRAM. Un modèle qui déborde sur CPU
répond quand même, sans erreur, dix fois plus lentement et de façon
erratique — ce qui ressemble à un modèle peu fiable jusqu'à ce qu'on
regarde `size` moins `size_vram` dans `/api/ps`.

## Contexte Ollama : le piège le plus coûteux

L'endpoint OpenAI-compatible `/v1` qu'utilise Hermes Agent **ne transporte
pas `num_ctx`**. Trois leviers, par ordre de préférence :

1. **`PARAMETER num_ctx` dans un Modelfile** — par modèle, définitif, sans
   effet de bord. C'est ainsi que `qwen3.5:9b-128k` et `gemma4:12b-64k`
   existent. `ollama show --modelfile <tag>` pour inspecter.
2. **`options.num_ctx` dans la requête** — possible sur les endpoints
   natifs (`/api/embeddings`), pas sur `/v1`.
3. **`OLLAMA_CONTEXT_LENGTH`** — global, donc dangereux : le porter à 65536
   pour l'agent a fait passer le modèle d'embedding de 0,64 Go à 5,88 Go de
   VRAM et 57 s par appel.

En dessous de ~64k servis, les schémas d'outils sont tronqués et l'agent
répond qu'il n'a pas d'outils — ce qui est alors littéralement vrai.
`backend/runtime/context_guard.py` le détecte au démarrage.

## Commandes

```bash
python -m pytest backend/tests -q          # ~4 min, doit être vert
cd frontend && npx tsc --noEmit            # typecheck
```

Backend et frontend se lancent via `preview_start` (`.claude/launch.json`),
jamais avec un `npm run dev` détaché.

## Conventions

- Le CHANGELOG raconte le **pourquoi** et les mesures, pas la liste des
  fichiers touchés. Une entrée corrigée par une mesure ultérieure est
  amendée explicitement, jamais réécrite en silence.
- Les commentaires expliquent la raison d'être, pas le fonctionnement — une
  règle sans son pourquoi se fait supprimer au premier refactoring.
- Les tests nomment l'incident qu'ils empêchent.
- Ne jamais commiter sans que la suite complète soit verte.
