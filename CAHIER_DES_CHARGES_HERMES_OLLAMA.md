# Cahier des charges — Hermes Ollama
### Édition consolidée & normative — Version 4.0 (juillet 2026)
### Configuration cible : AMD RX 6800 16 Go / Intel i5-13500 / 32 Go DDR5

---

> **Note de portabilité et d'usage**
>
> Ce document est la **source de vérité unique** du projet Hermes Ollama. Il fusionne et remplace les trois documents antérieurs (spécification matérielle v2.0, catalogue de modèles de juillet 2026, guide d'installation & interface v4.0). Il est **auto-suffisant** : aucune connaissance d'un document externe n'est requise.
>
> Il est conçu pour être **réutilisable sur n'importe quel LLM** : vous pouvez le fournir intégralement à un assistant de code (Claude Code, ou autre) pour faire construire le projet, ou le donner par sections.
>
> **Principe directeur transversal :** *les modèles d'IA sont de la configuration, pas du code.* Tous les noms de modèles vivent dans `config/models.yaml` et `.env`. Remplacer un modèle par un meilleur ne doit jamais exiger de modifier le cœur du système.
>
> **Statut des sections :** tout le corps du document est **normatif** (à implémenter). Seule l'**Annexe B — Pistes prospectives** est explicitement **non-normative** (veille technologique, à ne pas implémenter en l'état).

---

## Sommaire

1. [Résumé exécutif](#1-résumé-exécutif)
2. [Présentation & finalité](#2-présentation--finalité)
3. [Configuration matérielle & implications](#3-configuration-matérielle--implications)
4. [Stack technique](#4-stack-technique)
5. [Catalogue de modèles (modèles vérifiés)](#5-catalogue-de-modèles-modèles-vérifiés)
6. [Périmètre fonctionnel](#6-périmètre-fonctionnel)
7. [Principes de conception](#7-principes-de-conception)
8. [Architecture logicielle](#8-architecture-logicielle)
9. [Système multi-agents](#9-système-multi-agents)
10. [Routage des modèles](#10-routage-des-modèles)
11. [Mémoire persistante](#11-mémoire-persistante)
12. [Gestion de contexte](#12-gestion-de-contexte)
13. [Gestion des tâches](#13-gestion-des-tâches)
14. [Gestion des fichiers & du code](#14-gestion-des-fichiers--du-code)
15. [Workflows](#15-workflows)
16. [Vérification & contrôle qualité](#16-vérification--contrôle-qualité)
17. [Sécurité (Aegis) & validation humaine](#17-sécurité-aegis--validation-humaine)
18. [Journalisation & audit](#18-journalisation--audit)
19. [Gestion des erreurs & reprise](#19-gestion-des-erreurs--reprise)
20. [Auto-évolution (HSE)](#20-auto-évolution-hse)
21. [Monitoring matériel](#21-monitoring-matériel)
22. [Exigences non-fonctionnelles](#22-exigences-non-fonctionnelles)
23. [Interface utilisateur (spécification détaillée)](#23-interface-utilisateur-spécification-détaillée)
24. [API & contrats de données](#24-api--contrats-de-données)
25. [Installation & déploiement](#25-installation--déploiement)
26. [Règles de fonctionnement & d'autonomie](#26-règles-de-fonctionnement--dautonomie)
27. [Priorités de développement](#27-priorités-de-développement)
28. [Critères d'acceptation & matrice de tests](#28-critères-dacceptation--matrice-de-tests)
29. [Annexes](#29-annexes)

---

## 1. Résumé exécutif

Hermes Ollama est un **assistant IA local, autonome et extensible**, conçu pour **un seul utilisateur**, fonctionnant sur une configuration **RX 6800 16 Go / i5-13500 / 32 Go DDR5**. Ce n'est pas un chatbot : c'est un **outil de travail réel**, capable de comprendre un contexte projet, d'analyser fichiers/code/documents, de proposer et d'exécuter des actions contrôlées, de demander validation sur les actions sensibles, et de conserver une mémoire utile dans le temps.

Le système combine :

- dialogue naturel en streaming ;
- **système multi-agents** spécialisés (orchestrateur + agents métier) ;
- **routage intelligent** entre tiers de modèles selon la tâche et la VRAM disponible ;
- **mémoire persistante multi-niveaux** (épisodique, sémantique, procédurale + skills) ;
- exécution **contrôlée, traçable et réversible** ;
- gestion de tâches avec reprise après interruption ;
- vérification automatisée (lint, tests, revue par second modèle) ;
- sécurité par défaut (whitelist, validations, secrets protégés) ;
- **adaptation continue au matériel** (VRAM, température, offload).

La configuration matérielle permet de faire tourner **des modèles denses jusqu'à ~14B en VRAM pure**, des **MoE ~30B** (peu de paramètres actifs) confortablement, et d'**offloader jusqu'à ~30B denses** grâce aux 32 Go de RAM (avec dégradation de vitesse).

Valeur du produit : **utile, contrôlé, extensible, local, fiable et économe en VRAM**. Priorité à la fiabilité sur l'ambition : *mieux vaut un agent qui finit 10 tâches simples sans se tromper qu'un agent qui promet la lune et casse un dépôt Git.*

---

## 2. Présentation & finalité

### 2.1 Objectif

Mettre en place un **co-pilote technique polyvalent local** capable de :

- comprendre un contexte projet ;
- analyser fichiers, code, documents, instructions ;
- proposer des actions et un plan ;
- exécuter certaines tâches de manière contrôlée ;
- demander validation quand une action devient sensible ;
- conserver une mémoire utile dans le temps ;
- fonctionner en local autant que possible ;
- s'adapter à plusieurs types de projets sans être spécialisé.

### 2.2 Domaines couverts

Développement logiciel ; rédaction de documentation ; analyse de fichiers ; organisation de tâches ; recherche d'informations en contexte local ; assistance à la décision ; contrôle qualité ; automatisation de routines ; génération de contenus structurés ; orchestration de plusieurs modèles selon la tâche.

### 2.3 Utilisateur cible

- **un seul utilisateur** (simplifie droits, mémoire, validations, interfaces) ;
- qui souhaite **garder la main** sur les décisions critiques ;
- qui veut une IA **locale, utile, claire et fiable** ;
- capable d'utiliser des outils techniques, mais assisté pour gagner du temps et réduire la charge mentale.

### 2.4 Positionnement

Hermes se situe à l'intersection de : un assistant conversationnel, un agent d'exécution local, un organisateur personnel de projet, un routeur intelligent de modèles, et un moteur de mémoire et de contexte.

---

## 3. Configuration matérielle & implications

> Section fondamentale : elle conditionne directement les choix de modèles, de performances et d'architecture.

### 3.1 Configuration cible

| Composant | Modèle | Capacité |
|---|---|---|
| GPU | AMD RX 6800 | 16 Go VRAM GDDR6, RDNA2 (gfx1030) |
| CPU | Intel i5-13500 | 14 cœurs (6P + 8E), 20 threads |
| RAM | DDR5 | 32 Go |
| Backend GPU | ROCm / HIP | RDNA2, ROCm 6.x/7.x |

### 3.2 GPU — RX 6800 (16 Go VRAM)

Carte RDNA2, configuration sérieuse pour l'inférence locale.

| Taille modèle | Quantisation | Tient en VRAM seule | Notes |
|---|---|---|---|
| 2B à 4B | Q4 à Q8 | ✅ Oui | Ultra rapide |
| 7B à 8B | Q4 à Q8 | ✅ Oui | Confortable |
| 12B à 14B | Q4 | ✅ Oui | Optimal |
| 14B | Q6/Q8 | ⚠️ Limite | Possible selon modèle |
| MoE 30B (≈3B actifs) | Q4 | ✅ Oui | Se comporte comme un petit modèle |
| 27B à 32B denses | Q4 | ⚠️ Offload partiel | CPU prend le relai |
| 70B | Q2/Q3 | ❌ Offload lourd | Très lent |

**Règle de calcul approximative (VRAM nécessaire) :**
- Q4 : `paramètres_milliards × 0,55 Go`
- Q6 : `paramètres_milliards × 0,75 Go`
- Q8 : `paramètres_milliards × 1,0 Go`
- **MoE** : ne compter que les **paramètres actifs** pour la vitesse, mais **prévoir le poids total** pour le chargement (ex. MoE 30B-A3B ≈ 19 Go disque, ~12-14 Go VRAM Q4).

**Exemples :** Qwen3-14B Q4 ≈ 8,5 Go ✅ · gemma3:12b Q4 ≈ 8,1 Go ✅ · Mixtral 8x7B Q4 ≈ 26 Go ❌ (offload).

**Règle d'or :** un modèle qui tient **intégralement en VRAM** est 3 à 8× plus rapide qu'un modèle en offload CPU. Privilégier ≤14B Q4 (ou MoE ~30B) pour la vitesse ; ne monter en 27-32B denses que pour les tâches critiques où la qualité prime sur la latence.

### 3.3 Backend AMD — ROCm / HIP

| OS | Backend | Maturité | Recommandation |
|---|---|---|---|
| Linux (Ubuntu 24.04 LTS) | ROCm natif | ✅ Mature | **Recommandé** |
| Windows 11 | ROCm/HIP | ⚠️ Fonctionnel | Dépannage uniquement |

- Sur Linux, Ollama détecte automatiquement la RX 6800 via ROCm.
- Variable critique : `HSA_OVERRIDE_GFX_VERSION=10.3.0` (la RX 6800 est gfx1030, pas toujours reconnue nativement).
- **Point de vigilance :** une régression ROCm récente peut causer des `SIGSEGV` sur certaines cartes RDNA2 avec l'override ; en cas de crash au démarrage d'Ollama, downgrader vers une version ROCm stable (ex. 6.4.1).

> **Recommandation ferme :** Linux (Ubuntu 24.04 LTS) pour une configuration optimale. Les gains GPU sur ROCm natif sont significatifs.

### 3.4 CPU — i5-13500

14 cœurs (6P + 8E), 20 threads. Rôles : offload des couches ne tenant pas en VRAM ; inférence des modèles d'embedding légers ; orchestration/routage/mémoire ; traitement et indexation des fichiers.

**Performance CPU seul (indicatif) :** 7B Q4 ≈ 8-12 t/s ; 14B Q4 offload partiel ≈ 4-8 t/s ; à éviter au-delà de 20B sans GPU.

### 3.5 RAM — 32 Go DDR5

| Usage | RAM allouée |
|---|---|
| Système d'exploitation | ~4-6 Go |
| Ollama + modèle en cours | ~4-8 Go |
| Offload CPU layers | ~4-12 Go (selon modèle) |
| Backend Python (Hermes) | ~2-4 Go |
| Base vectorielle (ChromaDB) | ~1-2 Go |
| Marge libre | ~4-8 Go |

**Capacité d'offload combinée :** 16 Go VRAM + ~16 Go RAM ≈ ~32 Go d'espace modèle total → modèles jusqu'à ~30B Q4 en offload partiel (vitesse dégradée).

### 3.6 Profils de performance attendus

| Tier | Modèle exemple (vérifié) | Tokens/s attendus | Usage recommandé |
|---|---|---|---|
| Turbo | `qwen3:1.7b` / `llama3.2:3b` | ~80-120 t/s | Routage, réponses rapides |
| Standard | `qwen3:8b` / `llama3.1:8b` | ~40-60 t/s | Tâches courantes, rédaction |
| Qualité | `qwen3:14b` / `qwen3-coder:30b` (MoE) | ~20-40 t/s | Raisonnement, code |
| Puissant | `qwen3:32b` / `deepseek-r1:32b` (offload) | ~8-18 t/s | Tâches complexes |
| Extrême | `llama3.3:70b` Q2 (offload lourd) | ~2-5 t/s | Dernier recours |

> Valeurs estimatives : dépendent du contexte injecté, de la longueur de sortie et de la charge système. Au-delà de ~8k tokens de contexte, la latence augmente sensiblement même sur GPU.

### 3.7 Contraintes de stockage

| Poste | Espace |
|---|---|
| Modèles actifs (sélection raisonnée) | ~50-90 Go |
| Base vectorielle + mémoire | ~5-10 Go |
| Journaux, snapshots, données projet | ~2-5 Go |
| **Total recommandé** | **~100 Go minimum sur SSD NVMe** |

---

## 4. Stack technique

### 4.1 Composants

| Rôle | Outil | Justification |
|---|---|---|
| Serveur de modèles | **Ollama** | Support natif ROCm AMD, API REST simple |
| Backend | **Python 3.11+ / FastAPI** | Écosystème IA riche, typage Pydantic |
| Framework agents | **LangChain / LangGraph** | Orchestration, mémoire, outils, graphes |
| Base vectorielle | **ChromaDB** | Local, simple, performant mono-utilisateur |
| Base relationnelle | **SQLite via SQLAlchemy** | Local, zéro infra |
| Interface web | **Next.js 15 + TypeScript + Tailwind + shadcn/ui** | Premium, type-safe bout-en-bout |
| Temps réel | **WebSocket (socket.io / websockets)** | Streaming, statut live |
| Notifications | **python-telegram-bot** | Alertes hors interface |
| Fichiers | **Pathlib + Watchdog** | Surveillance locale |
| Lint / tests | **subprocess + pytest** | Vérification post-modification |
| Secrets | **python-dotenv + keyring** | Secrets hors code |
| Monitoring GPU | **rocm-smi / amdgpu-stats** | VRAM, température |

### 4.2 Architecture de services

```
┌─────────────────────────────────────────────────────┐
│                    HERMES OLLAMA                      │
├─────────────────────────────────────────────────────┤
│  Interface Utilisateur (Next.js + shadcn/ui)         │
├────────────────────┬────────────────────────────────┤
│  Orchestrateur     │  Gestionnaire de tâches         │
│  (FastAPI/LangGraph)│  (SQLite)                      │
├────────────────────┼────────────────────────────────┤
│  Routeur modèles   │  Gestionnaire mémoire           │
│                    │  (ChromaDB + SQLite)            │
├────────────────────┼────────────────────────────────┤
│  Moteur sécurité   │  Journal d'audit                │
│  (Aegis)           │  (SQLite + fichiers JSON)       │
├────────────────────┼────────────────────────────────┤
│  Gestionnaire      │  Moteur de vérification         │
│  de fichiers       │  (lint, tests, syntaxe)         │
├────────────────────┼────────────────────────────────┤
│  Monitor GPU       │  Auto-évolution (HSE)           │
├─────────────────────────────────────────────────────┤
│              Ollama API (localhost:11434)            │
├─────────────────────────────────────────────────────┤
│         RX 6800 (ROCm) + i5-13500 (offload)          │
└─────────────────────────────────────────────────────┘
```

---

## 5. Catalogue de modèles (modèles vérifiés)

> **Tous les modèles ci-dessous existent réellement sur Ollama.** Les modèles spéculatifs des versions antérieures (familles 1-bit « Bonsai », `qwen3.6`) ont été retirés du corps normatif et déplacés en **[Annexe B](#annexe-b--pistes-prospectives-non-normatif)** (veille, non implémentés).
>
> **Mise à jour 2026-07-26 — `config/models.yaml` fait foi pour les tags exacts.**
> Conformément au principe directeur du document (« les modèles d'IA sont
> de la configuration, pas du code »), le tableau ci-dessous est
> *indicatif du rôle* ; la valeur exacte vit dans `config/models.yaml`.
> La colonne « Configuré » reflète ce qui est réellement installé et
> utilisé sur la machine cible — vérifié par `ollama list` le 2026-07-26,
> les douze rôles répondant présents. Plusieurs valeurs ont évolué depuis
> la v4.0 : `gemma4:12b` (sorti depuis, donc sorti de l'Annexe B),
> `qwen3.5:9b`, `phi4-reasoning` et Hermes-4-14B remplacent leurs
> prédécesseurs. Le remplacement s'est fait par `models.yaml` seul, sans
> toucher au cœur — ce qui valide le principe directeur.

### 5.1 Modèles par rôle et par agent

| Rôle dans Hermes | Agent | Recommandé v4.0 | **Configuré (2026-07-26)** | VRAM ≈ | Pourquoi |
|---|---|---|---|---|---|
| Routage rapide | Swift | `qwen3:1.7b` | `qwen3:1.7b` | ~1,5 Go | Ultra-léger, **épinglé en VRAM** (§22) |
| Orchestration | Prime | `qwen3:14b` | `hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M` | ~9 Go | Tool-calling structuré explicite |
| Code principal | Atlas | `qwen3-coder:30b` | `qwen3-coder:30b` (MoE 30B-A3B) | ~13 Go | Qualité 30B, vitesse ~3B actifs |
| Code agentique | Atlas (alt.) | `devstral` (24b) | `devstral` | ~14 Go | Entraîné agent-first (édition de fichiers) |
| Raisonnement / QA | Veritas | `deepseek-r1:14b` | `deepseek-r1:14b` | ~9 Go | Chain-of-thought natif |
| Rédaction | Scribe | `qwen3:8b` | `qwen3.5:9b` | ~6,6 Go | 256k de contexte, gains raisonnement |
| Recherche / RAG | Minerva | `qwen3:8b` + RAG | `qwen3.5:9b` + RAG | ~6,6 Go | Synthèse, extraction |
| Embeddings | Echo | `nomic-embed-text` | `nomic-embed-text` | ~0,3 Go | **Épinglé en VRAM** (§22) |
| Vision | Eyes | `gemma3:12b` | `gemma4:12b` (multimodal) | ~7,6 Go | Architecture sans encodeur, plus léger |
| Sécurité / audit | Aegis | `phi4:14b` | `phi4-reasoning:14b-q4_K_M` | ~11 Go | Variante entraînée au raisonnement structuré |
| Analyse avancée | (escalade) | `gpt-oss:20b` | ~13-15 Go | 128k | Poids ouverts OpenAI, raisonnement ajustable |
| Double-check léger | (parallèle) | `qwen3:4b` / `gemma3:4b` | ~3 Go | 128k | Vérification rapide peu coûteuse |
| Escalade critique | (rare) | `deepseek-r1:32b` (offload) | 16+8 Go | 32k | Raisonnement maximal |
| Best-of dense | (rare) | `qwen3:32b` / `gemma3:27b` (offload) | 16+8 Go | 128k | Qualité maximale locale |

### 5.2 Fenêtres de contexte (indicatif — vérifier au `ollama show`)

| Modèle | Contexte max | Remarque |
|---|---|---|
| `qwen3:1.7b/4b/8b/14b/32b` | jusqu'à 128k | selon build |
| `qwen3-coder:30b` | 256k | idéal analyse de dépôts |
| `deepseek-r1:14b/32b` | 32k-128k | selon distillation |
| `gemma3:4b/12b/27b` | 128k | multimodal (1b = texte seul, 32k) |
| `phi4:14b` | 16k | plus petit → chat analytique court |
| `gpt-oss:20b` | 128k | — |
| `llama3.2:3b` / `llama3.1:8b` | 128k | — |

> La fenêtre annoncée ne garantit pas une vitesse constante : au-delà de ~8k tokens, la latence croît. **Toujours** dimensionner le contexte réellement chargé (paramètre `num_ctx`) selon la VRAM disponible.

### 5.3 Combos VRAM intelligents (16 Go)

La VRAM ne peut pas tout charger simultanément. Combos qui fonctionnent :

| Combo | Modèles chargés | VRAM totale | Usage |
|---|---|---|---|
| Rapide + Code | `qwen3:1.7b` (1,5) + `qwen3-coder:30b` (13) | ~14,5 Go ✅ | Dev quotidien |
| Rapide + Polyvalent | `qwen3:1.7b` (1,5) + `qwen3:14b` (9) | ~10,5 Go ✅ | Chat + orchestration |
| Rapide + Raisonnement | `qwen3:1.7b` (1,5) + `deepseek-r1:14b` (9) | ~10,5 Go ✅ | Vérification |
| Rapide + Vision | `qwen3:1.7b` (1,5) + `gemma3:12b` (9) | ~10,5 Go ✅ | Analyse images |
| Triple léger | `qwen3:1.7b` (1,5) + `qwen3:8b` (5,5) + `nomic` (0,3) | ~7,3 Go ✅ | Rédaction + RAG |
| Rapide + Double-check | `qwen3:1.7b` (1,5) + `qwen3:4b` (3) + `nomic` (0,3) | ~4,8 Go ✅ | Routage + vérif parallèle |
| ⚠️ Deux 14B denses | `qwen3:14b` (9) + `deepseek-r1:14b` (9) | ~18 Go ❌ | Offload → lent |

> **Règle Hermes VRAM :** toujours garder `qwen3:1.7b` + `nomic-embed-text` chargés (~1,8 Go). Ils servent au routage et à la recherche sémantique et pèsent presque rien. Charger ensuite le modèle principal selon la tâche. Respecter `OLLAMA_MAX_LOADED_MODELS=2`.

### 5.4 Sélection d'installation par phase

```bash
# ── Phase 1 — Essentiels (~40 Go) ──────────────────────────────
ollama pull qwen3:1.7b            # Routage rapide (toujours chargé)
ollama pull qwen3:14b             # Polyvalent / orchestration
ollama pull qwen3-coder:30b       # Code (MoE)
ollama pull deepseek-r1:14b       # Raisonnement / vérification
ollama pull nomic-embed-text      # Embeddings RAG

# ── Phase 2 — Extension (~25 Go) ───────────────────────────────
ollama pull qwen3:8b              # Rédaction rapide
ollama pull gemma3:12b            # Vision
ollama pull phi4:14b              # Sécurité / audit
ollama pull qwen3:4b              # Double-check léger

# ── Phase 3 — Puissance (~40 Go) ───────────────────────────────
ollama pull gpt-oss:20b           # Analyse avancée
ollama pull devstral              # Code agentique
ollama pull deepseek-r1:32b       # Raisonnement maximal (offload)
```

> Avant chaque `pull`, vérifier le tag exact et la taille via `ollama show <modèle>` ou la bibliothèque Ollama. Les tags peuvent évoluer (ex. `qwen3-coder:30b` == `qwen3-coder:30b-a3b-q4_K_M`).

---

## 6. Périmètre fonctionnel

### 6.1 Inclus

Interface de dialogue ; exécution locale via Ollama ; routage intelligent ; mémoire persistante (courte, longue, documentaire) ; contexte multi-documents ; lecture/écriture de fichiers ; analyse de code ; aide à la rédaction ; gestion de tâches avec statuts ; planification et suivi de missions ; journalisation ; vérification avant action sensible ; escalade de validation ; intégration Telegram ; règles et politiques de sécurité ; reprise après interruption ; profils de modèles par tâche ; support multi-projets ; **profils adaptés au matériel RX 6800** ; **surveillance thermique GPU/CPU** ; **gestion de la charge VRAM (anti-OOM)** ; **système multi-agents** ; **workflows visuels** ; **auto-évolution (skills)**.

### 6.2 Exclus

Multi-utilisateur ; SaaS public ; collaboration temps réel en équipe ; paiement ; automatisation non contrôlée de systèmes critiques ; exécution libre de commandes destructrices ; autonomie totale sans garde-fous ; **fine-tuning** de modèles ; **entraînement** de modèles.

---

## 7. Principes de conception

1. **Local d'abord** — tout ce qui peut tourner localement doit l'être.
2. **Contrôlé d'abord** — toute action risquée est validée ou encadrée.
3. **Traçable** — chaque action importante laisse une trace.
4. **Réversible** — les changements sont annulables autant que possible.
5. **Modulaire** — chaque brique est indépendante.
6. **Extensible** — nouveaux modèles, outils, usages sans réarchitecture.
7. **Polyvalent** — non limité à un seul type de projet.
8. **Lisible** — l'utilisateur comprend ce que fait l'agent sans deviner.
9. **Fiable avant d'être ambitieux** — finir des tâches simples sans erreur plutôt que promettre et casser.
10. **Économe en VRAM** — ne jamais charger un modèle lourd si un léger suffit.

---

## 8. Architecture logicielle

### 8.1 Monorepo

```
hermes-ollama/
├── .venv/                       # Environnement Python
├── .env / .env.example          # Config (secrets hors git)
├── backend/                     # FastAPI — Python
│   ├── main.py
│   ├── core/                    # orchestrator, message_bus, workflow_engine,
│   │                            #   router, snapshot_manager
│   ├── agents/                  # base_agent + 10 agents (voir §9)
│   ├── memory/                  # episodic, semantic, procedural, skill_library,
│   │                            #   ebbinghaus, rag_engine
│   ├── self_evolution/          # skill_extractor, auto_evaluator,
│   │                            #   reflection_engine, progression_tracker
│   ├── tools/                   # git, code, file, system, search
│   ├── security/                # aegis_engine, permission_matrix, secret_scanner
│   ├── monitoring/              # gpu_monitor, performance_tracker, health_checker
│   ├── connectors/              # ollama_client, telegram_bot, websocket_manager
│   └── api/routes/              # agents, chat, tasks, workflows, memory,
│                                #   files, system, logs  + websocket.py
├── frontend/                    # Next.js 15 — TypeScript (voir §23)
├── data/
│   ├── db/hermes.db             # SQLite principal
│   ├── db/chroma/               # ChromaDB
│   ├── snapshots/  logs/  workflows/
└── config/
    ├── agents.yaml  models.yaml  security.yaml
    ├── triggers.yaml  projects.yaml
```

### 8.2 Modules principaux

| Module | Rôle | Technologie |
|---|---|---|
| Orchestrateur | Reçoit la demande, décide du flux, supervise | FastAPI, LangGraph |
| Routeur de modèles | Sélectionne le modèle selon la tâche + VRAM | Python (règles + LLM léger) |
| Message bus | Communication inter-agents | Python (queue/événements) |
| Gestionnaire de mémoire | Enregistre, récupère, résume | ChromaDB + SQLite |
| Gestionnaire de tâches | Suit missions et états | SQLite + SQLAlchemy |
| Gestionnaire de fichiers | Lit, indexe, modifie, compare | Pathlib + Watchdog |
| Moteur de vérification | Teste, lint, compare | subprocess + pytest |
| Moteur de sécurité (Aegis) | Valide permissions, bloque le sensible | Python, règles statiques |
| Journal d'audit | Trace l'historique | SQLite + fichiers JSON |
| Monitor GPU | Surveille VRAM, température | rocm-smi / amdgpu-stats |
| Auto-évolution (HSE) | Extrait/évalue/réfléchit sur les skills | Python |
| Interface | Dialogue, supervision, validation | Next.js / shadcn |
| Connecteurs | Telegram, WebSocket | python-telegram-bot |

---

## 9. Système multi-agents

Hermes fonctionne comme une **équipe d'agents spécialisés** coordonnés par un orchestrateur. Chaque agent est défini dans `config/agents.yaml` (nom, modèle, always-on, déclencheurs, permissions).

### 9.1 Fiches agents

> Colonne modèle mise à jour le 2026-07-26 pour refléter
> `config/models.yaml`, qui fait foi (§5.1).

| Agent | Rôle | Modèle | Always-on | Déclencheurs | Entrées → Sorties |
|---|---|---|---|---|---|
| **Hermes Prime** | Orchestrateur : décompose, délègue, supervise | Hermes-4-14B | Non | Toute demande utilisateur | Demande → plan + délégations |
| **Hermes Swift** | Routage/classification ultra-rapide | `qwen3:1.7b` | **Oui** | Chaque requête (pré-tri) | Demande → type de tâche + tier |
| **Atlas** | Développeur : analyse/génère/refactore du code | `qwen3-coder:30b` (ou `devstral`) | Non | Tâche de code | Fichiers → patch + tests |
| **Minerva** | Recherche & RAG documentaire | `qwen3.5:9b` + `nomic` | Non | Recherche/synthèse | Requête → passages + synthèse |
| **Hermes Scribe** | Rédaction de contenu/documentation | `qwen3.5:9b` | Non | Rédaction | Brief → document |
| **Aegis** | Sécurité : valide permissions, bloque le sensible | `phi4-reasoning:14b` | **Oui** | Toute action à risque | Action → verdict (autoriser/bloquer/escalader) |
| **Kronos** | Planification, priorisation, échéances | Hermes-4-14B | Non | Création/tri de tâches | Objectif → plan de tâches |
| **Hermes Eyes** | Vision : analyse d'images/screenshots | `gemma4:12b` | Non | Image jointe | Image → description/extraction |
| **Veritas** | QA : vérifie le travail des autres agents | `deepseek-r1:14b` | Non | Tâche critique | Sortie → verdict + corrections |
| **Echo** | Mémoire & skills : indexe, récupère, synchronise | `qwen3.5:9b` + `nomic` | **Oui** | Fin de tâche, requête mémoire | Événement → mémoire à jour |

### 9.2 Protocole de communication (message bus)

Les agents échangent via un **bus de messages** typé. Types de messages minimaux :

- `TASK_DELEGATION` (Prime → agent) : id, description, contexte, contraintes.
- `TASK_RESULT` (agent → Prime) : id, résultat, artefacts, métriques.
- `VALIDATION_REQUEST` (agent → Aegis) : action, risque, impact, fichiers.
- `VALIDATION_GRANTED` / `VALIDATION_DENIED` (Aegis → agent) : verdict + motif.
- `MEMORY_WRITE` / `MEMORY_QUERY` (agent → Echo) : contenu ou requête.
- `ESCALATION` (agent → utilisateur) : demande de validation humaine.

Chaque message est **horodaté, tracé** (§18) et affiché en temps réel dans la vue Agents (§23).

### 9.3 Contrôle croisé (tâches critiques)

1. Génération par l'agent principal (ex. Atlas / `qwen3-coder:30b`).
2. Revue par un second modèle (Veritas / `deepseek-r1:14b`).
3. Validation par règles déterministes (lint, tests, syntaxe).
4. Décision : validation humaine si nécessaire.

---

## 10. Routage des modèles

### 10.1 Matrice de routage (modèles vérifiés)

| Type de tâche | Modèle par défaut | Alternative rapide | Escalade qualité |
|---|---|---|---|
| Conversation simple | `qwen3:8b` | `qwen3:1.7b` | `qwen3:14b` |
| Classification / routage | `qwen3:1.7b` | — | — |
| Rédaction | `qwen3:8b` | `llama3.1:8b` | `qwen3:14b` |
| Résumé court | `qwen3:1.7b` | — | `qwen3:8b` |
| Résumé long | `qwen3:8b` | — | `qwen3:14b` |
| Code — analyse | `qwen3-coder:30b` | `qwen3:8b` | — |
| Code — génération | `qwen3-coder:30b` | — | `devstral` |
| Code — refactoring | `qwen3-coder:30b` | — | `deepseek-r1:14b` (revue) |
| Raisonnement complexe | `deepseek-r1:14b` | `qwen3:14b` | `deepseek-r1:32b` |
| Extraction d'infos | `qwen3:8b` | `qwen3:1.7b` | — |
| Recherche documentaire | `qwen3:8b` + RAG | — | `qwen3:14b` |
| Génération de plans | `qwen3:14b` | `qwen3:8b` | — |
| Vérification finale | `deepseek-r1:14b` | `phi4:14b` | `deepseek-r1:32b` |
| Embeddings | `nomic-embed-text` | `mxbai-embed-large` | — |
| Reformulation | `qwen3:8b` | `qwen3:1.7b` | — |
| Analyse d'image | `gemma3:12b` | `gemma3:4b` | `gemma3:27b` |

### 10.2 Critères de routage

Le choix dépend de : type de tâche identifié ; longueur estimée de la sortie ; complexité du raisonnement ; besoin vitesse vs précision ; **VRAM disponible au moment de la requête** ; **modèle déjà chargé** (éviter le rechargement) ; contrainte de temps de l'utilisateur.

### 10.3 Persistance de modèle (keepalive)

Ollama garde les modèles en VRAM un certain temps après usage (`OLLAMA_KEEP_ALIVE`). Hermes doit :

- consulter les modèles chargés **avant** de demander un chargement :
  ```
  GET http://localhost:11434/api/ps   → modèles actuellement en VRAM
  ```
- **réutiliser un modèle déjà chargé** si la qualité est suffisante ;
- ne charger un modèle plus lourd que si la tâche le justifie ;
- préférer un modèle déjà chargé à un modèle légèrement meilleur nécessitant un rechargement.

---

## 11. Mémoire persistante

### 11.1 Mémoire courte durée (RAM, non persistée)

Objectif de session ; étapes en cours ; éléments de raisonnement immédiat ; modèle actif courant.

### 11.2 Mémoire longue durée (SQLite, persistée)

Préférences utilisateur ; habitudes de travail ; règles de sécurité ; format de réponse préféré ; stratégies de projet ; décisions validées ; **modèles préférés par catégorie de tâche** ; éléments récurrents utiles.

### 11.3 Mémoire documentaire (ChromaDB + embeddings)

Documents PDF ; notes Markdown ; fichiers texte ; configs ; documentation projet ; historiques de décisions.

**Chunking recommandé :** taille 512 tokens, overlap 64 tokens, embedding `nomic-embed-text`.

### 11.4 Typologie cognitive (formalisation)

- **Épisodique** (SQLite) : événements datés, sessions, décisions.
- **Sémantique** (ChromaDB) : connaissances vectorisées, documents.
- **Procédurale** (SQLite) : skills réutilisables (§20), procédures.
- **Skill library** : compétences apprises, avec score de confiance et decay.

### 11.5 Règles mémoire

Éviter les doublons (hash + similarité sémantique) ; **dater** tout élément ; conserver les versions ; permettre la suppression explicite ; marquer la fraîcheur (date + score de confiance).

### 11.6 Decay (Ebbinghaus)

Les mémoires et skills peu utilisées voient leur score décroître dans le temps (courbe d'oubli), les remontées d'usage le renforcent. Activable via `EBBINGHAUS_DECAY_ENABLED`.

---

## 12. Gestion de contexte

Sources : conversation courante ; mémoire longue durée ; fichiers locaux ; documents importés ; notes de projet ; historiques de tâches ; règles d'utilisation ; logs.

**Exigences :** éviter de tout réinjecter ; prioriser le contexte pertinent ; **résumer automatiquement** le contexte trop long ; distinguer stable vs temporaire ; éviter les contradictions ; **respecter la fenêtre de contexte du modèle chargé** ; **tronquer intelligemment** sans perte d'information critique (résumer les parties les moins récentes plutôt que couper brutalement).

---

## 13. Gestion des tâches

### 13.1 Champs d'une tâche

Titre ; description ; objectif ; statut ; priorité ; date de création ; historique d'exécution ; fichiers concernés ; validations nécessaires ; résultats de tests ; **modèle(s) utilisé(s)** ; agent responsable.

### 13.2 Statuts

à faire ; en cours ; bloquée ; en attente de validation ; en test ; terminée ; annulée ; réversible ; partiellement réussie ; à reprendre.

### 13.3 Vues

Kanban, Liste, Timeline, Gantt (voir §23).

---

## 14. Gestion des fichiers & du code

### 14.1 Fichiers

Fonctions : lire, analyser un dossier, comparer, résumer, modifier (autorisé), créer, proposer un patch, détecter incohérences/doublons, indexer.

**Règles :** jamais modifier un fichier sensible sans garde-fou ; toujours tracer les modifications ; toujours indiquer les fichiers touchés ; **backup automatique avant modification** ; **proposer un diff lisible avant application**.

### 14.2 Code

Fonctions : lire l'arborescence ; comprendre l'architecture ; identifier les points d'entrée ; analyser les erreurs ; corriger ; créer des composants ; refactoriser ; écrire/mettre à jour des tests ; documenter ; proposer une architecture ; vérifier les conventions ; détecter les régressions ; préparer un commit clair.

**Modèle recommandé : `qwen3-coder:30b`** (revue `deepseek-r1:14b`).

**Bonnes pratiques imposées :** respecter les conventions du dépôt ; ne pas réécrire du code stable inutilement ; limiter les changements au périmètre nécessaire ; exécuter les tests après modification ; expliquer les impacts ; **ne jamais supposer que ça compile parce que « ça a l'air bon »**.

---

## 15. Workflows

Moteur de **workflows** enchaînant des agents selon un graphe, défini en YAML (`data/workflows/`), éditable via un **éditeur visuel nœuds-connexions** (React Flow) dans l'interface (§23).

Un workflow décrit : nœuds (agent + action), connexions (flux), points de **validation humaine**, conditions. Exemple `full-code-review` : `Minerva (analyse) → Atlas (corrige) → Veritas (vérifie) → Validation humaine → Atlas (applique) → Scribe (rapport)`.

Fonctions : créer, importer YAML, templates, **simuler** (dry-run), lancer, sauvegarder, planifier (déclencheurs `triggers.yaml`, ex. résumé quotidien à 18h).

---

## 16. Vérification & contrôle qualité

**Chaîne minimale :**

```
Génération → Vérif. syntaxique → Lint → Tests → Vérif. logique
           → Revue second modèle (si critique) → Validation humaine (si risqué)
```

**Contrôles minimaux :** syntaxe ; logique ; imports ; tests (`pytest`, `jest`… selon projet) ; lint ; build ; contrôle des fichiers modifiés.

**Contrôles avancés :** revue critique par second modèle (`deepseek-r1:14b` vérifie `qwen3-coder:30b`) ; détection de comportements non désirés ; contrôle de sécurité basique ; comparaison avant/après.

---

## 17. Sécurité (Aegis) & validation humaine

### 17.1 Exigences de sécurité

Accès limité aux dossiers autorisés (**whitelist explicite** via `ALLOWED_PATHS`) ; interdiction par défaut des commandes destructrices ; **protection des secrets** (jamais en clair dans les logs) ; permissions minimales ; séparation lecture/écriture ; contrôle des actions système ; confirmation obligatoire pour le sensible ; journalisation des événements critiques ; **coupure d'autonomie instantanée** possible ; **les modèles n'accèdent pas au réseau** (Ollama local, aucune fuite).

### 17.2 Matrice de permissions

Définie dans `security.yaml` : par catégorie d'action (lecture fichier, écriture fichier, exécution commande, opération Git, réseau, système), niveau d'autorisation par défaut et condition d'escalade. Aegis (always-on, `phi4:14b`) évalue chaque action à risque avant exécution.

### 17.3 Validation humaine obligatoire pour

Suppression de fichiers ; modification de secrets/`.env` ; opération Git critique (reset, force push, merge de branche principale) ; déploiement ; migration de données ; modification de config système ; actions réseau importantes ; commande non réversible ; action hors périmètre défini ; doute élevé sur l'intention.

### 17.4 Format de validation

```
┌─────────────────────────────────────────┐
│  ⚠️  VALIDATION REQUISE                  │
├─────────────────────────────────────────┤
│  Action     : [description]              │
│  Risque     : [niveau + explication]     │
│  Impact     : [ce qui sera modifié]      │
│  Fichiers   : [liste]                    │
│  Motif      : [pourquoi Hermes agit]     │
│  Si OUI     : [conséquence]              │
│  Si NON     : [conséquence]              │
├─────────────────────────────────────────┤
│  [Approuver]  [Refuser]  [Modifier]      │
└─────────────────────────────────────────┘
```

### 17.5 Niveaux d'autonomie

| Niveau | Conditions |
|---|---|
| **Faible** (défaut) | Toutes les actions proposées avant exécution |
| **Moyen** | Tâches répétitives et sûres, périmètre connu |
| **Élevé** | Instruction explicite + cadre borné + périmètre défini |
| **Critique** | Interdit sans confirmation humaine systématique |

---

## 18. Journalisation & audit

Chaque action importante produit un log JSON structuré :

```json
{
  "timestamp": "2026-07-23T14:32:11",
  "session_id": "uuid",
  "task_id": "uuid",
  "agent": "atlas",
  "request": "texte de la demande",
  "routing_decision": {
    "task_type": "code",
    "model_selected": "qwen3-coder:30b",
    "tier": 3,
    "reason": "refactoring complexe détecté"
  },
  "context_used": ["fichier_A.py", "mémoire_règles_projet"],
  "steps_executed": [ "..." ],
  "files_modified": [ "..." ],
  "tests_run": { "status": "passed", "count": 12 },
  "validation_requested": false,
  "duration_ms": 8432,
  "tokens_used": 2341,
  "tokens_per_second": 27.8,
  "vram_used_gb": 9.2,
  "result": "success"
}
```

Stockage : table `audit_log` (SQLite) + fichiers JSON dans `data/logs/`. Consultable via la vue Logs (§23). **Aucun secret** ne doit apparaître dans les logs.

---

## 19. Gestion des erreurs & reprise

### 19.1 Cas spécifiques matériel AMD

- **OOM VRAM** : modèle trop lourd → **downgrade automatique** vers tier inférieur.
- **ROCm non détecté** : Ollama bascule en CPU → alerter l'utilisateur, continuer en mode dégradé.
- **Ollama indisponible** (port 11434) : attendre, **retenter 3 fois** (backoff), puis notifier.

### 19.2 Cas généraux

Modèle non téléchargé → proposer `ollama pull` avec confirmation ; contexte trop long → résumer les parties les moins récentes ; erreur réseau ; erreur de lecture fichier ; erreur de syntaxe ; test en échec ; commande bloquée ; **interruption de session → sauvegarde d'état** ; redémarrage système → **reprise au dernier point sûr** ; conflit Git ; réponse ambiguë → **demander clarification plutôt qu'agir**.

### 19.3 Snapshots & rollback

`snapshot_manager` sauvegarde l'état (tâches, contexte, fichiers modifiés) toutes les N étapes configurables (`data/snapshots/`), permettant reprise et annulation.

---

## 20. Auto-évolution (HSE)

Module **Hermes Self-Evolution** : le système apprend de ses exécutions.

| Composant | Rôle |
|---|---|
| `skill_extractor` | Détecte une procédure réussie et la transforme en **skill** réutilisable |
| `auto_evaluator` | Évalue succès/échec d'une exécution, met à jour le score de confiance |
| `reflection_engine` | Génère une réflexion post-tâche (ce qui a marché, ce qui a échoué) |
| `progression_tracker` | Suit taux de succès global, skills créées, évolution dans le temps |

Paramètres (`.env`) : `SKILL_AUTO_VALIDATE_THRESHOLD` (ex. 0.95), `SKILL_MIN_CONFIDENCE` (ex. 0.30), `REFLECTION_ENABLED`. Une skill n'est appliquée automatiquement qu'au-dessus du seuil de confiance ; sinon elle reste « en révision ».

---

## 21. Monitoring matériel

Le module `gpu_monitor` (via `rocm-smi` / `amdgpu-stats`) expose en temps réel : VRAM utilisée (Go / 16), température GPU, modèles chargés (`ollama ps`), charge GPU, usage CPU (P/E cores), RAM, swap, espace disque.

**Seuils (`.env`) :** `GPU_ALERT_TEMP_C=85` (alerte), `GPU_CRITICAL_TEMP_C=90` (suggérer une pause), `GPU_VRAM_WARNING_PCT=85`. Ne jamais lancer deux modèles lourds simultanément. Données publiées via WebSocket vers la statusbar et la vue System (§23).

---

## 22. Exigences non-fonctionnelles

### 22.1 Performance

| Tâche | Latence cible |
|---|---|
| Réponse simple (Tier 1) | < 1 s pour le premier token |
| Tâche standard (Tier 2) | < 3 s pour le premier token |
| Tâche complexe (Tier 3) | < 8 s pour le premier token |
| Recherche mémoire | < 500 ms |
| Indexation document | < 10 s par document standard |

Streaming token par token ; pas de blocage silencieux ; traitement progressif.

### 22.2 Fiabilité & paramètres de génération

Reprise après erreur sans perte de contexte ; limiter le non-déterminisme (température basse pour le critique) ; préférer les actions vérifiables ; sauvegarde d'état toutes les N étapes.

| Contexte | Température | Top-p |
|---|---|---|
| Tâches critiques (code, config) | 0.1 à 0.3 | 0.9 |
| Tâches standard | 0.5 à 0.7 | 0.95 |
| Tâches créatives | 0.7 à 1.0 | 0.95 |

### 22.3 Maintenabilité

Code modulaire (un fichier par module) ; fonctions séparées et documentées ; règles centralisées en config ; logs JSON lisibles ; **variables de config dans `.env`** (modèles par défaut, chemins, seuils).

### 22.4 Évolutivité

Ajout de modèles via `models.yaml` ; ajout d'outils sans toucher au cœur ; ajout de sources de mémoire ; ajout de workflows sans réarchitecture.

---

## 23. Interface utilisateur (spécification détaillée)

Application web locale (`localhost:3000`), Next.js 15 + TypeScript + Tailwind + shadcn/ui, **100 % locale** après installation. Type-safe bout-en-bout (Pydantic côté backend, TypeScript/Zod côté frontend).

### 23.1 Layout global permanent

```
┌─────────────────────────────────────────────────────────────────┐
│ TOPBAR : 〔 HERMES 〕 〔 projet ▼ 〕 〔 ● 3 agents 〕 〔 ⚙ 〕   │
├──────────┬──────────────────────────────────────────────────────┤
│ SIDEBAR  │            ZONE PRINCIPALE (change selon la page)      │
│ (fixe)   │                                                        │
├──────────┴──────────────────────────────────────────────────────┤
│ STATUSBAR : GPU 9.2/16Go ▐▌ 62°C · CPU 34% · RAM 18/32Go ·       │
│             ● 3 agents · Queue: 2                                 │
└─────────────────────────────────────────────────────────────────┘
```

- **Topbar** : logo (retour Hub), sélecteur de projet, indicateur d'agents actifs, paramètres.
- **Sidebar** : Hub · Chat · Agents · Tasks · Flows · Memory · Files · Logs · Terminal · System.
- **Statusbar** (MAJ toutes les 2 s via WebSocket) : GPU (VRAM/temp/charge), CPU, RAM, agents actifs, file d'attente.

### 23.2 Vue HUB (accueil)

Vision synthétique : métriques clés (agents actifs, tâches en cours, GPU, mémoire) ; activité récente ; tâches en cours (barres de progression) ; agents actifs ; métriques 24 h (tâches OK, tokens, sessions, erreurs, taux de succès, skills créées, temps moyen).

### 23.3 Vue CHAT (la plus utilisée)

- Saisie textuelle + pièces jointes (glisser-déposer de fichiers).
- **Streaming token par token** avec vitesse (t/s) affichée.
- Modèle utilisé + tier visibles ; **switch manuel** de modèle/agent possible.
- Sélecteur d'agent : **Auto** (routage) ou choix manuel parmi les agents.
- Modes : Conversation / Assistance / Supervision / Exécution / Analyse.
- **Panneau contexte** : fichiers actifs, mémoires utilisées, skills mobilisées, étapes en cours.
- **Diff intégré** avant/après pour les modifications de code.
- Boutons d'action : Approuver / Modifier / Refuser / Commenter directement dans le chat.
- Historique persistant par session.

### 23.4 Vue AGENTS (centre de contrôle)

Cartes par agent : statut, rôle, modèle + VRAM, tâche courante + progression, métriques (tokens, blocages, validations), actions (Config / Logs / Pause / Arrêter). **Flux de communications inter-agents en temps réel** (`[Prime → Atlas] TASK_DELEGATION …`).

### 23.5 Vue TASKS

Multi-vues : **Kanban** (À faire / En cours / En validation / Terminées), Liste, Timeline, Gantt. Cartes avec priorité, agent, progression, badge Aegis si validation requise.

### 23.6 Vue WORKFLOWS

Éditeur visuel nœuds-connexions (React Flow) : liste des flows (exécutions, planification), canvas d'édition, points de validation humaine, actions Lancer / Sauvegarder / **Simuler**, import YAML, templates.

### 23.7 Vue MEMORY

Onglets Sémantique / Épisodique / Procédurale / Skills / Profil. **Skill library** (confiance, decay, usages, tags, procédure). **Recherche sémantique** avec scores. **Progression HSE** (taux de succès, skills créées, réflexions).

### 23.8 Vue FILES

Arborescence des projets autorisés, aperçu, indexation, diff, actions encadrées par Aegis.

### 23.9 Vue LOGS

Journal d'audit consultable : demande, décision de routage + modèle, erreurs/corrections, validations, fichiers modifiés, résultats de tests, reprises, **métriques (t/s, durée, VRAM)**.

### 23.10 Vue TERMINAL

Terminal intégré **contrôlé** (xterm.js), commandes encadrées par la matrice de permissions.

### 23.11 Vue SYSTEM (monitoring temps réel)

GPU (VRAM/temp/charge/ROCm, modèles en VRAM, VRAM libre) ; CPU (usage, fréquence, cœurs P/E, threads) ; RAM/swap ; disque (modèles Ollama, données Hermes, libre) ; **statut des services** (Ollama, FastAPI, ChromaDB, ROCm, Telegram).

### 23.12 Design system

```css
/* Thème sombre premium Hermes */
--bg-base:      #0A0A0F;   --bg-surface:  #111118;   --bg-elevated: #1A1A24;
--accent:       #6366F1;   /* Indigo — actions      */
--success:      #10B981;   --warning:     #F59E0B;   --danger:      #EF4444;
--text-primary: #F1F5F9;   --text-muted:  #64748B;
--font-ui:   'Inter Variable';    --font-code: 'JetBrains Mono';
```

Le thème doit rester lisible et cohérent ; composants issus de shadcn/ui ; animations via Framer Motion ; graphiques via Recharts.

---

## 24. API & contrats de données

> Esquisse normative : les noms exacts peuvent être affinés à l'implémentation, mais la surface fonctionnelle doit être couverte.

### 24.1 Endpoints REST (FastAPI)

| Domaine | Endpoints (indicatif) |
|---|---|
| Chat | `POST /chat` (stream), `GET /chat/sessions`, `GET /chat/sessions/{id}` |
| Agents | `GET /agents`, `GET /agents/{id}`, `POST /agents/{id}/pause` |
| Tâches | `GET /tasks`, `POST /tasks`, `PATCH /tasks/{id}`, `GET /tasks/{id}` |
| Workflows | `GET /workflows`, `POST /workflows`, `POST /workflows/{id}/run`, `POST /workflows/{id}/simulate` |
| Mémoire | `GET /memory/search`, `POST /memory`, `DELETE /memory/{id}`, `GET /skills` |
| Fichiers | `GET /files`, `GET /files/content`, `POST /files/diff`, `POST /files/apply` |
| Système | `GET /system/status`, `GET /system/models`, `GET /system/gpu` |
| Logs | `GET /logs`, `GET /logs/{session_id}` |

Documentation auto-générée sur `/docs` (Swagger).

### 24.2 WebSocket (temps réel)

Événements poussés : `system.metrics` (GPU/CPU/RAM, toutes les 2 s) ; `chat.token` (streaming) ; `agent.message` (bus inter-agents) ; `task.update` ; `validation.request`.

### 24.3 Modèle de données (esquisse)

**SQLite (`hermes.db`)** — tables principales :

- `sessions(id, started_at, project, summary)`
- `tasks(id, title, description, objective, status, priority, agent, created_at, models_used, files, test_results)`
- `memory_long(id, type, content, created_at, confidence, decay, tags)`
- `skills(id, name, description, procedure, confidence, decay, uses, success, tags, created_at)`
- `audit_log(id, timestamp, session_id, task_id, agent, payload_json)`
- `preferences(key, value)`

**ChromaDB (`chroma/`)** — collections :

- `documents` (chunks 512/overlap 64, embedding `nomic-embed-text`, métadonnées : source, page, date)
- `semantic_memory` (décisions, résumés de sessions)

### 24.4 Contrat d'échange inter-agents

Message : `{ id, from, to, type, payload, timestamp, task_id }` où `type ∈ {TASK_DELEGATION, TASK_RESULT, VALIDATION_REQUEST, VALIDATION_GRANTED, VALIDATION_DENIED, MEMORY_WRITE, MEMORY_QUERY, ESCALATION}` (§9.2).

---

## 25. Installation & déploiement

### 25.1 Choix de l'OS

**Ubuntu 24.04 LTS recommandé** (ROCm mature, communauté large). Windows 11 : dépannage uniquement.

### 25.2 Préparer le système

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  curl wget git build-essential software-properties-common \
  apt-transport-https ca-certificates gnupg lsb-release \
  htop nvtop radeontop \
  python3.11 python3.11-venv python3.11-dev python3-pip pipx \
  nodejs npm
npm install -g pnpm
```

### 25.3 ROCm pour la RX 6800

```bash
# Installer ROCm (adapter la version à la ligne stable courante)
# via l'installeur amdgpu-install d'AMD :
sudo amdgpu-install --usecase=rocm,hiplibsdk --no-dkms -y
sudo reboot

# Groupes nécessaires
sudo usermod -a -G render,video $USER   # puis re-login / reboot
groups $USER                            # doit afficher : render video

# Vérifier la détection GPU
rocminfo | grep -A 5 "Agent"
rocm-smi
```

**Override critique (RX 6800 = gfx1030)** — persistant pour le shell ET le service :

```bash
echo 'export HSA_OVERRIDE_GFX_VERSION=10.3.0' >> ~/.bashrc && source ~/.bashrc

sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="HSA_OVERRIDE_GFX_VERSION=10.3.0"
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_KEEP_ALIVE=10m"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=2"
EOF
```

> En cas de `SIGSEGV` au démarrage d'Ollama avec ROCm récent, downgrader vers une version ROCm stable (ex. 6.4.1).

### 25.4 Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl daemon-reload && sudo systemctl enable --now ollama
sudo systemctl restart ollama
ollama --version

# Vérifier l'usage GPU
ollama run qwen3:8b "Dis bonjour"     # terminal 1
ollama ps ; rocm-smi                    # terminal 2 → VRAM doit grimper, backend = GPU
```

Puis télécharger les modèles par phase (§5.4).

### 25.5 Environnement Python

```bash
mkdir ~/hermes-ollama && cd ~/hermes-ollama
python3.11 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip setuptools wheel
```

`requirements.txt` (principales dépendances) :

```
fastapi  uvicorn[standard]  pydantic  python-dotenv
langchain  langchain-community  langchain-ollama  langgraph
chromadb  sqlalchemy  alembic
websockets  python-socketio
watchdog  gitpython
python-telegram-bot  apscheduler
python-jose  cryptography  python-multipart  keyring
httpx  aiofiles  rich  typer  pyyaml  jinja2
# monitoring GPU AMD (selon disponibilité) : amdgpu-stats
```

> Épingler les versions au moment du build. Vérifier la disponibilité réelle de chaque paquet (certains, comme des libs de monitoring AMD, dépendent de l'environnement) et prévoir un fallback (`rocm-smi` en subprocess).

### 25.6 Environnement Node / Frontend

```bash
# Node LTS via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc && nvm install --lts && nvm use --lts

cd ~/hermes-ollama
pnpm create next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
cd frontend
pnpm dlx shadcn@latest init         # dark theme, CSS variables
pnpm dlx shadcn@latest add button card dialog dropdown-menu input label badge \
  progress separator sheet sidebar tabs table toast tooltip scroll-area \
  skeleton avatar alert-dialog command popover
pnpm add framer-motion zustand recharts @xyflow/react \
  @xterm/xterm @xterm/addon-fit @xterm/addon-web-links \
  socket.io-client lucide-react react-markdown remark-gfm rehype-highlight
```

### 25.7 Fichier `.env` (template)

```bash
# ── OLLAMA ──────────────────────────────────────────
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_KEEP_ALIVE=10m

# ── MODÈLES PAR DÉFAUT (vérifiés) ───────────────────
MODEL_SWIFT=qwen3:1.7b
MODEL_STANDARD=qwen3:14b
MODEL_CODE=qwen3-coder:30b
MODEL_REASONING=deepseek-r1:14b
MODEL_WRITING=qwen3:8b
MODEL_VISION=gemma3:12b
MODEL_SECURITY=phi4:14b
MODEL_EMBED=nomic-embed-text
MODEL_FALLBACK_HEAVY=deepseek-r1:32b

# ── BACKEND / FRONTEND ──────────────────────────────
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
SECRET_KEY=change_me_with_a_random_256bit_key
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# ── MÉMOIRE ─────────────────────────────────────────
CHROMA_PATH=./data/db/chroma
SQLITE_PATH=./data/db/hermes.db

# ── SÉCURITÉ ────────────────────────────────────────
ALLOWED_PATHS=/home/user/projects,/home/user/documents
MAX_FILE_SIZE_MB=50

# ── TELEGRAM (optionnel) ────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ── GPU MONITORING ──────────────────────────────────
GPU_VRAM_TOTAL_GB=16
GPU_ALERT_TEMP_C=85
GPU_CRITICAL_TEMP_C=90
GPU_VRAM_WARNING_PCT=85

# ── AUTO-ÉVOLUTION ──────────────────────────────────
SKILL_AUTO_VALIDATE_THRESHOLD=0.95
SKILL_MIN_CONFIDENCE=0.30
REFLECTION_ENABLED=true
EBBINGHAUS_DECAY_ENABLED=true
```

### 25.8 Lancement

```bash
# Backend
cd ~/hermes-ollama && source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000        # --reload en dev

# Frontend (2e terminal)
cd ~/hermes-ollama/frontend && pnpm dev                    # ou pnpm build && pnpm start
```

Script `start.sh` recommandé : vérifie Ollama, affiche le statut GPU (`rocm-smi`), liste les modèles, démarre backend puis frontend, gère l'arrêt propre (`trap`).

| Service | URL |
|---|---|
| Interface Hermes | http://localhost:3000 |
| API FastAPI | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Ollama API | http://localhost:11434 |

### 25.9 Vérifications

```bash
ollama ps ; ollama list
rocm-smi ; rocm-smi --showmeminfo vram ; rocm-smi --showtemp
sudo systemctl status ollama ; sudo journalctl -u ollama -f
free -h ; df -h ~/.ollama
```

### 25.10 Dépannage

| Problème | Symptôme | Solution |
|---|---|---|
| GPU non détecté | `ollama ps` montre CPU | Vérifier `HSA_OVERRIDE_GFX_VERSION=10.3.0` dans le service |
| OOM VRAM | Crash au chargement | Modèle de tier inférieur / downgrade auto |
| ROCm non détecté | `rocminfo` vide | `usermod -a -G render,video` + reboot |
| SIGSEGV ROCm | Crash démarrage Ollama | Downgrader ROCm (ex. 6.4.1) |
| Ollama lent (CPU) | <5 t/s, pas de VRAM | Redémarrer le service après l'override |
| ChromaDB | Permission denied | `chmod -R 755 ./data/db/chroma` |
| Port 8000 occupé | FastAPI ne démarre pas | `lsof -i :8000` puis kill |

---

## 26. Règles de fonctionnement & d'autonomie

### 26.1 Règles générales

Ne pas agir sans contexte suffisant ; ne pas supposer une intention non exprimée ; demander validation pour tout risque ; privilégier la clarté sur l'exhaustivité ; éviter les changements inutiles ; documenter toute action importante.

### 26.2 Règles de qualité

Chaque sortie doit être vérifiable ; chaque action explicable ; chaque changement justifié ; chaque blocage visible.

### 26.3 Règles spécifiques matériel

Ne jamais charger un modèle si la VRAM disponible est insuffisante → downgrade auto ; surveiller la température GPU (alerte > 85 °C, pause suggérée > 90 °C) ; ne pas lancer deux modèles lourds simultanément ; préférer un modèle déjà chargé à un modèle légèrement meilleur nécessitant un rechargement.

---

## 27. Priorités de développement

### Priorité haute
Orchestration de base + client Ollama ; routage de modèles configurable ; mémoire persistante (SQLite + ChromaDB) ; gestion de tâches ; journalisation structurée ; validation humaine ; vérification technique de base ; **monitor GPU basique (VRAM)**.

### Priorité moyenne
Interface Next.js complète ; intégration Telegram ; recherche avancée documents ; score de confiance des réponses ; résumé automatique de contexte ; gestion fine des profils de modèles ; **double-check par second modèle**.

### Priorité basse
Agents spécialisés multiples avancés ; tableaux de bord & métriques riches ; automatisations multi-étapes complexes ; support multimodal poussé ; personnalisation avancée ; auto-évolution complète (HSE).

> **Ordre de construction recommandé (walking skeleton) :** `ollama_client` → `router` (config) → 1 agent (Prime) → FastAPI `/chat` streaming → page Chat minimale → mémoire → tâches → Aegis → monitor GPU → agents restants → workflows → HSE.

---

## 28. Critères d'acceptation & matrice de tests

### 28.1 Critères d'acceptation

Le projet est conforme si Hermes peut :

- comprendre une demande simple et répondre en < 5 s ;
- choisir automatiquement un modèle adapté parmi ceux disponibles ;
- utiliser la mémoire pertinente sans tout réinjecter ;
- analyser un document local et en extraire une synthèse ;
- résumer un contexte long de manière cohérente ;
- proposer un plan d'action explicite et validable ;
- modifier un fichier autorisé avec **diff présenté avant application** ;
- exécuter une vérification (lint, tests) et en rapporter le résultat ;
- signaler une erreur proprement avec le contexte d'échec ;
- demander validation avant toute action sensible ;
- reprendre une mission après interruption au dernier point sûr ;
- garder des traces lisibles et consultables de chaque session ;
- fonctionner pour des projets variés sans reconfiguration lourde ;
- **exploiter la RX 6800 pour l'inférence GPU sans configuration manuelle**.

### 28.2 Matrice de tests (Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| T1 | Ollama actif, modèles Phase 1 installés | L'utilisateur pose une question simple | Réponse en streaming, premier token < 1 s (Tier 1) |
| T2 | Une tâche de code est demandée | Le routeur choisit un modèle | `qwen3-coder:30b` sélectionné, tracé dans le log |
| T3 | `qwen3:14b` déjà chargé en VRAM | Nouvelle tâche standard arrive | Le modèle chargé est réutilisé (pas de rechargement) |
| T4 | VRAM insuffisante pour le modèle demandé | Demande de chargement | Downgrade automatique vers un tier inférieur + alerte |
| T5 | Un document PDF est importé | Recherche sémantique | Passages pertinents retournés avec scores (< 500 ms) |
| T6 | Une modification de fichier est proposée | Avant application | Diff lisible affiché, attente d'approbation |
| T7 | Action = suppression de fichier | L'agent tente l'action | Aegis exige une validation humaine |
| T8 | Session interrompue en cours de mission | Redémarrage | Reprise au dernier point sûr, contexte préservé |
| T9 | Code modifié | Fin de tâche | Lint + tests exécutés, résultat rapporté |
| T10 | Température GPU > 85 °C | Monitoring | Alerte affichée ; > 90 °C → pause suggérée |
| T11 | Ollama arrêté (port 11434 fermé) | Requête | 3 tentatives (backoff) puis notification claire |
| T12 | Un `.env`/secret est ciblé par une action | Tentative de modification | Validation humaine obligatoire, secret jamais loggé en clair |

---

## 29. Annexes

### Annexe A — Glossaire

- **Ollama** : serveur d'inférence local exposant une API REST (port 11434).
- **ROCm / HIP** : pile de calcul GPU d'AMD (équivalent CUDA).
- **VRAM** : mémoire vidéo du GPU (16 Go ici).
- **Offload** : report de couches du modèle sur CPU/RAM quand la VRAM est insuffisante.
- **Quantisation (Q4/Q6/Q8)** : compression des poids ; Q4 = plus léger/rapide, Q8 = plus précis/lourd.
- **MoE (Mixture-of-Experts)** : architecture où seuls quelques experts (paramètres actifs) sont utilisés par token → qualité d'un gros modèle, coût d'un petit.
- **RAG** : Retrieval-Augmented Generation (recherche + génération).
- **Embedding** : représentation vectorielle d'un texte pour la recherche sémantique.
- **Skill (HSE)** : procédure réutilisable apprise par le système, avec score de confiance et decay.
- **Decay (Ebbinghaus)** : décroissance du score des mémoires/skills peu utilisées.
- **Keepalive** : durée de rétention d'un modèle en VRAM après usage.
- **Tier** : niveau de modèle (Turbo/Standard/Qualité/Puissant/Extrême).

### Annexe B — Pistes prospectives *(NON NORMATIF)*

> ⚠️ Cette annexe est de la **veille technologique**. Ces éléments **ne doivent pas être implémentés** dans le corps du système tant que leur disponibilité réelle sur Ollama n'est pas confirmée. Ils remplaceraient, le cas échéant, certains modèles vérifiés — via `models.yaml` uniquement, sans toucher au cœur.

- **Modèles 1-bit natifs (famille « Bonsai » / PrismML)** : promesse d'un
  8B tenant dans ~1 Go et d'un 27B dans ~4 Go.
  **Testé le 2026-07-25 — verdict : réel, mais inutilisable en l'état.**
  PrismML a publié Bonsai 27B le 14/07/2026 : compression ternaire de
  Qwen3.6-27B, poids {−1, 0, +1}, 1,71 bit/poids, 7,17 Go pour le build
  ternaire, multimodal, 262k de contexte, Apache 2.0. ROCm est annoncé
  supporté. Le modèle a été téléchargé et testé sur la machine cible :
  **Ollama ne peut pas le charger** — `tensor "output.weight" size
  overflow`, au chargement comme à la génération. Le format `Q2_0_g128`
  provient d'un *fork* de llama.cpp avec noyaux personnalisés, non
  remonté en amont ; l'Ollama de la machine (0.32.3) embarque la version
  amont. Aucun build du dépôt n'est exploitable : les variantes `Q2_0`,
  `PQ2_0` et `Q2_g64` partagent ce format, `F16` pèse 53,8 Go (hors
  budget VRAM), et les fichiers `dspark-*` sont des modèles *drafter*
  pour décodage spéculatif, pas le modèle principal. Blob supprimé.
  **À reconsidérer uniquement si le format est remonté dans llama.cpp
  amont**, donc dans Ollama. L'intérêt reste entier : un 27B multimodal
  à ~7 Go libérerait la moitié du budget VRAM et couvrirait à la fois les
  rôles `code` et `vision`.
- **`gemma4`** : n'est plus prospectif — sorti depuis, installé, et promu
  au rôle `vision` dans `models.yaml` (voir §5.1).
- **Moteur d'inférence « Colibrì »** : proof-of-concept streamant des experts depuis le SSD pour faire tourner des modèles massifs (centaines de milliards de paramètres) sur peu de RAM, mais à une vitesse inutilisable (~0,05 t/s). **Hors périmètre** — à surveiller, pas à utiliser.
- **Nouvelles générations denses** (au-delà de `qwen3`/`gemma3`) : dès qu'un modèle supérieur est disponible sur Ollama et tient dans les contraintes VRAM, l'ajouter dans `models.yaml` et mettre à jour la matrice de routage (§10).

### Annexe C — Changelog du cahier des charges

- **v2.0** — édition matérielle : sections matériel, stack, catalogue modèles, profils de perf, stockage, règles de routage avec seuils.
- **Catalogue 07/2026** — recommandations par agent, combos VRAM, sélections par phase (incluait des modèles spéculatifs).
- **v4.0 (install & interface)** — OS/ROCm/Ollama, env Python/Node, arborescence complète, `.env`, spécification détaillée des 9 vues + design system.
- **v4.0.1 (2026-07-26)** — mise à jour factuelle après audit de conformité :
  tableaux de modèles (§5.1, §9.1) alignés sur `config/models.yaml`, qui
  fait foi pour les tags exacts ; Annexe B enrichie du résultat réel du
  test Bonsai 27B et de la sortie de `gemma4` du prospectif. Aucun
  changement normatif : seules des constatations.
- **v4.0 consolidée** — fusion normative des trois sources ; **substitution des modèles spéculatifs par des modèles vérifiés** ; ajout : fiches agents normalisées, protocole message bus, esquisse API/modèle de données, matrice de tests d'acceptation, séparation normatif/prospectif.

### Annexe D — Récapitulatif d'installation en 9 étapes

```
1. OS         Ubuntu 24.04 LTS
2. ROCm       amdgpu-install + usermod render/video + HSA_OVERRIDE_GFX_VERSION=10.3.0
3. Ollama     install.sh + config systemd + pull des modèles (par phase)
4. Python     venv 3.11 + requirements.txt
5. Node       pnpm + Next.js 15 + shadcn/ui + dépendances frontend
6. Structure  arborescence monorepo + .env configuré
7. Lancement  ./start.sh → backend :8000 + frontend :3000
8. Accès      http://localhost:3000
9. Vérif      rocm-smi + ollama ps + /docs
```

---

*Fin du cahier des charges — Hermes Ollama v4.0 consolidée. Configuration RX 6800 16 Go / i5-13500 / 32 Go DDR5. Document normatif, réutilisable sur tout LLM. Source de vérité unique du projet.*
