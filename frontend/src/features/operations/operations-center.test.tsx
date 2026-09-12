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
import { fireEvent, render, screen } from "@testing-library/react";

import { Cause, OperationsCenter } from "./operations-center";

// Le hook est simulé : ces gardes portent sur ce que la vue **fait des
// données**, pas sur le transport, qui a ses propres gardes côté Python.
const apercu = vi.hoisted(() => ({ valeur: {} as Record<string, unknown> }));

const salles = vi.hoisted(() => ({ valeur: undefined as unknown }));

/** L'aperçu d'un point de reprise et le résultat d'une restauration
 *  (HOS-291). Simulés comme le reste : ces gardes portent sur ce que la
 *  vue **dit** d'un refus et d'une suppression, pas sur le transport. */
const apercuPoint = vi.hoisted(() => ({ valeur: undefined as unknown }));
const restauration = vi.hoisted(() => ({
  valeur: undefined as unknown,
  appels: [] as unknown[],
}));

// `undefined` par défaut : le détail d'un run n'est rendu que sur
// sélection, et un hook simulé qui rendrait des données par défaut ferait
// croire à un affichage qu'on ne mesure pas. Les gardes qui déplient un
// run réassignent `lignee.valeur` avant de rendre.
const lignee = vi.hoisted(() => ({ valeur: undefined as unknown }));

vi.mock("@/hooks/use-api", () => ({
  useOperationsApercu: () => ({
    data: apercu.valeur,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useControlRooms: () => ({
    data: salles.valeur,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useOperationsLignee: () => ({ data: lignee.valeur }),
  useOperationsContrat: () => ({ data: undefined }),
  useApercuCheckpoint: () => ({
    data: apercuPoint.valeur,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useRestaurerCheckpoint: () => ({
    data: restauration.valeur,
    isPending: false,
    isError: false,
    error: null,
    mutate: (args: unknown) => restauration.appels.push(args),
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

describe("les Control Rooms ne fabriquent aucun taux", () => {
  it("affiche « jamais mesuré » plutôt que 100 % sur zéro tâche", async () => {
    const { ControlRoom } = await import("./operations-center");
    render(
      <ControlRoom
        salle={{
          agent: "atlas",
          identite: { status: "ready", capabilities: ["code_generation"] },
          connu: true,
          runs_en_cours: [],
          reussite: {
            mesure: false,
            taux: null,
            total: 0,
            detail: "aucune tâche exécutée — rien à mesurer",
          },
          confiance: { score: null, niveau: null },
        }}
      />,
    );
    expect(screen.getByText(/jamais mesuré/)).toBeTruthy();
    expect(screen.queryByText(/100%/)).toBeNull();
    // La confiance dit déjà « unknown » quand elle ne sait pas : on la
    // relaie, on ne l'interprète pas.
    expect(screen.getByText(/non disponible/)).toBeTruthy();
  });

  it("affiche un taux réel quand il est mesuré", async () => {
    const { ControlRoom } = await import("./operations-center");
    render(
      <ControlRoom
        salle={{
          agent: "atlas",
          identite: { status: "ready", capabilities: [] },
          connu: true,
          runs_en_cours: [],
          reussite: { mesure: true, taux: 75, total: 4, detail: "3/4" },
          confiance: { score: 80, niveau: "trusted" },
        }}
      />,
    );
    expect(screen.getByText(/75%/)).toBeTruthy();
    expect(screen.getByText(/80\/100/)).toBeTruthy();
  });

  it("dit qu'un agent inconnu est une absence, pas un agent vide", async () => {
    const { ControlRoom } = await import("./operations-center");
    render(
      <ControlRoom
        salle={{
          agent: "jamais-vu",
          identite: null,
          connu: false,
          runs_en_cours: [],
          reussite: { mesure: false, taux: null, total: 0, detail: "" },
          confiance: { score: null, niveau: null },
        }}
      />,
    );
    expect(screen.getByText(/inconnu du superviseur/)).toBeTruthy();
  });
});


// ═══ Revenir en arrière, et ce que l'écran en dit (A-3, HOS-291) ═════

describe("les points de reprise", () => {
  const POINT = {
    identifiant: "3e9bc4d387ec",
    workspace: "C:/ws/projet",
    motif: "avant la mission : refonte",
    mission: "m-1",
    run: "",
    mecanisme: "fichiers",
    fichiers: 2,
    cree_le: "2026-09-11T18:00:00Z",
    avec_etat: false,
  };

  function monter(etat: Record<string, unknown> = {}) {
    apercu.valeur = { ...VIDE, points_de_reprise: bloc([POINT], "backend.checkpoints") };
    apercuPoint.valeur = etat.apercu;
    restauration.valeur = etat.restauration;
    restauration.appels = [];
    return render(<OperationsCenter />);
  }

  it("déplie l'aperçu et met en avant ce qui sera détruit", async () => {
    monter({
      apercu: {
        checkpoint: POINT.identifiant,
        workspace: POINT.workspace,
        a_restaurer: ["src/app.py"],
        a_recreer: ["LISEZMOI.md"],
        a_supprimer: ["src/genere_apres.py"],
        vide: false,
        resume: "1 à réécrire, 1 à recréer, **1 à supprimer**",
        applique: false,
      },
    });

    fireEvent.click(screen.getByText(/avant la mission/));

    // La liste destructive est nommée à part, jamais fondue dans un
    // compteur : c'est la seule des trois qui détruise du travail.
    // Deux endroits le disent — le résumé et le badge d'alarme — et
    // c'est voulu : le compte destructif ne doit pas dépendre d'un seul
    // élément qu'un remaniement pourrait retirer sans qu'on le voie.
    expect(screen.getAllByText(/1 à supprimer/).length).toBeGreaterThan(0);
    expect(screen.getByText(/src\/genere_apres\.py/)).toBeInTheDocument();
  });

  it("dit « accord à décider », pas « refusé », quand Aegis attend un humain", () => {
    monter({
      apercu: {
        checkpoint: POINT.identifiant, workspace: POINT.workspace,
        a_restaurer: ["src/app.py"], a_recreer: [], a_supprimer: [],
        vide: false, resume: "1 à réécrire", applique: false,
      },
      restauration: {
        restaure: false, checkpoint: POINT.identifiant,
        verdict: "require_human_validation",
        motif: "data_migration always requires human validation",
        accord_a_decider: true,
        a_restaurer: [], a_recreer: [], a_supprimer: [],
        etat_repris: false, etat_non_repris: "",
      },
    });

    fireEvent.click(screen.getByText(/avant la mission/));

    // Le défaut que cette garde empêche : afficher « échec » sur une
    // gouvernance qui fonctionne. L'opérateur conclurait que la
    // restauration est cassée au moment précis où elle marche, et
    // cesserait d'essayer au lieu d'aller décider l'accord.
    expect(screen.getByText(/Accord à décider/)).toBeInTheDocument();
    expect(screen.queryByText(/^Refusé/)).not.toBeInTheDocument();
  });

  it("ne tait pas un état de mission non repris", () => {
    monter({
      apercu: {
        checkpoint: POINT.identifiant, workspace: POINT.workspace,
        a_restaurer: ["src/app.py"], a_recreer: [], a_supprimer: [],
        vide: false, resume: "1 à réécrire", applique: false,
      },
      restauration: {
        restaure: true, checkpoint: POINT.identifiant, workspace: POINT.workspace,
        verdict: "allow", motif: "", accord_a_decider: false,
        a_restaurer: ["src/app.py"], a_recreer: [], a_supprimer: [],
        etat_repris: false,
        etat_non_repris: "restauration de l'état refusée : un accord distinct a été déposé",
        resume: "1 à réécrire",
      },
    });

    fireEvent.click(screen.getByText(/avant la mission/));

    // Un point de reprise sans son état ne ramène que la moitié
    // (HOS-223). Un succès partiel silencieux ferait repartir d'un état
    // que l'opérateur croit revenu.
    expect(screen.getByText(/Restauré/)).toBeInTheDocument();
    expect(screen.getByText(/état non repris/)).toBeInTheDocument();
  });
});

// ═══ §15.5 — explicabilité et ressources d'un run ═══════════════════
//
// `Run.decision` (HOS-242) et la comptabilité physique R-6 existaient
// déjà côté registre et transitaient déjà par `/operations/.../lignee` —
// aucune ligne du Cockpit ne les lisait. Ces gardes portent sur le
// dernier pas : la vue affiche ce que le backend a mesuré, jamais plus,
// jamais un zéro à la place d'un « non mesuré ».

function run(partiel: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    identifiant: "r-1234567890",
    mission: "m-1",
    objectif: "objectif",
    statut: "reussi",
    cause: null,
    raison: "",
    modele: "qwen3.6-35b",
    runtime: "ollama",
    fournisseur: "",
    agent: "atlas",
    workspace: "",
    projet: "",
    tentative: 1,
    parent: null,
    motif_de_reprise: "",
    jetons_entree: 0,
    jetons_sortie: 0,
    cout: 0,
    cree_le: "2026-09-12T00:00:00Z",
    demarre_le: null,
    fini_le: null,
    contrat: false,
    decision: "",
    vram_reservee_octets: null,
    vram_machine_debut_octets: null,
    vram_machine_pic_octets: null,
    exclusif: null,
    ...partiel,
  };
}

function ouvrirLeRun() {
  apercu.valeur = {
    ...VIDE,
    runs: bloc({ en_cours: [run()], nombre_en_cours: 1 }),
  };
  render(<OperationsCenter />);
  fireEvent.click(screen.getByText("objectif"));
}

describe("le routage et la consommation physique d'un run", () => {
  it("affiche le repli quand le routeur a dévié", () => {
    lignee.valeur = bloc(
      [
        run({
          decision: JSON.stringify({
            runtime_demande: "openrouter",
            runtime_servi: "ollama",
            modele: "qwen3.6-35b",
            repli: "openrouter indisponible, servi par ollama",
          }),
        }),
      ],
      "backend.runs.registre.lignee",
    );
    ouvrirLeRun();
    expect(
      screen.getByText(/openrouter indisponible, servi par ollama/),
    ).toBeTruthy();
  });

  it("ne dit rien quand le routeur a obtenu ce qu'il demandait", () => {
    lignee.valeur = bloc(
      [
        run({
          decision: JSON.stringify({
            runtime_demande: "ollama",
            runtime_servi: "ollama",
            modele: "qwen3.6-35b",
          }),
        }),
      ],
      "backend.runs.registre.lignee",
    );
    ouvrirLeRun();
    expect(screen.queryByText(/repli/)).toBeNull();
    expect(screen.queryByText(/substitution/)).toBeNull();
  });

  it("montre l'écart machine seulement quand le run était exclusif", () => {
    lignee.valeur = bloc(
      [
        run({
          vram_reservee_octets: 2 * 1024 ** 3,
          vram_machine_debut_octets: 4 * 1024 ** 3,
          vram_machine_pic_octets: 6 * 1024 ** 3,
          exclusif: true,
        }),
      ],
      "backend.runs.registre.lignee",
    );
    ouvrirLeRun();
    expect(screen.getAllByText(/réservé 2\.0 Gio/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/écart machine/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/exclusif, majorant/).length).toBeGreaterThan(0);
  });

  it("dit « non attribuable » plutôt que de montrer un écart partagé", () => {
    lignee.valeur = bloc(
      [
        run({
          vram_machine_debut_octets: 4 * 1024 ** 3,
          vram_machine_pic_octets: 9 * 1024 ** 3,
          exclusif: false,
        }),
      ],
      "backend.runs.registre.lignee",
    );
    ouvrirLeRun();
    expect(screen.getByText(/non attribuable — partagée avec un autre run/)).toBeTruthy();
    expect(screen.queryByText(/écart machine/)).toBeNull();
  });

  it("n'affiche rien — jamais un zéro — quand rien n'a été mesuré", () => {
    lignee.valeur = bloc([run()], "backend.runs.registre.lignee");
    ouvrirLeRun();
    expect(screen.queryByText(/réservé/)).toBeNull();
    expect(screen.queryByText(/écart machine/)).toBeNull();
    expect(screen.queryByText(/attribuable/)).toBeNull();
  });
});
