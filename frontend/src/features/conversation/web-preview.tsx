"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ExternalLink, Globe, RefreshCw, X } from "lucide-react";

/**
 * Live web preview panel (HOS-075) — the safe alternative to a terminal.
 *
 * A real terminal from chat means an unsandboxed shell reachable from
 * whatever the model decides to type into it: no gated tool-calling exists
 * for that yet, so it stays out of scope (flagged to the user, not quietly
 * dropped). A sandboxed `<iframe>` with its own URL bar has no such
 * problem — it's the same trust boundary as opening a browser tab, and
 * covers the concrete ask ("un rendu en temps réel de l'application")
 * without inventing a new privileged execution path.
 */

function normalizeUrl(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  try {
    const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
    const url = new URL(withProtocol);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return url.toString();
  } catch {
    return null;
  }
}

export function WebPreviewPanel({ onClose }: { onClose: () => void }) {
  const [input, setInput] = useState(
    typeof window !== "undefined" ? window.location.origin : "",
  );
  const [url, setUrl] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const load = () => {
    const normalized = normalizeUrl(input);
    if (!normalized) { setError("URL invalide — utilisez une adresse http(s), par exemple localhost:3010."); return; }
    setError(null);
    setUrl(normalized);
    setReloadKey((k) => k + 1);
  };

  return (
    <motion.div
      /* Pas d'`exit` : ce panneau plein écran contient une iframe (HOS-196).
         Les iframes ignorent le fondu CSS de leur conteneur — elles restent
         composées à pleine visibilité tant que l'animation de sortie n'est
         pas confirmée terminée, et cette confirmation dépend d'une frame de
         peinture qui peut manquer (GPU chargé par un rendu en parallèle,
         onglet en arrière-plan). Constaté sur le même mécanisme dans
         `cockpit-shell.tsx` : un panneau `fixed inset-0 z-40` resté coincé
         couvrirait l'application entière, bouton de fermeture compris. Sans
         `exit`, la fermeture est instantanée au lieu de s'animer sur 150ms
         — un choix délibéré, pas un oubli. */
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      transition={{ duration: 0.15 }}
      className="fixed inset-0 z-40 flex flex-col bg-hermes-bg-deep"
    >
      <div className="flex items-center gap-2 border-b border-hermes-border/70 px-4 py-3">
        <Globe size={14} className="shrink-0 text-hermes-cyan" />
        <span className="hidden shrink-0 font-mono text-[11px] uppercase tracking-[0.14em] text-hermes-muted md:block">
          Aperçu web
        </span>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") load(); }}
          placeholder="http://localhost:3010"
          className="ml-2 w-full max-w-md rounded-lg border border-hermes-border bg-hermes-elevated/60
            px-3 py-1.5 font-mono text-[11px] text-hermes-text-bright focus:outline-none focus:border-hermes-cyan/50"
        />
        <button
          onClick={load}
          className="shrink-0 rounded-lg border border-hermes-cyan/40 bg-hermes-cyan/10 px-3 py-1.5
            font-mono text-[10px] uppercase tracking-wider text-hermes-cyan transition-all hover:bg-hermes-cyan/20"
        >
          Charger
        </button>
        {url && (
          <>
            <button
              onClick={() => setReloadKey((k) => k + 1)}
              title="Recharger"
              className="shrink-0 rounded-lg border border-hermes-border px-2 py-1.5 text-hermes-muted
                transition-all hover:border-hermes-cyan/40 hover:text-hermes-cyan"
            >
              <RefreshCw size={12} />
            </button>
            <a
              href={url} target="_blank" rel="noreferrer" title="Ouvrir dans un nouvel onglet"
              className="shrink-0 rounded-lg border border-hermes-border px-2 py-1.5 text-hermes-muted
                transition-all hover:border-hermes-cyan/40 hover:text-hermes-cyan"
            >
              <ExternalLink size={12} />
            </a>
          </>
        )}
        <button
          onClick={onClose}
          title="Fermer (Échap)"
          className="ml-auto shrink-0 rounded-lg border border-hermes-border px-2 py-1.5 text-hermes-muted
            transition-all hover:border-hermes-red/40 hover:text-hermes-red"
        >
          <X size={13} />
        </button>
      </div>

      {error && (
        <div className="border-b border-hermes-red/20 bg-hermes-red/5 px-4 py-2 text-[11px] text-hermes-red">
          {error}
        </div>
      )}

      <div className="min-h-0 flex-1">
        {url ? (
          <iframe
            key={reloadKey}
            src={url}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
            className="h-full w-full border-0 bg-white"
            title="Aperçu web"
          />
        ) : (
          <div className="flex h-full items-center justify-center px-6 text-center text-[12px] text-hermes-dim">
            Entrez une URL locale — par exemple le serveur de développement du Cockpit —
            pour voir le rendu en direct pendant que vous travaillez.
          </div>
        )}
      </div>
    </motion.div>
  );
}
