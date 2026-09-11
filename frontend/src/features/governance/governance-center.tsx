"use client";

import { useState } from "react";
import {
  useApprovals,
  useApproveAction,
  useAuditLog,
  useAutonomy,
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
import type { AuditEntry, EntreeJournal } from "@/types/hermes";
import type { CategorieAegis } from "@/services/client";

/* ═══════════════════════════════════════════════════════════════════
   Governance Center — fusion de Governance et Policy.

   Les deux écrans consommaient exactement les mêmes hooks et donc les
   mêmes trois endpoints : ils affichaient les mêmes données sous deux
   noms, avec deux mises en page qui divergeaient à chaque évolution.

   **G-36 puis G-37 ont changé les trois sources, pas la mise en page.**
   Les trois endpoints d'origine venaient de `backend/policy/` (HOS-046),
   et aucun des trois ne décrivait quoi que ce soit :

     approbations  file en mémoire sans producteur  -> file d'Aegis (SQLite)
     règles        dix règles qu'aucun chemin        -> matrice Aegis, celle
                   n'évalue, et qui contredisent        qu'`AegisEngine` relit
                   la politique en vigueur              à chaque évaluation
     audit         anneau en mémoire, 0 entrée       -> journal du §18
                                                        (SQLite + fichiers)

   Le défaut n'était pas une surface manquante : c'était un consommateur
   branché sur la mauvaise source. Ni le compteur d'orphelins ni le typage
   ne pouvaient le voir, puisque les deux surfaces existaient.

   La fusion garde le meilleur des deux : l'architecture de Policy
   (briques du scaffold, recherche, filtres par catégorie, remontée
   d'erreur de décision) et le rendu de Governance (journal d'audit en
   colonnes plutôt qu'en JSON brut, règles avec état activé/désactivé et
   description, métadonnées de demande d'approbation).
   ═══════════════════════════════════════════════════════════════════ */

type Tab = "approvals" | "rules" | "audit";

export function GovernanceCenter() {
  // G-37 : `usePolicyRules` sert les dix regles de `backend/policy/`.
  // Mesure du 2026-09-11 : elles ne sont evaluees NULLE PART —
  // `set_policy_engine` n'est jamais appele, et les trois evenements que
  // le `ServiceSpec` declare produire (`approval.requested`,
  // `approval.granted`, `audit.created`) comptent zero occurrence sur le
  // bus durable. Pire, deux d'entre elles contredisent la politique en
  // vigueur : `internet_access_allowed: allow` contre `network_call` qui
  // exige « high », et `system_modification_denied: deny` contre
  // `system_config` qui demande un humain.
  //
  // L'ecran montre desormais la matrice qu'`AegisEngine` relit a chaque
  // evaluation. Meme responsabilite — « quelle politique s'applique » —
  // et une seule autorite.
  const autonomie = useAutonomy();
  const approvals = useApprovals();
  const audit = useAuditLog();
  const approve = useApproveAction();
  const reject = useRejectAction();

  const [tab, setTab] = useState<Tab>("approvals");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("Tous");
  const [lastError, setLastError] = useState<string | null>(null);

  const categories = autonomie.data?.categories ?? [];
  const allAudit = audit.data ?? [];
  const filtres = ["Tous", "humain", "autorise"];

  const visibleRules = categories.filter((c) => {
    const hay = `${c.nom} ${c.effet_courant}`.toLowerCase();
    if (search && !hay.includes(search.toLowerCase())) return false;
    return filter === "Tous" || c.effet_courant === filter;
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
          { label: "Catégories d'action", value: categories.length },
          {
            label: "Toujours humain",
            value: categories.filter((c) => c.mandatory_validation).length,
          },
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
            placeholder="Rechercher une catégorie d'action…"
            filters={filtres}
            activeFilter={filter}
            onFilter={setFilter}
          />
          <AsyncPanel
            title="Politique en vigueur"
            subtitle={
              `${visibleRules.length} catégorie(s) sur ${categories.length} — ` +
              `niveau d'autonomie « ${autonomie.data?.level ?? "?"} »` +
              `${autonomie.data?.overridden ? " (dérogation d'exécution)" : ""}`
            }
            isLoading={autonomie.isLoading}
            isError={autonomie.isError}
            error={autonomie.error}
            isEmpty={visibleRules.length === 0}
            emptyLabel={
              categories.length === 0
                ? "La matrice Aegis n'a pas été servie."
                : "Aucune catégorie ne correspond à ce filtre."
            }
          >
            <p className="pb-3 text-[10px] text-hermes-dim">
              Ce que chaque catégorie d&apos;action donne au niveau courant.
              Les catégories « toujours humain » ne se contournent à aucun
              niveau (§17.3) : monter le curseur ne les supprime pas.
            </p>
            <div className="flex flex-col gap-1.5">
              {visibleRules.map((c) => (
                <CategorieRow key={c.nom} c={c} />
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
            subtitle={`${visibleAudit.length} entrée(s) — /api/v1/logs (journal §18)`}
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
                    e.timestamp ? new Date(e.timestamp).toLocaleString() : "—",
                },
                { header: "Agent", cell: (e) => e.agent || "—" },
                {
                  header: "Demande",
                  cell: (e) => (
                    <span className="text-[11px] text-hermes-muted" title={e.request ?? ""}>
                      {(e.request ?? "—").slice(0, 70)}
                    </span>
                  ),
                },
                {
                  header: "Modèle choisi",
                  cell: (e) => (
                    <span
                      className="num text-[10px] text-hermes-glacier"
                      title={String(
                        (e.routing_decision as { reason?: string } | null)?.reason ?? "",
                      )}
                    >
                      {String(
                        (e.routing_decision as { model_selected?: string } | null)
                          ?.model_selected ?? "—",
                      )}
                    </span>
                  ),
                },
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

/**
 * Une catégorie de la matrice Aegis — la politique réellement appliquée.
 *
 * Remplace `RuleRow`, qui rendait une règle de `backend/policy/` : dix
 * règles qu'aucun chemin n'évalue, et dont deux contredisent celle-ci.
 * Ce composant ne calcule pas l'effet : il l'affiche. Le recalculer ici
 * ferait diverger l'écran du moteur au premier changement de seuil.
 */
function CategorieRow({ c }: { c: CategorieAegis }) {
  const humain = c.effet_courant === "humain";
  return (
    <div
      className="flex items-center justify-between gap-4 p-2.5 clip-corner-sm
        bg-hermes-bg-deep/50 border border-hermes-border/50"
    >
      <span className="min-w-0 flex items-center gap-2">
        <span className="num text-[11.5px] text-hermes-text truncate">{c.nom}</span>
        {c.mandatory_validation && (
          <Badge variant="danger">toujours humain</Badge>
        )}
        {!c.mutating && <Badge variant="success">lecture seule</Badge>}
      </span>
      <span className="flex items-center gap-2 shrink-0">
        {c.min_autonomy_for_auto_allow && !c.mandatory_validation && (
          <span className="num text-[10px] text-hermes-dim">
            auto dès « {c.min_autonomy_for_auto_allow} »
          </span>
        )}
        <Badge variant={humain ? "warning" : "success"}>
          {humain ? "humain" : "autorisé"}
        </Badge>
      </span>
    </div>
  );
}

function ResultBadge({ entry }: { entry: EntreeJournal | AuditEntry }) {
  // G-37 : la forme vient desormais du journal du §18, ou `result` vaut
  // « success » / « failed ». Les valeurs de l'anneau de `backend/policy/`
  // (`APPROVED`, `ALLOWED`) sont conservees dans la comparaison : elles ne
  // couteraient rien a garder et leur retrait ne prouverait rien.
  const r = String(entry.result ?? "").toUpperCase();
  if (!r) return <Badge>—</Badge>;
  const ok = r === "APPROVED" || r === "ALLOWED" || r === "SUCCESS";
  return <Badge variant={ok ? "success" : "danger"}>{entry.result}</Badge>;
}
