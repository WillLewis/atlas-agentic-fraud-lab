import type { JSX, ReactNode } from "react";

interface ChartRevealProps {
  children: ReactNode;
}

export function ChartReveal({ children }: ChartRevealProps): JSX.Element {
  return (
    <figure data-visible="true" className="line-plot-reveal w-full">
      {children}
    </figure>
  );
}
