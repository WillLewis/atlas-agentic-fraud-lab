import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        atlas: {
          ink: "#f6f7fb",
          surface: "#eef2f7",
          panel: "#ffffff",
          border: "#d8dee9",
          muted: "#667085",
          text: "#1f2937",
          accent: "#1f6feb",
          warn: "#b54708",
          danger: "#d92d20",
          ok: "#027a48"
        },
        intro: {
          background: "#faf8f2",
          foreground: "#1f2937",
          card: "#ffffff",
          secondary: "#f1efe8",
          muted: "#667085",
          accent: "#2b7cff",
          border: "rgba(31, 41, 55, 0.1)",
          red: "#df3344",
          judge: "#a87908"
        }
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Inter", "sans-serif"],
        display: ["Inter Display", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"]
      }
    }
  },
  plugins: []
};

export default config;
