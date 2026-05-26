#!/usr/bin/env python3
"""Transparent search harness for a curated Project Atlas demo case.

The harness searches over dataset seeds and run seeds with fixed,
predeclared KPI thresholds. It writes every attempted candidate to a
JSON report so a promoted walkthrough case is traceable as a selected
synthetic demo, not an empirical benchmark.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
SCRIPTS = REPO_ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from atlas.ledger.ledger import load_round_state, round_state_path  # noqa: E402
from atlas.ledger.replay import build_replay_payload, persist_replay_payload  # noqa: E402
from atlas.ledger.run_engine import execute_run  # noqa: E402
from atlas.model.train import train_baseline_model  # noqa: E402
from atlas.red_team.mutations import ALLOWED_FAMILY_IDS  # noqa: E402
from atlas.synthetic.fixture_health import (  # noqa: E402
    FixtureHealthReport,
    evaluate_fixture_health,
)
from generate_synthetic import persist_dataset, run_pipeline  # noqa: E402


DEFAULT_SEARCH_ROOT = Path("/private/tmp/atlas_demo_case_search")
DEFAULT_DATASET_SEEDS = "6001,42,1764886470,1001,2025"
DEFAULT_RUN_SEEDS = "42-62"

TARGETS: dict[str, float] = {
    "miss_abs_drop": 0.3333,
    "max_final_miss": 0.3333,
    "final_recall": 0.66,
    "loss_rel_drop": 0.50,
    "accepted_fixes": 1.0,
    "accepted_family_count": 2.0,
    "rejected_generalization_fixes": 1.0,
    "max_final_false_positive_rate": 0.05,
    "max_final_challenge_rate": 0.08,
    "max_final_alert_rate": 0.15,
    "max_final_decline_rate": 0.0025,
}

PROMOTED_OUTPUT_SUBDIRS: tuple[str, ...] = (
    "baseline_models",
    "decision_thresholds",
    "defensive_fixes",
    "demo_replays",
    "ledgers",
    "model_vulnerabilities",
    "reports",
    "runs",
)


def _parse_seed_list(raw: str) -> list[int]:
    out: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_s, end_s = token.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            if end < start:
                raise ValueError(f"invalid descending seed range: {token}")
            out.extend(range(start, end + 1))
        else:
            out.append(int(token))
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search for a publishable synthetic demo case."
    )
    parser.add_argument(
        "--dataset-seeds",
        default=DEFAULT_DATASET_SEEDS,
        help=(
            "Comma-separated integers or ranges, e.g. '42,100-105'. "
            f"Default: {DEFAULT_DATASET_SEEDS}."
        ),
    )
    parser.add_argument(
        "--run-seeds",
        default=DEFAULT_RUN_SEEDS,
        help=(
            "Comma-separated integers or ranges, e.g. '42,100-105'. "
            f"Default: {DEFAULT_RUN_SEEDS}."
        ),
    )
    parser.add_argument("--customer-count", type=int, default=600)
    parser.add_argument("--search-root", type=Path, default=DEFAULT_SEARCH_ROOT)
    parser.add_argument("--report-path", type=Path, default=None)
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--keep-existing-search-root", action="store_true")
    return parser.parse_args(argv)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def _prepare_search_root(path: Path, *, keep_existing: bool) -> None:
    if path.exists() and not keep_existing:
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _generate_dataset(*, dataset_seed: int, customer_count: int, data_dir: Path) -> None:
    splits, recipients = run_pipeline(seed=dataset_seed, customer_count=customer_count)
    persist_dataset(
        output_dir=data_dir,
        splits=splits,
        recipients=recipients,
        seed=dataset_seed,
        customer_count=customer_count,
    )


def _train_baseline(*, dataset_seed: int, data_dir: Path, outputs_root: Path) -> None:
    train_baseline_model(
        seed=dataset_seed,
        data_dir=data_dir,
        output_dir=outputs_root / "baseline_models" / "baseline_v1",
        fitted_thresholds_dir=outputs_root / "decision_thresholds",
    )


def _reports_for_run(*, outputs_root: Path, run_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted((outputs_root / "reports").glob(f"judge_{run_id}_*.json")):
        with path.open("r", encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def _family_from_fix_id(defensive_fix_id: str) -> str | None:
    for family_id in ALLOWED_FAMILY_IDS:
        if family_id in defensive_fix_id:
            return family_id
    return None


def _is_rejected_generalization_case(report: dict[str, Any]) -> bool:
    if report.get("accepted_by_judge") is True:
        return False
    holdouts = report.get("holdout_generalization")
    if not isinstance(holdouts, dict):
        return False
    return (
        holdouts.get("found_adaptive_set_pass") is True
        and (
            holdouts.get("clean_holdout_pass") is False
            or holdouts.get("locked_adaptive_holdout_pass") is False
            or holdouts.get("drifted_holdout_pass") is False
        )
    )


def _score_candidate(
    *,
    dataset_seed: int,
    customer_count: int,
    fixture_health: FixtureHealthReport,
    payload: dict[str, Any],
    outputs_root: Path,
) -> dict[str, Any]:
    metrics = payload["charts"]["round_metrics"]
    baseline = metrics[0]
    final = metrics[-1]
    reports = _reports_for_run(outputs_root=outputs_root, run_id=payload["run"]["run_id"])
    accepted = [r for r in reports if r.get("accepted_by_judge") is True]
    accepted_families = sorted(
        {
            family
            for report in accepted
            if (family := _family_from_fix_id(str(report.get("defensive_fix_id", ""))))
        }
    )
    rejected_generalization = [
        r for r in reports if _is_rejected_generalization_case(r)
    ]
    baseline_loss = float(baseline.get("synthetic_loss_allowed") or 0.0)
    final_loss = float(final.get("synthetic_loss_allowed") or 0.0)
    loss_abs_drop = baseline_loss - final_loss
    baseline_miss = float(baseline.get("model_miss_rate") or 0.0)
    final_miss = float(final.get("model_miss_rate") or 0.0)
    final_recall = float(final.get("recall_at_fixed_action_rate") or 0.0)
    result = {
        "dataset_seed": int(dataset_seed),
        "run_seed": int(payload["run"]["seed"]),
        "customer_count": int(customer_count),
        "run_id": payload["run"]["run_id"],
        "accepted_fixes": len(accepted),
        "accepted_rounds": [int(r["round_id"]) for r in accepted],
        "accepted_fix_families": accepted_families,
        "accepted_family_count": len(accepted_families),
        "rejected_generalization_fixes": len(rejected_generalization),
        "rejected_generalization_rounds": [
            int(r["round_id"]) for r in rejected_generalization
        ],
        "baseline_miss": round(baseline_miss, 4),
        "final_miss": round(final_miss, 4),
        "miss_abs_drop": round(baseline_miss - final_miss, 4),
        "baseline_recall": round(
            float(baseline.get("recall_at_fixed_action_rate") or 0.0), 4
        ),
        "final_recall": round(final_recall, 4),
        "baseline_loss": baseline_loss,
        "final_loss": final_loss,
        "loss_abs_drop": loss_abs_drop,
        "loss_rel_drop": round(loss_abs_drop / baseline_loss, 4)
        if baseline_loss
        else 0.0,
        "final_false_positive_rate": round(
            float(final.get("false_positive_rate_at_fixed_action_rate") or 0.0), 4
        ),
        "final_challenge_rate": round(float(final.get("challenge_rate") or 0.0), 4),
        "final_alert_rate": round(float(final.get("alert_rate") or 0.0), 4),
        "final_decline_rate": round(float(final.get("decline_rate") or 0.0), 4),
        "locked_holdout_passes": [
            bool(r.get("holdout_generalization", {}).get("locked_adaptive_holdout_pass"))
            for r in accepted
        ],
        "drifted_holdout_passes": [
            bool(r.get("holdout_generalization", {}).get("drifted_holdout_pass"))
            for r in accepted
        ],
        "fixture_health": fixture_health,
    }
    result["qualifies"] = _qualifies(result)
    return result


def _qualifies(result: dict[str, Any]) -> bool:
    story_gate_passes = (
        result["accepted_family_count"] >= int(TARGETS["accepted_family_count"])
        or (
            result["accepted_fixes"] >= int(TARGETS["accepted_fixes"])
            and result["rejected_generalization_fixes"]
            >= int(TARGETS["rejected_generalization_fixes"])
        )
    )
    return (
        result["fixture_health"]["passed"]
        and result["accepted_fixes"] >= int(TARGETS["accepted_fixes"])
        and story_gate_passes
        and result["miss_abs_drop"] >= TARGETS["miss_abs_drop"]
        and result["final_miss"] <= TARGETS["max_final_miss"]
        and result["final_recall"] >= TARGETS["final_recall"]
        and result["loss_rel_drop"] >= TARGETS["loss_rel_drop"]
        and result["final_false_positive_rate"]
        <= TARGETS["max_final_false_positive_rate"]
        and result["final_challenge_rate"] <= TARGETS["max_final_challenge_rate"]
        and result["final_alert_rate"] <= TARGETS["max_final_alert_rate"]
        and result["final_decline_rate"] <= TARGETS["max_final_decline_rate"]
        and all(result["locked_holdout_passes"])
        and all(result["drifted_holdout_passes"])
    )


def _run_candidate(
    *,
    dataset_seed: int,
    run_seed: int,
    customer_count: int,
    data_dir: Path,
    outputs_root: Path,
    fixture_health: FixtureHealthReport,
) -> dict[str, Any]:
    run_state = execute_run(
        seed=run_seed,
        demo_mode="public",
        max_rounds=3,
        outputs_root=outputs_root,
        data_dir=data_dir,
    )
    round_states = []
    for round_id in range(1, run_state.max_rounds + 1):
        path = round_state_path(run_state.run_id, round_id, outputs_root=outputs_root)
        if path.exists():
            round_states.append(
                load_round_state(run_state.run_id, round_id, outputs_root=outputs_root)
            )
    payload = build_replay_payload(
        run_state,
        round_states,
        outputs_root=outputs_root,
        data_dir=data_dir,
    )
    persist_replay_payload(payload, run_id=run_state.run_id, outputs_root=outputs_root)
    return _score_candidate(
        dataset_seed=dataset_seed,
        customer_count=customer_count,
        fixture_health=fixture_health,
        payload=payload,
        outputs_root=outputs_root,
    )


def _promote_candidate(
    *,
    data_dir: Path,
    outputs_root: Path,
) -> None:
    target_data = REPO_ROOT / "data" / "synthetic"
    if target_data.exists():
        shutil.rmtree(target_data)
    shutil.copytree(data_dir, target_data)

    target_outputs = REPO_ROOT / "outputs"
    target_outputs.mkdir(parents=True, exist_ok=True)
    for subdir in PROMOTED_OUTPUT_SUBDIRS:
        src = outputs_root / subdir
        if not src.exists():
            continue
        dst = target_outputs / subdir
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    dataset_seeds = _parse_seed_list(args.dataset_seeds)
    run_seeds = _parse_seed_list(args.run_seeds)
    search_root = args.search_root.resolve()
    report_path = (
        args.report_path.resolve()
        if args.report_path is not None
        else search_root / "search_report.json"
    )
    _prepare_search_root(search_root, keep_existing=args.keep_existing_search_root)

    attempts: list[dict[str, Any]] = []
    promoted: dict[str, Any] | None = None

    for dataset_seed in dataset_seeds:
        dataset_root = search_root / f"dataset_seed_{dataset_seed}"
        data_dir = dataset_root / "data" / "synthetic"
        outputs_root = dataset_root / "outputs"
        _generate_dataset(
            dataset_seed=dataset_seed,
            customer_count=args.customer_count,
            data_dir=data_dir,
        )
        fixture_health = evaluate_fixture_health(data_dir=data_dir)
        dataset_record: dict[str, Any] = {
            "dataset_seed": int(dataset_seed),
            "customer_count": int(args.customer_count),
            "fixture_health": fixture_health,
        }
        if not fixture_health["passed"]:
            dataset_record["qualifies"] = False
            dataset_record["skipped_reason"] = "fixture_health_failed"
            attempts.append(dataset_record)
            print(json.dumps(dataset_record, sort_keys=True), flush=True)
            continue

        _train_baseline(
            dataset_seed=dataset_seed,
            data_dir=data_dir,
            outputs_root=outputs_root,
        )

        for run_seed in run_seeds:
            result = _run_candidate(
                dataset_seed=dataset_seed,
                run_seed=run_seed,
                customer_count=args.customer_count,
                data_dir=data_dir,
                outputs_root=outputs_root,
                fixture_health=fixture_health,
            )
            attempts.append(result)
            print(json.dumps(result, sort_keys=True), flush=True)
            if result["qualifies"]:
                promoted = {
                    "dataset_seed": int(dataset_seed),
                    "run_seed": int(run_seed),
                    "run_id": result["run_id"],
                    "metrics": result,
                }
                if args.promote:
                    _promote_candidate(data_dir=data_dir, outputs_root=outputs_root)
                    promoted["promoted_to_repo"] = True
                break
        if promoted is not None:
            break

    summary = {
        "targets": TARGETS,
        "dataset_seeds": dataset_seeds,
        "run_seeds": run_seeds,
        "customer_count": int(args.customer_count),
        "attempts": attempts,
        "selected": promoted,
    }
    _write_json(report_path, summary)
    print(f"search_report={report_path}")
    return 0 if promoted is not None else 1


if __name__ == "__main__":
    sys.exit(main())
