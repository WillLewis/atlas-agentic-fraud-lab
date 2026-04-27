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

  * ``boost_graph_risk``               — multiplies
                                          ``entity_graph_risk_score`` by
                                          2.0 so the model learns a
                                          larger relative weight on
                                          relationship-graph risk.
  * ``boost_recent_security_signals``  — multiplies
                                          ``password_recovery_count_72h``
                                          by 2.0 so recent recovery
                                          events steer the score upward.
  * ``boost_geo_consistency``          — remaps ``geo_consistency_flag``
                                          from ``{0, 1}`` to ``{-1, 1}``
                                          giving the model a directional
                                          signal on geo consistency.
  * ``boost_current_device_tenure``    — applies ``log1p`` to
                                          ``current_device_tenure_days``
                                          so the model sees a compressed
                                          tenure scale.
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
    }
)

# Per-family closed-enum spec list. Mirrors the strategy_agent's
# previous ``_FEATURE_TRANSFORMS_BY_FAMILY`` (now imported back into
# strategy_agent from here so this file is the single source of truth).
_FEATURE_TRANSFORMS_BY_FAMILY: Final[dict[str, tuple[str, ...]]] = {
    "low_velocity_high_graph_risk": ("boost_graph_risk",),
    "recent_change_feature_delay": ("boost_recent_security_signals",),
    "activity_channel_shift":      ("boost_geo_consistency",),
    "current_device_mismatch":     ("boost_current_device_tenure",),
}


# ---------------------------------------------------------------------------
# Transform implementations
#
# Each ``_apply_<spec>`` is a pure ``np.ndarray -> np.ndarray`` function
# operating on a copy of the matrix. ``_apply_spec`` dispatches by name.
# ---------------------------------------------------------------------------


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
        out[:, idx] = out[:, idx] * 2.0
    elif spec == "boost_recent_security_signals":
        idx = FEATURE_COLUMNS.index("password_recovery_count_72h")
        out[:, idx] = out[:, idx] * 2.0
    elif spec == "boost_geo_consistency":
        idx = FEATURE_COLUMNS.index("geo_consistency_flag")
        # {0, 1} → {-1, 1}
        out[:, idx] = (2.0 * out[:, idx]) - 1.0
    elif spec == "boost_current_device_tenure":
        idx = FEATURE_COLUMNS.index("current_device_tenure_days")
        out[:, idx] = np.log1p(out[:, idx])
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
        refuses holdouts at the entry point).
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
        # Candidate uses baseline's fitted thresholds (per the Phase 7
        # ``thresholds_v1`` convention in ``fix_applier``); do NOT
        # overwrite ``outputs/decision_thresholds/thresholds_v1.yaml``.
        fit_thresholds=False,
    )

    rel_root = f"outputs/{CANDIDATE_MODELS_SUBDIR}/{candidate_version}"
    changed = [
        f"{rel_root}/model.joblib",
        f"{rel_root}/calibration.json",
        f"{rel_root}/feature_columns.json",
        f"{rel_root}/baseline_summary.json",
    ]
    return candidate_version, changed


__all__ = [
    "ALLOWED_FEATURE_TRANSFORMS",
    "apply_feature_fix",
    "propose_feature_fix",
]
