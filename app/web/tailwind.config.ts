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
        }
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Inter", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"]
      }
    }
  },
  plugins: []
};

export default config;
