"""Phase 7 manifest module tests.

Round-trip persistence, ID helpers, deterministic JSON, error paths.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atlas.blue_team.manifest import (
    DefensiveFixManifest,
    MissingManifestError,
    MissingVulnerabilityError,
    ModelVulnerabilityRecord,
    card_to_record,
    load_fix_manifest,
    load_vulnerability_record,
    make_defensive_fix_id,
    persist_cards_as_records,
    persist_fix_manifest,
    persist_vulnerability_record,
)


@pytest.fixture
def outputs(tmp_path) -> Path:
    return tmp_path / "outputs"


# ---------------------------------------------------------------------------
# make_defensive_fix_id
# ---------------------------------------------------------------------------


def test_make_defensive_fix_id_format():
    fid = make_defensive_fix_id(1, "mv_round1_low_velocity_high_graph_risk", "policy_fix")
    assert fid == "fix_round1_low_velocity_high_graph_risk_policy_fix"


def test_make_defensive_fix_id_deterministic():
    a = make_defensive_fix_id(2, "mv_round2_label_noise_mislearned", "model_calibration_fix")
    b = make_defensive_fix_id(2, "mv_round2_label_noise_mislearned", "model_calibration_fix")
    assert a == b


def test_make_defensive_fix_id_strips_round_prefix():
    """If vulnerability_id has the matching ``mv_round{N}_`` prefix, the
    helper strips it for readability."""
    fid = make_defensive_fix_id(3, "mv_round3_overfit_fix_failure", "policy_fix")
    assert "mv_round3_" not in fid
    assert "overfit_fix_failure" in fid


def test_make_defensive_fix_id_rejects_unknown_fix_type():
    with pytest.raises(ValueError, match="unknown fix_type"):
        make_defensive_fix_id(1, "mv_round1_x", "invalid_fix")


# ---------------------------------------------------------------------------
# ModelVulnerabilityRecord round-trip
# ---------------------------------------------------------------------------


def _sample_record() -> ModelVulnerabilityRecord:
    return ModelVulnerabilityRecord(
        model_vulnerability_id="mv_round1_low_velocity_high_graph_risk",
        run_id="run_test", round_id=1,
        family_id="low_velocity_high_graph_risk",
        found_adaptive_set_event_ids=["tx_000001", "tx_000002"],
        model_miss_rate=0.95,
        recommended_defensive_fix_types=["feature_fix", "policy_fix"],
        summary="Synthetic high-risk events ...",
    )


def test_vulnerability_record_round_trip(outputs):
    record = _sample_record()
    persist_vulnerability_record(record, outputs_root=outputs)
    loaded = load_vulnerability_record(
        record["model_vulnerability_id"], outputs_root=outputs
    )
    assert loaded == record


def test_vulnerability_record_byte_identical_on_rewrite(outputs):
    record = _sample_record()
    p1 = persist_vulnerability_record(record, outputs_root=outputs)
    bytes_a = p1.read_bytes()
    p2 = persist_vulnerability_record(record, outputs_root=outputs)
    bytes_b = p2.read_bytes()
    assert bytes_a == bytes_b


def test_missing_vulnerability_raises(outputs):
    with pytest.raises(MissingVulnerabilityError, match="not found"):
        load_vulnerability_record("mv_does_not_exist", outputs_root=outputs)


def test_vulnerability_record_lands_under_gitignored_subdir(outputs):
    record = _sample_record()
    p = persist_vulnerability_record(record, outputs_root=outputs)
    assert p.parent.name == "model_vulnerabilities"
    # The parent.parent is the outputs_root we passed.
    assert p.parent.parent == outputs


# ---------------------------------------------------------------------------
# card_to_record + persist_cards_as_records
# ---------------------------------------------------------------------------


def _sample_card():
    from atlas.red_team.model_vulnerability_packager import ModelVulnerabilityCard
    return ModelVulnerabilityCard(
        model_vulnerability_id="mv_round1_score_boundary_cluster",
        round_id=1,
        family_id="score_boundary_cluster",
        summary="Synthetic high-risk ...",
        valid_high_risk_events_tested=12,
        accepted_high_risk_events=12,
        model_miss_rate=1.0,
        miss_rate_lift_vs_random=1.0,
        estimated_synthetic_loss_allowed=1500000.0,
        affected_decision_action="accept",
        safe_cohort_definition={"cohort_size": 12},
        recommended_defensive_fix_types=("policy_fix",),
    )


def test_card_to_record_sorts_event_ids():
    card = _sample_card()
    record = card_to_record(
        card, run_id="run_test",
        found_adaptive_set_event_ids=["tx_000005", "tx_000001", "tx_000003"],
    )
    # Sorted for byte-stability
    assert record["found_adaptive_set_event_ids"] == ["tx_000001", "tx_000003", "tx_000005"]
    assert record["recommended_defensive_fix_types"] == ["policy_fix"]


def test_persist_cards_as_records_bulk(outputs):
    card = _sample_card()
    paths = persist_cards_as_records(
        [card], run_id="run_test",
        found_adaptive_set_event_ids=["tx_000001"],
        outputs_root=outputs,
    )
    assert len(paths) == 1
    record = load_vulnerability_record(
        "mv_round1_score_boundary_cluster", outputs_root=outputs
    )
    assert record["family_id"] == "score_boundary_cluster"


# ---------------------------------------------------------------------------
# DefensiveFixManifest round-trip
# ---------------------------------------------------------------------------


def _sample_manifest() -> DefensiveFixManifest:
    return DefensiveFixManifest(
        defensive_fix_id="fix_round1_score_boundary_cluster_policy_fix",
        run_id="run_test", round_id=1,
        vulnerability_id="mv_round1_score_boundary_cluster",
        fix_type="policy_fix",
        proposed_threshold_overrides={"challenge_score_threshold": 0.69},
        expected_rate_limit_claim={"max_false_positive_rate_increase": 0.001},
    )


def test_fix_manifest_round_trip(outputs):
    m = _sample_manifest()
    persist_fix_manifest(m, outputs_root=outputs)
    loaded = load_fix_manifest(m.defensive_fix_id, outputs_root=outputs)
    assert loaded == m


def test_fix_manifest_byte_identical(outputs):
    m = _sample_manifest()
    p1 = persist_fix_manifest(m, outputs_root=outputs)
    bytes_a = p1.read_bytes()
    p2 = persist_fix_manifest(m, outputs_root=outputs)
    bytes_b = p2.read_bytes()
    assert bytes_a == bytes_b


def test_missing_manifest_raises(outputs):
    with pytest.raises(MissingManifestError, match="not found"):
        load_fix_manifest("fix_does_not_exist", outputs_root=outputs)


def test_fix_manifest_lands_under_gitignored_subdir(outputs):
    m = _sample_manifest()
    p = persist_fix_manifest(m, outputs_root=outputs)
    assert p.parent.name == "defensive_fixes"


# ---------------------------------------------------------------------------
# DefensiveFixManifest carries structured params per family
# ---------------------------------------------------------------------------


def test_policy_manifest_carries_threshold_overrides(outputs):
    m = DefensiveFixManifest(
        defensive_fix_id="fix_p", run_id="r", round_id=1,
        vulnerability_id="x", fix_type="policy_fix",
        proposed_threshold_overrides={"challenge_score_threshold": 0.69},
    )
    persist_fix_manifest(m, outputs_root=outputs)
    loaded = load_fix_manifest("fix_p", outputs_root=outputs)
    assert loaded.proposed_threshold_overrides == {"challenge_score_threshold": 0.69}


def test_calibration_manifest_carries_seed_and_l2(outputs):
    m = DefensiveFixManifest(
        defensive_fix_id="fix_c", run_id="r", round_id=1,
        vulnerability_id="x", fix_type="model_calibration_fix",
        proposed_training_seed=1001, proposed_l2_strength=0.5,
    )
    persist_fix_manifest(m, outputs_root=outputs)
    loaded = load_fix_manifest("fix_c", outputs_root=outputs)
    assert loaded.proposed_training_seed == 1001
    assert loaded.proposed_l2_strength == 0.5


def test_feature_manifest_carries_transforms(outputs):
    m = DefensiveFixManifest(
        defensive_fix_id="fix_f", run_id="r", round_id=1,
        vulnerability_id="x", fix_type="feature_fix",
        proposed_feature_transforms=("boost_graph_risk",),
    )
    persist_fix_manifest(m, outputs_root=outputs)
    loaded = load_fix_manifest("fix_f", outputs_root=outputs)
    assert loaded.proposed_feature_transforms == ("boost_graph_risk",)
