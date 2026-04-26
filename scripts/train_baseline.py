#!/usr/bin/env python3
"""Phase 4 baseline trainer entry point.

Reads:
    data/synthetic/features/{train,validation}.json
    data/synthetic/labels/label_generation.json
    data/synthetic/splits/customers_split_membership.json

Writes:
    outputs/baseline_models/baseline_v1/{model.joblib, calibration.json,
                                         feature_columns.json,
                                         baseline_summary.json}

Holdout partitions are NEVER used for fitting — Phase 4 invariant.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="train_baseline",
        description=(
            "Train the Phase 4 baseline mock scorer + calibrator on the "
            "synthetic dataset and persist artifacts under "
            "outputs/baseline_models/baseline_v1/."
        ),
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "data" / "synthetic",
        help="Phase 2/3 dataset directory (default: data/synthetic).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "baseline_models" / "baseline_v1",
        help="Where to write trained baseline artifacts.",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    # Import inside main so --help works even if sklearn isn't installed.
    from atlas.model.train import train_baseline_model

    if not args.quiet:
        print(f"atlas baseline trainer")
        print(f"  seed       : {args.seed}")
        print(f"  data_dir   : {args.data_dir}")
        print(f"  output_dir : {args.output_dir}")

    summary = train_baseline_model(
        seed=args.seed, data_dir=args.data_dir, output_dir=args.output_dir
    )

    if not args.quiet:
        print()
        print(f"  fit_partition_counts        : {summary['fit_partition_counts']}")
        print(f"  calibration_partition_counts: {summary['calibration_partition_counts']}")
        print(f"  label_distribution.train    : {summary['label_distribution']['train']}")
        print(f"  label_distribution.validation: {summary['label_distribution']['validation']}")
        print(f"  artifacts                   : {sorted(summary['artifact_paths'].values())}")
        print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
