// app/web/components/DualLabel.tsx
// Renders the canonical technical term as a muted mono subtitle beneath a
// plain-language headline. Pair the headline + this subtitle, and put the
// definition on the wrapping element's title attribute for a hover tooltip.

export function TermNote({ children }: { children: React.ReactNode }) {
  return (
    <span className="mt-0.5 block font-mono text-[10px] normal-case tracking-wide text-atlas-muted/80">
      {children}
    </span>
  );
}
