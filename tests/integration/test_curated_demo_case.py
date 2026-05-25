"""Curated demo seed integration coverage."""
from __future__ import annotations

import json

import pytest


@pytest.mark.slow
def test_curated_seed_pair_meets_publish_thresholds(tmp_path):
    from scripts.search_demo_case import main

    report_path = tmp_path / "search_report.json"
    search_root = tmp_path / "search"

    rc = main(
        [
            "--dataset-seeds",
            "6001",
            "--run-seeds",
            "42",
            "--customer-count",
            "600",
            "--search-root",
            str(search_root),
            "--report-path",
            str(report_path),
        ]
    )

    assert rc == 0
    summary = json.loads(report_path.read_text())
    metrics = summary["selected"]["metrics"]

    assert metrics["final_recall"] >= 0.50
    assert metrics["miss_abs_drop"] >= 0.3333
    assert metrics["loss_rel_drop"] >= 0.30
    assert metrics["final_false_positive_rate"] <= 0.05
    assert metrics["final_alert_rate"] <= 0.15
    assert metrics["final_challenge_rate"] <= 0.08
    assert metrics["final_decline_rate"] <= 0.0025
    assert all(metrics["locked_holdout_passes"])
    assert all(metrics["drifted_holdout_passes"])
