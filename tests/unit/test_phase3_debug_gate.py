"""Debug-only direct-feature-mutation gate tests.

Bible §18 Phase 3 acceptance criterion:
  "Block direct feature mutation unless DEBUG_DIRECT_FEATURE_MUTATION=true."
"""
from __future__ import annotations

import pytest

from atlas.synthetic.features import (
    DEBUG_MUTATION_ENABLED_VALUE,
    DEBUG_MUTATION_ENV_VAR,
    DirectFeatureMutationDisabledError,
    apply_direct_feature_mutation,
    is_direct_feature_mutation_enabled,
)


# --- helpers ---------------------------------------------------------------


def _sample_feature(features_global):
    """Pick a fixture-derived feature vector with a non-zero login_count_30d
    so divide-by-zero edge cases don't interfere with override math."""
    for fv in features_global:
        if fv["login_count_30d"] > 0:
            return dict(fv)
    return dict(features_global[0])


# --- gate behavior ---------------------------------------------------------


def test_disabled_by_default(monkeypatch, features_global):
    """Without the env var, calls must raise."""
    monkeypatch.delenv(DEBUG_MUTATION_ENV_VAR, raising=False)
    assert is_direct_feature_mutation_enabled() is False

    fv = _sample_feature(features_global)
    with pytest.raises(DirectFeatureMutationDisabledError):
        apply_direct_feature_mutation(fv, {"login_count_72h": 99})


def test_enabled_with_env_var_true(monkeypatch, features_global):
    monkeypatch.setenv(DEBUG_MUTATION_ENV_VAR, DEBUG_MUTATION_ENABLED_VALUE)
    assert is_direct_feature_mutation_enabled() is True

    fv = _sample_feature(features_global)
    result = apply_direct_feature_mutation(fv, {"login_count_72h": 99})
    assert result["login_count_72h"] == 99


def test_returns_new_record_does_not_mutate_original(monkeypatch, features_global):
    monkeypatch.setenv(DEBUG_MUTATION_ENV_VAR, DEBUG_MUTATION_ENABLED_VALUE)
    fv = _sample_feature(features_global)
    original_value = fv["login_count_72h"]
    result = apply_direct_feature_mutation(fv, {"login_count_72h": 99})
    assert result["login_count_72h"] == 99
    assert fv["login_count_72h"] == original_value, (
        "original feature vector must not be mutated in-place"
    )


def test_multiple_overrides_applied(monkeypatch, features_global):
    monkeypatch.setenv(DEBUG_MUTATION_ENV_VAR, DEBUG_MUTATION_ENABLED_VALUE)
    fv = _sample_feature(features_global)
    result = apply_direct_feature_mutation(
        fv,
        {
            "login_count_72h": 5,
            "geo_consistency_flag": 0,
            "entity_graph_risk_score": 0.42,
        },
    )
    assert result["login_count_72h"] == 5
    assert result["geo_consistency_flag"] == 0
    assert result["entity_graph_risk_score"] == 0.42


# --- validator integration -------------------------------------------------


def test_rejects_negative_count(monkeypatch, features_global):
    monkeypatch.setenv(DEBUG_MUTATION_ENV_VAR, DEBUG_MUTATION_ENABLED_VALUE)
    fv = _sample_feature(features_global)
    with pytest.raises(ValueError, match="login_count_72h must be >= 0"):
        apply_direct_feature_mutation(fv, {"login_count_72h": -1})


def test_rejects_out_of_range_ratio(monkeypatch, features_global):
    monkeypatch.setenv(DEBUG_MUTATION_ENV_VAR, DEBUG_MUTATION_ENABLED_VALUE)
    fv = _sample_feature(features_global)
    with pytest.raises(ValueError, match="entity_graph_risk_score out of bounds"):
        apply_direct_feature_mutation(fv, {"entity_graph_risk_score": 1.5})


def test_rejects_invalid_geo_flag(monkeypatch, features_global):
    monkeypatch.setenv(DEBUG_MUTATION_ENV_VAR, DEBUG_MUTATION_ENABLED_VALUE)
    fv = _sample_feature(features_global)
    with pytest.raises(ValueError, match="geo_consistency_flag must be 0 or 1"):
        apply_direct_feature_mutation(fv, {"geo_consistency_flag": 2})


def test_rejects_unknown_keys(monkeypatch, features_global):
    monkeypatch.setenv(DEBUG_MUTATION_ENV_VAR, DEBUG_MUTATION_ENABLED_VALUE)
    fv = _sample_feature(features_global)
    with pytest.raises(ValueError, match="unknown FeatureVector keys"):
        apply_direct_feature_mutation(fv, {"some_phase_4_field": 99})


# --- strict-equality on env var --------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["1", "True", "TRUE", "yes", "y", "on", "TrUe", " true", "true ", ""],
)
def test_strict_equality_only_literal_true_enables(monkeypatch, features_global, value):
    """Env values other than literal "true" must NOT enable the gate.

    Permissive truthy parsing would silently bypass the safety contract.
    """
    monkeypatch.setenv(DEBUG_MUTATION_ENV_VAR, value)
    assert is_direct_feature_mutation_enabled() is False, (
        f"env value {value!r} must NOT enable the gate"
    )

    fv = _sample_feature(features_global)
    with pytest.raises(DirectFeatureMutationDisabledError):
        apply_direct_feature_mutation(fv, {"login_count_72h": 99})


def test_re_evaluated_per_call(monkeypatch, features_global):
    """Toggling the env var between calls must be respected — the flag
    must not be cached at module import time."""
    fv = _sample_feature(features_global)

    monkeypatch.setenv(DEBUG_MUTATION_ENV_VAR, DEBUG_MUTATION_ENABLED_VALUE)
    result = apply_direct_feature_mutation(fv, {"login_count_72h": 5})
    assert result["login_count_72h"] == 5

    monkeypatch.delenv(DEBUG_MUTATION_ENV_VAR, raising=False)
    with pytest.raises(DirectFeatureMutationDisabledError):
        apply_direct_feature_mutation(fv, {"login_count_72h": 7})


def test_normal_recomputation_path_does_not_read_env_var(monkeypatch, dataset):
    """``recompute_feature_vectors`` must succeed regardless of the env var
    state. The debug flag is for ``apply_direct_feature_mutation`` only."""
    from atlas.synthetic.features import recompute_feature_vectors

    monkeypatch.delenv(DEBUG_MUTATION_ENV_VAR, raising=False)
    fvs_off = recompute_feature_vectors(
        dataset["transfer_events"], dataset["customers"], dataset["devices"],
        dataset["graph_edges"], dataset["login_sessions"], dataset["security_events"],
    )

    monkeypatch.setenv(DEBUG_MUTATION_ENV_VAR, DEBUG_MUTATION_ENABLED_VALUE)
    fvs_on = recompute_feature_vectors(
        dataset["transfer_events"], dataset["customers"], dataset["devices"],
        dataset["graph_edges"], dataset["login_sessions"], dataset["security_events"],
    )

    # Identical output regardless of env state — the normal path is
    # env-independent by construction.
    assert fvs_off == fvs_on
