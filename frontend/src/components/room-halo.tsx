"use client";

import { useEffect } from "react";

/**
 * Le halo qui suit le curseur (HOS-197).
 *
 * La direction retenue (`.design/cockpit/Main.dc.html`) fait de la pièce
 * une source de lumière mobile : le halo sodium suit la souris, et la
 * grille technique ne se révèle que là où il tombe. L'ancienne version
 * était la même pièce, mais figée à une position — l'écart concret entre
 * « seul l'opérateur a été mis en place » (faux, vérifié) et ce qui
 * manquait réellement.
 *
 * ## Pourquoi un composant à part, sans rendu
 *
 * Il n'écrit rien dans le DOM (`return null`) : `body::before`/`::after`
 * dans `globals.css` restent les seules couches qui peignent la pièce.
 * Ce composant ne fait qu'écrire deux variables CSS sur la racine — la
 * même technique que `rail.tsx` pour `--rail-w`, pour la même raison :
 * plusieurs règles CSS indépendantes doivent suivre la même valeur sans
 * qu'aucune ne devienne la source de vérité d'une autre.
 *
 * ## Pourquoi `requestAnimationFrame` et pas un `setState`
 *
 * `mousemove` tire des dizaines de fois par seconde. Passer par `setState`
 * redéclencherait un rendu React à chaque événement pour ne changer, au
 * fond, qu'un style inline sur `<html>` — `CenterBoundary`/`AnimatePresence`
 * en ont déjà assez sans ajouter un re-rendu de plus par mouvement de
 * souris. Écrire directement la variable CSS, une fois par frame au plus,
 * est le chemin le plus court entre l'événement et l'effet visuel.
 */
export function RoomHalo() {
  useEffect(() => {
    const racine = document.documentElement;
    let planifie = false;
    let dernierEvenement: MouseEvent | null = null;

    const appliquer = () => {
      planifie = false;
      const e = dernierEvenement;
      if (!e) return;
      const mx = ((e.clientX / window.innerWidth) * 100).toFixed(1) + "%";
      const my = ((e.clientY / window.innerHeight) * 100).toFixed(1) + "%";
      racine.style.setProperty("--room-mx", mx);
      racine.style.setProperty("--room-my", my);
    };

    const onMouseMove = (e: MouseEvent) => {
      dernierEvenement = e;
      if (!planifie) {
        planifie = true;
        requestAnimationFrame(appliquer);
      }
    };

    window.addEventListener("mousemove", onMouseMove, { passive: true });
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      // Rendre la main aux valeurs par défaut de globals.css plutôt que de
      // laisser la pièce figée sur la dernière position connue si ce
      // composant est un jour démonté sans que l'application le soit.
      racine.style.removeProperty("--room-mx");
      racine.style.removeProperty("--room-my");
    };
  }, []);

  return null;
}

export default RoomHalo;
