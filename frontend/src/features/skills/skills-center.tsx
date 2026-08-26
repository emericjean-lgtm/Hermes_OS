"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sparkles, FolderTree, Search } from "lucide-react";
import { Badge } from "@/components/ui/card";
import {
  AsyncPanel, CenterHeader, CenterTabs, DataTable, StatGrid, Toolbar,
} from "@/components/center-scaffold";
import { skillsClient, type AgentSkills } from "@/services/client";

/**
 * Skills Center (HOS-176).
 *
 * Cet écran affichait **zéro compétence**. Il lisait le registre du
 * `SkillDistributor`, qui est vide — mesuré le 2026-08-26 : `GET /skills`
 * rend `count: 0`. Pendant ce temps Hermes Agent en porte **quatre-vingt-une**
 * sur le disque, lues depuis HOS-153 par `backend/skills/registre.py`, et
 * aucune surface ne les montrait.
 *
 * Les deux registres restent distincts, et l'écran le dit : le distributeur
 * décrit ce que Hermes OS *distribuerait*, l'agent porte ce que le cerveau
 * des missions *sait déjà faire*. Les fondre ferait croire le distributeur
 * peuplé — exactement le genre d'illusion que ce projet passe son temps à
 * défaire.
 */

type Onglet = "agent" | "distributeur";

export function SkillsCenter() {
  const [onglet, setOnglet] = useState<Onglet>("agent");
  const [filtre, setFiltre] = useState("");

  const agent = useQuery({
    queryKey: ["skills", "agent"],
    queryFn: () => skillsClient.agentSkills(),
    staleTime: 60_000,
  });

  const distributeur = useQuery({
    queryKey: ["skills", "distributeur"],
    queryFn: () => skillsClient.list(),
    staleTime: 60_000,
  });

  const total = agent.data?.total ?? 0;
  const domaines = agent.data?.domaines ?? [];
  const distribues = distributeur.data?.length ?? 0;

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Skills Center"
        subtitle="Ce que le cerveau des missions sait déjà faire, et ce que Hermes OS distribue"
      />

      <StatGrid
        columns={4}
        stats={[
          { label: "Compétences de l'agent", value: total },
          { label: "Domaines", value: domaines.length },
          {
            label: "Registre du distributeur",
            value: distribues,
            tone: distribues === 0 ? "warn" : "ok",
          },
          {
            label: "Le plus fourni",
            value: domaines.length
              ? [...domaines].sort(
                  (a, b) => b.competences.length - a.competences.length,
                )[0].nom
              : "—",
          },
        ]}
      />

      <div className="mt-6">
        <CenterTabs<Onglet>
          tabs={[
            { id: "agent", label: "Agent", badge: total || undefined },
            {
              id: "distributeur",
              label: "Distributeur",
              badge: distribues || undefined,
            },
          ]}
          active={onglet}
          onChange={setOnglet}
        />
      </div>

      <div className="mt-4">
        {onglet === "agent" ? (
          <OngletAgent
            requete={agent}
            filtre={filtre}
            setFiltre={setFiltre}
          />
        ) : (
          <OngletDistributeur nombre={distribues} requete={distributeur} />
        )}
      </div>
    </div>
  );
}

/* ── Les compétences réelles de l'agent ─────────────────────────────── */

function OngletAgent({
  requete, filtre, setFiltre,
}: {
  requete: ReturnType<typeof useQuery<AgentSkills>>;
  filtre: string;
  setFiltre: (v: string) => void;
}) {
  const domaines = requete.data?.domaines ?? [];

  const lignes = useMemo(() => {
    const q = filtre.trim().toLowerCase();
    return domaines.flatMap((d) =>
      d.competences
        .filter(
          (c) =>
            !q ||
            c.nom.toLowerCase().includes(q) ||
            c.description.toLowerCase().includes(q) ||
            d.nom.toLowerCase().includes(q),
        )
        .map((c) => ({ ...c, domaine: d.nom })),
    );
  }, [domaines, filtre]);

  return (
    <AsyncPanel
      title="Compétences portées par Hermes Agent"
      subtitle={requete.data?.racine ?? "Lues sur le disque, pas déclarées"}
      isLoading={requete.isLoading}
      isError={requete.isError}
      error={requete.error}
      isEmpty={lignes.length === 0}
      emptyLabel={
        filtre
          ? `Aucune compétence ne correspond à « ${filtre} ».`
          : "Aucune compétence trouvée sous le dossier de l'agent."
      }
      action={
        <Toolbar
          search={filtre}
          onSearch={setFiltre}
          placeholder="Filtrer par nom, domaine ou description"
        />
      }
    >
      <DataTable
        rows={lignes}
        rowKey={(r) => `${r.domaine}/${r.nom}`}
        columns={[
          {
            header: "Domaine",
            cell: (r) => (
              <span className="inline-flex items-center gap-1.5">
                <FolderTree size={11} className="text-hermes-dim" />
                <span className="num text-[11px] text-hermes-muted">
                  {r.domaine}
                </span>
              </span>
            ),
          },
          {
            header: "Compétence",
            cell: (r) => (
              <span className="inline-flex items-center gap-1.5">
                <Sparkles size={11} className="text-hermes-sodium" />
                <span className="num text-[11px] text-hermes-text">{r.nom}</span>
              </span>
            ),
          },
          {
            header: "Ce qu'elle fait",
            cell: (r) => (
              <span className="text-[11px] text-hermes-muted">
                {r.description || <span className="text-hermes-dim">—</span>}
              </span>
            ),
          },
        ]}
      />
    </AsyncPanel>
  );
}

/* ── Le distributeur, dit tel qu'il est ─────────────────────────────── */

function OngletDistributeur({
  nombre, requete,
}: {
  nombre: number;
  requete: { isLoading: boolean; isError: boolean; error?: unknown };
}) {
  return (
    <AsyncPanel
      title="Registre du distributeur"
      subtitle="Ce que Hermes OS distribuerait aux agents"
      isLoading={requete.isLoading}
      isError={requete.isError}
      error={requete.error}
      isEmpty={nombre === 0}
      emptyLabel={
        "Ce registre est vide. Il décrit les compétences que Hermes OS " +
        "distribuerait lui-même — un mécanisme distinct de celles que " +
        "l'agent porte déjà, et qui n'a jamais été peuplé. L'onglet Agent " +
        "montre ce qui existe réellement."
      }
    >
      <p className="text-xs text-hermes-muted">
        {nombre} compétence(s) enregistrée(s) côté distributeur.
      </p>
    </AsyncPanel>
  );
}

export default SkillsCenter;
