"use client";

import { useInView } from "../../hooks/useInView";

export function TransitionBeat() {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.4 });

  return (
    <section
      id="atlas-intro-protocol-rule"
      ref={ref}
      className="relative flex items-center justify-center overflow-hidden border-y border-intro-border bg-intro-secondary/60 py-48"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.5]"
        style={{
          backgroundImage:
            "linear-gradient(to right, var(--atlas-intro-border) 1px, transparent 1px), linear-gradient(to bottom, var(--atlas-intro-border) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
          maskImage: "radial-gradient(ellipse at center, black 30%, transparent 75%)"
        }}
      />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-intro-accent/40 to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-intro-accent/40 to-transparent" />

      <div className="relative space-y-12 px-6 text-center">
        <div className="font-mono text-[10px] uppercase tracking-[0.4em] text-intro-accent">
          The Protocol Rule
        </div>
        <div className="flex flex-col items-center gap-6 md:flex-row md:gap-12">
          <span
            className={[
              "atlas-intro-fade-up atlas-intro-fade-slow font-display text-4xl font-extrabold uppercase tracking-normal text-intro-foreground md:text-6xl",
              inView ? "is-visible" : ""
            ].join(" ")}
          >
            Agents propose.
          </span>
          <span
            aria-hidden="true"
            className="block h-px overflow-hidden bg-intro-accent/40 transition-[width] duration-[2200ms] ease-out"
            style={{
              width: inView ? "6rem" : "0rem",
              transitionDelay: "700ms"
            }}
          />
          <span
            className={[
              "atlas-intro-fade-up atlas-intro-fade-slow font-display text-4xl font-extrabold uppercase tracking-normal text-intro-accent md:text-6xl",
              inView ? "is-visible" : ""
            ].join(" ")}
            style={{ transitionDelay: "1200ms" }}
          >
            Code decides.
          </span>
        </div>
        <p className="mx-auto max-w-md text-sm text-intro-muted">
          Agents reduce model miss rate, suggest defensive fixes, and argue for
          calibration. A deterministic judge, code rather than a model, accepts
          or rejects every recommendation.
        </p>
      </div>
    </section>
  );
}
