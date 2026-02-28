import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // 7 context network colors
        network: {
          academic: { DEFAULT: "#6366f1", light: "#a5b4fc", dark: "#4338ca" },
          professional: {
            DEFAULT: "#0ea5e9",
            light: "#7dd3fc",
            dark: "#0369a1",
          },
          financial: { DEFAULT: "#10b981", light: "#6ee7b7", dark: "#047857" },
          health: { DEFAULT: "#f43f5e", light: "#fda4af", dark: "#be123c" },
          "personal-growth": {
            DEFAULT: "#f59e0b",
            light: "#fcd34d",
            dark: "#b45309",
          },
          social: { DEFAULT: "#8b5cf6", light: "#c4b5fd", dark: "#6d28d9" },
          ventures: { DEFAULT: "#ec4899", light: "#f9a8d4", dark: "#be185d" },
        },
        // App-wide semantic colors
        surface: {
          DEFAULT: "#0f172a",
          raised: "#1e293b",
          overlay: "#334155",
        },
        border: {
          DEFAULT: "#334155",
          subtle: "#1e293b",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
