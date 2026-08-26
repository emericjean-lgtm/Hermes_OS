"use client";

import { useState } from "react";
import { CenterHeader, CenterTabs } from "@/components/center-scaffold";
import { SystemCenter } from "./system-center";
import { HealthCenter } from "@/features/health/health-center";

/**
 * System Center (HOS-177).
 *
 * `system` et `health` décrivaient le même objet — les sous-systèmes de
 * Hermes OS — par deux écrans séparés : l'un l'inventaire et le graphe de
 * dépendances, l'autre la santé et le rapport du composition root. Un
 * opérateur qui voulait savoir « ce composant va-t-il bien, et de quoi
 * dépend-il ? » devait traverser deux onglets.
 *
 * Les deux vues sont conservées telles quelles, sous un seul onglet. Les
 * fondre en un écran unique aurait demandé de réécrire six cents lignes
 * pour un gain d'ergonomie que deux onglets donnent déjà.
 */

type Vue = "sante" | "composants";

export function SystemCenterMerged() {
  const [vue, setVue] = useState<Vue>("sante");

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="System Center"
        subtitle="Santé des sous-systèmes, inventaire des composants et graphe de dépendances"
        right={
          <CenterTabs<Vue>
            tabs={[
              { id: "sante", label: "Santé" },
              { id: "composants", label: "Composants" },
            ]}
            active={vue}
            onChange={setVue}
          />
        }
      />
      {/* `imbrique` supprime l'en-tête des deux vues : le titre et les
          onglets vivent ici, et deux en-têtes empilés donneraient un titre
          en double. */}
      {vue === "sante" ? <HealthCenter imbrique /> : <SystemCenter imbrique />}
    </div>
  );
}

export default SystemCenterMerged;
