import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { VerificationReport } from "./verification-report";
import type { MissionVerification } from "@/types/hermes";

/**
 * §15.5 lot 2 — HOS-222 avait déjà posé la règle côté backend : `measured`,
 * `mesure_impossible` et `indetermines` ne se confondent pas avec un
 * succès. Rien ne la vérifiait côté écran. Mesuré en runtime réel avant
 * correction : une mission sans workspace lié (`measured: false`,
 * `workspace: null`) rendait « Confirmé sur le disque : 0 fichier(s)
 * touché(s) » — le faux positif exact que `verification.py` existe pour
 * empêcher, reformulé par la couche UI plutôt que lu depuis le backend.
 */

describe("VerificationReport", () => {
  it("affiche l'absence de mesure sans jamais parler de succès", () => {
    render(<VerificationReport v={null} />);

    expect(screen.getByText(/aucune vérification disque/i)).toBeInTheDocument();
    expect(screen.queryByText(/confirmé sur le disque/i)).toBeNull();
    expect(screen.queryByText(/0 fichier/i)).toBeNull();
  });

  it("ne convertit jamais measured=false en succès à 0 fichier, avec ou sans workspace lié", () => {
    const nonMesuree: MissionVerification = {
      measured: false,
      verdict: "indisponible",
      mesure_impossible: false,
      contradicted: false,
      workspace: undefined,
      created: [],
      modified: [],
      deleted: [],
      indetermines: [],
    };

    render(<VerificationReport v={nonMesuree} />);

    expect(screen.getByText(/aucune vérification disque/i)).toBeInTheDocument();
    expect(screen.queryByText(/confirmé sur le disque/i)).toBeNull();
    expect(screen.queryByText(/0 fichier/i)).toBeNull();
  });

  it("distingue l'échec de lecture (HOS-222) de l'absence de workspace", () => {
    const illisible: MissionVerification = {
      measured: false,
      verdict: "indisponible",
      mesure_impossible: true,
      contradicted: false,
      workspace: "C:/ws/illisible",
      created: [],
      modified: [],
      deleted: [],
      indetermines: ["secret.env"],
    };

    render(<VerificationReport v={illisible} />);

    expect(screen.getByText(/mesure impossible/i)).toBeInTheDocument();
    expect(screen.getByText(/C:\/ws\/illisible/)).toBeInTheDocument();
    expect(screen.queryByText(/aucune vérification disque/i)).toBeNull();
    expect(screen.queryByText(/confirmé sur le disque/i)).toBeNull();
  });

  it("affiche la preuve réelle quand la mesure a eu lieu et confirme la mission", () => {
    const verifiee: MissionVerification = {
      measured: true,
      verdict: "reussi",
      mesure_impossible: false,
      contradicted: false,
      workspace: "C:/ws/proof",
      created: ["proof.txt"],
      modified: [],
      deleted: [],
      indetermines: [],
      tests: { ran: false, reason: "aucun runner applicable" },
    };

    render(<VerificationReport v={verifiee} />);

    expect(screen.getByText(/confirmé sur le disque/i)).toBeInTheDocument();
    expect(screen.getByText(/1 fichier\(s\) touché\(s\)/i)).toBeInTheDocument();
    expect(screen.getByText("C:/ws/proof", { exact: false })).toBeInTheDocument();
  });

  it("signale les fichiers indéterminés au lieu de les compter comme du zéro", () => {
    const partielle: MissionVerification = {
      measured: true,
      verdict: "reussi",
      mesure_impossible: false,
      contradicted: false,
      workspace: "C:/ws/partiel",
      created: ["a.txt"],
      modified: [],
      deleted: [],
      indetermines: ["b.txt", "c.txt"],
    };

    render(<VerificationReport v={partielle} />);

    expect(screen.getByText("Indéterminés")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("n'affiche aucune ligne « Indéterminés » quand il n'y en a pas", () => {
    const propre: MissionVerification = {
      measured: true,
      verdict: "reussi",
      mesure_impossible: false,
      contradicted: false,
      workspace: "C:/ws/propre",
      created: ["a.txt"],
      modified: [],
      deleted: [],
      indetermines: [],
    };

    render(<VerificationReport v={propre} />);

    expect(screen.queryByText("Indéterminés")).toBeNull();
  });

  it("garde le bandeau d'alarme quand le disque contredit un succès annoncé", () => {
    const contredite: MissionVerification = {
      measured: true,
      verdict: "echoue",
      mesure_impossible: false,
      contradicted: true,
      workspace: "C:/ws/vide",
      created: [],
      modified: [],
      deleted: [],
      indetermines: [],
    };

    render(<VerificationReport v={contredite} />);

    expect(screen.getByText(/la mesure contredit ce rapport/i)).toBeInTheDocument();
  });
});
