"""Phase 7 model-calibration fix family.

Owns:

  * ``propose_calibration_fix(family_id) -> (training_seed, l2_strength)`` —
    closed enum of (seed, C) pairs per family.
  * ``apply_calibration_fix(manifest, ...)`` — calls
    ``atlas.model.train.train_baseline_model`` with the manifest's
    ``proposed_training_seed`` + ``proposed_l2_strength`` overrides into
    ``outputs/baseline_models/<defensive_fix_id>/``. Same artifact
    layout as ``baseline_v1`` so Phase 5 ``_bundle_for_version`` loads
    the candidate without changes.

NEVER fits on holdout labels. The Phase 4 trainer's existing invariant
carries forward — ``load_features_for_partition`` refuses
``locked_adaptive_holdout`` and ``drifted_holdout`` at the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from atlas.blue_team.manifest import DEFAULT_OUTPUTS_ROOT, DefensiveFixManifest
from atlas.model.loader import DEFAULT_DATA_DIR
from atlas.model.train import train_baseline_model

# ---------------------------------------------------------------------------
# Path conventions
# ---------------------------------------------------------------------------

CANDIDATE_MODELS_SUBDIR: Final[str] = "baseline_models"
_CANDIDATE_THRESHOLD_CAP_MARGIN: Final[float] = 1.1


def candidate_models_dir(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> Path:
    """Single source of truth for the candidate-model output dir.

    Mirrors the layout the Phase 5 judge's
    ``atlas.judge.evaluate.BASELINE_MODELS_ROOT`` resolves against. The
    judge's ``_bundle_for_version`` loads
    ``BASELINE_MODELS_ROOT / model_version`` — we write here so the
    judge picks candidates up without any loader changes.
    """
    return outputs_root / CANDIDATE_MODELS_SUBDIR


# ---------------------------------------------------------------------------
# Per-family closed-enum proposal params
# ---------------------------------------------------------------------------


# Per-family ``(training_seed_offset, l2_strength)`` pairs.
#
# ``l2_strength`` expressed as the sklearn ``C`` parameter (inverse
# regularization). Phase 4 baseline uses ``C=1.0``.
#
# Closed enum — the calibration-fix agent must NEVER emit a (seed, C)
# pair outside this map. Adding a new family here is a deliberate change.
_CALIBRATION_PARAMS_BY_FAMILY: Final[dict[str, tuple[int, float]]] = {
    "label_noise_mislearned": (1001, 0.5),  # tighter L2
    "overfit_fix_failure":    (2002, 2.0),  # looser L2
}

# Default fallback for families that don't have a specific entry. Used
# by the strategy agent when a request includes ``model_calibration_fix``
# for a family not in the closed enum above.
_DEFAULT_CALIBRATION_PARAMS: Final[tuple[int, float]] = (3003, 1.0)


# ---------------------------------------------------------------------------
# Propose
# ---------------------------------------------------------------------------


def propose_calibration_fix(*, family_id: str) -> tuple[int, float]:
    """Return the per-family ``(training_seed, l2_strength)``.

    Pure function; closed enum on ``family_id``; deterministic.
    """
    return _CALIBRATION_PARAMS_BY_FAMILY.get(family_id, _DEFAULT_CALIBRATION_PARAMS)


# ---------------------------------------------------------------------------
# Apply — train candidate model
# ---------------------------------------------------------------------------


def apply_calibration_fix(
    manifest: DefensiveFixManifest,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> tuple[str, list[str]]:
    """Train a candidate model with the manifest's seed + L2 overrides.

    Returns ``(candidate_model_version, [relative changed file paths])``.

    Behavior:
      * Calls ``train_baseline_model(seed=..., data_dir=..., output_dir=...,
        model_version=..., c_override=...)`` — the Phase 4 trainer.
      * Trainer reads only ``train`` and ``validation`` partitions
        (loader refuses holdouts at the entry point).
      * Writes the four-file model artifact set under
        ``outputs/baseline_models/<defensive_fix_id>/`` and a candidate
        threshold overlay under
        ``outputs/decision_thresholds/<defensive_fix_id>.yaml``.
      * The four files have the same shape as ``baseline_v1`` so Phase 5
        ``_bundle_for_version`` loads them by directory name.

    Raises:
        ValueError: ``manifest.fix_type != "model_calibration_fix"`` or
                    required ``proposed_training_seed`` /
                    ``proposed_l2_strength`` is missing.
    """
    if manifest.fix_type != "model_calibration_fix":
        raise ValueError(
            f"apply_calibration_fix received fix_type "
            f"{manifest.fix_type!r}; expected 'model_calibration_fix'"
        )
    if manifest.proposed_training_seed is None:
        raise ValueError(
            f"manifest {manifest.defensive_fix_id} has no "
            "proposed_training_seed — nothing to fit."
        )
    if manifest.proposed_l2_strength is None:
        raise ValueError(
            f"manifest {manifest.defensive_fix_id} has no "
            "proposed_l2_strength — nothing to fit."
        )

    candidate_version = manifest.defensive_fix_id
    output_dir = candidate_models_dir(outputs_root) / candidate_version

    train_baseline_model(
        seed=int(manifest.proposed_training_seed),
        data_dir=data_dir,
        output_dir=output_dir,
        model_version=candidate_version,
        c_override=float(manifest.proposed_l2_strength),
        fit_thresholds=True,
        threshold_version=candidate_version,
        threshold_fit_cap_margin=_CANDIDATE_THRESHOLD_CAP_MARGIN,
        fitted_thresholds_dir=outputs_root / "decision_thresholds",
    )

    # Surface relative paths matching what the strategy agent's
    # ``_files_changed_for`` advertised in the public response.
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
    "CANDIDATE_MODELS_SUBDIR",
    "apply_calibration_fix",
    "candidate_models_dir",
    "propose_calibration_fix",
]
