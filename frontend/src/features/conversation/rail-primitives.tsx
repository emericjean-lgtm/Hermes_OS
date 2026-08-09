"use client";

import React from "react";

/** Shared by conversation-center.tsx and project-panel.tsx — pulled out
 *  rather than one importing it from the other, which would make the two
 *  files circularly dependent. */
export function RailPanel({ title, icon, children }: {
  title: string; icon: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-hermes-border/70 bg-hermes-card/60">
      <div className="flex items-center gap-1.5 border-b border-hermes-border/50 px-3 py-2">
        <span className="text-hermes-cyan/70">{icon}</span>
        <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-hermes-muted">{title}</h3>
      </div>
      <div className="p-3">{children}</div>
    </section>
  );
}

export function Placeholder({ children }: { children: React.ReactNode }) {
  return <p className="py-1 text-[10.5px] leading-relaxed text-hermes-dim">{children}</p>;
}
