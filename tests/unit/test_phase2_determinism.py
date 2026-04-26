"""Determinism tests for Phase 2.

Verifies that the synthetic-data pipeline is byte-deterministic given
``(seed, customer_count)`` — same inputs produce identical record lists
and identical on-disk JSON files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import generate_synthetic as gen_synth


def test_same_seed_same_records(build_dataset):
    a = build_dataset(42, 30)
    b = build_dataset(42, 30)
    for key in (
        "customers",
        "accounts",
        "devices",
        "recipients",
        "external_accounts",
        "graph_edges",
        "login_sessions",
        "security_events",
        "transfer_events",
        "label_records",
    ):
        assert a[key] == b[key], f"{key} differs between two same-seed builds"


def test_different_seeds_different_records(dataset, dataset_alt_seed):
    # Customer IDs are positional (cust_000001..cust_000060) so they match
    # by construction; what should differ are the random-derived fields.
    a_segments = [c["customer_segment"] for c in dataset["customers"]]
    b_segments = [c["customer_segment"] for c in dataset_alt_seed["customers"]]
    assert a_segments != b_segments, "different seed must produce different segments"

    a_tx_ids = {t["transfer_event_id"] for t in dataset["transfer_events"]}
    b_tx_ids = {t["transfer_event_id"] for t in dataset_alt_seed["transfer_events"]}
    # Counts differ because transfer_freq is a random draw per customer.
    assert a_tx_ids != b_tx_ids


def test_different_counts_scale_correctly(build_dataset):
    small = build_dataset(42, 30)
    large = build_dataset(42, 90)
    assert len(small["customers"]) == 30
    assert len(large["customers"]) == 90
    # With 3x more customers, account count scales 1:1 (1:1 link).
    assert len(small["accounts"]) == 30
    assert len(large["accounts"]) == 90


@pytest.mark.parametrize("seed", [42, 99, 7, 1024])
def test_main_produces_byte_identical_dataset_across_runs(tmp_path: Path, seed: int):
    """Two consecutive ``main`` invocations at the same seed produce
    SHA-256-identical files for every JSON file in the output."""
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    gen_synth.main(
        ["--seed", str(seed), "--customer-count", "40",
         "--output-dir", str(out1), "--quiet"]
    )
    gen_synth.main(
        ["--seed", str(seed), "--customer-count", "40",
         "--output-dir", str(out2), "--quiet"]
    )

    files1 = sorted(p.relative_to(out1) for p in out1.rglob("*.json"))
    files2 = sorted(p.relative_to(out2) for p in out2.rglob("*.json"))
    assert files1 == files2, f"file lists differ between runs at seed={seed}"

    for rel in files1:
        h1 = hashlib.sha256((out1 / rel).read_bytes()).hexdigest()
        h2 = hashlib.sha256((out2 / rel).read_bytes()).hexdigest()
        assert h1 == h2, f"{rel} differs between runs at seed={seed}"


def test_manifest_paths_relative_to_output_dir(tmp_path: Path):
    out = tmp_path / "ds"
    gen_synth.main(
        ["--seed", "42", "--customer-count", "30",
         "--output-dir", str(out), "--quiet"]
    )
    manifest = json.loads((out / "manifest.json").read_text())

    # Every path in `files` must be relative (not start with `/`) and
    # must resolve to a real file when joined with output_dir.
    def walk(node, path=""):
        if isinstance(node, str):
            assert not node.startswith("/"), f"manifest path is absolute: {node}"
            assert (out / node).exists(), f"manifest path does not resolve: {node}"
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(manifest["files"])


def test_manifest_seed_and_count_recorded(tmp_path: Path):
    out = tmp_path / "ds"
    gen_synth.main(
        ["--seed", "1234", "--customer-count", "50",
         "--output-dir", str(out), "--quiet"]
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["seed"] == 1234
    assert manifest["customer_count"] == 50
    assert manifest["counts"]["by_partition"] == {
        "train": 30,
        "validation": 5,
        "clean_holdout": 5,
        "locked_adaptive_holdout": 5,
        "drifted_holdout": 5,
    }
