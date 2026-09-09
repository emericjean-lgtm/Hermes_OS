/**
 * Le Cerveau — ce que Hermes Agent porte reellement (HOS-266).
 *
 * Hermes OS est le systeme d'exploitation ; ce Center est la fenetre sur le
 * processus qu'il heberge. Sessions tenues, outils dont il dispose, profils
 * configures, delegation en cours, routines planifiees — tout vient du
 * gateway JSON-RPC par le pont, mesure et non deduit.
 *
 * **Lecture seule, et c'est un choix.** Reprendre une session ou activer un
 * toolset ecrit dans l'etat de l'agent, et poser ces gestes demanderait de
 * trancher d'abord qui, de Hermes OS ou de l'agent, en est autorite. Tant
 * que la reponse n'est pas ecrite, un bouton qui pretendrait le faire
 * serait un bouton sans backend — exactement ce que la regle anti-orphelin
 * interdit.
 */
import { useState } from "react";
import { motion } from "framer-motion";
import { Card, Badge } from "@/components/ui/card";
import { CenterHeader, PanelLoading } from "@/components/center-scaffold";
import {
  useAgentVue,
  useBrancherSession,
  useHistoriqueSession,
  useRenommerSession,
  useBasculerToolset,
  useAgentPermissions,
} from "@/hooks/use-api";
import type {
  AgentListeDTO,
  AgentSessionDTO,
  AgentToolsetDTO,
  AgentProfileDTO,
} from "@/services/client";
import { PanelLoading as Chargement } from "@/components/center-scaffold";
import {
  History, Wrench, Bot, GitBranch, Clock, Split, BookOpen, Pencil, X,
  ShieldAlert,
} from "lucide-react";

type Vue =
  | "sessions" | "outils" | "bots" | "delegation" | "routines" | "permissions";

const ONGLETS: { id: Vue; label: string; icone: typeof History }[] = [
  { id: "sessions", label: "Sessions", icone: History },
  { id: "outils", label: "Outils", icone: Wrench },
  { id: "bots", label: "Bots", icone: Bot },
  { id: "delegation", label: "Délégation", icone: GitBranch },
  { id: "routines", label: "Routines", icone: Clock },
  { id: "permissions", label: "Permissions", icone: ShieldAlert },
];

/** Une panne du gateway n'est pas « rien à afficher ». */
function Indisponible({ erreur }: { erreur: string | null }) {
  return (
    <div className="py-6 space-y-2">
      <div className="text-[11px] text-hermes-amber font-mono">
        Le cerveau n'a pas répondu.
      </div>
      <div className="text-[11px] text-hermes-muted font-mono break-all">
        {erreur ?? "cause inconnue"}
      </div>
      <div className="text-[10px] text-hermes-dim font-mono">
        C'est une panne, pas une absence : rien n'est mesuré tant qu'elle dure.
      </div>
    </div>
  );
}

function Vide({ quoi }: { quoi: string }) {
  return (
    <div className="flex items-center gap-2 justify-center py-10">
      <span className="text-hermes-dim font-mono">◇</span>
      <span className="text-[11px] text-hermes-muted font-mono">
        Aucun {quoi} enregistré
      </span>
    </div>
  );
}

/** « 100 servis sur 200 » plutôt que « 100 » : un chiffre exact peut mentir. */
function Compte({ liste }: { liste: AgentListeDTO<unknown> }) {
  // `total` est la taille de la page, pas un decompte : le gateway plafonne
  // `session.list` a 200. Dire « sur 200 » presentait ce plafond comme un
  // total — exact et faux. `tronque` dit ce qu'on sait vraiment.
  return (
    <span className="text-[11px] font-mono text-hermes-muted tabular-nums">
      {liste.total}
      {liste.tronque ? " affichées, et il en reste" : ""}
    </span>
  );
}

function horodatage(secondes?: number): string {
  if (!secondes) return "—";
  return new Date(secondes * 1000).toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export function CerveauCenter() {
  const [vue, setVue] = useState<Vue>("sessions");
  const { data, isLoading, isError, error } = useAgentVue();

  return (
    <div className="space-y-4">
      <CenterHeader
        title="Cerveau"
        subtitle="Ce que Hermes Agent porte, mesuré par le pont"
      />

      <div className="flex items-center gap-1.5">
        {ONGLETS.map(({ id, label, icone: Icone }) => (
          <button
            key={id}
            onClick={() => setVue(id)}
            aria-current={vue === id ? "page" : undefined}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-mono
              border clip-corner-sm transition-colors
              ${
                vue === id
                  ? "text-hermes-sodium border-hermes-sodium/45 bg-hermes-sodium/[0.09]"
                  : "text-hermes-muted border-hermes-border hover:text-hermes-text"
              }`}
          >
            <Icone className="w-3 h-3" />
            {label}
          </button>
        ))}
      </div>

      {vue === "permissions" ? (
        <Permissions />
      ) : isLoading ? (
        <Card title="Cerveau">
          <PanelLoading />
        </Card>
      ) : isError ? (
        <Card title="Cerveau">
          <div className="flex items-start gap-2.5 py-4">
            <span className="text-hermes-red text-glow-red font-mono text-sm">⚠</span>
            <div className="text-[11px] text-hermes-muted font-mono break-all">
              {error instanceof Error ? error.message : "Endpoint injoignable"}
            </div>
          </div>
        </Card>
      ) : !data ? null : (
        <>
          {vue === "sessions" && <Sessions liste={data.sessions} />}
          {vue === "outils" && <Outils liste={data.toolsets} />}
          {vue === "bots" && <Bots liste={data.profils} />}
          {vue === "delegation" && <Delegation etat={data.delegation} />}
          {vue === "routines" && <Routines liste={data.routines} />}
        </>
      )}
    </div>
  );
}

/** Le fil d'une session stockee, lu a la demande. */
function Historique({ cle, titre, onFermer }: {
  cle: string; titre: string; onFermer: () => void;
}) {
  const { data, isLoading, isError, error } = useHistoriqueSession(cle);
  const [deplie, setDeplie] = useState<number | null>(null);

  return (
    <div className="mb-3 border border-hermes-sodium/40 bg-hermes-sodium/[0.04]">
      <div className="flex items-center justify-between gap-3 px-2.5 py-2 border-b border-hermes-border/60">
        <span className="text-[11px] font-mono text-hermes-text truncate">
          {titre || cle}
        </span>
        <button
          onClick={onFermer}
          aria-label="Fermer la session"
          className="shrink-0 text-hermes-muted hover:text-hermes-text"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      {isLoading ? (
        <Chargement />
      ) : isError ? (
        <div className="px-2.5 py-3 text-[11px] font-mono text-hermes-alarm break-all">
          {error instanceof Error ? error.message : "Endpoint injoignable"}
        </div>
      ) : !data?.disponible ? (
        <Indisponible erreur={data?.erreur ?? null} />
      ) : !data.elements.length ? (
        <Vide quoi="message" />
      ) : (
        <div className="max-h-[420px] overflow-y-auto divide-y divide-hermes-border/40">
          {/* `row_id` seul ne suffit pas comme cle : un message `tool` n'en
              a pas, et deux d'entre eux collisionnaient sur `undefined` —
              React l'a signale en console, pas l'oeil. */}
          {data.elements.map((m, i) => (
            <div key={`${m.row_id ?? "tool"}-${i}`} className="px-2.5 py-2">
              <div className="flex items-baseline gap-2">
                <Badge variant={m.role === "user" ? "info" : "default"}>
                  {m.role}
                </Badge>
                {m.name && (
                  <span className="text-[10px] font-mono text-hermes-sodium">
                    {m.name}
                  </span>
                )}
                {m.timestamp ? (
                  <span className="text-[10px] font-mono text-hermes-dim tabular-nums">
                    {horodatage(m.timestamp)}
                  </span>
                ) : null}
              </div>
              {m.text ? (
                <div className="pt-1 text-[11px] font-mono text-hermes-text whitespace-pre-wrap break-words">
                  {m.text}
                </div>
              ) : m.args ? (
                <div className="pt-1 text-[10px] font-mono text-hermes-muted whitespace-pre-wrap break-all">
                  {JSON.stringify(m.args).slice(0, 400)}
                </div>
              ) : null}
              {m.reasoning && (
                <button
                  onClick={() =>
                    setDeplie(deplie === m.row_id ? null : m.row_id ?? null)
                  }
                  className="mt-1 text-[10px] font-mono text-hermes-dim hover:text-hermes-muted"
                >
                  {deplie === m.row_id ? "masquer" : "voir"} le raisonnement
                </button>
              )}
              {deplie === m.row_id && m.reasoning && (
                <div className="mt-1 px-2 py-1.5 border-l-2 border-hermes-border text-[10px] font-mono text-hermes-muted whitespace-pre-wrap break-words">
                  {m.reasoning}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Sessions({ liste }: { liste: AgentListeDTO<AgentSessionDTO> }) {
  const brancher = useBrancherSession();
  const renommer = useRenommerSession();
  const [ouverte, setOuverte] = useState<{ cle: string; titre: string } | null>(
    null,
  );
  // Le resultat de la derniere demande, refus compris : un refus du runtime
  // revient en 200 et doit se lire, pas disparaitre.
  const resultat = brancher.data;

  return (
    <Card title="Sessions tenues par le cerveau">
      <div className="flex items-center justify-between pb-2">
        <span className="text-[10px] font-mono text-hermes-dim">
          Brancher demande à l'agent d'écrire dans son propre état — Hermes OS
          n'y touche pas.
        </span>
        <Compte liste={liste} />
      </div>
      {resultat && (
        <div
          className={`mb-2 px-2.5 py-2 border text-[10px] font-mono ${
            resultat.applique
              ? "border-hermes-arc/45 text-hermes-arc bg-hermes-arc/[0.07]"
              : "border-hermes-gold/45 text-hermes-gold bg-hermes-gold/[0.07]"
          }`}
        >
          {resultat.applique
            ? `Branche créée : ${resultat.titre} (${resultat.cle_stockee}) — ${resultat.messages} message(s) repris du parent ${resultat.parent}.`
            : `Refus du runtime : ${resultat.erreur}`}
        </div>
      )}
      {brancher.isError && (
        <div className="mb-2 px-2.5 py-2 border border-hermes-alarm/45 text-[10px] font-mono text-hermes-alarm">
          La demande n'a pas abouti :{" "}
          {brancher.error instanceof Error
            ? brancher.error.message
            : "transport injoignable"}
        </div>
      )}
      {renommer.data && !renommer.data.applique && (
        <div className="mb-2 px-2.5 py-2 border border-hermes-gold/45 text-[10px] font-mono text-hermes-gold">
          Renommage refusé : {renommer.data.erreur}
        </div>
      )}
      {ouverte && (
        <Historique
          cle={ouverte.cle}
          titre={ouverte.titre}
          onFermer={() => setOuverte(null)}
        />
      )}
      {!liste.disponible ? (
        <Indisponible erreur={liste.erreur} />
      ) : !liste.elements.length ? (
        <Vide quoi="session" />
      ) : (
        <div className="space-y-1.5 max-h-[520px] overflow-y-auto">
          {liste.elements.map((s, i) => (
            <motion.div
              key={s.id}
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.01, 0.25) }}
              className="border border-hermes-border/60 px-2.5 py-2"
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[11px] font-mono text-hermes-text truncate">
                  {s.title || "(sans titre)"}
                </span>
                <span className="text-[10px] font-mono text-hermes-dim shrink-0 tabular-nums">
                  {horodatage(s.started_at)}
                </span>
              </div>
              <div className="text-[10px] font-mono text-hermes-muted truncate">
                {s.preview}
              </div>
              <div className="flex items-center gap-2 pt-1">
                <Badge variant="default">{s.source}</Badge>
                <span className="text-[10px] font-mono text-hermes-dim tabular-nums">
                  {s.message_count} message{s.message_count > 1 ? "s" : ""}
                </span>
                <span className="text-[10px] font-mono text-hermes-dim truncate">
                  {s.id}
                </span>
                <button
                  onClick={() =>
                    setOuverte({ cle: s.id, titre: s.title })
                  }
                  aria-label={`Lire la session ${s.title || s.id}`}
                  className="ml-auto flex items-center gap-1 px-1.5 py-0.5 shrink-0
                    text-[10px] font-mono border border-hermes-border
                    text-hermes-muted hover:text-hermes-sodium
                    hover:border-hermes-sodium/45"
                >
                  <BookOpen className="w-2.5 h-2.5" />
                  Lire
                </button>
                <button
                  onClick={() => {
                    const titre = window.prompt(
                      "Nouveau titre de la session", s.title || "");
                    if (titre && titre.trim()) {
                      renommer.mutate({ cle: s.id, titre: titre.trim() });
                    }
                  }}
                  disabled={renommer.isPending}
                  aria-label={`Renommer la session ${s.title || s.id}`}
                  className="flex items-center gap-1 px-1.5 py-0.5 shrink-0
                    text-[10px] font-mono border border-hermes-border
                    text-hermes-muted hover:text-hermes-sodium
                    hover:border-hermes-sodium/45 disabled:opacity-50"
                >
                  <Pencil className="w-2.5 h-2.5" />
                  {renommer.isPending ? "…" : "Renommer"}
                </button>
                <button
                  onClick={() =>
                    brancher.mutate({
                      cle: s.id,
                      titre: `Branche de ${s.title || s.id}`,
                    })
                  }
                  disabled={brancher.isPending}
                  aria-label={`Brancher la session ${s.title || s.id}`}
                  className="flex items-center gap-1 px-1.5 py-0.5 shrink-0
                    text-[10px] font-mono border border-hermes-border
                    text-hermes-muted hover:text-hermes-sodium
                    hover:border-hermes-sodium/45 disabled:opacity-50"
                >
                  <Split className="w-2.5 h-2.5" />
                  {brancher.isPending ? "…" : "Brancher"}
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </Card>
  );
}

function Outils({ liste }: { liste: AgentListeDTO<AgentToolsetDTO> }) {
  const actifs = liste.elements.filter((t) => t.enabled).length;
  const basculer = useBasculerToolset();
  return (
    <Card title="Outils dont le cerveau dispose">
      <div className="flex items-center justify-between pb-2">
        <span className="text-[11px] font-mono text-hermes-muted tabular-nums">
          {actifs} actif{actifs > 1 ? "s" : ""} sur {liste.elements.length}
        </span>
        <Compte liste={liste} />
      </div>
      <div className="pb-2 text-[10px] font-mono text-hermes-dim">
        Activer ou désactiver écrit la configuration de l'agent : l'effet
        porte sur les missions, pas seulement sur cet écran.
      </div>
      {basculer.data && !basculer.data.applique && (
        <div className="mb-2 px-2.5 py-2 border border-hermes-gold/45 text-[10px] font-mono text-hermes-gold">
          Refusé : {basculer.data.erreur}
        </div>
      )}
      {!liste.disponible ? (
        <Indisponible erreur={liste.erreur} />
      ) : !liste.elements.length ? (
        <Vide quoi="toolset" />
      ) : (
        <div className="grid grid-cols-2 gap-1.5 max-h-[520px] overflow-y-auto">
          {liste.elements.map((t) => (
            <div
              key={t.name}
              className="flex items-start justify-between gap-2 border border-hermes-border/60 px-2.5 py-2"
            >
              <div className="min-w-0">
                <div className="text-[11px] font-mono text-hermes-text truncate">
                  {t.name}
                </div>
                <div className="text-[10px] font-mono text-hermes-dim truncate">
                  {t.description}
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="text-[10px] font-mono text-hermes-muted tabular-nums">
                  {t.tool_count}
                </span>
                <button
                  onClick={() =>
                    basculer.mutate({ nom: t.name, actif: !t.enabled })
                  }
                  disabled={basculer.isPending}
                  aria-label={`${t.enabled ? "Désactiver" : "Activer"} le toolset ${t.name}`}
                  title={t.enabled ? "Désactiver" : "Activer"}
                  className="disabled:opacity-50"
                >
                  <Badge variant={t.enabled ? "success" : "default"}>
                    {t.enabled ? "actif" : "inactif"}
                  </Badge>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function Bots({ liste }: { liste: AgentListeDTO<AgentProfileDTO> }) {
  return (
    <Card title="Bots (profils du cerveau)">
      <div className="flex justify-end pb-2">
        <Compte liste={liste} />
      </div>
      {!liste.disponible ? (
        <Indisponible erreur={liste.erreur} />
      ) : !liste.elements.length ? (
        <Vide quoi="profil" />
      ) : (
        <div className="space-y-1.5">
          {liste.elements.map((p) => (
            <div
              key={p.name}
              className="border border-hermes-border/60 px-2.5 py-2"
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[11px] font-mono text-hermes-text truncate">
                  {p.display_name || p.name}
                </span>
                {p.is_default && <Badge variant="info">défaut</Badge>}
              </div>
              <div className="text-[10px] font-mono text-hermes-muted truncate">
                {p.description || "aucune description"}
              </div>
              <div className="flex items-center gap-2 pt-1 text-[10px] font-mono text-hermes-dim">
                <span className="truncate">{p.model}</span>
                <span>·</span>
                <span>{p.provider}</span>
                <span>·</span>
                <span className="tabular-nums">{p.skill_count} skills</span>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="pt-3 text-[10px] font-mono text-hermes-dim">
        Créer et configurer un Bot écrit dans l'état de l'agent : la
        surface reste en lecture tant que l'autorité sur cet état n'est pas
        tranchée.
      </div>
    </Card>
  );
}

function Delegation({
  etat,
}: {
  etat: {
    disponible: boolean;
    erreur: string | null;
    actifs: unknown[];
    en_pause: boolean | null;
    profondeur_max: number | null;
    enfants_max: number | null;
  };
}) {
  return (
    <Card title="Délégation">
      {!etat.disponible ? (
        <Indisponible erreur={etat.erreur} />
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-4 gap-2">
            <Mesure label="Subagents actifs" valeur={etat.actifs.length} />
            <Mesure
              label="En pause"
              valeur={etat.en_pause === null ? "—" : etat.en_pause ? "oui" : "non"}
            />
            <Mesure label="Profondeur max" valeur={etat.profondeur_max ?? "—"} />
            <Mesure label="Enfants max" valeur={etat.enfants_max ?? "—"} />
          </div>
          {!etat.actifs.length && <Vide quoi="subagent actif" />}
          <div className="text-[10px] font-mono text-hermes-dim">
            Le pont sait piloter un subagent (steer, interrupt) mais pas en
            lancer un : <code>subagent.start</code> n'existe pas dans ce
            runtime. Un subagent naît de l'agent lui-même.
          </div>
        </div>
      )}
    </Card>
  );
}

function Mesure({ label, valeur }: { label: string; valeur: React.ReactNode }) {
  return (
    <div className="border border-hermes-border/60 px-2.5 py-2">
      <div className="text-[9.5px] font-mono uppercase tracking-[0.11em] text-hermes-dim">
        {label}
      </div>
      <div className="text-[15px] font-mono text-hermes-text tabular-nums">
        {valeur}
      </div>
    </div>
  );
}

function Routines({ liste }: { liste: AgentListeDTO<Record<string, unknown>> }) {
  return (
    <Card title="Routines planifiées">
      <div className="flex justify-end pb-2">
        <Compte liste={liste} />
      </div>
      {!liste.disponible ? (
        <Indisponible erreur={liste.erreur} />
      ) : !liste.elements.length ? (
        <Vide quoi="routine" />
      ) : (
        <div className="space-y-1.5">
          {liste.elements.map((r, i) => (
            <div
              key={String(r.id ?? r.name ?? i)}
              className="border border-hermes-border/60 px-2.5 py-2"
            >
              <div className="text-[11px] font-mono text-hermes-text truncate">
                {String(r.name ?? r.id ?? "(sans nom)")}
              </div>
              <div className="text-[10px] font-mono text-hermes-dim truncate">
                {String(r.schedule ?? r.cron ?? "")}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

/** Ce que Hermes OS a répondu quand l'agent a demandé à écrire. */
function Permissions() {
  const { data, isLoading, isError, error } = useAgentPermissions();

  const libelle: Record<string, { texte: string; ton: "success" | "warning" | "danger" }> = {
    accordee: { texte: "accordée", ton: "success" },
    refusee_hors_workspace: { texte: "hors workspace", ton: "danger" },
    refusee_protege: { texte: "fichier protégé", ton: "danger" },
    sans_option: { texte: "aucune option", ton: "warning" },
  };

  return (
    <Card title="Décisions d'écriture demandées par le cerveau">
      {isLoading ? (
        <Chargement />
      ) : isError ? (
        <div className="py-4 text-[11px] font-mono text-hermes-alarm break-all">
          {error instanceof Error ? error.message : "Endpoint injoignable"}
        </div>
      ) : !data ? null : (
        <>
          <div className="flex items-center justify-between pb-2">
            <span className="text-[11px] font-mono text-hermes-muted tabular-nums">
              {data.refus} refus sur {data.total} décision
              {data.total > 1 ? "s" : ""}
            </span>
            <span className="text-[10px] font-mono text-hermes-dim">
              fenêtre de {data.borne}
              {data.tronque ? ", et il en reste" : ""}
            </span>
          </div>
          <div className="pb-2 text-[10px] font-mono text-hermes-dim">
            Un refus ne prouve pas qu'une écriture a été empêchée : le
            terminal de l'agent ne demande aucune permission et peut
            réessayer par là.
          </div>
          {!data.elements.length ? (
            <Vide quoi="décision" />
          ) : (
            <div className="space-y-1.5 max-h-[520px] overflow-y-auto">
              {data.elements.map((d, i) => {
                const l = libelle[d.issue] ?? {
                  texte: d.issue, ton: "warning" as const,
                };
                return (
                  <div
                    key={`${d.quand}-${i}`}
                    className="border border-hermes-border/60 px-2.5 py-2"
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-[11px] font-mono text-hermes-text truncate">
                        {d.chemin}
                      </span>
                      <Badge variant={l.ton}>{l.texte}</Badge>
                    </div>
                    <div className="text-[10px] font-mono text-hermes-muted truncate">
                      {d.detail}
                    </div>
                    <div className="text-[10px] font-mono text-hermes-dim tabular-nums">
                      {horodatage(d.quand)}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

export default CerveauCenter;
