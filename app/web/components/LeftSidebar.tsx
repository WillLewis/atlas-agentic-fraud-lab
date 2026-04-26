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
// IntersectionObserver hook — picks the topmost visible section as active.
// Falls back to the first step when no section is intersecting (e.g., user
// has scrolled above the first section) and the last step when all sections
// have scrolled past.
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

    // Account for the sticky disclaimer banner (~52px) at the top by
    // shrinking the observable region from the top, and bias the active
    // state toward sections in the upper half of the viewport.
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort(
            (a, b) => a.boundingClientRect.top - b.boundingClientRect.top
          );
        if (visible.length > 0) {
          const top = visible[0]!.target.id;
          setActiveId(top);
        }
      },
      {
        rootMargin: "-64px 0px -50% 0px",
        threshold: [0, 0.1, 0.25, 0.5]
      }
    );

    for (const el of elements) observer.observe(el);

    return () => observer.disconnect();
  }, [steps]);

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
      className="sticky top-12 hidden h-[calc(100vh-3rem)] shrink-0 border-r border-atlas-border bg-atlas-ink/60 px-3 py-6 md:block"
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
                  "group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-atlas-panel text-atlas-text"
                    : "text-atlas-muted hover:bg-atlas-panel/60 hover:text-atlas-text"
                ].join(" ")}
              >
                {/* Abstract step indicator: numbered circle.
                    aria-hidden because the visible label below carries the semantic step. */}
                <span
                  aria-hidden="true"
                  className={[
                    "relative flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold tabular-nums",
                    isActive
                      ? "border-atlas-accent bg-atlas-accent/15 text-atlas-accent"
                      : "border-atlas-border bg-atlas-surface text-atlas-muted group-hover:border-atlas-muted"
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
