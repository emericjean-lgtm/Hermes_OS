"use client";

import { useState } from "react";
import { CenterHeader, CenterTabs } from "@/components/center-scaffold";
import { RuntimeCenter } from "./runtime-center";
import { MonitoringCenter } from "@/features/monitoring/monitoring-center";
import { EventsCenter } from "@/features/events/events-center";
import DeploymentCenter from "@/features/deployment/deployment-center";

/**
 * Runtime Center (HOS-177).
 *
 * Quatre onglets décrivaient la même chose sous quatre titres :
 *
 *   runtime      runtimes enregistrés, modèles chargés, ressources
 *   monitoring   flux temps réel, journal runtime, allocations
 *   deployment   RAM totale, RAM utilisée, état RAM, GPU
 *   events       flux d'événements
 *
 * « Deployment » n'affichait aucun déploiement : quatre cartes de mémoire
 * et une de GPU, c'est-à-dire du runtime sous un nom qui promettait autre
 * chose. Un opérateur cherchant « combien de VRAM reste-t-il » avait trois
 * onglets candidats et aucune raison d'en préférer un.
 *
 * Les quatre vues sont conservées, sous un seul onglet et quatre sections.
 * Rien n'est perdu ; ce qui disparaît, c'est l'obligation de deviner
 * laquelle regarder.
 */

type Vue = "ressources" | "flux" | "evenements" | "memoire";

const VUES: { id: Vue; label: string }[] = [
  { id: "ressources", label: "Ressources" },
  { id: "flux", label: "Flux temps réel" },
  { id: "evenements", label: "Événements" },
  { id: "memoire", label: "Mémoire & GPU" },
];

export function RuntimeCenterMerged() {
  const [vue, setVue] = useState<Vue>("ressources");

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Runtime Center"
        subtitle="Modèles chargés, ressources, flux d'événements et empreinte matérielle"
        right={
          <CenterTabs<Vue> tabs={VUES} active={vue} onChange={setVue} />
        }
      />
      {vue === "ressources" && <RuntimeCenter imbrique />}
      {vue === "flux" && <MonitoringCenter imbrique />}
      {vue === "evenements" && <EventsCenter imbrique />}
      {vue === "memoire" && <DeploymentCenter imbrique />}
    </div>
  );
}

export default RuntimeCenterMerged;
