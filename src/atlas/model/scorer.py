"""Baseline scorer (Phase 4).

Loads the trained baseline + calibration + feature-column manifest from
``outputs/baseline_models/baseline_v1/`` and applies them to a single
``FeatureVector`` to produce a calibrated score in ``[0, 1]``.

Determinism: the runtime feature matrix reads only the columns named in
``feature_columns.json`` — this is the single source of truth for column
order across fit and score time. The scorer never reads
``synthetic_truth_label`` (it isn't on the ``FeatureVector`` type), so
label leakage at score time is structurally impossible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

from atlas.model.calibration import apply_calibrator
from atlas.model.loader import (
    DEFAULT_OUTPUT_DIR,
    MissingDatasetError,
    feature_vector_to_array,
)
from atlas.synthetic.features import FeatureVector


# ---------------------------------------------------------------------------
# Bundle — everything the route handler needs to score one event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaselineModelBundle:
    """Loaded estimator + calibration + ordered feature columns.

    ``base_model`` is a sklearn ``Pipeline`` (``StandardScaler`` +
    ``LogisticRegression``, optionally preceded by a Phase 7
    feature-fix transformer named ``pre_model_step``). The scorer +
    calibrator only require ``predict_proba``; ``Pipeline`` forwards
    that to its terminal step transparently, so this field is typed
    ``Any`` rather than the concrete estimator class.
    """

    base_model: Any
    calibration: dict[str, Any]
    feature_columns: tuple[str, ...]
    model_version: str


class MissingBaselineModelError(FileNotFoundError):
    """Raised when the trained baseline artifacts are missing.

    Distinct from a generic FileNotFoundError so route handlers can produce
    a clear "run `make train` first" message.
    """


# ---------------------------------------------------------------------------
# Loader (called once at API startup)
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise MissingBaselineModelError(
            f"Baseline artifact not found at {path}. "
            f"Run `make train` to fit the baseline model."
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_baseline_bundle(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> BaselineModelBundle:
    """Load the four baseline artifacts from disk.

    Raises ``MissingBaselineModelError`` if any required artifact is
    missing — the route handlers catch this and surface a 503 with a
    "run `make train` first" hint.
    """
    model_path = output_dir / "model.joblib"
    calibration_path = output_dir / "calibration.json"
    columns_path = output_dir / "feature_columns.json"

    if not model_path.exists():
        raise MissingBaselineModelError(
            f"Baseline model artifact not found at {model_path}. "
            f"Run `make train` to fit the baseline model."
        )

    base_model = joblib.load(model_path)
    calibration = _read_json(calibration_path)
    columns_doc = _read_json(columns_path)

    return BaselineModelBundle(
        base_model=base_model,
        calibration=calibration,
        feature_columns=tuple(columns_doc["feature_columns"]),
        model_version=columns_doc.get("model_version", "baseline_v1"),
    )


# ---------------------------------------------------------------------------
# Score one event
# ---------------------------------------------------------------------------


def score_features(
    feature_vector: FeatureVector, bundle: BaselineModelBundle
) -> float:
    """Apply ``bundle.base_model`` + calibrator to one feature vector.

    Returns a calibrated probability in ``[0, 1]``. The 15-feature input
    matrix is built from ``bundle.feature_columns`` only — ``event_id``,
    ``customer_id``, and any non-FeatureVector field never enter the model.
    """
    arr = feature_vector_to_array(feature_vector, bundle.feature_columns)
    # sklearn expects shape (1, n_features); we score a single row.
    raw = float(bundle.base_model.predict_proba([arr])[0][1])
    params = bundle.calibration["parameters"]
    return apply_calibrator(raw, slope=params["slope"], intercept=params["intercept"])
