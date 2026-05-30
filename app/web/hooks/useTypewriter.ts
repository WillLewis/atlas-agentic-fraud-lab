"use client";

import { useEffect, useState } from "react";

export function useTypewriter(
  text: string,
  start: boolean,
  speed = 14,
  startDelay = 0
) {
  const [output, setOutput] = useState("");

  useEffect(() => {
    let frame = 0;
    let timeout = 0;

    if (!start) {
      timeout = window.setTimeout(() => setOutput(""), 0);
      return () => clearTimeout(timeout);
    }

    if (
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      timeout = window.setTimeout(() => setOutput(text), 0);
      return () => clearTimeout(timeout);
    }

    const begin = () => {
      let index = 0;
      let last = performance.now();

      const tick = (now: number) => {
        if (now - last >= speed) {
          index = Math.min(
            text.length,
            index + Math.max(1, Math.floor((now - last) / speed))
          );
          setOutput(text.slice(0, index));
          last = now;
        }
        if (index < text.length) frame = requestAnimationFrame(tick);
      };

      frame = requestAnimationFrame(tick);
    };

    timeout = window.setTimeout(begin, startDelay);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timeout);
    };
  }, [text, start, speed, startDelay]);

  return output;
}
