// app/web/app/layout.tsx
// Root layout for the Project Atlas web shell.
//
// Every user-facing label here flows from config/demo.yaml via
// getDemoConfig(). No institution name, model name, or disclaimer string is
// hard-coded — the safety scanner depends on this.
//
// The disclaimer banner is a persistent slot at the top of every page.
// Component 7 (DisclaimerBanner.tsx) will replace the inline placeholder
// below with the real component; the slot's structural position and styling
// stay stable across that swap.

import type { Metadata } from "next";
import "./globals.css";

import { DisclaimerBanner } from "../components/DisclaimerBanner";
import { getDemoConfig } from "../lib/demoConfig";

export function generateMetadata(): Metadata {
  const config = getDemoConfig();
  return {
    title: "Project ATLAS — Synthetic Fraud-Model Evaluation",
    description: [
      `Synthetic red/blue evaluation arena for ${config.model_label}`,
      `at ${config.institution_label}.`,
      "Local-only, public-safe demo. Not a production fraud system."
    ].join(" "),
    robots: { index: false, follow: false }
  };
}

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      {/* ``suppressHydrationWarning`` covers attributes injected by
          browser extensions (e.g. ColorZilla's ``cz-shortcut-listen``,
          dark-mode helpers) before React hydrates. Per Next.js docs at
          https://nextjs.org/docs/messages/react-hydration-error this is
          the recommended escape for body-level extension noise. The
          flag is scoped to ``<body>`` so genuine hydration mismatches
          inside the page tree still surface. */}
      <body
        className="min-h-screen bg-intro-background text-atlas-text antialiased"
        suppressHydrationWarning
      >
        {/* Persistent disclaimer banner slot.
            Banner content lives in <DisclaimerBanner />; this wrapper owns
            the sticky positioning so the rest of layout doesn't have to know
            about scroll behavior. */}
        <div
          role="region"
          aria-label="Synthetic-only disclaimer"
          className="sticky top-0 z-40"
          data-slot="disclaimer-banner"
        >
          <DisclaimerBanner />
        </div>

        {children}
      </body>
    </html>
  );
}
