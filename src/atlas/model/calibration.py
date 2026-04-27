"""Score calibration (Phase 4 — Platt sigmoid).

Fits a 1-D logistic regression (Platt scaling) on the validation
partition's raw scores to map the trained baseline's `predict_proba`
output to a calibrated probability in ``[0, 1]``.

Phase 4 invariants:
  * Calibration fits on **validation only**. Holdouts never enter this
    path. The loader's allow-list enforces it upstream; this module
    additionally records ``fit_partition="validation"`` in the metadata.
  * Calibration parameters serialize to JSON as plain floats, so the
    saved artifact is human-readable and deterministic across runs.
  * Pure math at apply time — no sklearn dependency. Component 5/6 route
    handlers can apply the calibrator without re-importing sklearn.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression

from atlas.model.loader import LabeledFeature, feature_vector_to_array

# Pinned hyperparameters for the Platt scaler. Same values across train + cal
# runs guarantee bit-identical calibration parameters.
_PLATT_RANDOM_STATE: int = 42
_PLATT_MAX_ITER: int = 1000
_PLATT_C: float = 1.0


def fit_calibrator(
    base_model: Any,
    validation: list[LabeledFeature],
    feature_columns: tuple[str, ...],
) -> dict:
    """Fit a Platt sigmoid mapping on the validation partition's raw scores.

    Args:
        base_model: The trained baseline. Phase 4 onward this is a
            sklearn ``Pipeline`` (``StandardScaler`` +
            ``LogisticRegression``, optionally preceded by a Phase 7
            feature-fix transformer); we only require an estimator
            with ``predict_proba``.
        validation: ``LabeledFeature`` records from
            ``load_validation_labeled_features``.
        feature_columns: The exact ordered column tuple from the loader.
            Must match the columns used during ``base_model``'s fit.

    Returns:
        A ``CalibrationMetadata``-shaped dict ready to serialize as JSON.
    """
    if not validation:
        raise ValueError("validation set is empty — cannot fit calibrator")

    x_val = np.asarray(
        [feature_vector_to_array(lf["feature_vector"], feature_columns) for lf in validation],
        dtype=float,
    )
    y_val = np.asarray([lf["binary_label"] for lf in validation], dtype=int)

    raw_scores = base_model.predict_proba(x_val)[:, 1].reshape(-1, 1)

    platt = LogisticRegression(
        C=_PLATT_C,
        solver="lbfgs",
        random_state=_PLATT_RANDOM_STATE,
        max_iter=_PLATT_MAX_ITER,
    )
    platt.fit(raw_scores, y_val)

    slope = float(platt.coef_[0][0])
    intercept = float(platt.intercept_[0])

    return {
        "method": "platt",
        "fit_partition": "validation",
        "n_validation_records": len(validation),
        "parameters": {"slope": slope, "intercept": intercept},
    }


def apply_calibrator(raw_score: float, slope: float, intercept: float) -> float:
    """Apply the Platt sigmoid: ``1 / (1 + exp(-(slope * raw + intercept)))``.

    Math-only implementation — the API path can call this without
    importing sklearn at request time. Returns a float in ``[0, 1]``.
    """
    if not math.isfinite(raw_score):
        raise ValueError(f"raw_score must be finite, got {raw_score}")
    z = slope * raw_score + intercept
    # Numerically stable sigmoid: exp(-|z|) / (1 + exp(-|z|))
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)
