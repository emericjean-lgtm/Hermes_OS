"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import {
  useAutonomousAction,
  useAutonomousGoal,
  useAutonomousGoals,
  useAutonomousReport,
  useAutonomousStatus,
  useAutonomousTimeline,
  useStartAutonomousGoal,
} from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";
import {
  BrainCircuit,
  Play,
  Pause,
  XCircle,
  CheckCircle,
  AlertCircle,
  History,
} from "lucide-react";
import { CenterHeader } from "@/components/center-scaffold";
import { DecompositionPanel } from "@/features/missions/decomposition-panel";

// This Center used to render four module-level constants — MOCK_GOAL,
// MOCK_SESSION, MOCK_DECISIONS and MOCK_TIMELINE — describing a fabricated
// mission on a "ktransformers" runtime, plus a "Pipeline Flow" card with five
// hard-coded green ticks (Security Validation ✓, Policy Check ✓, ...) that were
// true regardless of what the system had done. Meanwhile /api/v1/autonomous
// executed real missions against Ollama. Everything below is now live
// (R-002 P3).

const statusBadge = (status: string | undefined) => {
  const v: Record<string, "success" | "warning" | "danger" | "default"> = {
    completed: "success", executing: "warning", analyzing: "default",
    planning: "default", failed: "danger", cancelled: "danger", paused: "warning",
  };
  return <Badge variant={v[status ?? ""] || "default"}>{status ?? "unknown"}</Badge>;
};

export function AutonomousCenter() {
  const [request, setRequest] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [repository, setRepository] = useState("");
  const [branch, setBranch] = useState("");
  // Deliberately NOT component state (HOS-102). The Cockpit shell keys its
  // AnimatePresence on the active view, so switching tabs unmounts this
  // Center outright — a goal id held in useState died with it while the
  // goal itself kept running on the server, which is exactly the "the task
  // disappeared" the operator reported.
  const { selectedGoalId, selectGoal } = useCockpitStore();
  const goalId = selectedGoalId ?? undefined;

  const status = useAutonomousStatus();
  const goals = useAutonomousGoals();
  const start = useStartAutonomousGoal();
  const action = useAutonomousAction();
  // Read from the polled query rather than from start.data: a mutation's
  // result is a snapshot frozen at the instant the goal was created, so the
  // status badge below used to show "analyzing" forever — and it vanished
  // with the mutation on unmount.
  const goalQuery = useAutonomousGoal(goalId);
  const goal = goalQuery.data;
  // Le statut est passé au rapport pour qu'il cesse d'interroger une fois
  // l'objectif réglé — sans lui, le rapport se figeait à sa première
  // valeur pendant toute l'exécution (HOS-117).
  const report = useAutonomousReport(goalId, goal?.status);
  const timeline = useAutonomousTimeline(goalId);

  const rep = report.data;
  const busy = start.isPending;
  const knownGoals = goals.data?.goals ?? [];

  const execute = () => {
    const text = request.trim();
    if (!text) return;
    const context: Record<string, unknown> = {};
    if (localPath.trim()) context.local_path = localPath.trim();
    if (repository.trim()) context.repository = repository.trim();
    if (branch.trim()) context.branch = branch.trim();
    start.mutate(
      { userRequest: text, context },
      { onSuccess: (g) => selectGoal(g.goal_id) },
    );
  };

  return (
    <div className="animate-fade-in p-6">
      {/* Header — the badge reflects the engine's real counters */}
      <CenterHeader
        title="Autonomous OS"
        subtitle="Noyau agentique final — HOS-063"
        right={<>{status.isLoading ? (
          <Badge variant="default">Vérification du noyau…</Badge>
        ) : status.isError ? (
          <Badge variant="danger">
            <AlertCircle className="w-3 h-3 mr-1" />
            Noyau injoignable
          </Badge>
        ) : (
          <Badge variant="success">
            <BrainCircuit className="w-3 h-3 mr-1" />
            {status.data?.total_goals ?? 0} objectif(s) · {status.data?.active ?? 0} actif(s)
          </Badge>
        )}</>}
      />

      {/* Goal Input — now actually starts a mission */}
      <Card title="Objectif" className="mb-6">
        <div className="flex gap-3">
          <input
            type="text"
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") execute();
            }}
            placeholder="Décrivez votre objectif… ex. « Analyser le module d'authentification »"
            className="flex-1 bg-hermes-bg border border-hermes-border rounded-lg px-4 py-2.5 text-sm text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
          />
          <button
            onClick={execute}
            disabled={!request.trim() || busy}
            className="px-4 py-2.5 bg-hermes-amber/10 text-hermes-amber-bright border border-hermes-amber/30 rounded-lg hover:bg-hermes-amber/20 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Play className="w-4 h-4" />
            {busy ? "En cours…" : "Exécuter"}
          </button>
        </div>

        {/* Project binding (HOS-067) — optional. A goal bound to either
            requires Aegis validation before it runs (see the "paused"
            status below) instead of the unconditional pass-through a
            plain, unbound goal gets. */}
        <div className="grid grid-cols-3 gap-3 mt-3">
          <input
            type="text"
            value={localPath}
            onChange={(e) => setLocalPath(e.target.value)}
            placeholder="Dossier local (optionnel) — ex. C:\projects\my-app"
            className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-[11px] text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
          />
          <input
            type="text"
            value={repository}
            onChange={(e) => setRepository(e.target.value)}
            placeholder="Dépôt GitHub (optionnel) — ex. owner/repo"
            className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-[11px] text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
          />
          <input
            type="text"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            placeholder="Branche (optionnel) — défaut : main"
            className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-[11px] text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
          />
        </div>
        {busy && (
          <div className="text-[10px] text-hermes-muted font-mono mt-2">
            Inférence réelle en cours — la durée dépend du modèle utilisé.
          </div>
        )}
        {start.isError && (
          <div className="text-[10px] text-hermes-red font-mono mt-2">
            {start.error instanceof Error ? start.error.message : "Échec du démarrage de l'objectif"}
          </div>
        )}
      </Card>

      {/* Engine counters — every number below comes from /autonomous/status */}
      <div className="grid grid-cols-6 gap-2 mb-6">
        {[
          { label: "Objectifs", value: status.data?.total_goals },
          { label: "Actifs", value: status.data?.active },
          { label: "Terminés", value: status.data?.completed },
          { label: "Échoués", value: status.data?.failed },
          { label: "Exécutions", value: status.data?.total_executions },
          { label: "Décisions", value: status.data?.decisions?.total_decisions },
        ].map((s) => (
          <div key={s.label} className="bg-hermes-card border border-hermes-border rounded-lg p-2 text-center">
            <div className="text-[9px] text-hermes-muted font-mono uppercase">{s.label}</div>
            <div className="text-sm font-bold font-mono text-hermes-text mt-0.5">
              {status.isLoading ? "…" : (s.value ?? "—")}
            </div>
          </div>
        ))}
      </div>

      {/* Reattachment (HOS-102). The engine holds every goal it has run,
          but nothing could enumerate them, so a goal whose id the UI had
          lost — by unmounting, or by a page reload — kept running with no
          way back to it. Shown whenever there is something to return to,
          including while another goal is selected: an operator who launched
          two goals should be able to switch between them. */}
      {knownGoals.length > 0 && (
        <Card title="Reprendre un objectif" className="mb-6">
          <div className="flex flex-col gap-1.5">
            {knownGoals.slice(0, 8).map((g) => (
              <button
                key={g.goal_id}
                onClick={() => selectGoal(g.goal_id)}
                className={`flex items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors
                  ${g.goal_id === goalId
                    ? "border-hermes-amber/40 bg-hermes-amber/[0.07]"
                    : "border-hermes-border/60 hover:bg-hermes-elevated/60"}`}
              >
                <History className="w-3 h-3 shrink-0 text-hermes-muted" />
                <span className="min-w-0 flex-1 truncate text-[11px] font-mono text-hermes-text">
                  {g.user_request}
                </span>
                {statusBadge(g.status)}
              </button>
            ))}
          </div>
        </Card>
      )}

      {!goalId && (
        <Card title="Objectif en cours" className="mb-6">
          <div className="text-xs text-hermes-muted font-mono py-3">
            {knownGoals.length > 0
              ? "Aucun objectif sélectionné. Reprenez-en un ci-dessus, ou décrivez-en un nouveau."
              : "Aucun objectif en cours. Décrivez-en un ci-dessus pour démarrer une mission réelle."}
          </div>
        </Card>
      )}

      {goalId && goal && (
        <Card title="Objectif en cours" className="mb-6">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[10px] text-hermes-muted font-mono uppercase mb-1">Demande utilisateur</div>
              <div className="text-xs text-hermes-text font-mono bg-hermes-bg p-2 rounded-lg border border-hermes-border/50">
                {goal.user_request}
              </div>
              <div className="text-[10px] text-hermes-muted font-mono uppercase mt-3 mb-1">Interprétation</div>
              <div className="text-[10px] text-hermes-text">{goal.interpreted_goal}</div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: "Domaine", value: goal.domain, color: "text-hermes-blue" },
                { label: "Langue", value: goal.language, color: "text-hermes-green" },
                {
                  label: "Complexité",
                  value: `${((goal.complexity ?? 0) * 100).toFixed(0)}%`,
                  color: "text-hermes-amber",
                },
                { label: "Statut", value: goal.status, color: "text-hermes-purple" },
              ].map((s) => (
                <div key={s.label} className="bg-hermes-card/50 border border-hermes-border/50 rounded-lg p-2">
                  <div className="text-[9px] text-hermes-muted font-mono uppercase">{s.label}</div>
                  <div className={`text-sm font-bold font-mono ${s.color}`}>{s.value || "—"}</div>
                </div>
              ))}
            </div>
          </div>
          {(goal.local_path || goal.repository) && (
            <div className="mt-3 pt-3 border-t border-hermes-border/30 flex gap-4 text-[10px] font-mono">
              {goal.local_path && (
                <div>
                  <span className="text-hermes-muted uppercase">Local : </span>
                  <span className="text-hermes-text">{goal.local_path}</span>
                </div>
              )}
              {goal.repository && (
                <div>
                  <span className="text-hermes-muted uppercase">Dépôt : </span>
                  <span className="text-hermes-text">
                    {goal.repository}{goal.branch ? `@${goal.branch}` : ""}
                  </span>
                </div>
              )}
            </div>
          )}
          {goal.status === "paused" && (
            <div className="mt-3 pt-3 border-t border-hermes-border/30 text-[10px] font-mono text-hermes-amber flex items-center gap-2">
              <AlertCircle className="w-3 h-3" />
              {/* Ce message envoyait éditer `autonomy_level` dans un fichier
                  et redémarrer. Le curseur existe maintenant dans le
                  Validation Center (HOS-115) — envoyer quelqu'un modifier
                  une configuration à la main pour un réglage qui a son
                  bouton, c'est décrire le produit d'avant. */}
              Cet objectif touche un projet réel et nécessite une validation
              humaine (Aegis) avant de démarrer. Approuvez-le dans la file
              d&apos;attente, ou relevez le niveau d&apos;autonomie depuis le
              Validation Center, puis reprenez-le.
            </div>
          )}
          {goal.knowledge_context && (
            <div className="mt-3 pt-3 border-t border-hermes-border/30">
              <div className="text-[10px] text-hermes-muted font-mono uppercase mb-1">
                Missions passées
              </div>
              <div className="text-[10px] text-hermes-text">{goal.knowledge_context}</div>
            </div>
          )}
        </Card>
      )}

      {/* Execution + decisions, both from the report */}
      {goalId && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <Card title="Exécution">
            {report.isLoading && (
              <div className="text-[10px] text-hermes-muted font-mono">Chargement du rapport…</div>
            )}
            {report.isError && goal?.status === "paused" && (
              <div className="text-[10px] text-hermes-amber font-mono">
                Pas encore de rapport — cet objectif est en pause en attente
                de validation humaine et n&apos;a pas encore été exécuté.
              </div>
            )}
            {report.isError && goal?.status !== "paused" && (
              <div className="text-[10px] text-hermes-red font-mono">
                Rapport indisponible
              </div>
            )}
            {rep && (
              <div className="space-y-2">
                <div
                  className={`text-[10px] font-mono p-2 rounded border ${
                    rep.execution_summary?.startsWith("WARNING:")
                      ? "text-hermes-red border-hermes-red/40 bg-hermes-red/5"
                      : "text-hermes-text border-hermes-border/50 bg-hermes-bg"
                  }`}
                >
                  {rep.execution_summary}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Agents</span>
                  <div className="flex gap-1 flex-wrap justify-end">
                    {rep.agents_used.length === 0 ? (
                      <span className="text-[10px] text-hermes-muted font-mono">aucun</span>
                    ) : (
                      rep.agents_used.map((a) => (
                        <Badge key={a} variant="default" className="text-[9px]">{a}</Badge>
                      ))
                    )}
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Runtimes</span>
                  <span className="text-[10px] font-mono text-hermes-text">
                    {rep.runtimes_used.join(", ") || "aucun"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Durée</span>
                  <span className="text-[10px] font-mono text-hermes-text">
                    {rep.total_duration_ms.toFixed(0)}ms
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Résultat</span>
                  {statusBadge(rep.success ? "completed" : "failed")}
                </div>
                {/* HOS-121 : « Résultat » ci-dessus est ce que la mission
                    prétend. Sur l'essai Skills360 il valait « completed »
                    au-dessus d'un livrable dont les tests ne compilaient
                    pas — parce que `verification_run` exige le niveau
                    d'autonomie `high` et que la configuration livrée est
                    `medium`. Cette ligne-ci dit ce qui a été *constaté*,
                    et « non mesurée » est un état à part entière : ce
                    n'est ni un succès ni un échec. */}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">
                    Qualité constatée
                  </span>
                  {rep.qualite === "verifiee" ? (
                    <Badge variant="success" className="text-[9px]">vérifiée</Badge>
                  ) : rep.qualite === "contredite" ? (
                    <Badge variant="danger" className="text-[9px]">contredite</Badge>
                  ) : (
                    <span
                      title={
                        String(
                          (rep.verification as { tests?: { reason?: string } } | null)
                            ?.tests?.reason ?? "",
                        ) || "aucune vérification n'a été tentée"
                      }
                    >
                      <Badge variant="warning" className="text-[9px]">
                        non mesurée
                      </Badge>
                    </span>
                  )}
                </div>
                {/* `tools_used` était rempli par le moteur et affiché nulle
                    part. Étiqueté « retenus au plan » et non « appelés » :
                    il vient des décisions de planification
                    (AutonomousOrchestrator, `plan_decisions`), pas d'un
                    compteur d'invocations. Les confondre annoncerait un
                    travail qui n'a peut-être pas eu lieu (HOS-117). */}
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[10px] text-hermes-muted font-mono shrink-0">
                    Outils retenus au plan
                  </span>
                  <div className="flex gap-1 flex-wrap justify-end">
                    {rep.tools_used && rep.tools_used.length > 0 ? (
                      rep.tools_used.map((t) => (
                        <Badge key={t} variant="default" className="text-[9px]">{t}</Badge>
                      ))
                    ) : (
                      <span className="text-[10px] text-hermes-muted font-mono">aucun</span>
                    )}
                  </div>
                </div>
              </div>
            )}
          </Card>

          <Card title={`Décisions${rep ? ` (${rep.decisions.length})` : ""}`}>
            {report.isLoading && (
              <div className="text-[10px] text-hermes-muted font-mono">Chargement des décisions…</div>
            )}
            {rep && rep.decisions.length === 0 && (
              <div className="text-[10px] text-hermes-muted font-mono">
                Le moteur n&apos;a enregistré aucune décision pour cet objectif.
              </div>
            )}
            <div className="space-y-1.5">
              {rep?.decisions.map((d) => (
                <div key={d.decision_id} className="text-[9px] font-mono">
                  <div className="flex items-center justify-between">
                    <div className="text-hermes-muted">
                      {d.decision_type.replace(/_/g, " ")}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-hermes-text">{d.selected}</span>
                      <span className="text-hermes-green">
                        {(d.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                  <div className="text-[8px] text-hermes-muted/70 truncate">{d.reason}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* La décomposition réelle de l'objectif (HOS-117).
          L'orchestrateur construit une vraie mission DAG ; le Center
          n'en montrait que des compteurs et des décisions, jamais les
          tâches. Le lien objectif → mission passe par la session, que
          rien n'exposait — d'où l'impression d'un cul-de-sac. Même
          panneau que le Mission Center : une seule vue du DAG, pas deux
          qui divergeraient. */}
      {goalId && goal?.mission_id && (
        <div className="mb-6">
          <DecompositionPanel missionId={goal.mission_id} />
        </div>
      )}

      {goalId && goal && !goal.mission_id && goal.status !== "paused" && (
        <Card title="Décomposition" className="mb-6">
          <p className="text-[10px] text-hermes-muted font-mono">
            Cet objectif n&apos;a pas encore de mission — la planification
            n&apos;a pas produit de DAG, ou elle est encore en cours.
          </p>
        </Card>
      )}

      {/* Timeline + lessons, both real */}
      {goalId && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <Card title="Chronologie">
            {timeline.isLoading && (
              <div className="text-[10px] text-hermes-muted font-mono">Chargement de la chronologie…</div>
            )}
            {timeline.data?.timeline.length === 0 && (
              <div className="text-[10px] text-hermes-muted font-mono">
                Aucune entrée pour l&apos;instant.
              </div>
            )}
            <div className="space-y-0">
              {timeline.data?.timeline.map((t, i) => (
                <div key={`${t.event}-${i}`} className="flex items-center gap-2 py-1.5 border-b border-hermes-border/20 last:border-0">
                  <div className="w-1.5 h-1.5 rounded-full bg-hermes-green" />
                  <span className="text-[10px] font-mono text-hermes-text flex-1">
                    {t.event.replace(/_/g, " ")}
                  </span>
                  <span className="text-[9px] text-hermes-muted font-mono">
                    {t.decisions.length} décision(s)
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Apprentissage">
            {rep && rep.lessons.length === 0 && rep.improvements.length === 0 && (
              <div className="text-[10px] text-hermes-muted font-mono">
                Aucune leçon enregistrée pour cet objectif.
              </div>
            )}
            <div className="flex flex-col gap-1.5 text-[10px] font-mono">
              {rep?.lessons.map((l, i) => (
                <div key={`lesson-${i}`} className="flex items-start gap-2 text-hermes-green">
                  <CheckCircle className="w-3 h-3 mt-0.5 shrink-0" />
                  <span className="text-hermes-text">{l}</span>
                </div>
              ))}
              {rep?.improvements.map((im, i) => (
                <div key={`improvement-${i}`} className="flex items-start gap-2 text-hermes-amber">
                  <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                  <span className="text-hermes-text">{im}</span>
                </div>
              ))}
            </div>
            {status.data && (
              <div className="mt-3 pt-2 border-t border-hermes-border/30 text-[9px] font-mono text-hermes-muted">
                boucle mémoire : {status.data.memory_loop.missions} mission(s),{" "}
                {status.data.memory_loop.success_rate}% de réussite,{" "}
                {status.data.memory_loop.total_lessons} leçon(s)
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Controls — these buttons were inert; they now call the real endpoints */}
      <Card title="Contrôles">
        <div className="flex gap-3 items-center">
          <button
            onClick={() => goalId && action.mutate({ goalId, action: "resume" })}
            disabled={!goalId || action.isPending}
            className="px-4 py-2 bg-hermes-green/10 text-hermes-green border border-hermes-green/30 rounded-lg hover:bg-hermes-green/20 transition-colors flex items-center gap-2 text-xs font-mono disabled:opacity-40"
          >
            <Play className="w-3 h-3" /> Reprendre
          </button>
          <button
            onClick={() => goalId && action.mutate({ goalId, action: "pause" })}
            disabled={!goalId || action.isPending}
            className="px-4 py-2 bg-hermes-amber/10 text-hermes-amber border border-hermes-amber/30 rounded-lg hover:bg-hermes-amber/20 transition-colors flex items-center gap-2 text-xs font-mono disabled:opacity-40"
          >
            <Pause className="w-3 h-3" /> Pause
          </button>
          <button
            onClick={() => goalId && action.mutate({ goalId, action: "cancel" })}
            disabled={!goalId || action.isPending}
            className="px-4 py-2 bg-hermes-red/10 text-hermes-red border border-hermes-red/30 rounded-lg hover:bg-hermes-red/20 transition-colors flex items-center gap-2 text-xs font-mono disabled:opacity-40"
          >
            <XCircle className="w-3 h-3" /> Annuler
          </button>
          {!goalId && (
            <span className="text-[10px] text-hermes-muted font-mono">
              Démarrez un objectif pour activer les contrôles.
            </span>
          )}
        </div>
      </Card>
    </div>
  );
}
