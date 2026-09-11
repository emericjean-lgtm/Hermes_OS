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

## 3. PolicyEngine (HOS-046) — **removed**, 2026-09-11 (G-38)

There used to be a third system here, `backend/policy/`. It is gone: 9 modules, its `ServiceSpec`, and its `/api/v1/policy/*` + `/approval/*` + `/audit` routes.

**This section previously said it had "genuine callers outside its own package — `runtime/recovery/recovery_engine.py`, `workspace/workspace_manager.py`, `ral/runtime_decision.py`". That was wrong, and it is the exact mistake this file exists to prevent.** None of the three ever imported `backend.policy`. They have their own engines, which happen to share the name: `RecoveryPolicyEngine` (`runtime/recovery/recovery_policy.py`), `WorkspacePolicyEngine` (`workspace/workspace_policy.py`), and the HOS-016 runtime-routing policy engine. Four distinct objects called "PolicyEngine"; a reader who trusted this file would have believed the removal broke three subsystems. It broke none — measured: 344 → 338 routes, nothing else lost.

What it actually was: ten hard-coded rules that **nothing evaluated** (`AutonomousGuard.set_policy_engine()` was never called), an in-memory approval queue with no producer, and an in-memory audit ring that never received an entry. Two of its ten rules **contradicted** the policy actually in force — `internet_access_allowed: allow` against Aegis's `network_call` (minimum autonomy "high"), and `system_modification_denied: deny` against `system_config` (which asks a human, not a refusal). Full diagnostic: CHANGELOG HOS-286.

**A real documented gap that survives it**: `ToolPolicy.evaluate()`'s WRITE branch is a literal no-op (`# Policy engine would check sandbox readonly status` → `pass`). `ToolPolicy` is a *fourth* unrelated thing, in the connector adapters — no code path enforces write-sandboxing platform-wide through it. Only Code Intelligence got a local patch (R-006).

## The net effect

If you're asking "is this action actually gated," trace whether it goes through **Aegis** — that's the one universal answer, and since G-38 it is the *only* one. SecurityEngine is a real, correctly-implemented system protecting one specific thing (agent trust scoring); wrong to assume it is a general-purpose gate the way Aegis is.

Aegis's policy lives in `config/security.yaml` (`action_categories`), read by `PermissionMatrix` and re-read by `AegisEngine` on **every** evaluation. The cockpit shows it under Governance → "Politique en vigueur", with each category's effect at the current autonomy level — computed by the backend from the same comparison the engine makes, never recomputed on screen.
