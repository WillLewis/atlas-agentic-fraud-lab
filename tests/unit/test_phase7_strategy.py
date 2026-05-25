"""Phase 7 strategy_agent tests.

Three-way intersection logic, deterministic candidate emission,
no-unsupported-fix-leak, per-family manifest contents.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.api.schemas.fix import ALLOWED_FIX_TYPES
from atlas.blue_team.manifest import (
    MissingVulnerabilityError,
    ModelVulnerabilityRecord,
    load_fix_manifest,
    make_defensive_fix_id,
    persist_vulnerability_record,
)
from atlas.blue_team.strategy_agent import (
    DefensiveFixCandidate,
    DESCRIPTION_TEMPLATES,
    EXPECTED_BENEFIT_TEMPLATE,
    propose_fixes,
    reset_caches,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _clear_caches():
    reset_caches()
    yield
    reset_caches()


@pytest.fixture
def outputs(tmp_path) -> Path:
    out = tmp_path / "outputs"
    return out


def _persist(record_kwargs, outputs):
    persist_vulnerability_record(
        ModelVulnerabilityRecord(**record_kwargs),
        outputs_root=outputs,
    )


# ---------------------------------------------------------------------------
# 3-way intersection
# ---------------------------------------------------------------------------


def test_intersection_returns_candidates_per_surviving_pair(outputs):
    """low_velocity_high_graph_risk recommends [feature_fix, policy_fix];
    round 1 allows [feature_fix, policy_fix]; request asks for both → 2."""
    _persist({
        "model_vulnerability_id": "mv_round1_low_velocity_high_graph_risk",
        "run_id": "r", "round_id": 1,
        "family_id": "low_velocity_high_graph_risk",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["feature_fix", "policy_fix"],
        "summary": "...",
    }, outputs)
    cands = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_low_velocity_high_graph_risk"],
        allowed_fix_types=["feature_fix", "policy_fix", "model_calibration_fix"],
        outputs_root=outputs,
    )
    fix_types = sorted(c.fix_type for c in cands)
    assert fix_types == ["feature_fix", "policy_fix"]


def test_round_config_excludes_calibration_in_round_1(outputs):
    """Round 1's defensive_fix_types_allowed is [feature_fix, policy_fix].
    Even if request includes model_calibration_fix, intersection drops it."""
    _persist({
        "model_vulnerability_id": "mv_round1_label_noise_mislearned",
        "run_id": "r", "round_id": 1,
        "family_id": "label_noise_mislearned",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["model_calibration_fix"],
        "summary": "...",
    }, outputs)
    cands = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_label_noise_mislearned"],
        allowed_fix_types=["model_calibration_fix"],
        outputs_root=outputs,
    )
    # Empty intersection (round 1 doesn't allow calibration) → 0 candidates
    assert cands == []


def test_card_recommendation_controls_emitted_fix_types(outputs):
    """The card's closed-enum recommendations control emitted fix types."""
    _persist({
        "model_vulnerability_id": "mv_round1_score_boundary_cluster",
        "run_id": "r", "round_id": 1,
        "family_id": "score_boundary_cluster",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["feature_fix", "policy_fix"],
        "summary": "...",
    }, outputs)
    cands = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_score_boundary_cluster"],
        allowed_fix_types=["feature_fix", "policy_fix"],
        outputs_root=outputs,
    )
    assert [c.fix_type for c in cands] == ["feature_fix", "policy_fix"]


def test_empty_intersection_yields_empty_result_not_error(outputs):
    _persist({
        "model_vulnerability_id": "mv_round1_low_velocity_high_graph_risk",
        "run_id": "r", "round_id": 1,
        "family_id": "low_velocity_high_graph_risk",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["feature_fix", "policy_fix"],
        "summary": "...",
    }, outputs)
    # Round 1 allows [feature_fix, policy_fix]; request asks for [model_calibration_fix]
    # → empty intersection, NOT an error.
    cands = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_low_velocity_high_graph_risk"],
        allowed_fix_types=["model_calibration_fix"],
        outputs_root=outputs,
    )
    assert cands == []


# ---------------------------------------------------------------------------
# No unsupported fix family leaks
# ---------------------------------------------------------------------------


def test_every_emitted_fix_type_in_canonical_enum(outputs):
    """All emitted candidates must have fix_type ∈ ALLOWED_FIX_TYPES."""
    for fam, fixes in [
        ("low_velocity_high_graph_risk", ["feature_fix", "policy_fix"]),
        ("score_boundary_cluster", ["feature_fix", "policy_fix"]),
        ("activity_channel_shift", ["feature_fix"]),
    ]:
        vuln_id = f"mv_round1_{fam}"
        _persist({
            "model_vulnerability_id": vuln_id, "run_id": "r", "round_id": 1,
            "family_id": fam, "found_adaptive_set_event_ids": [],
            "model_miss_rate": 1.0,
            "recommended_defensive_fix_types": fixes, "summary": "...",
        }, outputs)
    cands = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=[
            "mv_round1_low_velocity_high_graph_risk",
            "mv_round1_score_boundary_cluster",
            "mv_round1_activity_channel_shift",
        ],
        allowed_fix_types=list(ALLOWED_FIX_TYPES),
        outputs_root=outputs,
    )
    for c in cands:
        assert c.fix_type in ALLOWED_FIX_TYPES


def test_propose_rejects_unknown_fix_type_in_request(outputs):
    _persist({
        "model_vulnerability_id": "mv_round1_score_boundary_cluster",
        "run_id": "r", "round_id": 1,
        "family_id": "score_boundary_cluster",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["policy_fix"],
        "summary": "...",
    }, outputs)
    with pytest.raises(ValueError, match="unknown fix_type"):
        propose_fixes(
            run_id="r", round_id=1,
            model_vulnerability_ids=["mv_round1_score_boundary_cluster"],
            allowed_fix_types=["unsupported_fix"],
            outputs_root=outputs,
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_propose_deterministic_under_input_reordering(outputs):
    for fam in ("low_velocity_high_graph_risk", "score_boundary_cluster"):
        _persist({
            "model_vulnerability_id": f"mv_round1_{fam}",
            "run_id": "r", "round_id": 1, "family_id": fam,
            "found_adaptive_set_event_ids": [], "model_miss_rate": 1.0,
            "recommended_defensive_fix_types": ["policy_fix"]
                if fam == "score_boundary_cluster" else ["feature_fix", "policy_fix"],
            "summary": "...",
        }, outputs)
    a = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_low_velocity_high_graph_risk", "mv_round1_score_boundary_cluster"],
        allowed_fix_types=["policy_fix", "feature_fix"],
        outputs_root=outputs,
    )
    b = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_score_boundary_cluster", "mv_round1_low_velocity_high_graph_risk"],
        allowed_fix_types=["feature_fix", "policy_fix"],
        outputs_root=outputs,
    )
    assert a == b


# ---------------------------------------------------------------------------
# Per-family manifest content
# ---------------------------------------------------------------------------


def test_policy_manifest_has_threshold_overrides(outputs):
    _persist({
        "model_vulnerability_id": "mv_round1_score_boundary_cluster",
        "run_id": "r", "round_id": 1,
        "family_id": "score_boundary_cluster",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["policy_fix"],
        "summary": "...",
    }, outputs)
    cands = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_score_boundary_cluster"],
        allowed_fix_types=["policy_fix"],
        outputs_root=outputs,
    )
    manifest = load_fix_manifest(cands[0].defensive_fix_id, outputs_root=outputs)
    assert manifest.fix_type == "policy_fix"
    assert manifest.proposed_threshold_overrides
    assert "challenge_score_threshold" in manifest.proposed_threshold_overrides


def test_policy_manifest_uses_current_threshold_version(outputs):
    threshold_dir = outputs / "decision_thresholds"
    threshold_dir.mkdir(parents=True)
    with (REPO_ROOT / "config" / "decision_thresholds.yaml").open() as fh:
        doc = yaml.safe_load(fh)
    doc["decision_threshold_version"] = "threshold_round1_accepted"
    doc["decision_thresholds"]["challenge_score_threshold"] = 0.30
    with (threshold_dir / "threshold_round1_accepted.yaml").open("w") as fh:
        yaml.safe_dump(doc, fh, sort_keys=True)

    _persist({
        "model_vulnerability_id": "mv_round1_score_boundary_cluster",
        "run_id": "r", "round_id": 1,
        "family_id": "score_boundary_cluster",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["policy_fix"],
        "summary": "...",
    }, outputs)
    cands = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_score_boundary_cluster"],
        allowed_fix_types=["policy_fix"],
        outputs_root=outputs,
        current_threshold_version="threshold_round1_accepted",
    )
    manifest = load_fix_manifest(cands[0].defensive_fix_id, outputs_root=outputs)
    assert manifest.proposed_threshold_overrides == {
        "challenge_score_threshold": 0.285,
    }


def test_calibration_manifest_has_seed_and_l2(outputs):
    _persist({
        "model_vulnerability_id": "mv_round2_label_noise_mislearned",
        "run_id": "r", "round_id": 2,
        "family_id": "label_noise_mislearned",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["model_calibration_fix"],
        "summary": "...",
    }, outputs)
    cands = propose_fixes(
        run_id="r", round_id=2,
        model_vulnerability_ids=["mv_round2_label_noise_mislearned"],
        allowed_fix_types=["model_calibration_fix"],
        outputs_root=outputs,
    )
    manifest = load_fix_manifest(cands[0].defensive_fix_id, outputs_root=outputs)
    assert manifest.fix_type == "model_calibration_fix"
    assert manifest.proposed_training_seed is not None
    assert manifest.proposed_l2_strength is not None


def test_feature_manifest_has_transforms(outputs):
    _persist({
        "model_vulnerability_id": "mv_round1_low_velocity_high_graph_risk",
        "run_id": "r", "round_id": 1,
        "family_id": "low_velocity_high_graph_risk",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["feature_fix"],
        "summary": "...",
    }, outputs)
    cands = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_low_velocity_high_graph_risk"],
        allowed_fix_types=["feature_fix"],
        outputs_root=outputs,
    )
    manifest = load_fix_manifest(cands[0].defensive_fix_id, outputs_root=outputs)
    assert manifest.fix_type == "feature_fix"
    assert manifest.proposed_feature_transforms


# ---------------------------------------------------------------------------
# Description + benefit text closed-enum
# ---------------------------------------------------------------------------


def test_description_text_from_template(outputs):
    _persist({
        "model_vulnerability_id": "mv_round1_low_velocity_high_graph_risk",
        "run_id": "r", "round_id": 1,
        "family_id": "low_velocity_high_graph_risk",
        "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["policy_fix"],
        "summary": "...",
    }, outputs)
    cands = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_low_velocity_high_graph_risk"],
        allowed_fix_types=["policy_fix"], outputs_root=outputs,
    )
    cand = cands[0]
    assert cand.description == DESCRIPTION_TEMPLATES[
        ("low_velocity_high_graph_risk", "policy_fix")
    ]
    assert cand.expected_benefit == EXPECTED_BENEFIT_TEMPLATE.format(
        family_id="low_velocity_high_graph_risk"
    )


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_unknown_round_id_raises(outputs):
    _persist({
        "model_vulnerability_id": "mv_round1_low_velocity_high_graph_risk",
        "run_id": "r", "round_id": 1,
        "family_id": "low_velocity_high_graph_risk",
        "found_adaptive_set_event_ids": [], "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["policy_fix"], "summary": "...",
    }, outputs)
    with pytest.raises(ValueError, match="unknown round_id"):
        propose_fixes(
            run_id="r", round_id=999,
            model_vulnerability_ids=["mv_round1_low_velocity_high_graph_risk"],
            allowed_fix_types=["policy_fix"],
            outputs_root=outputs,
        )


def test_missing_vulnerability_raises(outputs):
    with pytest.raises(MissingVulnerabilityError):
        propose_fixes(
            run_id="r", round_id=1,
            model_vulnerability_ids=["mv_does_not_exist"],
            allowed_fix_types=["policy_fix"],
            outputs_root=outputs,
        )


def test_candidate_id_format(outputs):
    _persist({
        "model_vulnerability_id": "mv_round1_score_boundary_cluster",
        "run_id": "r", "round_id": 1,
        "family_id": "score_boundary_cluster",
        "found_adaptive_set_event_ids": [], "model_miss_rate": 1.0,
        "recommended_defensive_fix_types": ["policy_fix"], "summary": "...",
    }, outputs)
    cands = propose_fixes(
        run_id="r", round_id=1,
        model_vulnerability_ids=["mv_round1_score_boundary_cluster"],
        allowed_fix_types=["policy_fix"],
        outputs_root=outputs,
    )
    assert cands[0].defensive_fix_id == "fix_round1_score_boundary_cluster_policy_fix"
