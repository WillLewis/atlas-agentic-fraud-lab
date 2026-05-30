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
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from atlas.model.calibration import apply_calibrator, fit_calibrator
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

# Where ``train_baseline_model`` writes the fitted thresholds YAML and
# the path to the in-repo template it copies non-fitted sections from.
# Both expressed relative to the repo root so the trainer can be
# called from anywhere.
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
_FITTED_THRESHOLDS_DIR: Path = _REPO_ROOT / "outputs" / "decision_thresholds"
_THRESHOLDS_TEMPLATE_PATH: Path = (
    _REPO_ROOT / "config" / "decision_thresholds.yaml"
)

# Decimal places for the persisted threshold floats. Matches the
# in-repo template's precision and keeps the YAML byte-stable.
_THRESHOLD_FLOAT_PRECISION: int = 4

# Fitted thresholds target a conservative fraction of the configured
# caps. The config caps are judge limits, not training goals; leaving
# headroom keeps clean / locked holdout action rates under those limits
# when validation and holdout score distributions differ.
_THRESHOLD_FIT_CAP_MARGIN: float = 0.5
_DECLINE_THRESHOLD_FIT_CAP_MARGIN: float = 0.0


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


# ---------------------------------------------------------------------------
# Threshold fitting (Phase 11+)
#
# The in-repo ``config/decision_thresholds.yaml`` carries demo-constant
# thresholds chosen for a hypothetical high-variance scorer. The actual
# calibrated logistic on the small synthetic training set produces a
# narrow score band — so the persisted thresholds put every event into
# ``accept`` and the round loop becomes degenerate (model_miss_rate=1.0,
# every fix looks like a no-op).
#
# These helpers fit ``(challenge, alert, decline)`` thresholds at the
# upper-tail quantiles of validation calibrated scores corresponding to
# the configured action-rate caps. ``train_baseline_model`` writes the
# result to ``outputs/decision_thresholds/<threshold_version>.yaml`` so
# the Phase 5 judge picks it up via the existing alternate-thresholds
# resolution path. The in-repo template is preserved verbatim and acts
# as the fallback on fresh checkouts.
# ---------------------------------------------------------------------------


def _calibrated_validation_scores(
    base_pipeline: Pipeline,
    val_data: list[LabeledFeature],
    columns: tuple[str, ...],
    calibration: dict,
) -> np.ndarray:
    """Apply the trained pipeline + Platt calibrator to the validation
    set and return the calibrated scores (one float per record, in
    ``[0, 1]``).

    Mirrors what ``atlas.model.scorer.score_features`` does at runtime,
    so the fitted thresholds operate on the exact distribution the
    scoring API will produce.
    """
    x_val = np.asarray(
        [feature_vector_to_array(lf["feature_vector"], columns) for lf in val_data],
        dtype=float,
    )
    raw = base_pipeline.predict_proba(x_val)[:, 1]
    params = calibration["parameters"]
    slope = float(params["slope"])
    intercept = float(params["intercept"])
    return np.asarray(
        [apply_calibrator(float(r), slope=slope, intercept=intercept) for r in raw],
        dtype=float,
    )


def _fit_baseline_thresholds(
    calibrated_scores: np.ndarray,
    action_rate_limits: dict,
    *,
    cap_margin: float = _THRESHOLD_FIT_CAP_MARGIN,
    decline_cap_margin: float = _DECLINE_THRESHOLD_FIT_CAP_MARGIN,
) -> tuple[float, float, float]:
    """Fit ``(challenge, alert, decline)`` thresholds at the upper-tail
    quantiles corresponding to the configured action-rate caps.

    For each rate cap ``r`` the threshold is the ``(1 - r)``-th
    percentile of the calibrated validation scores — i.e. the score
    above which approximately ``r`` fraction of validation events sit.
    Order is enforced (challenge ≤ alert ≤ decline); each value is
    clamped to ``[0, 1]`` and rounded to 4 decimals for byte-stable
    persistence.

    Args:
        calibrated_scores: 1-D array of validation scores in ``[0, 1]``.
        action_rate_limits: mapping from
            ``config/decision_thresholds.yaml.action_rate_limits``.

    Returns:
        ``(challenge_threshold, alert_threshold, decline_threshold)``.
    """
    if calibrated_scores.size == 0:
        raise ValueError("cannot fit thresholds — calibrated_scores is empty")

    # Pull caps out of the action_rate_limits block. ``decline`` is
    # in basis points (1 bp = 0.01%); ``alert`` and ``challenge`` are
    # percentages.
    decline_cap = (
        float(action_rate_limits.get("decline_rate_limit_bps", 25))
        / 10000.0
        * float(decline_cap_margin)
    )
    alert_cap = (
        float(action_rate_limits.get("alert_rate_limit_pct", 15.0))
        / 100.0
        * float(cap_margin)
    )
    # Each cap r maps to the (1 - r) quantile.  numpy.quantile uses the
    # 'linear' method by default — deterministic across runs.
    #
    # For fitted model candidates, keep challenge collapsed into the
    # alert threshold. The acceptance rule allows only a tiny challenge
    # rate increase, while the alert cap is the intended fixed action-rate
    # channel for the curated demo. Policy fixes can still create a
    # separate challenge band explicitly.
    alert_q = float(np.quantile(calibrated_scores, 1.0 - alert_cap))
    challenge_q = alert_q
    decline_q = (
        1.0
        if decline_cap <= 0.0
        else float(np.quantile(calibrated_scores, 1.0 - decline_cap))
    )

    # Enforce challenge ≤ alert ≤ decline (could violate ordering on
    # tied / very small distributions).
    decline_q = max(decline_q, alert_q)

    # Clamp + round.
    def _clip(v: float) -> float:
        return round(max(0.0, min(1.0, v)), _THRESHOLD_FLOAT_PRECISION)

    return _clip(challenge_q), _clip(alert_q), _clip(decline_q)


def _persist_fitted_thresholds(
    challenge: float,
    alert: float,
    decline: float,
    *,
    threshold_version: str,
    template_path: Path,
    output_dir: Path,
) -> Path:
    """Write the fitted thresholds YAML at
    ``output_dir/<threshold_version>.yaml``.

    Copies ``action_rate_limits``, ``customer_friction_tolerances``,
    ``decision_bands``, and ``allowed_reason_codes`` verbatim from the
    in-repo template so the file is a drop-in replacement that
    ``atlas.model.policy.load_decision_policy_config`` parses without
    changes.
    """
    if not template_path.exists():
        raise FileNotFoundError(
            f"decision-thresholds template not found at {template_path}. "
            "Phase 11 threshold fitting needs the in-repo template as the "
            "source of action-rate limits + decision-band labels."
        )
    with template_path.open("r", encoding="utf-8") as fh:
        template = yaml.safe_load(fh) or {}

    fitted_doc: dict = {}
    for key, value in template.items():
        if key == "decision_threshold_version":
            fitted_doc[key] = threshold_version
        elif key == "decision_thresholds":
            fitted_doc[key] = {
                "challenge_score_threshold": challenge,
                "alert_score_threshold": alert,
                "decline_score_threshold": decline,
            }
        else:
            # action_rate_limits, customer_friction_tolerances,
            # decision_bands, allowed_reason_codes — copy verbatim.
            fitted_doc[key] = value

    out_path = output_dir / f"{threshold_version}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(fitted_doc, fh, sort_keys=True, default_flow_style=False)
    return out_path


def train_baseline_model(
    seed: int = DEFAULT_TRAIN_SEED,
    data_dir: Path = DEFAULT_DATA_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    model_version: str | None = None,
    c_override: float | None = None,
    pre_model_step=None,
    fit_thresholds: bool = True,
    threshold_version: str | None = None,
    threshold_fit_cap_margin: float = _THRESHOLD_FIT_CAP_MARGIN,
    decline_threshold_fit_cap_margin: float = _DECLINE_THRESHOLD_FIT_CAP_MARGIN,
    fitted_thresholds_dir: Path = _FITTED_THRESHOLDS_DIR,
    thresholds_template_path: Path = _THRESHOLDS_TEMPLATE_PATH,
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

    Phase 11 threshold-fitting:

      * ``fit_thresholds`` (default ``True``) — score the validation
        set with the calibrated pipeline and write
        ``<fitted_thresholds_dir>/<threshold_version>.yaml`` with
        thresholds at the upper-tail quantiles corresponding to the
        action-rate caps in
        ``config/decision_thresholds.yaml.action_rate_limits``. The
        Phase 5 judge resolves ``thresholds_v1`` to this file when
        present (falling back to the in-repo template otherwise).
      * Phase 7 candidate retraining (``feature_fix`` /
        ``model_calibration_fix``) passes ``fit_thresholds=False`` so
        candidate models reuse the baseline's fitted thresholds and
        do not overwrite ``thresholds_v1.yaml``.
      * ``fitted_thresholds_dir`` / ``thresholds_template_path``
        kwargs are exposed so tests can point at hermetic paths.
      * ``threshold_version`` lets model-changing defensive-fix
        candidates materialize their own decision-threshold overlay
        under the candidate version while preserving the same
        action-rate-limit template.
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

    # --- Phase 11: fit decision thresholds from validation distribution ---
    # Default-on for the baseline path; opted-out by Phase 7 candidate
    # retraining (which reuses baseline's fitted thresholds).
    if fit_thresholds:
        # Read the in-repo template once for action-rate caps + verbatim
        # sections (decision_bands, allowed_reason_codes, etc.).
        if not thresholds_template_path.exists():
            raise FileNotFoundError(
                f"decision-thresholds template not found at "
                f"{thresholds_template_path}. Threshold fitting needs the "
                "in-repo template as the source of action-rate limits."
            )
        with thresholds_template_path.open("r", encoding="utf-8") as fh:
            template_doc = yaml.safe_load(fh) or {}
        action_rate_limits = template_doc.get("action_rate_limits") or {}
        effective_threshold_version = str(
            threshold_version
            if threshold_version is not None
            else template_doc.get("decision_threshold_version", THRESHOLD_VERSION)
        )
        threshold_version_for_summary = str(
            template_doc.get("decision_threshold_version", THRESHOLD_VERSION)
        )

        calibrated_scores = _calibrated_validation_scores(
            base, val_data, columns, calibration
        )
        challenge, alert, decline = _fit_baseline_thresholds(
            calibrated_scores,
            action_rate_limits,
            cap_margin=threshold_fit_cap_margin,
            decline_cap_margin=decline_threshold_fit_cap_margin,
        )
        _persist_fitted_thresholds(
            challenge, alert, decline,
            threshold_version=effective_threshold_version,
            template_path=thresholds_template_path,
            output_dir=fitted_thresholds_dir,
        )
    else:
        threshold_version_for_summary = THRESHOLD_VERSION

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
        "threshold_version": threshold_version_for_summary,
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
