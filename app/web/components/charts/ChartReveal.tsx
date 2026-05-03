"use client";

import { useEffect, useRef, useState } from "react";
import type { JSX, ReactNode } from "react";

interface ChartRevealProps {
  children: ReactNode;
}

export function ChartReveal({ children }: ChartRevealProps): JSX.Element {
  const figureRef = useRef<HTMLElement | null>(null);
  const [hasEntered, setHasEntered] = useState(false);

  useEffect(() => {
    const node = figureRef.current;
    if (!node) {
      return;
    }

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const animationFrame = window.requestAnimationFrame(() => {
      if (mediaQuery.matches || !("IntersectionObserver" in window)) {
        setHasEntered(true);
      }
    });

    if (mediaQuery.matches || !("IntersectionObserver" in window)) {
      return () => window.cancelAnimationFrame(animationFrame);
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) {
          return;
        }
        setHasEntered(true);
        observer.unobserve(entry.target);
      },
      { root: null, rootMargin: "0px 0px -16% 0px", threshold: 0.28 }
    );

    observer.observe(node);
    return () => {
      window.cancelAnimationFrame(animationFrame);
      observer.disconnect();
    };
  }, []);

  return (
    <figure
      ref={figureRef}
      data-visible={hasEntered ? "true" : "false"}
      className="line-plot-reveal w-full"
    >
      {children}
    </figure>
  );
}
