import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      // ── Color system (mirrors CSS variables in globals.css) ───────────────
      colors: {
        space: {
          deep:     "var(--color-space-deep)",
          midnight: "var(--color-space-midnight)",
          navy:     "var(--color-space-navy)",
          surface:  "var(--color-space-surface)",
          elevated: "var(--color-space-elevated)",
          border:   "var(--color-space-border)",
          "border-strong": "var(--color-space-border-strong)",
          text:     "var(--color-text-primary)",
          muted:    "var(--color-text-secondary)",
          tertiary: "var(--color-text-tertiary)",
          accent:   "var(--color-text-accent)",
        },
        accent: {
          indigo:        "var(--color-accent-indigo)",
          "indigo-bright": "var(--color-accent-indigo-bright)",
          "indigo-dim":    "var(--color-accent-indigo-dim)",
          "indigo-glow":   "var(--color-accent-indigo-glow)",
          amber:         "var(--color-accent-amber)",
          "amber-bright":  "var(--color-accent-amber-bright)",
          "amber-dim":     "var(--color-accent-amber-dim)",
          "amber-glow":    "var(--color-accent-amber-glow)",
          green:         "var(--color-accent-green)",
          "green-bright":  "var(--color-accent-green-bright)",
          "green-dim":     "var(--color-accent-green-dim)",
          red:           "var(--color-accent-red)",
          "red-bright":    "var(--color-accent-red-bright)",
          "red-glow":      "var(--color-accent-red-glow)",
        },
      },

      // ── Typography ────────────────────────────────────────────────────────
      fontFamily: {
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        body:    ["var(--font-body)", "system-ui", "sans-serif"],
        mono:    ["var(--font-mono)", "monospace"],
      },

      // ── Border radius ─────────────────────────────────────────────────────
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },

      // ── Box shadows ───────────────────────────────────────────────────────
      boxShadow: {
        "indigo-glow": "var(--shadow-indigo-glow)",
        "amber-glow":  "var(--shadow-amber-glow)",
        panel:         "var(--shadow-panel)",
      },

      // ── Transitions ───────────────────────────────────────────────────────
      transitionDuration: {
        fast: "var(--transition-fast)",
        base: "var(--transition-base)",
        slow: "var(--transition-slow)",
      },

      // ── Animation ─────────────────────────────────────────────────────────
      keyframes: {
        "pulse-red": {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0.6" },
        },
        "satellite-ping": {
          "75%, 100%": { transform: "scale(2)", opacity: "0" },
        },
        "data-update": {
          "0%":   { color: "var(--color-accent-indigo-bright)" },
          "100%": { color: "var(--color-text-data)" },
        },
      },
      animation: {
        "pulse-red":    "pulse-red 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "sat-ping":     "satellite-ping 1.5s ease-out infinite",
        "data-update":  "data-update 1s ease-out forwards",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
