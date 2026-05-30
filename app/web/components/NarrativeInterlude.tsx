"use client";

import { useMemo } from "react";

import { useInView } from "../hooks/useInView";

interface NarrativeInterludeProps {
  id: string;
  eyebrow: string;
  title: string;
  lead: string;
  paragraphs: readonly string[];
  footer?: string;
  criteria?: readonly string[];
  watermark?: string;
}

export function NarrativeInterlude({
  id,
  eyebrow,
  title,
  lead,
  paragraphs,
  footer,
  criteria = [],
  watermark
}: NarrativeInterludeProps) {
  const observerOptions = useMemo<IntersectionObserverInit>(
    () => ({
      threshold: 0.35,
      rootMargin: "-18% 0px -18% 0px"
    }),
    []
  );
  const { ref, inView } = useInView<HTMLElement>(observerOptions, false);
  const headingId = `${id}-heading`;

  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className="atlas-narrative-break"
    >
      {watermark ? (
        <span aria-hidden="true" className="atlas-narrative-watermark">
          {watermark}
        </span>
      ) : null}

      <article
        ref={ref}
        className={[
          "atlas-narrative-panel",
          inView ? "is-visible" : ""
        ].join(" ")}
      >
        <span aria-hidden="true" className="atlas-narrative-rule" />
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.22em] text-atlas-accent">
          {eyebrow}
        </p>
        <h2 id={headingId} className="atlas-narrative-title">
          {title}
        </h2>
        <p className="atlas-narrative-lead">{lead}</p>
        {paragraphs.map((paragraph) => (
          <p key={paragraph} className="atlas-narrative-copy">
            {paragraph}
          </p>
        ))}

        {criteria.length > 0 ? (
          <ul className="atlas-narrative-criteria" aria-label="Evaluation criteria">
            {criteria.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}

        {footer ? (
          <div className="atlas-narrative-footer">
            <span>{footer}</span>
          </div>
        ) : null}
      </article>
    </section>
  );
}

export default NarrativeInterlude;
