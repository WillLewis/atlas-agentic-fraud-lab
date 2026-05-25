#!/usr/bin/env python3
"""Phase 2 dataset generator for Project Atlas.

Pipeline (single seeded RNG, threaded through every step):

    customers → accounts → devices → recipients → external_accounts →
    graph_edges → login_sessions → security_events → transfer_events →
    label_generation → splits + drift

Output layout under ``--output-dir`` (default ``data/synthetic/``):

    manifest.json                                  ← counts + file paths

    entities/
        customers.json, accounts.json, devices.json, external_accounts.json,
        recipients.json                            ← shared; ALL recipients
    events/
        login_sessions.json, security_events.json, transfer_events.json
    graph/
        graph_edges.json
    labels/
        label_generation.json

    splits/
        train.json, validation.json, clean_holdout.json   ← customer_id lists
        customers_split_membership.json                   ← customer→partition map

    holdouts/
        locked/                                    ← .claude/settings.json deny
            customers.json, accounts.json, devices.json, external_accounts.json,
            graph_edges.json, login_sessions.json, security_events.json,
            transfer_events.json, labels.json
        drifted/
            customers.json, accounts.json, devices.json, external_accounts.json,
            graph_edges.json, login_sessions.json, security_events.json,
            transfer_events.json
            labels/                                ← .claude/settings.json deny
                labels.json

Locked-partition isolation contract: train/validation/clean_holdout records
appear in the GLOBAL files (entities/, events/, etc.). The locked_adaptive_
holdout and drifted_holdout records are written only into the corresponding
``holdouts/*/`` subtree — they are never duplicated into the global tables.
This matches ``.claude/settings.json:8-9`` read-deny rules.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Bootstrap src/ onto sys.path so the script runs without an editable
# install. Phase 4+ may package an entry point in pyproject.toml.
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import yaml  # noqa: E402  (post sys.path bootstrap)

from atlas.synthetic.accounts import generate_accounts  # noqa: E402
from atlas.synthetic.customers import generate_customers  # noqa: E402
from atlas.synthetic.devices import generate_devices  # noqa: E402
from atlas.synthetic.events import (  # noqa: E402
    REFERENCE_NOW,
    generate_login_sessions,
    generate_security_events,
    generate_transfer_events,
)
from atlas.synthetic.features import (  # noqa: E402
    FeatureVector,
    recompute_feature_vectors,
)
from atlas.synthetic.graph import generate_graph_edges  # noqa: E402
from atlas.synthetic.labels import generate_label_generation_records  # noqa: E402
from atlas.synthetic.recipients import (  # noqa: E402
    generate_external_accounts,
    generate_recipients,
)
from atlas.synthetic.splits import (  # noqa: E402
    PARTITION_NAMES,
    SplitsResult,
    assert_no_customer_leak,
    build_splits,
)

# ---------------------------------------------------------------------------
# CLI defaults
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "synthetic"
DEFAULT_CUSTOMER_COUNT = 600
DEMO_CONFIG_PATH = REPO_ROOT / "config" / "demo.yaml"

# Partitions whose data flows into the global flat files.
GLOBAL_PARTITION_NAMES: tuple[str, ...] = ("train", "validation", "clean_holdout")

# Generated subdirs that ``--clean`` removes before writing.
GENERATED_SUBDIRS: tuple[str, ...] = (
    "entities",
    "events",
    "graph",
    "labels",
    "splits",
    "holdouts",
    "features",
)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="generate_synthetic",
        description=(
            "Generate the Phase 2 synthetic dataset under data/synthetic/. "
            "Deterministic given (seed, customer_count): same inputs produce "
            "byte-identical JSON."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Integer seed. Defaults to reproducibility.default_seed in config/demo.yaml.",
    )
    parser.add_argument(
        "--customer-count",
        type=int,
        default=DEFAULT_CUSTOMER_COUNT,
        help=f"Number of synthetic customers to generate (default: {DEFAULT_CUSTOMER_COUNT}, min: 10).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write the dataset into (default: data/synthetic/).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output.",
    )
    return parser.parse_args(argv)


def load_default_seed() -> int:
    """Read ``reproducibility.default_seed`` from ``config/demo.yaml``."""
    if not DEMO_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"config/demo.yaml not found at {DEMO_CONFIG_PATH}; pass --seed explicitly"
        )
    with DEMO_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    repro = cfg.get("reproducibility")
    if not isinstance(repro, dict) or "default_seed" not in repro:
        raise ValueError(
            "config/demo.yaml is missing reproducibility.default_seed"
        )
    return int(repro["default_seed"])


# ---------------------------------------------------------------------------
# Generation pipeline
# ---------------------------------------------------------------------------


def run_pipeline(seed: int, customer_count: int) -> tuple[SplitsResult, list]:
    """Run the full generation pipeline. Returns ``(SplitsResult, recipients)``.

    Recipients are returned separately because they are a shared pool
    (no customer binding) and are written once globally.
    """
    rng = random.Random(seed)
    customers = generate_customers(rng, customer_count, seed)
    accounts = generate_accounts(rng, customers)
    devices = generate_devices(rng, customers)
    recipients = generate_recipients(rng, customer_count)
    external_accounts = generate_external_accounts(rng, customers)
    graph_edges = generate_graph_edges(rng, customers, devices, recipients)
    login_sessions = generate_login_sessions(rng, customers, devices)
    security_events = generate_security_events(rng, customers, login_sessions)
    transfer_events = generate_transfer_events(
        rng, customers, accounts, devices, graph_edges
    )
    label_records = generate_label_generation_records(
        rng, transfer_events, customers, devices, recipients, security_events
    )
    splits = build_splits(
        rng,
        customers,
        accounts,
        devices,
        recipients,
        external_accounts,
        graph_edges,
        login_sessions,
        security_events,
        transfer_events,
        label_records,
    )
    assert_no_customer_leak(splits)
    return splits, recipients


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def write_json(path: Path, obj: Any) -> None:
    """Write ``obj`` as pretty-printed JSON. Trailing newline for clean diffs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def clean_generated_subdirs(output_dir: Path) -> None:
    """Remove the known generated subdirs and ``manifest.json``.

    Preserves ``.gitkeep`` and any files outside the generated layout. This
    makes ``make seed`` idempotent without touching unrelated user state.
    """
    for sub in GENERATED_SUBDIRS:
        target = output_dir / sub
        if target.exists():
            shutil.rmtree(target)
    manifest = output_dir / "manifest.json"
    if manifest.exists():
        manifest.unlink()


def collect_global_records(splits: SplitsResult) -> dict[str, list]:
    """Concatenate train + validation + clean_holdout records into 'global' lists."""
    out: dict[str, list] = {
        "customers": [],
        "accounts": [],
        "devices": [],
        "external_accounts": [],
        "graph_edges": [],
        "login_sessions": [],
        "security_events": [],
        "transfer_events": [],
        "label_records": [],
    }
    for pname in GLOBAL_PARTITION_NAMES:
        p = splits.partitions[pname]
        out["customers"].extend(p.customers)
        out["accounts"].extend(p.accounts)
        out["devices"].extend(p.devices)
        out["external_accounts"].extend(p.external_accounts)
        out["graph_edges"].extend(p.graph_edges)
        out["login_sessions"].extend(p.login_sessions)
        out["security_events"].extend(p.security_events)
        out["transfer_events"].extend(p.transfer_events)
        out["label_records"].extend(p.label_records)
    return out


def compute_features_per_partition(
    splits: SplitsResult,
) -> dict[str, list[FeatureVector]]:
    """For each partition, recompute features using ONLY that partition's
    customer / device / edge / event view.

    This is the split-safe calling pattern from the Phase 3 plan: graph-
    derived feature counts (``shared_device_degree``,
    ``shared_recipient_degree``) reflect partition-local cohorts, so a
    train-partition feature vector cannot leak relationship information
    from the locked or drifted holdouts.
    """
    out: dict[str, list[FeatureVector]] = {}
    for pname, p in splits.partitions.items():
        out[pname] = recompute_feature_vectors(
            transfer_events=p.transfer_events,
            customers=p.customers,
            devices=p.devices,
            graph_edges=p.graph_edges,
            login_sessions=p.login_sessions,
            security_events=p.security_events,
        )
    return out


def persist_dataset(
    output_dir: Path,
    splits: SplitsResult,
    recipients: list,
    seed: int,
    customer_count: int,
) -> None:
    """Write all per-table JSON files + manifest under ``output_dir``."""
    clean_generated_subdirs(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    g = collect_global_records(splits)
    features_by_partition = compute_features_per_partition(splits)

    # --- Global entity tables (train + val + clean only) ---
    write_json(output_dir / "entities" / "customers.json", g["customers"])
    write_json(output_dir / "entities" / "accounts.json", g["accounts"])
    write_json(output_dir / "entities" / "devices.json", g["devices"])
    write_json(output_dir / "entities" / "external_accounts.json", g["external_accounts"])
    # Recipients are a shared pool — full list goes to the global file.
    write_json(output_dir / "entities" / "recipients.json", recipients)

    # --- Global event tables ---
    write_json(output_dir / "events" / "login_sessions.json", g["login_sessions"])
    write_json(output_dir / "events" / "security_events.json", g["security_events"])
    write_json(output_dir / "events" / "transfer_events.json", g["transfer_events"])

    # --- Global graph + labels ---
    write_json(output_dir / "graph" / "graph_edges.json", g["graph_edges"])
    write_json(output_dir / "labels" / "label_generation.json", g["label_records"])

    # --- Splits manifests (customer_id lists, no record data) ---
    for pname in GLOBAL_PARTITION_NAMES:
        p = splits.partitions[pname]
        write_json(
            output_dir / "splits" / f"{pname}.json",
            {
                "partition": pname,
                "customer_count": len(p.customer_ids),
                "customer_ids": list(p.customer_ids),
            },
        )
    write_json(
        output_dir / "splits" / "customers_split_membership.json",
        {
            "schema_version": 1,
            "customers_split_membership": dict(splits.customer_split_membership),
        },
    )

    # --- Per-partition Phase 3 feature artifacts ---
    # train + validation + clean_holdout features go into the global-readable
    # features/ subdir. Locked + drifted feature artifacts are written into
    # their respective holdouts/ subtree below so the same .claude/settings.json
    # deny rules continue to apply.
    for pname in GLOBAL_PARTITION_NAMES:
        write_json(
            output_dir / "features" / f"{pname}.json",
            features_by_partition[pname],
        )

    # --- Locked adaptive holdout (full data, isolated from global) ---
    locked = splits.partitions["locked_adaptive_holdout"]
    locked_dir = output_dir / "holdouts" / "locked"
    write_json(locked_dir / "customers.json", locked.customers)
    write_json(locked_dir / "accounts.json", locked.accounts)
    write_json(locked_dir / "devices.json", locked.devices)
    write_json(locked_dir / "external_accounts.json", locked.external_accounts)
    write_json(locked_dir / "graph_edges.json", locked.graph_edges)
    write_json(locked_dir / "login_sessions.json", locked.login_sessions)
    write_json(locked_dir / "security_events.json", locked.security_events)
    write_json(locked_dir / "transfer_events.json", locked.transfer_events)
    write_json(locked_dir / "labels.json", locked.label_records)
    # Phase 3: locked-partition feature artifact lives alongside the locked
    # entities/events. Same deny gate as the rest of holdouts/locked/.
    write_json(
        locked_dir / "feature_vectors.json",
        features_by_partition["locked_adaptive_holdout"],
    )

    # --- Drifted holdout (drift applied; labels in subdir per deny rule) ---
    drifted = splits.partitions["drifted_holdout"]
    drifted_dir = output_dir / "holdouts" / "drifted"
    write_json(drifted_dir / "customers.json", drifted.customers)
    write_json(drifted_dir / "accounts.json", drifted.accounts)
    write_json(drifted_dir / "devices.json", drifted.devices)
    write_json(drifted_dir / "external_accounts.json", drifted.external_accounts)
    write_json(drifted_dir / "graph_edges.json", drifted.graph_edges)
    write_json(drifted_dir / "login_sessions.json", drifted.login_sessions)
    write_json(drifted_dir / "security_events.json", drifted.security_events)
    write_json(drifted_dir / "transfer_events.json", drifted.transfer_events)
    # Drifted labels go to a separate `labels/` subdir matching
    # .claude/settings.json:9 read-deny.
    write_json(drifted_dir / "labels" / "labels.json", drifted.label_records)
    # Phase 3: drifted-partition feature vectors are computed from the
    # drifted (post-drift) events. Lives alongside the drifted entities,
    # NOT under labels/ — features are not labels.
    write_json(
        drifted_dir / "feature_vectors.json",
        features_by_partition["drifted_holdout"],
    )

    # --- Manifest ---
    manifest = build_manifest(
        splits,
        recipients,
        seed,
        customer_count,
        output_dir,
        features_by_partition,
    )
    write_json(output_dir / "manifest.json", manifest)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _rel(path: Path, base: Path) -> str:
    """Render ``path`` relative to ``base`` for portable manifests.

    Paths in ``manifest.json`` are relative to the manifest's own
    directory (i.e. the ``--output-dir``), so a consumer can resolve any
    file from the manifest by joining its location with the listed
    relative path.
    """
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def _label_distribution(records: list) -> dict[str, int]:
    return dict(Counter(r["synthetic_truth_label"] for r in records))


def build_manifest(
    splits: SplitsResult,
    recipients: list,
    seed: int,
    customer_count: int,
    output_dir: Path,
    features_by_partition: dict[str, list[FeatureVector]],
) -> dict[str, Any]:
    g = collect_global_records(splits)

    locked_dir = output_dir / "holdouts" / "locked"
    drifted_dir = output_dir / "holdouts" / "drifted"

    return {
        "schema_version": 2,
        "manifest_label": "atlas_synthetic_dataset_v3",
        "seed": seed,
        "customer_count": customer_count,
        "reference_now_utc": REFERENCE_NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "split_fractions": {
            pname: getattr(splits.fractions, pname) for pname in PARTITION_NAMES
        },
        "counts": {
            "global": {
                "customers": len(g["customers"]),
                "accounts": len(g["accounts"]),
                "devices": len(g["devices"]),
                "recipients_pool_total": len(recipients),
                "external_accounts": len(g["external_accounts"]),
                "graph_edges": len(g["graph_edges"]),
                "login_sessions": len(g["login_sessions"]),
                "security_events": len(g["security_events"]),
                "transfer_events": len(g["transfer_events"]),
                "label_records": len(g["label_records"]),
            },
            "by_partition": {
                pname: len(p.customer_ids)
                for pname, p in splits.partitions.items()
            },
            "feature_vectors_by_partition": {
                pname: len(fvs) for pname, fvs in features_by_partition.items()
            },
        },
        "label_distribution": {
            "global_train_val_clean": _label_distribution(g["label_records"]),
            "locked_adaptive_holdout": _label_distribution(
                splits.partitions["locked_adaptive_holdout"].label_records
            ),
            "drifted_holdout": _label_distribution(
                splits.partitions["drifted_holdout"].label_records
            ),
        },
        "files": {
            "entities": {
                "customers": _rel(output_dir / "entities" / "customers.json", output_dir),
                "accounts": _rel(output_dir / "entities" / "accounts.json", output_dir),
                "devices": _rel(output_dir / "entities" / "devices.json", output_dir),
                "recipients": _rel(output_dir / "entities" / "recipients.json", output_dir),
                "external_accounts": _rel(
                    output_dir / "entities" / "external_accounts.json", output_dir
                ),
            },
            "events": {
                "login_sessions": _rel(output_dir / "events" / "login_sessions.json", output_dir),
                "security_events": _rel(output_dir / "events" / "security_events.json", output_dir),
                "transfer_events": _rel(output_dir / "events" / "transfer_events.json", output_dir),
            },
            "graph": {
                "graph_edges": _rel(output_dir / "graph" / "graph_edges.json", output_dir),
            },
            "labels": {
                "label_generation": _rel(output_dir / "labels" / "label_generation.json", output_dir),
            },
            "features": {
                "train": _rel(output_dir / "features" / "train.json", output_dir),
                "validation": _rel(output_dir / "features" / "validation.json", output_dir),
                "clean_holdout": _rel(
                    output_dir / "features" / "clean_holdout.json", output_dir
                ),
            },
            "splits": {
                "train": _rel(output_dir / "splits" / "train.json", output_dir),
                "validation": _rel(output_dir / "splits" / "validation.json", output_dir),
                "clean_holdout": _rel(output_dir / "splits" / "clean_holdout.json", output_dir),
                "customers_split_membership": _rel(
                    output_dir / "splits" / "customers_split_membership.json", output_dir
                ),
            },
            "holdouts": {
                "locked_adaptive_holdout": {
                    "customers": _rel(locked_dir / "customers.json", output_dir),
                    "accounts": _rel(locked_dir / "accounts.json", output_dir),
                    "devices": _rel(locked_dir / "devices.json", output_dir),
                    "external_accounts": _rel(locked_dir / "external_accounts.json", output_dir),
                    "graph_edges": _rel(locked_dir / "graph_edges.json", output_dir),
                    "login_sessions": _rel(locked_dir / "login_sessions.json", output_dir),
                    "security_events": _rel(locked_dir / "security_events.json", output_dir),
                    "transfer_events": _rel(locked_dir / "transfer_events.json", output_dir),
                    "labels": _rel(locked_dir / "labels.json", output_dir),
                    "feature_vectors": _rel(locked_dir / "feature_vectors.json", output_dir),
                },
                "drifted_holdout": {
                    "customers": _rel(drifted_dir / "customers.json", output_dir),
                    "accounts": _rel(drifted_dir / "accounts.json", output_dir),
                    "devices": _rel(drifted_dir / "devices.json", output_dir),
                    "external_accounts": _rel(drifted_dir / "external_accounts.json", output_dir),
                    "graph_edges": _rel(drifted_dir / "graph_edges.json", output_dir),
                    "login_sessions": _rel(drifted_dir / "login_sessions.json", output_dir),
                    "security_events": _rel(drifted_dir / "security_events.json", output_dir),
                    "transfer_events": _rel(drifted_dir / "transfer_events.json", output_dir),
                    "labels": _rel(drifted_dir / "labels" / "labels.json", output_dir),
                    "feature_vectors": _rel(drifted_dir / "feature_vectors.json", output_dir),
                    "drift_applied": True,
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    seed = args.seed if args.seed is not None else load_default_seed()
    customer_count = args.customer_count
    output_dir = Path(args.output_dir).resolve()
    quiet: bool = args.quiet

    if not quiet:
        print(f"atlas synthetic generator")
        print(f"  seed           : {seed}")
        print(f"  customer_count : {customer_count}")
        print(f"  output_dir     : {output_dir}")

    splits, recipients = run_pipeline(seed=seed, customer_count=customer_count)
    persist_dataset(
        output_dir=output_dir,
        splits=splits,
        recipients=recipients,
        seed=seed,
        customer_count=customer_count,
    )

    if not quiet:
        manifest_path = output_dir / "manifest.json"
        sizes = {
            pname: len(p.customer_ids) for pname, p in splits.partitions.items()
        }
        print(f"  partition sizes: {sizes}")
        print(f"  manifest       : {manifest_path}")
        print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
