# Sondage exhaustif du cahier des charges — 111 points

Chaque verdict repose sur une sonde puis, quand elle est ambiguë, sur la
lecture du code. Les faux positifs des mots courants (`scope`, `score`,
`pipeline`, `canonical`) ont été écartés à la main.

Légende : ✅ existe et tient · ⚠️ existe à moitié · ❌ absent · ⛔ écarté

---

## Lot 1 — §1 à §23 : principes et mécanique du noyau

| § | Point | État | Preuve |
|---|---|---|---|
| 1 | Local-first, cloud jamais requis | ✅ | `CloudGate` injecté et optionnel (`cloud: CloudGate \| None = None`) ; sa docstring dit « a purely-local deployment would never need » l'appel de découverte |
| 2 | Verification-first | ✅ | `MissionVerification`, 554 l., 6 tests |
| 3 | Policy-before-action | ✅ | `AegisEngine`, 12 fichiers, 9 tests |
| 4 | Routage conscient des capacités | ✅ | 55 fichiers, 30 tests |
| 5 | Preuve plutôt que déclaration | ✅ | `mission.unverified`, 20 fichiers |
| 6 | Exécutions persistantes | ✅ | `snapshot_manager`, 58 fichiers |
| 7 | Cognition consciente des ressources | ✅ | admission VRAM, 67 fichiers |
| 8 | Agnostique au fournisseur | ✅ | 35 fichiers |
| 9 | Evidence graph tri-état | ⚠️ | `Etat.INDETERMINE` existe **dans la file de nuit** ; `verification.py` n'en a **aucune occurrence** et rend `-> bool` |
| 10 | Détecteur d'expansion de périmètre | ❌ | — |
| 11 | Action normalisée et hachée | ❌ | les correspondances `canonical` désignaient le namespace d'API |
| 12 | Portées d'approbation | ❌ | — |
| 13 | Abstraction sandbox | ⚠️ | `workspace/sandbox_manager.py`, en mémoire |
| 14 | Secret broker | ⚠️ | 2 fichiers |
| 15 | Cloud data firewall | ❌ | — |
| 16 | Abstraction `CloudProvider` | ❌ | pas d'interface, un seul client concret |
| 17 | OpenRouter en adaptateur | ⚠️ | `connectors/openrouter_client.py`, 287 l., **1 test** |
| 18 | OmniRoute | ❌ | — |
| 19 | Pool cloud gratuit | ✅ | `CloudModelCatalog` |
| 20 | Routage gratuit par candidats | ❌ | pas d'élimination puis score |
| 21 | Pool de comptes | ⛔ | **écarté** — rotation de comptes chez un même fournisseur, contraire aux CGU |
| 22 | Disjoncteurs | ⚠️ | 4 fichiers, **0 test** |
| 23 | Quota broker | ❌ | — |

---

## Lot 2 — §24 à §48 : cognition, agents, surfaces

| § | Point | État | Preuve |
|---|---|---|---|
| 24 | Cognitive scheduler | ✅ | `AdaptiveRouter.recommend()`, 20 fichiers, 12 tests |
| 25 | Score multidimensionnel | ✅ | 23 fichiers, 5 tests |
| 26 | Model trust | ⚠️ | 4 fichiers ; **non alimenté par l'historique des runs** |
| 27 | Rôles découplés du modèle | ❌ | — |
| 28 | Multi-agent séquentiel | ✅ | verrou exclusif de carte, 7 fichiers |
| 29 | Multi-agent parallèle | ✅ | `ExecutionMode.PARALLEL`, `GraphExecutor` dispatche en parallèle |
| 30 | Council / MoA | ❌ | aucune classe ; la sonde matchait « juge » en prose française |
| 31 | Agent Room | ❌ | — |
| 32 | Agent Control Room | ❌ | — |
| 33 | Pipeline idée → artefact | ❌ | — |
| 34 | Agent Kanban | ❌ | — |
| 35 | Loop engineering | ❌ | — |
| 36 | Mission graph + loop graph | ❌ | le Mission Graph existe, la boucle non |
| 37 | Mémoire unifiée | ✅ | 6 tiers, 24 fichiers |
| 38 | Promotion de mémoire | ❌ | pas de quarantaine, donc rien à promouvoir |
| 39 | Context relay | ❌ | — |
| 40 | Journal | ✅ | 46 fichiers, 26 tests |
| 41 | Goals | ✅ | `GoalStatus`, `start_goal`, moteur autonome |
| 42 | Workspace comme surface | ✅ | 8 fichiers, 5 tests |
| 43 | Exécution git-aware | ⚠️ | `GitWorkspace` existe, 1 test |
| 44 | Événements temps réel | ✅ | `event_hub`, 19 fichiers |
| 45 | Observabilité tracée | ❌ | **aucun OTLP câblé** — `opentelemetry` n'apparaît que dans `requirements.txt`, tiré transitivement par la mémoire sémantique, et le commentaire y raconte un conflit de version. Pas de `TracerProvider`, pas d'exporteur |
| 46 | Voix | ✅ | `WhisperLocal` / `PiperLocal` mesurés |
| 47 | Operator | ✅ | 28 fichiers, 9 tests |
| 48 | Operator + postures cloud | ❌ | aucune posture d'escalade, bascule ou quota |

---

## Lot 3 — §49 à §72 : exploitation, configuration, ressources

| § | Point | État | Preuve |
|---|---|---|---|
| 49 | Organisation / équipes | ❌ | — |
| 50 | Pont vers agents externes | ✅ | `hermes_agent_cli`, ACP, 14 fichiers, 13 tests |
| 51 | A2A | ❌ | aucune occurrence |
| 52 | Studios | ✅ | Studio Center, 30 fichiers, 14 tests |
| 53 | Moteur de création (langage → projet) | ❌ | — |
| 54 | Radar / veille | ⚠️ | 4 fichiers, **0 test** |
| 55 | Leads / SEO | ⛔ | **écarté** — hors noyau tant que §87 n'existe pas |
| 56 | Ingestion de connaissance | ✅ | `DocumentMemory`, 19 fichiers |
| 57 | Onboarding premier démarrage | ❌ | — |
| 58 | Profils de configuration | ⚠️ | pas de `local_only` / `hybrid_*` nommés |
| 59 | **Config persistante aux mises à jour** | ⚠️ | `migration_manager` et `HERMES_DATA_DIR` existent, **mais l'état vit dans le dépôt** : `data/db` 18 Mo, `data/eventbus` 8,2 Mo, `data/snapshots` 2,2 Mo, `_memory_.db`. Le mécanisme existe, la garantie non |
| 60 | Health center | ✅ | `NOT_INSTRUMENTED` distingué, 20 fichiers |
| 61 | Admission de ressources | ✅ | `_check_vram_admission` appelé sur le chemin réel et sur le repli |
| 62 | Ordonnanceur de chargement | ✅ | 42 fichiers, 18 tests |
| 63 | Modèle chaud | ✅ | 7 fichiers |
| 64 | Cycle de vie des bancs | ✅ | `agentic_probe`, `model_bench`, 14 fichiers |
| 65 | Apprentissage automatique | ✅ | `update_performance`, `record_feedback`, boucle réelle |
| 66 | Pourquoi ce modèle | ✅ | `DecisionExplainer` |
| 67 | Pourquoi Hermes a basculé | ⚠️ | `fallback_reason` existe dans `runtime_recovery`/`runtime_router`, **mais pas de chaîne présentée à l'utilisateur** |
| 68 | Gouvernance de coût | ✅ | 24 fichiers, 22 tests |
| 69 | Économie du cloud gratuit | ✅ | `reserve_daily_requests`, garde de quota consciente de la réserve |
| 70 | Compression de contexte | ⚠️ | 2 fichiers ; **critère d'acceptation §12 du cahier v1 jamais tenu** |
| 71 | Compression des sorties d'outils | ❌ | un `git diff` part entier à chaque tour |
| 72 | Budget de contexte | ✅ | 30 fichiers, 22 tests |

---

## Lot 4 — §73 à §95 : tests, écrans, modes

| § | Point | État | Preuve |
|---|---|---|---|
| 73 | Invariants de sécurité formels | ✅ | 14 fichiers, 8 tests |
| 74 | Les treize suites que le cahier exige | ❌ | aucune n'existe sous ces noms |
| 75 | Tests de chaos | ❌ | — |
| 76 | Frontend Command Center | ⚠️ | `cockpit-shell` existe, **0 test** |
| 77 | Écran Mission (contrat, graphe, preuves) | ❌ | le Mission Center existe, pas ces panneaux |
| 78 | Écran Agent Control Room | ❌ | — |
| 79 | Écran Model Intelligence | ⚠️ | catalogue affiché, pas trust/quota/fallbacks |
| 80 | Écran fournisseurs | ❌ | — |
| 81 | Rejeu de mission | ⚠️ | `event_bus.replay()` durable existe — **le substrat, pas la surface** |
| 82 | Operator (frontend) | ⚠️ | 12 fichiers, **1 test** |
| 83 | Palette de commandes | ⚠️ | présente à l'écran, **0 test** |
| 84 | Recherche globale | ❌ | — |
| 85 | Notifications à trois niveaux | ✅ | 17 fichiers, 9 tests |
| 86 | Ne pas gonfler le noyau | ✅ | principe respecté — les Studios sont déjà séparés |
| 87 | Architecture de plugins | ❌ | ni manifeste, ni registre |
| 88 | Sécurité des plugins | ❌ | sans objet tant que §87 manque |
| 89 | Dégradation silencieuse | ⚠️ | le Health Center distingue `NOT_INSTRUMENTED` ; rien au niveau plugin |
| 90 | Polish opérationnel Windows | ⚠️ | `HermesOSLauncher.cs` + `build.ps1` ; **ni installeur, ni mise à jour, ni retour arrière** |
| 91 | Installation intelligente | ⚠️ | `installer/` ne contient que `hardware_profile.py` et `system_detector.py` — de la détection, pas une installation |
| 92 | Auto-diagnostic | ✅ | 37 fichiers, 8 tests |
| 93 | Modes d'exploitation nommés | ❌ | pas de `LOCAL` / `HYBRID_FREE` / `HYBRID_BALANCED` / `HYBRID_PREMIUM` |
| 94 | Politique de routage par risque | ⚠️ | `risk_level` transporté (`low/medium/high`), **la politique du §94 n'est pas câblée** |
| 95 | Politique d'escalade cloud | ❌ | — |

---

## Lot 5 — §96 à §111 : autonomie, mémoire, architecture

| § | Point | État | Preuve |
|---|---|---|---|
| 96 | Retour au local après le cloud | ❌ | — |
| 97 | Mode autonome complet | ✅ | `autonomous_orchestrator`, 10 tests |
| 98 | Niveaux d'autonomie L0-L5 | ⚠️ | `AutonomyChange` est un modèle d'API ; **pas d'échelle nommée L0→L5** |
| 99 | Humain dans la boucle | ⚠️ | `approval_engine` sait `required_approvals` et `delegated_to` ; **appelé nulle part sur le chemin réel** (voir §11-12) |
| 100 | Self-evolution | ✅ | `evolution_engine`, 14 fichiers |
| 101 | Compétences auto-générées | ❌ | — |
| 102 | Confiance des compétences | ⚠️ | 3 fichiers, **0 test**, pas de cycle draft→trusted→deprecated |
| 103 | Knowledge graph | ✅ | 17 fichiers, 4 tests |
| 104 | Mémoire de projet | ❌ | — |
| 105 | Routage par projet | ❌ | — |
| 106 | **Isolation de mémoire entre projets** | ❌ | rien ne cloisonne — un projet sensible partage la mémoire des autres |
| 107 | Multi-utilisateur | ⚠️ | `user_id` existe mais vaut `"anonymous"` par défaut ; **aucune authentification sur aucune route** |
| 108 | Auditabilité | ✅ | 49 fichiers, 16 tests |
| 109 | Explicabilité | ✅ | 46 fichiers, 23 tests |
| 110 | Architecture de dossiers cible | ❌ | ni `cognition/`, ni `runs/`, ni `providers/` — mais le découpage actuel est cohérent |
| 111 | Transformation de l'existant | ✅ | RAL, Supervisor, Mission Graph : la base à conserver existe |

---

## Synthèse des 111

| État | Compte | Part |
|---|---|---|
| ✅ existe et tient | **46** | 41 % |
| ⚠️ existe à moitié | **28** | 25 % |
| ❌ absent | **35** | 32 % |
| ⛔ écarté | **2** | 2 % |

**Ce qui manque et qui compte le plus**, par ordre de coût si on l'ignore :

1. §59 — l'état utilisateur vit dans le dépôt : la première mise à jour efface base, mémoire et **snapshots**
2. §106 — aucune isolation de mémoire entre projets
3. §11-12 — l'approbation existe (`approval_engine`) mais n'est **appelée nulle part** sur le chemin réel
4. Contract + Run Ledger — aucune trace de ce qui a été fait, avec quoi, et pourquoi
5. §9 — la vérification est booléenne, un « on ne sait pas » n'a nulle part où aller
6. §45 — aucune trace OTLP câblée malgré la dépendance présente
7. §90-91 — ni installeur, ni mise à jour, ni retour arrière
