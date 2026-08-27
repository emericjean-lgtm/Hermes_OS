"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Plus, Trash2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { useStudioNarrate } from "@/hooks/use-api";

/**
 * Le formulaire de narration du Studio Center (HOS-196).
 *
 * ## Pourquoi il existe
 *
 * La voix « Michael » (HOS-195) n'était joignable que par l'agent, via
 * l'outil MCP `studio_narrate` — aucun écran, aucune route REST. Pour
 * narrer une réplique, il fallait donc décrire dans le chat ce qu'on
 * voulait entendre plutôt que de le taper directement, ce que ce Center
 * fait déjà pour le rendu d'image (voir `composer.tsx`).
 *
 * ## Ce qu'il ne fait pas
 *
 * Il ne choisit ni la voix ni les réglages — `exaggeration`/`cfg_weight`
 * viennent de `reglages.json`, mesurés une fois pour la narration
 * continue, pas redevinés ici. Le formulaire ne fait que soumettre des
 * répliques et un dossier de sortie ; `backend/studio/narration.py`
 * réserve la carte et synthétise, exactement comme le fait l'agent.
 */

interface Replique {
  id: string;
  texte: string;
}

function nouvelleReplique(n: number): Replique {
  return { id: `replique_${n}`, texte: "" };
}

export function Narration() {
  const [repliques, setRepliques] = useState<Replique[]>([nouvelleReplique(1)]);
  const [dossier, setDossier] = useState("");
  const narrer = useStudioNarrate();

  const ajouter = () =>
    setRepliques((r) => [...r, nouvelleReplique(r.length + 1)]);

  const retirer = (id: string) =>
    setRepliques((r) => (r.length > 1 ? r.filter((x) => x.id !== id) : r));

  const modifier = (id: string, champ: "id" | "texte", valeur: string) =>
    setRepliques((r) => r.map((x) => (x.id === id ? { ...x, [champ]: valeur } : x)));

  const soumettre = () => {
    const lignes = repliques
      .filter((r) => r.texte.trim())
      .map((r) => ({ id: r.id.trim() || r.id, texte: r.texte }));
    if (!lignes.length) return;
    narrer.mutate({ lignes, dossier: dossier.trim() || undefined });
  };

  const reponse = narrer.data;
  const pretes = repliques.some((r) => r.texte.trim());

  return (
    <Card
      title="Narration"
      subtitle="Voix clonée « Michael » — Chatterbox TTS"
      accent="amber"
    >
      <div className="flex flex-col gap-3">
        <p className="text-[11.5px] leading-relaxed text-hermes-muted">
          Chaque réplique charge le modèle une seule fois pour tout le lot —
          les synthétiser une à une rechargerait le modèle à chaque appel
          (9 à 27 s mesurées). Comme un rendu d&apos;image, la synthèse
          réserve la carte partagée et refuse plutôt que de déborder si un
          rendu ComfyUI la tient déjà.
        </p>

        <div className="flex flex-col gap-2">
          {repliques.map((r, i) => (
            <div key={r.id} className="flex items-start gap-2">
              <input
                type="text"
                value={r.id}
                onChange={(e) => modifier(r.id, "id", e.target.value)}
                placeholder={`replique_${i + 1}`}
                title="Identifiant — nomme le fichier de sortie"
                className="w-28 shrink-0 rounded-lg border border-hermes-border bg-hermes-bg
                  px-2 py-1.5 font-mono text-[11px] text-hermes-muted outline-none
                  focus:border-hermes-amber"
              />
              <textarea
                value={r.texte}
                onChange={(e) => modifier(r.id, "texte", e.target.value)}
                placeholder="Ce que Michael doit dire…"
                rows={2}
                className="flex-1 resize-none rounded-lg border border-hermes-border bg-hermes-bg
                  px-3 py-2 font-mono text-sm text-hermes-text outline-none
                  focus:border-hermes-amber"
              />
              <button
                onClick={() => retirer(r.id)}
                disabled={repliques.length === 1}
                title="Retirer cette réplique"
                className="mt-1.5 shrink-0 rounded-lg border border-hermes-border p-1.5
                  text-hermes-muted transition-all hover:border-hermes-alarm/40
                  hover:text-hermes-alarm disabled:opacity-30"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}

          <button
            onClick={ajouter}
            className="flex w-fit items-center gap-1.5 rounded-lg border border-hermes-border/50
              px-3 py-1.5 font-mono text-[11px] text-hermes-muted transition-all
              hover:border-hermes-amber/40 hover:text-hermes-amber"
          >
            <Plus size={11} /> Ajouter une réplique
          </button>
        </div>

        <label className="flex flex-col gap-1">
          <span className="tech-label">Dossier de sortie (optionnel)</span>
          <input
            type="text"
            value={dossier}
            onChange={(e) => setDossier(e.target.value)}
            placeholder="E:\YouTube\Generations\narration\… — horodaté si vide"
            className="rounded-lg border border-hermes-border bg-hermes-bg px-3 py-1.5
              font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
          />
        </label>

        <div className="flex items-center justify-between gap-3">
          <div className="min-h-[18px] flex-1">
            {reponse && !reponse.success && (
              <div className="flex items-start gap-1.5">
                <AlertTriangle size={12} className="mt-0.5 shrink-0 text-hermes-alarm" />
                <span className="text-[11px] leading-relaxed text-hermes-alarm">
                  {reponse.error || reponse.erreur || "la synthèse a échoué"}
                </span>
              </div>
            )}
            {reponse?.success && (
              <span className="num text-[11px] text-hermes-arc">
                {reponse.segments.length} réplique(s) synthétisée(s) — {reponse.dossier}
              </span>
            )}
            {narrer.isError && (
              <span className="text-[11px] text-hermes-alarm">
                {(narrer.error as Error).message}
              </span>
            )}
          </div>

          <button
            onClick={soumettre}
            disabled={!pretes || narrer.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-hermes-amber px-4 py-1.5
              font-mono text-xs text-black transition-colors hover:bg-hermes-amber-bright
              disabled:opacity-40"
          >
            {narrer.isPending && <Loader2 size={12} className="animate-spin" />}
            {narrer.isPending ? "Synthèse…" : "Narrer"}
          </button>
        </div>

        {/* Le détail par réplique : `reussie` globale masque une réplique
            en échec au milieu d'un lot qui a autrement fonctionné — le
            même défaut que "success: true" au-dessus d'un travail
            partiel, contre lequel ce dépôt écrit des tests depuis
            HOS-190. */}
        {reponse && reponse.segments.length > 0 && (
          <div className="flex flex-col gap-1 border-t border-hermes-border/40 pt-2.5">
            {reponse.segments.map((s) => (
              <div key={s.id} className="flex items-start gap-1.5">
                {s.reussi ? (
                  <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-hermes-arc" />
                ) : (
                  <AlertTriangle size={12} className="mt-0.5 shrink-0 text-hermes-alarm" />
                )}
                <span className="num text-[11px] text-hermes-muted">{s.id}</span>
                {s.reussi ? (
                  <span className="text-[11px] text-hermes-dim">
                    {s.duree_s ? `${s.duree_s.toFixed(1)} s` : ""} — {s.chemin}
                  </span>
                ) : (
                  <span className="text-[11px] text-hermes-alarm">{s.erreur}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

export default Narration;
