import type { Config } from "tailwindcss";

/** Colours are declared here AND as CSS variables in globals.css. That
 *  duplication is load-bearing: without the entries below, `text-hermes-muted`
 *  and friends compile to nothing and every label silently inherits the body
 *  colour. Keep the two files in sync.
 *
 *  "SODIUM" redesign: the legacy key names (cyan/magenta/violet/green/amber)
 *  are kept as the public API so all 22 Centers pick up the new palette
 *  without 22 simultaneous edits — but every value now resolves through the
 *  CSS variables, which point at the new industrial palette. The name says
 *  cyan; the colour is sodium amber. New work should prefer the semantic
 *  names (sodium/glacier/steel/arc/gold/alarm). */
export default {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        hermes: {
          // Chassis — cold carbon
          bg: "var(--hermes-bg)",
          "bg-deep": "var(--hermes-bg-deep)",
          surface: "var(--hermes-surface)",
          card: "var(--hermes-card)",
          elevated: "var(--hermes-elevated)",
          border: "var(--hermes-border)",
          "border-bright": "var(--hermes-border-bright)",

          // Signal — semantic names, preferred for new work
          sodium: "var(--hermes-sodium)",
          "sodium-deep": "var(--hermes-sodium-deep)",
          glacier: "var(--hermes-glacier)",
          steel: "var(--hermes-steel)",
          arc: "var(--hermes-arc)",
          gold: "var(--hermes-gold)",
          alarm: "var(--hermes-alarm)",

          // Legacy aliases — same values, old names, so existing markup works
          cyan: "var(--hermes-cyan)",
          "cyan-dim": "var(--hermes-cyan-dim)",
          magenta: "var(--hermes-magenta)",
          violet: "var(--hermes-violet)",
          green: "var(--hermes-green)",
          amber: "var(--hermes-amber)",
          red: "var(--hermes-red)",
          blue: "var(--hermes-blue)",
          "amber-bright": "var(--hermes-amber-bright)",
          purple: "var(--hermes-purple)",

          // Type
          text: "var(--hermes-text)",
          "text-bright": "var(--hermes-text-bright)",
          muted: "var(--hermes-muted)",
          dim: "var(--hermes-dim)",
        },
      },
      fontFamily: {
        // Three roles, actually loaded via next/font in app/layout.tsx.
        // The previous config declared JetBrains Mono and never loaded it,
        // so every `font-mono` label silently fell back to the OS default.
        display: ["var(--font-chakra)", "var(--font-barlow)", "system-ui", "sans-serif"],
        sans: ["var(--font-barlow)", "system-ui", "sans-serif"],
        mono: ["var(--font-plex)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        "glow-cyan": "var(--glow-sodium)",
        "glow-sodium": "var(--glow-sodium)",
        "glow-magenta": "var(--glow-glacier)",
        "glow-green": "var(--glow-arc)",
        "glow-red": "var(--glow-alarm)",
        "glow-amber": "var(--glow-gold)",
        panel: "var(--shadow-panel)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.45s ease-out",
        "slide-up": "slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "count-in": "count-in 0.5s cubic-bezier(0.16, 1, 0.3, 1) backwards",
        "glow-breathe": "glow-breathe 3.4s ease-in-out infinite",
        shimmer: "shimmer 0.7s ease-out",
      },
      keyframes: {
        fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      transitionTimingFunction: {
        // Decelerating ease for anything that "arrives" on screen.
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
        // Slight overshoot, for controls that should feel sprung.
        "out-back": "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
    },
  },
  plugins: [],
} satisfies Config;
