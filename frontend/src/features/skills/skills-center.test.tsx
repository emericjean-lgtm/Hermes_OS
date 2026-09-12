/**
 * Ce que l'écran Runs ↔ Skills refuse d'inventer (G-34, HOS-282).
 *
 * La relation Run ↔ Skill a coûté cinq passes — G-29 à G-33 — dont deux
 * qui ont refusé de la fabriquer faute de preuve. La reconstituer à
 * l'affichage annulerait tout ce travail à la dernière étape, et
 * personne ne le verrait : un écran qui range une mutation orpheline
 * sous le premier Run venu a exactement l'aspect d'un écran juste.
 *
 * Ces gardes rendent le composant réel, avec le client simulé. Elles
 * portent donc aussi la propriété que le DoD demande explicitement :
 * l'écran **consomme** la route, il n'est pas seulement prêt à le faire.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type {
  ObservationsSkills, GouvernanceSkills, SkillPosee, VersionsSkills,
} from "@/services/client";

const donnees = vi.hoisted(() => ({
  observations: {} as ObservationsSkills,
  gouvernance: {} as GouvernanceSkills,
  versions: {} as VersionsSkills,
  appels: 0,
  appelsGouvernance: 0,
  appelsVersions: 0,
}));

vi.mock("@/services/client", () => ({
  skillsClient: {
    agentSkills: () =>
      Promise.resolve({
        total: 0,
        racine: "/agent/skills",
        domaines: [],
        correlation_impossible: "mesure G-27",
      }),
    list: () => Promise.resolve([]),
    observations: () => {
      donnees.appels += 1;
      return Promise.resolve(donnees.observations);
    },
    gouvernance: () => {
      donnees.appelsGouvernance += 1;
      return Promise.resolve(donnees.gouvernance);
    },
    versions: () => {
      donnees.appelsVersions += 1;
      return Promise.resolve(donnees.versions);
    },
  },
}));

vi.mock("@/hooks/use-api", () => ({
  useSkillsCatalogue: () => ({ data: undefined, isLoading: false, isError: false }),
  useSkillsRecherche: () => ({ data: undefined, isLoading: false, isError: false }),
  useSkillDetail: () => ({ data: undefined, isLoading: false, isError: false }),
}));

import { SkillsCenter } from "./skills-center";

function mutation(skill: string, turn: string, action = "created") {
  return { skill, action, provenance: "local", turn_id: turn, observe_a: 1.0 };
}

const VIDE: ObservationsSkills = {
  retention_jours: 7,
  etat_lisible: false,
  observees: 0,
  registre_lisible: true,
  runs: [],
  non_rattachees: [],
};

const GOUV_VIDE: GouvernanceSkills = {
  dossier_lisible: false,
  racine: "/agent/skills/.hub",
  operations: [],
  posees: [],
  alertes: { alterees: 0, absentes: 0, bloquees: 0 },
  angle_mort: "un refus silencieux n'ecrit rien",
};

function posee(p: Partial<SkillPosee>): SkillPosee {
  return {
    nom: "une", source: "official", identifiant: "official/x/une",
    confiance: "builtin", verdict: "safe", chemin: "x/une",
    empreinte_attendue: "sha256:aaaa", empreinte_reelle: "sha256:aaaa",
    etat: "conforme", findings: {}, ...p,
  };
}

const VERSIONS_VIDE: VersionsSkills = {
  ledger_lisible: false,
  racine: "/agent/skills/.curator_ledger.jsonl",
  total: 0,
  entrees: [],
  rollback_declenchable: false,
  rollback_absent_raison: "aucune RPC ne l'expose depuis Hermes OS",
};

async function ouvrirGouvernance(g: GouvernanceSkills) {
  donnees.gouvernance = g;
  donnees.observations = VIDE;
  donnees.versions = VERSIONS_VIDE;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <SkillsCenter />
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByText("Gouvernance"));
}

async function ouvrirVersions(v: VersionsSkills) {
  donnees.gouvernance = GOUV_VIDE;
  donnees.observations = VIDE;
  donnees.versions = v;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <SkillsCenter />
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByText("Versions"));
}

async function ouvrir(observations: ObservationsSkills) {
  donnees.gouvernance = GOUV_VIDE;
  donnees.observations = observations;
  donnees.versions = VERSIONS_VIDE;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <SkillsCenter />
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByText(/Runs .* Skills/));
}

beforeEach(() => {
  donnees.appels = 0;
  donnees.appelsGouvernance = 0;
  donnees.appelsVersions = 0;
});

describe("l'onglet Runs ↔ Skills", () => {
  it("consomme réellement la route, il n'est pas seulement prêt", async () => {
    // Le défaut que ce dépôt appelle « backend orphelin » : une route
    // correcte, testée, et qu'aucun écran n'appelle. Ici la garde tient
    // le sens inverse — l'écran appelle bien le client.
    await ouvrir({
      ...VIDE,
      etat_lisible: true,
      observees: 1,
      runs: [{ run: "RUN-ALPHA", detail: null, skills: [mutation("g34-une", "T1")] }],
    });
    await waitFor(() => expect(donnees.appels).toBeGreaterThan(0));
    expect(await screen.findByText("RUN-ALPHA")).toBeInTheDocument();
    expect(screen.getByText("g34-une")).toBeInTheDocument();
  });

  it("montre plusieurs Skills sous le Run qui les a mutées", async () => {
    await ouvrir({
      ...VIDE,
      etat_lisible: true,
      observees: 2,
      runs: [
        {
          run: "RUN-ALPHA",
          detail: null,
          skills: [mutation("g34-une", "T1"), mutation("g34-deux", "T1")],
        },
      ],
    });
    expect(await screen.findByText("g34-une")).toBeInTheDocument();
    expect(screen.getByText("g34-deux")).toBeInTheDocument();
  });

  it("ne mélange pas deux Runs", async () => {
    // La mutation qui compte : un écran qui aplatit les groupes montrerait
    // les quatre compétences partout, et paraîtrait parfaitement normal.
    await ouvrir({
      ...VIDE,
      etat_lisible: true,
      observees: 2,
      runs: [
        { run: "RUN-ALPHA", detail: null, skills: [mutation("alpha-seule", "T1")] },
        { run: "RUN-BETA", detail: null, skills: [mutation("beta-seule", "T2")] },
      ],
    });
    const alpha = (await screen.findByText("RUN-ALPHA")).closest("div.border");
    const beta = screen.getByText("RUN-BETA").closest("div.border");
    expect(alpha).not.toBeNull();
    expect(beta).not.toBeNull();
    expect(alpha!.textContent).toContain("alpha-seule");
    expect(alpha!.textContent).not.toContain("beta-seule");
    expect(beta!.textContent).toContain("beta-seule");
    expect(beta!.textContent).not.toContain("alpha-seule");
  });

  it("n'affiche aucun Run pour une mutation qui n'en a pas", async () => {
    // « Une donnée absente doit rester explicitement absente. » Le bloc
    // des orphelines porte la cause, et aucun identifiant de Run ne doit
    // y apparaître — pas même celui du Run affiché juste au-dessus.
    await ouvrir({
      ...VIDE,
      etat_lisible: true,
      observees: 2,
      runs: [{ run: "RUN-ALPHA", detail: null, skills: [mutation("rattachee", "T1")] }],
      non_rattachees: [
        { ...mutation("orpheline", ""), raison: "sans_etiquette" },
      ],
    });
    const bloc = (await screen.findByText(/Mutations sans Run/))
      .closest("div")!.parentElement!;
    expect(bloc.textContent).toContain("orpheline");
    expect(bloc.textContent).not.toContain("RUN-ALPHA");
    expect(bloc.textContent).toContain("aucune etiquette");
  });

  it("distingue les deux causes d'absence de Run", async () => {
    await ouvrir({
      ...VIDE,
      etat_lisible: true,
      observees: 2,
      non_rattachees: [
        { ...mutation("sans", ""), raison: "sans_etiquette" },
        { ...mutation("etrangere", "venue-d-ailleurs"), raison: "etiquette_non_resolue" },
      ],
    });
    expect(await screen.findByText("aucune etiquette")).toBeInTheDocument();
    expect(screen.getByText("etiquette non resolue")).toBeInTheDocument();
  });

  it("le pivot par Skill ne nomme que des Runs présents dans la donnée", async () => {
    // Requirement : plusieurs Runs utilisant le MEME Skill. Le pivot est
    // dérivé de `runs`, donc structurellement incapable d'en nommer un
    // autre — cette garde le tient sur le rendu, pas sur l'intention.
    await ouvrir({
      ...VIDE,
      etat_lisible: true,
      observees: 2,
      runs: [
        { run: "RUN-ALPHA", detail: null, skills: [mutation("partagee", "T1")] },
        { run: "RUN-BETA", detail: null, skills: [mutation("partagee", "T2")] },
      ],
    });
    fireEvent.click(await screen.findByText("Par Skill"));
    const carte = (await screen.findByText("partagee")).closest("div.border")!;
    expect(carte.textContent).toContain("RUN-ALPHA");
    expect(carte.textContent).toContain("RUN-BETA");
    expect(carte.textContent).toContain("2 Run(s)");
  });

  it("dit « absent du Run Ledger », et se tait si le registre est illisible", async () => {
    // Deux absences qui se ressemblent et ne disent pas la même chose :
    // un Run que le Ledger ne connaît pas, et un Ledger qu'on n'a pas pu
    // lire. Les confondre ferait dire « Run inconnu » d'un Run connu.
    await ouvrir({
      ...VIDE,
      etat_lisible: true,
      observees: 1,
      registre_lisible: true,
      runs: [{ run: "RUN-ALPHA", detail: null, skills: [mutation("s", "T1")] }],
    });
    expect(await screen.findByText(/absent du Run Ledger/)).toBeInTheDocument();
  });

  it("annonce la panne du registre plutôt que des Runs inconnus", async () => {
    await ouvrir({
      ...VIDE,
      etat_lisible: true,
      observees: 1,
      registre_lisible: false,
      runs: [{ run: "RUN-ALPHA", detail: null, skills: [mutation("s", "T1")] }],
    });
    expect(await screen.findByText(/Run Ledger n'a pas pu etre lu/))
      .toBeInTheDocument();
    expect(screen.queryByText(/absent du Run Ledger/)).toBeNull();
  });

  it("un observateur absent se lit « aucune observation », pas « aucune mutation »", async () => {
    // Trois situations que Hermes OS ne distingue pas d'ici : plugin
    // absent, désactivé, ou qui n'a rien vu. Affirmer « aucune mutation »
    // serait une conclusion que la donnée ne soutient pas.
    await ouvrir(VIDE);
    const vide = await screen.findByText(/Aucune observation/);
    expect(vide.textContent).toContain("pas installe");
    expect(vide.textContent).toContain("Ce n'est pas");
  });
});

describe("l'onglet Gouvernance", () => {
  it("consomme la route et montre ce que le hub a pose", async () => {
    await ouvrirGouvernance({
      ...GOUV_VIDE,
      dossier_lisible: true,
      posees: [posee({ nom: "actual-setup" })],
    });
    await waitFor(() => expect(donnees.appelsGouvernance).toBeGreaterThan(0));
    expect(await screen.findByText("actual-setup")).toBeInTheDocument();
  });

  it("montre le verdict ET la confiance, jamais l'un sans l'autre", async () => {
    // Mesure du 2026-09-10 : meme verdict `dangerous`, issues opposees —
    // passee sur une source `builtin`, bloquee sur une source `community`.
    // Un ecran qui tairait la confiance rendrait les deux identiques.
    await ouvrirGouvernance({
      ...GOUV_VIDE,
      dossier_lisible: true,
      posees: [posee({
        nom: "actual-setup", verdict: "dangerous", confiance: "builtin",
        findings: { critical: 5, medium: 3 },
      })],
    });
    const ligne = (await screen.findByText("actual-setup")).closest("tr")!;
    expect(ligne.textContent).toContain("dangerous");
    expect(ligne.textContent).toContain("builtin");
    expect(ligne.textContent).toContain("8 finding(s)");
    expect(ligne.textContent).toContain("5 critique(s)");
  });

  it("n'annonce pas `conforme` quand l'empreinte differe", async () => {
    // Le faux succes tel qu'il se verrait a l'ecran : « installee » ne
    // veut pas dire « inchangee ».
    await ouvrirGouvernance({
      ...GOUV_VIDE,
      dossier_lisible: true,
      posees: [posee({
        etat: "alteree",
        empreinte_attendue: "sha256:aaaa",
        empreinte_reelle: "sha256:bbbb",
      })],
      alertes: { alterees: 1, absentes: 0, bloquees: 0 },
    });
    const ligne = (await screen.findByText("une")).closest("tr")!;
    expect(ligne.textContent).toContain("alteree");
    expect(ligne.textContent).not.toContain("conforme");
  });

  it("distingue « annoncee, absente » de « alteree »", async () => {
    await ouvrirGouvernance({
      ...GOUV_VIDE,
      dossier_lisible: true,
      posees: [posee({ etat: "annoncee_absente", empreinte_reelle: "" })],
      alertes: { alterees: 0, absentes: 1, bloquees: 0 },
    });
    expect(await screen.findByText("annoncee, absente")).toBeInTheDocument();
    expect(screen.queryByText("alteree")).toBeNull();
  });

  it("montre un blocage dans le journal, sans rien poser", async () => {
    await ouvrirGouvernance({
      ...GOUV_VIDE,
      dossier_lisible: true,
      operations: [{
        horodatage: "2026-09-10T19:54:04Z", action: "BLOCKED",
        skill: "docker", source: "skills.sh", confiance: "community",
        verdict: "dangerous", detail: "25_findings",
      }],
      alertes: { alterees: 0, absentes: 0, bloquees: 1 },
    });
    expect(await screen.findByText("BLOCKED")).toBeInTheDocument();
    expect(screen.getByText("25_findings")).toBeInTheDocument();
    expect(screen.queryByText(/Posees par le hub/)).toBeNull();
  });

  it("dit « ligne illisible » plutot que de deviner une operation", async () => {
    // Le parseur comptait les mots : « ceci n'est pas une ligne d'audit »
    // en fait six et devenait une operation. L'ecran doit refleter le
    // refus de deviner, pas le masquer.
    await ouvrirGouvernance({
      ...GOUV_VIDE,
      dossier_lisible: true,
      operations: [{
        horodatage: "", action: "", skill: "", source: "", confiance: "",
        verdict: "", detail: "ceci n'est pas une ligne d'audit",
      }],
    });
    expect(await screen.findByText("ligne illisible")).toBeInTheDocument();
  });

  it("affiche l'angle mort plutot que de laisser croire le journal exhaustif",
    async () => {
      await ouvrirGouvernance({
        ...GOUV_VIDE,
        dossier_lisible: true,
        posees: [posee({})],
        angle_mort: "un refus silencieux n'ecrit ni fichier ni ligne d'audit",
      });
      expect(await screen.findByText(/Angle mort/)).toBeInTheDocument();
      expect(screen.getByText(/refus silencieux/)).toBeInTheDocument();
    });

  it("un hub absent se lit comme tel, pas comme une panne", async () => {
    await ouvrirGouvernance(GOUV_VIDE);
    const vide = await screen.findByText(/dossier `.hub`/);
    expect(vide.textContent).toContain("jamais ete posee");
  });
});

describe("l'onglet Versions", () => {
  // Le ledger de mutations de l'agent, LU (G-42, HOS-303). Population
  // distincte des trois autres onglets : chaque entree ici EST une
  // version, jamais un horodatage ou un hash fabrique.

  it("consomme réellement la route, il n'est pas seulement prêt", async () => {
    await ouvrirVersions(VERSIONS_VIDE);
    await waitFor(() => expect(donnees.appelsVersions).toBeGreaterThan(0));
  });

  it("un ledger absent se lit comme tel, pas comme une panne", async () => {
    await ouvrirVersions(VERSIONS_VIDE);
    const vide = await screen.findByText(/n'existe pas encore/);
    expect(vide.textContent).toContain("aucune mutation");
  });

  it("montre le diff derive des before/after, pas une declaration", async () => {
    await ouvrirVersions({
      ...VERSIONS_VIDE,
      ledger_lisible: true,
      total: 1,
      entrees: [{
        id: "g42-un", horodatage: "2026-09-12T10:00:00+00:00",
        acteur: "user", action: "created", skill: "g42-scratch",
        fichiers: [{ chemin: "a/SKILL.md", etat: "ajoute" }],
        rollback_de: null, absorbe_dans: null,
      }],
    });
    expect(await screen.findByText("g42-scratch")).toBeInTheDocument();
    expect(screen.getByText("created")).toBeInTheDocument();
    expect(screen.getByText(/\+1/)).toBeInTheDocument();
  });

  it("un acteur hors de la liste connue est dit inconnu, jamais devine", async () => {
    await ouvrirVersions({
      ...VERSIONS_VIDE,
      ledger_lisible: true,
      total: 1,
      entrees: [{
        id: "g42-deux", horodatage: "2026-09-12T10:00:00+00:00",
        acteur: "acteur_inconnu", action: "created", skill: "g42-scratch",
        fichiers: [], rollback_de: null, absorbe_dans: null,
      }],
    });
    expect(await screen.findByText("acteur inconnu")).toBeInTheDocument();
  });

  it("dit pourquoi le rollback n'est pas declenchable, ne le tait pas", async () => {
    await ouvrirVersions({
      ...VERSIONS_VIDE,
      ledger_lisible: true,
      total: 1,
      entrees: [{
        id: "g42-trois", horodatage: "2026-09-12T10:00:00+00:00",
        acteur: "user", action: "created", skill: "g42-scratch",
        fichiers: [], rollback_de: null, absorbe_dans: null,
      }],
    });
    expect(await screen.findByText(/Rollback :/)).toBeInTheDocument();
    expect(screen.getByText(/aucune RPC/)).toBeInTheDocument();
  });

  it("montre le lien vers l'entree d'origine d'un rollback", async () => {
    await ouvrirVersions({
      ...VERSIONS_VIDE,
      ledger_lisible: true,
      total: 1,
      entrees: [{
        id: "g42-quatre", horodatage: "2026-09-12T10:05:00+00:00",
        acteur: "user", action: "rollback", skill: "g42-scratch",
        fichiers: [], rollback_de: "g42-un", absorbe_dans: null,
      }],
    });
    expect(await screen.findByText(/rollback de g42-un/)).toBeInTheDocument();
  });
});
