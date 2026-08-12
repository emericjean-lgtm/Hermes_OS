# Choisir un modèle agentique pour Hermes OS

Ce document existe parce que le choix du modèle a été le facteur le plus
décisif — et le plus contre-intuitif — de l'intégration de Hermes Agent.
Cinq défauts distincts ont produit des missions « réussies » au-dessus d'un
workspace vide ; le dernier était simplement un modèle incapable de tenir
une boucle d'outils.

## Le critère qui décide : la mesure locale

`backend/model_intelligence/agentic_probe.py` exécute une vraie tâche
agentique via le CLI Hermes Agent installé et lit le verdict **sur le
disque**, jamais dans la réponse du modèle. C'est le seul juge.

```bash
python -c "
import sys; sys.path.insert(0,'.')
from backend.model_intelligence.agentic_probe import probe, save_result
for _ in range(3):
    r = probe('mon-modele:tag'); save_result(r); print(r)
"
```

Trois essais minimum : un seul échantillon s'est révélé faux à répétition.
Les sondes prennent un verrou exclusif — deux modèles en VRAM simultanément
mesurent la contention, pas le modèle.

## Résultats mesurés sur ce déploiement (RX 6800, 16 Go)

| Modèle | Taille | ctx servi | VRAM | Succès | Durée |
|---|---|---|---|---|---|
| **`lfm2.5-2.6b-128k`** | 2,7 Md | 131072 | **1,67 Go** | **3/3** | 28-41 s |
| `qwen3.5:9b-128k` | 9,7 Md | 131072 | 10,18 Go | 3/3 | ~47 s |
| `devstral` | 23,6 Md | 65536 | déborde 10,75 Go sur CPU | 1/3 | ~300 s |
| `gemma4:12b-64k` | 11,9 Md | 65536 | 8,49 Go | 0/3 | ~430 s |
| `gemma4:12b-128k` | 11,9 Md | 131072 | 8,19 Go | 0/2 | ~945 s |

## Ce que cette sonde mesure vraiment — et ce qu'elle ne mesure pas

Elle demande de **créer un fichier avec un chemin et un contenu**. Elle
mesure donc « mener à bien une écriture », ce qui confond deux capacités
distinctes : choisir le bon outil, et construire correctement ses arguments.

Le cas `gemma4:12b` le montre. Des tests antérieurs menés séparément contre
les outils MCP de Hermes OS ont donné :

- `files_list` ✅ — appel réel, vraies données du workspace
- `files_read` ✅ — README.md et ARCHITECTURE.md réellement lus
- `security_evaluate` ✅ — a bien renvoyé `require_human_validation`
- `files_diff` ⚠️ — bon outil sélectionné, **paramètre `path` manquant**

Donc gemma4 **sait** comprendre une tâche, choisir un outil et exploiter un
résultat. Sa faiblesse observée porte sur la construction des arguments — et
c'est précisément ce que la sonde exige. Un `0/3` ici ne signifie pas
« incapable d'agentique », mais « ne mène pas à bien une écriture ».

Cette nuance ne change pas la décision : une mission produit toujours un
artefact, donc un modèle qui échoue à écrire n'est pas utilisable comme
cerveau de mission. Elle change en revanche l'usage ailleurs — gemma4 reste
un candidat correct pour de l'analyse en lecture seule.

**Limite connue de l'instrument** : la sonde n'enregistre pas les arguments
générés. Elle ne peut donc pas distinguer « le modèle a omis `path` » de
« l'adaptateur ou le transport MCP l'a perdu ». Attribuer un échec de
paramètre au modèle demande un test contrôlé — même prompt, même schéma,
deux modèles, arguments comparés — que cet outil ne sait pas encore mener.

Le contexte n'y change rien : `gemma4:12b-128k`, créé via Modelfile et servi
à 131072 sans le moindre débordement (8,19 Go, 0 % CPU), donne le même 0
appel d'outil pour un temps doublé.

## Ce qui ne prédit rien

**Le nombre de paramètres.** La corrélation est nulle, voire inversée :
2,7 Md réussit 3/3, 11,9 Md échoue 0/3. Un plancher de taille aurait
rejeté le meilleur modèle disponible ici.

**La déclaration `tools` d'Ollama.** `qwen3-embedding:0.6b` l'annonce.

**Les benchmarks publiés.** Gemma4 obtient 54,2 % sur MCP Atlas — un
benchmark agentique réel — et 0/3 chez nous. Les benchmarks servent à
constituer une liste courte, jamais à décider.

**Le contexte annoncé.** `devstral` supporte 131 072 et se faisait servir
4096 : l'endpoint OpenAI `/v1` ne transporte pas `num_ctx`, seul
`OLLAMA_CONTEXT_LENGTH` compte.

## Ce qui prédit réellement

**Le post-entraînement agentique.** LFM2.5-2.6B a été entraîné par
renforcement sur des scénarios d'usage d'outils ; les modèles qu'il bat
sont des généralistes à qui l'on demande de se comporter en agent. C'est la
seule caractéristique qui sépare les gagnants des perdants ici, et elle
n'apparaît dans aucune métadonnée — il faut lire la fiche du modèle.

**La tenue intégrale en VRAM au contexte de service.** Un modèle qui
déborde répond quand même, sans erreur, simplement dix fois plus lentement
et de façon erratique. Vu de l'extérieur cela ressemble exactement à un
modèle peu fiable.

## Le budget VRAM, concrètement

Sur 16 Go, avec ≥64k de contexte requis pour que les schémas d'outils ne
soient pas tronqués :

```
poids du modèle + cache KV au contexte servi + buffers  <  16 Go
```

Le cache KV croît avec le contexte, ce qui crée un piège circulaire :
augmenter le contexte pour réparer la troncature est précisément ce qui
fait déborder un gros modèle. `devstral` à 65536 réclame 25,52 Go.

Vérifier avant d'adopter :

```bash
curl -s http://127.0.0.1:11434/api/ps | python -c "
import sys,json
for m in json.load(sys.stdin)['models']:
    tot, vram = m['size'], m['size_vram']
    print(m['name'], 'ctx', m.get('context_length'),
          'cpu_offload', round((tot-vram)/1e9,2), 'GB')"
```

Toute valeur `cpu_offload` non nulle disqualifie le modèle pour l'agentique
(`ModelProfile.cpu_offload_bytes`).

## Modèles évalués et écartés

**Meta Muse Glimmer 30B** (Apache 2.0, août 2026) — écarté sur cette
machine. Sa fiche est pourtant la plus prometteuse rencontrée : entraîné
sur des scénarios d'outils *et de récupération après échec*, MCP Atlas
75,5 %, SWE-Bench Pro 51,2 %, et il cite nommément Hermes Agent comme
pattern d'orchestration. Mais la quantification la plus agressive
(K-Quant-17GB) pèse 16,76 Go de poids seuls, plus 1,40 Go de projecteur
vision et 1,63 Go de drafter DFlash, avant tout cache KV. Cible officielle
Meta : 24 Go. Sur 16 Go il déborderait — le mode d'échec déjà mesuré sur
`devstral`. **À reconsidérer avec une carte de 24 Go ou plus.**

## Où chercher

- Fiches Hugging Face — chercher explicitement « agentic », « tool use »,
  « function calling » dans la section post-entraînement, pas seulement les
  scores généralistes.
- **BFCL v4** (avril 2026) : Agentic 40 %, Multi-Turn 30 %, Live 10 %,
  Non-Live 10 %, mesure d'hallucination 10 %. Le référentiel le plus proche
  de ce que fait Hermes Agent.
- Familles explicitement orientées appel d'outils : xLAM, ToolACE, Hammer,
  FunReason — des 7-8 Md y dépassent des modèles bien plus gros.

Dans tous les cas : la liste courte vient des benchmarks, **la décision
vient de la sonde**.
