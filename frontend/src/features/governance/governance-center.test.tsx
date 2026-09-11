/**
 * Ce que l'écran de gouvernance refuse d'afficher (G-36, HOS-285).
 *
 * Le cockpit lisait `/approval`, la file de `backend/policy/` — un
 * dictionnaire en mémoire dont `set_policy_engine` n'est jamais appelé,
 * donc sans aucun producteur. Il annonçait « aucune approbation en
 * attente » par construction, pendant qu'Aegis accumulait des demandes
 * réelles : mesure du 2026-09-11, 206 lignes `pending` du 2026-08-10 au
 * 2026-09-02, qu'aucun écran ne pouvait montrer.
 *
 * Ces gardes tiennent la moitié qui reste après le rebranchement : que
 * l'écran montre ce qui attend vraiment une décision, et que le bouton
 * applique la décision qu'il annonce.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import type { ApprobationAegis } from "@/types/hermes";

const etat = vi.hoisted(() => ({
  approbations: [] as ApprobationAegis[],
  approuvees: [] as string[],
  rejetees: [] as string[],
}));

vi.mock("@/hooks/use-api", () => ({
  // G-37 : l'onglet Regles lit desormais la matrice Aegis, la seule
  // politique reellement appliquee.
  useAutonomy: () => ({
    data: { level: "medium", levels: [], overridden: false,
            always_validated: [], categories: [] },
    isLoading: false, isError: false, error: null,
  }),
  useAuditLog: () => ({ data: [], isLoading: false, isError: false }),
  useApprovals: () => ({
    data: etat.approbations,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useApproveAction: () => ({
    mutate: ({ id }: { id: string }) => etat.approuvees.push(id),
    isPending: false,
  }),
  useRejectAction: () => ({
    mutate: ({ id }: { id: string }) => etat.rejetees.push(id),
    isPending: false,
  }),
}));

import { GovernanceCenter } from "./governance-center";

function demande(p: Partial<ApprobationAegis>): ApprobationAegis {
  return {
    id: "a1",
    action_type: "skill_install",
    description: "Install skill official/devops/actual-setup",
    target_path: null,
    requesting_agent: "hermes-os.cockpit",
    reason: "skill_install always requires human validation",
    status: "pending",
    task_id: null,
    project_id: null,
    created_at: "2026-09-11T03:00:00Z",
    decided_at: null,
    expires_at: null,
    portee: "action",
    portee_racine: null,
    usages_restants: null,
    discriminants: null,
    expired: false,
    ...p,
  };
}

beforeEach(() => {
  etat.approuvees = [];
  etat.rejetees = [];
});

describe("la file d'approbation affichée", () => {
  it("montre la demande réelle d'Aegis", () => {
    etat.approbations = [demande({})];
    render(<GovernanceCenter />);
    expect(
      screen.getByText(/Install skill official\/devops\/actual-setup/),
    ).toBeInTheDocument();
    expect(screen.getByText("skill_install")).toBeInTheDocument();
  });

  it("n'affiche pas comme « en attente » ce qui est déjà décidé", () => {
    // Un écran qui listerait les lignes décidées ferait redemander une
    // décision déjà prise — et Aegis, lui, ne la reprendrait pas : une
    // approbation consommée passe à `used`.
    etat.approbations = [
      demande({ id: "decidee", status: "used", description: "Deja consommee" }),
      demande({ id: "refusee", status: "refused", description: "Deja refusee" }),
      demande({ id: "vivante", description: "Attend vraiment" }),
    ];
    render(<GovernanceCenter />);
    expect(screen.getByText(/Attend vraiment/)).toBeInTheDocument();
    expect(screen.queryByText(/Deja consommee/)).toBeNull();
    expect(screen.queryByText(/Deja refusee/)).toBeNull();
  });

  it("écarte une demande expirée", () => {
    // Aegis ne la consommera plus. La laisser ferait croire qu'une
    // décision sert encore à quelque chose.
    etat.approbations = [demande({ expired: true, description: "Perimee" })];
    render(<GovernanceCenter />);
    expect(screen.queryByText(/Perimee/)).toBeNull();
  });

  it("« Approuver » approuve, « Rejeter » rejette", async () => {
    // La mutation qui compte : un bouton qui applique l'inverse de ce
    // qu'il annonce est indiscernable d'un bouton correct, jusqu'au jour
    // où une pose refusée s'installe.
    etat.approbations = [demande({ id: "x1" })];
    render(<GovernanceCenter />);
    fireEvent.click(screen.getByText("Approuver"));
    await Promise.resolve();
    expect(etat.approuvees).toEqual(["x1"]);
    expect(etat.rejetees).toEqual([]);

    fireEvent.click(screen.getByText("Rejeter"));
    await Promise.resolve();
    expect(etat.rejetees).toEqual(["x1"]);
  });
});
