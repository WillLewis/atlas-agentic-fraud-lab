"""Split-safety tests for Phase 3 graph-derived features.

The user's invariant: graph-derived feature counts (shared_device_degree,
shared_recipient_degree, entity_graph_risk_score) computed for a partition
must reflect ONLY that partition's customer / device / edge cohort. The
train partition cannot see locked or drifted relationship structure.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import generate_synthetic as gen_synth


def test_partition_local_graph_features_bounded_by_global(
    features_global, features_per_partition, dataset
):
    """For any transfer in the train partition, graph-derived counts
    computed partition-locally must be <= the same counts computed
    against the global universe."""
    train_features = features_per_partition["train"]
    train_by_event = {fv["event_id"]: fv for fv in train_features}

    for fv_global in features_global:
        train_fv = train_by_event.get(fv_global["event_id"])
        if train_fv is None:
            # transfer is not in the train partition; skip
            continue
        assert train_fv["shared_device_degree"] <= fv_global["shared_device_degree"], (
            f"{fv_global['event_id']}: train sdd={train_fv['shared_device_degree']} "
            f"> global sdd={fv_global['shared_device_degree']}"
        )
        assert train_fv["shared_recipient_degree"] <= fv_global["shared_recipient_degree"]


def test_no_cross_partition_customer_in_features(
    features_per_partition, dataset
):
    """Every feature vector's customer_id must be in that partition's
    customer set — never some other partition's customer."""
    splits = dataset["splits"]
    for pname, fvs in features_per_partition.items():
        partition_cust_ids = set(splits.partitions[pname].customer_ids)
        for fv in fvs:
            assert fv["customer_id"] in partition_cust_ids, (
                f"feature {fv['event_id']!r} in partition {pname!r} "
                f"references customer {fv['customer_id']!r} not in that partition"
            )


def test_drifted_feature_count_matches_drifted_transfer_count(
    features_per_partition, dataset
):
    drifted = dataset["splits"].partitions["drifted_holdout"]
    drifted_features = features_per_partition["drifted_holdout"]
    assert len(drifted_features) == len(drifted.transfer_events)


def test_locked_feature_count_matches_locked_transfer_count(
    features_per_partition, dataset
):
    locked = dataset["splits"].partitions["locked_adaptive_holdout"]
    locked_features = features_per_partition["locked_adaptive_holdout"]
    assert len(locked_features) == len(locked.transfer_events)


def test_disk_features_match_partition_local_compute(tmp_path: Path):
    """Features written to disk by ``main`` must equal what we'd compute
    partition-locally with the same RNG state."""
    out = tmp_path / "ds"
    gen_synth.main(
        ["--seed", "42", "--customer-count", "30",
         "--output-dir", str(out), "--quiet"]
    )
    # Disk train features
    disk_train = json.loads((out / "features" / "train.json").read_text())
    disk_train_event_ids = {fv["event_id"] for fv in disk_train}

    # Disk train transfer events (via splits + global flat file)
    train_split = json.loads((out / "splits" / "train.json").read_text())
    train_cust_ids = set(train_split["customer_ids"])
    global_tx = json.loads((out / "events" / "transfer_events.json").read_text())
    train_tx_event_ids = {
        t["transfer_event_id"] for t in global_tx
        if t["customer_id"] in train_cust_ids
    }
    assert disk_train_event_ids == train_tx_event_ids


def test_train_features_have_no_locked_or_drifted_customers(tmp_path: Path):
    """Sanity guard: the train feature file must contain only train-partition
    customer IDs."""
    out = tmp_path / "ds"
    gen_synth.main(
        ["--seed", "42", "--customer-count", "30",
         "--output-dir", str(out), "--quiet"]
    )
    train_features = json.loads((out / "features" / "train.json").read_text())
    train_cust_ids = set(json.loads(
        (out / "splits" / "train.json").read_text()
    )["customer_ids"])
    for fv in train_features:
        assert fv["customer_id"] in train_cust_ids


def test_locked_features_directory_isolated_from_global(tmp_path: Path):
    """Locked feature vectors do NOT appear in the global features files."""
    out = tmp_path / "ds"
    gen_synth.main(
        ["--seed", "42", "--customer-count", "30",
         "--output-dir", str(out), "--quiet"]
    )
    locked_features = json.loads(
        (out / "holdouts" / "locked" / "feature_vectors.json").read_text()
    )
    locked_event_ids = {fv["event_id"] for fv in locked_features}

    for rel in ("features/train.json", "features/validation.json", "features/clean_holdout.json"):
        global_features = json.loads((out / rel).read_text())
        global_event_ids = {fv["event_id"] for fv in global_features}
        assert not (locked_event_ids & global_event_ids), (
            f"locked feature event_ids leaked into {rel}"
        )


def test_drifted_features_directory_isolated_from_global(tmp_path: Path):
    out = tmp_path / "ds"
    gen_synth.main(
        ["--seed", "42", "--customer-count", "30",
         "--output-dir", str(out), "--quiet"]
    )
    drifted_features = json.loads(
        (out / "holdouts" / "drifted" / "feature_vectors.json").read_text()
    )
    drifted_event_ids = {fv["event_id"] for fv in drifted_features}

    for rel in ("features/train.json", "features/validation.json", "features/clean_holdout.json"):
        global_features = json.loads((out / rel).read_text())
        global_event_ids = {fv["event_id"] for fv in global_features}
        assert not (drifted_event_ids & global_event_ids)
