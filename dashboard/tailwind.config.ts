import type { Config } from "tailwindcss";

// Every color maps to a CSS variable in app/globals.css (the single source of the tokens).
const rgb = (name: string) => `rgb(var(--aw-${name}) / <alpha-value>)`;

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: rgb("bg"),
        foreground: rgb("text"),
        muted: rgb("text-muted"),
        surface: { DEFAULT: rgb("surface"), raised: rgb("surface-raised") },
        accent: {
          DEFAULT: rgb("accent"),
          strong: rgb("accent-strong"),
          soft: "var(--aw-accent-soft)",
        },
        amber: rgb("amber"),
        danger: rgb("danger"),
        success: rgb("success"),
      },
      borderColor: {
        DEFAULT: "var(--aw-border)",
        strong: "var(--aw-border-strong)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      backgroundImage: {
        // Amber radial highlight over an orange gradient. Dark text on any point is >= 6.35:1.
        hero: "radial-gradient(circle at 85% 15%, rgb(var(--aw-amber)) 0%, transparent 55%), linear-gradient(135deg, rgb(var(--aw-accent-strong)) 0%, rgb(var(--aw-accent)) 100%)",
        "cap-bar": "linear-gradient(90deg, rgb(var(--aw-accent-strong)), rgb(var(--aw-amber)))",
      },
      boxShadow: {
        glow: "0 0 60px -12px rgb(var(--aw-accent-strong) / 0.6)",
      },
      dropShadow: {
        glow: "0 0 4px rgb(var(--aw-accent) / 0.6)",
      },
    },
  },
  plugins: [],
};

export default config;
