/**
 * La console d'opérations, et ce qu'elle refuse d'inventer (HOS-235).
 *
 * Ces gardes tiennent une seule propriété, et c'est celle qui a coûté le
 * plus cher à ce dépôt : **une interface moins spectaculaire mais vraie
 * vaut mieux qu'une interface impressionnante mais fausse.**
 *
 * Douze jalons ont travaillé côté serveur à ce qu'un « on ne sait pas »
 * ne se range jamais avec un « c'est bon ». Le refaire à l'affichage
 * annulerait tout ce travail à la dernière étape.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { Cause, OperationsCenter } from "./operations-center";

// Le hook est simulé : ces gardes portent sur ce que la vue **fait des
// données**, pas sur le transport, qui a ses propres gardes côté Python.
const apercu = vi.hoisted(() => ({ valeur: {} as Record<string, unknown> }));

vi.mock("@/hooks/use-api", () => ({
  useOperationsApercu: () => ({
    data: apercu.valeur,
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/hooks/use-store", () => ({
  useCockpitStore: (selecteur: (s: unknown) => unknown) =>
    selecteur({ liveEvents: [], wsConnected: false }),
}));

function bloc<T>(donnees: T, source = "backend.runs.registre") {
  return { disponible: true, source, donnees };
}

function indisponible(source: string, raison: string) {
  return { disponible: false, source, donnees: null, raison };
}

const VIDE = {
  runs: bloc({ en_cours: [], nombre_en_cours: 0 }),
  fournisseurs: bloc(
    { configures: [], aucun_configure: true, etats: [] },
    "backend.ral.courtier",
  ),
  approbations: bloc(
    { en_attente: [], portees_vivantes: [] },
    "backend.security.approvals",
  ),
  points_de_reprise: bloc([], "backend.checkpoints"),
  installation: bloc(
    {
      version_du_code: "1.0.0",
      version_installee: null,
      racine_d_etat: "/etat",
      sante: { sain: true, controles: [] },
    },
    "backend.maj",
  ),
};

describe("le tri-état survit jusqu'à l'écran", () => {
  it("distingue zéro mesuré de non mesurable", () => {
    apercu.valeur = { ...VIDE };
    const { unmount } = render(<OperationsCenter />);
    // Zéro mesuré : on a regardé, il n'y en a pas.
    expect(screen.getAllByText(/Mesuré, pas supposé/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Non mesurable/)).toBeNull();
    unmount();

    apercu.valeur = {
      ...VIDE,
      points_de_reprise: indisponible("backend.checkpoints", "disque illisible"),
    };
    render(<OperationsCenter />);
    // Non mesurable : la source n'a pas répondu, et on le dit.
    expect(screen.getByText(/Non mesurable/)).toBeTruthy();
    expect(screen.getByText(/disque illisible/)).toBeTruthy();
  });

  it("n'affiche jamais 0 pour un indicateur non mesurable", () => {
    apercu.valeur = {
      ...VIDE,
      approbations: indisponible("backend.security.approvals", "base absente"),
    };
    render(<OperationsCenter />);
    // Le tiret cadratin, pas un zéro : un zéro se lit « rien ne s'est
    // passé », une indisponibilité se lit « on ne sait pas ».
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("affiche un vrai zéro quand il est mesuré", () => {
    apercu.valeur = { ...VIDE };
    render(<OperationsCenter />);
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);
  });

  it("dit qu'aucun fournisseur configuré est le défaut, pas une panne", () => {
    apercu.valeur = { ...VIDE };
    render(<OperationsCenter />);
    expect(screen.getByText(/sans clé, le cloud est injoignable/)).toBeTruthy();
  });

  it("ne présente pas une version jamais marquée comme la version du code", () => {
    apercu.valeur = { ...VIDE };
    render(<OperationsCenter />);
    expect(screen.getByText(/jamais marquée/)).toBeTruthy();
  });

  it("signale l'écart entre version du code et version installée", () => {
    apercu.valeur = {
      ...VIDE,
      installation: bloc(
        {
          version_du_code: "1.1.0",
          version_installee: "1.0.0",
          racine_d_etat: "/etat",
          sante: { sain: true, controles: [] },
        },
        "backend.maj",
      ),
    };
    render(<OperationsCenter />);
    expect(screen.getByText(/mise à jour non confirmée/)).toBeTruthy();
  });

  it("ne peint pas un contrôle sans objet comme un échec", () => {
    apercu.valeur = {
      ...VIDE,
      installation: bloc(
        {
          version_du_code: "1.0.0",
          version_installee: "1.0.0",
          racine_d_etat: "/etat",
          sante: {
            sain: true,
            controles: [
              {
                nom: "points de reprise",
                etat: "indisponible",
                detail: "aucun",
                critique: false,
              },
            ],
          },
        },
        "backend.maj",
      ),
    };
    render(<OperationsCenter />);
    // « Sans objet », pas « échec » : une installation neuve n'a pas de
    // points de reprise, et le peindre en rouge ferait chercher une
    // panne qui n'existe pas.
    expect(screen.getByText("sans objet")).toBeTruthy();
  });
});

describe("les trois états d'une cause", () => {
  it("distingue non démontrée, cherchée-non-trouvée, et nommée", () => {
    const { unmount: u1 } = render(<Cause cause={null} />);
    expect(screen.getByText(/cause non démontrée/)).toBeTruthy();
    u1();

    const { unmount: u2 } = render(<Cause cause="inconnue" />);
    expect(screen.getByText(/cherchée/)).toBeTruthy();
    u2();

    render(<Cause cause="ressource" />);
    expect(screen.getByText("ressource")).toBeTruthy();
  });
});

describe("la trace ne fabrique rien", () => {
  it("reste vide quand le runtime n'émet rien", () => {
    apercu.valeur = { ...VIDE };
    render(<OperationsCenter />);
    expect(
      screen.getByText(/pas de battement de cœur inventé/),
    ).toBeTruthy();
  });
});

describe("chaque section nomme sa source", () => {
  it("affiche le module Hermes dont vient chaque bloc", () => {
    apercu.valeur = { ...VIDE };
    render(<OperationsCenter />);
    for (const source of [
      "backend.runs.registre",
      "backend.ral.courtier",
      "backend.security.approvals",
      "backend.checkpoints",
      "backend.maj",
    ]) {
      expect(
        screen.getAllByText(new RegExp(source.replace(/\./g, "\\."))).length,
      ).toBeGreaterThan(0);
    }
  });
});
