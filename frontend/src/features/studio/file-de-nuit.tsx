"use client";

import { useState } from "react";
import { AlertTriangle, Loader2, Moon, Plus, Trash2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { useStudioStartNight, useStudioTemplates } from "@/hooks/use-api";

/**
 * Le formulaire de la file de nuit (HOS-206).
 *
 * ## Pourquoi il existe
 *
 * L'onglet Nuit n'affichait qu'un rapport, et aucun bouton n'y menait :
 * `POST /studio/night` exigeait un `graphe` complet, que l'écran ne sait
 * pas composer — la règle du dépôt réserve cette décision au gabarit ou à
 * l'agent. La file de nuit était donc une capacité réelle et testée,
 * inaccessible autrement qu'en la demandant à l'agent dans le chat.
 *
 * Même défaut que la voix Michael et que les trois paramètres de
 * HOS-199 : du code qui marche, sans commande à l'écran.
 *
 * ## Ce qu'il ne fait pas
 *
 * Il ne compose aucun graphe. Chaque plan part comme un **nom de
 * gabarit** et des paramètres explicites ; `gabarits.py` bâtit le graphe.
 */

interface PlanNuit {
  cle: number;
  identifiant: string;
  consigne: string;
}

export function FileDeNuit() {
  const { data: catalogue } = useStudioTemplates();
  const lancer = useStudioStartNight();

  const [gabarit, setGabarit] = useState("plan_video");
  const [format, setFormat] = useState("paysage");
  const [duree, setDuree] = useState(2);
  const [etapes, setEtapes] = useState(8);
  const [minutes, setMinutes] = useState(45);
  const [plans, setPlans] = useState<PlanNuit[]>([
    { cle: 1, identifiant: "plan_1", consigne: "" },
  ]);

  if (!catalogue) {
    return (
      <Card title="Lancer une nuit">
        <p className="text-xs text-hermes-dim">Chargement des gabarits…</p>
      </Card>
    );
  }

  const fiche = catalogue.gabarits[gabarit];
  const offerts = fiche?.formats ?? Object.keys(catalogue.formats);
  const formatEffectif = offerts.includes(format) ? format : offerts[0];
  const dims = catalogue.formats[formatEffectif];

  const pas = catalogue.images?.pas ?? 8;
  const imagesMax = catalogue.images?.max ?? 257;
  const images = Math.max(
    1,
    Math.min(imagesMax, Math.round((Math.max(0, duree) * 24) / pas) * pas + 1),
  );

  // Le coût, annoncé avant le clic — et il se compte en heures ici, pas en
  // minutes : c'est la chose la plus utile à savoir avant de lancer une file
  // qui tiendra la carte toute la nuit.
  const coutFixe = catalogue.cout?.fixe_s ?? 56;
  const coutParMpx = catalogue.cout?.par_mpx_image_s ?? 13.27;
  const minutesParPlan =
    (coutFixe +
      (coutParMpx * ((dims?.largeur ?? 0) * (dims?.hauteur ?? 0) * images)) / 1e6) /
    60;
  const remplis = plans.filter((p) => p.consigne.trim());
  const heures = (minutesParPlan * remplis.length) / 60;

  const soumettre = () => {
    if (!remplis.length) return;
    lancer.mutate({
      plans: remplis.map((p) => ({
        identifiant: p.identifiant.trim() || `plan_${p.cle}`,
        consigne: p.consigne.trim(),
        gabarit,
        parametres: { format_: formatEffectif, images, etapes },
      })),
      minutes,
    });
  };

  const reponse = lancer.data;

  return (
    <Card title="Lancer une nuit" subtitle="Une file de plans, relus au matin" accent="amber">
      <div className="flex flex-col gap-3">
        <p className="text-[11.5px] leading-relaxed text-hermes-muted">
          Chaque plan est rendu à son tour, la carte réservée pour lui seul, puis{" "}
          <strong className="text-hermes-text">confronté à sa consigne</strong> par un
          modèle de vision. Le rapport du matin distingue « retenu » de
          « indéterminé » — un fichier produit n&apos;est pas un plan réussi.
        </p>

        {/* Les réglages sont communs à toute la file : une nuit sert à décliner
            un même plan, pas à mélanger des formats. Seule la consigne change
            d'un plan à l'autre. */}
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="tech-label">Gabarit</span>
            <select
              value={gabarit}
              onChange={(e) => setGabarit(e.target.value)}
              className="rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
            >
              {Object.entries(catalogue.gabarits)
                .filter(([, g]) => g.sortie === "video")
                .map(([cle, g]) => (
                  <option key={cle} value={cle}>
                    {g.titre}
                  </option>
                ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="tech-label">Format</span>
            <select
              value={formatEffectif}
              onChange={(e) => setFormat(e.target.value)}
              className="rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
            >
              {offerts.map((n) => (
                <option key={n} value={n}>
                  {n} — {catalogue.formats[n]?.largeur}×{catalogue.formats[n]?.hauteur}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="tech-label">Durée (s)</span>
            <input
              type="number"
              min={1}
              max={Math.floor((imagesMax - 1) / 24)}
              step={0.5}
              value={duree}
              onChange={(e) => setDuree(Number(e.target.value))}
              className="w-20 rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="tech-label">Étapes</span>
            <input
              type="number"
              min={1}
              max={50}
              value={etapes}
              onChange={(e) => setEtapes(Number(e.target.value))}
              className="w-20 rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
            />
          </label>

          <label
            className="flex flex-col gap-1"
            title="Au-delà, le plan est abandonné et la file passe au suivant"
          >
            <span className="tech-label">Délai max / plan (min)</span>
            <input
              type="number"
              min={5}
              max={240}
              step={5}
              value={minutes}
              onChange={(e) => setMinutes(Number(e.target.value))}
              className="w-24 rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
            />
          </label>
        </div>

        <div className="flex flex-col gap-2 border-t border-hermes-border/40 pt-3">
          {plans.map((p, i) => (
            <div key={p.cle} className="flex items-start gap-2">
              <input
                type="text"
                value={p.identifiant}
                onChange={(e) =>
                  setPlans((v) =>
                    v.map((x) => (x.cle === p.cle ? { ...x, identifiant: e.target.value } : x)),
                  )
                }
                placeholder={`plan_${i + 1}`}
                title="Nomme le fichier et la ligne du rapport"
                className="w-28 shrink-0 rounded-lg border border-hermes-border bg-hermes-bg
                  px-2 py-1.5 font-mono text-[11px] text-hermes-muted outline-none
                  focus:border-hermes-amber"
              />
              <textarea
                value={p.consigne}
                rows={2}
                onChange={(e) =>
                  setPlans((v) =>
                    v.map((x) => (x.cle === p.cle ? { ...x, consigne: e.target.value } : x)),
                  )
                }
                placeholder="Ce que ce plan doit montrer — c'est aussi ce à quoi le relecteur le comparera…"
                className="flex-1 resize-none rounded-lg border border-hermes-border bg-hermes-bg
                  px-3 py-2 font-mono text-sm text-hermes-text outline-none
                  focus:border-hermes-amber"
              />
              <button
                onClick={() =>
                  setPlans((v) => (v.length > 1 ? v.filter((x) => x.cle !== p.cle) : v))
                }
                disabled={plans.length === 1}
                title="Retirer ce plan"
                className="mt-1.5 shrink-0 rounded-lg border border-hermes-border p-1.5
                  text-hermes-muted transition-all hover:border-hermes-alarm/40
                  hover:text-hermes-alarm disabled:opacity-30"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
          <button
            onClick={() =>
              setPlans((v) => [
                ...v,
                {
                  cle: Math.max(0, ...v.map((x) => x.cle)) + 1,
                  identifiant: `plan_${v.length + 1}`,
                  consigne: "",
                },
              ])
            }
            className="flex w-fit items-center gap-1.5 rounded-lg border border-hermes-border/50
              px-3 py-1.5 font-mono text-[11px] text-hermes-muted transition-all
              hover:border-hermes-amber/40 hover:text-hermes-amber"
          >
            <Plus size={11} /> Ajouter un plan
          </button>
        </div>

        {remplis.length > 0 && dims && (
          <p className="text-[11px] leading-relaxed text-hermes-dim">
            {remplis.length} plan(s) de {(images / 24).toFixed(2)} s en {dims.largeur}×
            {dims.hauteur} — compter environ{" "}
            <span className="num text-hermes-muted">
              {heures < 1 ? `${Math.round(heures * 60)} min` : `${heures.toFixed(1)} h`}
            </span>{" "}
            au total, la carte réservée pendant tout ce temps.
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
                nuit lancée — {reponse.plans} plan(s), rapport dans {reponse.journal}
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
            disabled={!remplis.length || lancer.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-hermes-amber px-4 py-1.5
              font-mono text-xs text-black transition-colors hover:bg-hermes-amber-bright
              disabled:opacity-40"
          >
            {lancer.isPending ? <Loader2 size={12} className="animate-spin" /> : <Moon size={12} />}
            {lancer.isPending ? "Lancement…" : "Lancer la nuit"}
          </button>
        </div>
      </div>
    </Card>
  );
}

export default FileDeNuit;
