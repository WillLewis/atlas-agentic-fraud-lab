"""Baseline model trainer (Phase 4).

Fits a deterministic logistic baseline on the ``train`` partition,
calibrates score distribution on ``validation``, and persists four
artifacts under ``outputs/baseline_models/baseline_v1/``:

  * ``model.joblib``           — pickled sklearn ``Pipeline`` (always
                                 includes a ``StandardScaler`` step
                                 before the ``LogisticRegression`` so
                                 lbfgs converges on mixed-scale inputs;
                                 may also include a leading
                                 ``pre_model_step`` for Phase 7
                                 feature-fix candidates)
  * ``calibration.json``       — Platt slope + intercept
  * ``feature_columns.json``   — ordered feature column list
  * ``baseline_summary.json``  — read-only metadata for Phase 9 web app

Phase 4 invariants enforced here:
  * ``train_baseline_model`` calls only the loader's
    ``load_train_labeled_features`` / ``load_validation_labeled_features``
    entry points. The loader refuses holdout partitions outright.
  * ``random_state=42`` and a high ``max_iter`` pin the L-BFGS solver
    so the same training data produces byte-identical coefficients.
    ``StandardScaler`` is parameter-free and deterministic, so the
    full pipeline stays byte-stable across runs.
  * No Phase 5 judge metrics computed here. The summary contains only
    identity, fit / cal counts, and label distributions.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from atlas.model.calibration import fit_calibrator
from atlas.model.loader import (
    DEFAULT_DATA_DIR,
    DEFAULT_OUTPUT_DIR,
    FEATURE_COLUMNS,
    BaselineSummary,
    LabeledFeature,
    feature_vector_to_array,
    load_train_labeled_features,
    load_validation_labeled_features,
)

# ---------------------------------------------------------------------------
# Pinned baseline hyperparameters
# ---------------------------------------------------------------------------

DEFAULT_TRAIN_SEED: int = 42
# Raised from 1000 to 5000: lbfgs converges far below this floor on the
# standardized matrix, but the high cap leaves headroom for Phase 7
# feature-fix candidates whose ``pre_model_step`` reshapes one or two
# columns before standardization (e.g. ``boost_graph_risk`` doubles
# ``entity_graph_risk_score``).
_BASE_MAX_ITER: int = 5000
_BASE_C: float = 1.0
_BASE_SOLVER: str = "lbfgs"

MODEL_VERSION: str = "baseline_v1"
THRESHOLD_VERSION: str = "thresholds_v1"

# Manifest path for reading reference_now_utc from the Phase 2/3 dataset.
_MANIFEST_PATH_REL: str = "manifest.json"


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------


def _label_distribution(labeled: list[LabeledFeature]) -> dict[str, int]:
    """Count synthetic_truth_label values for the partition summary."""
    out: dict[str, int] = {}
    for lf in labeled:
        out[lf["synthetic_truth_label"]] = out.get(lf["synthetic_truth_label"], 0) + 1
    return out


def _build_matrices(
    labeled: list[LabeledFeature], columns: tuple[str, ...]
) -> tuple[np.ndarray, np.ndarray]:
    """Convert ``LabeledFeature`` records to ``(X, y)`` numpy arrays.

    ``X`` reads ONLY the columns in ``columns``. ``synthetic_truth_label``
    is never on the ``FeatureVector`` type, so the input matrix
    structurally cannot include the label.
    """
    if not labeled:
        raise ValueError("labeled feature list is empty")
    x = np.asarray(
        [feature_vector_to_array(lf["feature_vector"], columns) for lf in labeled],
        dtype=float,
    )
    y = np.asarray([lf["binary_label"] for lf in labeled], dtype=int)
    return x, y


def _read_reference_now_utc(data_dir: Path) -> str:
    manifest_path = data_dir / _MANIFEST_PATH_REL
    if not manifest_path.exists():
        return ""
    with manifest_path.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    return manifest.get("reference_now_utc", "")


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def train_baseline_model(
    seed: int = DEFAULT_TRAIN_SEED,
    data_dir: Path = DEFAULT_DATA_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    model_version: str | None = None,
    c_override: float | None = None,
    pre_model_step=None,
) -> BaselineSummary:
    """Train + calibrate + persist a baseline-shape model.

    Reads:
        ``data_dir/features/{train,validation}.json``
        ``data_dir/labels/label_generation.json``
        ``data_dir/splits/{train,validation}.json``  (cross-check)

    Writes:
        ``output_dir/model.joblib``
        ``output_dir/calibration.json``
        ``output_dir/feature_columns.json``
        ``output_dir/baseline_summary.json``

    Returns the baseline summary dict (also written to disk).

    Holdout partitions are NEVER touched — the loader refuses them at the
    ``load_features_for_partition`` entry point.

    Phase 7 keyword-only extensions (non-breaking; defaults preserve
    Phase 4 behavior):

      * ``model_version`` — embed this version string in
        ``feature_columns.json`` and ``baseline_summary.json`` instead
        of the Phase-4 default ``MODEL_VERSION`` (``"baseline_v1"``).
        Used by the bank-defense calibration / feature-fix appliers so
        the candidate artifact carries the candidate's
        ``defensive_fix_id`` as its identity.
      * ``c_override`` — override the sklearn ``LogisticRegression(C=…)``
        inverse-regularization parameter. ``None`` keeps the Phase 4
        baseline ``_BASE_C = 1.0``. Used by the calibration-fix family
        to surface alternate L2 strengths.
      * ``pre_model_step`` — optional sklearn-compatible transformer
        prepended to the model. When provided, the persisted artifact
        is a ``Pipeline([("pre_model_step", pre_model_step),
        ("standardize", StandardScaler()), ("model",
        LogisticRegression)])`` so the SAME transform runs at fit and
        predict time. Used by the feature-fix family to bake a closed-
        enum training-data transform into the candidate artifact while
        preserving the public ``/score`` ``FeatureVector`` shape.

    The persisted artifact is always a ``Pipeline``. When
    ``pre_model_step`` is omitted the pipeline is
    ``Pipeline([("standardize", StandardScaler()), ("model",
    LogisticRegression)])``. The scorer / calibrator only require an
    estimator with ``predict_proba``; ``Pipeline`` forwards that to
    its terminal step transparently.
    """
    train_data = load_train_labeled_features(data_dir)
    val_data = load_validation_labeled_features(data_dir)

    columns = FEATURE_COLUMNS
    x_train, y_train = _build_matrices(train_data, columns)
    x_val, _ = _build_matrices(val_data, columns)

    effective_model_version = model_version if model_version is not None else MODEL_VERSION
    effective_c = float(c_override) if c_override is not None else _BASE_C

    # --- Fit baseline on TRAIN only ---
    inner_model = LogisticRegression(
        C=effective_c,
        solver=_BASE_SOLVER,
        random_state=seed,
        max_iter=_BASE_MAX_ITER,
    )
    # Always-Pipeline: the StandardScaler step normalizes the
    # mixed-scale 15-feature matrix (counts vs ratios vs tenure-days
    # vs graph scores) so lbfgs converges. Phase 7 feature-fix
    # candidates put their custom transform first, then standardize,
    # then the model — so the closed-enum spec runs on raw inputs at
    # both fit and predict time, while the standardizer keeps lbfgs
    # well-conditioned on whatever the spec produces.
    steps: list[tuple[str, object]] = []
    if pre_model_step is not None:
        steps.append(("pre_model_step", pre_model_step))
    steps.append(("standardize", StandardScaler()))
    steps.append(("model", inner_model))
    base = Pipeline(steps)
    base.fit(x_train, y_train)

    # --- Calibrate on VALIDATION only ---
    calibration = fit_calibrator(base, val_data, columns)

    # --- Persist artifacts ---
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.joblib"
    calibration_path = output_dir / "calibration.json"
    columns_path = output_dir / "feature_columns.json"
    summary_path = output_dir / "baseline_summary.json"

    joblib.dump(base, model_path)
    _write_json(calibration_path, calibration)
    _write_json(
        columns_path,
        {
            "model_version": effective_model_version,
            "feature_columns": list(columns),
        },
    )

    summary: BaselineSummary = {
        "model_version": effective_model_version,
        "threshold_version": THRESHOLD_VERSION,
        "train_seed": seed,
        "reference_now_utc": _read_reference_now_utc(data_dir),
        "fit_partition_counts": {"train": len(train_data)},
        "calibration_partition_counts": {"validation": len(val_data)},
        "label_distribution": {
            "train": _label_distribution(train_data),
            "validation": _label_distribution(val_data),
        },
        "feature_columns": list(columns),
        "artifact_paths": {
            "model": "model.joblib",
            "calibration": "calibration.json",
            "feature_columns": "feature_columns.json",
            "baseline_summary": "baseline_summary.json",
        },
    }
    _write_json(summary_path, summary)
    # Stash sklearn version + the effective L2 strength on the summary
    # post-hoc so callers (component 7 CLI, web app, judge tests) can
    # see provenance without it being part of the BaselineSummary
    # TypedDict contract.
    summary_with_provenance = dict(summary)
    summary_with_provenance["sklearn_version"] = sklearn.__version__
    summary_with_provenance["l2_strength_c"] = effective_c
    _write_json(summary_path, summary_with_provenance)

    return summary
