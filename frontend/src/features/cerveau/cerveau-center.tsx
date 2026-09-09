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
import { useAgentVue, useBrancherSession } from "@/hooks/use-api";
import type {
  AgentListeDTO,
  AgentSessionDTO,
  AgentToolsetDTO,
  AgentProfileDTO,
} from "@/services/client";
import { History, Wrench, Bot, GitBranch, Clock, Split } from "lucide-react";

type Vue = "sessions" | "outils" | "bots" | "delegation" | "routines";

const ONGLETS: { id: Vue; label: string; icone: typeof History }[] = [
  { id: "sessions", label: "Sessions", icone: History },
  { id: "outils", label: "Outils", icone: Wrench },
  { id: "bots", label: "Bots", icone: Bot },
  { id: "delegation", label: "Délégation", icone: GitBranch },
  { id: "routines", label: "Routines", icone: Clock },
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

function horodatage(secondes: number): string {
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

      {isLoading ? (
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

function Sessions({ liste }: { liste: AgentListeDTO<AgentSessionDTO> }) {
  const brancher = useBrancherSession();
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
                    brancher.mutate({
                      cle: s.id,
                      titre: `Branche de ${s.title || s.id}`,
                    })
                  }
                  disabled={brancher.isPending}
                  aria-label={`Brancher la session ${s.title || s.id}`}
                  className="ml-auto flex items-center gap-1 px-1.5 py-0.5 shrink-0
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
  return (
    <Card title="Outils dont le cerveau dispose">
      <div className="flex items-center justify-between pb-2">
        <span className="text-[11px] font-mono text-hermes-muted tabular-nums">
          {actifs} actif{actifs > 1 ? "s" : ""} sur {liste.elements.length}
        </span>
        <Compte liste={liste} />
      </div>
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
                <Badge variant={t.enabled ? "success" : "default"}>
                  {t.enabled ? "actif" : "inactif"}
                </Badge>
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

export default CerveauCenter;
