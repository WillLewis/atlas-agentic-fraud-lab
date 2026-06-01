"use client";

import { useMemo } from "react";

import { useInView } from "../../hooks/useInView";

export function HeroSection() {
  const observerOptions = useMemo<IntersectionObserverInit>(
    () => ({
      threshold: 0.2,
      rootMargin: "-35% 0px -35% 0px"
    }),
    []
  );
  const { ref, inView } = useInView<HTMLElement>(observerOptions, false);

  return (
    <section
      id="atlas-intro-hero"
      ref={ref}
      className="relative flex min-h-screen flex-col items-center justify-center px-6 pt-32"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 flex items-center justify-center"
      >
        <span className="select-none font-display text-[25vw] font-extrabold leading-none tracking-normal text-intro-foreground/[0.04]">
          ATLAS
        </span>
      </div>

      <div
        className={[
          "atlas-intro-fade-up atlas-intro-fade-slow relative max-w-2xl space-y-8 text-center",
          inView ? "is-visible" : ""
        ].join(" ")}
      >
        <div className="inline-flex items-center gap-2 rounded-full border border-intro-border bg-intro-card/60 px-3 py-1 backdrop-blur-sm">
          <span className="atlas-intro-status-pulse h-1.5 w-1.5 rounded-full bg-intro-accent" />
          <span className="font-mono text-[10px] uppercase tracking-wider text-intro-foreground/70">
            Research Preview · v0.1
          </span>
        </div>

        <h1 className="text-balance text-4xl font-medium leading-[1.05] tracking-normal md:text-5xl">
          A synthetic lab for evaluating{" "}
          <span className="text-intro-accent">adversarial agentic safeguards.</span>
        </h1>

        <p className="mx-auto max-w-lg text-lg text-intro-muted">
          Project ATLAS observes a red-team agent, a bank-defense agent, and a
          deterministic judge as they test and propose defensive fixes for a
          mock account-takeover risk scorer, one synthetic round at a time.
        </p>

        <div className="flex items-center justify-center gap-3 pt-2">
          <span className="font-mono text-[10px] uppercase tracking-widest text-intro-muted">
            Generated cases · Defensive evaluation · Local mock scorer
          </span>
        </div>
      </div>

      <div className="absolute bottom-12 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-widest text-intro-muted">
          Scroll to observe
        </span>
        <span className="relative block h-12 w-px overflow-hidden bg-intro-border">
          <span className="atlas-intro-scroll-hint absolute inset-0 bg-intro-accent" />
        </span>
      </div>
    </section>
  );
}
