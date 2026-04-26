"""Phase 5 holdout / evaluation-set loaders.

Loads the four evaluation sets the judge consumes:

  * ``clean_holdout``           — ``data/synthetic/features/clean_holdout.json``
                                  + global labels + global transfer events.
  * ``found_adaptive_set``      — input contract: caller passes event-ids
                                  drawn from the global readable feature
                                  artifact (train + validation + clean).
  * ``locked_adaptive_holdout`` — ``data/synthetic/holdouts/locked/{feature_vectors,labels,transfer_events}.json``.
  * ``drifted_holdout``         — ``data/synthetic/holdouts/drifted/{feature_vectors,transfer_events}.json``
                                  + ``data/synthetic/holdouts/drifted/labels/labels.json``.

The locked / drifted reads are normal Python file I/O; the
``.claude/settings.json`` Read-tool deny applies to my tool calls (and
shell ``cat``/``ls``), not to runtime code execution.

Each loader returns a list of ``JudgeEvalRecord``s — a labeled
``FeatureVector`` enriched with the source transfer event's
``amount_bucket``. The judge needs ``amount_bucket`` to compute
``synthetic_loss_allowed`` (Bible §16.6); pre-joining here avoids a
second pass over the events file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, Sequence, TypedDict

from atlas.model.loader import (
    DEFAULT_DATA_DIR,
    LABEL_BINARY_MAP,
    MissingDatasetError,
)
from atlas.synthetic.features import FeatureVector
from atlas.synthetic.labels import LabelGenerationRecord


HOLDOUT_NAMES: Final[tuple[str, ...]] = (
    "clean_holdout",
    "found_adaptive_set",
    "locked_adaptive_holdout",
    "drifted_holdout",
)

# Partitions in the global readable feature artifact. ``found_adaptive_set``
# event-ids must be drawn from this union.
_GLOBAL_READABLE_PARTITIONS: Final[tuple[str, ...]] = (
    "train",
    "validation",
    "clean_holdout",
)


class JudgeEvalRecord(TypedDict):
    """One labeled feature vector enriched with its transfer-event amount
    bucket. The judge consumes this everywhere — scoring uses
    ``feature_vector``, ground truth uses ``binary_label``, synthetic-loss
    metrics use ``amount_bucket``.
    """

    event_id: str
    customer_id: str
    feature_vector: FeatureVector
    synthetic_truth_label: str
    binary_label: int
    amount_bucket: str


# ---------------------------------------------------------------------------
# Disk helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise MissingDatasetError(
            f"Phase 2/3 holdout artifact not found at {path}. "
            f"Run `make seed` to regenerate the synthetic dataset."
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Join helper — features × labels × transfer events
# ---------------------------------------------------------------------------


def _join(
    features: list[FeatureVector],
    labels: list[LabelGenerationRecord],
    transfers: list[dict[str, Any]],
    *,
    eval_set_name: str,
) -> list[JudgeEvalRecord]:
    """Feature-driven join. Every feature must have a matching label AND
    a matching transfer event. Labels / transfers without a matching
    feature are silently ignored (they belong to other partitions).
    """
    labels_by_id = {label["event_id"]: label for label in labels}
    amount_by_id = {tx["transfer_event_id"]: tx["amount_bucket"] for tx in transfers}

    out: list[JudgeEvalRecord] = []
    for fv in features:
        eid = fv["event_id"]
        label = labels_by_id.get(eid)
        if label is None:
            raise ValueError(
                f"{eval_set_name}: feature {eid!r} has no matching label record. "
                f"Likely cause: features and labels were generated from "
                f"different `make seed` runs."
            )
        amount = amount_by_id.get(eid)
        if amount is None:
            raise ValueError(
                f"{eval_set_name}: feature {eid!r} has no matching transfer event "
                f"(needed for amount_bucket → synthetic_loss_allowed)."
            )
        synthetic_label = label["synthetic_truth_label"]
        binary = LABEL_BINARY_MAP.get(synthetic_label)
        if binary is None:
            raise ValueError(
                f"{eval_set_name}: label {eid!r} has unknown "
                f"synthetic_truth_label {synthetic_label!r}; expected one of "
                f"{sorted(LABEL_BINARY_MAP)}"
            )
        out.append(
            JudgeEvalRecord(
                event_id=eid,
                customer_id=fv["customer_id"],
                feature_vector=fv,
                synthetic_truth_label=synthetic_label,
                binary_label=binary,
                amount_bucket=amount,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Per-set path bundles
# ---------------------------------------------------------------------------


def _clean_holdout_paths(data_dir: Path) -> tuple[Path, Path, Path]:
    return (
        data_dir / "features" / "clean_holdout.json",
        data_dir / "labels" / "label_generation.json",
        data_dir / "events" / "transfer_events.json",
    )


def _locked_holdout_paths(data_dir: Path) -> tuple[Path, Path, Path]:
    base = data_dir / "holdouts" / "locked"
    return (
        base / "feature_vectors.json",
        base / "labels.json",
        base / "transfer_events.json",
    )


def _drifted_holdout_paths(data_dir: Path) -> tuple[Path, Path, Path]:
    base = data_dir / "holdouts" / "drifted"
    return (
        base / "feature_vectors.json",
        base / "labels" / "labels.json",
        base / "transfer_events.json",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_eval_set(
    name: str,
    *,
    found_adaptive_set_event_ids: Sequence[str] | None = None,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[JudgeEvalRecord]:
    """Load one of the four evaluation sets the judge consumes.

    For ``found_adaptive_set`` the caller MUST supply
    ``found_adaptive_set_event_ids`` (a non-empty list of event-ids that
    all exist in the global readable feature artifact — train + validation
    + clean_holdout). For the other three sets the parameter is ignored.
    """
    if name not in HOLDOUT_NAMES:
        raise ValueError(
            f"unknown eval set {name!r}; expected one of {list(HOLDOUT_NAMES)}"
        )

    if name == "clean_holdout":
        feat_p, lab_p, tx_p = _clean_holdout_paths(data_dir)
        return _join(_read_json(feat_p), _read_json(lab_p), _read_json(tx_p), eval_set_name=name)

    if name == "locked_adaptive_holdout":
        feat_p, lab_p, tx_p = _locked_holdout_paths(data_dir)
        return _join(_read_json(feat_p), _read_json(lab_p), _read_json(tx_p), eval_set_name=name)

    if name == "drifted_holdout":
        feat_p, lab_p, tx_p = _drifted_holdout_paths(data_dir)
        return _join(_read_json(feat_p), _read_json(lab_p), _read_json(tx_p), eval_set_name=name)

    # found_adaptive_set
    if not found_adaptive_set_event_ids:
        raise ValueError(
            "found_adaptive_set requires a non-empty "
            "found_adaptive_set_event_ids list."
        )
    requested = list(found_adaptive_set_event_ids)
    if len(requested) != len(set(requested)):
        raise ValueError(
            "found_adaptive_set_event_ids must not contain duplicates."
        )

    readable: list[FeatureVector] = []
    for partition in _GLOBAL_READABLE_PARTITIONS:
        readable.extend(_read_json(data_dir / "features" / f"{partition}.json"))
    readable_by_id = {f["event_id"]: f for f in readable}
    missing = [eid for eid in requested if eid not in readable_by_id]
    if missing:
        raise ValueError(
            f"found_adaptive_set: {len(missing)} event_id(s) not in the "
            f"readable global feature artifact (train + validation + "
            f"clean_holdout). First 5: {missing[:5]}"
        )
    features = [readable_by_id[eid] for eid in requested]
    labels = _read_json(data_dir / "labels" / "label_generation.json")
    transfers = _read_json(data_dir / "events" / "transfer_events.json")
    return _join(features, labels, transfers, eval_set_name=name)
