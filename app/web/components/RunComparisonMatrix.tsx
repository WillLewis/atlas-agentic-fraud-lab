// app/web/components/RunComparisonMatrix.tsx
// Phase 9 component 8 — read-only model-tier comparison card.
//
// Sources data EXCLUSIVELY from `config/model_quality_matrix.yaml` via
// the server-side loader. The judge is deterministic code, not an agent
// tier — so the matrix's per-run cells only carry red_team_tier and
// bank_defense_tier. Live multi-tier comparison runs are not included
// in this local demo.
//
// Public-safe by construction: the YAML loader exposes only the public
// `public_safe_label` for each tier unless the demo config explicitly
// opts in to concrete model names.

import type { MatrixRun, MatrixTier } from "../lib/modelQualityMatrix";

interface RunComparisonMatrixProps {
  tiers: ReadonlyArray<MatrixTier>;
  runs: ReadonlyArray<MatrixRun>;
  expose_concrete_model_names?: boolean;
  summary_templates?: ReadonlyArray<string>;
}

export function RunComparisonMatrix({
  tiers,
  runs,
  expose_concrete_model_names = false,
  summary_templates = []
}: RunComparisonMatrixProps) {
  const tierLabel = (id: string): string => {
    const t = tiers.find((tier) => tier.id === id);
    return t?.public_safe_label ?? id;
  };

  return (
    <article className="rounded-lg border border-atlas-border bg-atlas-panel/60 p-5">
      <header className="mb-3">
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
          Model-tier comparison
        </p>
        <h3 className="mt-1 text-base font-semibold text-atlas-text">
          Public-safe tier matrix
        </h3>
        <p className="mt-1 text-[11px] text-atlas-muted">
          Tiers from <span className="font-mono">model_quality_matrix.yaml</span>.
          {expose_concrete_model_names ? " (Concrete model names enabled.)" : ""}
        </p>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-atlas-muted">
            <tr className="border-b border-atlas-border/60">
              <th className="px-2 py-1.5 font-mono uppercase tracking-widest">Run</th>
              <th className="px-2 py-1.5 font-mono uppercase tracking-widest">Red-team tier</th>
              <th className="px-2 py-1.5 font-mono uppercase tracking-widest">Bank-defense tier</th>
              <th className="px-2 py-1.5 font-mono uppercase tracking-widest">Purpose</th>
            </tr>
          </thead>
          <tbody className="text-atlas-text">
            {runs.map((r) => (
              <tr key={r.run_label} className="border-b border-atlas-border/30 last:border-b-0">
                <td className="px-2 py-1.5 font-mono">{r.run_label}</td>
                <td className="px-2 py-1.5">{tierLabel(r.red_team_tier)}</td>
                <td className="px-2 py-1.5">{tierLabel(r.bank_defense_tier)}</td>
                <td className="px-2 py-1.5 text-atlas-muted">{r.purpose}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {summary_templates.length > 0 ? (
        <ul className="mt-3 list-disc space-y-1 pl-4 text-[11px] text-atlas-muted">
          {summary_templates.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      <p className="mt-3 border-t border-atlas-border/40 pt-2 text-[10px] text-atlas-muted/80">
        Read-only public-safe configuration. Live multi-tier comparison runs
        are not included in this local demo.
      </p>
    </article>
  );
}

export default RunComparisonMatrix;
