import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

/**
 * La surface d'API exposée et celle réellement empruntée (HOS-188).
 *
 * `use-api.ts` expose une centaine de hooks. Quatorze n'ont aucun
 * consommateur — et ils ne sont pas de même nature : certains sont des
 * chemins morts, d'autres des **capacités que le backend sert et qu'aucun
 * écran n'offre**. Supprimer les seconds effacerait la trace d'une
 * fonction manquante ; les laisser sans rien dire les rend invisibles
 * jusqu'à la prochaine relecture.
 *
 * Ce test les inscrit avec leur raison. Un hook ajouté sans consommateur
 * fait échouer la suite, ce qui force la décision au moment où elle est
 * facile à prendre plutôt que six mois plus tard. Un hook enfin branché la
 * fait échouer aussi : il faut alors le retirer de la liste, et c'est très
 * bien — c'est la dette qui diminue.
 *
 * Ce n'est pas une exemption : c'est un inventaire daté qui refuse de
 * grossir en silence.
 */

/** Pourquoi chacun n'est pas branché, et ce qu'il faudrait pour l'être. */
const SANS_CONSOMMATEUR: Record<string, string> = {
  // ── Capacités réelles qu'aucun écran n'offre ──
  useCreateAgent:
    "aucun écran ne crée d'agent — les six sont amorcés au démarrage",
  useStartExecution:
    "les exécutions naissent d'une mission ; démarrer une exécution nue " +
    "est un chemin hérité dont la sémantique n'a pas été établie",
  useConversationDecision:
    "l'approbation d'une action en conversation existe côté serveur, " +
    "sans interface — c'est la posture « décision attendue » de l'opérateur",
  useSelectSkills:
    "la sélection de compétences pour une tâche n'est offerte nulle part",

  // ── Détails dont le Center montre déjà le résumé ──
  useAgent: "l'Agent Center liste ; il n'a pas de vue de détail",
  useExecution:
    "l'Execution Center liste les exécutions ; il n'a pas de vue de détail",
  useRuntimeHealth: "le Runtime Center lit les ressources, pas ce résumé",
  useEvolutionStatus: "l'Evolution Center affiche propositions et rapports",
  useSecurityEvents: "le Security Center affiche menaces et permissions",
  useSkillCache: "le Skills Center montre les compétences, pas son cache",
  useSendMessage: "la messagerie inter-agents n'a pas d'écran",

  // ── Capacités d'agents spécialisés, sans surface dédiée ──
  useCodeIntelligenceCapabilities:
    "le Code Intel Center affiche les fournisseurs, pas les capacités",
  useKlaatCodeCapabilities:
    "aucun écran ne présente KlaatCode séparément des autres agents",
  useOhMyPiCapabilities:
    "aucun écran ne présente OhMyPi séparément des autres agents",
};

function lire(relatif: string): string {
  return fs.readFileSync(path.resolve(__dirname, "..", relatif), "utf-8");
}

function hooksExposes(): string[] {
  const source = lire("hooks/use-api.ts");
  return [...source.matchAll(/^export function (use\w+)/gm)].map((m) => m[1]);
}

function hooksConsommes(exposes: string[]): Set<string> {
  // Tout le code source sauf la déclaration elle-même : un hook qui ne
  // s'appelle que dans le fichier qui le définit n'est pas consommé.
  const racine = path.resolve(__dirname, "..");
  const corpus: string[] = [];
  const parcourir = (dossier: string) => {
    for (const e of fs.readdirSync(dossier, { withFileTypes: true })) {
      const p = path.join(dossier, e.name);
      if (e.isDirectory()) {
        // `__tests__` est exclu, et c'est le coeur de la mesure : ce
        // fichier-ci nomme les quatorze hooks, et les compter comme des
        // usages les declarait tous branches. « Consomme » veut dire
        // consomme par l'application, pas mentionne quelque part.
        if (e.name !== "node_modules" && e.name !== "__tests__") parcourir(p);
      } else if (/\.tsx?$/.test(e.name) && !p.endsWith(path.join("hooks", "use-api.ts"))) {
        corpus.push(fs.readFileSync(p, "utf-8"));
      }
    }
  };
  parcourir(racine);
  const tout = corpus.join("\n");
  return new Set(exposes.filter((h) => new RegExp(`\\b${h}\\b`).test(tout)));
}

describe("Surface d'API", () => {
  it("n'expose aucun hook inutilisé qui ne soit pas inscrit", () => {
    const exposes = hooksExposes();
    expect(exposes.length).toBeGreaterThan(80);

    const consommes = hooksConsommes(exposes);
    const orphelins = exposes.filter((h) => !consommes.has(h));
    const nonInscrits = orphelins.filter((h) => !(h in SANS_CONSOMMATEUR));

    expect(
      nonInscrits,
      "Ces hooks n'ont aucun consommateur et ne figurent pas dans " +
        "l'inventaire. Branchez-les, retirez-les, ou inscrivez-les avec " +
        "la raison — mais décidez maintenant.",
    ).toEqual([]);
  });

  it("n'inscrit aucun hook qui aurait été branché depuis", () => {
    // Le sens inverse compte autant : un hook branché puis laissé dans
    // l'inventaire ferait croire à une lacune résolue depuis longtemps.
    const exposes = hooksExposes();
    const consommes = hooksConsommes(exposes);
    const perimes = Object.keys(SANS_CONSOMMATEUR).filter((h) => consommes.has(h));

    expect(
      perimes,
      "Ces hooks sont désormais utilisés : retirez-les de l'inventaire.",
    ).toEqual([]);
  });

  it("n'inscrit aucun hook qui n'existe plus", () => {
    const exposes = new Set(hooksExposes());
    const fantomes = Object.keys(SANS_CONSOMMATEUR).filter((h) => !exposes.has(h));

    expect(
      fantomes,
      "Ces hooks ont été supprimés : retirez-les de l'inventaire.",
    ).toEqual([]);
  });

  it("donne une raison à chaque inscription", () => {
    // Une entrée sans raison est une exemption déguisée.
    for (const [hook, raison] of Object.entries(SANS_CONSOMMATEUR)) {
      expect(raison.length, `${hook} : raison trop courte`).toBeGreaterThan(25);
    }
  });
});
