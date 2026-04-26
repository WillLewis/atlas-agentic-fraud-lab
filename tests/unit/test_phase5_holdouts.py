"""Phase 5 holdout-loader tests.

Reads real persisted holdouts (``make seed`` artifacts), confirms each
``JudgeEvalRecord`` has the expected shape, exercises every edge case
on ``found_adaptive_set``, and verifies the cross-checks fire on
misaligned features / labels / transfer events.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.judge.holdouts import (
    HOLDOUT_NAMES,
    JudgeEvalRecord,
    load_eval_set,
)
from atlas.judge.metrics import AMOUNT_BUCKET_TO_SYNTHETIC_LOSS

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# HOLDOUT_NAMES
# ---------------------------------------------------------------------------


def test_holdout_names_canonical():
    assert HOLDOUT_NAMES == (
        "clean_holdout",
        "found_adaptive_set",
        "locked_adaptive_holdout",
        "drifted_holdout",
    )


# ---------------------------------------------------------------------------
# Each persisted set loads + records have JudgeEvalRecord shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["clean_holdout", "locked_adaptive_holdout", "drifted_holdout"],
)
def test_load_each_persisted_eval_set(name):
    records = load_eval_set(name)
    assert len(records) > 0, f"{name} loaded empty"
    sample = records[0]
    # Required JudgeEvalRecord keys
    expected_keys = {
        "event_id", "customer_id", "feature_vector",
        "synthetic_truth_label", "binary_label", "amount_bucket",
    }
    assert set(sample) == expected_keys
    # Type sanity
    for r in records:
        assert isinstance(r["event_id"], str) and r["event_id"].startswith("tx_")
        assert r["binary_label"] in (0, 1)
        assert r["amount_bucket"] in AMOUNT_BUCKET_TO_SYNTHETIC_LOSS
        assert r["synthetic_truth_label"] in {
            "normal_activity", "high_risk_synthetic_activity"
        }


def test_locked_holdout_actually_reads_locked_dir():
    """Sanity: the count from the loader matches the count of records on
    disk. Confirms that runtime Python file I/O works through the
    ``.claude/settings.json`` Read-tool deny rule.
    """
    locked_features_path = (
        REPO_ROOT / "data" / "synthetic" / "holdouts" / "locked"
        / "feature_vectors.json"
    )
    if not locked_features_path.exists():
        pytest.skip("locked feature_vectors.json not present")
    with locked_features_path.open() as fh:
        on_disk_count = len(json.load(fh))
    loaded = load_eval_set("locked_adaptive_holdout")
    assert len(loaded) == on_disk_count


def test_drifted_holdout_actually_reads_drifted_dir():
    drifted_features_path = (
        REPO_ROOT / "data" / "synthetic" / "holdouts" / "drifted"
        / "feature_vectors.json"
    )
    if not drifted_features_path.exists():
        pytest.skip("drifted feature_vectors.json not present")
    with drifted_features_path.open() as fh:
        on_disk_count = len(json.load(fh))
    loaded = load_eval_set("drifted_holdout")
    assert len(loaded) == on_disk_count


# ---------------------------------------------------------------------------
# found_adaptive_set
# ---------------------------------------------------------------------------


def test_found_adaptive_set_with_valid_ids():
    clean = load_eval_set("clean_holdout")
    ids = [r["event_id"] for r in clean[:3]]
    fas = load_eval_set("found_adaptive_set", found_adaptive_set_event_ids=ids)
    assert [r["event_id"] for r in fas] == ids  # order preserved
    assert len(fas) == 3


def test_found_adaptive_set_requires_ids():
    with pytest.raises(ValueError, match="non-empty"):
        load_eval_set("found_adaptive_set")
    with pytest.raises(ValueError, match="non-empty"):
        load_eval_set("found_adaptive_set", found_adaptive_set_event_ids=[])


def test_found_adaptive_set_rejects_duplicates():
    clean = load_eval_set("clean_holdout")
    eid = clean[0]["event_id"]
    with pytest.raises(ValueError, match="duplicates"):
        load_eval_set(
            "found_adaptive_set",
            found_adaptive_set_event_ids=[eid, eid],
        )


def test_found_adaptive_set_rejects_unknown_ids():
    with pytest.raises(ValueError, match="not in the readable global"):
        load_eval_set(
            "found_adaptive_set",
            found_adaptive_set_event_ids=["tx_does_not_exist"],
        )


def test_found_adaptive_set_rejects_locked_only_ids():
    """A locked-only event_id is NOT in the readable global feature
    artifact — must be rejected. Guards against agents getting
    locked-holdout ground-truth via this back-door.
    """
    locked = load_eval_set("locked_adaptive_holdout")
    locked_id = locked[0]["event_id"]
    with pytest.raises(ValueError, match="not in the readable global"):
        load_eval_set(
            "found_adaptive_set",
            found_adaptive_set_event_ids=[locked_id],
        )


# ---------------------------------------------------------------------------
# Unknown name
# ---------------------------------------------------------------------------


def test_unknown_eval_set_name_raises():
    with pytest.raises(ValueError, match="unknown eval set"):
        load_eval_set("not_a_real_set")


# ---------------------------------------------------------------------------
# Misalignment cross-checks
# ---------------------------------------------------------------------------


def _write(p: Path, doc):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc))


def test_misaligned_features_to_labels_raises(tmp_path):
    """If a feature has no matching label, the loader must raise."""
    data_dir = tmp_path / "synthetic"

    feat = {
        "event_id": "tx_aaa", "customer_id": "cust_aaa",
        "login_count_72h": 0, "login_count_30d": 0, "login_velocity_ratio": 0.0,
        "challenge_count_72h": 0, "challenge_pass_ratio_30d": 0.0,
        "password_recovery_count_72h": 0,
        "device_count_72h": 1, "current_device_tenure_days": 100,
        "geo_consistency_flag": 1, "transfer_count_72h": 0,
        "recipient_tenure_days": 100,
        "shared_device_degree": 0, "shared_recipient_degree": 0,
        "entity_graph_risk_score": 0.0, "cash_movement_velocity_score": 0.0,
    }
    _write(data_dir / "features" / "clean_holdout.json", [feat])
    # Label points at a DIFFERENT event
    _write(
        data_dir / "labels" / "label_generation.json",
        [{
            "event_id": "tx_bbb", "latent_drivers": {},
            "synthetic_risk_probability": 0.0,
            "synthetic_truth_label": "normal_activity",
        }],
    )
    # Transfer event has the right id (so we isolate the label-misalignment)
    _write(
        data_dir / "events" / "transfer_events.json",
        [{"transfer_event_id": "tx_aaa", "amount_bucket": "amount_bucket_03"}],
    )
    with pytest.raises(ValueError, match="no matching label record"):
        load_eval_set("clean_holdout", data_dir=data_dir)


def test_misaligned_features_to_transfers_raises(tmp_path):
    """If a feature has no matching transfer event, the loader must
    raise (judge needs amount_bucket for synthetic_loss_allowed)."""
    data_dir = tmp_path / "synthetic"

    feat = {
        "event_id": "tx_aaa", "customer_id": "cust_aaa",
        "login_count_72h": 0, "login_count_30d": 0, "login_velocity_ratio": 0.0,
        "challenge_count_72h": 0, "challenge_pass_ratio_30d": 0.0,
        "password_recovery_count_72h": 0,
        "device_count_72h": 1, "current_device_tenure_days": 100,
        "geo_consistency_flag": 1, "transfer_count_72h": 0,
        "recipient_tenure_days": 100,
        "shared_device_degree": 0, "shared_recipient_degree": 0,
        "entity_graph_risk_score": 0.0, "cash_movement_velocity_score": 0.0,
    }
    _write(data_dir / "features" / "clean_holdout.json", [feat])
    _write(
        data_dir / "labels" / "label_generation.json",
        [{
            "event_id": "tx_aaa", "latent_drivers": {},
            "synthetic_risk_probability": 0.0,
            "synthetic_truth_label": "normal_activity",
        }],
    )
    # Transfer events file points at a DIFFERENT transfer
    _write(
        data_dir / "events" / "transfer_events.json",
        [{"transfer_event_id": "tx_bbb", "amount_bucket": "amount_bucket_03"}],
    )
    with pytest.raises(ValueError, match="no matching transfer event"):
        load_eval_set("clean_holdout", data_dir=data_dir)


def test_unknown_truth_label_raises(tmp_path):
    """A label whose synthetic_truth_label isn't in LABEL_BINARY_MAP
    must raise — guards against silent label corruption."""
    data_dir = tmp_path / "synthetic"

    feat = {
        "event_id": "tx_aaa", "customer_id": "cust_aaa",
        "login_count_72h": 0, "login_count_30d": 0, "login_velocity_ratio": 0.0,
        "challenge_count_72h": 0, "challenge_pass_ratio_30d": 0.0,
        "password_recovery_count_72h": 0,
        "device_count_72h": 1, "current_device_tenure_days": 100,
        "geo_consistency_flag": 1, "transfer_count_72h": 0,
        "recipient_tenure_days": 100,
        "shared_device_degree": 0, "shared_recipient_degree": 0,
        "entity_graph_risk_score": 0.0, "cash_movement_velocity_score": 0.0,
    }
    _write(data_dir / "features" / "clean_holdout.json", [feat])
    _write(
        data_dir / "labels" / "label_generation.json",
        [{
            "event_id": "tx_aaa", "latent_drivers": {},
            "synthetic_risk_probability": 0.0,
            "synthetic_truth_label": "made_up_label",
        }],
    )
    _write(
        data_dir / "events" / "transfer_events.json",
        [{"transfer_event_id": "tx_aaa", "amount_bucket": "amount_bucket_03"}],
    )
    with pytest.raises(ValueError, match="unknown synthetic_truth_label"):
        load_eval_set("clean_holdout", data_dir=data_dir)


def test_missing_dataset_raises_clear_error(tmp_path):
    """Empty data_dir → MissingDatasetError with a 'run make seed' hint."""
    from atlas.model.loader import MissingDatasetError

    with pytest.raises(MissingDatasetError, match="make seed"):
        load_eval_set("clean_holdout", data_dir=tmp_path / "nope")
