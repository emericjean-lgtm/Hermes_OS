# Multi-Agent Collaboration Architecture (HOS-044)

## Overview

The Multi-Agent Collaboration Engine enables agents to cooperate, share information, delegate tasks, request help, reach consensus, and resolve conflicts. It sits on top of the Agent Supervisor (HOS-043) and integrates with the Event Bus (HOS-034).

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     CollaborationEngine                           │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │  MessageBus  │  │ContextSharing│  │DelegationManager │       │
│  │  (direct,     │  │ (permission- │  │ (accept→start→  │       │
│  │   broadcast,  │  │  based,      │  │  complete,      │       │
│  │   group,      │  │  public/     │  │  expertise)     │       │
│  │   help req)   │  │  restricted) │  │                  │       │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘       │
│         │                 │                   │                  │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌────────┴─────────┐      │
│  │Conversations │  │  editable_by │  │ incoming/outgoing│      │
│  │ acknowledged │  │  visible_to  │  │ pending/unmatched│      │
│  │ read/unread  │  │  by_owner    │  │ by_mission       │      │
│  └──────────────┘  └──────────────┘  └──────────────────┘      │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ ConsensusEngine  │  │ ConflictResolver │                     │
│  │ (unanimous,      │  │ (5 types,        │                     │
│  │  majority,       │  │  auto-resolve,   │                     │
│  │  super-majority, │  │  escalate,       │                     │
│  │  single)         │  │  propose)        │                     │
│  └──────────────────┘  └──────────────────┘                     │
│                                                                  │
│  Reviews: request_review → submit_review (approved/rejected)    │
│                                                                  │
│  EventBus → collaboration.* + message.* + consensus.* + conflict.*│
└──────────────────────────────────────────────────────────────────┘
```

## Components

### MessageBus
- **Direct**: agent → agent private messages
- **Broadcast**: one → all agents
- **Group**: one → multiple agents (shared conversation_id)
- **Help Request**: specialized messages with required capabilities
- **Help Response**: reply to help requests, accept/reject
- **Conversations**: threaded messaging with conversation_id
- **Acknowledgments**: read/acknowledged status tracking

### ContextSharing
- Share context with fine-grained permissions: `visible_to`, `editable_by`
- Public contexts (empty permission lists = visible to all)
- Collaborative updates (if permitted)
- Query by owner, mission, or visible_to agent

### DelegationManager
- Delegate tasks: `from_agent → to_agent`
- Request expertise: unmatched delegations (to_agent="") for capability matching
- Workflow: REQUESTED → ACCEPTED → IN_PROGRESS → COMPLETED
- Support for rejection and failure states

### ConsensusEngine
- **Unanimous**: all voters must agree
- **Majority**: 50% + 1 wins
- **Super-majority**: 2/3 threshold
- **Single**: first vote decides
- Configurable minimum voters and timeouts

### ConflictResolver
- 5 conflict types: DISAGREEMENT, RESOURCE_CONFLICT, CONCURRENT_MODIFICATION, DECISION_INCOMPATIBLE, PRIORITY_CLASH
- Auto-resolution strategies per type:
  - Disagreement → majority proposal
  - Resource → first-come-first-served
  - Priority → priority ordering
  - Concurrent → accept first proposal
- Escalation when auto-resolution fails

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | /collaboration/messages?agent_id= | Inbox |
| POST | /collaboration/messages | Send direct message |
| POST | /collaboration/messages/broadcast | Broadcast |
| GET | /collaboration/messages/unread?agent_id= | Unread messages |
| GET | /collaboration/messages/conversation/{id} | Thread |
| POST | /collaboration/delegate | Delegate task |
| GET | /collaboration/delegations?agent_id=&pending= | List delegations |
| POST | /collaboration/delegations/{id}/accept | Accept |
| POST | /collaboration/delegations/{id}/complete | Complete |
| POST | /collaboration/review | Request review |
| POST | /collaboration/review/{id} | Submit review |
| POST | /collaboration/consensus | Propose consensus |
| POST | /collaboration/consensus/{id}/vote | Cast vote |
| GET | /collaboration/history?mission_id= | Full mission history |

## Events

| Event | Trigger |
|---|---|
| collaboration.started | Engine initialized |
| message.sent | Any message sent |
| message.received | Message acknowledged |
| task.delegated | Delegation created/completed |
| review.requested | Review requested |
| review.completed | Review submitted |
| consensus.started | Consensus proposal created |
| consensus.reached | Quorum met, winner determined |
| conflict.detected | Conflict registered |
| conflict.resolved | Conflict resolved |

## Integration Points

- **AgentSupervisor (HOS-043)**: agent registry for message routing and delegation
- **Mission Graph (HOS-041)**: mission/node context for all collaboration
- **Event Bus (HOS-034)**: publishes all collaboration lifecycle events

## Thread Safety

All components use `threading.RLock()` for reentrant thread safety, allowing methods to call other locked methods within the same component (critical for `stats()` → `get_active()` and `auto_resolve()` → `resolve()` patterns).

## Validation

- pytest: 64/64 passed
- Thread safety: concurrent messages (20 threads), context sharing (10 threads), delegations (15 threads)
- 980+ total architecture tests (HOS-000 through HOS-044)
