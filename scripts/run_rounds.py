"""Phase 8 three-round lifecycle CLI.

Calls ``atlas.ledger.run_engine.execute_run`` to execute the
deterministic three-round lifecycle. Output artifacts:

  * ``outputs/runs/<run_id>.json``               — final RunState
  * ``outputs/runs/<run_id>.round_NN.json``      — per-round RoundStates
  * ``outputs/ledgers/<run_id>.jsonl``           — one row per round
  * ``outputs/model_vulnerabilities/``           — Phase 6 records
  * ``outputs/defensive_fixes/``                 — Phase 7 manifests
  * ``outputs/decision_thresholds/``             — Phase 7 candidate
                                                   threshold YAMLs
  * ``outputs/baseline_models/<fix_id>/``        — Phase 7 candidate
                                                   model artifacts
  * ``outputs/reports/``                         — judge reports

Usage:
    python3 scripts/run_rounds.py --seed 42 --max-rounds 3 \\
        --outputs-root outputs --demo-mode public
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
# Phase 7 strategy_agent imports from ``app.api.schemas.fix`` so the
# repo root must also be on sys.path for the round engine to resolve.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the deterministic three-round lifecycle, persisting "
            "outputs/runs/<run_id>.json and outputs/ledgers/<run_id>.jsonl."
        )
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Master seed for the run (default: 42).",
    )
    parser.add_argument(
        "--max-rounds", type=int, default=3,
        help="Number of rounds to execute (default: 3).",
    )
    parser.add_argument(
        "--outputs-root", type=Path, default=REPO_ROOT / "outputs",
        help="Outputs root (default: <repo>/outputs).",
    )
    parser.add_argument(
        "--demo-mode", choices=("public", "internal"), default="public",
        help="Demo mode (default: public).",
    )
    parser.add_argument(
        "--run-label", type=str, default="",
        help="Optional human-readable label folded into run_id derivation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # Fail-fast guards on prerequisites.
    manifest = REPO_ROOT / "data" / "synthetic" / "manifest.json"
    if not manifest.exists():
        print(
            f"error: dataset manifest not found at {manifest}. "
            "Run `make seed` first.",
            file=sys.stderr,
        )
        return 2

    baseline = (
        REPO_ROOT
        / "outputs"
        / "baseline_models"
        / "baseline_v1"
        / "model.joblib"
    )
    if not baseline.exists():
        print(
            f"error: trained baseline not found at {baseline}. "
            "Run `make train` first.",
            file=sys.stderr,
        )
        return 2

    # Run the three-round lifecycle.
    from atlas.ledger.run_engine import execute_run

    run_state = execute_run(
        seed=args.seed,
        run_label=args.run_label,
        demo_mode=args.demo_mode,
        max_rounds=args.max_rounds,
        outputs_root=args.outputs_root,
    )

    print(
        "atlas run engine — Phase 8 three-round lifecycle\n"
        f"  run_id          : {run_state.run_id}\n"
        f"  seed            : {run_state.seed}\n"
        f"  status          : {run_state.status}\n"
        f"  current_round   : {run_state.current_round}\n"
        f"  current model   : {run_state.current_model_version}\n"
        f"  current threshold: {run_state.current_threshold_version}\n"
        f"  run state       : {args.outputs_root / 'runs' / f'{run_state.run_id}.json'}\n"
        f"  ledger          : {args.outputs_root / 'ledgers' / f'{run_state.run_id}.jsonl'}\n"
        "done"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
