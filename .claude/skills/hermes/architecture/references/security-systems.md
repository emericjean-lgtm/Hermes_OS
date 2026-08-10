# The three governance layers — disambiguated

Hermes OS has three real, non-equivalent permission/policy systems. Confusing them — assuming any one enforces more than it actually does — is the single most likely security-review mistake in this codebase. This file exists to make the distinction impossible to miss.

## 1. Aegis — `backend/security/aegis_engine.py` + `permission_matrix.py`

**The real, universal, always-consulted gate.** Deterministic, config-driven from `config/security.yaml`:
- `autonomy_level`: `low` / `medium` / `high` (currently `medium`, deliberately raised from the shipped `low` — see the cahier des charges §17.5's four named levels: Faible/Moyen/Élevé/Critique).
- Per action-category config: `mutating`, `path_based`, `mandatory_validation`, `min_autonomy_for_auto_allow`.
- `AegisEngine.evaluate(ActionRequest) -> AegisDecision(verdict: ALLOW | DENY | REQUIRE_HUMAN_VALIDATION)`.
- Path-based categories are checked against `Settings.allowed_paths_list` (`ALLOWED_PATHS`) as a **hard boundary no autonomy level can override**; a `project_root`, when given, can only narrow access further, never widen it beyond the global whitelist.

`AegisAgent` (`agents/aegis.py`) wraps the engine, adds human-approval consumption (`security/approvals.py`, SQLite-backed, single-use per approval), and publishes every check to the World-A message bus.

**Real callers** (confirmed, not aspirational): `tools/file_tools.py` (every file write), `tools/git_tools.py`, `tools/verification.py`, `mcp_server.server.security_evaluate`, `mission/routes.py::_check_mission_security`, `autonomous/autonomous_guard.py::AegisSecurityAdapter`.

**If you're gating a new mutating action, this is the system to add a category to** — `config/security.yaml`'s `action_categories`, following the existing pattern (see e.g. the `web_search` category added in HOS-078 with its own reasoning comment for why its threshold sits below `cloud_inference`'s).

## 2. SecurityEngine — `backend/security/security_engine.py` (HOS-057)

A more elaborate, real, tested 5-stage pipeline: `PermissionManager` (explicit grant/revoke) → `AgentTrustEngine` (dynamic 0–100 trust score) → `ThreatDetector` → `IsolationManager`, combined in `check_access()`. DI-wired, real `/api/v1/security/*` routes.

**Not the mission/task dispatch gate.** `MissionExecutor`'s own constructor docstring states plainly: `security_engine.check_access()` is not used to gate real dispatch, because no default permissions/policies are configured anywhere — wiring it into mandatory dispatch today would silently block every real mission. This was a deliberate decision, not an oversight.

**What actually is wired**: only the `trust` sub-engine (`AgentTrustEngine`). `MissionExecutor._sync_agent_released()` calls `trust_engine.record_result()` after every task, and `agents/routes.py` surfaces real trust scores. The permission/threat/isolation pipeline is live and independently callable via its own routes, but plays no role in whether a mission or task is actually allowed to run.

## 3. PolicyEngine — `backend/policy/policy_engine.py` (HOS-046)

`RuleEvaluator` (real built-in rules — `git_merge_requires_review`, `workspace_delete_requires_approval`, `cloud_runtime_requires_review`, and others) + `ApprovalEngine` + `AuditLog` (immutable, capped). DI-wired, real `/api/v1/policy/*` + approval + audit routes.

**Has genuine callers outside its own package** — `runtime/recovery/recovery_engine.py`, `workspace/workspace_manager.py`, `ral/runtime_decision.py` — so it's not purely dormant. But `AutonomousGuard.set_policy_engine()` (the hook that would let it gate autonomous goals) is never called by the bootstrap — only `set_security_engine()` is — so PolicyEngine's own step of `AutonomousGuard.check_action()` never actually runs in production. It protects its own specific corners (workspace deletion, cloud-runtime escalation, recovery decisions), not a unified front door.

**Separately, a real documented gap**: `ToolPolicy.evaluate()`'s WRITE branch is a literal no-op (`# Policy engine would check sandbox readonly status` → `pass`) — no code path currently enforces write-sandboxing platform-wide through this engine. Only Code Intelligence got a local patch for this (R-006), not a platform-wide fix.

## The net effect

If you're asking "is this action actually gated," trace whether it goes through **Aegis** — that's the one universal answer. SecurityEngine and PolicyEngine are real, correctly-implemented systems protecting specific things (agent trust scoring; workspace/cloud/recovery policy rules respectively) — useful to know about, wrong to assume either is a general-purpose gate the way Aegis is.
