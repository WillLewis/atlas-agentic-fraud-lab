// app/web/components/LeftSidebar.tsx
// Five-step left-rail navigation for the Project Atlas scrollytelling page.
//
// Step labels are public-safe and match Bible §8 narrative ordering exactly.
// They live in a single STEPS constant so the safety scanner can inspect
// them as structured data (CLAUDE.md / Bible §22) and so a future API route
// can serialize the same shape if needed.
//
// Abstract shapes only — numbered circles + connector segments. No human
// imagery, photos, or person icons (Bible §8 Step 1, architecture doc
// §1.2 failure mode "uses human images").
//
// Active section tracking uses IntersectionObserver so we don't burn a
// scroll listener; the sidebar gracefully no-ops when sections aren't yet
// mounted (e.g., suspense, partial hydration, or before component 15
// composes the page).

"use client";

import { useEffect, useMemo, useState } from "react";

// ---------------------------------------------------------------------------
// Step metadata — single source of truth for the navigation rail.
// Section IDs are referenced from app/page.tsx (component 15) as anchors.
// ---------------------------------------------------------------------------

export interface SidebarStep {
  id: string;
  label: string;
  step_number: number;
}

export const SIDEBAR_STEPS: readonly SidebarStep[] = [
  { id: "agents-assigned", label: "Agents Assigned", step_number: 1 },
  { id: "agents-deployed", label: "Agents Deployed", step_number: 2 },
  { id: "round-1", label: "Round 1", step_number: 3 },
  { id: "round-2", label: "Round 2", step_number: 4 },
  { id: "round-3", label: "Round 3 — Final Report", step_number: 5 }
] as const;

// ---------------------------------------------------------------------------
// Scroll-spy hook — picks the last section whose top has crossed the
// viewport marker. This keeps the rail aligned with the section the reader is
// actually in, instead of jumping early when the next section peeks into view.
// ---------------------------------------------------------------------------

function useActiveStepId(steps: readonly SidebarStep[]): string {
  const fallback = steps[0]?.id ?? "";
  const [activeId, setActiveId] = useState<string>(fallback);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const elements = steps
      .map((s) => document.getElementById(s.id))
      .filter((el): el is HTMLElement => el !== null);

    if (elements.length === 0) return;

    const updateActive = () => {
      const markerY = 96;
      let nextActive = elements[0]?.id ?? fallback;

      for (const el of elements) {
        const top = el.getBoundingClientRect().top;
        if (top <= markerY) {
          nextActive = el.id;
        } else {
          break;
        }
      }

      setActiveId((current) => (current === nextActive ? current : nextActive));
    };

    updateActive();
    window.addEventListener("scroll", updateActive, { passive: true });
    window.addEventListener("resize", updateActive);

    return () => {
      window.removeEventListener("scroll", updateActive);
      window.removeEventListener("resize", updateActive);
    };
  }, [fallback, steps]);

  return activeId;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LeftSidebar() {
  const steps = useMemo(() => SIDEBAR_STEPS, []);
  const activeId = useActiveStepId(steps);

  return (
    <nav
      aria-label="Project Atlas — five-step narrative navigation"
      className="sticky top-12 hidden h-[calc(100vh-3rem)] shrink-0 border-r border-atlas-border bg-atlas-panel/85 px-3 py-6 backdrop-blur md:block"
      style={{ width: "var(--atlas-sidebar-width)" }}
    >
      <p className="px-3 pb-4 font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
        Five-step demo
      </p>
      <ol className="flex flex-col gap-1">
        {steps.map((step, index) => {
          const isActive = step.id === activeId;
          const isLast = index === steps.length - 1;
          return (
            <li key={step.id} className="relative">
              <a
                href={`#${step.id}`}
                aria-current={isActive ? "step" : undefined}
                className={[
                  "group flex items-center gap-3 rounded-md border px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-atlas-accent/25",
                  isActive
                    ? "border-atlas-accent/40 bg-atlas-accent/10 text-atlas-text shadow-sm"
                    : "border-transparent text-atlas-muted hover:bg-atlas-surface/70 hover:text-atlas-text"
                ].join(" ")}
              >
                {/* Abstract step indicator: numbered circle.
                    aria-hidden because the visible label below carries the semantic step. */}
                <span
                  aria-hidden="true"
                  className={[
                    "relative flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold tabular-nums",
                    isActive
                      ? "border-atlas-accent bg-atlas-accent/10 text-atlas-accent"
                      : "border-atlas-border bg-atlas-panel text-atlas-muted group-hover:border-atlas-muted"
                  ].join(" ")}
                >
                  {step.step_number}
                </span>
                <span className="leading-tight">{step.label}</span>
              </a>
              {/* Connector segment between steps — purely decorative shape. */}
              {!isLast && (
                <span
                  aria-hidden="true"
                  className="absolute left-[1.5rem] top-[2.25rem] h-3 w-px bg-atlas-border"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
