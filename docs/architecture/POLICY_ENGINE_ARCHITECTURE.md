# Human Approval & Policy Engine Architecture (HOS-046)

## Overview

The Policy Engine is the central governance authority for Hermes OS. All sensitive operations must pass through it. It evaluates rules, manages human approval workflows, and maintains a complete audit trail.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        PolicyEngine                               │
│                                                                  │
│  evaluate(operation, agent, risk, context) → ALLOW/DENY/REVIEW   │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │  RuleEvaluator   │  │  ApprovalEngine  │  │  AuditLog    │   │
│  │ (10 built-in     │  │ (approve/reject/ │  │ (immutable,  │   │
│  │  rules, custom)  │  │  delegate/cancel,│  │  10000 max,  │   │
│  │                  │  │  multi-approval) │  │  auto-prune) │   │
│  └────────┬─────────┘  └────────┬─────────┘  └──────┬───────┘   │
│           │                     │                   │           │
│  ┌────────┴─────────────────────┴───────────────────┴───────┐   │
│  │                 ApprovalQueue                            │   │
│  │  Priority-sorted: CRITICAL > HIGH > NORMAL > LOW         │   │
│  │  Auto-expiry, status management, thread-safe             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  EventBus → policy.{allowed,denied} + approval.{requested,      │
│             granted,rejected,expired} + audit.created            │
└──────────────────────────────────────────────────────────────────┘
```

## Components

### RuleEvaluator
10 built-in rules covering all sensitive operations:

| Rule | Operation | Decision | Priority |
|---|---|---|---|
| system_modification_denied | system_modification | DENY | 25 |
| critical_risk_denied | risk_level >= 9 | DENY | 25 |
| git_merge_requires_review | git_merge | REVIEW_REQUIRED | 10 |
| workspace_delete_requires | workspace_delete | REVIEW_REQUIRED | 10 |
| cloud_runtime_requires_review | runtime_cloud | REVIEW_REQUIRED | 10 |
| git_rollback_requires_approval | git_rollback | REVIEW_REQUIRED | 10 |
| high_risk_requires_review | risk_level >= 7 | REVIEW_REQUIRED | 15 |
| external_tool_requires_review | external_tool | REVIEW_REQUIRED | 8 |
| model_download_allowed | model_download | ALLOW | 5 |
| internet_access_allowed | internet_access | ALLOW | 1 |

Custom rules via `register()` — priority-based evaluation, DENY > REVIEW > ALLOW.

### ApprovalEngine
- **approve(approval_id, approver_id, comment)** — adds approver, checks multi-approval threshold
- **reject(approval_id, rejecter_id, comment)** — immediate rejection
- **delegate(approval_id, from_id, to_id)** — transfer ownership
- **cancel(approval_id)** — cancel request
- **check_expired()** — auto-expire stale requests

### ApprovalQueue
- Priority-sorted: CRITICAL (3) > HIGH (2) > NORMAL (1) > LOW (0)
- Auto-expiry based on timeout_seconds
- Status management with indexes

### AuditLog
- Immutable journal: who, what, when, why, result, duration
- Max 10000 entries, auto-prune oldest
- Queryable by agent, mission, operation, action

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | /policy/rules | List all rules |
| POST | /policy/evaluate | Evaluate operation |
| GET | /approval | Pending approvals |
| POST | /approval/{id}/approve | Approve |
| POST | /approval/{id}/reject | Reject |
| GET | /audit?agent_id=&mission_id=&operation= | Audit log |

## Events

| Event | Trigger |
|---|---|
| policy.allowed | Operation allowed |
| policy.denied | Operation denied |
| approval.requested | New approval created |
| approval.granted | Approval request granted |
| approval.rejected | Approval request rejected |
| approval.expired | Request timed out |
| audit.created | Audit entry recorded |

## Example: Mission with Human Approval Before Git Merge

```
1. CoderAgent initiates merge:
   PolicyEngine.evaluate(operation="git_merge", agent="coder", risk=3.0)
     → Rule: "git_merge_requires_review" matches
     → Decision: REVIEW_REQUIRED
     → Auto-creates ApprovalRequest with approval_id="abc123"

2. Approval Queue:
   [PENDING] abc123 | priority=HIGH | operation=git_merge | agent=coder

3. Human Admin reviews and approves:
   POST /approval/abc123/approve {approver_id: "admin", comment: "LGTM"}
     → Status: APPROVED
     → Audit: [admin, approved, git_merge, "LGTM"]

4. CoderAgent can now proceed with merge ✅
```

## Integration Points

- **Workspace Manager (HOS-045)**: consults policy before git_merge, workspace_delete
- **Agent Supervisor (HOS-043)**: consults policy before delegation, sensitive ops
- **Runtime (HOS-034-040)**: consults policy before model_download, cloud access
- **Event Bus (HOS-034)**: publishes all governance events

## Validation

- pytest: 45/45 passed
- Thread safety: concurrent evaluations (20 threads), approvals (10 threads), audits (15 threads)
- 1073+ total architecture tests (HOS-000 through HOS-046)
