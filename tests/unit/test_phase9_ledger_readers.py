"""Phase 9 ledger read-helper tests.

Validates the thin readers added in component 2 against hermetic tmp
output trees:

  * ``list_run_states``                       — walks outputs/runs/, skips
                                                 round companions
  * ``load_round_states``                     — bulk per-run round loader
  * ``load_judge_report``                     — single report by id; raises
                                                 ``MissingJudgeReportError``
  * ``load_run_model_vulnerability_records``  — filters by run_id
  * ``load_run_defensive_fix_manifests``      — filters by run_id

All helpers operate on persisted artifacts only — no business logic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.ledger.ledger import (
    MissingJudgeReportError,
    RoundState,
    RunState,
    defensive_fixes_dir,
    list_run_states,
    load_judge_report,
    load_round_states,
    load_run_defensive_fix_manifests,
    load_run_model_vulnerability_records,
    model_vulnerabilities_dir,
    persist_round_state,
    persist_run_state,
    reports_dir,
)


def _run_state(run_id="run_test1234", status="completed"):
    return RunState(
        run_id=run_id,
        seed=42,
        demo_mode="public",
        status=status,
        created_at_utc="2026-06-01T12:00:00Z",
        current_round=3,
        current_model_version="baseline_v1",
        current_threshold_version="thresholds_v1",
        run_label="test",
        max_rounds=3,
    )


def _round_state(run_id, round_id):
    return RoundState(
        run_id=run_id,
        round_id=round_id,
        status="completed",
        model_version_before="baseline_v1",
        threshold_version_before="thresholds_v1",
        model_version_after="baseline_v1",
        threshold_version_after="thresholds_v1",
        model_miss_rate_before=1.0,
        model_miss_rate_after=1.0,
        recall_at_fixed_action_rate_before=0.0,
        recall_at_fixed_action_rate_after=0.0,
        safety_scan_passed=True,
    )


# ---------------------------------------------------------------------------
# list_run_states
# ---------------------------------------------------------------------------


def test_list_run_states_empty_dir_returns_empty(tmp_path):
    assert list_run_states(tmp_path / "outputs") == []


def test_list_run_states_returns_persisted(tmp_path):
    outputs = tmp_path / "outputs"
    a = _run_state("run_aaaaaa01")
    b = _run_state("run_bbbbbb02")
    persist_run_state(a, outputs_root=outputs)
    persist_run_state(b, outputs_root=outputs)
    runs = list_run_states(outputs)
    assert [r.run_id for r in runs] == ["run_bbbbbb02", "run_aaaaaa01"]


def test_list_run_states_skips_round_companions(tmp_path):
    """``run_xxx.round_01.json`` must NOT be parsed as a RunState."""
    outputs = tmp_path / "outputs"
    rs = _run_state("run_zzzzzz01")
    persist_run_state(rs, outputs_root=outputs)
    persist_round_state(_round_state(rs.run_id, 1), outputs_root=outputs)
    persist_round_state(_round_state(rs.run_id, 2), outputs_root=outputs)
    runs = list_run_states(outputs)
    assert len(runs) == 1
    assert runs[0].run_id == "run_zzzzzz01"


def test_list_run_states_skips_unrelated_json(tmp_path):
    """A stray non-RunState JSON shouldn't crash the listing."""
    outputs = tmp_path / "outputs"
    persist_run_state(_run_state("run_aaaaaa01"), outputs_root=outputs)
    bogus = outputs / "runs" / "stray.json"
    bogus.write_text(json.dumps({"unexpected": "shape"}))
    runs = list_run_states(outputs)
    assert [r.run_id for r in runs] == ["run_aaaaaa01"]


# ---------------------------------------------------------------------------
# load_round_states
# ---------------------------------------------------------------------------


def test_load_round_states_empty_when_none(tmp_path):
    assert load_round_states("run_x", outputs_root=tmp_path / "outputs") == []


def test_load_round_states_orders_by_round_id(tmp_path):
    outputs = tmp_path / "outputs"
    persist_run_state(_run_state("run_zzzzzz01"), outputs_root=outputs)
    # Persist out of order.
    persist_round_state(_round_state("run_zzzzzz01", 3), outputs_root=outputs)
    persist_round_state(_round_state("run_zzzzzz01", 1), outputs_root=outputs)
    persist_round_state(_round_state("run_zzzzzz01", 2), outputs_root=outputs)
    rounds = load_round_states("run_zzzzzz01", outputs_root=outputs)
    assert [r.round_id for r in rounds] == [1, 2, 3]


def test_load_round_states_filters_by_run_id(tmp_path):
    """Other runs' round files must NOT bleed into the result."""
    outputs = tmp_path / "outputs"
    persist_round_state(_round_state("run_aaaaaa01", 1), outputs_root=outputs)
    persist_round_state(_round_state("run_bbbbbb02", 1), outputs_root=outputs)
    a = load_round_states("run_aaaaaa01", outputs_root=outputs)
    b = load_round_states("run_bbbbbb02", outputs_root=outputs)
    assert [r.run_id for r in a] == ["run_aaaaaa01"]
    assert [r.run_id for r in b] == ["run_bbbbbb02"]


# ---------------------------------------------------------------------------
# load_judge_report
# ---------------------------------------------------------------------------


def test_load_judge_report_missing_raises(tmp_path):
    with pytest.raises(MissingJudgeReportError, match="make run-rounds"):
        load_judge_report("judge_nope", outputs_root=tmp_path / "outputs")


def test_load_judge_report_round_trip(tmp_path):
    outputs = tmp_path / "outputs"
    rdir = reports_dir(outputs)
    rdir.mkdir(parents=True)
    payload = {
        "judge_report_id": "judge_x",
        "run_id": "run_aaaaaa01",
        "round_id": 1,
        "accepted_by_judge": True,
        "baseline": {"model_miss_rate": 1.0},
        "fixed": {"model_miss_rate": 0.5},
    }
    (rdir / "judge_x.json").write_text(json.dumps(payload, sort_keys=True))
    loaded = load_judge_report("judge_x", outputs_root=outputs)
    assert loaded == payload


# ---------------------------------------------------------------------------
# load_run_model_vulnerability_records
# ---------------------------------------------------------------------------


def _write_mv_record(outputs, mv_id, run_id):
    mdir = model_vulnerabilities_dir(outputs)
    mdir.mkdir(parents=True, exist_ok=True)
    record = {
        "model_vulnerability_id": mv_id,
        "run_id": run_id,
        "round_id": 1,
        "family_id": "score_boundary_cluster",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["policy_fix"],
        "summary": "stable",
    }
    (mdir / f"{mv_id}.json").write_text(json.dumps(record, sort_keys=True))
    return record


def test_load_run_model_vulnerability_records_empty_dir(tmp_path):
    assert load_run_model_vulnerability_records(
        "run_x", outputs_root=tmp_path / "outputs"
    ) == []


def test_load_run_model_vulnerability_records_filters_by_run_id(tmp_path):
    outputs = tmp_path / "outputs"
    _write_mv_record(outputs, "mv_round1_a", "run_aaaaaa01")
    _write_mv_record(outputs, "mv_round1_b", "run_aaaaaa01")
    _write_mv_record(outputs, "mv_round1_c", "run_bbbbbb02")
    a = load_run_model_vulnerability_records(
        "run_aaaaaa01", outputs_root=outputs,
    )
    assert {r["model_vulnerability_id"] for r in a} == {
        "mv_round1_a", "mv_round1_b",
    }
    assert all(r["run_id"] == "run_aaaaaa01" for r in a)


# ---------------------------------------------------------------------------
# load_run_defensive_fix_manifests
# ---------------------------------------------------------------------------


def _write_fix_manifest(outputs, fix_id, run_id):
    fdir = defensive_fixes_dir(outputs)
    fdir.mkdir(parents=True, exist_ok=True)
    record = {
        "defensive_fix_id": fix_id,
        "run_id": run_id,
        "round_id": 1,
        "vulnerability_id": "mv_round1_x",
        "fix_type": "policy_fix",
    }
    (fdir / f"{fix_id}.json").write_text(json.dumps(record, sort_keys=True))


def test_load_run_defensive_fix_manifests_empty(tmp_path):
    assert load_run_defensive_fix_manifests(
        "run_x", outputs_root=tmp_path / "outputs"
    ) == []


def test_load_run_defensive_fix_manifests_filters(tmp_path):
    outputs = tmp_path / "outputs"
    _write_fix_manifest(outputs, "fix_round1_a", "run_aaaaaa01")
    _write_fix_manifest(outputs, "fix_round1_b", "run_bbbbbb02")
    a = load_run_defensive_fix_manifests(
        "run_aaaaaa01", outputs_root=outputs,
    )
    assert [r["defensive_fix_id"] for r in a] == ["fix_round1_a"]
