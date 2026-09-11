"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Sparkles, FolderTree, Search, ChevronLeft, ChevronRight, GitBranch, Unlink,
  ShieldCheck, ShieldAlert, FileWarning,
} from "lucide-react";
import { Badge } from "@/components/ui/card";
import {
  AsyncPanel, CenterHeader, CenterTabs, DataTable, StatGrid, Toolbar,
} from "@/components/center-scaffold";
import {
  skillsClient, type AgentSkills, type SkillProvenance,
  type ObservationsSkills, type MutationObservee, type RaisonSansRun,
  type GouvernanceSkills, type SkillPosee, type EtatPosee,
  type ResultatInstallation, type StatutInstallation,
} from "@/services/client";
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

type Onglet = "agent" | "runs" | "gouvernance" | "distributeur" | "catalogue";

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

  // Le dossier du cycle de vie tenu par le hub de l'agent, verifie
  // (G-35). Troisieme population : ni l'inventaire, ni les mutations d'un
  // Run — les operations d'installation, avec leur controle de securite.
  const gouvernance = useQuery({
    queryKey: ["skills", "gouvernance"],
    queryFn: () => skillsClient.gouvernance(),
    staleTime: 30_000,
  });

  // Les mutations observees, et le Run qui les a demandees (G-34). Requete
  // separee de l'inventaire : deux populations distinctes, deux couts —
  // celle-ci rejoue le bus, l'autre marche l'arbre des competences.
  const observations = useQuery({
    queryKey: ["skills", "observations"],
    queryFn: () => skillsClient.observations(),
    staleTime: 30_000,
  });

  const total = agent.data?.total ?? 0;
  const domaines = agent.data?.domaines ?? [];
  const distribues = distributeur.data?.length ?? 0;
  const runsObserves = observations.data?.runs.length ?? 0;
  const alertes = gouvernance.data?.alertes;
  const aSignaler = (alertes?.alterees ?? 0) + (alertes?.absentes ?? 0);

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
              id: "runs",
              label: "Runs ↔ Skills",
              badge: runsObserves || undefined,
            },
            {
              id: "gouvernance",
              label: "Gouvernance",
              badge: aSignaler || undefined,
            },
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
        ) : onglet === "runs" ? (
          <OngletRuns requete={observations} />
        ) : onglet === "gouvernance" ? (
          <OngletGouvernance requete={gouvernance} />
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
          {
            header: "D'où elle vient",
            cell: (r) => <EtiquetteProvenance competence={r} />,
          },
        ]}
      />
      {/* Cette phrase disait « aucune compétence n'est rattachée à un
          Run ». G-33 l'a périmée sans que rien ne rougisse, parce qu'elle
          était une affirmation d'écran et non une lecture de donnée. Elle
          dit désormais ce qui est vrai de CET inventaire — aucun fichier de
          compétence installée ne nomme un Run — et renvoie à l'onglet où la
          relation existe réellement. */}
      <p className="pt-3 text-[10px] text-hermes-dim">
        Cet inventaire ne porte aucun Run : {requete.data
          ?.correlation_impossible ?? "corrélation non mesurée"}. Les
        mutations observées, elles, sont rattachées — onglet{" "}
        <span className="text-hermes-muted">Runs ↔ Skills</span>.
      </p>
    </AsyncPanel>
  );
}

/**
 * Une categorie de provenance, et la preuve en infobulle.
 *
 * Mesure G-27 du 2026-09-10 sur cette installation : 60 systeme intactes,
 * 4 generees par l'agent, 1 conflit. Les categories viennent des fichiers de
 * l'agent — `.bundled_manifest` (avec verification d'empreinte),
 * `.hub/lock.json`, `.usage.json` — jamais d'une deduction.
 */
function EtiquetteProvenance({
  competence,
}: {
  competence: {
    provenance: SkillProvenance;
    provenance_preuve: string;
    provenance_conflit?: string[];
  };
}) {
  const table: Record<
    SkillProvenance,
    { texte: string; ton: "success" | "warning" | "danger" | "info" }
  > = {
    systeme_intacte: { texte: "système, intacte", ton: "success" },
    systeme_modifiee: { texte: "système, modifiée", ton: "warning" },
    posee_par_le_hub: { texte: "posée par le hub", ton: "info" },
    generee_par_l_agent: { texte: "générée par l'agent", ton: "info" },
    sans_marqueur: { texte: "sans marqueur", ton: "warning" },
    conflit: { texte: "provenance en conflit", ton: "danger" },
    inconnue: { texte: "inconnue", ton: "warning" },
  };
  const l = table[competence.provenance] ?? {
    texte: competence.provenance,
    ton: "warning" as const,
  };
  const conflit = competence.provenance_conflit;
  return (
    <span
      className="inline-flex items-center gap-1.5"
      title={
        conflit
          ? `${competence.provenance_preuve} — created_by ${conflit.join(" / ")}`
          : competence.provenance_preuve
      }
    >
      <Badge variant={l.ton}>{l.texte}</Badge>
    </span>
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
        Consultation seule. Le runtime répond « installé » sans vérifier,
        y compris quand son scanner a bloqué la pose : un bouton ici ferait
        passer un refus de sécurité pour une réussite. La pose se demande
        par identifiant dans l'onglet Gouvernance, sous l'autorité d'Aegis,
        et son résultat y est vérifié sur le disque.
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

/* -- Quel Run a mute quelle Skill --------------------------------- */

/**
 * La premiere surface produit de la relation Run <-> Skill (G-34, HOS-282).
 *
 * Trois proprietaires, et l'ecran n'en est aucun : la mutation vient de
 * l'observateur installe chez l'agent, la relation `turnId -> run` du bus
 * durable de Hermes OS, et ce qu'*est* le Run du Run Ledger. Cet ecran ne
 * fait que les mettre cote a cote.
 *
 * ## Ce qu'il ne fait jamais
 *
 * Il ne complete pas. Une mutation sans Run reste sans Run, et va dans son
 * propre bloc avec sa cause -- jamais dans un Run << inconnu >>, qui se
 * lirait comme un vrai et finirait affiche a cote d'eux. Un Run absent du
 * Ledger affiche son identifiant seul plutot qu'un objectif emprunte au
 * voisin.
 *
 * ## Deux vues, une seule donnee
 *
 * << Par Run >> et << Par Skill >> sont deux lectures de `runs` -- la
 * seconde est un pivot, pas une seconde requete. C'est ce qui rend visible
 * qu'un meme Skill a servi a plusieurs Runs sans qu'aucune ligne ne soit
 * dupliquee dans la donnee.
 */
function OngletRuns({
  requete,
}: {
  requete: ReturnType<typeof useQuery<ObservationsSkills>>;
}) {
  const [vue, setVue] = useState<"run" | "skill">("run");
  const d = requete.data;
  const runs = d?.runs ?? [];
  const orphelines = d?.non_rattachees ?? [];

  // Le pivot : un Skill, les Runs qui l'ont mute. Derive de `runs`, donc
  // incapable de nommer un Run que la donnee ne porte pas.
  const parSkill = useMemo(() => {
    const table = new Map<string, { run: string; m: MutationObservee }[]>();
    for (const r of runs) {
      for (const m of r.skills) {
        const liste = table.get(m.skill) ?? [];
        liste.push({ run: r.run, m });
        table.set(m.skill, liste);
      }
    }
    return [...table.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [runs]);

  return (
    <AsyncPanel
      title="Ce que chaque Run a fait des Skills"
      subtitle={
        d
          ? `${d.observees} mutation(s) observee(s) \u00b7 retention ${d.retention_jours} jours`
          : "Observees chez l'agent, rattachees par Hermes OS"
      }
      isLoading={requete.isLoading}
      isError={requete.isError}
      error={requete.error}
      isEmpty={runs.length === 0 && orphelines.length === 0}
      emptyLabel={
        d && !d.etat_lisible
          ? "Aucune observation. L'observateur n'est pas installe, pas active, " +
            "ou n'a rien vu \u2014 trois situations que Hermes OS ne distingue " +
            "pas d'ici. Ce n'est pas \u00ab aucune mutation \u00bb."
          : "Aucune mutation de Skill observee pendant la periode de retention."
      }
      action={
        <div className="flex items-center gap-1.5">
          {(["run", "skill"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setVue(v)}
              className={`num text-[10px] uppercase tracking-[0.11em] px-2 py-1
                border clip-corner-sm transition-colors ${
                  vue === v
                    ? "text-hermes-sodium border-hermes-sodium/45 bg-hermes-sodium/[0.09]"
                    : "text-hermes-dim border-hermes-border/60 hover:text-hermes-muted"
                }`}
            >
              {v === "run" ? "Par Run" : "Par Skill"}
            </button>
          ))}
        </div>
      }
    >
      {d && !d.registre_lisible && runs.length > 0 && (
        <p className="mb-3 text-[10px] text-hermes-amber">
          Le Run Ledger n&apos;a pas pu etre lu : les Runs sont montres par
          leur seul identifiant. Ce n&apos;est pas &laquo;&nbsp;ces Runs sont
          inconnus&nbsp;&raquo;.
        </p>
      )}

      {vue === "run" ? (
        <div className="space-y-3">
          {runs.map((r) => (
            <div
              key={r.run}
              className="border border-hermes-border/60 clip-corner-sm p-3"
            >
              <div className="flex items-baseline justify-between gap-3 mb-2">
                <span className="inline-flex items-center gap-1.5">
                  <GitBranch size={11} className="text-hermes-glacier" />
                  <span className="num text-[11px] text-hermes-text">{r.run}</span>
                </span>
                {r.detail ? (
                  <span className="flex items-center gap-2">
                    <Badge variant="info">{r.detail.statut}</Badge>
                    <span className="text-[10px] text-hermes-muted">
                      {r.detail.objectif || r.detail.mission || "\u2014"}
                    </span>
                  </span>
                ) : d?.registre_lisible ? (
                  <span className="text-[10px] text-hermes-dim">
                    absent du Run Ledger
                  </span>
                ) : null}
              </div>
              <DataTable
                rows={r.skills}
                rowKey={(m, i) => `${r.run}/${m.turn_id}/${m.skill}/${i}`}
                columns={colonnesMutation}
              />
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {parSkill.map(([skill, occurrences]) => (
            <div
              key={skill}
              className="border border-hermes-border/60 clip-corner-sm p-3"
            >
              <div className="flex items-baseline justify-between gap-3 mb-2">
                <span className="inline-flex items-center gap-1.5">
                  <Sparkles size={11} className="text-hermes-sodium" />
                  <span className="num text-[11px] text-hermes-text">{skill}</span>
                </span>
                <span className="num text-[10px] text-hermes-dim">
                  {occurrences.length} mutation(s) {"\u00b7"}{" "}
                  {new Set(occurrences.map((o) => o.run)).size} Run(s)
                </span>
              </div>
              <DataTable
                rows={occurrences}
                rowKey={(o, i) => `${skill}/${o.run}/${i}`}
                columns={[
                  {
                    header: "Run",
                    cell: (o) => (
                      <span className="num text-[11px] text-hermes-glacier">
                        {o.run}
                      </span>
                    ),
                  },
                  {
                    header: "Action",
                    cell: (o) => (
                      <Badge variant="info">{o.m.action || "\u2014"}</Badge>
                    ),
                  },
                  {
                    header: "Tour",
                    cell: (o) => <Etiquette valeur={o.m.turn_id} />,
                  },
                  {
                    header: "Observee",
                    cell: (o) => <Horodatage v={o.m.observe_a} />,
                  },
                ]}
              />
            </div>
          ))}
        </div>
      )}

      {orphelines.length > 0 && (
        <div className="mt-5 pt-4 border-t border-hermes-border/60">
          <div className="flex items-center gap-1.5 mb-2">
            <Unlink size={11} className="text-hermes-dim" />
            <span className="num text-[10px] uppercase tracking-[0.11em] text-hermes-muted">
              Mutations sans Run ({orphelines.length})
            </span>
          </div>
          <p className="mb-2 text-[10px] text-hermes-dim">
            Elles sont montrees a part, jamais rangees sous un Run
            &laquo;&nbsp;inconnu&nbsp;&raquo; : une telle cle se lirait comme
            un vrai Run.
          </p>
          <DataTable
            rows={orphelines}
            rowKey={(m, i) => `orpheline/${m.skill}/${i}`}
            columns={[
              ...colonnesMutation,
              {
                header: "Pourquoi aucun Run",
                cell: (m: MutationObservee & { raison: RaisonSansRun }) => (
                  <RaisonAbsence raison={m.raison} />
                ),
              },
            ]}
          />
        </div>
      )}
    </AsyncPanel>
  );
}

const colonnesMutation = [
  {
    header: "Competence",
    cell: (m: MutationObservee) => (
      <span className="inline-flex items-center gap-1.5">
        <Sparkles size={11} className="text-hermes-sodium" />
        <span className="num text-[11px] text-hermes-text">
          {m.skill || "\u2014"}
        </span>
      </span>
    ),
  },
  {
    header: "Action",
    cell: (m: MutationObservee) => (
      <Badge variant="info">{m.action || "\u2014"}</Badge>
    ),
  },
  {
    header: "Tour",
    cell: (m: MutationObservee) => <Etiquette valeur={m.turn_id} />,
  },
  {
    header: "Observee",
    cell: (m: MutationObservee) => <Horodatage v={m.observe_a} />,
  },
];

/** L'etiquette de tour, tronquee. Un `uuid4` entier mange la colonne, et
 *  l'entier reste en infobulle pour qui veut la recouper avec le bus. */
function Etiquette({ valeur }: { valeur: string }) {
  if (!valeur) return <span className="text-hermes-dim">absente</span>;
  return (
    <span className="num text-[10px] text-hermes-muted" title={valeur}>
      {valeur.slice(0, 12)}
      {"\u2026"}
    </span>
  );
}

function Horodatage({ v }: { v: number }) {
  if (!v) return <span className="text-hermes-dim">{"\u2014"}</span>;
  return (
    <span className="num text-[10px] text-hermes-muted">
      {new Date(v * 1000).toLocaleString()}
    </span>
  );
}

/** Les deux causes bornees par le backend. L'ecran ne les paraphrase pas :
 *  il les traduit, et n'en invente pas une troisieme. */
function RaisonAbsence({ raison }: { raison: RaisonSansRun }) {
  const table: Record<RaisonSansRun, { texte: string; titre: string }> = {
    sans_etiquette: {
      texte: "aucune etiquette",
      titre:
        "Le tour ne portait pas de turnId : hors Run (le chat), ou un agent " +
        "sans le contrat G-31.",
    },
    etiquette_non_resolue: {
      texte: "etiquette non resolue",
      titre:
        "Une etiquette existe, mais Hermes OS n'a pas la relation : jamais " +
        "frappee ici, ou elaguee par les sept jours de retention du bus.",
    },
  };
  const l = table[raison];
  if (!l) return <span className="text-hermes-dim">{raison}</span>;
  return (
    <span title={l.titre}>
      <Badge variant="warning">{l.texte}</Badge>
    </span>
  );
}

/* -- Le cycle de vie, verifie ------------------------------------- */

/**
 * Ce que le cycle de vie des Skills a reellement fait (G-35, HOS-283).
 *
 * L'agent tient ce dossier lui-meme, sur son disque : `.hub/audit.log` et
 * `.hub/lock.json`. Hermes OS le lit et le CONFRONTE au disque en
 * recalculant l'empreinte de chaque competence posee. Cet ecran ne montre
 * donc pas ce que l'agent a annonce, mais ce que la verification a trouve.
 *
 * ## Pourquoi le verdict et la confiance sont cote a cote
 *
 * Mesure du 2026-09-10 : `actual-setup` est posee avec un verdict
 * `dangerous` et cinq findings critiques, parce que sa source est
 * `builtin` ; une autre competence au meme verdict a ete BLOQUEE parce
 * qu'elle etait `community`. Meme verdict, issues opposees. Afficher
 * « installee » sans ces deux colonnes tairait exactement ce dont un
 * operateur a besoin.
 *
 * ## Ce que l'ecran ne peut pas montrer, et le dit
 *
 * Un refus silencieux — nom introuvable, deja installee sans `--force` —
 * n'ecrit ni fichier ni ligne d'audit. Aucun lecteur a posteriori ne peut
 * le distinguer d'une operation jamais demandee. La phrase est affichee
 * plutot que tue.
 */
function OngletGouvernance({
  requete,
}: {
  requete: ReturnType<typeof useQuery<GouvernanceSkills>>;
}) {
  const d = requete.data;
  const posees = d?.posees ?? [];
  const operations = d?.operations ?? [];

  return (
    <AsyncPanel
      title="Cycle de vie des Skills, verifie"
      subtitle={d?.racine ?? "Le dossier que l'agent tient lui-meme"}
      isLoading={requete.isLoading}
      isError={requete.isError}
      error={requete.error}
      action={<DemandeDInstallation />}
      isEmpty={posees.length === 0 && operations.length === 0}
      emptyLabel={
        d && !d.dossier_lisible
          ? "Le dossier `.hub` de l'agent n'existe pas : aucune competence " +
            "n'a jamais ete posee par le hub sur cette installation."
          : "Aucune operation de cycle de vie enregistree."
      }
    >
      {posees.length > 0 && (
        <>
          <div className="flex items-center gap-1.5 mb-2">
            <ShieldCheck size={11} className="text-hermes-arc" />
            <span className="num text-[10px] uppercase tracking-[0.11em] text-hermes-muted">
              Posees par le hub ({posees.length})
            </span>
          </div>
          <DataTable
            rows={posees}
            rowKey={(p) => p.nom}
            columns={[
              {
                header: "Competence",
                cell: (p: SkillPosee) => (
                  <span className="inline-flex items-center gap-1.5">
                    <Sparkles size={11} className="text-hermes-sodium" />
                    <span className="num text-[11px] text-hermes-text">{p.nom}</span>
                  </span>
                ),
              },
              {
                header: "Source",
                cell: (p: SkillPosee) => (
                  <span className="text-[10px] text-hermes-muted" title={p.identifiant}>
                    {p.source || "\u2014"}
                  </span>
                ),
              },
              {
                header: "Confiance",
                cell: (p: SkillPosee) => (
                  <span className="num text-[10px] text-hermes-glacier">
                    {p.confiance || "\u2014"}
                  </span>
                ),
              },
              { header: "Verdict du scan", cell: (p: SkillPosee) => <Verdict p={p} /> },
              { header: "Verifiee", cell: (p: SkillPosee) => <EtatVerifie p={p} /> },
            ]}
          />
        </>
      )}

      {operations.length > 0 && (
        <div className="mt-5 pt-4 border-t border-hermes-border/60">
          <div className="flex items-center gap-1.5 mb-2">
            <FileWarning size={11} className="text-hermes-dim" />
            <span className="num text-[10px] uppercase tracking-[0.11em] text-hermes-muted">
              Journal des operations ({operations.length})
            </span>
          </div>
          <DataTable
            rows={operations}
            rowKey={(o, i) => `${o.horodatage}/${o.skill}/${i}`}
            columns={[
              {
                header: "Quand",
                cell: (o) => (
                  <span className="num text-[10px] text-hermes-muted">
                    {o.horodatage || "\u2014"}
                  </span>
                ),
              },
              { header: "Action", cell: (o) => <ActionSkill action={o.action} /> },
              {
                header: "Competence",
                cell: (o) => (
                  <span className="num text-[11px] text-hermes-text">
                    {o.skill || "\u2014"}
                  </span>
                ),
              },
              {
                header: "Source",
                cell: (o) => (
                  <span className="text-[10px] text-hermes-muted">
                    {o.source ? `${o.source} / ${o.confiance}` : "\u2014"}
                  </span>
                ),
              },
              {
                header: "Verdict",
                cell: (o) => (
                  <span className="num text-[10px] text-hermes-muted">
                    {o.verdict || "\u2014"}
                  </span>
                ),
              },
              {
                header: "Detail",
                cell: (o) => (
                  <span className="num text-[10px] text-hermes-dim" title={o.detail}>
                    {o.detail || "\u2014"}
                  </span>
                ),
              },
            ]}
          />
        </div>
      )}

      {d && (
        <p className="pt-3 text-[10px] text-hermes-dim">
          Angle mort : {d.angle_mort}.
        </p>
      )}
    </AsyncPanel>
  );
}

/**
 * Demander la pose d'une Skill — sous l'autorite d'Aegis (G-36, HOS-285).
 *
 * Ce bouton n'installe rien. Il soumet l'action a Aegis, qui la met en
 * attente d'un accord humain : `skill_install` est declare
 * `mandatory_validation` dans `config/security.yaml`, donc jamais
 * auto-autorise, quel que soit le niveau d'autonomie.
 *
 * Le second appel, apres accord, consomme l'approbation — une fois. Ce
 * n'est pas un detour d'implementation : une file qui rejouerait des
 * actions stockees aurait besoin d'un repartiteur capable de tout
 * reexecuter, ce qu'une barriere de securite ne doit pas posseder.
 *
 * Et le statut affiche vient du DISQUE. `skills.manage install` rend
 * `installed: true` dans tous les cas, y compris apres un blocage du
 * scanner : le montrer serait exactement le faux succes que cette serie
 * de passes demonte depuis G-26.
 */
function DemandeDInstallation() {
  const [identifiant, setIdentifiant] = useState("");
  const qc = useQueryClient();
  const demande = useMutation({
    mutationFn: (id: string) => skillsClient.installer(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["skills", "gouvernance"] });
      qc.invalidateQueries({ queryKey: ["approbations-aegis"] });
    },
  });
  const r = demande.data;

  return (
    <div className="flex flex-col items-end gap-1.5">
      <div className="flex items-center gap-1.5">
        <input
          value={identifiant}
          onChange={(e) => setIdentifiant(e.target.value)}
          placeholder="official/devops/actual-setup"
          className="num text-[10.5px] bg-hermes-bg-deep/60 border border-hermes-border/60
            clip-corner-sm px-2 py-1 w-[250px] text-hermes-text
            placeholder:text-hermes-dim focus:outline-none focus:border-hermes-sodium/50"
        />
        <button
          type="button"
          disabled={!identifiant.trim() || demande.isPending}
          onClick={() => demande.mutate(identifiant.trim())}
          className="num text-[10px] uppercase tracking-[0.11em] px-2 py-1 border
            clip-corner-sm text-hermes-sodium border-hermes-sodium/45
            bg-hermes-sodium/[0.09] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {demande.isPending ? "\u2026" : "Demander la pose"}
        </button>
      </div>
      {demande.isError && (
        <span className="text-[10px] text-hermes-red">
          {String((demande.error as Error)?.message ?? "echec de la demande")}
        </span>
      )}
      {r && <ResultatDeDemande r={r} />}
    </div>
  );
}

/** Les six issues bornees, traduites et jamais paraphrasees. */
function ResultatDeDemande({ r }: { r: ResultatInstallation }) {
  const table: Record<
    StatutInstallation,
    { texte: string; ton: "success" | "warning" | "danger" | "info"; aide: string }
  > = {
    posee: {
      texte: "posee et verifiee", ton: "success",
      aide: "empreinte du disque egale a celle du verrou",
    },
    approbation_requise: {
      texte: "approbation requise", ton: "warning",
      aide: "rien n'a ete ecrit — decidez dans Gouvernance, puis redemandez",
    },
    bloquee_par_le_scanner: {
      texte: "bloquee par le scanner", ton: "danger",
      aide: "l'accord humain autorise la demande, pas la pose",
    },
    sans_effet: {
      texte: "sans effet", ton: "warning",
      aide: "rien n'a ete ecrit : nom introuvable, ou deja posee",
    },
    refusee: { texte: "refusee", ton: "danger", aide: "refus d'Aegis" },
    indisponible: {
      texte: "indisponible", ton: "danger",
      aide: "le runtime ou Aegis n'a pas repondu",
    },
  };
  const l = table[r.statut] ?? {
    texte: r.statut, ton: "warning" as const, aide: "",
  };
  return (
    <span className="flex items-center gap-1.5" title={r.raison ?? l.aide}>
      <Badge variant={l.ton}>{l.texte}</Badge>
      <span className="text-[10px] text-hermes-dim max-w-[280px] truncate">
        {r.skill ? `${r.skill} \u00b7 ${l.aide}` : l.aide}
      </span>
    </span>
  );
}

/** Le verdict du scanner et ses findings. Le verdict seul ne suffit pas :
 *  `dangerous` est passe sur une source `builtin` et a bloque sur une
 *  source `community`, mesure le 2026-09-10. */
function Verdict({ p }: { p: SkillPosee }) {
  const total = Object.values(p.findings).reduce((a, b) => a + b, 0);
  const critiques = p.findings.critical ?? 0;
  const ton =
    p.verdict === "safe" ? "success" : p.verdict === "dangerous" ? "danger" : "warning";
  return (
    <span
      className="inline-flex items-center gap-1.5"
      title={
        total
          ? Object.entries(p.findings)
              .map(([s, n]) => `${n} ${s}`)
              .join(", ")
          : "aucun finding enregistre"
      }
    >
      <Badge variant={ton}>{p.verdict || "\u2014"}</Badge>
      {total > 0 && (
        <span className="num text-[10px] text-hermes-dim">
          {total} finding(s){critiques ? `, ${critiques} critique(s)` : ""}
        </span>
      )}
    </span>
  );
}

/** Le resultat de la CONFRONTATION, pas ce que l'agent a annonce. */
function EtatVerifie({ p }: { p: SkillPosee }) {
  if (p.etat === "conforme") {
    return (
      <span
        className="inline-flex items-center gap-1.5"
        title={`empreinte recalculee ${p.empreinte_reelle}`}
      >
        <ShieldCheck size={11} className="text-hermes-arc" />
        <Badge variant="success">conforme</Badge>
      </span>
    );
  }
  const libelle: Record<EtatPosee, { texte: string; titre: string }> = {
    conforme: { texte: "conforme", titre: "" },
    alteree: {
      texte: "alteree",
      titre:
        `Le verrou annonce ${p.empreinte_attendue}, le disque porte ` +
        `${p.empreinte_reelle} : le dossier a change depuis le scan.`,
    },
    annoncee_absente: {
      texte: "annoncee, absente",
      titre:
        `Le verrou l'annonce sous ${p.chemin || "(sans chemin)"}, ` +
        "le dossier n'est pas la.",
    },
  };
  const l = libelle[p.etat];
  return (
    <span className="inline-flex items-center gap-1.5" title={l.titre}>
      <ShieldAlert size={11} className="text-hermes-red" />
      <Badge variant="danger">{l.texte}</Badge>
    </span>
  );
}

/** Les actions que l'agent ecrit. Une valeur inattendue est rendue telle
 *  quelle : la ranger dans l'une des trois connues serait une affirmation. */
function ActionSkill({ action }: { action: string }) {
  if (!action) return <span className="text-hermes-dim">ligne illisible</span>;
  const ton =
    action === "INSTALL" ? "success" : action === "BLOCKED" ? "danger" : "info";
  return <Badge variant={ton}>{action}</Badge>;
}

export default SkillsCenter;
