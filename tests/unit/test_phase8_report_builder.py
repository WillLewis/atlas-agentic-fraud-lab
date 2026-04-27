"""Phase 8 report_builder tests.

Closed-enum transcript templates + final-report summary + in-process
safety_scan rules. The plan calls out: clean templates pass, banned
phrases trip ``safety_scan_passed=False``.
"""
from __future__ import annotations

import pytest

from atlas.ledger.report_builder import (
    ROUND_LABELS,
    build_final_report_summary,
    build_round_transcript_summary,
    reset_caches,
    safety_scan_text,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    reset_caches()
    yield
    reset_caches()


# ---------------------------------------------------------------------------
# Round transcript: closed-enum verdicts + clean safety scan
# ---------------------------------------------------------------------------


def test_round_summary_accepted_verdict():
    text, ok = build_round_transcript_summary(
        round_id=1, n_cards=3, n_fixes=2,
        selected_fix_id="fix_round1_x",
        accepted_fix_id="fix_round1_x",
        model_version_after="model_round1_accepted",
        threshold_version_after="threshold_round1_accepted",
    )
    assert "accepted" in text
    assert "Round 1" in text
    assert "model=model_round1_accepted" in text
    assert ok is True


def test_round_summary_rejected_verdict():
    text, ok = build_round_transcript_summary(
        round_id=2, n_cards=3, n_fixes=2,
        selected_fix_id="fix_round2_y",
        accepted_fix_id=None,
        model_version_after="baseline_v1",
        threshold_version_after="thresholds_v1",
    )
    assert "rejected" in text
    assert "fix_round2_y" in text
    assert ok is True


def test_round_summary_no_candidate_verdict():
    text, ok = build_round_transcript_summary(
        round_id=3, n_cards=0, n_fixes=0,
        selected_fix_id=None, accepted_fix_id=None,
        model_version_after="baseline_v1",
        threshold_version_after="thresholds_v1",
    )
    assert "no_candidate" in text
    assert "none" in text
    assert ok is True


def test_round_summary_byte_stable_for_same_inputs():
    """Closed-enum template is deterministic."""
    a, _ = build_round_transcript_summary(
        round_id=1, n_cards=3, n_fixes=2,
        selected_fix_id="fix_x", accepted_fix_id="fix_x",
        model_version_after="m1", threshold_version_after="t1",
    )
    b, _ = build_round_transcript_summary(
        round_id=1, n_cards=3, n_fixes=2,
        selected_fix_id="fix_x", accepted_fix_id="fix_x",
        model_version_after="m1", threshold_version_after="t1",
    )
    assert a == b


# ---------------------------------------------------------------------------
# Final-report summary
# ---------------------------------------------------------------------------


def test_final_report_summary_three_round_trend():
    text, ok = build_final_report_summary(
        run_id="run_test01", total_rounds=3, accepted_count=2,
        miss_rate_trend=[1.0, 0.5, 0.3],
        final_model_version="model_round3_accepted",
        final_threshold_version="threshold_round3_accepted",
    )
    assert "run_test01" in text
    assert "3 rounds" in text
    assert "2 accepted" in text
    # Trend rendered with fixed 4-digit precision arrow chain.
    assert "1.0000 → 0.5000 → 0.3000" in text
    assert ok is True


def test_final_report_summary_no_rounds():
    text, ok = build_final_report_summary(
        run_id="run_empty", total_rounds=0, accepted_count=0,
        miss_rate_trend=[],
        final_model_version="baseline_v1",
        final_threshold_version="thresholds_v1",
    )
    assert "(no rounds)" in text
    assert ok is True


# ---------------------------------------------------------------------------
# Safety scan flow
# ---------------------------------------------------------------------------


def test_safety_scan_text_empty_passes():
    assert safety_scan_text("") is True


def test_safety_scan_text_clean_template_passes():
    text, _ = build_round_transcript_summary(
        round_id=1, n_cards=3, n_fixes=2,
        selected_fix_id="fix_x", accepted_fix_id=None,
        model_version_after="baseline_v1",
        threshold_version_after="thresholds_v1",
    )
    assert safety_scan_text(text) is True


def test_safety_scan_text_banned_phrase_flags_false():
    """Regression guard — if a banned phrase ever leaks into a template,
    ``safety_scan_passed`` flips to False so the round_state surfaces it.
    """
    # Use a real-institution-name pattern from config/safety.yaml; if any
    # template ever rendered this, it would (and should) trip safety.
    text = "Round 1: blind spot exposed in jpmorgan-style routing."
    assert safety_scan_text(text) is False


# ---------------------------------------------------------------------------
# Round labels stable
# ---------------------------------------------------------------------------


def test_round_labels_stable():
    assert ROUND_LABELS[0] == "Baseline"
    assert ROUND_LABELS[1] == "Round 1"
    assert ROUND_LABELS[3] == "Round 3"
