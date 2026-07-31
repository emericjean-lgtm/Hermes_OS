"use client";

import React, { useState } from "react";

/** Confirmation explicite avant une action irréversible.
 *
 *  Simuler, appliquer ou annuler une proposition d'évolution modifie le système ;
 *  supprimer un espace de travail détruit son contenu ; révoquer une permission
 *  change la posture de sécurité. Aucune de ces actions ne doit partir sur un
 *  simple clic (P-002 §5).
 *
 *  La confirmation est locale à l'interface : elle **ne remplace pas** les
 *  systèmes Policy / Security / Approval du backend, qui restent seuls maîtres
 *  d'autoriser ou de refuser. Elle empêche seulement le déclenchement accidentel.
 */

export type ActionSeverity = "destructive" | "impactful";

interface Props {
  /** Libellé du bouton au repos. */
  label: string;
  /** Ce que l'action va réellement faire, en une phrase. */
  description: string;
  /** Le nom exact de la cible, affiché pour que l'utilisateur vérifie. */
  target: string;
  severity?: ActionSeverity;
  disabled?: boolean;
  pending?: boolean;
  onConfirm: () => void;
}

export function ConfirmAction({
  label,
  description,
  target,
  severity = "impactful",
  disabled,
  pending,
  onConfirm,
}: Props) {
  const [armed, setArmed] = useState(false);

  const tone =
    severity === "destructive"
      ? "border-hermes-red/40 text-hermes-red hover:bg-hermes-red/10"
      : "border-hermes-amber/40 text-hermes-amber hover:bg-hermes-amber/10";

  if (!armed) {
    return (
      <button
        onClick={() => setArmed(true)}
        disabled={disabled || pending}
        className={`px-2 py-1 text-[10px] font-mono rounded border transition-colors disabled:opacity-40 ${tone}`}
      >
        {label}
      </button>
    );
  }

  return (
    <div
      role="alertdialog"
      aria-label={`Confirmer : ${label}`}
      className="inline-flex flex-col gap-1 rounded-lg border border-hermes-border bg-hermes-bg p-2 text-left"
    >
      <div className="text-[10px] font-mono text-hermes-text">{description}</div>
      <div className="text-[10px] font-mono text-hermes-muted">
        Cible : <span className="text-hermes-text">{target}</span>
      </div>
      <div className="flex gap-1 mt-1">
        <button
          onClick={() => {
            setArmed(false);
            onConfirm();
          }}
          disabled={pending}
          className={`px-2 py-1 text-[10px] font-mono rounded border disabled:opacity-40 ${tone}`}
        >
          {pending ? "En cours…" : `Confirmer : ${label}`}
        </button>
        <button
          onClick={() => setArmed(false)}
          className="px-2 py-1 text-[10px] font-mono rounded border border-hermes-border text-hermes-muted hover:text-hermes-text"
        >
          Annuler
        </button>
      </div>
    </div>
  );
}
