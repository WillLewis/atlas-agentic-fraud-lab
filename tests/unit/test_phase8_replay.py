"""Phase 8 replay-builder tests.

Verifies ``build_replay_payload`` + ``persist_replay_payload`` against
the ``app/web/lib/types.ts`` shapes (RunDetail / FiveStepStory /
MetricSnapshot). Builds a synthetic ``RunState`` + ``RoundState`` set
plus a fabricated judge-report file so the tests are hermetic and fast
(no live round execution).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _run_state(run_id="run_replay01", current_round=3, max_rounds=3):
    from atlas.ledger.ledger import RunState

    return RunState(
        run_id=run_id,
        seed=42,
        demo_mode="public",
        status="completed",
        created_at_utc="2026-06-01T12:00:00Z",
        current_round=current_round,
        current_model_version="baseline_v1",
        current_threshold_version="thresholds_v1",
        run_label="replay_fix",
        max_rounds=max_rounds,
    )


def _round_state(
    *,
    run_id="run_replay01",
    round_id=1,
    accepted_fix_id=None,
    judge_report_id="judge_replay_round1",
    miss_before=1.0,
    miss_after=1.0,
):
    from atlas.ledger.ledger import RoundState

    return RoundState(
        run_id=run_id,
        round_id=round_id,
        status="completed",
        model_version_before="baseline_v1",
        threshold_version_before="thresholds_v1",
        model_version_after="baseline_v1",
        threshold_version_after="thresholds_v1",
        model_miss_rate_before=miss_before,
        model_miss_rate_after=miss_after,
        recall_at_fixed_action_rate_before=0.0,
        recall_at_fixed_action_rate_after=0.0,
        safety_scan_passed=True,
        accepted_fix_id=accepted_fix_id,
        judge_report_id=judge_report_id,
        transcript_summary=(
            f"Round {round_id}: red-team surfaced 0 model_vulnerability cards; "
            "bank-defense proposed 0 candidate(s); "
            "judge no_candidate the selected candidate none. "
            "Carry-forward: model=baseline_v1, threshold=thresholds_v1."
        ),
        model_vulnerability_card_paths=[],
        defensive_fix_paths=[],
    )


def _write_judge_report(outputs, judge_report_id, accepted=False):
    """Persist a stub judge_report.json under outputs/reports/."""
    rdir = outputs / "reports"
    rdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "judge_report_id": judge_report_id,
        "accepted_by_judge": accepted,
        "judge_notes": "...",
        "holdout_generalization": {},
        "run_id": "r", "round_id": 1, "defensive_fix_id": "fx",
        "baseline": {
            "model_miss_rate": 1.0,
            "recall_at_fixed_action_rate": 0.0,
            "false_positive_rate_at_fixed_action_rate": 0.05,
            "synthetic_loss_allowed": 1234.0,
            "challenge_rate": 0.1,
            "alert_rate": 0.1,
            "decline_rate": 0.0,
        },
        "fixed": {
            "model_miss_rate": 0.5,
            "recall_at_fixed_action_rate": 0.5,
            "false_positive_rate_at_fixed_action_rate": 0.05,
            "synthetic_loss_allowed": 600.0,
            "challenge_rate": 0.12,
            "alert_rate": 0.10,
            "decline_rate": 0.0,
        },
    }
    with (rdir / f"{judge_report_id}.json").open("w") as fh:
        json.dump(payload, fh, sort_keys=True)


@pytest.fixture
def replay_outputs(tmp_path):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    return outputs


# ---------------------------------------------------------------------------
# Top-level shape
# ---------------------------------------------------------------------------


def test_build_replay_payload_top_level_keys(replay_outputs):
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=i) for i in (1, 2, 3)]
    for r in rs:
        _write_judge_report(replay_outputs, r.judge_report_id)
    payload = build_replay_payload(
        _run_state(), rs, outputs_root=replay_outputs,
    )
    assert sorted(payload.keys()) == ["charts", "five_step_story", "run"]


def test_build_replay_payload_five_steps(replay_outputs):
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=i) for i in (1, 2, 3)]
    for r in rs:
        _write_judge_report(replay_outputs, r.judge_report_id)
    payload = build_replay_payload(
        _run_state(), rs, outputs_root=replay_outputs,
    )
    five = payload["five_step_story"]
    assert len(five) == 5
    assert [s["step_id"] for s in five] == [1, 2, 3, 4, 5]
    # Each step has a title + cards list.
    for step in five:
        assert isinstance(step["title"], str)
        assert step["title"]
        assert isinstance(step["cards"], list)


def test_build_replay_payload_step1_includes_judge(replay_outputs):
    """Step 1 surfaces deterministic-judge alongside red/blue agents."""
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=1)]
    _write_judge_report(replay_outputs, rs[0].judge_report_id)
    payload = build_replay_payload(
        _run_state(current_round=1, max_rounds=1), rs, outputs_root=replay_outputs,
    )
    step1_cards = payload["five_step_story"][0]["cards"]
    cats = {c.get("category") for c in step1_cards}
    assert "red_team" in cats
    assert "bank_defense" in cats
    assert "deterministic_judge" in cats


def test_build_replay_payload_step5_has_final_report(replay_outputs):
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=i) for i in (1, 2, 3)]
    for r in rs:
        _write_judge_report(replay_outputs, r.judge_report_id)
    payload = build_replay_payload(
        _run_state(), rs, outputs_root=replay_outputs,
    )
    step5_cards = payload["five_step_story"][4]["cards"]
    final = [c for c in step5_cards if c.get("category") == "final_report"]
    assert len(final) == 1
    assert "summary" in final[0]
    assert final[0]["safety_scan_passed"] is True


# ---------------------------------------------------------------------------
# RunDetail shape
# ---------------------------------------------------------------------------


def test_build_replay_payload_run_detail_shape(replay_outputs):
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=i) for i in (1, 2, 3)]
    for r in rs:
        _write_judge_report(replay_outputs, r.judge_report_id)
    payload = build_replay_payload(
        _run_state(), rs, outputs_root=replay_outputs,
    )
    run = payload["run"]
    expected = {
        "run_id", "seed", "demo_mode", "status", "current_round",
        "created_at_utc", "rounds", "latest_metrics",
    }
    assert expected.issubset(set(run))
    assert run["seed"] == 42
    assert run["status"] == "completed"
    assert len(run["rounds"]) == 3


# ---------------------------------------------------------------------------
# MetricSnapshot shape + kinds
# ---------------------------------------------------------------------------


METRIC_FIELDS = {
    "round_id", "round_label", "kind",
    "model_miss_rate", "recall_at_fixed_action_rate",
    "false_positive_rate_at_fixed_action_rate", "synthetic_loss_allowed",
    "challenge_rate", "alert_rate", "decline_rate",
}


def test_build_replay_payload_round_metrics_kinds(replay_outputs):
    """Round 0 = baseline; rounds 1+ = fixed (no ``interpolated``)."""
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=i) for i in (1, 2, 3)]
    for r in rs:
        _write_judge_report(replay_outputs, r.judge_report_id)
    payload = build_replay_payload(
        _run_state(), rs, outputs_root=replay_outputs,
    )
    snaps = payload["charts"]["round_metrics"]
    # 1 baseline + 3 fixed
    assert len(snaps) == 4
    assert snaps[0]["kind"] == "baseline"
    assert snaps[0]["round_id"] == 0
    for s in snaps[1:]:
        assert s["kind"] == "fixed"
    # No interpolated kind present.
    assert "interpolated" not in {s["kind"] for s in snaps}


def test_build_replay_payload_metric_field_names(replay_outputs):
    """Field names mirror ``app/web/lib/types.ts.MetricSnapshot``."""
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=1)]
    _write_judge_report(replay_outputs, rs[0].judge_report_id)
    payload = build_replay_payload(
        _run_state(current_round=1, max_rounds=1), rs, outputs_root=replay_outputs,
    )
    for s in payload["charts"]["round_metrics"]:
        assert set(s.keys()) == METRIC_FIELDS


def test_build_replay_payload_baseline_from_first_round_judge(replay_outputs):
    """Round-0 baseline snapshot draws from round 1's judge ``baseline``."""
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=1)]
    _write_judge_report(replay_outputs, rs[0].judge_report_id)
    payload = build_replay_payload(
        _run_state(current_round=1, max_rounds=1), rs, outputs_root=replay_outputs,
    )
    baseline_snap = payload["charts"]["round_metrics"][0]
    # Matches the values written into the stub judge report's "baseline" side.
    assert baseline_snap["model_miss_rate"] == 1.0
    assert baseline_snap["recall_at_fixed_action_rate"] == 0.0
    assert baseline_snap["synthetic_loss_allowed"] == 1234.0


def test_build_replay_payload_accepted_uses_fixed_metrics(replay_outputs):
    """Accepted round → snapshot derives from ``fixed`` side of judge report."""
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=1, accepted_fix_id="fix_round1_x")]
    _write_judge_report(
        replay_outputs, rs[0].judge_report_id, accepted=True,
    )
    payload = build_replay_payload(
        _run_state(current_round=1, max_rounds=1), rs, outputs_root=replay_outputs,
    )
    round1_snap = payload["charts"]["round_metrics"][1]
    assert round1_snap["model_miss_rate"] == 0.5
    assert round1_snap["recall_at_fixed_action_rate"] == 0.5


def test_build_replay_payload_rejected_uses_baseline_metrics(replay_outputs):
    """Rejected round → snapshot derives from ``baseline`` (carry-forward)."""
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=1, accepted_fix_id=None)]
    _write_judge_report(replay_outputs, rs[0].judge_report_id, accepted=False)
    payload = build_replay_payload(
        _run_state(current_round=1, max_rounds=1), rs, outputs_root=replay_outputs,
    )
    round1_snap = payload["charts"]["round_metrics"][1]
    assert round1_snap["model_miss_rate"] == 1.0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_persist_replay_payload_writes_under_demo_replays(replay_outputs):
    from atlas.ledger.replay import build_replay_payload, persist_replay_payload

    rs = [_round_state(round_id=1)]
    _write_judge_report(replay_outputs, rs[0].judge_report_id)
    payload = build_replay_payload(
        _run_state(current_round=1, max_rounds=1), rs, outputs_root=replay_outputs,
    )
    out = persist_replay_payload(
        payload, run_id="run_replay01", outputs_root=replay_outputs,
    )
    assert out == replay_outputs / "demo_replays" / "run_replay01.json"
    assert out.parent.name == "demo_replays"
    # Re-parses cleanly.
    with out.open() as fh:
        roundtrip = json.load(fh)
    assert sorted(roundtrip.keys()) == ["charts", "five_step_story", "run"]


def test_persist_replay_payload_byte_identical_on_rewrite(replay_outputs):
    from atlas.ledger.replay import build_replay_payload, persist_replay_payload

    rs = [_round_state(round_id=1)]
    _write_judge_report(replay_outputs, rs[0].judge_report_id)
    payload = build_replay_payload(
        _run_state(current_round=1, max_rounds=1), rs, outputs_root=replay_outputs,
    )
    p = persist_replay_payload(
        payload, run_id="run_replay01", outputs_root=replay_outputs,
    )
    bytes_a = p.read_bytes()
    persist_replay_payload(
        payload, run_id="run_replay01", outputs_root=replay_outputs,
    )
    bytes_b = p.read_bytes()
    assert bytes_a == bytes_b


# ---------------------------------------------------------------------------
# Step 2 environment cards: pulled from manifest counts.global
# ---------------------------------------------------------------------------


def test_build_replay_payload_step2_environment_uses_real_manifest(
    replay_outputs,
):
    """Step 2 cards come from ``data/synthetic/manifest.json:counts.global``."""
    from atlas.ledger.replay import build_replay_payload

    rs = [_round_state(round_id=1)]
    _write_judge_report(replay_outputs, rs[0].judge_report_id)
    payload = build_replay_payload(
        _run_state(current_round=1, max_rounds=1),
        rs,
        outputs_root=replay_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
    )
    step2_cards = payload["five_step_story"][1]["cards"]
    assert step2_cards  # non-empty
    cats = {c["category"] for c in step2_cards}
    assert cats == {"environment"}


# ---------------------------------------------------------------------------
# No-rounds edge case
# ---------------------------------------------------------------------------


def test_build_replay_payload_zero_rounds(replay_outputs):
    """Run with no rounds → empty round_metrics, no per-round cards."""
    from atlas.ledger.replay import build_replay_payload

    payload = build_replay_payload(
        _run_state(current_round=0, max_rounds=3), [],
        outputs_root=replay_outputs,
    )
    assert payload["charts"]["round_metrics"] == []
    # Steps 3/4/5 still rendered with empty card lists.
    assert len(payload["five_step_story"]) == 5
    assert payload["run"]["latest_metrics"] is None
