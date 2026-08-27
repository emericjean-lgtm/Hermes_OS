"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  studioClient,
  systemClient,
  missionsClient,
  agentsClient,
  collaborationClient,
  runtimeClient,
  memoryClient,
  skillsClient,
  toolsClient,
  governanceClient,
  executionClient,
  eventsClient,
  alexandrieClient,
  evolutionClient,
  securityClient,
  subsystemClient,
  klaatcodeClient,
  ohmypiClient,
  codeIntelligenceClient,
  type CodeIntelligenceTaskKind,
  type CodeIntelligenceTaskRequest,
  autonomousClient,
  modelIntelligenceClient,
  conversationClient,
  workspaceClient,
  verificationClient,
  monitoringClient,
  projectsClient,
  filesystemBrowseClient,
  gitClient,
} from "@/services/client";
import type { ToolHealthSummary } from "@/services/client";
import type {
  Mission,
  MissionReport,
  Agent,
  CollaborationMessage,
  Delegation,
  RuntimeInfo,
  MemoryEntry,
  SearchResult,
  Skill,
  SkillSelection,
  ToolDefinition,
  ToolExecution,
  PolicyRule,
  ApprovalRequest,
  AuditEntry,
  ExecutionSummary,
  ExecutionStatistics,
  SystemHealth,
  SystemStatistics,
  SystemEvent,
  KnowledgeGraph,
  Experience,
  ResourceStatus,
  MCPServer,
  ToolHealth,
  AlexandrieStatus,
  AlexandrieSearchResults,
  AlexandrieSyncResult,
} from "@/types/hermes";

// ── System ──────────────────────────────────────────
export function useSystemHealth() {
  return useQuery<SystemHealth>({ queryKey: ["system", "health"], queryFn: systemClient.health });
}
export function useSystemStatistics() {
  return useQuery<SystemStatistics>({ queryKey: ["system", "statistics"], queryFn: systemClient.statistics });
}
// The Assistant's model picker used to fetch this once in a bare useEffect
// with a swallowed catch: a single failed request (e.g. the backend still
// warming up) left the picker stuck on "Auto only" for the rest of the
// session, silently. react-query's default retry (providers.tsx) gives it
// two more attempts, and isError/refetch let the caller show and recover
// from a real, persistent failure instead of hiding it.
/** L'état du harnais, rafraîchi régulièrement : il change sans action de
 *  l'utilisateur — un backend qui redémarre, une session qui se ferme. */
export function useHarnais() {
  return useQuery({
    queryKey: ["system", "harnais"],
    queryFn: systemClient.harnais,
    refetchInterval: 15_000,
  });
}

export function useSystemModelRoles() {
  return useQuery({ queryKey: ["system", "models"], queryFn: systemClient.models });
}

// ── Missions ─────────────────────────────────────────
export function useMissions() {
  return useQuery<Mission[]>({ queryKey: ["missions"], queryFn: missionsClient.list });
}
export function useMission(id: string | null) {
  return useQuery<Mission | null>({
    queryKey: ["missions", id],
    queryFn: () => (id ? missionsClient.get(id) : null),
    enabled: !!id,
  });
}
export function useMissionGraph(id: string | null) {
  return useQuery({
    queryKey: ["missions", id, "graph"],
    queryFn: () => (id ? missionsClient.graph(id) : null),
    enabled: !!id,
  });
}
export function useCreateMission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: missionsClient.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["missions"] }),
  });
}
export function useMissionReport(id: string | undefined) {
  return useQuery<MissionReport | null>({
    queryKey: ["missions", id, "report"],
    queryFn: () => missionsClient.report(id as string),
    enabled: Boolean(id),
  });
}
export function useMissionAction(id: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["missions"] });
    qc.invalidateQueries({ queryKey: ["missions", id] });
  };
  return {
    start: useMutation({ mutationFn: () => missionsClient.start(id), onSuccess: invalidate }),
    pause: useMutation({ mutationFn: () => missionsClient.pause(id), onSuccess: invalidate }),
    resume: useMutation({ mutationFn: () => missionsClient.resume(id), onSuccess: invalidate }),
    cancel: useMutation({ mutationFn: () => missionsClient.cancel(id), onSuccess: invalidate }),
  };
}

// ── Agents ───────────────────────────────────────────
export function useAgents() {
  return useQuery<Agent[]>({
    queryKey: ["agents"],
    queryFn: agentsClient.list,
    // Real activity now changes agent status/load (HOS-070) — before this,
    // nothing ever updated it after the initial registration, so polling
    // would have been pointless.
    refetchInterval: 5_000,
  });
}
export function useAgent(id: string | null) {
  return useQuery<Agent | null>({
    queryKey: ["agents", id],
    queryFn: () => (id ? agentsClient.get(id) : null),
    enabled: !!id,
  });
}
export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: agentsClient.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

// ── Collaboration ────────────────────────────────────
export function useCollaborationMessages(mission_id?: string) {
  return useQuery<CollaborationMessage[]>({
    queryKey: ["collaboration", "messages", mission_id],
    queryFn: () => collaborationClient.messages(mission_id ? { mission_id } : undefined),
  });
}
export function useSendMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: collaborationClient.sendMessage,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["collaboration"] }),
  });
}

// ── Runtime ──────────────────────────────────────────
export function useRuntimes() {
  return useQuery<RuntimeInfo[]>({ queryKey: ["runtimes"], queryFn: runtimeClient.list });
}
export function useRuntimeHealth() {
  return useQuery({ queryKey: ["runtimes", "health"], queryFn: runtimeClient.health });
}
export function useResourceStatus() {
  return useQuery<ResourceStatus>({ queryKey: ["runtime", "resources"], queryFn: runtimeClient.resources });
}

/** Real, currently-resident models (HOS-072) — Ollama's own /api/ps,
 *  distinct from the (always-empty in practice, see backend module
 *  docstring) allocation bookkeeping. */
export function useLoadedModels() {
  return useQuery({
    queryKey: ["runtime", "loaded-models"],
    queryFn: runtimeClient.loadedModels,
    refetchInterval: 10_000,
  });
}

export function useUnloadModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: runtimeClient.unloadModel,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runtime", "loaded-models"] });
      qc.invalidateQueries({ queryKey: ["runtime", "resources"] });
    },
  });
}

// ── Memory ───────────────────────────────────────────
export function useMemorySearch(q: string, mode: "hybrid" | "graph" | "keyword" = "hybrid") {
  return useQuery<SearchResult[]>({
    queryKey: ["memory", "search", q, mode],
    queryFn: () => memoryClient.search(q, mode),
    enabled: q.length > 0,
  });
}
export function useKnowledgeGraph(node_id?: string) {
  return useQuery<KnowledgeGraph>({
    queryKey: ["memory", "graph", node_id],
    queryFn: () => memoryClient.graph(node_id, 3),
  });
}
export function useExperiences() {
  return useQuery<Experience[]>({ queryKey: ["memory", "experiences"], queryFn: memoryClient.experiences });
}
export function useMemoryStatistics() {
  return useQuery({ queryKey: ["memory", "statistics"], queryFn: memoryClient.statistics });
}

// ── Skills ───────────────────────────────────────────
export function useSelectSkills(taskDescription: string) {
  return useQuery<SkillSelection[]>({
    queryKey: ["skills", "select", taskDescription],
    queryFn: () => skillsClient.select({ task_description: taskDescription }),
    enabled: taskDescription.length > 3,
  });
}
export function useSkillCache() {
  return useQuery({ queryKey: ["skills", "cache"], queryFn: skillsClient.cache });
}

// ── Tools ────────────────────────────────────────────
export function useTools() {
  return useQuery<ToolDefinition[]>({ queryKey: ["tools"], queryFn: toolsClient.list });
}
/** Les outils que l'agent peut vraiment appeler (HOS-187).
 *
 *  `useTools` rend le registre declare, dont `POST /tools/execute` refuse
 *  chaque entree faute d'executeur. Celui-ci rend la surface MCP, qui est
 *  celle qu'une mission emprunte. */
export function useAgentTools() {
  return useQuery({ queryKey: ["tools", "agent"], queryFn: toolsClient.agent });
}

export function useToolsHealth() {
  // Aggregate, not a per-tool list — see ToolHealthSummary.
  return useQuery<ToolHealthSummary>({
    queryKey: ["tools", "health"],
    queryFn: toolsClient.health,
  });
}
export function useMCPServers() {
  return useQuery<MCPServer[]>({ queryKey: ["tools", "mcp"], queryFn: toolsClient.mcpServers });
}

// ── Governance ───────────────────────────────────────
export function usePolicyRules() {
  return useQuery<PolicyRule[]>({ queryKey: ["policy", "rules"], queryFn: governanceClient.rules });
}
export function useApprovals() {
  return useQuery<ApprovalRequest[]>({ queryKey: ["approvals"], queryFn: governanceClient.approvals });
}
export function useApproveAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, comment }: { id: string; comment?: string }) => governanceClient.approve(id, comment),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });
}
export function useRejectAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, comment }: { id: string; comment?: string }) => governanceClient.reject(id, comment),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });
}
export function useAuditLog(params?: Record<string, string>) {
  return useQuery<AuditEntry[]>({
    queryKey: ["audit", params],
    queryFn: () => governanceClient.audit(params),
  });
}

// ── Execution ────────────────────────────────────────
export function useExecutions() {
  return useQuery<ExecutionSummary[]>({
    queryKey: ["executions"],
    queryFn: executionClient.list,
    // Real activity now arrives here as Missions run (HOS-069) — poll while
    // any task is genuinely in flight, matching the pattern already used
    // for Autonomous/Mission timelines.
    refetchInterval: 5_000,
  });
}
export function useExecution(id: string | null) {
  return useQuery<ExecutionSummary | null>({
    queryKey: ["executions", id],
    queryFn: () => (id ? executionClient.get(id) : null),
    enabled: !!id,
  });
}
export function useStartExecution() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: executionClient.start,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["executions"] }),
  });
}
export function useExecutionAction(id: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["executions"] });
    qc.invalidateQueries({ queryKey: ["executions", id] });
  };
  return {
    pause: useMutation({ mutationFn: () => executionClient.pause(id), onSuccess: invalidate }),
    resume: useMutation({ mutationFn: () => executionClient.resume(id), onSuccess: invalidate }),
    cancel: useMutation({ mutationFn: () => executionClient.cancel(id), onSuccess: invalidate }),
  };
}

// ── Events ───────────────────────────────────────────

// ── Alexandrie ───────────────────────────────────────
export function useAlexandrieStatus() {
  return useQuery<AlexandrieStatus>({ queryKey: ["alexandrie", "status"], queryFn: alexandrieClient.status, refetchInterval: 15000 });
}
export function useAlexandrieHealth() {
  return useQuery({ queryKey: ["alexandrie", "health"], queryFn: alexandrieClient.health, refetchInterval: 30000 });
}
export function useAlexandrieSearch(q: string, mode: "hybrid" | "fulltext" | "semantic" = "hybrid") {
  return useQuery<AlexandrieSearchResults>({
    queryKey: ["alexandrie", "search", q, mode],
    queryFn: () => alexandrieClient.search(q, mode),
    enabled: q.length > 1,
  });
}
export function useAlexandrieSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data?: { user_id?: string; incremental?: boolean }) => alexandrieClient.sync(data || {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alexandrie"] });
      qc.invalidateQueries({ queryKey: ["memory"] });
    },
  });
}
export function useAlexandrieSyncHistory() {
  return useQuery({ queryKey: ["alexandrie", "sync", "history"], queryFn: () => alexandrieClient.syncHistory() });
}
export function useAlexandrieDocuments() {
  return useQuery({ queryKey: ["alexandrie", "documents"], queryFn: () => alexandrieClient.documents() });
}
export function useAlexandrieGraph(node_id?: string) {
  return useQuery({
    queryKey: ["alexandrie", "graph", node_id],
    queryFn: () => alexandrieClient.graph(node_id),
    enabled: true,
  });
}

// ── Evolution (R-001) ───────────────────────────────────────────────

export function useEvolutionProposals(status?: string) {
  return useQuery({
    queryKey: ["evolution", "proposals", status ?? "all"],
    queryFn: () => evolutionClient.proposals(status),
    refetchInterval: 15_000,
  });
}

export function useEvolutionReports(limit = 10) {
  return useQuery({
    queryKey: ["evolution", "reports", limit],
    queryFn: () => evolutionClient.reports(limit),
    refetchInterval: 30_000,
  });
}

export function useEvolutionStatus() {
  return useQuery({
    queryKey: ["evolution", "status"],
    queryFn: () => evolutionClient.status(),
    refetchInterval: 15_000,
  });
}

// ── Security & System (RC3) ─────────────────────────────────────────

export function useSecurityStatus() {
  return useQuery({
    queryKey: ["security", "status"],
    queryFn: () => securityClient.status(),
    refetchInterval: 10_000,
  });
}

export function useSecurityThreats(limit = 50) {
  return useQuery({
    queryKey: ["security", "threats", limit],
    queryFn: () => securityClient.threats(limit),
    refetchInterval: 15_000,
  });
}

export function useSecurityEvents(limit = 100) {
  return useQuery({
    queryKey: ["security", "events", limit],
    queryFn: () => securityClient.events(limit),
    refetchInterval: 15_000,
  });
}

/** Le niveau d'autonomie en vigueur (§17.5).
 *
 * Pas de `refetchInterval` : contrairement aux menaces ou aux événements,
 * ce réglage ne change que si quelqu'un le change. L'interroger en boucle
 * ferait clignoter un réglage de sécurité sans jamais rien apprendre. */
export function useAutonomy() {
  return useQuery({
    queryKey: ["security", "autonomy"],
    queryFn: () => securityClient.autonomy(),
  });
}

/** Changer le niveau, ou revenir à celui de `config/security.yaml`.
 *
 * Le cache est invalidé sur la réponse du serveur plutôt que mis à jour
 * de façon optimiste : afficher un niveau que le moteur n'aurait pas
 * accepté ferait croire à une permission qui n'existe pas. */
export function useSetAutonomy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (level: string | null) =>
      level === null ? securityClient.resetAutonomy() : securityClient.setAutonomy(level),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["security"] });
    },
  });
}

export function useSubsystemHealth() {
  return useQuery({
    queryKey: ["system", "subsystem-health"],
    queryFn: () => subsystemClient.health(),
    refetchInterval: 10_000,
  });
}

export function useSubsystemAssembly() {
  return useQuery({
    queryKey: ["system", "assembly"],
    queryFn: () => subsystemClient.assembly(),
    refetchInterval: 30_000,
  });
}

export function useSubsystemStatistics() {
  return useQuery({
    queryKey: ["system", "subsystem-statistics"],
    queryFn: () => subsystemClient.statistics(),
    refetchInterval: 15_000,
  });
}

// ── KlaatCode / Oh My Pi ──────────────────────────────────
// klaatcodeClient and ohmypiClient were complete but had no hooks, so the two
// panels rendered module-level MOCK_CAPABILITIES constants and a hard-coded
// "MCP Connected" badge instead of the live agent (RC3 P8).

export function useKlaatCodeStatus() {
  return useQuery({
    queryKey: ["klaatcode", "status"],
    queryFn: () => klaatcodeClient.status(),
    refetchInterval: 15_000,
  });
}

export function useKlaatCodeCapabilities() {
  return useQuery({
    queryKey: ["klaatcode", "capabilities"],
    queryFn: () => klaatcodeClient.capabilities(),
  });
}

export function useOhMyPiStatus() {
  return useQuery({
    queryKey: ["ohmypi", "status"],
    queryFn: () => ohmypiClient.status(),
    refetchInterval: 15_000,
  });
}

export function useOhMyPiCapabilities() {
  return useQuery({
    queryKey: ["ohmypi", "capabilities"],
    queryFn: () => ohmypiClient.capabilities(),
  });
}

// ── Code Intelligence (R-006) ─────────────────────────────
// CodeIntelligenceAgent/Router were real but never instantiated in
// production, so the Center rendered no routing decision at all. These call
// the real /api/v1/code-intelligence surface built to fix that.

export function useCodeIntelligenceStatus() {
  return useQuery({
    queryKey: ["code-intelligence", "status"],
    queryFn: () => codeIntelligenceClient.status(),
    refetchInterval: 15_000,
  });
}

export function useCodeIntelligenceCapabilities() {
  return useQuery({
    queryKey: ["code-intelligence", "capabilities"],
    queryFn: () => codeIntelligenceClient.capabilities(),
  });
}

export function useCodeIntelligenceProviders() {
  return useQuery({
    queryKey: ["code-intelligence", "providers"],
    queryFn: () => codeIntelligenceClient.providers(),
    refetchInterval: 15_000,
  });
}

export function useCodeIntelligenceHistory(limit = 50) {
  return useQuery({
    queryKey: ["code-intelligence", "history", limit],
    queryFn: () => codeIntelligenceClient.history(limit),
  });
}

export function useRunCodeIntelligenceTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, body }: { kind: CodeIntelligenceTaskKind; body: CodeIntelligenceTaskRequest }) =>
      codeIntelligenceClient.runTask(kind, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["code-intelligence"] });
    },
  });
}

// ── Autonomous (HOS-063) ──────────────────────────────────
// No hooks existed for the autonomous surface, so the Center that displays it
// had nothing to call and rendered fabricated constants instead (R-002 P3).

export function useAutonomousStatus() {
  return useQuery({
    queryKey: ["autonomous", "status"],
    queryFn: () => autonomousClient.status(),
    refetchInterval: 5_000,
  });
}

/** Every goal the engine still holds, newest first (HOS-102).
 *
 *  This is what lets the Autonomous Center reattach to a goal it launched
 *  and then lost — by switching tabs, which unmounts the Center, or by
 *  reloading the page. Polled on the same cadence as the status counters
 *  it sits next to, so a goal that finishes while you are looking at the
 *  list stops claiming to be running. */
export function useAutonomousGoals() {
  return useQuery({
    queryKey: ["autonomous", "goals"],
    queryFn: () => autonomousClient.goals(),
    refetchInterval: 5_000,
  });
}

export function useAutonomousGoal(goalId: string | undefined) {
  return useQuery({
    queryKey: ["autonomous", "goal", goalId],
    queryFn: () => autonomousClient.goal(goalId as string),
    enabled: Boolean(goalId),
    refetchInterval: 3_000,
  });
}

// A goal in one of these statuses will not change again on its own — no
// autonomous re-planning happens after a pause (see AutonomousOrchestrator.
// resume_goal(), which only flips the status flag). Polling past this point
// just spends requests forever for a value that has already settled; a
// manual pause/resume/cancel already invalidates ["autonomous"] itself
// (useAutonomousAction), so stopping here doesn't lose any real update.
const AUTONOMOUS_SETTLED_STATUSES = new Set(["completed", "failed", "cancelled", "paused"]);

export function useAutonomousReport(goalId: string | undefined, goalStatus?: string) {
  return useQuery({
    queryKey: ["autonomous", "report", goalId],
    queryFn: () => autonomousClient.report(goalId as string),
    enabled: Boolean(goalId),
    // A goal that never reached execution (e.g. paused pending Aegis
    // validation) will never produce a report — retrying a 404 that can
    // only ever be a 404 just adds noise.
    retry: false,
    // Sans rafraîchissement, ce rapport se figeait à sa première valeur
    // (HOS-117). Le statut, l'objectif et la chronologie se rafraîchissaient
    // toutes les 3 à 5 s ; « Exécution », « Décisions » et « Apprentissage »
    // restaient sur leur premier état pendant toute la durée de l'objectif —
    // un panneau immobile pendant que le travail avance ressemble à un
    // panneau en panne.
    //
    // On s'arrête dès que l'objectif est réglé, même règle que la
    // chronologie : interroger indéfiniment une valeur qui ne changera plus
    // est du bruit (HOS-067 follow-up).
    refetchInterval: goalStatus && AUTONOMOUS_SETTLED_STATUSES.has(goalStatus)
      ? false
      : 3_000,
  });
}

export function useAutonomousTimeline(goalId: string | undefined) {
  return useQuery({
    queryKey: ["autonomous", "timeline", goalId],
    queryFn: () => autonomousClient.timeline(goalId as string),
    enabled: Boolean(goalId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && AUTONOMOUS_SETTLED_STATUSES.has(status) ? false : 3_000;
    },
  });
}

export function useStartAutonomousGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userRequest, context }: { userRequest: string; context?: Record<string, unknown> }) =>
      autonomousClient.start(userRequest, context),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["autonomous"] });
    },
  });
}

/** Pause / resume / cancel. The Center's control buttons were inert. */
export function useAutonomousAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ goalId, action }: {
      goalId: string;
      action: "pause" | "resume" | "cancel";
    }) => autonomousClient[action](goalId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["autonomous"] });
    },
  });
}

// ── Model Intelligence (HOS-060) ──────────────────────────

export function useModelIntelligence() {
  return useQuery({
    queryKey: ["models", "intelligence"],
    queryFn: () => modelIntelligenceClient.models(),
    refetchInterval: 20_000,
  });
}

export function useModelRanking() {
  return useQuery({
    queryKey: ["models", "ranking"],
    queryFn: () => modelIntelligenceClient.ranking(),
    refetchInterval: 30_000,
  });
}

/** Le catalogue mesuré (HOS-108). Aucun refetchInterval : une campagne dure
 *  une à deux heures de GPU, ces lignes ne bougent pas toutes les 30 s. */
export function useModelCatalogue() {
  return useQuery({
    queryKey: ["models", "catalogue"],
    queryFn: () => modelIntelligenceClient.catalogue(),
  });
}

/** Real routing recommendation. The Center used to sleep a random
 *  600–1000 ms and return a hard-coded decision (R-002 P3/P5). */
export function useRecommendModel() {
  return useMutation({
    mutationFn: (payload: { task_type?: string; task_description: string; max_vram_mb?: number }) =>
      modelIntelligenceClient.recommend(payload),
  });
}

export function useModelHistory(limit = 50) {
  return useQuery({
    queryKey: ["models", "history", limit],
    queryFn: () => modelIntelligenceClient.history(limit),
  });
}

/** Real, stored benchmark results (HOS-065) — no longer a fresh batch of
 *  random.uniform() numbers regenerated on every call. */
export function useModelBenchmarks(modelId?: string) {
  return useQuery({
    queryKey: ["models", "benchmarks", modelId ?? "all"],
    queryFn: () => modelIntelligenceClient.benchmarks(modelId),
  });
}

/** Triggers one real benchmark run (a real Ollama call) — slow by
 *  construction, see BenchmarkScheduler's own docstring. */
export function useRunBenchmark() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { model_id: string; task_type: string }) =>
      modelIntelligenceClient.runBenchmark(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models", "benchmarks"] });
      qc.invalidateQueries({ queryKey: ["models", "ranking"] });
    },
  });
}

/** Real cross-runtime/quantization comparison for one model (HOS-071
 *  Phase D) — ModelRuntimeOptimizer's own math, wired to a route for the
 *  first time. */
export function useModelOptimize(modelId: string | undefined) {
  return useQuery({
    queryKey: ["models", "optimize", modelId],
    queryFn: () => modelIntelligenceClient.optimize(modelId as string),
    enabled: !!modelId,
  });
}

/** OpenRouter cloud escalation status (HOS-066C) — cheap (reads a cache,
 *  never itself spends quota), so a short poll is fine. */
export function useCloudStatus() {
  return useQuery({
    queryKey: ["models", "cloud-status"],
    queryFn: () => modelIntelligenceClient.cloudStatus(),
    refetchInterval: 30_000,
  });
}

// ── Conversation (HOS-062) ────────────────────────────────



export function useConversationDecision() {
  return useMutation({
    mutationFn: ({ sessionId, decision }: {
      sessionId: string;
      decision: "approve" | "cancel";
    }) => conversationClient[decision](sessionId),
  });
}

// ── Workspace / Verification / Monitoring (P-001) ─────────
// Ces API existaient toutes ; aucun écran ne les atteignait.

export function useWorkspaces() {
  return useQuery({
    queryKey: ["workspace", "list"],
    queryFn: () => workspaceClient.list(),
    refetchInterval: 10_000,
  });
}

export function useWorkspaceAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: {
      id: string;
      action: "lock" | "release" | "remove";
    }) => workspaceClient[action](id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workspace"] }),
  });
}

// ── Projects & Git ───────────────────────────────────────
export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: projectsClient.list });
}
export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: projectsClient.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
export function useRemoveProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: projectsClient.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof projectsClient.update>[1] }) =>
      projectsClient.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
/** Really probes root_path on disk (exists/is-dir/readable/writable) and
 *  persists the result — the only way a Project's root starts granting
 *  filesystem access via Aegis's dynamic whitelist. */
export function useValidateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => projectsClient.validate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
/** Read-only directory listing for the "add a workspace" folder picker
 *  (GET /filesystem/browse) — not Aegis-gated, directories only, never
 *  file contents. `enabled: false` by default since this is invoked on
 *  demand (a click), not on mount. */
export function useFilesystemBrowse(path: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["filesystem", "browse", path ?? ""],
    queryFn: () => filesystemBrowseClient.browse(path),
    enabled,
    retry: false,
  });
}
/** Real `git status` on the project's root_path — silently disabled
 *  (`enabled: !!repoPath`) rather than firing on an empty path, and
 *  `retry: false` because a 400 ("not a repository") is a legitimate,
 *  non-transient answer, not a flake to retry into a success. */
export function useGitStatus(repoPath: string | null | undefined) {
  return useQuery({
    queryKey: ["git", "status", repoPath],
    queryFn: () => gitClient.status(repoPath as string),
    enabled: !!repoPath,
    retry: false,
  });
}
export function useCreatePullRequest() {
  return useMutation({ mutationFn: gitClient.createPullRequest });
}
/** Binds/unbinds a conversation session's active workspace
 *  (POST /conversation/{id}/project). Invalidates the session's own
 *  context query so anything reading active_project_id picks up the
 *  change immediately. */
export function useBindProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, projectId }: { sessionId: string; projectId: string | null }) =>
      conversationClient.bindProject(sessionId, projectId),
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ["conversation", "context", vars.sessionId] }),
  });
}

export function useVerificationRunners() {
  return useQuery({
    queryKey: ["verification", "runners"],
    queryFn: () => verificationClient.runners(),
  });
}

export function useRunVerification() {
  return useMutation({
    mutationFn: verificationClient.run,
  });
}

export function useMonitoringResources() {
  return useQuery({
    queryKey: ["monitoring", "resources"],
    queryFn: () => monitoringClient.resources(),
    refetchInterval: 5_000,
  });
}

export function useRuntimeEventLog(limit = 50) {
  return useQuery({
    queryKey: ["monitoring", "runtime-events", limit],
    queryFn: () => monitoringClient.runtimeEvents(limit),
    refetchInterval: 10_000,
  });
}

export function useRuntimeIntelligence() {
  return useQuery({
    queryKey: ["monitoring", "intelligence"],
    queryFn: () => monitoringClient.intelligenceScores(),
    refetchInterval: 30_000,
  });
}

export function useExecutionStatistics() {
  return useQuery<ExecutionStatistics>({
    queryKey: ["execution", "statistics"],
    queryFn: () => executionClient.statistics(),
    refetchInterval: 10_000,
  });
}

export function useResourceAllocations() {
  return useQuery({
    queryKey: ["monitoring", "allocations"],
    queryFn: () => monitoringClient.allocations(),
    refetchInterval: 10_000,
  });
}

// ── Evolution : actions à effet de bord (P-002) ───────────
// simulate / approve / apply modifient le système. Le Cockpit les expose
// derrière une confirmation explicite (voir components/confirm-action.tsx) ;
// l'autorisation finale reste au backend (Policy / Security / Approval).

export function useEvolutionAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: {
      id: string;
      action: "simulate" | "approve" | "apply";
    }) => evolutionClient[action](id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["evolution"] }),
  });
}

export function useEvolutionAnalyze() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => evolutionClient.analyze(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["evolution"] }),
  });
}

/** Le Studio (HOS-190).
 *
 *  Rafraîchi à la seconde pendant qu'un rendu tourne, à la minute sinon :
 *  la VRAM ne bouge que quand quelque chose travaille, et sonder un
 *  compteur GPU par PowerShell coûte assez pour ne pas le faire pour
 *  rien. */
export function useStudioState() {
  return useQuery({
    queryKey: ["studio", "state"],
    queryFn: studioClient.state,
    refetchInterval: 5000,
  });
}

export function useStudioModels() {
  return useQuery({ queryKey: ["studio", "models"], queryFn: studioClient.models });
}

export function useStudioVram(actif: boolean) {
  return useQuery({
    queryKey: ["studio", "vram"],
    queryFn: studioClient.vram,
    refetchInterval: actif ? 2000 : 30000,
  });
}
