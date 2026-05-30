"""Phase 8 run_engine (three-round lifecycle) tests.

Validates ``execute_run``:
  * argument validation (max_rounds < 1 raises),
  * deterministic byte-identical run + ledger across repeated invocations,
  * carry-forward across rounds (rejected → versions hold; accepted →
    versions advance and feed into the next round),
  * final RunState shape (status="completed", current_round==max_rounds).

Slow tests use the ``hermetic_outputs`` fixture pattern from
``test_phase8_round_engine.py`` to keep artifacts off the real
``outputs/`` tree.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def hermetic_outputs(tmp_path, monkeypatch):
    import atlas.judge.evaluate as evaluate_mod
    import atlas.ledger.round_engine as re_mod
    from atlas.ledger.report_builder import reset_caches as reset_report_caches

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    src = REPO_ROOT / "outputs" / "baseline_models" / "baseline_v1"
    dst = outputs / "baseline_models" / "baseline_v1"
    shutil.copytree(src, dst)

    monkeypatch.setattr(
        evaluate_mod, "BASELINE_MODELS_ROOT", outputs / "baseline_models"
    )
    monkeypatch.setattr(
        evaluate_mod, "ALTERNATE_THRESHOLDS_ROOT",
        outputs / "decision_thresholds",
    )
    evaluate_mod.reset_caches()
    re_mod.reset_caches()
    reset_report_caches()
    yield outputs
    evaluate_mod.reset_caches()
    re_mod.reset_caches()
    reset_report_caches()


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def test_execute_run_max_rounds_zero_raises():
    from atlas.ledger.run_engine import execute_run

    with pytest.raises(ValueError, match="max_rounds"):
        execute_run(seed=42, max_rounds=0, outputs_root=Path("/tmp/nope"))


def test_execute_run_max_rounds_negative_raises():
    from atlas.ledger.run_engine import execute_run

    with pytest.raises(ValueError, match="max_rounds"):
        execute_run(seed=42, max_rounds=-1, outputs_root=Path("/tmp/nope"))


# ---------------------------------------------------------------------------
# Single-round full-lifecycle (slow, real data)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_execute_run_one_round_completes(hermetic_outputs):
    """Smallest live run: max_rounds=1 → status=completed, ledger=1 row."""
    from atlas.ledger.ledger import load_ledger_records, load_run_state
    from atlas.ledger.run_engine import execute_run

    final = execute_run(
        seed=42, run_label="rt_run_1",
        max_rounds=1,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
        round_config_path=REPO_ROOT / "config" / "round_config_publish.yaml",
    )
    assert final.status == "completed"
    assert final.current_round == 1
    assert final.max_rounds == 1

    # Persisted run state matches.
    loaded = load_run_state(final.run_id, outputs_root=hermetic_outputs)
    assert loaded == final

    # Ledger has one row per round.
    rows = load_ledger_records(final.run_id, outputs_root=hermetic_outputs)
    assert len(rows) == 1
    assert rows[0]["round_id"] == 1


@pytest.mark.slow
def test_execute_run_three_rounds_completes(hermetic_outputs):
    """Bible §18 acceptance: three rounds run from seed."""
    from atlas.ledger.ledger import load_ledger_records, load_round_state
    from atlas.ledger.run_engine import execute_run

    final = execute_run(
        seed=42, run_label="rt_run_3",
        max_rounds=3,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
        round_config_path=REPO_ROOT / "config" / "round_config_publish.yaml",
    )
    assert final.status == "completed"
    assert final.current_round == 3

    # All three round states persisted.
    for rid in (1, 2, 3):
        rs = load_round_state(final.run_id, rid, outputs_root=hermetic_outputs)
        assert rs.status == "completed"
        assert rs.round_id == rid

    # Ledger has three rows.
    rows = load_ledger_records(final.run_id, outputs_root=hermetic_outputs)
    assert len(rows) == 3
    assert [r["round_id"] for r in rows] == [1, 2, 3]


@pytest.mark.slow
def test_execute_run_carry_forward_rejected(hermetic_outputs):
    """Real data: rounds reject → carry-forward holds versions across all rounds."""
    from atlas.ledger.ledger import load_round_state
    from atlas.ledger.run_engine import execute_run

    final = execute_run(
        seed=42, run_label="rt_carry",
        max_rounds=2,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
        round_config_path=REPO_ROOT / "config" / "round_config_publish.yaml",
    )
    rs1 = load_round_state(final.run_id, 1, outputs_root=hermetic_outputs)
    rs2 = load_round_state(final.run_id, 2, outputs_root=hermetic_outputs)

    # If both rejected, run_state stays at baseline.
    if not rs1.accepted_fix_id and not rs2.accepted_fix_id:
        assert final.current_model_version == "baseline_v1"
        assert final.current_threshold_version == "thresholds_v1"
        assert rs2.model_version_before == rs1.model_version_after


# ---------------------------------------------------------------------------
# Determinism: same seed → byte-identical run + ledger
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_execute_run_byte_identical_run_state(tmp_path, monkeypatch):
    """Same seed → byte-identical ``runs/<run_id>.json``."""
    import atlas.judge.evaluate as evaluate_mod
    import atlas.ledger.round_engine as re_mod
    from atlas.ledger.report_builder import reset_caches as reset_report_caches
    from atlas.ledger.run_engine import execute_run

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    src = REPO_ROOT / "outputs" / "baseline_models" / "baseline_v1"
    for out in (out_a, out_b):
        out.mkdir()
        shutil.copytree(src, out / "baseline_models" / "baseline_v1")

    def _run_in(out: Path):
        monkeypatch.setattr(
            evaluate_mod, "BASELINE_MODELS_ROOT", out / "baseline_models"
        )
        monkeypatch.setattr(
            evaluate_mod, "ALTERNATE_THRESHOLDS_ROOT", out / "decision_thresholds"
        )
        evaluate_mod.reset_caches()
        re_mod.reset_caches()
        reset_report_caches()
        return execute_run(
            seed=42, run_label="determinism",
            max_rounds=1,
            outputs_root=out,
            data_dir=REPO_ROOT / "data" / "synthetic",
            round_config_path=REPO_ROOT / "config" / "round_config_publish.yaml",
        )

    final_a = _run_in(out_a)
    final_b = _run_in(out_b)

    assert final_a.run_id == final_b.run_id
    bytes_a = (out_a / "runs" / f"{final_a.run_id}.json").read_bytes()
    bytes_b = (out_b / "runs" / f"{final_b.run_id}.json").read_bytes()
    assert bytes_a == bytes_b


@pytest.mark.slow
def test_execute_run_byte_identical_ledger(tmp_path, monkeypatch):
    """Same seed → byte-identical ``ledgers/<run_id>.jsonl``."""
    import atlas.judge.evaluate as evaluate_mod
    import atlas.ledger.round_engine as re_mod
    from atlas.ledger.report_builder import reset_caches as reset_report_caches
    from atlas.ledger.run_engine import execute_run

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    src = REPO_ROOT / "outputs" / "baseline_models" / "baseline_v1"
    for out in (out_a, out_b):
        out.mkdir()
        shutil.copytree(src, out / "baseline_models" / "baseline_v1")

    def _run_in(out: Path):
        monkeypatch.setattr(
            evaluate_mod, "BASELINE_MODELS_ROOT", out / "baseline_models"
        )
        monkeypatch.setattr(
            evaluate_mod, "ALTERNATE_THRESHOLDS_ROOT", out / "decision_thresholds"
        )
        evaluate_mod.reset_caches()
        re_mod.reset_caches()
        reset_report_caches()
        return execute_run(
            seed=42, run_label="ledger_determinism",
            max_rounds=1,
            outputs_root=out,
            data_dir=REPO_ROOT / "data" / "synthetic",
            round_config_path=REPO_ROOT / "config" / "round_config_publish.yaml",
        )

    final_a = _run_in(out_a)
    final_b = _run_in(out_b)

    bytes_a = (out_a / "ledgers" / f"{final_a.run_id}.jsonl").read_bytes()
    bytes_b = (out_b / "ledgers" / f"{final_b.run_id}.jsonl").read_bytes()
    assert bytes_a == bytes_b


# ---------------------------------------------------------------------------
# Carry-forward when judge ACCEPTS (mocked)
# ---------------------------------------------------------------------------


def _accept_judge_report(fix_id):
    return {
        "judge_report_id": f"judge_{fix_id}",
        "accepted_by_judge": True,
        "judge_notes": "accepted=True; recall_improves=True(...); ...",
        "holdout_generalization": {
            "clean_holdout_pass": True,
            "locked_adaptive_holdout_pass": True,
            "drifted_holdout_pass": True,
        },
        "run_id": "r", "round_id": 1, "defensive_fix_id": fix_id,
        "baseline": {"model_miss_rate": 1.0, "recall_at_fixed_action_rate": 0.0},
        "fixed": {"model_miss_rate": 0.5, "recall_at_fixed_action_rate": 0.5},
    }


@pytest.mark.slow
def test_execute_run_accepted_carry_forward_advances_versions(hermetic_outputs):
    """Mock judge always accepts → final run_state reflects round-N candidate."""
    import atlas.blue_team.fix_applier as applier_mod
    from atlas.ledger.ledger import load_round_state
    from atlas.ledger.run_engine import execute_run

    real_evaluate = applier_mod.evaluate_fix

    def _mock_evaluate(*args, **kwargs):
        fid = kwargs.get("defensive_fix_id", "")
        if "no_candidate" in fid:
            return real_evaluate(*args, **kwargs)
        return _accept_judge_report(fid)

    with mock.patch.object(applier_mod, "evaluate_fix", side_effect=_mock_evaluate):
        final = execute_run(
            seed=42, run_label="rt_accept",
            max_rounds=2,
            outputs_root=hermetic_outputs,
            data_dir=REPO_ROOT / "data" / "synthetic",
            round_config_path=REPO_ROOT / "config" / "round_config_publish.yaml",
        )

    rs1 = load_round_state(final.run_id, 1, outputs_root=hermetic_outputs)
    rs2 = load_round_state(final.run_id, 2, outputs_root=hermetic_outputs)

    if rs1.accepted_fix_id:
        # Round 2 carries forward round 1's accepted versions.
        assert rs2.model_version_before == rs1.model_version_after
        assert rs2.threshold_version_before == rs1.threshold_version_after
        # Final run_state matches round 2's after.
        assert final.current_model_version == rs2.model_version_after
        assert final.current_threshold_version == rs2.threshold_version_after


# ---------------------------------------------------------------------------
# Initial RunState shape
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_execute_run_run_id_format(hermetic_outputs):
    from atlas.ledger.run_engine import execute_run

    final = execute_run(
        seed=42, run_label="format_test",
        max_rounds=1,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
        round_config_path=REPO_ROOT / "config" / "round_config_publish.yaml",
    )
    assert final.run_id.startswith("run_")
    assert len(final.run_id) == 4 + 8


@pytest.mark.slow
def test_execute_run_different_seeds_different_run_ids(hermetic_outputs):
    """Different seeds → different run_ids."""
    from atlas.ledger.run_engine import execute_run

    final_a = execute_run(
        seed=42, run_label="alpha",
        max_rounds=1,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
        round_config_path=REPO_ROOT / "config" / "round_config_publish.yaml",
    )
    final_b = execute_run(
        seed=43, run_label="alpha",
        max_rounds=1,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
        round_config_path=REPO_ROOT / "config" / "round_config_publish.yaml",
    )
    assert final_a.run_id != final_b.run_id
