"use client";

import { useId, useMemo, useState } from "react";
import { motion } from "framer-motion";

/**
 * Le profil d'un modèle, sur ses sept axes mesurés (HOS-179).
 *
 * Le catalogue porte, pour chaque modèle, une note de 0 à 100 par axe —
 * agentique, capacité, code, vision, extraction, long contexte,
 * raisonnement. Sept dimensions comparables : c'est littéralement la forme
 * qu'un radar sert à lire, et elles n'étaient rendues nulle part. Le
 * Cockpit n'avait **aucun graphique** ; `recharts` était installé et
 * importé par zéro fichier.
 *
 * ## Pourquoi pas recharts
 *
 * Il est là, il ferait le travail, et son rendu par défaut se reconnaît sur
 * un millier de tableaux de bord. Le contrat SODIUM proscrit nommément ce
 * genre de reprise. Soixante lignes de SVG donnent ici la géométrie de la
 * maison : anneaux **polygonaux** et non circulaires, comme les chanfreins
 * des cartes, et une seule couleur d'accent.
 *
 * ## Ce qu'il refuse de dessiner
 *
 * Un axe non mesuré n'est pas tracé à zéro : il serait indiscernable d'un
 * modèle qui a échoué. Il est laissé en creux, et l'étiquette passe en
 * gris. C'est la même règle que l'oscilloscope, qui tient une ligne plate
 * plutôt que d'inventer un mouvement — une valeur affichée est une valeur
 * mesurée.
 */

export interface AxeNote {
  axe: string;
  /** `null` = non mesuré. Jamais confondu avec zéro. */
  note: number | null;
}

export interface SerieRadar {
  nom: string;
  couleur: string;
  axes: AxeNote[];
}

const ANNEAUX = [25, 50, 75, 100];

function point(cx: number, cy: number, rayon: number, i: number, n: number) {
  // Départ à midi, sens horaire : la lecture commence en haut, comme un
  // cadran d'instrument.
  const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
  return [cx + rayon * Math.cos(angle), cy + rayon * Math.sin(angle)] as const;
}

function polygone(cx: number, cy: number, rayon: number, n: number): string {
  return Array.from({ length: n }, (_, i) => point(cx, cy, rayon, i, n))
    .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
}

export function RadarAxes({
  series,
  taille = 300,
  libelles,
}: {
  series: SerieRadar[];
  taille?: number;
  /** Les axes à afficher, dans l'ordre. Fixés par l'appelant pour que deux
   *  modèles se superposent sur la même grille. */
  libelles: string[];
}) {
  const id = useId();
  const [survole, setSurvole] = useState<number | null>(null);

  const marge = 46;
  const cx = taille / 2;
  const cy = taille / 2;
  const rMax = taille / 2 - marge;
  const n = libelles.length;

  const tracees = useMemo(
    () =>
      series.map((s) => {
        const par = new Map(s.axes.map((a) => [a.axe, a.note]));
        const points = libelles.map((l, i) => {
          const note = par.get(l);
          const mesure = note !== null && note !== undefined;
          const r = mesure ? (note! / 100) * rMax : 0;
          return { ...{ mesure, note: note ?? null }, xy: point(cx, cy, r, i, n) };
        });
        return { ...s, points };
      }),
    [series, libelles, cx, cy, rMax, n],
  );

  if (n === 0) {
    return (
      <p className="text-xs text-hermes-dim">Aucun axe mesuré à comparer.</p>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${taille} ${taille}`}
      className="w-full h-auto select-none"
      role="img"
      aria-label={`Profil mesuré sur ${n} axes : ${series.map((s) => s.nom).join(", ")}`}
    >
      <defs>
        {tracees.map((s, k) => (
          <radialGradient key={k} id={`${id}-g${k}`} cx="50%" cy="50%">
            <stop offset="0%" stopColor={s.couleur} stopOpacity="0.30" />
            <stop offset="100%" stopColor={s.couleur} stopOpacity="0.06" />
          </radialGradient>
        ))}
      </defs>

      {/* La grille : des polygones, pas des cercles — la même géométrie
          anguleuse que les chanfreins des cartes. */}
      {ANNEAUX.map((pct) => (
        <polygon
          key={pct}
          points={polygone(cx, cy, (pct / 100) * rMax, n)}
          fill="none"
          stroke="var(--hermes-border)"
          strokeWidth={pct === 100 ? 1 : 0.5}
          opacity={pct === 100 ? 0.9 : 0.45}
        />
      ))}

      {libelles.map((_, i) => {
        const [x, y] = point(cx, cy, rMax, i, n);
        return (
          <line
            key={i}
            x1={cx} y1={cy} x2={x} y2={y}
            stroke="var(--hermes-border)"
            strokeWidth={survole === i ? 1.2 : 0.5}
            opacity={survole === i ? 0.9 : 0.4}
          />
        );
      })}

      {tracees.map((s, k) => (
        <g key={s.nom}>
          <motion.polygon
            points={s.points.map((p) => `${p.xy[0].toFixed(1)},${p.xy[1].toFixed(1)}`).join(" ")}
            fill={`url(#${id}-g${k})`}
            stroke={s.couleur}
            strokeWidth={1.4}
            strokeLinejoin="round"
            initial={{ opacity: 0, scale: 0.82 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.55, delay: k * 0.08, ease: [0.16, 1, 0.3, 1] }}
            style={{ transformOrigin: `${cx}px ${cy}px` }}
          />
          {s.points.map((p, i) =>
            p.mesure ? (
              <circle
                key={i}
                cx={p.xy[0]} cy={p.xy[1]}
                r={survole === i ? 3.4 : 2.1}
                fill={s.couleur}
                className="transition-all duration-150"
              />
            ) : null,
          )}
        </g>
      ))}

      {libelles.map((label, i) => {
        const [x, y] = point(cx, cy, rMax + 20, i, n);
        // Un axe qu'aucune série n'a mesuré s'affiche en creux : le tracer à
        // zéro le rendrait indiscernable d'un échec.
        const mesure = tracees.some((s) => s.points[i].mesure);
        const ancre = Math.abs(x - cx) < 6 ? "middle" : x > cx ? "start" : "end";
        return (
          <text
            key={label}
            x={x} y={y}
            textAnchor={ancre}
            dominantBaseline="middle"
            className="num"
            fontSize="8.5"
            letterSpacing="0.09em"
            fill={
              !mesure ? "var(--hermes-dim)"
              : survole === i ? "var(--hermes-text-bright)"
              : "var(--hermes-muted)"
            }
            style={{ textTransform: "uppercase", cursor: "default" }}
            onMouseEnter={() => setSurvole(i)}
            onMouseLeave={() => setSurvole(null)}
          >
            {label}
            {!mesure && " ·"}
          </text>
        );
      })}

      {survole !== null && (
        <g>
          {tracees.map((s, k) =>
            s.points[survole].mesure ? (
              <text
                key={s.nom}
                x={cx} y={cy + 4 + k * 13}
                textAnchor="middle"
                className="num"
                fontSize="11"
                fill={s.couleur}
              >
                {s.points[survole].note}
              </text>
            ) : null,
          )}
        </g>
      )}
    </svg>
  );
}
