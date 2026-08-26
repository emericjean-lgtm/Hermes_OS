"use client";

import { useEffect } from "react";
import { useWebSocket } from "@/hooks/use-websocket";
import { useCockpitStore } from "@/hooks/use-store";

/**
 * La seule souscription au bus d'événements (HOS-182).
 *
 * Le store portait `liveEvents`, `addLiveEvent` et `wsConnected` depuis le
 * début — et **rien ne les alimentait**. `addLiveEvent` n'était appelé que
 * par les tests. Conséquences visibles, et qui étaient là depuis
 * longtemps : le compteur `EVT` de la barre d'état affichait `0` en
 * permanence, et sa ligne d'événement disait « Aucun événement reçu » quoi
 * qu'il arrive. Le Dashboard, lui, ouvrait sa propre socket dans son coin.
 *
 * Ce composant ne rend rien. Il est monté une fois par le shell, hors de
 * l'arbre des Centers, et pousse dans le store ce qui arrive. Trois
 * surfaces s'en servent désormais — la barre d'état, le Dashboard et
 * l'opérateur — pour une seule connexion au lieu d'une par consommateur.
 *
 * Monté inconditionnellement, et c'est le point : l'opérateur n'apparaît
 * que sur certains onglets, mais le flux doit continuer d'arriver quand on
 * regarde ailleurs, sinon la posture affichée à l'arrivée sur l'onglet
 * serait celle d'un système qu'on vient de cesser d'écouter.
 */
export function FluxEvenements() {
  const addLiveEvent = useCockpitStore((s) => s.addLiveEvent);
  const setWsConnected = useCockpitStore((s) => s.setWsConnected);

  const { connected } = useWebSocket({ onEvent: addLiveEvent });

  useEffect(() => {
    setWsConnected(connected);
  }, [connected, setWsConnected]);

  return null;
}
