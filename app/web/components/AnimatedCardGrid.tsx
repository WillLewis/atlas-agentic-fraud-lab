"use client";

import { Children, type CSSProperties, type ReactNode } from "react";

import { useInView } from "../hooks/useInView";

const CARD_STAGGER_MS = 320;
const CARD_REVEAL_OPTIONS: IntersectionObserverInit = {
  rootMargin: "0px 0px -8% 0px",
  threshold: 0.01
};

interface AnimatedCardGridProps {
  children: ReactNode;
  className: string;
  itemClassName?: string;
  itemClassNames?: readonly string[];
  staggerMs?: number;
}

interface AnimatedAgentCardGridProps {
  children: ReactNode;
}

function itemClassNameFor(
  itemClassName: string | undefined,
  itemClassNames: readonly string[] | undefined,
  index: number
) {
  return itemClassNames?.[index] ?? itemClassName;
}

function itemStyle(index: number, staggerMs: number): CSSProperties {
  return {
    "--atlas-card-delay": `${index * staggerMs}ms`
  } as CSSProperties;
}

export function AnimatedCardGrid({
  children,
  className,
  itemClassName,
  itemClassNames,
  staggerMs = CARD_STAGGER_MS
}: AnimatedCardGridProps) {
  const { ref, inView } = useInView<HTMLDivElement>(CARD_REVEAL_OPTIONS, true);

  return (
    <div
      ref={ref}
      data-visible={inView ? "true" : "false"}
      className={`atlas-card-grid ${className}`}
    >
      {Children.toArray(children).map((card, i) => (
        <div
          key={i}
          className={["atlas-card-item", itemClassNameFor(itemClassName, itemClassNames, i)]
            .filter(Boolean)
            .join(" ")}
          style={itemStyle(i, staggerMs)}
        >
          {card}
        </div>
      ))}
    </div>
  );
}

export function AnimatedAgentCardGrid({ children }: AnimatedAgentCardGridProps) {
  const { ref, inView } = useInView<HTMLUListElement>(CARD_REVEAL_OPTIONS, true);

  return (
    <ul
      ref={ref}
      role="list"
      data-visible={inView ? "true" : "false"}
      className="atlas-card-grid mx-auto flex max-w-6xl flex-wrap justify-center gap-x-4 gap-y-7 px-2"
    >
      {Children.toArray(children).map((card, i) => (
        <li
          key={i}
          className="atlas-card-item w-full max-w-sm sm:w-[calc(50%-0.5rem)] lg:w-[calc(33.333%-0.75rem)] xl:w-[calc(25%-0.75rem)]"
          style={itemStyle(i, CARD_STAGGER_MS)}
        >
          {card}
        </li>
      ))}
    </ul>
  );
}
