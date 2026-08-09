# R-006 — Code Intelligence : intégration réelle, Cockpit complet, validation locale

**Date** : 9 août 2026
**Nature** : intégration (raccordement de code existant), pas de nouveau sous-système.
**Machine** : Windows 11 · i5-13500 · 32 Go DDR5 · **AMD RX 6800 16 Go** · Ollama · Hermes OS local · Next.js

> Chaque affirmation ci-dessous est appuyée par une exécution réelle (test hermétique, requête HTTP réelle contre le backend local, ou appel direct au composition root). Aucune valeur n'est estimée ni extrapolée. Les échecs trouvés — y compris ceux non corrigés dans cette passe — sont documentés, pas masqués.

---

## Décision

# **GO AVEC CONDITIONS**

Le diagnostic initial était exact : `CodeIntelligenceRouter` et `CodeIntelligenceAgent` (HOS-055D) étaient du code réel et non trivial, **jamais instancié en production**. Ils le sont maintenant, via le composition root réel, aux côtés d'une troisième voie authentique (Hermes-native, Model Intelligence → Runtime → Ollama) qui n'existait pas du tout avant cette passe.

Ce qui fonctionne réellement, de bout en bout, vérifié en direct : la voie **Hermes-native** (inférence Ollama réelle, RX 6800, réponse correcte mesurée). Ce qui a été trouvé **structurellement cassé**, indépendamment du raccordement Hermes, et documenté sans être maquillé : l'intégration CLI de **KlaatCode** (commandes construites contre une interface qui n'existe pas dans la version installée) et d'**Oh My Pi** (paquet npm qui ne résout pas en exécutable). Ce qui a été trouvé **non appliqué malgré les apparences** : `ToolPolicy`/`ToolSandbox` — un garde-fou d'écriture a donc été ajouté spécifiquement pour Code Intelligence.

**Conditions restantes avant un GO sans réserve** : voir §21.

---

## 1. État initial (avant R-006)

| Constat | Preuve |
|---|---|
| `CodeIntelligenceRouter`/`CodeIntelligenceAgent` réels, jamais instanciés en production | Cartographie complète : seuls le fichier lui-même et les tests les importaient |
| Aucune route `/api/v1/code-intelligence` | `grep` sur `backend/api/` → 0 résultat ; confirmé par `curl` → `404` |
| Frontend déjà honnête sur le manque | `code-intelligence-center.tsx` affichait déjà un bandeau « Router not exposed » depuis une passe R-002 antérieure, plutôt que des données fabriquées |
| `ci_scorer.py` (Runtime Scorer) orphelin | Docstring annonçant une intégration Runtime Orchestrator jamais construite |
| KlaatCode/Oh My Pi réellement installés et interrogeables individuellement | `/klaatcode/status`, `/ohmypi/status` déjà réels (routes préexistantes, non dupliquées) |

## 2. Architecture réelle trouvée

```
CodeIntelligenceAgent (orchestrateur pur, pas un BaseAgent)
 ├─ CodeIntelligenceRouter (scoring pondéré, 5 facteurs)
 ├─ KlaatCodeAgent → KlaatCodeMCPAdapter → KlaatCodeClient → subprocess (npx klaatcode)
 ├─ OhMyPiAgent → OhMyPiMCPAdapter → OhMyPiClient → subprocess (npx omp)
 └─ HermesNativeExecutor (nouveau, R-006 Phase 3) → ModelRouter → OllamaClient → Ollama réel
```

Trois couches existaient pour KlaatCode/Oh My Pi (Agent → MCP Adapter → Client) ; seule la couche Client était réellement atteinte par les routes HTTP préexistantes (`routes.py`). Les couches Agent étaient elles-mêmes du code mort. R-006 ne les a pas dupliquées : `CodeIntelligenceAgent` route maintenant à travers les mêmes instances de production (`service_registry.py`), pas de nouvelles.

## 3. Composition root — REAL + VERIFIED

`backend/core/bootstrap/service_registry.py::_make_code_intelligence` construit `CodeIntelligenceAgent` en réutilisant **exactement** les singletons déjà adoptés pour `klaatcode`/`ohmypi` (`kc_routes._adapter`, `omp_routes._adapter`) — vérifié par identité d'objet (`is`), pas par égalité de valeur :

```python
assert agent._klaatcode_agent._mcp_adapter is bootstrap.container.get("klaatcode")
assert agent._ohmypi_agent._mcp_adapter is bootstrap.container.get("ohmypi")
```

7 tests dédiés dans `tests/integration/test_assembly.py`, tous passants contre l'app réelle (`create_app()`, pas un routeur reconstruit à la main).

## 4. Surface API — REAL + VERIFIED

`GET/POST /api/v1/code-intelligence/{status,capabilities,providers,analyze,review,debug,explain,history}` — 8 endpoints, tous adaptateurs purs (aucune logique métier dupliquée). Validation Pydantic : un `force_provider` invalide renvoie **422** avec la liste réelle des valeurs acceptées, jamais un 500.

Vérifié en direct :
```
curl /api/v1/code-intelligence/status   → agent_id, compteurs réels
curl /api/v1/code-intelligence/providers → statuts réels des 3 providers
curl -X POST .../analyze {force_provider: bogus} → 422
```

## 5. CodeIntelligenceAgent — REAL + VERIFIED

`execute_task()` classe la tâche, route, exécute, enregistre en mémoire, publie les événements, met à jour les métriques. Aucun succès fabriqué : un exécuteur non lié échoue honnêtement (comportement déjà corrigé sous R-002 P5, confirmé intact).

## 6. CodeIntelligenceRouter — REAL + VERIFIED (étendu, pas remplacé)

Scoring 5 facteurs inchangé pour KlaatCode/Oh My Pi. Un troisième candidat (`HERMES_NATIVE`) ajouté avec son propre scoring, **désactivé par défaut** (`hermes_native_available: bool = False`) pour préserver exactement le comportement des appelants existants et des tests antérieurs à R-006. 7 nouveaux tests couvrent : éligibilité par type de tâche, exclusion honnête des types sans équivalent (`DEBUGGING`, `DIAGNOSTICS`, `ARCHITECTURE_REVIEW` n'ont pas de version Hermes-native), et un test d'adaptation réelle (l'historique fait bien basculer le gagnant).

## 7. Hermes-native — REAL + VERIFIED (nouveau, R-006 Phase 3)

`HermesNativeExecutor` : même `ModelRouter`/`OllamaClient` que tout le reste de Hermes (aucun second moteur). Limité aux types de tâches réellement une génération one-shot (`CODE_ANALYSIS`, `CODE_GENERATION`, `REFACTORING`, `CODE_REVIEW`, `DOCUMENTATION`, `TEST_GENERATION`, `OPTIMIZATION`) — `DEBUGGING`/`DIAGNOSTICS`/`ARCHITECTURE_REVIEW` en sont explicitement exclus (aucun débogueur, aucune analyse de projet réelle).

**Exécution réelle mesurée** (via l'UI reconstruite, force_provider=hermes_native) :
```
Tâche : "Explique en une phrase ce que fait cette fonction" + code réel
Modèle : qwen3-coder:30b (choisi par ModelRouter, priorité par défaut)
Durée : 29 242 ms
Résultat : "Cette fonction prend deux paramètres a et b et retourne leur somme."
```
Réponse correcte, GPU réellement sollicité (RX 6800), durée cohérente avec un modèle 30B en réponse froide.

## 8. KlaatCode — INTÉGRATION RÉELLE, CAPACITÉ CASSÉE (anomalie majeure, non corrigée)

Réellement installé (`npx klaatcode --help` répond), réellement invoqué en subprocess. **Mais** `klaatcode_client.py::_build_command` construit des commandes (`analyze --project`, `inspect --file`, `plan`, `edit --content`, `search`, `diagnostics --file`, `validate --file`) qui ne correspondent à **aucune commande réelle** du CLI installé (version 2.4.4). La vraie interface, révélée par `--help` :

```
chat [options] [dir]    Start interactive AI chat (default command)
run [options] [prompt]  Run a task non-interactively (agentic)
serve / web / acp / login / logout / whoami / completions
```

Conséquence mesurée : `POST /code-intelligence/analyze {force_provider: klaatcode}` → routage correct, action résolue correctement (`analyze_project`), subprocess réellement lancé, **échec réel** : `error: unknown option '--project'`. Hermes atteint réellement KlaatCode (le critère de R-006) ; KlaatCode lui-même ne peut aboutir sur aucune action testée, indépendamment de Hermes. Voir §19 pour le périmètre de la correction.

## 9. Oh My Pi — PAQUET RÉEL, EXÉCUTABLE INTROUVABLE (anomalie majeure, non corrigée)

`omp@1.0.0` existe réellement sur npm (`npm view omp` le confirme), mais `npx omp` échoue systématiquement : `npm error could not determine executable to run` — le paquet ne déclare pas de `bin` utilisable par `npx` dans cet environnement. Conséquence mesurée : toute tâche routée vers Oh My Pi échoue à l'étape subprocess, jamais à l'étape de routage/traduction Hermes.

## 10. MCP — REAL + VERIFIED (bug corrigé)

Avant R-006 : KlaatCode liait un adaptateur jetable (pas celui interrogé par les routes), Oh My Pi n'avait même pas de notion de `server_bound`. Corrigé :
- `registry_seeding.py` passe désormais le **vrai** adaptateur adopté à `register_klaatcode()`.
- `OhMyPiMCPAdapter` a maintenant un vrai `bind_server()`/`_server`, câblé depuis `_register_ohmypi_server()`.
- Nouvel état explicite à 5 valeurs (`derive_mcp_status`) : `not_configured` / `unavailable` / `unbound` / `connected` / `disconnected` — jamais « connecté » simplement parce qu'une classe existe.

Mesuré en direct après correction : KlaatCode → `server_bound: true, mcp_status: "disconnected"` (lié à un vrai enregistrement, mais aucune poignée de main MCP live n'existe nulle part dans ce code — honnête). Oh My Pi → `server_bound: true, mcp_status: "unavailable"` (lié, mais le client sous-jacent ne répond jamais réellement).

## 11. Sandbox — GARDE-FOU RÉEL AJOUTÉ (R-006 Phase 9)

Découverte critique en auditant : `ToolPolicy.evaluate()` a une branche `WRITE` qui est un **no-op documenté** (`# Policy engine would check sandbox readonly status` → `pass`), et **ni** `KlaatCodeMCPAdapter.execute()` **ni** `OhMyPiMCPAdapter.execute()` ne consulte jamais le `ToolSandbox` qu'ils reçoivent au constructeur. Rien, en dessous de `CodeIntelligenceAgent`, n'empêchait réellement une écriture.

Correction scopée à Code Intelligence (pas une réécriture de la plateforme Tools/MCP entière, hors périmètre de R-006) : `CodeIntelligenceAgent._unsandboxed_write()` refuse catégoriquement toute tâche `REFACTORING`/`CODE_GENERATION` routée vers KlaatCode ou Oh My Pi (Hermes-native est exempté — il ne touche jamais un fichier). Vérifié contre le composition root réel :
```
agent.execute_task("refactoring", {}, force_provider=KLATCODE)
→ FAILURE : "refactoring would write through an external provider with no sandbox — refused"
```
Aucun des 4 endpoints HTTP exposés (`analyze/review/debug/explain`) n'atteint de toute façon un type de tâche à écriture — confirmé par les tables de traduction réelles (`CI_TO_KLAATCODE_TASK_TYPE`/`CI_TO_OHMYPI_TASK_TYPE`).

## 12. Runtime (`ci_scorer.py`) — LEGACY, documenté orphelin (R-006 Phase 10)

`CIRuntimeScorer` reste non câblé, délibérément : le câbler dans `CodeIntelligenceRouter` dupliquerait le scoring déjà réel (mêmes 5 facteurs) ; le câbler dans le vrai Runtime Orchestrator confondrait deux décisions distinctes (sélection d'un runtime d'inférence Ollama/GPU vs. sélection d'un outil CLI externe). Documenté dans le fichier lui-même et dans `ROADMAP.md` (réf. M-14).

## 13. Model Intelligence — REAL + INTEGRATED (via Hermes-native uniquement)

`ModelRouter`/`config/models.yaml` interviennent réellement dans le chemin Hermes-native (`code_analysis`, `code_generation`, `code_refactor`). **Décision d'architecture explicite de l'utilisateur** : KlaatCode/Oh My Pi restent des providers externes avec leur propre mode d'exécution — Model Intelligence ne s'applique jamais à eux. Confirmé : `grep ModelRouter` sur les chemins klaatcode/ohmypi → 0 résultat.

## 14. EventBus — REAL + VERIFIED (bug corrigé)

`ci.task.started` était déclaré dans `CI_EVENTS` depuis HOS-055D sans **aucun** appel `.publish()` nulle part — corrigé. Les 7 événements (`agent_ready`, `routing_decided`, `task_started`, `task_completed`, `task_failed`, `hybrid_executed`, `recorded_to_memory`, plus 2 nouveaux `hermes_native_completed`/`hermes_native_failed`) sont enregistrés dans le composition root (`produced_events`) et atteignent réellement le bus système — vérifié en interrogeant `SystemEventBus.query()` après une exécution réelle :
```python
agent.execute_task("code_analysis", {}, force_provider=KLATCODE)
types = {e.type for e in bus.query() if e.source == "code_intelligence"}
assert "ci.task.started" in types  # le trou historique, maintenant comblé
assert "ci.routing.decided" in types
```

## 15. Frontend — REAL + VERIFIED (Cockpit reconstruit, R-006 Phase 8)

Le Center précédent affichait honnêtement l'absence d'API (hérité de R-002). Reconstruit entièrement sur `/api/v1/code-intelligence/*` : Overview (tâches, taux de succès, provider actif), Providers (3 cartes réelles), Code Tasks (formulaire réel : type de tâche, provider forcé, chemin, instruction, code), Routing & Execution (dernière décision réelle + résultat), History (tableau réel). Bug corrigé en chemin : `success_rate` était affiché sans `× 100` (`0.73` → « 1 % » au lieu de « 73 % »).

Vérifié en direct dans le navigateur, cycle complet : sélection de provider → lancement → réponse Ollama réelle affichée → entrée d'historique réelle créée.

## 16. Tests — 4 nouveaux fichiers, ~90 tests dédiés à R-006, suite complète vérifiée

`test_code_intelligence_routes.py`, `test_hermes_native_executor.py`, `test_mcp_status.py`, `test_provider_install_detection.py`, plus extensions de `test_code_intelligence.py`, `test_klaatcode_integration.py`, `test_ohmypi_integration.py`, `test_assembly.py`. Deux tests préexistants corrigés parce qu'ils asseraient l'ancien comportement fabriqué (succès simulé via un stub) plutôt que le comportement réel désormais honnête — pas supprimés, corrigés pour vérifier le vrai comportement (voir §20).

**Suite complète** (`tests/` + `backend/tests/`) : **3677 passed, 3 skipped**, 2 échecs, 745,71 s. Les deux échecs sont des anomalies de timing/ordonnancement **préexistantes**, sans rapport avec Code Intelligence, confirmées en isolant chacune (passent seules en < 1 s) :
- `test_task_executor_shares_the_container_model_intelligence` — flake d'ordonnancement déjà documenté aux passes précédentes (HOS-073 à HOS-075).
- `test_audit_log.py::test_throughput_is_measured_from_the_first_token` — mesure de débit sensible au timing réel (`asyncio.run` + `delay=0.01`), sensible à la charge machine pendant une exécution de suite complète de 12+ minutes ; sans lien avec `backend/audit_log.py` ni aucun fichier modifié dans cette passe.

Frontend : `tsc --noEmit` → 0 erreur. `vitest run` → 69/69 (dont les 4 nouveaux tests React pour le bug de pourcentage et le Center reconstruit — les premiers tests React du projet, `@vitejs/plugin-react` ajouté à `vitest.config.ts` pour les rendre exécutables). `next build` → succès (ESLint absent du projet, préexistant, sans lien avec R-006 — le build aboutit quand même).

## 17. Tâches réellement exécutées (séquentiel, jamais en parallèle)

| Provider | Tâche | Résultat | Détail |
|---|---|---|---|
| Hermes-native | `code_analysis` (explication de fonction) | ✅ Succès | qwen3-coder:30b, 29 242 ms, réponse correcte |
| KlaatCode | `code_analysis` → `analyze_project` | ❌ Échec réel | `unknown option '--project'` — CLI installé, interface différente |
| Oh My Pi | `debugging` → `debug_start` | ❌ Échec réel | `npm error could not determine executable to run` |
| KlaatCode | `refactoring` (forcé, sandbox) | ❌ Refusé | Garde-fou §11, aucun subprocess lancé |

## 18. Performances mesurées

| Métrique | Valeur | Source |
|---|---|---|
| Hermes-native, qwen3-coder:30b, réponse froide | 29 242 ms | mesure directe (`duration_ms` réel) |
| KlaatCode, subprocess (échec rapide) | ~860-890 ms | `client_stats.avg_duration_ms` |
| Oh My Pi, subprocess (échec rapide) | ~700-955 ms | `client_stats.avg_duration_ms` |
| Suite composition root (127-128 tests) | 80-145 s | variance liée à la charge machine, pas au code |
| Suite complète (`tests/` + `backend/tests/`) | **3677 passed, 3 skipped**, 2 échecs — en 12m25s | voir §19 |

## 19. Anomalies trouvées

| # | Sévérité | Anomalie | Statut |
|---|---|---|---|
| 1 | **Critique** | `CodeIntelligenceAgent`/`Router` jamais instanciés en production | ✅ Corrigé (§3) |
| 2 | **Critique** | Aucune route `/api/v1/code-intelligence` | ✅ Corrigé (§4) |
| 3 | **Majeure** | Traduction de vocabulaire de tâches absente entre la couche CI et KlaatCode/Oh My Pi (`omp code_review` envoyé tel quel) | ✅ Corrigé |
| 4 | **Majeure** | `success_rate` affiché sans conversion en pourcentage | ✅ Corrigé |
| 5 | **Majeure** | « MCP bound » toujours faux (mauvais adaptateur lié / champ inexistant) | ✅ Corrigé |
| 6 | **Majeure** | Détection d'installation acceptait la présence de `npx`/`bunx` comme preuve | ✅ Corrigé |
| 7 | **Majeure** | Sondage de santé répété à chaque appel sans cooldown (amplifie #6) | ✅ Corrigé |
| 8 | **Critique** | `ToolPolicy`/`ToolSandbox` n'appliquent réellement rien à une écriture | ✅ Garde-fou ajouté côté Code Intelligence (§11) — la plateforme Tools/MCP elle-même reste non corrigée (hors périmètre) |
| 9 | **Critique** | `ci.task.started` jamais publié malgré sa déclaration | ✅ Corrigé |
| 10 | **Majeure** | Intégration CLI KlaatCode contre une interface qui n'existe pas | ❌ Non corrigé — hors périmètre « raccordement seul » |
| 11 | **Majeure** | Paquet `omp` sans exécutable résoluble via npx | ❌ Non corrigé — hors périmètre « raccordement seul » |

## 20. Corrections apportées (résumé)

Composition root (Phase 1) · Surface API 8 endpoints (Phase 2) · Routage 3 voies (Phase 3) · Traduction de vocabulaire de tâches (Phase 4) · États MCP réels (Phase 5) · Détection d'installation réelle + cooldown (Phase 6) · Bug d'affichage du pourcentage (Phase 7) · Center reconstruit (Phase 8) · Garde-fou d'écriture (Phase 9) · Documentation de l'orphelin Runtime Scorer (Phase 10) · Publication d'événement manquante (Phase 11) · Deux tests corrigés pour refléter le comportement honnête au lieu du succès fabriqué par un stub (`test_execute_with_force_provider`, `test_code_agent_selects_provider`).

## 21. Limitations connues et conditions du GO

1. **KlaatCode** ne peut aboutir sur aucune opération réelle testée — son intégration CLI doit être réécrite contre la vraie interface (`run <prompt>`, événements JSON), hors périmètre de cette passe.
2. **Oh My Pi** ne peut aboutir sur aucune opération réelle testée — le paquet `omp` doit être diagnostiqué/reconfiguré (nom de paquet, version, ou mécanisme d'exécution alternatif à `npx`).
3. **`ToolPolicy`/`ToolSandbox`** restent un no-op pour toute la plateforme Tools/MCP au-delà de Code Intelligence — le garde-fou ajouté ici est un correctif local, pas une correction de la plateforme.
4. **Aucun flux d'approbation de sandbox réel** n'existe encore (Workspace → Sandbox → Diff → Approval → Apply, tel que décrit dans la demande) — le garde-fou actuel refuse catégoriquement plutôt que d'orchestrer ce flux, qui reste à construire si des écritures réelles sont un jour nécessaires.

**Verdict** : le raccordement demandé par R-006 est réel, testé, et vérifié en conditions locales. Les deux limitations externes (KlaatCode, Oh My Pi) et le garde-fou de sécurité local justifient un **GO AVEC CONDITIONS** plutôt qu'un GO sans réserve — aucune n'invalide le travail de raccordement lui-même, qui est la portée exacte de cette passe.
