"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Sparkles, FolderTree, Search, ChevronLeft, ChevronRight,
} from "lucide-react";
import { Badge } from "@/components/ui/card";
import {
  AsyncPanel, CenterHeader, CenterTabs, DataTable, StatGrid, Toolbar,
} from "@/components/center-scaffold";
import { skillsClient, type AgentSkills } from "@/services/client";
import {
  useSkillsCatalogue, useSkillsRecherche, useSkillDetail,
} from "@/hooks/use-api";

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
 *
 * ## Le chiffre de l'onglet Agent était faux (HOS-274)
 *
 * Il annonçait 60 compétences. Le runtime en sert 65, et **40 seulement
 * étaient communes** : `registre.py` lisait `hermes/hermes-agent/skills` —
 * les compétences livrées avec le *dépôt* de l'agent — au lieu du dossier
 * **actif** `hermes/skills`, et il ignorait le champ `platforms:` que
 * chaque `SKILL.md` déclare. Cet écran montrait donc `imessage`, `findmy`
 * et `apple-notes` à un agent Windows qui ne les chargera jamais, tout en
 * taisant 25 compétences qu'il porte vraiment.
 *
 * Corrigé, le disque et la RPC `skills.manage list` concordent exactement.
 * L'onglet Agent reste servi par le disque : lui seul porte les
 * descriptions, et il ne coûte pas un aller-retour de gateway.
 *
 * ## Le catalogue (HOS-274)
 *
 * Troisième registre, distant celui-là : 5493 entrées du hub, mesurées.
 * **Consultation seule.** `skills.manage install` rend `installed: true`
 * sans regarder ce que `do_install` a fait — mesure : un nom qui n'existe
 * nulle part rend `true`, et le même `true` sort quand le scanner de
 * sécurité a BLOQUÉ la pose. Un bouton dessus ferait passer un refus de
 * sécurité pour une réussite.
 */

type Onglet = "agent" | "distributeur" | "catalogue";

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
            { id: "catalogue", label: "Catalogue" },
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
        ) : onglet === "catalogue" ? (
          <OngletCatalogue />
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

/* ── Le hub, consultable et rien de plus ────────────────────────────── */

function OngletCatalogue() {
  const [requete, setRequete] = useState("");
  const [saisie, setSaisie] = useState("");
  const [page, setPage] = useState(1);
  const [ouverte, setOuverte] = useState<string | null>(null);

  // La recherche part vers le hub DISTANT, et chaque appel fait reecrire a
  // l'agent son index de 705 Ko. Cablee directement sur la frappe, « obsidian »
  // en declenchait huit — une par prefixe, chacune une cle React Query
  // distincte, donc aucune n'etait dedupliquee. On attend que la frappe
  // s'arrete.
  useEffect(() => {
    const t = setTimeout(() => {
      setRequete(saisie);
      setOuverte(null);
    }, 400);
    return () => clearTimeout(t);
  }, [saisie]);

  const hub = useSkillsCatalogue(page);
  const trouvees = useSkillsRecherche(requete);
  const enRecherche = requete.trim().length > 0;
  const liste = enRecherche ? trouvees : hub;
  const elements = liste.data?.elements ?? [];

  const sousTitre = enRecherche
    ? `${trouvees.data?.total ?? 0} résultat(s)${
        trouvees.data?.tronque ? ", plafond de 20 atteint" : ""
      }`
    : `${hub.data?.total ?? 0} entrées, page ${hub.data?.page ?? page} sur ${
        hub.data?.pages ?? 0
      }`;

  return (
    <AsyncPanel
      title="Catalogue du hub"
      subtitle={sousTitre}
      isLoading={liste.isLoading}
      isError={liste.isError}
      error={liste.error}
      isEmpty={!liste.isLoading && elements.length === 0}
      emptyLabel={
        liste.data && !liste.data.disponible
          ? `Le cerveau n'a pas répondu : ${liste.data.erreur ?? "cause inconnue"}`
          : "Aucune entrée ne correspond."
      }
      action={
        <div className="flex items-center gap-2">
          <Toolbar
            search={saisie}
            onSearch={setSaisie}
            placeholder="Chercher dans le hub"
          />
          {!enRecherche && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                aria-label="Page précédente"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="border border-hermes-border px-1 py-1
                  text-hermes-muted hover:text-hermes-text
                  disabled:opacity-30 disabled:hover:text-hermes-muted"
              >
                <ChevronLeft size={12} />
              </button>
              <button
                type="button"
                aria-label="Page suivante"
                disabled={page >= (hub.data?.pages ?? 1)}
                onClick={() => setPage((p) => p + 1)}
                className="border border-hermes-border px-1 py-1
                  text-hermes-muted hover:text-hermes-text
                  disabled:opacity-30 disabled:hover:text-hermes-muted"
              >
                <ChevronRight size={12} />
              </button>
            </div>
          )}
        </div>
      }
    >
      <p className="pb-3 text-[11px] text-hermes-dim">
        Consultation seule. Installer depuis le cockpit n'est pas offert :
        le runtime répond « installé » sans vérifier, y compris quand son
        scanner de sécurité a bloqué la pose.
      </p>
      <div className="space-y-1.5">
        {elements.map((e, i) => {
          const nom = e.name ?? e.identifier ?? "";
          return (
            <div key={`${nom}-${i}`}>
              <button
                type="button"
                onClick={() => setOuverte((o) => (o === nom ? null : nom))}
                aria-expanded={ouverte === nom}
                className="w-full text-left border border-hermes-border/60
                  px-2.5 py-2 hover:border-hermes-sodium/45"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="inline-flex items-center gap-1.5">
                    <Sparkles size={11} className="text-hermes-sodium" />
                    <span className="num text-[11px] text-hermes-text">
                      {nom}
                    </span>
                  </span>
                  {e.source && <Badge variant="info">{e.source}</Badge>}
                </div>
                {e.description && (
                  <p className="pt-1 text-[11px] text-hermes-muted line-clamp-2">
                    {e.description}
                  </p>
                )}
              </button>
              {ouverte === nom && <DetailDuHub nom={nom} />}
            </div>
          );
        })}
      </div>
    </AsyncPanel>
  );
}

/** `connu: false` n'est pas une panne : le hub ignore ce nom. */
function DetailDuHub({ nom }: { nom: string }) {
  const { data, isLoading, isError } = useSkillDetail(nom);

  if (isLoading || isError || !data) return null;
  if (!data.disponible) {
    return (
      <p className="border border-t-0 border-hermes-border/60 px-2.5 py-2
        text-[11px] text-hermes-amber">
        {data.erreur ?? "le cerveau n'a pas répondu"}
      </p>
    );
  }
  if (!data.connu) {
    return (
      <p className="border border-t-0 border-hermes-border/60 px-2.5 py-2
        text-[11px] text-hermes-muted">
        Le hub ne connaît pas ce nom. Une compétence installée hors hub tombe
        ici : ce n'est pas une erreur de lecture.
      </p>
    );
  }

  const apercu = data.info["skill_md_preview"];
  const tags = data.info["tags"];
  return (
    <div className="border border-t-0 border-hermes-border/60 px-2.5 py-2
      space-y-1.5">
      {Array.isArray(tags) && tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tags.map((t, i) => (
            <span
              key={`${String(t)}-${i}`}
              className="num text-[10px] text-hermes-glacier
                border border-hermes-glacier/30 px-1.5 py-0.5"
            >
              {String(t)}
            </span>
          ))}
        </div>
      )}
      {typeof apercu === "string" && apercu.trim().length > 0 && (
        <pre className="text-[10px] text-hermes-muted whitespace-pre-wrap
          max-h-[240px] overflow-y-auto">
          {apercu}
        </pre>
      )}
    </div>
  );
}

export default SkillsCenter;
