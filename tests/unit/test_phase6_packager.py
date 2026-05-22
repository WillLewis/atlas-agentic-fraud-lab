"""Phase 6 ModelVulnerabilityCard packager tests.

Verify card shape matches OpenAPI, summary strings + cohort keys are
public-safe (pass scripts/safety_scan.py rules), recommended fix types
come from the closed enumeration, and packaging is deterministic.
"""
from __future__ import annotations

import random
from dataclasses import asdict
from pathlib import Path

import pytest

from atlas.red_team.fraud_scenario_agent import run_search, reset_caches
from atlas.red_team.model_vulnerability_packager import (
    FAMILY_SUMMARY_TEMPLATES,
    RECOMMENDED_FIX_TYPES_BY_FAMILY,
    SAFE_COHORT_FEATURES,
    ModelVulnerabilityCard,
    package_cards,
)
from atlas.red_team.mutations import ALLOWED_FAMILY_IDS

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def search_result(trained_baseline_dir, monkeypatch):
    """One round-1 search result we can package + assert against."""
    import atlas.judge.evaluate as evaluate_mod
    import atlas.model.scorer as scorer_mod
    monkeypatch.setattr(scorer_mod, "DEFAULT_OUTPUT_DIR", trained_baseline_dir)
    monkeypatch.setattr(
        evaluate_mod, "BASELINE_MODELS_ROOT", trained_baseline_dir.parent
    )
    reset_caches()
    result = run_search(
        run_id="run_test", round_id=1,
        search_methods=["random", "evolutionary", "graph_probe"],
        max_score_queries=1200,
        outputs_root=trained_baseline_dir.parent.parent,
    )
    yield result
    reset_caches()


# ---------------------------------------------------------------------------
# RECOMMENDED_FIX_TYPES_BY_FAMILY canonical map
# ---------------------------------------------------------------------------


def test_recommended_fix_types_covers_every_family():
    assert set(RECOMMENDED_FIX_TYPES_BY_FAMILY) == set(ALLOWED_FAMILY_IDS)


def test_recommended_fix_types_uses_closed_enum():
    """Only Phase 7 fix-family identifiers may appear."""
    allowed = {"feature_fix", "policy_fix", "model_calibration_fix"}
    for types in RECOMMENDED_FIX_TYPES_BY_FAMILY.values():
        assert set(types).issubset(allowed)


def test_family_summary_templates_cover_every_family():
    assert set(FAMILY_SUMMARY_TEMPLATES) == set(ALLOWED_FAMILY_IDS)


def test_safe_cohort_features_are_phase3_features():
    """All five must be names from the Bible §11.3 / Phase 3 feature set."""
    expected_phase3_features = {
        "entity_graph_risk_score", "shared_recipient_degree",
        "shared_device_degree", "cash_movement_velocity_score",
        "recipient_tenure_days",
    }
    assert set(SAFE_COHORT_FEATURES) == expected_phase3_features


# ---------------------------------------------------------------------------
# Card shape — matches OpenAPI ModelVulnerabilityCard
# ---------------------------------------------------------------------------


def test_card_required_fields_present(search_result):
    cards = package_cards(
        candidates=search_result.candidates, round_id=1,
        random_baseline=search_result.by_method.get("random"),
    )
    assert cards, "no cards generated; expected at least one"
    required = {
        "model_vulnerability_id", "round_id", "family_id", "summary",
        "model_miss_rate",
    }
    for card in cards:
        d = asdict(card)
        assert required.issubset(d)


def test_card_optional_fields_have_correct_types(search_result):
    cards = package_cards(
        candidates=search_result.candidates, round_id=1,
        random_baseline=search_result.by_method.get("random"),
    )
    for card in cards:
        assert isinstance(card.valid_high_risk_events_tested, int)
        assert isinstance(card.accepted_high_risk_events, int)
        assert isinstance(card.model_miss_rate, float)
        assert isinstance(card.estimated_synthetic_loss_allowed, float)
        assert card.affected_decision_action in {"accept", "challenge", "alert", "decline"}
        assert isinstance(card.safe_cohort_definition, dict)
        assert isinstance(card.recommended_defensive_fix_types, tuple)


def test_card_id_format(search_result):
    cards = package_cards(
        candidates=search_result.candidates, round_id=1,
        random_baseline=search_result.by_method.get("random"),
    )
    for card in cards:
        assert card.model_vulnerability_id == f"mv_round1_{card.family_id}"
        assert card.model_vulnerability_id.startswith("mv_")


def test_card_recommended_fix_types_from_closed_map(search_result):
    cards = package_cards(
        candidates=search_result.candidates, round_id=1,
        random_baseline=search_result.by_method.get("random"),
    )
    for card in cards:
        assert (
            tuple(card.recommended_defensive_fix_types)
            == RECOMMENDED_FIX_TYPES_BY_FAMILY[card.family_id]
        )


def test_card_summary_from_template_map(search_result):
    cards = package_cards(
        candidates=search_result.candidates, round_id=1,
        random_baseline=search_result.by_method.get("random"),
    )
    for card in cards:
        assert card.summary == FAMILY_SUMMARY_TEMPLATES[card.family_id]


def test_card_cohort_keys(search_result):
    cards = package_cards(
        candidates=search_result.candidates, round_id=1,
        random_baseline=search_result.by_method.get("random"),
    )
    for card in cards:
        cohort_feature_keys = set(card.safe_cohort_definition.keys()) - {"cohort_size"}
        assert cohort_feature_keys == set(SAFE_COHORT_FEATURES)


# ---------------------------------------------------------------------------
# Public-safe — summaries pass scripts/safety_scan.py
# ---------------------------------------------------------------------------


def test_summary_strings_pass_safety_scan():
    """Run the production safety scanner directly on every summary."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from safety_scan import compile_rules, load_config

    cfg = load_config(REPO_ROOT / "config" / "safety.yaml")
    rules = compile_rules(cfg)
    for family_id, summary in FAMILY_SUMMARY_TEMPLATES.items():
        for rule in rules:
            for pattern in rule.patterns:
                m = pattern.search(summary)
                assert m is None, (
                    f"summary for {family_id!r} matches "
                    f"{rule.id} ({rule.severity}): {m.group(0)!r}"
                )


# ---------------------------------------------------------------------------
# Packager behavior
# ---------------------------------------------------------------------------


def test_package_cards_empty_input_returns_empty_list():
    assert package_cards(candidates=[], round_id=1) == []


def test_package_cards_skips_families_with_no_accepted_high_risk():
    """If a family found valid high-risk but model didn't accept any,
    it doesn't generate a card."""
    from atlas.red_team.random_search import CandidateResult
    fv = {
        "event_id": "tx_x", "customer_id": "cust_x",
        "login_count_72h": 0, "login_count_30d": 0, "login_velocity_ratio": 0.0,
        "challenge_count_72h": 0, "challenge_pass_ratio_30d": 0.0,
        "password_recovery_count_72h": 0, "device_count_72h": 1,
        "current_device_tenure_days": 100, "geo_consistency_flag": 1,
        "transfer_count_72h": 0, "recipient_tenure_days": 100,
        "shared_device_degree": 0, "shared_recipient_degree": 0,
        "entity_graph_risk_score": 0.0, "cash_movement_velocity_score": 0.0,
    }
    # High-risk but the policy challenged it (not accepted)
    cands = [
        CandidateResult(
            candidate_id="cand_aaaaaaaa", family_id="low_velocity_high_graph_risk",
            target_event_id="tx_001", score=0.85, decision_action="challenge",
            synthetic_truth_label="high_risk_synthetic_activity",
            amount_bucket="amount_bucket_05", feature_vector=fv,
        )
    ]
    cards = package_cards(candidates=cands, round_id=1)
    assert cards == []


def test_package_cards_deterministic(search_result):
    """Same input → identical card list."""
    a = package_cards(
        candidates=search_result.candidates, round_id=1,
        random_baseline=search_result.by_method.get("random"),
    )
    b = package_cards(
        candidates=search_result.candidates, round_id=1,
        random_baseline=search_result.by_method.get("random"),
    )
    assert a == b


def test_no_random_baseline_yields_none_lift(search_result):
    cards = package_cards(
        candidates=search_result.candidates, round_id=1, random_baseline=None,
    )
    assert all(c.miss_rate_lift_vs_random is None for c in cards)


def test_card_floats_rounded_to_4dp(search_result):
    cards = package_cards(
        candidates=search_result.candidates, round_id=1,
        random_baseline=search_result.by_method.get("random"),
    )
    for card in cards:
        for v in (card.model_miss_rate, card.estimated_synthetic_loss_allowed):
            assert round(v, 4) == v
        if card.miss_rate_lift_vs_random is not None:
            assert round(card.miss_rate_lift_vs_random, 4) == card.miss_rate_lift_vs_random
