"use client";

import { useSyncExternalStore } from "react";

import { useInView } from "../../hooks/useInView";

const MANIFEST = [
  {
    term: "under_ranked_cohort",
    gloss:
      "A slice the scorer is treating as lower risk than the synthetic ground truth says it should."
  },
  {
    term: "model_miss_rate",
    gloss:
      "Share of synthetic high-risk cases the scorer fails to flag in a given cohort."
  },
  {
    term: "action_rate_limit",
    gloss:
      "Ceiling on extra reviews or declines a defense is allowed to introduce."
  },
  {
    term: "fix_generalization_score",
    gloss:
      "A judge-derived signal that the defensive fix works beyond the examples that produced it."
  }
] as const;

function usePrefersReducedMotion() {
  return useSyncExternalStore(
    (onStoreChange) => {
      const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
      if (!query) return () => undefined;
      query.addEventListener("change", onStoreChange);
      return () => query.removeEventListener("change", onStoreChange);
    },
    () => {
      return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    },
    () => false
  );
}

function LoopDiagram() {
  const reducedMotion = usePrefersReducedMotion();

  return (
    <svg
      viewBox="0 0 480 360"
      role="img"
      aria-label="Schematic of the ATLAS evaluation loop: red-team tests the mock risk scorer, bank-defense proposes defensive fixes, and the judge evaluates."
      className="block h-auto w-full"
    >
      <defs>
        <marker
          id="atlas-intro-arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
        </marker>
        <pattern
          id="atlas-intro-grid"
          width="24"
          height="24"
          patternUnits="userSpaceOnUse"
        >
          <path
            d="M24 0H0V24"
            fill="none"
            stroke="currentColor"
            strokeOpacity="0.06"
            strokeWidth="1"
          />
        </pattern>
      </defs>

      <rect
        width="480"
        height="360"
        fill="url(#atlas-intro-grid)"
        className="text-intro-foreground"
      />

      <g transform="translate(240 180)">
        <circle
          r="68"
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.18"
          strokeDasharray="3 4"
          className="text-intro-foreground"
        >
          {!reducedMotion ? (
            <animateTransform
              attributeName="transform"
              type="rotate"
              from="0"
              to="360"
              dur="60s"
              repeatCount="indefinite"
            />
          ) : null}
        </circle>
        <circle
          r="46"
          fill="var(--atlas-intro-card)"
          stroke="currentColor"
          strokeOpacity="0.25"
          className="text-intro-foreground"
        />
        <text
          textAnchor="middle"
          y="-4"
          className="fill-current text-[9px] uppercase tracking-[0.18em]"
          style={{ fontFamily: "JetBrains Mono, ui-monospace, monospace" }}
        >
          mock_risk
        </text>
        <text
          textAnchor="middle"
          y="10"
          className="fill-current text-[9px] uppercase tracking-[0.18em]"
          style={{ fontFamily: "JetBrains Mono, ui-monospace, monospace" }}
        >
          scorer
        </text>
        <text
          textAnchor="middle"
          y="26"
          className="fill-current text-[8px] tracking-[0.18em] opacity-60"
          style={{ fontFamily: "JetBrains Mono, ui-monospace, monospace" }}
        >
          v0.1 · synthetic
        </text>
      </g>

      {[
        { x: 80, y: 80, label: "RED_TEAM", sub: "tests", color: "var(--atlas-intro-red-team)" },
        { x: 400, y: 80, label: "BLUE_TEAM", sub: "fixes", color: "var(--atlas-intro-accent)" },
        { x: 240, y: 320, label: "JUDGE", sub: "evaluates", color: "var(--atlas-intro-judge)" }
      ].map((node) => (
        <g key={node.label} transform={`translate(${node.x} ${node.y})`}>
          <circle r="6" fill={node.color} opacity="0.9" />
          <circle r="14" fill="none" stroke={node.color} strokeOpacity="0.35" />
          <text
            x="0"
            y="-22"
            textAnchor="middle"
            className="fill-current text-[9px] uppercase tracking-[0.18em]"
            style={{ fontFamily: "JetBrains Mono, ui-monospace, monospace" }}
          >
            {node.label}
          </text>
          <text
            x="0"
            y="32"
            textAnchor="middle"
            className="fill-intro-muted text-[8px] uppercase tracking-[0.18em]"
            style={{ fontFamily: "JetBrains Mono, ui-monospace, monospace" }}
          >
            {node.sub}
          </text>
        </g>
      ))}

      <g
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.35"
        strokeWidth="1"
        className="text-intro-foreground"
        markerEnd="url(#atlas-intro-arrow)"
      >
        <path d="M96 96 C 150 140, 180 160, 198 160" />
        <path d="M384 96 C 330 140, 300 160, 282 160" />
        <path d="M240 306 C 240 260, 240 240, 240 226" />
      </g>

      {!reducedMotion ? (
        <>
          <circle r="2.5" fill="var(--atlas-intro-red-team)">
            <animateMotion
              dur="6s"
              repeatCount="indefinite"
              path="M96 96 C 150 140, 180 160, 198 160"
            />
          </circle>
          <circle r="2.5" fill="var(--atlas-intro-accent)">
            <animateMotion
              dur="6s"
              repeatCount="indefinite"
              begin="2s"
              path="M384 96 C 330 140, 300 160, 282 160"
            />
          </circle>
          <circle r="2.5" fill="var(--atlas-intro-judge)">
            <animateMotion
              dur="6s"
              repeatCount="indefinite"
              begin="4s"
              path="M240 306 C 240 260, 240 240, 240 226"
            />
          </circle>
        </>
      ) : null}
    </svg>
  );
}

export function IntroNarrative() {
  const { ref, inView } = useInView<HTMLDivElement>();

  return (
    <section
      id="atlas-intro-premise"
      ref={ref}
      className={`atlas-intro-fade-up relative mx-auto grid max-w-screen-xl grid-cols-1 gap-12 border-t border-intro-border px-6 py-32 lg:grid-cols-12 ${
        inView ? "is-visible" : ""
      }`}
    >
      <div className="lg:col-span-5">
        <h2 className="mb-6 font-mono text-[11px] uppercase tracking-[0.2em] text-intro-accent">
          The Premise
        </h2>
        <div className="space-y-6 text-xl leading-relaxed text-intro-muted">
          <p>
            As a fintech AI/ML PM, one question I kept returning to was "how
            can multi-agent red teams test defensive systems at scale, so blue
            teams can drive acceptable defensive fixes before model
            vulnerabilities reach production?"
          </p>
          <p>
            Manual policies and back-testing still matter. But forward-testing
            with agentic systems, agents that can search broadly, adapt quickly,
            and surface gaps humans struggle to anticipate one by one, opens a
            different kind of measurement surface.
          </p>
          <p>
            Project ATLAS is a synthetic, defensive experiment. A red-team agent
            searches a mock account-takeover risk scorer for model
            vulnerabilities. A bank-defense agent responds with defensive fixes.
            A deterministic judge evaluates whether each recommendation actually
            works.
          </p>
          <p>
            No real data. No real controls, no production endpoints, no
            institution-specific thresholds. The environment is limited and
            synthetic by design, but it hints at how teams might prepare for a
            world where AI finds weak spots faster than manual processes can.
          </p>
        </div>
      </div>

      <div className="lg:col-span-7">
        <div className="overflow-hidden rounded-2xl bg-intro-card ring-1 ring-intro-border">
          <div className="flex items-center justify-between border-b border-intro-border px-5 py-3">
            <span className="font-mono text-[10px] uppercase tracking-widest text-intro-muted">
              Observation deck · evaluation loop
            </span>
            <span className="font-mono text-[10px] uppercase tracking-widest text-intro-accent">
              live · v0.1
            </span>
          </div>
          <div className="px-6 py-6">
            <LoopDiagram />
          </div>
        </div>

        <div className="mt-6 rounded-2xl border border-intro-border bg-intro-card/50">
          <div className="flex items-center justify-between border-b border-intro-border px-5 py-3">
            <span className="font-mono text-[10px] uppercase tracking-widest text-intro-muted">
              Protocol manifest
            </span>
            <span className="font-mono text-[10px] uppercase tracking-widest text-intro-muted">
              terms · 04
            </span>
          </div>
          <dl className="divide-y divide-intro-border">
            {MANIFEST.map((item) => (
              <div
                key={item.term}
                className="grid grid-cols-1 gap-2 px-5 py-4 md:grid-cols-12 md:gap-6"
              >
                <dt className="font-mono text-[11px] uppercase tracking-widest text-intro-accent md:col-span-4">
                  {item.term}
                </dt>
                <dd className="text-sm leading-relaxed text-intro-muted md:col-span-8">
                  {item.gloss}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}
