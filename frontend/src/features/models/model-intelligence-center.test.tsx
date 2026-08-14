import { describe, expect, it } from "vitest";
import { ligneDeDetail, noteColor } from "./model-intelligence-center";

/**
 * Le catalogue mesuré affiche des heures de GPU. Un rendu qui se trompe de
 * clé transforme une réussite en échec sans que rien ne le signale — la
 * même classe de panne que les vérificateurs faux qui ont produit cinq
 * faux zéros pendant les campagnes, un cran plus loin dans la chaîne.
 */

describe("ligneDeDetail — les conventions de clés des campagnes", () => {
  it("lit le verdict français de l'extraction", () => {
    // L'incident : le rendu ne lisait que `passed`. L'extraction écrit
    // `reussi`. gpt-oss, noté 100/100 avec ses cinq niveaux réussis,
    // s'affichait avec cinq croix rouges.
    const l = ligneDeDetail({ niveau: "arbitrage", reussi: true, detail: "conforme" }, 0);

    expect(l.ok).toBe(true);
    expect(l.nom).toBe("arbitrage");
    expect(l.note).toBe("conforme");
  });

  it("lit le verdict anglais du code", () => {
    const l = ligneDeDetail(
      { task: "compter_mots", level: "mythique", passed: false, detail: "SyntaxError" },
      0,
    );

    expect(l.ok).toBe(false);
    expect(l.nom).toBe("mythique");
    expect(l.note).toBe("SyntaxError");
  });

  it("lit `trouve` du long contexte et nomme la sonde par sa profondeur", () => {
    const l = ligneDeDetail(
      { contexte: 65536, profondeur: 0.95, trouve: true, secondes: 171.3, detail: "retrouvée" },
      0,
    );

    expect(l.ok).toBe(true);
    expect(l.nom).toBe("64k · profondeur 95 %");
    expect(l.duree).toBe(171.3);
  });

  it("dit que l'artefact agentique a été vérifié sur le disque", () => {
    // La discipline du projet : `success: true` ne prouve rien, seul
    // `artifact_verified` le fait. L'affichage doit porter la distinction.
    const l = ligneDeDetail(
      { success: true, tool_calls: 2, artifact_verified: true, duration_s: 56.5 },
      0,
    );

    expect(l.ok).toBe(true);
    expect(l.note).toContain("artefact vérifié sur disque");
  });

  it("n'annonce pas d'artefact vérifié quand il ne l'a pas été", () => {
    const l = ligneDeDetail({ success: true, tool_calls: 1, artifact_verified: false }, 0);

    expect(l.note).toBe("1 appel d'outil");
  });

  it("montre ce que le modèle a répondu quand une épreuve échoue", () => {
    const l = ligneDeDetail(
      { epreuve: "arithmetique", reussi: false, attendu: "479", recu: "La réponse est 475." },
      0,
    );

    expect(l.note).toContain("attendu 479");
    expect(l.note).toContain("475");
  });

  it("laisse `ok` indéfini quand aucune clé connue ne porte le verdict", () => {
    // Une information absente ne doit pas s'afficher comme un échec : le
    // rendu montre alors un point neutre, jamais une croix rouge.
    const l = ligneDeDetail({ quelque_chose: "de nouveau" }, 3);

    expect(l.ok).toBeUndefined();
    expect(l.nom).toBe("essai 4");
  });
});

describe("noteColor — non mesuré n'est pas zéro", () => {
  it("rend une couleur neutre pour un axe non mesuré", () => {
    expect(noteColor(null)).toBe("text-hermes-muted");
    expect(noteColor(undefined)).toBe("text-hermes-muted");
  });

  it("rend le rouge pour un zéro réellement mesuré", () => {
    // Le piège symétrique : 0 est une mesure, et doit se voir comme telle.
    expect(noteColor(0)).toBe("text-hermes-red");
  });

  it("gradue les notes du rouge au vert", () => {
    expect(noteColor(20)).toBe("text-hermes-red");
    expect(noteColor(33)).toBe("text-hermes-amber");
    expect(noteColor(67)).toBe("text-hermes-cyan");
    expect(noteColor(100)).toBe("text-hermes-green");
  });
});
