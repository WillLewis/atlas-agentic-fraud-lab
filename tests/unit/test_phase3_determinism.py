"""Determinism tests for Phase 3 feature recomputation.

Verifies same-input → same-output at the per-partition level and at the
``scripts.generate_synthetic`` CLI level (byte-identical disk artifacts
across runs at the same seed).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from atlas.synthetic.features import recompute_feature_vectors
from scripts import generate_synthetic as gen_synth


def test_same_input_same_features_global(dataset):
    a = recompute_feature_vectors(
        transfer_events=dataset["transfer_events"],
        customers=dataset["customers"],
        devices=dataset["devices"],
        graph_edges=dataset["graph_edges"],
        login_sessions=dataset["login_sessions"],
        security_events=dataset["security_events"],
    )
    b = recompute_feature_vectors(
        transfer_events=dataset["transfer_events"],
        customers=dataset["customers"],
        devices=dataset["devices"],
        graph_edges=dataset["graph_edges"],
        login_sessions=dataset["login_sessions"],
        security_events=dataset["security_events"],
    )
    assert a == b


def test_same_input_same_features_per_partition(dataset):
    splits = dataset["splits"]
    for p in splits.partitions.values():
        a = recompute_feature_vectors(
            transfer_events=p.transfer_events,
            customers=p.customers,
            devices=p.devices,
            graph_edges=p.graph_edges,
            login_sessions=p.login_sessions,
            security_events=p.security_events,
        )
        b = recompute_feature_vectors(
            transfer_events=p.transfer_events,
            customers=p.customers,
            devices=p.devices,
            graph_edges=p.graph_edges,
            login_sessions=p.login_sessions,
            security_events=p.security_events,
        )
        assert a == b, f"determinism failed for partition {p.name!r}"


def test_partition_call_order_independent(dataset):
    """Calling for partition X then Y produces the same X result as Y-then-X."""
    splits = dataset["splits"]
    train = splits.partitions["train"]
    locked = splits.partitions["locked_adaptive_holdout"]

    train_first = recompute_feature_vectors(
        train.transfer_events, train.customers, train.devices,
        train.graph_edges, train.login_sessions, train.security_events,
    )
    _ = recompute_feature_vectors(
        locked.transfer_events, locked.customers, locked.devices,
        locked.graph_edges, locked.login_sessions, locked.security_events,
    )
    train_after_locked = recompute_feature_vectors(
        train.transfer_events, train.customers, train.devices,
        train.graph_edges, train.login_sessions, train.security_events,
    )
    assert train_first == train_after_locked


@pytest.mark.parametrize("seed", [42, 99, 7])
def test_cli_byte_identical_features_across_runs(tmp_path: Path, seed: int):
    """Two consecutive ``main`` runs at the same seed produce identical
    Phase 3 feature artifacts (3 readable + 2 holdout files)."""
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    gen_synth.main(
        ["--seed", str(seed), "--customer-count", "30",
         "--output-dir", str(out1), "--quiet"]
    )
    gen_synth.main(
        ["--seed", str(seed), "--customer-count", "30",
         "--output-dir", str(out2), "--quiet"]
    )

    feature_paths = [
        "features/train.json",
        "features/validation.json",
        "features/clean_holdout.json",
        "holdouts/locked/feature_vectors.json",
        "holdouts/drifted/feature_vectors.json",
    ]
    for rel in feature_paths:
        h1 = hashlib.sha256((out1 / rel).read_bytes()).hexdigest()
        h2 = hashlib.sha256((out2 / rel).read_bytes()).hexdigest()
        assert h1 == h2, f"{rel} differs between runs at seed={seed}"


def test_manifest_feature_counts_match_files(tmp_path: Path):
    out = tmp_path / "ds"
    gen_synth.main(
        ["--seed", "42", "--customer-count", "30",
         "--output-dir", str(out), "--quiet"]
    )
    manifest = json.loads((out / "manifest.json").read_text())
    counts = manifest["counts"]["feature_vectors_by_partition"]

    for pname, rel in [
        ("train", "features/train.json"),
        ("validation", "features/validation.json"),
        ("clean_holdout", "features/clean_holdout.json"),
        ("locked_adaptive_holdout", "holdouts/locked/feature_vectors.json"),
        ("drifted_holdout", "holdouts/drifted/feature_vectors.json"),
    ]:
        n_records = len(json.loads((out / rel).read_text()))
        assert counts[pname] == n_records, (
            f"manifest.counts.feature_vectors_by_partition[{pname}] = "
            f"{counts[pname]} but file has {n_records} records"
        )
