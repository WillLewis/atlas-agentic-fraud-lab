"""Phase 8 ledger primitives tests.

Round-trip RunState + RoundState; LedgerRecord JSONL semantics;
deterministic ``make_run_id``; ``read_dataset_reference_now_utc``;
error paths.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.ledger.ledger import (
    DEFAULT_AGENT_ROSTER_VERSION,
    DEFAULT_BASELINE_MODEL_VERSION,
    DEFAULT_BASELINE_THRESHOLD_VERSION,
    LedgerRecord,
    MissingLedgerError,
    MissingRunError,
    ROUND_STATUSES,
    RUN_STATUSES,
    RoundState,
    RunState,
    append_ledger_record,
    ledgers_dir,
    load_ledger_records,
    load_round_state,
    load_run_state,
    make_run_id,
    persist_round_state,
    persist_run_state,
    read_dataset_reference_now_utc,
    runs_dir,
)
from atlas.model.loader import MissingDatasetError

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# make_run_id
# ---------------------------------------------------------------------------


def test_make_run_id_deterministic():
    a = make_run_id(seed=42, run_label="x", demo_mode="public")
    b = make_run_id(seed=42, run_label="x", demo_mode="public")
    assert a == b


def test_make_run_id_format():
    rid = make_run_id(seed=42, run_label="x", demo_mode="public")
    assert rid.startswith("run_")
    assert len(rid) == 4 + 8  # "run_" + 8 hex chars


def test_make_run_id_changes_with_seed():
    a = make_run_id(seed=42, run_label="x", demo_mode="public")
    b = make_run_id(seed=43, run_label="x", demo_mode="public")
    assert a != b


def test_make_run_id_changes_with_label():
    a = make_run_id(seed=42, run_label="alpha", demo_mode="public")
    b = make_run_id(seed=42, run_label="beta", demo_mode="public")
    assert a != b


def test_make_run_id_changes_with_demo_mode():
    a = make_run_id(seed=42, run_label="x", demo_mode="public")
    b = make_run_id(seed=42, run_label="x", demo_mode="internal")
    assert a != b


# ---------------------------------------------------------------------------
# read_dataset_reference_now_utc
# ---------------------------------------------------------------------------


def test_read_dataset_reference_now_utc_real_data():
    ref = read_dataset_reference_now_utc(REPO_ROOT / "data" / "synthetic")
    assert ref == "2026-06-01T12:00:00Z"


def test_read_dataset_reference_now_utc_missing(tmp_path):
    with pytest.raises(MissingDatasetError, match="make seed"):
        read_dataset_reference_now_utc(tmp_path / "nope")


def test_read_dataset_reference_now_utc_invalid(tmp_path):
    bad = tmp_path / "synthetic"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps({}))
    with pytest.raises(ValueError, match="reference_now_utc"):
        read_dataset_reference_now_utc(bad)


# ---------------------------------------------------------------------------
# RunState round-trip
# ---------------------------------------------------------------------------


def _sample_run_state() -> RunState:
    return RunState(
        run_id="run_test1234",
        seed=42,
        demo_mode="public",
        status="completed",
        created_at_utc="2026-06-01T12:00:00Z",
        current_round=3,
        current_model_version="baseline_v1",
        current_threshold_version="thresholds_v1",
        run_label="test",
        max_rounds=3,
    )


def test_run_state_round_trip(tmp_path):
    outputs = tmp_path / "outputs"
    rs = _sample_run_state()
    persist_run_state(rs, outputs_root=outputs)
    loaded = load_run_state(rs.run_id, outputs_root=outputs)
    assert loaded == rs


def test_run_state_byte_identical_on_rewrite(tmp_path):
    outputs = tmp_path / "outputs"
    rs = _sample_run_state()
    p1 = persist_run_state(rs, outputs_root=outputs)
    bytes_a = p1.read_bytes()
    persist_run_state(rs, outputs_root=outputs)
    bytes_b = p1.read_bytes()
    assert bytes_a == bytes_b


def test_load_run_state_missing_raises(tmp_path):
    with pytest.raises(MissingRunError, match="make run-rounds"):
        load_run_state("run_does_not_exist", outputs_root=tmp_path / "outputs")


def test_run_state_persisted_under_runs_dir(tmp_path):
    outputs = tmp_path / "outputs"
    rs = _sample_run_state()
    p = persist_run_state(rs, outputs_root=outputs)
    assert p == runs_dir(outputs) / f"{rs.run_id}.json"
    assert p.parent.name == "runs"


# ---------------------------------------------------------------------------
# RoundState round-trip
# ---------------------------------------------------------------------------


def _sample_round_state(round_id: int = 1) -> RoundState:
    return RoundState(
        run_id="run_test1234",
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
        accepted_fix_id=None,
        judge_report_id="judge_x",
        transcript_summary="Round 1: ...",
        model_vulnerability_card_paths=["outputs/model_vulnerabilities/mv_x.json"],
        defensive_fix_paths=["outputs/defensive_fixes/fix_x.json"],
    )


def test_round_state_round_trip(tmp_path):
    outputs = tmp_path / "outputs"
    rs = _sample_round_state(1)
    persist_round_state(rs, outputs_root=outputs)
    loaded = load_round_state(rs.run_id, rs.round_id, outputs_root=outputs)
    assert loaded == rs


def test_round_state_per_round_filename(tmp_path):
    outputs = tmp_path / "outputs"
    rs1 = _sample_round_state(1)
    rs3 = _sample_round_state(3)
    p1 = persist_round_state(rs1, outputs_root=outputs)
    p3 = persist_round_state(rs3, outputs_root=outputs)
    assert p1.name == "run_test1234.round_01.json"
    assert p3.name == "run_test1234.round_03.json"


def test_round_state_byte_identical_on_rewrite(tmp_path):
    outputs = tmp_path / "outputs"
    rs = _sample_round_state(1)
    p = persist_round_state(rs, outputs_root=outputs)
    bytes_a = p.read_bytes()
    persist_round_state(rs, outputs_root=outputs)
    bytes_b = p.read_bytes()
    assert bytes_a == bytes_b


# ---------------------------------------------------------------------------
# LedgerRecord JSONL
# ---------------------------------------------------------------------------


def _sample_ledger_row(round_id: int = 1) -> LedgerRecord:
    return {
        "run_id": "run_test1234",
        "round_id": round_id,
        "seed": 42,
        "demo_mode": "public",
        "model_version_before": "baseline_v1",
        "decision_threshold_version_before": "thresholds_v1",
        "model_version_after": "baseline_v1",
        "decision_threshold_version_after": "thresholds_v1",
        "agent_roster_version": "agents_v1",
        "safety_scan_passed": True,
        "judge_report_path": "outputs/reports/judge_x.json",
        "model_vulnerability_card_path": "outputs/model_vulnerabilities/mv_x.json",
    }


def test_append_ledger_record_writes_one_line(tmp_path):
    outputs = tmp_path / "outputs"
    p = append_ledger_record(_sample_ledger_row(1), outputs_root=outputs)
    assert p.read_text().count("\n") == 1
    assert p.parent.name == "ledgers"


def test_append_ledger_record_appends(tmp_path):
    outputs = tmp_path / "outputs"
    append_ledger_record(_sample_ledger_row(1), outputs_root=outputs)
    append_ledger_record(_sample_ledger_row(2), outputs_root=outputs)
    rows = load_ledger_records("run_test1234", outputs_root=outputs)
    assert len(rows) == 2
    assert [r["round_id"] for r in rows] == [1, 2]


def test_append_ledger_record_byte_identical_per_row(tmp_path):
    """Same row content → identical line bytes (sorted-key JSON)."""
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    append_ledger_record(_sample_ledger_row(1), outputs_root=out_a)
    append_ledger_record(_sample_ledger_row(1), outputs_root=out_b)
    bytes_a = (out_a / "ledgers" / "run_test1234.jsonl").read_bytes()
    bytes_b = (out_b / "ledgers" / "run_test1234.jsonl").read_bytes()
    assert bytes_a == bytes_b


def test_load_ledger_missing_raises(tmp_path):
    with pytest.raises(MissingLedgerError, match="make run-rounds"):
        load_ledger_records("run_nope", outputs_root=tmp_path / "outputs")


def test_ledger_record_field_names_match_web_shell():
    """``app/web/lib/types.ts.LedgerRecord`` field-for-field."""
    row = _sample_ledger_row(1)
    expected = {
        "run_id", "round_id", "seed", "demo_mode",
        "model_version_before", "decision_threshold_version_before",
        "model_version_after", "decision_threshold_version_after",
        "agent_roster_version", "safety_scan_passed",
        "judge_report_path", "model_vulnerability_card_path",
    }
    assert set(row) == expected


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_default_baseline_versions():
    assert DEFAULT_BASELINE_MODEL_VERSION == "baseline_v1"
    assert DEFAULT_BASELINE_THRESHOLD_VERSION == "thresholds_v1"
    assert DEFAULT_AGENT_ROSTER_VERSION == "agents_v1"


def test_status_enums():
    assert "running" in RUN_STATUSES and "completed" in RUN_STATUSES
    assert "completed" in ROUND_STATUSES
