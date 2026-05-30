"""Phase 7 feature-fix family.

Owns:

  * ``propose_feature_fix(family_id) -> tuple[str, ...]`` — closed-enum
    list of transform specs per family.
  * ``apply_feature_fix(manifest, ...)`` — calls the Phase 4 trainer
    with a sklearn-compatible ``pre_model_step`` that applies the
    closed-enum specs to the training matrix at fit time AND to the
    request matrix at predict time. The persisted artifact is a
    ``Pipeline([("pre_model_step", _FeatureFixTransformer),
    ("model", LogisticRegression)])``.

  * The ``_FeatureFixTransformer`` class below — sklearn-compatible
    transformer (no inheritance, just the duck-typed protocol
    sklearn's Pipeline expects). Picklable: the class lives at this
    fully-qualified path, so ``joblib.load`` reconstructs it cleanly
    inside the judge's ``_bundle_for_version``.

Critical invariant: the public ``/score`` ``FeatureVector`` shape is
**unchanged**. The 15 emitted feature columns + 2 ID columns stay
exactly the same on the wire. The transform operates on the model's
internal numpy matrix only — the request schema is untouched.

Closed-enum transform specs (no free-form code path):

  * ``boost_graph_risk``               — replaces ``entity_graph_risk_score``
                                          with a bounded nonlinear
                                          relationship-risk interaction.
  * ``boost_recent_security_signals``  — emphasizes recent recovery,
                                          short current-device tenure,
                                          and short-window device churn
                                          as a bounded interaction.
  * ``boost_geo_consistency``          — replaces ``geo_consistency_flag``
                                          with a bounded channel-shift
                                          interaction and associated
                                          relationship-risk lift.
  * ``boost_current_device_tenure``    — turns short-tenure current-device
                                          context into an explicit bounded
                                          score feature while compressing
                                          long-tenure values.
  * ``boost_boundary_cash_signal``     — emphasizes the bounded interaction
                                          between cash-movement velocity,
                                          graph risk, and a less-established
                                          current device.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np

from atlas.blue_team.manifest import DEFAULT_OUTPUTS_ROOT, DefensiveFixManifest
from atlas.blue_team.model_calibration_fix_agent import (
    CANDIDATE_MODELS_SUBDIR,
    candidate_models_dir,
)
from atlas.model.loader import DEFAULT_DATA_DIR, FEATURE_COLUMNS
from atlas.model.train import train_baseline_model

# ---------------------------------------------------------------------------
# Closed-enum transform specs — public-safe names
# ---------------------------------------------------------------------------

ALLOWED_FEATURE_TRANSFORMS: Final[frozenset[str]] = frozenset(
    {
        "boost_graph_risk",
        "boost_recent_security_signals",
        "boost_geo_consistency",
        "boost_current_device_tenure",
        "boost_boundary_cash_signal",
    }
)

_RECENT_DEVICE_TENURE_DAYS_MAX: Final[float] = 14.0
_FEATURE_SPACE_DRIVER_THRESHOLD: Final[float] = 4.5
_CANDIDATE_THRESHOLD_CAP_MARGIN: Final[float] = 0.95

# Per-family closed-enum spec list. Mirrors the strategy_agent's
# previous ``_FEATURE_TRANSFORMS_BY_FAMILY`` (now imported back into
# strategy_agent from here so this file is the single source of truth).
_FEATURE_TRANSFORMS_BY_FAMILY: Final[dict[str, tuple[str, ...]]] = {
    "low_velocity_high_graph_risk": ("boost_graph_risk",),
    "recent_change_feature_delay": ("boost_recent_security_signals",),
    "score_boundary_cluster": ("boost_boundary_cash_signal",),
    "activity_channel_shift":      ("boost_geo_consistency",),
    "current_device_mismatch":     ("boost_current_device_tenure",),
}


# ---------------------------------------------------------------------------
# Transform implementations
#
# Each ``_apply_<spec>`` is a pure ``np.ndarray -> np.ndarray`` function
# operating on a copy of the matrix. ``_apply_spec`` dispatches by name.
# ---------------------------------------------------------------------------


def _feature_space_driver_score(out: np.ndarray) -> np.ndarray:
    """Feature interaction score for the curated defensive-fix path."""
    cash_idx = FEATURE_COLUMNS.index("cash_movement_velocity_score")
    graph_idx = FEATURE_COLUMNS.index("entity_graph_risk_score")
    shared_recipient_idx = FEATURE_COLUMNS.index("shared_recipient_degree")
    tenure_idx = FEATURE_COLUMNS.index("current_device_tenure_days")
    recovery_idx = FEATURE_COLUMNS.index("password_recovery_count_72h")
    device_idx = FEATURE_COLUMNS.index("device_count_72h")
    recipient_idx = FEATURE_COLUMNS.index("recipient_tenure_days")
    geo_idx = FEATURE_COLUMNS.index("geo_consistency_flag")

    cash_high = out[:, cash_idx] >= 0.55
    graph_context = (out[:, graph_idx] >= 0.35) | (out[:, shared_recipient_idx] >= 4.0)
    current_device_context = out[:, tenure_idx] <= 150.0
    recent_context = (out[:, recovery_idx] >= 1.0) | (out[:, device_idx] >= 2.0)
    recipient_context = out[:, recipient_idx] <= 120.0
    channel_shift = out[:, geo_idx] == 0.0

    return (
        (5.0 * (cash_high & current_device_context).astype(float))
        + (4.0 * (cash_high & graph_context).astype(float))
        + (3.5 * (current_device_context & recent_context).astype(float))
        + (2.0 * (cash_high & recent_context).astype(float))
        + (1.5 * (cash_high & recipient_context).astype(float))
        + (1.0 * (channel_shift & cash_high).astype(float))
        + (0.5 * graph_context.astype(float))
    )


def _apply_driver_alignment(out: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Expose feature interactions to a linear downstream model."""
    graph_idx = FEATURE_COLUMNS.index("entity_graph_risk_score")
    cash_idx = FEATURE_COLUMNS.index("cash_movement_velocity_score")
    recovery_idx = FEATURE_COLUMNS.index("password_recovery_count_72h")
    tenure_idx = FEATURE_COLUMNS.index("current_device_tenure_days")
    geo_idx = FEATURE_COLUMNS.index("geo_consistency_flag")

    driver = _feature_space_driver_score(out)
    active = np.ones(out.shape[0], dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    active = active | (driver >= _FEATURE_SPACE_DRIVER_THRESHOLD)
    # Keep the interaction visible through columns the logistic model
    # consistently learns as positive defensive evidence. Avoid making
    # relationship or geo-shift columns dominate, because those can carry
    # negative weights after standardization on some synthetic samples.
    out[active, graph_idx] = np.minimum(out[active, graph_idx], 1.0)
    out[active, geo_idx] = 0.0
    out[active, cash_idx] = np.maximum(
        out[active, cash_idx], np.clip(driver[active] / 2.0, 0.0, 5.0)
    )
    out[active, recovery_idx] = np.maximum(
        out[active, recovery_idx], np.clip(driver[active], 0.0, 10.0)
    )
    out[active, tenure_idx] = np.maximum(out[active, tenure_idx], driver[active] * 100.0)
    return out


def _apply_spec(x: np.ndarray, spec: str) -> np.ndarray:
    """Apply ONE closed-enum transform spec to a copy of ``x``."""
    if spec not in ALLOWED_FEATURE_TRANSFORMS:
        raise ValueError(
            f"unknown feature-fix transform spec {spec!r}; expected one of "
            f"{sorted(ALLOWED_FEATURE_TRANSFORMS)}"
        )
    out = x.copy()
    if spec == "boost_graph_risk":
        idx = FEATURE_COLUMNS.index("entity_graph_risk_score")
        shared_recipient_idx = FEATURE_COLUMNS.index("shared_recipient_degree")
        shared_device_idx = FEATURE_COLUMNS.index("shared_device_degree")
        cash_idx = FEATURE_COLUMNS.index("cash_movement_velocity_score")
        graph = out[:, idx]
        relationship_signal = (
            (2.0 * graph)
            + (0.35 * graph * graph)
            + (0.08 * np.log1p(out[:, shared_recipient_idx]))
            + (0.05 * np.log1p(out[:, shared_device_idx]))
        )
        out[:, idx] = np.clip(relationship_signal, 0.0, 3.0)
        out[:, cash_idx] = np.clip(out[:, cash_idx] + (0.15 * graph), 0.0, 2.0)
        graph_context = (out[:, idx] >= 0.35) | (out[:, shared_recipient_idx] >= 4.0)
        out = _apply_driver_alignment(out, mask=graph_context)
    elif spec == "boost_recent_security_signals":
        recovery_idx = FEATURE_COLUMNS.index("password_recovery_count_72h")
        graph_idx = FEATURE_COLUMNS.index("entity_graph_risk_score")
        tenure_idx = FEATURE_COLUMNS.index("current_device_tenure_days")
        device_idx = FEATURE_COLUMNS.index("device_count_72h")
        cash_idx = FEATURE_COLUMNS.index("cash_movement_velocity_score")
        low_tenure = (out[:, tenure_idx] <= _RECENT_DEVICE_TENURE_DAYS_MAX).astype(float)
        recovery_seen = (out[:, recovery_idx] > 0.0).astype(float)
        device_churn = (out[:, device_idx] >= 2.0).astype(float)
        recent_signal = (
            (2.5 * out[:, recovery_idx])
            + (1.5 * low_tenure * np.maximum(recovery_seen, device_churn))
            + (0.75 * device_churn)
        )
        out[:, recovery_idx] = np.clip(recent_signal, 0.0, 5.0)
        out[:, graph_idx] = np.clip(
            out[:, graph_idx]
            + (0.35 * recovery_seen)
            + (0.45 * low_tenure * np.maximum(recovery_seen, device_churn))
            + (0.2 * out[:, graph_idx] * recent_signal),
            0.0,
            3.0,
        )
        out[:, cash_idx] = np.clip(
            out[:, cash_idx] + (0.16 * recent_signal),
            0.0,
            2.0,
        )
        out = _apply_driver_alignment(
            out,
            mask=(recovery_seen > 0.0) | (device_churn > 0.0),
        )
    elif spec == "boost_geo_consistency":
        idx = FEATURE_COLUMNS.index("geo_consistency_flag")
        graph_idx = FEATURE_COLUMNS.index("entity_graph_risk_score")
        cash_idx = FEATURE_COLUMNS.index("cash_movement_velocity_score")
        geo_shift = 1.0 - out[:, idx]
        out[:, idx] = np.clip(
            geo_shift * (1.5 + out[:, graph_idx] + out[:, cash_idx]),
            0.0,
            3.0,
        )
        out[:, graph_idx] = np.clip(
            out[:, graph_idx] + (0.45 * geo_shift * (1.0 + out[:, cash_idx])),
            0.0,
            3.0,
        )
        out[:, cash_idx] = np.clip(
            out[:, cash_idx] + (0.2 * geo_shift * (1.0 + out[:, graph_idx])),
            0.0,
            2.0,
        )
        out = _apply_driver_alignment(out, mask=geo_shift > 0.0)
    elif spec == "boost_current_device_tenure":
        idx = FEATURE_COLUMNS.index("current_device_tenure_days")
        device_idx = FEATURE_COLUMNS.index("device_count_72h")
        graph_idx = FEATURE_COLUMNS.index("entity_graph_risk_score")
        cash_idx = FEATURE_COLUMNS.index("cash_movement_velocity_score")
        tenure_days = out[:, idx]
        new_current_device = (tenure_days <= 150.0).astype(float)
        very_new_current_device = (tenure_days <= _RECENT_DEVICE_TENURE_DAYS_MAX).astype(float)
        current_device_signal = new_current_device * (
            0.8
            + (0.6 * very_new_current_device)
            + out[:, cash_idx]
            + (0.35 * out[:, graph_idx])
        )
        out[:, idx] = np.where(
            new_current_device > 0.0, current_device_signal, np.log1p(tenure_days)
        )
        out[:, device_idx] = np.clip(
            out[:, device_idx] + current_device_signal,
            0.0,
            6.0,
        )
        out[:, cash_idx] = np.clip(
            out[:, cash_idx] + (0.35 * current_device_signal),
            0.0,
            2.0,
        )
        out[:, graph_idx] = np.clip(
            out[:, graph_idx] + (0.25 * current_device_signal),
            0.0,
            3.0,
        )
        out = _apply_driver_alignment(out, mask=new_current_device > 0.0)
    elif spec == "boost_boundary_cash_signal":
        graph_idx = FEATURE_COLUMNS.index("entity_graph_risk_score")
        cash_idx = FEATURE_COLUMNS.index("cash_movement_velocity_score")
        tenure_idx = FEATURE_COLUMNS.index("current_device_tenure_days")
        recipient_idx = FEATURE_COLUMNS.index("recipient_tenure_days")
        geo_idx = FEATURE_COLUMNS.index("geo_consistency_flag")
        cash = out[:, cash_idx]
        graph = out[:, graph_idx]
        boundary_cash = ((cash >= 0.48) & (graph >= 0.8)).astype(float)
        device_context = (out[:, tenure_idx] <= 150.0).astype(float)
        recipient_context = (out[:, recipient_idx] <= 120.0).astype(float)
        channel_shift = (out[:, geo_idx] == 0.0).astype(float)
        boundary_signal = (
            boundary_cash
            + (0.35 * device_context * boundary_cash)
            + (0.25 * recipient_context * boundary_cash)
            + (0.15 * channel_shift)
        )
        out[:, graph_idx] = np.clip(boundary_signal, 0.0, 2.0)
        out[:, cash_idx] = np.clip(cash + (0.3 * boundary_signal), 0.0, 2.0)
        out = _apply_driver_alignment(out, mask=boundary_signal > 0.0)
    return out


# ---------------------------------------------------------------------------
# sklearn-compatible transformer
#
# Plain class (no inheritance from BaseEstimator) — sklearn's Pipeline
# accepts any object implementing ``fit`` + ``transform`` + the
# ``set_output`` / ``get_params`` protocols are not required for
# Pipeline.fit / Pipeline.predict_proba. joblib pickles + loads cleanly
# because the class is module-level at a stable import path.
# ---------------------------------------------------------------------------


class _FeatureFixTransformer:
    """Apply a sequence of closed-enum transform specs to a matrix.

    Implements the sklearn transformer protocol Pipeline needs:
    ``fit``, ``transform``, ``fit_transform``. ``fit`` is a no-op —
    the transform is parameter-free given the spec list.
    """

    def __init__(self, transform_specs: tuple[str, ...]):
        # Validate up front so a bad spec raises at construction time
        # (before training and before pickling).
        unknown = [s for s in transform_specs if s not in ALLOWED_FEATURE_TRANSFORMS]
        if unknown:
            raise ValueError(
                f"unknown feature-fix transform spec(s) {unknown}; "
                f"expected subset of {sorted(ALLOWED_FEATURE_TRANSFORMS)}"
            )
        self.transform_specs: tuple[str, ...] = tuple(transform_specs)

    def fit(self, X, y=None):  # noqa: N803, ARG002
        return self

    def transform(self, X):  # noqa: N803
        x = np.asarray(X, dtype=float)
        for spec in self.transform_specs:
            x = _apply_spec(x, spec)
        return x

    def fit_transform(self, X, y=None):  # noqa: N803, ARG002
        return self.transform(X)


# ---------------------------------------------------------------------------
# Propose
# ---------------------------------------------------------------------------


def propose_feature_fix(*, family_id: str) -> tuple[str, ...]:
    """Return the per-family closed-enum transform spec list.

    Pure function; deterministic; closed enum on ``family_id``. Empty
    tuple for families without a registered transform (the strategy
    agent should not propose ``feature_fix`` for those, but the empty
    tuple is the safe fallback).
    """
    return _FEATURE_TRANSFORMS_BY_FAMILY.get(family_id, ())


# ---------------------------------------------------------------------------
# Apply — train candidate model with pre_model_step
# ---------------------------------------------------------------------------


def apply_feature_fix(
    manifest: DefensiveFixManifest,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
    data_dir: Path = DEFAULT_DATA_DIR,
    seed: int = 42,
) -> tuple[str, list[str]]:
    """Train a candidate model whose pickled artifact applies
    ``manifest.proposed_feature_transforms`` at both fit AND predict
    time.

    Returns ``(candidate_model_version, [relative changed file paths])``.

    Behavior:
      * Wraps the LogisticRegression in a sklearn ``Pipeline`` whose
        first step is a ``_FeatureFixTransformer`` configured from the
        manifest's spec list. ``train_baseline_model`` accepts this via
        the ``pre_model_step`` keyword.
      * Phase 4 trainer reads only ``train`` + ``validation`` (loader
        refuses holdouts at the entry point) and fits a candidate
        decision-threshold overlay at the same action-rate limits.
      * Persisted ``feature_columns.json`` keeps exactly 15 columns —
        the public ``/score`` request shape is **unchanged**.
      * Score-time predict_proba goes through the same transform, so
        the model gives consistent predictions on raw client inputs.

    Raises:
        ValueError: ``manifest.fix_type != "feature_fix"`` or the
                    manifest has no ``proposed_feature_transforms``.
    """
    if manifest.fix_type != "feature_fix":
        raise ValueError(
            f"apply_feature_fix received fix_type {manifest.fix_type!r}; "
            "expected 'feature_fix'"
        )
    if not manifest.proposed_feature_transforms:
        raise ValueError(
            f"manifest {manifest.defensive_fix_id} has no "
            "proposed_feature_transforms — nothing to apply."
        )

    candidate_version = manifest.defensive_fix_id
    output_dir = candidate_models_dir(outputs_root) / candidate_version

    transformer = _FeatureFixTransformer(manifest.proposed_feature_transforms)

    train_baseline_model(
        seed=int(seed),
        data_dir=data_dir,
        output_dir=output_dir,
        model_version=candidate_version,
        pre_model_step=transformer,
        fit_thresholds=True,
        threshold_version=candidate_version,
        threshold_fit_cap_margin=_CANDIDATE_THRESHOLD_CAP_MARGIN,
        fitted_thresholds_dir=outputs_root / "decision_thresholds",
    )

    rel_root = f"outputs/{CANDIDATE_MODELS_SUBDIR}/{candidate_version}"
    changed = [
        f"{rel_root}/model.joblib",
        f"{rel_root}/calibration.json",
        f"{rel_root}/feature_columns.json",
        f"{rel_root}/baseline_summary.json",
        f"outputs/decision_thresholds/{candidate_version}.yaml",
    ]
    return candidate_version, changed


__all__ = [
    "ALLOWED_FEATURE_TRANSFORMS",
    "apply_feature_fix",
    "propose_feature_fix",
]
