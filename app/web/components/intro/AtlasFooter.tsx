export function AtlasFooter() {
  return (
    <footer className="border-t border-intro-border bg-intro-background py-12 text-intro-foreground">
      <div className="mx-auto flex max-w-screen-xl flex-col gap-6 px-6 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="h-3 w-3 bg-intro-foreground" />
          <span className="font-display text-sm font-extrabold tracking-normal">
            ATLAS
          </span>
        </div>
        <p className="w-full text-right font-mono text-[10px] uppercase tracking-widest text-intro-muted md:w-auto md:whitespace-nowrap">
          Will Lewis &nbsp;|&nbsp; AI/ML Product Manager &nbsp;|&nbsp;{" "}
          <a
            href="https://linkedin.com/in/willlinkedin"
            target="_blank"
            rel="noreferrer"
            className="underline-offset-4 hover:text-intro-accent hover:underline"
          >
            linkedin.com/in/willlinkedin
          </a>
        </p>
      </div>
    </footer>
  );
}
