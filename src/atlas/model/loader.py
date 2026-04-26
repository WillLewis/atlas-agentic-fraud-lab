"""Phase 4 training-data loaders + artifact-shape declarations.

Reads Phase 2/3 artifacts produced by ``make seed``:

  * ``data/synthetic/features/{train,validation,clean_holdout}.json`` —
    Phase 3 feature vectors (split-safe, partition-local).
  * ``data/synthetic/labels/label_generation.json`` — global labels for
    the train + validation + clean_holdout subset.
  * ``data/synthetic/splits/{train,validation,clean_holdout}.json`` —
    customer-id manifests for cross-checking.

Phase 4 fit-time invariants enforced here:

  * ``load_features_for_partition`` REFUSES the locked / drifted holdout
    partitions. Bible §18 Phase 4 acceptance + the user's "no fit-time
    leakage" rule. Holdout features land under ``holdouts/*/`` with
    ``.claude/settings.json`` deny rules; this loader keeps that contract
    intact at the import layer too.
  * ``join_features_to_labels`` is feature-driven: each feature must have
    a matching label or it raises. Labels with no matching feature are
    silently ignored (they belong to other partitions).
  * The joined ``LabeledFeature`` exposes ``synthetic_truth_label`` and a
    derived ``binary_label`` ONLY for trainer/calibrator use. The scorer
    (component 3) and policy (component 4) MUST NOT read either field at
    runtime — they're supervised targets, not features.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, TypedDict

from atlas.synthetic.features import FEATURE_VECTOR_KEYS, FeatureVector
from atlas.synthetic.labels import LabelGenerationRecord

# ---------------------------------------------------------------------------
# Path conventions
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR: Final[Path] = REPO_ROOT / "data" / "synthetic"
DEFAULT_OUTPUT_DIR: Final[Path] = (
    REPO_ROOT / "outputs" / "baseline_models" / "baseline_v1"
)

# ---------------------------------------------------------------------------
# Allowed fit partitions and feature-column ordering
# ---------------------------------------------------------------------------

# Partitions that Phase 4 is allowed to LOAD for fitting / calibration.
# clean_holdout is included for completeness (Phase 5 judge will use it),
# but trainer + calibrator must use only train + validation respectively.
ALLOWED_FIT_PARTITIONS: Final[tuple[str, ...]] = (
    "train",
    "validation",
    "clean_holdout",
)

# Partitions that this loader REFUSES outright. Phase 5+ uses these via
# different code paths (the judge module reads holdout artifacts directly
# from holdouts/*/).
FORBIDDEN_FIT_PARTITIONS: Final[tuple[str, ...]] = (
    "locked_adaptive_holdout",
    "drifted_holdout",
)

# Two non-feature keys on a FeatureVector that are NEVER part of the model
# input matrix.
_NON_FEATURE_KEYS: Final[frozenset[str]] = frozenset({"event_id", "customer_id"})

# Deterministic feature-column order. Sorted alphabetically so the order
# is reproducible regardless of dict-iteration order. Component 3 persists
# this exact list to ``feature_columns.json``; the scorer reads from that
# file rather than re-deriving, so column order survives across runs even
# if FEATURE_VECTOR_KEYS is later reordered.
FEATURE_COLUMNS: Final[tuple[str, ...]] = tuple(
    sorted(FEATURE_VECTOR_KEYS - _NON_FEATURE_KEYS)
)

# Mapping from synthetic_truth_label to a binary classification target.
# 0 = normal_activity, 1 = high_risk_synthetic_activity.
LABEL_BINARY_MAP: Final[dict[str, int]] = {
    "normal_activity": 0,
    "high_risk_synthetic_activity": 1,
}

# ---------------------------------------------------------------------------
# Joined record + artifact-shape TypedDicts
# ---------------------------------------------------------------------------


class LabeledFeature(TypedDict):
    """One feature vector joined to its supervised label.

    ``binary_label`` is the int target the trainer / calibrator consumes.
    ``synthetic_truth_label`` is kept as metadata for diagnostics and for
    label-leakage-prevention tests; the scorer must not read it.
    """

    event_id: str
    customer_id: str
    feature_vector: FeatureVector
    synthetic_truth_label: str
    binary_label: int


class TrainedModelMetadata(TypedDict):
    """Identity + provenance of the trained baseline.

    Persisted as part of ``baseline_summary.json`` — NOT a separate file.
    """

    model_version: str
    model_family: str
    train_seed: int
    feature_columns: list[str]
    n_train_records: int
    fit_partition: str
    sklearn_version: str


class CalibrationMetadata(TypedDict):
    """Stored as ``calibration.json``. Schema depends on calibration method.

    For Platt scaling (the Phase 4 default): ``parameters`` carries
    ``{"slope": float, "intercept": float}``. For isotonic regression a
    serialized step function would be stored instead — Phase 4 component
    3 picks one method and pins it here.
    """

    method: str
    fit_partition: str
    n_validation_records: int
    parameters: dict[str, Any]


class BaselineSummary(TypedDict):
    """Read-only baseline metadata. Phase 9 surfaces this in the web app.

    Intentionally does NOT include Phase 5 judge metrics (model_miss_rate,
    recall_at_fixed_action_rate, etc.) — those are computed by
    ``atlas.judge`` later.
    """

    model_version: str
    threshold_version: str
    train_seed: int
    reference_now_utc: str
    fit_partition_counts: dict[str, int]
    calibration_partition_counts: dict[str, int]
    label_distribution: dict[str, dict[str, int]]
    feature_columns: list[str]
    artifact_paths: dict[str, str]


# ---------------------------------------------------------------------------
# Disk loaders
# ---------------------------------------------------------------------------


class MissingDatasetError(FileNotFoundError):
    """Raised when a Phase 2/3 artifact is missing — usually because
    ``make seed`` has not been run yet.

    Distinct from a generic ``FileNotFoundError`` so route handlers and
    CLI entry points can produce a clear "run ``make seed`` first" message.
    """


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise MissingDatasetError(
            f"Phase 2/3 artifact not found at {path}. "
            f"Run `make seed` to generate the synthetic dataset."
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_features_for_partition(
    partition: str, data_dir: Path = DEFAULT_DATA_DIR
) -> list[FeatureVector]:
    """Load the per-partition feature artifact for ``partition``.

    REFUSES the locked / drifted holdout partitions. Phase 4 invariant:
    holdouts are not used for fitting. Holdout feature artifacts live
    under ``holdouts/*/feature_vectors.json`` and are read by the Phase 5
    judge through a different code path.
    """
    if partition in FORBIDDEN_FIT_PARTITIONS:
        raise ValueError(
            f"Phase 4 refuses to load partition {partition!r} for fitting. "
            f"Holdouts are not training or calibration data "
            f"(Bible §18 Phase 4 acceptance, §6.1 rule 8)."
        )
    if partition not in ALLOWED_FIT_PARTITIONS:
        raise ValueError(
            f"unknown partition {partition!r}; expected one of "
            f"{list(ALLOWED_FIT_PARTITIONS)}"
        )
    path = data_dir / "features" / f"{partition}.json"
    return _read_json(path)


def load_global_labels(
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[LabelGenerationRecord]:
    """Load the global label file (covers train + validation + clean_holdout)."""
    return _read_json(data_dir / "labels" / "label_generation.json")


def load_partition_customer_ids(
    partition: str, data_dir: Path = DEFAULT_DATA_DIR
) -> set[str]:
    """Load the customer-id list from the partition's split manifest.

    Used to cross-check that loaded features belong to the expected
    partition — guards against accidentally pointing at a different file.
    """
    if partition not in ALLOWED_FIT_PARTITIONS:
        raise ValueError(
            f"split manifest only exists for {list(ALLOWED_FIT_PARTITIONS)}; "
            f"got {partition!r}"
        )
    doc = _read_json(data_dir / "splits" / f"{partition}.json")
    return set(doc["customer_ids"])


# ---------------------------------------------------------------------------
# Join + cross-check
# ---------------------------------------------------------------------------


def join_features_to_labels(
    features: list[FeatureVector],
    labels: list[LabelGenerationRecord],
) -> list[LabeledFeature]:
    """Feature-driven join by ``event_id``.

    Raises if any feature has no matching label. Labels with no matching
    feature are silently ignored (they belong to other partitions of the
    global label file).
    """
    labels_by_event = {label["event_id"]: label for label in labels}
    out: list[LabeledFeature] = []
    for fv in features:
        event_id = fv["event_id"]
        label = labels_by_event.get(event_id)
        if label is None:
            raise ValueError(
                f"feature {event_id!r} has no matching label record. "
                f"Likely cause: features and labels were generated from "
                f"different `make seed` runs."
            )
        synthetic_label = label["synthetic_truth_label"]
        binary = LABEL_BINARY_MAP.get(synthetic_label)
        if binary is None:
            raise ValueError(
                f"label {event_id!r} has unknown synthetic_truth_label "
                f"{synthetic_label!r}; expected one of {sorted(LABEL_BINARY_MAP)}"
            )
        out.append(
            LabeledFeature(
                event_id=event_id,
                customer_id=fv["customer_id"],
                feature_vector=fv,
                synthetic_truth_label=synthetic_label,
                binary_label=binary,
            )
        )
    return out


def assert_features_in_partition(
    features: list[FeatureVector], partition_customer_ids: set[str]
) -> None:
    """Defensive cross-check: every feature's customer_id must be in the
    partition's customer set. Catches mis-pointed file paths."""
    leaked = [
        fv["event_id"]
        for fv in features
        if fv["customer_id"] not in partition_customer_ids
    ]
    if leaked:
        raise ValueError(
            f"{len(leaked)} feature(s) reference customers outside the "
            f"partition manifest. First 5: {leaked[:5]}"
        )


# ---------------------------------------------------------------------------
# Convenience helpers (component 3 calls these)
# ---------------------------------------------------------------------------


def load_train_labeled_features(
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[LabeledFeature]:
    """Load + join train features and labels. Trainer-only entry point."""
    features = load_features_for_partition("train", data_dir)
    labels = load_global_labels(data_dir)
    joined = join_features_to_labels(features, labels)
    cust_ids = load_partition_customer_ids("train", data_dir)
    assert_features_in_partition(features, cust_ids)
    return joined


def load_validation_labeled_features(
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[LabeledFeature]:
    """Load + join validation features and labels. Calibrator-only entry point."""
    features = load_features_for_partition("validation", data_dir)
    labels = load_global_labels(data_dir)
    joined = join_features_to_labels(features, labels)
    cust_ids = load_partition_customer_ids("validation", data_dir)
    assert_features_in_partition(features, cust_ids)
    return joined


def feature_vector_to_array(
    fv: FeatureVector, columns: tuple[str, ...] = FEATURE_COLUMNS
) -> list[float]:
    """Project a ``FeatureVector`` to an ordered float list for sklearn.

    Reads only the columns in ``columns`` — by construction this excludes
    ``event_id``, ``customer_id``, AND any field outside FEATURE_VECTOR_KEYS.
    The scorer's runtime feature matrix never includes ``synthetic_truth_label``
    because the label isn't on the FeatureVector type at all.
    """
    return [float(fv[col]) for col in columns]  # type: ignore[literal-required]
