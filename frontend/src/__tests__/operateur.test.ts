import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useCockpitStore } from "@/hooks/use-store";
import { POSTURES, type EtatOperateur } from "@/components/operateur";
import { TOPICS_SUIVIS, ETATS_DEDUITS } from "@/hooks/use-operateur";
import { ONGLETS_AVEC_OPERATEUR } from "@/components/operateur-de-garde";
import { ALL_NAV_ITEMS } from "@/components/nav-model";

/**
 * L'opérateur (HOS-182).
 *
 * Ces tests portent sur ce qui peut mentir en silence : une posture sans
 * dessin, un onglet qui n'existe plus, un signal local qui ne rend jamais
 * la main. Le fait que la posture corresponde à ce que fait vraiment le
 * système est gardé côté backend
 * (`test_topics_publies_sont_autorises.py` et
 * `test_table_operateur_pointe_sur_de_vrais_topics.py`) : c'est là que
 * vivent les vrais noms d'événements, et un test frontend qui les
 * recopierait ne prouverait que sa propre copie.
 */

beforeEach(() => {
  useCockpitStore.setState({
    activeView: "dashboard",
    liveEvents: [],
    operateurLocal: null,
    operateurVisible: true,
  });
});

describe("Postures", () => {
  it("chaque état déclaré a une posture dessinable", () => {
    // Le type énumère quinze états ; une posture manquante ferait rendre
    // `undefined` et l'opérateur disparaîtrait sans erreur.
    const etats = Object.keys(POSTURES) as EtatOperateur[];
    expect(etats.length).toBe(15);
    for (const e of etats) {
      const p = POSTURES[e];
      expect(p.libelle, `${e} sans libellé`).toBeTruthy();
      expect(p.teinte, `${e} sans teinte`).toMatch(/^#[0-9a-f]{6}$/i);
      expect(p.boucle, `${e} sans durée de boucle`).toBeTruthy();
      expect(p.bg, `${e} sans bras gauche`).toMatch(/^M/);
      expect(p.bd, `${e} sans bras droit`).toMatch(/^M/);
      expect(p.corps, `${e} sans boucle de corps`).toMatch(/^a-/);
    }
  });

  it("les teintes viennent du système SODIUM et pas d'ailleurs", () => {
    // Une teinte inventée passerait le test précédent tout en trahissant la
    // palette. Les six valeurs ci-dessous sont celles de globals.css.
    const PALETTE = new Set([
      "#ff9436", // sodium
      "#5eb8e8", // glacier
      "#9ede3a", // arc
      "#ffc93d", // gold
      "#ff5347", // alarm
      "#8695a6", // muted — le repos, qui n'est pas un signal
    ]);
    for (const [etat, p] of Object.entries(POSTURES)) {
      expect(PALETTE.has(p.teinte.toLowerCase()), `${etat} : ${p.teinte} hors palette`).toBe(true);
    }
  });

  it("le repos est la seule posture sans couleur de signal", () => {
    // Si une posture d'activité prenait le gris du repos, elle dirait
    // « rien ne se passe » en pleine activité.
    const gris = Object.entries(POSTURES).filter(([, p]) => p.teinte === "#8695a6");
    expect(gris.map(([e]) => e)).toEqual(["repos"]);
  });
});

describe("Onglets", () => {
  it("chaque onglet porteur existe dans la navigation", () => {
    // Un identifiant mal orthographié ferait disparaître l'opérateur d'un
    // onglet sans rien signaler — exactement le mode de panne qui a déjà
    // rendu huit Centers inatteignables.
    const connus = new Set(ALL_NAV_ITEMS.map((i) => i.id));
    for (const id of ONGLETS_AVEC_OPERATEUR) {
      expect(connus.has(id), `${id} n'est pas un onglet de la navigation`).toBe(true);
    }
  });

  it("couvre les trois onglets exigés", () => {
    for (const id of ["conversation", "missions", "autonomous"]) {
      expect(ONGLETS_AVEC_OPERATEUR.has(id)).toBe(true);
    }
  });

  it("laisse de côté les surfaces de référence", () => {
    // Rien ne s'y exécute : l'opérateur y serait un ornement.
    for (const id of ["governance", "security", "skills", "tools", "agents", "memory"]) {
      expect(ONGLETS_AVEC_OPERATEUR.has(id), `${id} ne devrait pas le porter`).toBe(false);
    }
  });
});

describe("Signal local", () => {
  afterEach(() => vi.useRealTimers());

  it("un onglet peut déclarer ce qu'il fait, avec une échéance", () => {
    const { result } = renderHook(() => useCockpitStore());
    act(() => result.current.signalerOperateur("ecriture", "réponse en cours", 5000));
    const local = result.current.operateurLocal;
    expect(local?.etat).toBe("ecriture");
    expect(local?.signal).toBe("réponse en cours");
    expect(local?.expire).toBeGreaterThan(Date.now());
  });

  it("l'échéance est absolue, pas une durée", () => {
    // Le shell compare, il ne décompte pas : une durée l'obligerait à
    // cadencer une horloge pour rien.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-26T12:00:00Z"));
    const { result } = renderHook(() => useCockpitStore());
    act(() => result.current.signalerOperateur("lecture", "test", 3000));
    expect(result.current.operateurLocal?.expire).toBe(Date.parse("2026-08-26T12:00:03Z"));
  });

  it("rendre la main efface l'affirmation", () => {
    const { result } = renderHook(() => useCockpitStore());
    act(() => result.current.signalerOperateur("parole", "synthèse", 60000));
    act(() => result.current.tairelOperateur());
    expect(result.current.operateurLocal).toBeNull();
  });

  it("un onglet qui oublie de se taire ne ment pas indéfiniment", () => {
    // La tenue par défaut borne l'affirmation : c'est ce qui empêche un
    // flux interrompu sans prévenir de laisser l'opérateur écrire pour
    // toujours.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-26T12:00:00Z"));
    const { result } = renderHook(() => useCockpitStore());
    act(() => result.current.signalerOperateur("reflexion", "flux ouvert"));
    const expire = result.current.operateurLocal!.expire;
    expect(expire - Date.now()).toBeLessThanOrEqual(30000);
    expect(expire).toBeGreaterThan(Date.now());
  });
});

describe("Table des signaux", () => {
  it("ne contient que des topics pointés", () => {
    // Un topic sans point n'est pas un topic : ce serait une catégorie,
    // et la liste blanche du backend refuse nommément les catégories nues.
    for (const t of TOPICS_SUIVIS) {
      expect(t, `${t} n'a pas la forme d'un topic`).toMatch(/^[a-z_]+\.[a-z_.]+$/);
    }
  });

  it("couvre les familles qui décrivent une activité de mission", () => {
    const familles = new Set(TOPICS_SUIVIS.map((t) => t.split(".")[0]));
    for (const f of ["filesystem", "execution", "task", "autonomous", "model", "runtime"]) {
      expect(familles.has(f), `aucun topic ${f}.*`).toBe(true);
    }
  });

  it("n'invente pas de posture pour la voix", () => {
    // Aucun des 125 topics du backend ne décrit une vérification en cours
    // ni une campagne de tests. Les câbler sur une approximation serait le
    // genre de vraisemblance que ce projet refuse : elles ne s'atteignent
    // que par signalerOperateur(), depuis un Center qui sait ce qu'il
    // déclenche.
    //
    // `filesystem.verification_failed` existe bien, mais il décrit un
    // échec constaté — il produit « défaut », pas « vérification ».
    expect(ETATS_DEDUITS.has("ecoute")).toBe(false);
    expect(ETATS_DEDUITS.has("parole")).toBe(false);
  });

  it("vérification et tests sont désormais déduits d'un vrai signal", () => {
    // Elles ne l'étaient pas : dessinées, testées, inatteignables. Plutôt
    // que de les câbler sur une approximation, le signal manquant a été
    // ajouté côté backend (HOS-184) — `verification.py` publie six topics
    // et sépare une suite de tests d'un passage de linter.
    expect(ETATS_DEDUITS.has("verification")).toBe(true);
    expect(ETATS_DEDUITS.has("tests")).toBe(true);
    expect(TOPICS_SUIVIS).toContain("verification.test.started");
    expect(TOPICS_SUIVIS).toContain("verification.check.started");
  });

  it("toute posture déduite d'un événement est dessinable", () => {
    for (const e of ETATS_DEDUITS) {
      expect(POSTURES[e], `${e} déduite mais non dessinée`).toBeDefined();
    }
  });
});
