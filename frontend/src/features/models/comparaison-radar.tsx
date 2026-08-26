"use client";

import { useEffect, useMemo, useState } from "react";
import { RadarAxes, type SerieRadar } from "@/components/radar-axes";
import type { BenchCatalogueDTO } from "@/services/client";

/**
 * Comparer deux modèles sur leurs sept axes mesurés (HOS-179).
 *
 * Le catalogue rendait déjà les notes, en table. Une table de dix modèles
 * sur sept axes se lit ligne par ligne : on y trouve une valeur, on n'y voit
 * pas une **forme**. Or c'est la forme qui décide — ce projet a passé une
 * semaine à mesurer que gpt-oss et Qwen3.8 ne se départagent pas sur une
 * moyenne mais sur deux profils différents.
 *
 * Deux séries au maximum, et c'est délibéré : un radar à cinq polygones
 * superposés est illisible, et cet écran sert à trancher entre deux
 * candidats, pas à contempler dix.
 */

const COULEURS = ["var(--hermes-sodium)", "var(--hermes-glacier)"] as const;

export function ComparaisonRadar({ catalogue }: { catalogue?: BenchCatalogueDTO }) {
  const modeles = useMemo(
    () => (catalogue?.models ?? []).map((m) => m.model).sort(),
    [catalogue],
  );

  const [gauche, setGauche] = useState("");
  const [droite, setDroite] = useState("");

  // Deux modèles réellement mesurés dès l'arrivée : un radar vide
  // n'apprend rien, et obliger à deux clics avant de voir quoi que ce soit
  // est le genre de friction qu'on reproche aux tableaux de bord.
  useEffect(() => {
    if (!modeles.length || gauche) return;
    const notes = (n: string) =>
      Object.values(catalogue?.models.find((m) => m.model === n)?.notes ?? {})
        .filter((v) => v !== null).length;
    const classes = [...modeles].sort((a, b) => notes(b) - notes(a));
    setGauche(classes[0] ?? "");
    setDroite(classes[1] ?? "");
  }, [modeles, gauche, catalogue]);

  const libelles = catalogue?.axes ?? [];

  const series: SerieRadar[] = useMemo(
    () =>
      [gauche, droite]
        .filter(Boolean)
        .map((nom, i) => {
          const e = catalogue?.models.find((m) => m.model === nom);
          return {
            nom,
            couleur: COULEURS[i] ?? COULEURS[0],
            axes: libelles.map((a) => ({ axe: a, note: e?.notes?.[a] ?? null })),
          };
        }),
    [gauche, droite, catalogue, libelles],
  );

  if (!catalogue || modeles.length === 0) return null;

  return (
    <div className="mb-5 grid grid-cols-1 lg:grid-cols-[minmax(0,340px)_1fr] gap-5 items-center">
      <div className="mx-auto w-full max-w-[340px]">
        <RadarAxes series={series} libelles={libelles} taille={320} />
      </div>

      <div className="flex flex-col gap-3">
        <p className="text-hermes-muted text-xs leading-relaxed">
          Une table donne des valeurs, un profil donne une <em>forme</em>. C&apos;est
          la forme qui départage : deux modèles de même moyenne peuvent avoir
          des usages opposés. Un axe marqué <span className="num text-hermes-dim">·</span> n&apos;a
          pas été mesuré — il est laissé en creux plutôt que tracé à zéro.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Selecteur
            label="Modèle A" couleur={COULEURS[0]} valeur={gauche}
            options={modeles} exclu={droite} onChange={setGauche}
          />
          <Selecteur
            label="Modèle B" couleur={COULEURS[1]} valeur={droite}
            options={modeles} exclu={gauche} onChange={setDroite}
          />
        </div>

        <Ecarts series={series} libelles={libelles} />
      </div>
    </div>
  );
}

function Selecteur({
  label, couleur, valeur, options, exclu, onChange,
}: {
  label: string;
  couleur: string;
  valeur: string;
  options: string[];
  exclu: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="tech-label text-hermes-dim inline-flex items-center gap-1.5">
        <span
          className="inline-block h-2 w-2 shrink-0"
          style={{ background: couleur, clipPath: "polygon(0 0,100% 0,100% 70%,70% 100%,0 100%)" }}
        />
        {label}
      </span>
      <select
        value={valeur}
        onChange={(e) => onChange(e.target.value)}
        className="num w-full clip-corner-sm border border-hermes-border bg-hermes-bg px-2.5 py-1.5
          text-[11px] text-hermes-text outline-none transition-colors
          focus:border-hermes-sodium hover:border-hermes-border-bright"
      >
        <option value="">—</option>
        {options.map((m) => (
          <option key={m} value={m} disabled={m === exclu}>{m}</option>
        ))}
      </select>
    </label>
  );
}

/** Les axes où les deux modèles divergent le plus.
 *
 *  C'est la lecture que le radar suggère et que l'œil doit sinon faire
 *  lui-même : nommer les deux ou trois axes qui décident. */
function Ecarts({ series, libelles }: { series: SerieRadar[]; libelles: string[] }) {
  if (series.length < 2) return null;

  const ecarts = libelles
    .map((axe) => {
      const a = series[0].axes.find((x) => x.axe === axe)?.note;
      const b = series[1].axes.find((x) => x.axe === axe)?.note;
      if (a === null || a === undefined || b === null || b === undefined) return null;
      return { axe, delta: a - b };
    })
    .filter((x): x is { axe: string; delta: number } => x !== null && Math.abs(x.delta) >= 15)
    .sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta))
    .slice(0, 3);

  if (ecarts.length === 0) {
    return (
      <p className="text-[11px] text-hermes-dim">
        Aucun axe ne les sépare de plus de quinze points — sur les axes mesurés,
        ces deux modèles se valent.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-1">
      {ecarts.map(({ axe, delta }) => (
        <li key={axe} className="flex items-center gap-2 text-[11px]">
          <span className="num uppercase tracking-[0.09em] text-hermes-dim w-28 shrink-0">
            {axe}
          </span>
          <span
            className="num tabular-nums"
            style={{ color: delta > 0 ? COULEURS[0] : COULEURS[1] }}
          >
            {delta > 0 ? "A" : "B"} +{Math.abs(delta)}
          </span>
        </li>
      ))}
    </ul>
  );
}
