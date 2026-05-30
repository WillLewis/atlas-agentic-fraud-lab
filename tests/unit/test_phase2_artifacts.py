"""On-disk artifact tests for Phase 2.

Verifies that ``scripts.generate_synthetic.main`` writes the expected
file layout under ``--output-dir`` and that locked / drifted holdout
records appear ONLY in their respective ``holdouts/*/`` subtrees.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import generate_synthetic as gen_synth

EXPECTED_FILES = {
    "manifest.json",
    "entities/customers.json",
    "entities/accounts.json",
    "entities/devices.json",
    "entities/recipients.json",
    "entities/external_accounts.json",
    "events/login_sessions.json",
    "events/security_events.json",
    "events/transfer_events.json",
    "graph/graph_edges.json",
    "labels/label_generation.json",
    # Phase 3 — per-partition feature artifacts.
    "features/train.json",
    "features/validation.json",
    "features/clean_holdout.json",
    "splits/train.json",
    "splits/validation.json",
    "splits/clean_holdout.json",
    "splits/customers_split_membership.json",
    "holdouts/locked/customers.json",
    "holdouts/locked/accounts.json",
    "holdouts/locked/devices.json",
    "holdouts/locked/external_accounts.json",
    "holdouts/locked/graph_edges.json",
    "holdouts/locked/login_sessions.json",
    "holdouts/locked/security_events.json",
    "holdouts/locked/transfer_events.json",
    "holdouts/locked/labels.json",
    "holdouts/locked/feature_vectors.json",
    "holdouts/drifted/customers.json",
    "holdouts/drifted/accounts.json",
    "holdouts/drifted/devices.json",
    "holdouts/drifted/external_accounts.json",
    "holdouts/drifted/graph_edges.json",
    "holdouts/drifted/login_sessions.json",
    "holdouts/drifted/security_events.json",
    "holdouts/drifted/transfer_events.json",
    "holdouts/drifted/labels/labels.json",
    "holdouts/drifted/feature_vectors.json",
}


@pytest.fixture(scope="module")
def disk_dataset(tmp_path_factory) -> Path:
    """Run ``main`` once and return the output directory."""
    out = tmp_path_factory.mktemp("ds")
    gen_synth.main(
        ["--seed", "42", "--customer-count", "60",
         "--output-dir", str(out), "--quiet"]
    )
    return out


def _all_relative_files(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*.json")}


def test_expected_layout_present(disk_dataset: Path):
    actual = _all_relative_files(disk_dataset)
    assert actual == EXPECTED_FILES, (
        f"layout mismatch:\n"
        f"  missing: {sorted(EXPECTED_FILES - actual)}\n"
        f"  extra  : {sorted(actual - EXPECTED_FILES)}"
    )


def test_locked_holdout_directory_isolated(disk_dataset: Path):
    """Locked holdout customer IDs do NOT appear in any global flat file."""
    locked_customers = json.loads(
        (disk_dataset / "holdouts" / "locked" / "customers.json").read_text()
    )
    locked_ids = {c["customer_id"] for c in locked_customers}

    global_customers = json.loads(
        (disk_dataset / "entities" / "customers.json").read_text()
    )
    global_ids = {c["customer_id"] for c in global_customers}

    assert not (locked_ids & global_ids), "locked customers leaked into global"


def test_drifted_holdout_directory_isolated(disk_dataset: Path):
    """Drifted holdout customer IDs do NOT appear in any global flat file."""
    drifted_customers = json.loads(
        (disk_dataset / "holdouts" / "drifted" / "customers.json").read_text()
    )
    drifted_ids = {c["customer_id"] for c in drifted_customers}

    global_customers = json.loads(
        (disk_dataset / "entities" / "customers.json").read_text()
    )
    global_ids = {c["customer_id"] for c in global_customers}

    assert not (drifted_ids & global_ids), "drifted customers leaked into global"


def test_locked_labels_not_in_global_labels(disk_dataset: Path):
    locked_labels = json.loads(
        (disk_dataset / "holdouts" / "locked" / "labels.json").read_text()
    )
    locked_label_event_ids = {l["event_id"] for l in locked_labels}

    global_labels = json.loads(
        (disk_dataset / "labels" / "label_generation.json").read_text()
    )
    global_label_event_ids = {l["event_id"] for l in global_labels}

    assert not (locked_label_event_ids & global_label_event_ids)


def test_drifted_labels_in_subdir_not_global(disk_dataset: Path):
    """Drifted labels live ONLY at holdouts/drifted/labels/labels.json."""
    drifted_labels_path = disk_dataset / "holdouts" / "drifted" / "labels" / "labels.json"
    assert drifted_labels_path.exists(), "drifted labels file missing"

    drifted_labels = json.loads(drifted_labels_path.read_text())
    drifted_event_ids = {l["event_id"] for l in drifted_labels}

    global_labels = json.loads(
        (disk_dataset / "labels" / "label_generation.json").read_text()
    )
    global_event_ids = {l["event_id"] for l in global_labels}

    assert not (drifted_event_ids & global_event_ids)


def test_membership_map_covers_all_customers(disk_dataset: Path):
    membership_doc = json.loads(
        (disk_dataset / "splits" / "customers_split_membership.json").read_text()
    )
    membership = membership_doc["customers_split_membership"]
    assert len(membership) == 60

    # Every customer ID across all 5 partitions appears exactly once
    locked = {c["customer_id"] for c in json.loads(
        (disk_dataset / "holdouts" / "locked" / "customers.json").read_text())}
    drifted = {c["customer_id"] for c in json.loads(
        (disk_dataset / "holdouts" / "drifted" / "customers.json").read_text())}
    train = set(json.loads((disk_dataset / "splits" / "train.json").read_text())["customer_ids"])
    val = set(json.loads((disk_dataset / "splits" / "validation.json").read_text())["customer_ids"])
    clean = set(json.loads((disk_dataset / "splits" / "clean_holdout.json").read_text())["customer_ids"])

    all_partitioned = locked | drifted | train | val | clean
    assert all_partitioned == set(membership.keys())


def test_manifest_counts_match_files(disk_dataset: Path):
    manifest = json.loads((disk_dataset / "manifest.json").read_text())
    counts = manifest["counts"]["global"]

    actual_customers = len(json.loads(
        (disk_dataset / "entities" / "customers.json").read_text()))
    assert counts["customers"] == actual_customers

    actual_tx = len(json.loads(
        (disk_dataset / "events" / "transfer_events.json").read_text()))
    assert counts["transfer_events"] == actual_tx

    actual_labels = len(json.loads(
        (disk_dataset / "labels" / "label_generation.json").read_text()))
    assert counts["label_records"] == actual_labels


def test_locked_partition_count_in_manifest(disk_dataset: Path):
    manifest = json.loads((disk_dataset / "manifest.json").read_text())
    assert manifest["counts"]["by_partition"] == {
        "train": 15,
        "validation": 6,
        "clean_holdout": 15,
        "locked_adaptive_holdout": 12,
        "drifted_holdout": 12,
    }


def test_make_seed_idempotent(tmp_path: Path):
    """Running main twice into the same output dir does not duplicate files."""
    out = tmp_path / "ds"
    gen_synth.main(["--seed", "42", "--customer-count", "30",
                    "--output-dir", str(out), "--quiet"])
    files_after_first = _all_relative_files(out)

    gen_synth.main(["--seed", "42", "--customer-count", "30",
                    "--output-dir", str(out), "--quiet"])
    files_after_second = _all_relative_files(out)

    assert files_after_first == files_after_second
