"""Phase 4 baseline model + scoring policy.

This package owns:

- ``atlas.model.train``       — fits the baseline mock scorer on the
                                ``train`` partition only (Phase 4 contract).
- ``atlas.model.calibration`` — fits score calibration on ``validation``
                                only. No holdout fitting.
- ``atlas.model.scorer``      — applies the trained baseline + calibrator
                                to a ``FeatureVector`` and returns the
                                calibrated score in ``[0, 1]``.
- ``atlas.model.policy``      — maps ``score + feature context`` to
                                ``decision_action`` / ``decision_band`` /
                                ``reason_codes`` using
                                ``config/decision_thresholds.yaml``.

Phase 4 contracts:
  * Synthetic + local-only.
  * No fit-time leakage. ``clean_holdout``, ``locked_adaptive_holdout``,
    ``drifted_holdout`` are NEVER used for fitting.
  * No label leakage into scoring inputs. ``synthetic_truth_label`` is read
    only at training time as the supervised target. Runtime feature matrix
    excludes labels by construction.
  * Deterministic. Same inputs + pinned ``random_state`` → identical
    artifacts and identical per-event scores.
  * ``model_version = "baseline_v1"`` and
    ``threshold_version = "thresholds_v1"`` in this phase.
"""

__all__: list[str] = []
