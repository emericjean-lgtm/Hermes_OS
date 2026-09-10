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

import type { ObservationsSkills } from "@/services/client";

const donnees = vi.hoisted(() => ({
  observations: {} as ObservationsSkills,
  appels: 0,
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

async function ouvrir(observations: ObservationsSkills) {
  donnees.observations = observations;
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
