# Contributing — Hermes OS

> Guide de contribution pour les développeurs.

---

## 1. Structure du projet

```
backend/
├── api/               # HOS-028 — API REST + WebSocket
│   ├── router.py      # MissionControlRouter
│   ├── models.py      # Pydantic models
│   └── hos_routes.py  # Handlers FastAPI
├── agent/             # HOS-017 à HOS-024
│   ├── execution_graph.py   # DAG
│   ├── task_planner.py      # Planification
│   ├── lifecycle.py         # Machine à états agents
│   ├── supervisor.py        # Supervision multi-agents
│   └── execution_engine.py  # Moteur d'exécution
├── ral/               # HOS-004 à HOS-016
│   ├── runtime.py           # RuntimeInterface Protocol
│   ├── runtime_registry.py  # Registry
│   ├── runtime_selector.py  # Sélecteur
│   ├── runtime_decision.py  # Moteur de décision
│   ├── runtime_router.py    # Routeur
│   ├── runtime_health.py    # Health monitor
│   ├── runtime_recovery.py  # Circuit breaker
│   ├── runtime_performance.py # Analyseur de performance
│   └── runtime_policy.py    # Politiques
├── memory/            # HOS-021
├── skills/            # HOS-022
├── events/            # HOS-025
├── integrations/      # HOS-023
│   └── hermes_agent/  # Hermes Agent adapter
├── services/          # HOS-027
└── api/               # HOS-028
```

## 2. Conventions

### Code

- **Python 3.10+** — Utilisation de `from __future__ import annotations`
- **Type hints** — Toutes les fonctions sont typées
- **Protocols** pour les interfaces, pas d'ABC
- **Dataclasses frozen=True** pour les objets immutables
- **Threading.RLock** pour la thread safety
- **Pas de singletons** — injection de dépendances

### Tests

- **Tous les tests sans réseau** — fake clients, stubs, in-memory
- `tests/architecture/` — tests d'architecture pure
- `tests/integrations/` — tests d'intégration avec adapters optionnels
- `tests/api/` — tests API (FastAPI TestClient)

### Documentation

- Chaque HOS doit mettre à jour :
  - `README.md` si nécessaire
  - `CHANGELOG.md`
  - `ROADMAP.md`
  - Documentation `docs/` impactée

## 3. Workflow Git

```
1. Créer une branche : git checkout -b feat/hos-NNN-description
2. Implémenter le HOS
3. Écrire les tests
4. Vérifier : pytest tests/ && python3 -m compileall backend tests
5. Mettre à jour la documentation
6. Commiter : git add -A && git commit -m "feat: HOS-NNN — description"
7. Pusher : git push
```

## 4. Règles

1. **Ne pas casser les tests existants** — `pytest tests/` doit toujours passer
2. **Ne pas modifier les contrats** HOS-000 à HOS-{N-1}
3. **Toute nouvelle abstraction** doit avoir un test
4. **Toute façade** doit juste déléguer — pas de logique dupliquée
5. **Documentation obligatoire** — un HOS n'est pas fini sans `CHANGELOG.md` + `ROADMAP.md` à jour

## 5. Test d'un HOS

```bash
# Compilation
python3 -m compileall backend tests

# Tests d'architecture
pytest tests/architecture/ -v

# Tests d'intégration
pytest tests/integrations/ -v

# Tests API
pytest tests/api/ -v

# Tout
pytest tests/ -q --tb=short
```
