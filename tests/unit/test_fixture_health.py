"""Fixture-health checks for curated demo datasets."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.judge.holdouts import load_eval_set
from atlas.synthetic.fixture_health import (
    FixtureHealthError,
    assert_fixture_health,
    evaluate_fixture_health,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "synthetic"


def test_curated_fixture_health_passes_thresholds():
    report = evaluate_fixture_health(data_dir=DATA_DIR)

    assert report["passed"] is True
    assert report["failed_holdouts"] == []
    assert report["holdouts"]["clean_holdout"]["high_risk_events"] >= 50
    assert report["holdouts"]["locked_adaptive_holdout"]["high_risk_events"] >= 25
    assert report["holdouts"]["drifted_holdout"]["high_risk_events"] >= 25


def test_fixture_health_raises_when_denominator_is_too_small():
    current = evaluate_fixture_health(data_dir=DATA_DIR)
    too_high = current["holdouts"]["clean_holdout"]["high_risk_events"] + 1

    with pytest.raises(FixtureHealthError, match="clean_holdout"):
        assert_fixture_health(
            data_dir=DATA_DIR,
            min_high_risk_by_holdout={"clean_holdout": too_high},
        )


def test_headline_holdout_customer_sets_are_isolated():
    split_customers = set()
    for split_name in ("train", "validation", "clean_holdout"):
        payload = json.loads((DATA_DIR / "splits" / f"{split_name}.json").read_text())
        split_customers.update(payload["customer_ids"])

    locked_customers = {
        r["customer_id"]
        for r in load_eval_set("locked_adaptive_holdout", data_dir=DATA_DIR)
    }
    drifted_customers = {
        r["customer_id"]
        for r in load_eval_set("drifted_holdout", data_dir=DATA_DIR)
    }

    assert split_customers.isdisjoint(locked_customers)
    assert split_customers.isdisjoint(drifted_customers)
    assert locked_customers.isdisjoint(drifted_customers)


def test_headline_holdout_ids_keep_synthetic_prefixes():
    for holdout_name in (
        "clean_holdout",
        "locked_adaptive_holdout",
        "drifted_holdout",
    ):
        records = load_eval_set(holdout_name, data_dir=DATA_DIR)
        assert records
        assert all(r["event_id"].startswith("tx_") for r in records)
        assert all(r["customer_id"].startswith("cust_") for r in records)
