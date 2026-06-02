"use client";

import { useMemo } from "react";

import { useInView } from "../../hooks/useInView";

export function TransitionBeat() {
  const observerOptions = useMemo<IntersectionObserverInit>(
    () => ({
      threshold: 0.2,
      rootMargin: "-35% 0px -35% 0px"
    }),
    []
  );
  const { ref, inView } = useInView<HTMLDivElement>(observerOptions, false);

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
        <div className="mx-auto grid w-full max-w-4xl grid-cols-1 items-center gap-5 sm:grid-cols-[minmax(0,1fr)_6rem_minmax(0,1fr)] md:grid-cols-[minmax(0,1fr)_7rem_minmax(0,1fr)] md:gap-8">
          <span
            className={[
              "atlas-intro-fade-up atlas-intro-fade-slow whitespace-nowrap text-center font-display text-4xl font-extrabold uppercase leading-[0.9] tracking-normal text-intro-foreground sm:text-right md:text-5xl",
              inView ? "is-visible" : ""
            ].join(" ")}
          >
            Agents
            <br />
            propose
          </span>
          <span
            aria-hidden="true"
            className="mx-auto block h-px overflow-hidden bg-intro-accent/40 transition-[width] duration-[2200ms] ease-out"
            style={{
              width: inView ? "100%" : "0rem",
              transitionDelay: "700ms"
            }}
          />
          <span
            className={[
              "atlas-intro-fade-up atlas-intro-fade-slow whitespace-nowrap text-center font-display text-4xl font-extrabold uppercase leading-[0.9] tracking-normal text-intro-accent sm:text-left md:text-5xl",
              inView ? "is-visible" : ""
            ].join(" ")}
            style={{ transitionDelay: "1200ms" }}
          >
            Code
            <br />
            decides
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
