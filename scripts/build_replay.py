"""Phase 8 replay-builder CLI.

Loads a completed run's state + ledger artifacts and emits a public-
safe ``ReplayPayload`` JSON file at
``outputs/demo_replays/<run_id>.json`` aligned to the web shell's
existing types in ``app/web/lib/types.ts``.

Usage:
    python3 scripts/build_replay.py --run-id run_xxxx \\
        --outputs-root outputs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
# Phase 7 strategy_agent imports from ``app.api.schemas.fix`` (transitive
# via the round engine's loader), so the repo root must be on sys.path.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a public-safe replay payload at "
            "outputs/demo_replays/<run_id>.json from a completed run's "
            "state + ledger artifacts."
        )
    )
    parser.add_argument(
        "--run-id", type=str, required=True,
        help="Run ID (matches outputs/runs/<run_id>.json filename).",
    )
    parser.add_argument(
        "--outputs-root", type=Path, default=REPO_ROOT / "outputs",
        help="Outputs root (default: <repo>/outputs).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    run_state_path = args.outputs_root / "runs" / f"{args.run_id}.json"
    if not run_state_path.exists():
        print(
            f"error: run state not found at {run_state_path}. "
            "Run `make run-rounds` first.",
            file=sys.stderr,
        )
        return 2

    from atlas.ledger.ledger import (
        load_round_state,
        load_run_state,
        round_state_path,
    )
    from atlas.ledger.replay import build_replay_payload, persist_replay_payload

    run_state = load_run_state(args.run_id, outputs_root=args.outputs_root)

    # Load each persisted RoundState. ``run_state.max_rounds`` bounds the
    # search; we stop at the first missing round so partial runs still
    # produce a useful replay (matches the 1-round edge-case test).
    round_states = []
    for rid in range(1, run_state.max_rounds + 1):
        path = round_state_path(args.run_id, rid, outputs_root=args.outputs_root)
        if not path.exists():
            break
        round_states.append(
            load_round_state(args.run_id, rid, outputs_root=args.outputs_root)
        )

    if not round_states:
        print(
            f"error: no round states found for run {args.run_id!r}. "
            "Run `make run-rounds` first.",
            file=sys.stderr,
        )
        return 2

    payload = build_replay_payload(
        run_state, round_states, outputs_root=args.outputs_root,
    )
    out_path = persist_replay_payload(
        payload, run_id=args.run_id, outputs_root=args.outputs_root,
    )

    print(
        "atlas replay builder — Phase 8\n"
        f"  run_id          : {run_state.run_id}\n"
        f"  rounds loaded   : {len(round_states)}\n"
        f"  five_step_story : {len(payload['five_step_story'])} steps\n"
        f"  round_metrics   : {len(payload['charts']['round_metrics'])} snapshots\n"
        f"  output          : {out_path}\n"
        "done"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
