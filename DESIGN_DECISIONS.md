# Design Decisions — Hermes OS

> **Pourquoi chaque choix architectural a été fait, quelles alternatives ont été considérées, et quelles sont les limites assumées.**

---

## 1. Runtime Abstraction Layer (Protocol plutôt que classe abstraite)

**Problème :** Comment définir un contrat runtime sans coupler les implémentations à une classe de base ? Les runtimes concrets (Ollama, OpenAI, Anthropic) ont des API très différentes.

**Alternatives :**
1. `ABC` + `abstractmethod` — couplage fort à la hiérarchie de classes
2. `Protocol` (PEP 544) — duck typing structurel
3. Interface en JSON Schema — validation runtime uniquement

**Solution retenue :** `Protocol`. Un runtime est tout objet qui expose `name`, `version`, `status`, `capabilities`, `start()`, `stop()`, `get()`. Aucune importation de classe de base n'est nécessaire.

**Avantages :** Les runtimes concrets n'ont pas besoin d'hériter d'une classe Hermes OS. Un wrapper de 5 lignes autour d'une API OpenAI existante devient immédiatement un runtime valide.

**Limites :** `Protocol` ne force pas l'implémentation à la définition (seulement à l'utilisation). Détecté par les tests.

---

## 2. Thread Safety avec RLock

**Problème :** Tous les modules centraux (Registry, Event Bus, Memory, Supervisor, Engine) doivent être thread-safe.

**Solution :** `threading.RLock` (reentrant lock) systématiquement. Permet à une méthode d'appeler une autre méthode du même objet sans deadlock.

**Alternatives :**
- `threading.Lock` — deadlock si récursion involontaire
- `asyncio.Lock` — ne protège pas les threads
- Aucun lock — crashes sous charge concurrente

---

## 3. Event Bus Central vs. Événements Distribués

**Problème :** Comment connecter les sous-systèmes (runtime, agents, mémoire, skills, exécution) sans couplage direct ?

**Solution :** Bus d'événements central :

1. **HOS-013** : `RuntimeEventBus` — événements runtime uniquement
2. **HOS-025** : `SystemEventBus` — bus unifié pour tous les sous-systèmes

Chaque bus est :
- Thread-safe
- En mémoire (historique configurable)
- Pub/sub avec filtrage optionnel
- Sans dépendance externe

**Alternatives rejetées :**
- Redis Streams — dépendance externe, complexité inutile pour la v1
- Kafka — surdimensionné pour un système mono-utilisateur
- Callbacks directs — couplage fort, pas d'historique

---

## 4. UnifiedMemory avec Backend Abstrait

**Problème :** Comment stocker la mémoire sans s'enchaîner à une technologie spécifique ?

**Solution :** `MemoryBackend` abstrait avec `InMemoryBackend` par défaut. La même API fonctionne avec SQLite, ChromaDB, PostgreSQL, Alexandrie — la commutation se fait par injection.

**Alternatives :**
- SQLite directement — simple mais pas extensible
- ChromaDB directement — conçu pour le vectoriel, pas le généraliste
- Redis — dépendance externe

---

## 5. AdaptiveSkillOrchestrator plutôt que chargement systématique

**Problème :** Charger toutes les skills (SKILL.md) à chaque mission est coûteux en tokens et en temps.

**Solution :** Orchestrateur adaptatif qui sélectionne dynamiquement les skills par :
- Correspondance de capacités (`capabilities`)
- Mots-clés de mission
- Limites configurables (`max_skills=10`, `max_tokens=50000`)
- 4 stratégies : `MINIMAL`, `BALANCED`, `EXHAUSTIVE`, `PERFORMANCE`

---

## 6. DAG d'exécution (ExecutionGraph) plutôt que pipeline linéaire

**Problème :** Les missions complexes ont des dépendances non linéaires. Un pipeline linéaire ne peut pas exprimer le parallélisme.

**Solution :** DAG (Directed Acyclic Graph) avec :
- Détection de cycles (Kahn)
- Tri topologique
- Niveaux de parallélisme
- Validation structurelle complète

---

## 7. Machine à états plutôt que booléens

**Problème :** Le cycle de vie d'un agent a 10 états avec des transitions complexes. Des booléens (`is_running`, `is_paused`) ne peuvent pas exprimer toute la grammaire.

**Solution :** Machine à états formelle (`AgentState`) avec transitions validées :

```python
ALLOWED_TRANSITIONS = {
    AgentState.CREATED: {AgentState.READY},
    AgentState.READY: {AgentState.SCHEDULED, AgentState.RUNNING},
    AgentState.RUNNING: {AgentState.PAUSED, AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED, AgentState.TIMEOUT},
    ...
}
```

Toute transition invalide lève `AgentLifecycleError`.

---

## 8. RuntimeDecisionEngine composite

**Problème :** Quel runtime choisir quand plusieurs sont disponibles ? Le choix dépend de multiples facteurs.

**Solution :** Score composite (0-1000) :
- Health (0-200)
- Reliability (0-250)
- Performance (0-200)
- Capability (0-150)
- Policy (0-100)
- Circuit penalty (0-100)

Pondéré, explicable, extensible.

---

## 9. HermesAgentAdapter encapsulé

**Problème :** Hermes Agent (NousResearch) a ses propres concepts (BaseAgent, ModelRouter, EchoAgent). Comment les intégrer sans contaminer l'architecture Hermes OS ?

**Solution :** Adapter pur — encapsule toute dépendance à Hermes Agent dans un seul module. Le reste du système ne connaît que l'interface publique de l'adapter.

---

## 10. MissionControlService comme unique point d'entrée

**Problème :** 9 sous-systèmes, chacun avec sa propre API. Le frontend et les intégrations ne peuvent pas tous les connaître.

**Solution :** Façade unique `MissionControlService` qui agrège :
- Missions → MultiAgentSupervisor
- Runtimes → RuntimeRegistry + RuntimeDecisionEngine
- Exécution → ExecutionEngine
- Mémoire → UnifiedMemory
- Skills → AdaptiveSkillOrchestrator
- Événements → SystemEventBus
- Intégrations → HermesAgentAdapter
- Système → Tous les sous-systèmes combinés

L'API REST (HOS-028) est une couche de validation/délégation au-dessus de cette façade. Aucune logique métier n'y réside.

---

## 11. Absence de singletons (sauf legacy SDS)

**Problème :** Les singletons compliquent les tests et le remplacement des implémentations.

**Solution :** Injection de dépendances systématique. `RuntimeRegistry`, `EventBus`, `UnifiedMemory` — tout est injecté. La seule exception est le `RuntimeHolder` legacy SDS, conservé pour la compatibilité mais isolé derrière `ActiveRuntimeContext`.

---

## 12. Tests sans réseau

**Problème :** Comment tester un système conçu pour fonctionner avec des API LLM externes sans dépendre de ces API ?

**Solution :** Fake clients (`FakeOllamaClient`, `StubRuntime`, `InMemoryBackend`) qui implémentent les mêmes Protocols. Les tests unitaires et d'architecture sont **tous** sans réseau. Les tests d'intégration réels sont optionnels et marqués explicitement.
