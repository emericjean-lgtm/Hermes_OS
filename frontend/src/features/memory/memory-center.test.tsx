/**
 * G-10 — la promotion d'un souvenir a enfin un appelant frontend.
 *
 * `POST /memory/{id}/promote` existait déjà, testé côté backend
 * (`test_memoire_promotion.py`), mais `ORPHELINS_CONNUS` le portait comme
 * route sans appelant : aucun écran ne montrait ce qui est en quarantaine,
 * et personne ne pouvait cliquer sur « promouvoir ». Ces gardes tiennent
 * la moitié produit : que le panneau montre ce qui attend vraiment une
 * validation, jamais ce qui est déjà promu, et que le bouton appelle la
 * mutation avec l'acteur réellement saisi — jamais une promotion anonyme.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import type { EpisodicMemoryRecord } from "@/types/hermes";

const etat = vi.hoisted(() => ({
  entries: [] as EpisodicMemoryRecord[],
  promues: [] as { id: string; promuPar: string }[],
  dernierOnError: undefined as ((e: unknown) => void) | undefined,
}));

vi.mock("@/hooks/use-api", () => ({
  useMemorySearch: () => ({ data: [], isLoading: false }),
  useKnowledgeGraph: () => ({ data: { nodes: [], edges: [] }, isLoading: false, isError: false, error: null }),
  useExperiences: () => ({ data: [] }),
  useMemoryStatistics: () => ({ data: {} }),
  useMemoryList: () => ({
    data: etat.entries,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useMemoryPromote: () => ({
    mutate: (
      vars: { id: string; promuPar: string },
      opts?: { onError?: (e: unknown) => void },
    ) => {
      etat.promues.push(vars);
      etat.dernierOnError = opts?.onError;
    },
    isPending: false,
  }),
  useAlexandrieStatus: () => ({ data: undefined }),
  useAlexandrieHealth: () => ({ data: { healthy: true }, isLoading: false }),
  useAlexandrieSearch: () => ({ data: { results: [] }, isLoading: false, isError: false, error: null }),
  useAlexandrieSync: () => ({ mutate: () => {}, isPending: false }),
  useAlexandrieSyncHistory: () => ({ data: { events: [] }, isLoading: false, isError: false, error: null }),
  useAlexandrieDocuments: () => ({ data: { documents: [], total: 0 }, isLoading: false, isError: false, error: null }),
  useAlexandrieGraph: () => ({ data: { edges: [] }, isLoading: false, isError: false, error: null }),
}));

import { MemoryCenter } from "./memory-center";

function souvenir(p: Partial<EpisodicMemoryRecord>): EpisodicMemoryRecord {
  return {
    id: "m1",
    project_id: "proj-A",
    type: "fact",
    content: "souvenir écrit par l'agent",
    tags: [],
    confidence: 1.0,
    created_at: "2026-09-12T00:00:00Z",
    origine: "agent",
    en_quarantaine: true,
    promu_par: null,
    verifie_le: null,
    ...p,
  };
}

beforeEach(() => {
  etat.entries = [];
  etat.promues = [];
  etat.dernierOnError = undefined;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("le panneau de quarantaine", () => {
  it("montre une mémoire réellement en quarantaine", () => {
    etat.entries = [souvenir({})];
    render(<MemoryCenter />);
    expect(screen.getByText(/souvenir écrit par l'agent/)).toBeInTheDocument();
    expect(screen.getByText("agent")).toBeInTheDocument();
  });

  it("n'affiche pas une mémoire déjà promue", () => {
    // Une mémoire dont `en_quarantaine` est faux est déjà validée : la
    // remontrer ferait redemander une décision déjà prise.
    etat.entries = [
      souvenir({ id: "promue", content: "DEJA_PROMUE", en_quarantaine: false, promu_par: "emeric" }),
      souvenir({ id: "vivante", content: "TOUJOURS_EN_ATTENTE" }),
    ];
    render(<MemoryCenter />);
    expect(screen.getByText(/TOUJOURS_EN_ATTENTE/)).toBeInTheDocument();
    expect(screen.queryByText(/DEJA_PROMUE/)).toBeNull();
  });

  it("le vide se dit : aucune mémoire en quarantaine", () => {
    etat.entries = [];
    render(<MemoryCenter />);
    expect(screen.getByText(/Aucune mémoire en quarantaine/)).toBeInTheDocument();
  });

  it("« Promouvoir » appelle la mutation avec l'acteur saisi", () => {
    etat.entries = [souvenir({ id: "m42" })];
    vi.spyOn(window, "prompt").mockReturnValue("emeric");
    render(<MemoryCenter />);
    fireEvent.click(screen.getByLabelText("Promouvoir la mémoire m42"));
    expect(etat.promues).toEqual([{ id: "m42", promuPar: "emeric" }]);
  });

  it("une saisie annulée ne promeut rien", () => {
    // `window.prompt` rend `null` sur Annuler : un clic annulé ne doit
    // jamais devenir une promotion anonyme.
    etat.entries = [souvenir({ id: "m43" })];
    vi.spyOn(window, "prompt").mockReturnValue(null);
    render(<MemoryCenter />);
    fireEvent.click(screen.getByLabelText("Promouvoir la mémoire m43"));
    expect(etat.promues).toEqual([]);
  });

  it("une promotion refusée par l'API s'affiche sur l'entrée concernée", () => {
    etat.entries = [souvenir({ id: "m44", content: "SOUVENIR_REFUSE" })];
    vi.spyOn(window, "prompt").mockReturnValue("emeric");
    render(<MemoryCenter />);
    fireEvent.click(screen.getByLabelText("Promouvoir la mémoire m44"));
    expect(etat.dernierOnError).toBeDefined();
    act(() => {
      etat.dernierOnError?.(new Error("409 Conflict: déjà promue"));
    });
    expect(screen.getByText(/409 Conflict: déjà promue/)).toBeInTheDocument();
  });
});
