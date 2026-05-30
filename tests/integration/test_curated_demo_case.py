"""Curated demo seed integration coverage."""
from __future__ import annotations

import json

import pytest


def _passing_candidate():
    return {
        "fixture_health": {"passed": True},
        "accepted_fixes": 2,
        "accepted_family_count": 2,
        "rejected_generalization_fixes": 0,
        "miss_abs_drop": 0.5,
        "final_miss": 0.04,
        "final_recall": 0.96,
        "loss_rel_drop": 0.6,
        "final_false_positive_rate": 0.03,
        "final_challenge_rate": 0.0,
        "final_alert_rate": 0.10,
        "final_decline_rate": 0.0,
        "locked_holdout_passes": [True, True],
        "drifted_holdout_passes": [True, True],
    }


def test_tightened_publish_thresholds_accept_two_family_case():
    from scripts.search_demo_case import _qualifies

    assert _qualifies(_passing_candidate()) is True

def test_tightened_publish_thresholds_reject_one_family_case():
    from scripts.search_demo_case import _qualifies

    candidate = _passing_candidate()
    candidate["accepted_fixes"] = 1
    candidate["accepted_family_count"] = 1
    candidate["rejected_generalization_fixes"] = 1
    candidate["locked_holdout_passes"] = [True]
    candidate["drifted_holdout_passes"] = [True]

    assert _qualifies(candidate) is False


def test_tightened_publish_thresholds_reject_high_final_miss():
    from scripts.search_demo_case import _qualifies

    candidate = _passing_candidate()
    candidate["final_miss"] = 0.5

    assert _qualifies(candidate) is False


def test_tightened_publish_thresholds_reject_implausibly_perfect_recall():
    from scripts.search_demo_case import _qualifies

    candidate = _passing_candidate()
    candidate["final_miss"] = 0.0
    candidate["final_recall"] = 1.0

    assert _qualifies(candidate) is False


def test_tightened_publish_thresholds_reject_low_final_recall():
    from scripts.search_demo_case import _qualifies

    candidate = _passing_candidate()
    candidate["final_miss"] = 0.10
    candidate["final_recall"] = 0.90

    assert _qualifies(candidate) is False


@pytest.mark.slow
def test_previous_seed_pair_no_longer_meets_publish_thresholds(tmp_path):
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

    assert rc == 1
    summary = json.loads(report_path.read_text())
    assert summary["selected"] is None
    metrics = summary["attempts"][0]

    assert metrics["qualifies"] is False
    if metrics.get("skipped_reason") == "fixture_health_failed":
        assert metrics["fixture_health"]["passed"] is False
    else:
        assert (
            metrics["final_miss"] > summary["targets"]["max_final_miss"]
            or metrics["final_recall"] < summary["targets"]["final_recall"]
            or metrics["final_recall"] > summary["targets"]["max_final_recall"]
        )
