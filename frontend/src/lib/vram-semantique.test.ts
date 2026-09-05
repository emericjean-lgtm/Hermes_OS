/** Une carte non mesurée ne s'affiche pas comme une carte au repos (A-15).
 *
 *  Le backend distingue depuis A-15 trois états : carte absente, carte
 *  mesurée, et carte présente dont aucune sonde n'a lu l'occupation. Dans
 *  ce dernier cas il rend `vram_used_bytes: 0` **par prudence** — un
 *  chiffre qu'il ne faut pas lire.
 *
 *  Sans ces aides, le Cockpit affichait « 0,0 / 16,0 Gio » et une jauge à
 *  0 % pour une carte que personne ne savait lire. C'est la confusion que
 *  A-15 corrige un étage plus bas, reproduite à l'écran.
 */
import { describe, expect, it } from "vitest";

import { formatGio, formatGioPair, vramLibre, vramMesuree, vramOccupee, vramPourcent } from "./format";

const CARTE = 17163091968; // RX 6800, la vraie capacité

const mesuree = {
  vram_total_bytes: CARTE,
  vram_used_bytes: 16232152268,
  vram_free_bytes: 930939700,
  available: true,
  occupation_mesuree: true,
};

const nonMesuree = {
  vram_total_bytes: CARTE,
  vram_used_bytes: 0,
  vram_free_bytes: 0,
  available: true,
  occupation_mesuree: false,
};

const absente = {
  vram_total_bytes: 0,
  vram_used_bytes: 0,
  vram_free_bytes: 0,
  available: false,
};

describe("sémantique VRAM", () => {
  it("laisse passer une mesure réelle", () => {
    expect(vramMesuree(mesuree)).toBe(true);
    expect(vramOccupee(mesuree)).toBe(16232152268);
    expect(vramPourcent(mesuree)).toBeCloseTo(94.6, 1);
  });

  it("refuse de rendre un chiffre pour une carte non mesurée", () => {
    expect(vramMesuree(nonMesuree)).toBe(false);
    expect(vramOccupee(nonMesuree)).toBeNull();
    expect(vramLibre(nonMesuree)).toBeNull();
    expect(vramPourcent(nonMesuree)).toBeNull();
  });

  it("affiche l'absence comme absente, jamais comme un zéro", () => {
    // C'est la ligne que voit l'opérateur : « — / 15.98 Gio », pas
    // « 0.0 / 15.98 Gio », qui se lit « la carte est libre ».
    expect(formatGioPair(vramOccupee(nonMesuree), nonMesuree.vram_total_bytes))
      .toBe("— / 16.0 Gio");
    expect(formatGio(vramLibre(nonMesuree))).toBe("—");
  });

  it("traite une carte absente comme non mesurée", () => {
    expect(vramMesuree(absente)).toBe(false);
    expect(vramPourcent(absente)).toBeNull();
  });

  it("traite une réponse antérieure au drapeau comme mesurée", () => {
    // Le champ est optionnel : un backend qui ne le rend pas encore
    // mesurait bien quelque chose sur toutes ses sources.
    const ancienne = { ...mesuree } as Record<string, unknown>;
    delete ancienne.occupation_mesuree;
    expect(vramMesuree(ancienne as typeof mesuree)).toBe(true);
  });

  it("ne se laisse pas piéger par une absence d'objet", () => {
    expect(vramMesuree(null)).toBe(false);
    expect(vramOccupee(undefined)).toBeNull();
  });
});
