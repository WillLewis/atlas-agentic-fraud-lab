"""Fixture-health checks for curated Project Atlas demo cases.

These checks do not score models and do not decide whether a defensive
fix passes. They only ensure the synthetic evaluation partitions have
enough high-risk examples for a walkthrough case to produce meaningful
judge-derived KPI movement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, TypedDict

from atlas.judge.holdouts import JudgeEvalRecord, load_eval_set
from atlas.model.loader import DEFAULT_DATA_DIR


HEADLINE_HOLDOUTS: Final[tuple[str, ...]] = (
    "clean_holdout",
    "locked_adaptive_holdout",
    "drifted_holdout",
)

DEFAULT_MIN_HIGH_RISK_BY_HOLDOUT: Final[dict[str, int]] = {
    "clean_holdout": 50,
    "locked_adaptive_holdout": 25,
    "drifted_holdout": 25,
}


class HoldoutHealth(TypedDict):
    total_events: int
    high_risk_events: int
    normal_events: int
    min_high_risk_events: int
    passed: bool


class FixtureHealthReport(TypedDict):
    passed: bool
    holdouts: dict[str, HoldoutHealth]
    failed_holdouts: list[str]


class FixtureHealthError(ValueError):
    """Raised when a dataset is too sparse for a publishable demo case."""


def _count_holdout(
    records: list[JudgeEvalRecord],
    *,
    min_high_risk_events: int,
) -> HoldoutHealth:
    high_risk = sum(1 for r in records if int(r["binary_label"]) == 1)
    total = len(records)
    return {
        "total_events": total,
        "high_risk_events": high_risk,
        "normal_events": total - high_risk,
        "min_high_risk_events": int(min_high_risk_events),
        "passed": high_risk >= int(min_high_risk_events),
    }


def evaluate_fixture_health(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    min_high_risk_by_holdout: dict[str, int] | None = None,
) -> FixtureHealthReport:
    """Return high-risk denominator health for headline holdouts."""
    thresholds = dict(DEFAULT_MIN_HIGH_RISK_BY_HOLDOUT)
    if min_high_risk_by_holdout:
        thresholds.update(
            {str(k): int(v) for k, v in min_high_risk_by_holdout.items()}
        )

    holdouts: dict[str, HoldoutHealth] = {}
    for name in HEADLINE_HOLDOUTS:
        records = load_eval_set(name, data_dir=data_dir)
        holdouts[name] = _count_holdout(
            records,
            min_high_risk_events=thresholds[name],
        )

    failed = [name for name, report in holdouts.items() if not report["passed"]]
    return {
        "passed": not failed,
        "holdouts": holdouts,
        "failed_holdouts": failed,
    }


def assert_fixture_health(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    min_high_risk_by_holdout: dict[str, int] | None = None,
) -> FixtureHealthReport:
    """Return the report or raise ``FixtureHealthError`` with details."""
    report = evaluate_fixture_health(
        data_dir=data_dir,
        min_high_risk_by_holdout=min_high_risk_by_holdout,
    )
    if report["passed"]:
        return report
    details = ", ".join(
        (
            f"{name} high_risk={report['holdouts'][name]['high_risk_events']} "
            f"< {report['holdouts'][name]['min_high_risk_events']}"
        )
        for name in report["failed_holdouts"]
    )
    raise FixtureHealthError(f"fixture health failed: {details}")


__all__ = [
    "DEFAULT_MIN_HIGH_RISK_BY_HOLDOUT",
    "FixtureHealthError",
    "FixtureHealthReport",
    "HEADLINE_HOLDOUTS",
    "assert_fixture_health",
    "evaluate_fixture_health",
]
