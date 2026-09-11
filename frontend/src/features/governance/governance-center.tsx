"use client";

import { useState } from "react";
import {
  useApprovals,
  useApproveAction,
  useAuditLog,
  usePolicyRules,
  useRejectAction,
} from "@/hooks/use-api";
import {
  AsyncPanel,
  CenterHeader,
  CenterTabs,
  DataTable,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import { Badge, Button, Beacon } from "@/components/ui/card";
import type { AuditEntry, PolicyRule } from "@/types/hermes";

/* ═══════════════════════════════════════════════════════════════════
   Governance Center — fusion de Governance et Policy.

   Les deux écrans consommaient exactement les mêmes hooks
   (usePolicyRules, useApprovals, useAuditLog, useApproveAction,
   useRejectAction) et donc les mêmes trois endpoints : ils affichaient
   les mêmes données sous deux noms, avec deux mises en page qui
   divergeaient à chaque évolution.

   La fusion garde le meilleur des deux : l'architecture de Policy
   (briques du scaffold, recherche, filtres par catégorie, remontée
   d'erreur de décision) et le rendu de Governance (journal d'audit en
   colonnes plutôt qu'en JSON brut, règles avec état activé/désactivé et
   description, métadonnées de demande d'approbation).
   ═══════════════════════════════════════════════════════════════════ */

type Tab = "approvals" | "rules" | "audit";

export function GovernanceCenter() {
  const rules = usePolicyRules();
  const approvals = useApprovals();
  const audit = useAuditLog();
  const approve = useApproveAction();
  const reject = useRejectAction();

  const [tab, setTab] = useState<Tab>("approvals");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("Tous");
  const [lastError, setLastError] = useState<string | null>(null);

  const allRules = rules.data ?? [];
  const allAudit = audit.data ?? [];
  const categories = [
    "Tous",
    ...Array.from(new Set(allRules.map((r) => r.category).filter(Boolean))).slice(0, 6),
  ];

  const visibleRules = allRules.filter((r) => {
    const hay = `${r.name} ${r.category} ${r.decision}`.toLowerCase();
    if (search && !hay.includes(search.toLowerCase())) return false;
    return filter === "Tous" || r.category === filter;
  });

  const visibleAudit = allAudit.filter((e) => {
    if (!search) return true;
    return JSON.stringify(e).toLowerCase().includes(search.toLowerCase());
  });

  // G-36 : la file lue est celle d'AEGIS — SQLite, alimentee sur le chemin
  // de requete reel. Celle de `backend/policy/` etait un dictionnaire en
  // memoire sans producteur : cet ecran annoncait « aucune approbation en
  // attente » par construction, quoi qu'il arrive.
  //
  // Une demande expiree est ecartee : Aegis ne la consommera plus, et la
  // laisser ici ferait croire qu'une decision sert encore a quelque chose.
  const pending = (approvals.data ?? []).filter(
    (a) => String(a.status).toLowerCase() === "pending" && !a.expired,
  );

  const decide = (id: string, verb: "approve" | "reject") => {
    setLastError(null);
    const mutation = verb === "approve" ? approve : reject;
    mutation.mutate(
      { id },
      { onError: (e) => setLastError(e instanceof Error ? e.message : "Décision refusée") },
    );
  };

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Governance Center"
        subtitle="Approbation humaine, moteur de politiques et piste d'audit"
        right={
          pending.length > 0 ? (
            <Badge variant="warning">
              <Beacon tone="amber" />
              {pending.length} en attente
            </Badge>
          ) : (
            <Badge variant="success">Aucune décision en attente</Badge>
          )
        }
      />

      <StatGrid
        columns={4}
        stats={[
          { label: "Règles", value: allRules.length },
          { label: "Catégories", value: Math.max(categories.length - 1, 0) },
          {
            label: "En attente",
            value: pending.length,
            tone: pending.length > 0 ? "warn" : "ok",
          },
          { label: "Entrées d'audit", value: allAudit.length },
        ]}
      />

      <CenterTabs
        active={tab}
        onChange={setTab}
        tabs={[
          {
            id: "approvals",
            label: "Approbations",
            badge: pending.length > 0 ? <Badge variant="warning">{pending.length}</Badge> : null,
          },
          { id: "rules", label: "Règles" },
          { id: "audit", label: "Audit" },
        ]}
      />

      {lastError && (
        <div className="mb-3 flex items-start gap-2 px-3 py-2 rounded-lg glass border border-hermes-red/40">
          <span className="text-hermes-red text-glow-red font-mono">⚠</span>
          <span className="text-hermes-red text-[11px] font-mono">{lastError}</span>
        </div>
      )}

      {/* ── Approbations ─────────────────────────────────────────── */}
      {tab === "approvals" && (
        <AsyncPanel
          title="Approbations en attente"
          subtitle={
            `${pending.length} demande(s) — /api/v1/security/approvals ` +
            `(file d'Aegis, un accord vaut pour une seule tentative)`
          }
          isLoading={approvals.isLoading}
          isError={approvals.isError}
          error={approvals.error}
          isEmpty={pending.length === 0}
          emptyLabel="Aucune approbation en attente."
        >
          <div className="flex flex-col gap-2">
            {pending.map((req) => (
              <div
                key={req.id}
                className="group flex items-start justify-between gap-4 p-3 rounded-lg
                  bg-hermes-bg-deep/50 border border-hermes-border/50
                  hover:border-hermes-amber/40 transition-colors"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    {/* Le type d'action EST la gravite ici : Aegis la tire
                        de `config/security.yaml`, ou `skill_install` est
                        `mandatory_validation`. Une priorite inventee a
                        l'ecran serait une affirmation que la donnee ne
                        porte pas. */}
                    <Badge
                      variant={
                        req.action_type.startsWith("skill_") ? "warning"
                        : req.action_type.includes("delete")
                          || req.action_type.includes("critical") ? "danger"
                        : "default"
                      }
                    >
                      {req.action_type}
                    </Badge>
                    <span className="text-[12px] font-medium text-hermes-text font-mono truncate">
                      {req.description || "—"}
                    </span>
                  </div>
                  <div className="text-[10px] text-hermes-dim font-mono">
                    demandee par {req.requesting_agent || "?"}
                    {req.created_at && ` · ${new Date(req.created_at).toLocaleString()}`}
                    {req.expires_at &&
                      ` · expire ${new Date(req.expires_at).toLocaleTimeString()}`}
                  </div>
                  {req.reason && (
                    <div className="text-[10px] text-hermes-muted mt-1">
                      {req.reason}
                    </div>
                  )}
                  {req.target_path && (
                    <div className="num text-[10px] text-hermes-glacier mt-1 truncate">
                      {req.target_path}
                    </div>
                  )}
                </div>
                <div className="flex gap-1.5 shrink-0">
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => decide(req.id, "reject")}
                    disabled={reject.isPending}
                  >
                    Rejeter
                  </Button>
                  <Button
                    variant="success"
                    size="sm"
                    onClick={() => decide(req.id, "approve")}
                    disabled={approve.isPending}
                  >
                    Approuver
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </AsyncPanel>
      )}

      {/* ── Règles ───────────────────────────────────────────────── */}
      {tab === "rules" && (
        <>
          <Toolbar
            search={search}
            onSearch={setSearch}
            placeholder="Rechercher une règle par nom, catégorie ou décision…"
            filters={categories}
            activeFilter={filter}
            onFilter={setFilter}
          />
          <AsyncPanel
            title="Règles de politique"
            subtitle={`${visibleRules.length} affichée(s) sur ${allRules.length} — /api/v1/policy/rules`}
            isLoading={rules.isLoading}
            isError={rules.isError}
            error={rules.error}
            isEmpty={visibleRules.length === 0}
            emptyLabel={
              allRules.length === 0
                ? "Aucune règle chargée."
                : "Aucune règle ne correspond à ce filtre."
            }
          >
            <div className="flex flex-col gap-1.5">
              {visibleRules.map((rule) => (
                <RuleRow key={rule.id} rule={rule} />
              ))}
            </div>
          </AsyncPanel>
        </>
      )}

      {/* ── Audit ────────────────────────────────────────────────── */}
      {tab === "audit" && (
        <>
          <Toolbar
            search={search}
            onSearch={setSearch}
            placeholder="Rechercher dans le journal d'audit…"
          />
          <AsyncPanel
            title="Journal d'audit"
            subtitle={`${visibleAudit.length} entrée(s) — /api/v1/audit`}
            isLoading={audit.isLoading}
            isError={audit.isError}
            error={audit.error}
            isEmpty={visibleAudit.length === 0}
            emptyLabel={
              allAudit.length === 0
                ? "Le journal d'audit est vide."
                : "Aucune entrée ne correspond à cette recherche."
            }
          >
            <DataTable
              rows={visibleAudit.slice(0, 200)}
              rowKey={(e, i) => e.id ?? String(i)}
              columns={[
                {
                  header: "Horodatage",
                  cell: (e) =>
                    e.created_at ? new Date(e.created_at).toLocaleTimeString() : "—",
                },
                { header: "Acteur", cell: (e) => e.principal || "—" },
                { header: "Opération", cell: (e) => e.operation || "—" },
                { header: "Résultat", cell: (e) => <ResultBadge entry={e} /> },
                {
                  header: "Durée",
                  align: "right",
                  cell: (e) =>
                    typeof e.duration_ms === "number" ? `${e.duration_ms} ms` : "—",
                },
              ]}
            />
          </AsyncPanel>
        </>
      )}
    </div>
  );
}

/* ── Sous-composants ────────────────────────────────────────────── */

function RuleRow({ rule }: { rule: PolicyRule }) {
  // /api/v1/policy/rules envoie `decision` en minuscules ("allow", "deny",
  // "review_required"). Ce composant lisait `rule.action` en majuscules — un
  // champ que l'endpoint n'a jamais renvoyé, donc un badge toujours vide (P-001).
  const decisionVariant: Record<string, "success" | "danger" | "warning"> = {
    allow: "success",
    deny: "danger",
    review_required: "warning",
  };

  return (
    <div
      className="group flex items-center justify-between gap-3 p-2.5 rounded-lg
        bg-hermes-bg-deep/50 border border-hermes-border/50
        hover:border-hermes-cyan/30 transition-colors"
    >
      <div className="min-w-0">
        <div className="text-[12px] font-medium text-hermes-text truncate">{rule.name}</div>
        {rule.description && (
          <div className="text-[10px] text-hermes-dim mt-0.5 truncate">{rule.description}</div>
        )}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {rule.category && <Badge>{rule.category}</Badge>}
        <Badge variant={rule.enabled ? "success" : "default"}>
          {rule.enabled ? "ACTIVE" : "INACTIVE"}
        </Badge>
        <Badge variant={decisionVariant[rule.decision] ?? "default"}>{rule.decision}</Badge>
      </div>
    </div>
  );
}

function ResultBadge({ entry }: { entry: AuditEntry }) {
  const r = String(entry.result ?? "").toUpperCase();
  if (!r) return <Badge>—</Badge>;
  const ok = r === "APPROVED" || r === "ALLOWED" || r === "SUCCESS";
  return <Badge variant={ok ? "success" : "danger"}>{entry.result}</Badge>;
}
