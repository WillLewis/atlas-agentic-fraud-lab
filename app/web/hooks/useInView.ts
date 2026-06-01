"use client";

import { useEffect, useRef, useState } from "react";

export function useInView<T extends HTMLElement = HTMLDivElement>(
  options: IntersectionObserverInit = {
    threshold: 0.2,
    rootMargin: "0px 0px -10% 0px"
  },
  once = true,
  initialInView = false
) {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(initialInView);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }

    const observer = new IntersectionObserver(([entry]) => {
      if (!entry) return;
      if (entry.isIntersecting) {
        setInView(true);
        if (once) observer.disconnect();
      } else if (!once) {
        setInView(false);
      }
    }, options);

    observer.observe(el);
    return () => observer.disconnect();
  }, [once, options]);

  return { ref, inView };
}
