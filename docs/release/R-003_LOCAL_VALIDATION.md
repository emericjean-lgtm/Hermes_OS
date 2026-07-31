# R-003 — Validation locale Hermes OS (RX 6800)

**Date** : 30 juillet 2026
**Nature** : audit de validation pré-production sur la machine réelle
**Règle appliquée** : aucune affirmation sans exécution réelle. Tout ce qui n'a pas
été exécuté est marqué comme tel, jamais présenté comme validé.

> **État : validation en cours.** Ce document consigne ce qui a été *réellement
> mesuré*. Les phases non terminées sont listées telles quelles à la fin, sans
> résultat inventé pour les combler.

---

## 1. Configuration matérielle et logicielle détectée

Relevé par exécution réelle (`Get-CimInstance`, registre, `--version`), pas déclaré.

| Élément | Valeur mesurée |
|---|---|
| OS | Microsoft Windows 11 Professionnel 10.0.26100 (build 26100) |
| CPU | 13th Gen Intel Core i5-13500 — 14 cœurs / 20 threads |
| RAM | 31,8 Go (34 107 604 992 octets) |
| GPU | **AMD Radeon RX 6800**, pilote 32.0.21043.19003, statut OK |
| VRAM | **15,98 Gio** (`HardwareInformation.qwMemorySize` = 17 163 091 968 octets) |
| WSL | WSL2, Ubuntu-24.04 (arrêté), docker-desktop (arrêté) |
| Ollama | 0.32.3, joignable sur `http://127.0.0.1:11434` |
| Python | 3.11.15 |
| Node / npm | v26.3.0 / 11.16.0 |
| Docker | 29.6.1 |
| ROCm | **`rocm-smi` absent** du PATH Windows et de WSL (`which rocm-smi` → rien) |

**Note sur la VRAM** : `Win32_VideoController.AdapterRAM` rapporte 4 293 918 720
octets (4 Gio) — c'est le plafond 32 bits classique de WMI, faux pour une carte de
16 Gio. La valeur réelle vient du registre. Le code de Hermes utilise désormais
cette source.

**Note sur ROCm** : `rocm-smi` n'étant disponible ni côté Windows ni dans WSL, la
télémétrie GPU ne peut pas venir de là. Elle est dérivée de deux sources
réellement mesurées : la capacité par le registre, l'occupation par
`/api/ps` d'Ollama (`size_vram`).

---

## 2. Anomalies trouvées et corrigées

Toutes ont été constatées par exécution, pas par lecture de code.

### R-003-01 — **Critique** : Hermes ne voyait aucun GPU

`GET /api/v1/runtime/resources` renvoyait `available: false`,
`vram_total_bytes: 0`, `name: "unknown"` — pendant qu'`ollama ps` montrait un
modèle résident à **100 % GPU** sur la RX 6800.

*Cause* : `ResourceManager.__init__` retombe sur `NoopGPUMonitor()` — le bouchon
de CI qui répond toujours `available=False` — et rien ne lui passait jamais de
vrai moniteur. Le `GPUMonitor` réel existait et fonctionnait.

*Correctif* : le composition root injecte `GPUMonitor()`. La valeur par défaut du
constructeur est laissée telle quelle pour que la suite unitaire reste hermétique.

*Vérification* :
```
AMD Radeon RX 6800 | available=True | total 15.98 GiB | used 308 MiB | free 15.68 GiB
```

### R-003-02 — **Majeure** : capacité VRAM inventée

`_try_ollama_ps()` renvoyait `vram_total_bytes = 16 * 1024**3  # Assume 16 GB` et
`vram_used_bytes = 0`. Une capacité supposée et une occupation jamais mesurée.

*Correctif* : capacité lue dans le registre du pilote, occupation sommée depuis
`size_vram` de `/api/ps`. Les deux nombres proviennent maintenant de quelque chose
qui les a mesurés.

### R-003-03 — **Critique** : le Cockpit ne pouvait pas joindre le backend

Deux défauts cumulés, tous deux livrés dans le dépôt :

1. `frontend/.env.local.example` livre `NEXT_PUBLIC_API_URL=http://localhost:8000`
   alors que `client.ts` fait `fetchJSON("/agents")` sur cette base — la valeur
   **doit** se terminer par `/api/v1`. En suivant la procédure documentée, chaque
   appel partait sur `/agents` au lieu de `/api/v1/agents`.
2. CORS codé en dur sur `http://localhost:3000` uniquement. Dès que le port 3000
   est pris — ce qui était le cas ici — chaque requête échouait en préflight :
   `OPTIONS http://localhost:8010/agents → 400 Bad Request`.

*Correctif* : l'exemple d'environnement inclut le préfixe et l'explique ; les
origines CORS viennent de `HERMES_CORS_ORIGINS` (défaut : ports 3000 et 3010, en
`localhost` et `127.0.0.1`).

### R-003-04 — **Critique** : le tableau de bord plantait

Une fois la connectivité rétablie, le Dashboard tombait en page blanche :
`TypeError: missions.filter is not a function`.

*Cause* : famille de dérives de contrat. Onze méthodes client déclaraient
`X[]` alors que les endpoints renvoient une enveloppe :

| Client | Endpoint | Renvoie réellement |
|---|---|---|
| `missions.list` | `/missions` | `{missions, total}` |
| `agents.list` | `/agents` | `{agents, total}` |
| `runtime.list` | `/runtimes` | `{runtimes, active, fallback}` |
| `skills.list` | `/skills` | `{skills, count, stats}` |
| `tools.list` | `/tools` | `{tools, count, stats}` |
| `governance.approvals` | `/approval` | `{approvals, total}` |
| `governance.rules` | `/policy/rules` | `{rules}` |
| `tools.mcpServers` | `/mcp/servers` | `{servers, count}` |
| `memory.experiences` | `/memory/experiences` | `{recommendations}` |
| `memory.searchAdvanced` | `/memory/search` | `{results, total}` |
| `skills.select` | `/skills/select` | `{selections, count}` |

Rien ne l'avait détecté **parce que le Cockpit n'avait jamais réussi à joindre le
backend** (R-003-03) : les appels échouaient, `data` restait `undefined` et les
gardes `?.` tenaient. La connectivité rétablie, la vraie forme casse le rendu.

*Correctif* : un helper `unwrap<T>(payload, key)` côté client, tolérant aussi un
tableau nu pour qu'un endpoint déjà déballé continue de fonctionner.

### R-003-05 — **Majeure** : `/tools/health` n'est pas une liste

L'endpoint renvoie un **agrégat** `{total, healthy, degraded_or_unhealthy,
avg_latency_ms}`. Le client le typait `ToolHealth[]` et `tools-center.tsx`
appelait `.slice(0,8).map(...)` dessus — ce qui lève sur un objet.

*Correctif* : type `ToolHealthSummary`, et le Centre affiche les totaux de flotte
en précisant que la santé par outil n'est pas exposée.

### R-003-06 — **Majeure** : WebSocket jamais connecté

Le Cockpit affichait `WS OFF` / `Disconnected` en permanence.

*Cause* : trois hooks interprètent `NEXT_PUBLIC_WS_URL` différemment.
`use-events.ts` et `lib/events.ts` la traitent comme une **origine** et ajoutent
le chemin ; `use-websocket.ts` — celui qu'utilise le Dashboard — la traitait comme
une **URL complète**, avec pour défaut un chemin `/ws/events` que le backend ne
sert pas.

*Correctif* : `use-websocket.ts` traite la variable comme une origine et ajoute
`/ws`, comme les deux autres.

*Vérification* : `WS LIVE` / `Streaming`, avec des événements réels qui arrivent :
```
system.metrics {"gpu":{"vram_used_gb":12.7,"vram_total_gb":17.16,...}}
```
Chaîne complète vérifiée : matériel → backend → WebSocket → Cockpit.

### R-003-07 — **Mineure** : `Uptime NaNs`

`dashboard-view.tsx` et `topbar.tsx` lisaient `health.uptime_s` ; `/api/v1/health`
renvoie `uptime_seconds`. Le type `SystemHealth` déclarait le mauvais nom, donc
`tsc` ne pouvait rien voir. Corrigé — affiche désormais `7m 41s`.

---

## 3. Anomalies constatées, non corrigées

| ID | Sévérité | Constat |
|---|---|---|
| R-003-08 | **Majeure** | **FreeBuff n'est pas intégré.** Deux modules existent (`adapter.py`, `__init__.py`), **aucune référence dans le composition root**, **aucune route** parmi les 245 chemins exposés, et `submit_prompt(simulate=True)` **par défaut** renvoie `f"Simulated Freebuff response for: ..."`. La ligne 289 dit elle-même « In a real scenario: validate API key, ping health endpoint ». Il n'y a rien à valider : la Phase 7 le concernant ne peut pas être satisfaite sans développement. |
| R-003-09 | **Mineure** | Les endpoints `/git/*` renvoient **403** même pour le dépôt courant : `'C:/Users/emeri/Hermes_OS-main' is outside ALLOWED_PATHS — a hard boundary`. Le bac à sable fonctionne (c'est une preuve pour la Phase 10) mais la configuration par défaut rend ces routes inutilisables. |
| R-003-10 | **Mineure** | Avertissement React `Each child in a list should have a unique "key" prop` dans `DashboardView`. |
| R-003-11 | **Mineure** | Un autre Hermes tourne sur le port 8000 depuis `C:\Users\emeri\hermes-ollama` (démarré le 26/07). Il ne répond pas sur `/api/v1/health`. Non touché ; cette validation utilise le port 8010. |

---

## 4. Phases réalisées

### Phase 1 — Démarrage ✅
Backend et Cockpit démarrés réellement. Assemblage vérifié :
```
34/34 sous-systèmes, 30 routeurs, 279 endpoints, 0 échec
cycles=[] dépendances manquantes={} services isolés=[]
registres: agents=10 outils=16 serveurs MCP=2 runtimes=1 compétences=0
```

### Phase 3 — Endpoints ✅
`scripts/validation/sweep_endpoints.py` sur l'application réelle :

| Résultat | Nombre |
|---|---|
| Couples méthode+chemin | **276** |
| `GET` → 200 | **103** |
| `POST` → 200 | 6 |
| Nécessitent un paramètre de chemin | 84 |
| Verbe mutant sans charge utile sûre | 61 |
| Ignorés (déclencheraient une inférence) | 11 |
| **WebSocket `/ws`** | **connecté, trame envoyée** |

Les 10 premiers « échecs » 422 étaient des **erreurs de ma sonde** (mauvais noms de
paramètres : `repo_path` et non `path`, `query` et non `q`). Reprises avec les bons
paramètres : toutes répondent 200. **Aucun endpoint réellement défaillant.**

### Phases 5-6 — Benchmarks par modèle 🔄 *en cours*

`scripts/validation/bench_models.py` applique strictement la discipline demandée :
GPU vérifié vide → chargement d'**un seul** modèle → attente de résidence réelle →
benchmarks → déchargement → **vérification que la VRAM est revenue** → modèle
suivant. Résultats écrits après chaque modèle : une interruption laisse des
mesures réelles, pas rien.

Toutes les métriques viennent des compteurs d'Ollama lui-même
(`load_duration`, `prompt_eval_duration`, `eval_duration`, `eval_count`) et de
`size_vram`. **Aucune n'est estimée.**

Résultats mesurés à ce stade (11 modèles sur 16) — extrait :

| Modèle | Taille | VRAM chargée | Chargement | TPS moyen | Processeur | VRAM rendue |
|---|---|---|---|---|---|---|
| qwen3:1.7b | 1,3 Go | 1,58 Gio | 3,6 s | ~221 | 100 % GPU | ✅ 0 Mio |
| qwen3:4b | 2,3 Go | 2,96 Gio | 5,1 s | ~123 | 100 % GPU | ✅ 0 Mio |
| hermes3-feedmail:64k | 4,3 Go | **12,03 Gio** | 9,5 s | ~88 | 100 % GPU | ✅ 0 Mio |
| deepseek-r1:14b | 8,4 Go | 8,81 Gio | 15,9 s | ~47 | 100 % GPU | ✅ 0 Mio |
| Hermes-4-14B Q4_K_M | 8,4 Go | 8,72 Gio | 13,2 s | ~49 | 100 % GPU | ✅ 0 Mio |
| phi4-reasoning:14b | 10,4 Go | 10,99 Gio | 15,7 s | ~39 | 100 % GPU | ✅ 0 Mio |

**Deux observations importantes :**

1. **`hermes3-feedmail:64k` occupe 12,03 Gio de VRAM pour 4,3 Go sur disque** — sa
   fenêtre de 64k contextes coûte près de 8 Gio de cache. Sur une carte de 16 Gio,
   c'est le modèle le plus contraignant du parc alors qu'il est parmi les plus
   petits.
2. **Le benchmark `long_context` échoue sur tous les modèles testés** (`quality=n`)
   : aucun ne restitue le nombre caché dans ~1500 mots de remplissage. À
   qualifier avant conclusion — la fenêtre de contexte par défaut d'Ollama (4096)
   peut tronquer le début du prompt, là où le nombre est placé. **Ne pas conclure
   à une défaillance des modèles sans avoir refait la mesure avec `num_ctx`
   explicite.**

Trois modèles dépassent la VRAM et déborderont sur le CPU — `qwen3-coder:30b`
(18 Go), `deepseek-r1:32b` (19 Go), `feedmail-coder:latest` (19 Go). Leurs
résultats seront marqués comme tels.

### Phase 13 — Cockpit ✅ (partiel)
Le Dashboard affiche désormais des données réelles vérifiées contre le backend :
santé `ok`, uptime réel, **1 runtime (`stub`, `started`)**, et les **10 agents
réels** déclarés dans `config/agents.yaml` (aegis, atlas, echo, hermes_eyes,
hermes_prime, hermes_scribe, hermes_swift, kronos, minerva, veritas). Flux
d'événements WebSocket actif avec télémétrie GPU réelle.

---

## 5. Ce qui n'a pas encore été exécuté

Listé sans résultat plutôt que rempli d'estimations :

| Phase | État |
|---|---|
| 2 / 13 — parcours exhaustif des ~20 Centers, chaque onglet et chaque bouton | Dashboard validé ; les autres Centers restent à parcourir un par un |
| 4 — KTransformers, llama.cpp, vLLM, Adaptive Router | **Non testés.** Seul `stub` est enregistré comme runtime actif ; l'inférence réelle passe par Ollama |
| 5-6 — 5 modèles restants + les axes runtime/CPU/GPU | En cours d'exécution |
| 7 — Alexandrie, KTransformers, KlaatCode, Oh My Pi | Non exercés bout en bout |
| 7 — **FreeBuff** | **Impossible** en l'état — voir R-003-08 |
| 8 — missions autonomes réelles bout en bout | Non exécutées dans cette session |
| 9 — multi-agent | Non exécuté |
| 10 — sécurité complète | Preuve partielle : le bac à sable refuse `/files` et `/git/*` hors `ALLOWED_PATHS` (403) |
| 11 — performances système | GPU/VRAM/RAM instrumentés ; CPU, SSD, IO, fuites non mesurés |
| 12 — Docker | Non exécuté (Docker 29.6.1 présent, `docker-desktop` WSL arrêté) |

---

## 6. Recommandations pour cette configuration (Windows 11 + RX 6800 16 Gio)

1. **Ne pas compter sur `rocm-smi`** : absent du PATH Windows et de WSL. La
   télémétrie doit passer par le registre (capacité) et `/api/ps` (occupation),
   ce que fait désormais le code.
2. **Surveiller les modèles à grande fenêtre**, pas seulement leur taille disque :
   `hermes3-feedmail:64k` fait 4,3 Go et consomme 12 Gio de VRAM.
3. **Trois modèles ne tiennent pas en VRAM** (18-19 Go pour 15,98 Gio
   disponibles). Ils fonctionneront avec débordement CPU, à un débit très
   inférieur : à réserver aux tâches non interactives.
4. **Le meilleur compromis mesuré** sur les modèles testés jusqu'ici se situe
   autour de 8-9 Gio de VRAM (deepseek-r1:14b, Hermes-4-14B) : ~47-50 tps en
   restant à 100 % GPU avec de la marge.
5. **Fixer `num_ctx` explicitement** avant de conclure quoi que ce soit sur le
   long contexte.

---

## Annexe — Reproduire

```bash
python scripts/validation/bench_models.py --out docs/release/bench_results.json
```

```bash
python scripts/validation/sweep_endpoints.py --out docs/release/endpoint_sweep.json
```

Backend et Cockpit (ports 8010/3010 pour ne pas heurter les services déjà en
place) :

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

```bash
npm --prefix frontend run dev -- --port 3010
```
