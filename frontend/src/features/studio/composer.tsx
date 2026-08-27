"use client";

import { useState } from "react";
import { AlertTriangle, Film, Image as ImageIcon, Loader2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { useStudioCompose, useStudioTemplates } from "@/hooks/use-api";
import type { GabaritDTO } from "@/services/client";

/**
 * Le formulaire de rendu du Studio Center (HOS-194).
 *
 * ## Pourquoi il existe
 *
 * L'onglet Atelier montrait la VRAM, la file et les modèles, et ne
 * permettait de lancer **rien**. Pour produire un plan il fallait passer
 * par l'agent ou par l'éditeur de ComfyUI — c'est-à-dire par une autre
 * application, ce que ce Center devait précisément éviter.
 *
 * ## Ce qu'il ne fait pas
 *
 * Il ne compose pas de graphe. Il envoie un **nom de gabarit** et des
 * paramètres explicites ; le graphe est bâti côté serveur par
 * `backend/studio/gabarits.py`, à partir de valeurs mesurées. Rien n'est
 * inféré de la consigne — ni la durée, ni le format, ni le modèle.
 *
 * La liste des gabarits et des formats vient du backend et n'est pas
 * recopiée ici : deux listes du même fait finissent par diverger.
 */

const CHAMPS: Record<string, { libelle: string; min: number; max: number; pas: number }> = {
  images: { libelle: "Images", min: 1, max: 257, pas: 8 },
  etapes: { libelle: "Étapes", min: 1, max: 50, pas: 1 },
  graine: { libelle: "Graine", min: 0, max: 999999, pas: 1 },
  cfg: { libelle: "CFG", min: 1, max: 20, pas: 0.5 },
};

export function Composer({ actif }: { actif: boolean }) {
  const { data: catalogue } = useStudioTemplates();
  const lancer = useStudioCompose();

  const [gabarit, setGabarit] = useState("plan_video");
  const [consigne, setConsigne] = useState("");
  const [format, setFormat] = useState("paysage");
  const [valeurs, setValeurs] = useState<Record<string, number>>({
    images: 49, etapes: 8, graine: 0, cfg: 7,
  });
  const [avecSon, setAvecSon] = useState(false);

  if (!catalogue) {
    return <Card title="Rendu"><p className="text-xs text-hermes-dim">Chargement des gabarits…</p></Card>;
  }

  const fiche: GabaritDTO | undefined = catalogue.gabarits[gabarit];
  const attendus = new Set(fiche?.parametres ?? []);
  const offerts = fiche?.formats ?? Object.keys(catalogue.formats);

  // Un format valide pour LTX ruine un rendu SDXL. Mesuré : le premier
  // formulaire offrait la même liste aux deux, un SDXL est parti en
  // 768 × 432 et l'image est sortie tuilée et déformée. On retombe donc
  // toujours sur un format que le moteur choisi sait rendre.
  const formatEffectif = offerts.includes(format) ? format : offerts[0];
  const dims = catalogue.formats[formatEffectif];

  const soumettre = () => {
    const parametres: Record<string, unknown> = { format_: formatEffectif };
    for (const [cle, v] of Object.entries(valeurs)) {
      if (attendus.has(cle)) parametres[cle] = v;
    }
    if (attendus.has("avec_son")) parametres.avec_son = avecSon;
    lancer.mutate({ gabarit, consigne, parametres });
  };

  const reponse = lancer.data;

  return (
    <Card
      title="Rendu"
      subtitle={fiche ? `${fiche.moteur} — ${fiche.note}` : undefined}
      accent="amber"
    >
      <div className="flex flex-col gap-3">
        {/* Le gabarit d'abord : il décide de ce que les autres champs
            veulent dire. */}
        <div className="flex flex-wrap gap-2">
          {Object.entries(catalogue.gabarits).map(([cle, g]) => (
            <button
              key={cle}
              onClick={() => setGabarit(cle)}
              className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] font-mono transition-all ${
                gabarit === cle
                  ? "border-hermes-amber/60 bg-hermes-amber/10 text-hermes-text"
                  : "border-hermes-border/50 text-hermes-muted hover:border-hermes-border"
              }`}
            >
              {g.sortie === "video" ? <Film size={11} /> : <ImageIcon size={11} />}
              {g.titre}
            </button>
          ))}
        </div>

        <textarea
          placeholder="Ce que le plan doit montrer — en anglais, c'est la langue des deux modèles…"
          value={consigne}
          onChange={(e) => setConsigne(e.target.value)}
          rows={3}
          className="resize-none rounded-lg border border-hermes-border bg-hermes-bg px-3 py-2
            font-mono text-sm text-hermes-text outline-none focus:border-hermes-amber"
        />

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="tech-label">Format</span>
            <select
              value={formatEffectif}
              onChange={(e) => setFormat(e.target.value)}
              className="rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
            >
              {offerts.map((nom) => (
                <option key={nom} value={nom}>
                  {nom} — {catalogue.formats[nom]?.largeur}×
                  {catalogue.formats[nom]?.hauteur}
                </option>
              ))}
            </select>
          </label>

          {Object.entries(CHAMPS)
            .filter(([cle]) => attendus.has(cle))
            .map(([cle, c]) => (
              <label key={cle} className="flex flex-col gap-1">
                <span className="tech-label">{c.libelle}</span>
                <input
                  type="number"
                  min={c.min}
                  max={c.max}
                  step={c.pas}
                  value={valeurs[cle]}
                  onChange={(e) =>
                    setValeurs((v) => ({ ...v, [cle]: Number(e.target.value) }))
                  }
                  className="w-24 rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                    font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
                />
              </label>
            ))}

          {attendus.has("avec_son") && (
            <label className="flex cursor-pointer items-center gap-2 pb-1.5">
              <input
                type="checkbox"
                checked={avecSon}
                onChange={(e) => setAvecSon(e.target.checked)}
                className="accent-hermes-sodium"
              />
              <span className="tech-label">Son natif (+21 %)</span>
            </label>
          )}
        </div>

        {/* Le coût, annoncé avant le clic. Cinq minutes de calcul par
            seconde de vidéo : c'est la chose la plus utile à savoir
            avant de lancer, et l'apprendre après serait une mauvaise
            surprise de vingt minutes. */}
        {fiche?.sortie === "video" && dims && (
          <p className="text-[11px] text-hermes-dim">
            {(valeurs.images / 24).toFixed(1)} s de vidéo en {dims.largeur}×{dims.hauteur} —
            compter environ{" "}
            <span className="num text-hermes-muted">
              {Math.round((valeurs.images / 24) * 5)} min
            </span>{" "}
            de calcul, la carte réservée pendant ce temps.
          </p>
        )}

        <div className="flex items-center justify-between gap-3">
          <div className="min-h-[18px] flex-1">
            {reponse && !reponse.success && (
              <div className="flex items-start gap-1.5">
                <AlertTriangle size={12} className="mt-0.5 shrink-0 text-hermes-alarm" />
                <span className="text-[11px] leading-relaxed text-hermes-alarm">
                  {reponse.error}
                </span>
              </div>
            )}
            {reponse?.success && (
              <span className="num text-[11px] text-hermes-arc">
                soumis — {reponse.prompt_id?.slice(0, 8)}
                {reponse.modeles_decharges?.length
                  ? ` · déchargé ${reponse.modeles_decharges.join(", ")}`
                  : ""}
              </span>
            )}
            {lancer.isError && (
              <span className="text-[11px] text-hermes-alarm">
                {(lancer.error as Error).message}
              </span>
            )}
          </div>

          <button
            onClick={soumettre}
            disabled={!consigne.trim() || lancer.isPending || actif}
            title={actif ? "Un rendu occupe déjà la carte" : undefined}
            className="flex items-center gap-1.5 rounded-lg bg-hermes-amber px-4 py-1.5
              font-mono text-xs text-black transition-colors hover:bg-hermes-amber-bright
              disabled:opacity-40"
          >
            {lancer.isPending && <Loader2 size={12} className="animate-spin" />}
            {actif ? "Carte occupée" : lancer.isPending ? "Soumission…" : "Lancer"}
          </button>
        </div>
      </div>
    </Card>
  );
}

export default Composer;
