"use client";

import { useMemo } from "react";

import { useInView } from "../../hooks/useInView";
import { useTypewriter } from "../../hooks/useTypewriter";

interface Agent {
  id: string;
  codename: string;
  role: string;
  accentVar: string;
  dotClass: string;
  borderClass: string;
  lines: string[];
}

const AGENTS: Agent[] = [
  {
    id: "red",
    codename: "AGENT_RED_TEAM",
    role: "Red-Team",
    accentVar: "var(--atlas-intro-red-team)",
    dotClass: "bg-intro-red",
    borderClass: "border-intro-red/20",
    lines: [
      "I'm going to look for places where the risk model is too confident.",
      "If I find a group of synthetic cases the model is treating as lower risk than it should, I'll flag the pattern and show the evidence.",
      "My job is to find the gap."
    ]
  },
  {
    id: "blue",
    codename: "AGENT_BLUE_TEAM",
    role: "Bank-Defense",
    accentVar: "var(--atlas-intro-accent)",
    dotClass: "bg-intro-accent",
    borderClass: "border-intro-accent/20",
    lines: [
      "I'm going to propose a way to close that gap.",
      "That might mean adjusting the model's decision line, adding a better signal, or recalibrating how the model scores risk.",
      "My job is to make the system stronger without creating too much friction for customers."
    ]
  },
  {
    id: "judge",
    codename: "JUDGE",
    role: "The Judge",
    accentVar: "var(--atlas-intro-judge)",
    dotClass: "bg-intro-judge",
    borderClass: "border-intro-judge/20",
    lines: [
      "I'm going to test the defensive fix.",
      "If it only works on the examples we already found, it fails. If it catches more risk but creates too many extra reviews or declines, it stays flagged.",
      "My job is to decide whether the defense actually holds up."
    ]
  }
];

const TYPEWRITER_SPEED_MS = 18;
const SEQUENCE_MS_PER_CHARACTER = 28;
const AGENT_PAUSE_MS = 700;

const agentText = (agent: Agent) => agent.lines.join("\n\n");

const START_DELAYS_MS = AGENTS.map((agent, index) => {
  if (index === 0) return 0;
  return AGENTS.slice(0, index).reduce(
    (delay, priorAgent) =>
      delay +
      agentText(priorAgent).length * SEQUENCE_MS_PER_CHARACTER +
      AGENT_PAUSE_MS,
    0
  );
});

function AgentCard({
  agent,
  index,
  sectionInView
}: {
  agent: Agent;
  index: number;
  sectionInView: boolean;
}) {
  const joined = agentText(agent);
  const startDelay = START_DELAYS_MS[index] ?? 0;
  const typed = useTypewriter(
    joined,
    sectionInView,
    TYPEWRITER_SPEED_MS,
    startDelay
  );

  return (
    <div
      className={[
        "atlas-intro-fade-up relative flex flex-col gap-6 overflow-hidden rounded-2xl border bg-intro-card p-8 ring-1 ring-black/[0.02]",
        agent.borderClass,
        sectionInView ? "is-visible" : ""
      ].join(" ")}
      style={{ transitionDelay: `${index * 120}ms` }}
    >
      <span
        aria-hidden="true"
        className="atlas-intro-sweep pointer-events-none absolute inset-y-0 -left-1/2 w-1/2 bg-gradient-to-r from-transparent via-intro-foreground/[0.04] to-transparent"
        style={{
          animation: sectionInView
            ? `atlas-intro-sweep-keyframe 1.4s ease-out ${startDelay}ms 1 forwards`
            : "none"
        }}
      />

      <div className="flex items-center justify-between border-b border-intro-border pb-3 font-mono text-[10px] uppercase tracking-widest">
        <span style={{ color: agent.accentVar }}>{agent.codename}</span>
        <span className="text-intro-muted">{agent.role}</span>
      </div>

      <div className="flex items-center gap-3">
        <span className={`h-2 w-2 rounded-full ${agent.dotClass}`} />
        <span className="font-mono text-[10px] uppercase tracking-widest text-intro-muted">
          first-person briefing
        </span>
      </div>

      <div className="min-h-[180px] whitespace-pre-line text-[15px] leading-relaxed text-intro-foreground/90">
        {typed}
        {sectionInView && typed.length < joined.length ? (
          <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse bg-intro-accent align-middle" />
        ) : null}
      </div>
    </div>
  );
}

export function AgentSetup() {
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
      id="atlas-intro-agents"
      ref={ref}
      className="border-t border-intro-border bg-intro-card/40 py-32"
    >
      <div className="mx-auto max-w-screen-xl px-6">
        <div className="mb-16 max-w-2xl space-y-3">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-intro-accent">
            Agent Initialization
          </h2>
          <p className="text-3xl font-medium tracking-normal">
            Three voices. One synthetic environment.
          </p>
          <p className="text-intro-muted">
            Each agent speaks for itself before any round begins.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {AGENTS.map((agent, index) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              index={index}
              sectionInView={inView}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
