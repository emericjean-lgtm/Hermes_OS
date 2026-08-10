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
