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
          ink: "#0b1020",
          surface: "#101729",
          panel: "#161e34",
          border: "#243054",
          muted: "#8a93b2",
          text: "#e6e9f2",
          accent: "#6ea8fe",
          warn: "#f4b860",
          danger: "#f06a6a",
          ok: "#7bd88f"
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
