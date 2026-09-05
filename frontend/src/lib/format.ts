/** Shared formatting helpers.
 *
 *  `formatBytes` existed as seven separate, unsynchronized local copies
 *  across agent-center, dashboard-view, conversation-center,
 *  deployment-center, model-intelligence-center, runtime-center and
 *  monitoring-center — all computing the identical bytes/1024³ value, but
 *  at different decimal precision (`.toFixed(1)` everywhere except
 *  Monitoring's `.toFixed(2)`) and under two different unit labels ("GB"
 *  in six places, "Gio" in one). The real VRAM total (17 163 091 968
 *  bytes) never actually disagreed between Centers — it just rendered as
 *  "16.0 GB" in some and "15.98 Gio" in others, which reads as a real
 *  discrepancy even though it's one real measurement shown two ways. */

/** Bytes to gibioctets (binary, ÷1024³) — the correct French label for
 *  this math is "Gio" (gibioctet), not "Go" (gigaoctet, decimal ÷1000³).
 *  Every real usage in this codebase computes the binary value, so this
 *  standardizes the label on what the number actually is rather than on
 *  the more common-but-technically-decimal "Go"/"GB". Returns "—" for a
 *  missing/non-numeric reading rather than "0.0" or "NaN" — an absent
 *  measurement should look absent. */
export function formatGio(bytes: number | null | undefined, decimals = 1): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes)) return "—";
  return (bytes / 1024 ** 3).toFixed(decimals);
}

/** `"used / total Gio"`, the pattern every Center's resource panel uses. */
export function formatGioPair(
  used: number | null | undefined,
  total: number | null | undefined,
  decimals = 1,
): string {
  return `${formatGio(used, decimals)} / ${formatGio(total, decimals)} Gio`;
}

/** L'état GPU tel que `GET /api/v1/runtime/resources` le rend. Déclaré ici
 *  en structurel plutôt qu'importé de `types/hermes` pour que ces aides
 *  restent utilisables par un appelant qui n'a qu'un fragment de l'objet. */
type EtatGpu = {
  vram_total_bytes: number;
  vram_used_bytes: number;
  vram_free_bytes: number;
  available: boolean;
  occupation_mesuree?: boolean;
} | null | undefined;

/** L'occupation de la carte a-t-elle été mesurée (A-15) ?
 *
 *  Le backend distinguait « pas de carte » de « carte présente, occupation
 *  illisible » depuis A-15 ; le Cockpit, lui, lisait `vram_used_bytes: 0`
 *  et affichait une carte au repos. C'est la même confusion que celle qui
 *  faisait admettre un modèle de trop, un étage plus haut.
 *
 *  Une réponse antérieure au drapeau vaut `true` : elle vient d'un backend
 *  dont toutes les sources mesuraient bien quelque chose. */
export function vramMesuree(gpu: EtatGpu): boolean {
  if (!gpu || !gpu.available) return false;
  return gpu.occupation_mesuree !== false;
}

/** Octets occupés, ou `null` quand rien ne les a mesurés. `formatGio(null)`
 *  rend déjà « — », donc les sites d'affichage n'ont rien de plus à faire. */
export function vramOccupee(gpu: EtatGpu): number | null {
  return vramMesuree(gpu) ? gpu!.vram_used_bytes : null;
}

/** Octets libres, ou `null`. Le zéro de prudence du backend ne veut pas
 *  dire « carte pleine » et ne doit jamais s'afficher comme tel. */
export function vramLibre(gpu: EtatGpu): number | null {
  return vramMesuree(gpu) ? gpu!.vram_free_bytes : null;
}

/** Taux d'occupation en pourcentage, ou `null` s'il n'y a rien à diviser.
 *  Les jauges qui exigent un nombre retombent sur 0 — accompagné du libellé
 *  « non mesurée », qui est ce qu'un lecteur lit réellement. */
export function vramPourcent(gpu: EtatGpu): number | null {
  if (!vramMesuree(gpu) || !gpu!.vram_total_bytes) return null;
  return (gpu!.vram_used_bytes / gpu!.vram_total_bytes) * 100;
}
