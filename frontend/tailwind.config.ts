import type { Config } from "tailwindcss";

/** Every colour is also a CSS variable in globals.css. Declaring them here
 *  is what makes `text-hermes-muted` and friends actually emit CSS — before
 *  this, `hermes.text` and `hermes.muted` existed only as variables, so 312
 *  usages of `text-hermes-muted` / `text-hermes-text` across the Centers
 *  compiled to nothing and every label silently inherited the body colour.
 *  That is why the cockpit looked flat: it had no secondary text tone. */
export default {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        hermes: {
          // Substrate
          bg: "#05070d",
          "bg-deep": "#03040a",
          surface: "#090c16",
          card: "#0d1120",
          elevated: "#131829",
          border: "#1e2740",
          "border-bright": "#2c3a5c",

          // Signal
          cyan: "#00e5ff",
          "cyan-dim": "#0891a8",
          magenta: "#ff2d92",
          violet: "#a855f7",
          green: "#2bff88",
          amber: "#ffb020",
          red: "#ff3355",
          blue: "#3b82f6",

          // Aliases kept so pre-redesign markup keeps rendering.
          "amber-bright": "#ffc44d",
          purple: "#a855f7",

          // Type — the two that were missing.
          text: "#e6ecf7",
          "text-bright": "#ffffff",
          muted: "#7b88a6",
          dim: "#4d5876",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "ui-monospace", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        "glow-cyan": "0 0 12px rgba(0,229,255,0.45), 0 0 32px rgba(0,229,255,0.15)",
        "glow-magenta": "0 0 12px rgba(255,45,146,0.45), 0 0 32px rgba(255,45,146,0.15)",
        "glow-green": "0 0 12px rgba(43,255,136,0.4), 0 0 28px rgba(43,255,136,0.12)",
        "glow-red": "0 0 12px rgba(255,51,85,0.45), 0 0 28px rgba(255,51,85,0.15)",
        "glow-amber": "0 0 12px rgba(255,176,32,0.4), 0 0 28px rgba(255,176,32,0.12)",
        panel: "0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.45s ease-out",
        "slide-up": "slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "count-in": "count-in 0.5s cubic-bezier(0.16, 1, 0.3, 1) backwards",
        "glow-breathe": "glow-breathe 3s ease-in-out infinite",
        shimmer: "shimmer 0.75s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      transitionTimingFunction: {
        // Decelerating ease used for anything that "arrives" on screen.
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
} satisfies Config;
