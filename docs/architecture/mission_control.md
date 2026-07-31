# Mission Control Dashboard — Hermes OS

> **HOS-029** — Interface utilisateur Next.js pour Hermes OS.
> Point d'entrée unique pour l'utilisateur, consomme exclusivement l'API HOS-028.

---

## Architecture

```mermaid
graph TB
    subgraph "Frontend Next.js (HOS-029)"
        UI[Dashboard Page]
        CHAT[Chat Page]
        PLACEHOLDER[Placeholder Pages]
    end

    subgraph "Components"
        LAYOUT[Layout: Sidebar + Topbar + StatusBar]
        DASH[HealthCard / StatisticsCard / RuntimeTable / MissionList / EventTimeline / HermesCard]
    end

    subgraph "State & Data"
        TANSTACK[TanStack Query Hooks]
        WS[WebSocket Hook]
        STORE[Dashboard Store]
        CLIENT[MissionControlClient]
    end

    subgraph "Backend API (HOS-028)"
        API[MissionControlRouter]
        WS_API[/ws/events WebSocket]
    end

    UI --> DASH
    DASH --> TANSTACK
    DASH --> WS
    TANSTACK --> CLIENT
    WS --> WS_API
    CLIENT --> API
    LAYOUT --> STORE
    LAYOUT --> TANSTACK
    LAYOUT --> WS
```

---

## Pages

| Route | Type | Description |
|---|---|---|
| `/` | Chat | Interface de chat Hermes (existante, inchangée) |
| `/dashboard` | Dashboard | Page principale avec tous les composants |
| `/missions` | Placeholder | Gestion des missions |
| `/agents` | Placeholder | Gestion des agents |
| `/runtimes` | Placeholder | Configuration des runtimes |
| `/memory` | Placeholder | Explorateur mémoire |
| `/skills` | Placeholder | Gestion des compétences |
| `/events` | Placeholder | Visualisation des événements |
| `/settings` | Placeholder | Configuration système |

---

## Composants Dashboard

### HealthCard
- État système global (HEALTHY/DEGRADED/UNHEALTHY)
- Version + Uptime
- Liste des sous-systèmes avec indicateurs
- États : chargement, erreur, vide

### StatisticsCard
- Missions (total, actives, complétées)
- Agents (total, en cours)
- Runtimes (total, healthy, degraded)
- Mémoire (entrées, scopes)
- Skills (enregistrés, chargés)
- Events (total)

### RuntimeTable
- Nom du runtime
- Statut (icône)
- Fiabilité (barre)
- Performance (barre)
- Taux de succès
- Nombre d'exécutions

### MissionList
- Titre + statut (icône couleur)
- Priorité, runtime, durée
- Barre de progression
- 10 missions maximum affichées

### EventTimeline
- Temps réel via WebSocket
- Filtres par sévérité (All/INFO/WARNING/ERROR/CRITICAL)
- Code couleur par sévérité
- Reconnexion automatique

### HermesCard
- Statut connexion
- Sessions actives
- Capacités (badges)

---

## Layout global

```
┌─────────────────────────────────────────────────────────┐
│  Topbar: Logo · Search · Health · Notifications         │
├──────────┬──────────────────────────────────────────────┤
│          │                                              │
│ Sidebar  │  Workspace (page content)                    │
│ (10 nav  │                                              │
│  items)  │                                              │
│          │                                              │
├──────────┴──────────────────────────────────────────────┤
│  StatusBar: Version · Health · Uptime · WS Connection   │
└─────────────────────────────────────────────────────────┘
```

---

## Intégrations

### TanStack Query (React Query)
- 17 hooks avec auto-refresh configurable
- Cache structuré par `queryKeys`
- Mutations avec invalidation automatique

### WebSocket
- Connexion automatique à `/api/hermes-os/ws/events`
- Reconnexion avec backoff exponentiel
- Heartbeat intégré
- Timeline temps réel des SystemEvents

---

## Types de données

Tous les types TypeScript (`src/types/mission-control.ts`) correspondent exactement aux modèles Pydantic de HOS-028 :

- `HealthResponse`, `StatusResponse`, `StatisticsResponse`
- `RuntimeInfo`, `RuntimeHealthInfo`, `RuntimeMetrics`
- `Mission`, `ExecutionStatus`
- `MemoryEntry`, `SkillInfo`, `SystemEvent`
- `HermesAgentStatus`

---

## Futures vues (préparées)

- **Mission Center** — création et suivi détaillé des missions
- **Chat** — interface de discussion avec les agents
- **Memory Explorer** — navigation et recherche mémoire
- **Skill Manager** — gestion des compétences chargées
- **Infrastructure** — monitoring des ressources système
- **Logs** — logs détaillés d'exécution
- **Settings** — configuration Hermes OS
