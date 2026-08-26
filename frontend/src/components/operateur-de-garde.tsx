"use client";

import { Operateur } from "@/components/operateur";
import { useOperateur } from "@/hooks/use-operateur";
import { useCockpitStore } from "@/hooks/use-store";

/**
 * L'opérateur, posé dans la pièce (HOS-182).
 *
 * ## Pourquoi dans le shell et non dans chaque Center
 *
 * Parce qu'une animation CSS repart de zéro quand son élément est démonté.
 * Le shell démonte le Center actif à chaque bascule d'onglet ; un opérateur
 * placé à l'intérieur recommencerait son geste à chaque fois qu'on change
 * de vue, ce qui reviendrait à dire que le système vient de recommencer sa
 * tâche. Ici il traverse les bascules sans s'interrompre — ce qui est
 * exact, puisque le système, lui, ne s'est pas interrompu.
 *
 * ## Où il apparaît
 *
 * Sur les onglets où le système *agit* pour vous, ou bien où l'on peut le
 * voir agir. Ailleurs — annuaires d'agents, règles de gouvernance, listes
 * de compétences — il n'aurait rien à dire, et une figure qui n'a rien à
 * dire redevient un ornement.
 *
 * ## Sans cadre
 *
 * Ce qui le rattache à la pièce est une flaque de lumière au sol, de la
 * teinte de son état. Pas de boîte, pas de bouton : la posture est le
 * message, et l'étiquette n'est là que pour nommer le signal qui l'a
 * produite — il faut pouvoir vérifier *pourquoi* il fait ce qu'il fait.
 */

/** Les onglets où il a quelque chose à dire.
 *
 *  Onze sur dix-huit. Les sept absents (agents, memory, skills, tools,
 *  governance, security, evolution, system) sont des surfaces de référence
 *  ou de configuration : rien ne s'y exécute, et l'opérateur y serait une
 *  décoration — précisément ce que ce cockpit s'interdit. */
export const ONGLETS_AVEC_OPERATEUR: ReadonlySet<string> = new Set([
  "dashboard",
  "conversation",
  "voice",
  "missions",
  "execution",
  "autonomous",
  "runtime",
  "workspace",
  "validation",
  "models",
  "code_intelligence",
]);

export function OperateurDeGarde() {
  const activeView = useCockpitStore((s) => s.activeView);
  const visible = useCockpitStore((s) => s.operateurVisible);
  const { etat, libelle, teinte, signal } = useOperateur();

  if (!visible || !ONGLETS_AVEC_OPERATEUR.has(activeView)) return null;

  return (
    <div
      // `hidden xl:block` : sous 1280 px, la figure mordrait sur le contenu.
      // Mieux vaut qu'elle disparaisse que de gêner la lecture d'un tableau.
      className="pointer-events-none fixed right-5 z-20 hidden xl:block select-none"
      style={{ bottom: "calc(var(--foot-h) + 2px)", ["--teinte-operateur" as string]: teinte }}
      aria-live="polite"
    >
      <div className="relative flex items-end gap-3">
        <div className="pb-6 text-right">
          <div
            className="num text-[11px] leading-tight tracking-[0.04em] transition-colors duration-300"
            style={{ color: teinte }}
          >
            {libelle}
          </div>
          <div className="tech-label mt-1 !text-[8.5px]">{signal}</div>
        </div>

        <div className="relative">
          <div className="operateur-flaque" />
          <Operateur etat={etat} taille={132} />
        </div>
      </div>
    </div>
  );
}
