"""Phase 7 bank-defense fixes.

This package owns the deterministic blue-team half of the loop:
proposal, application, judge integration, and visible rejection of
overfit / limit-violating fixes.

Module map (component-by-component fill order):

  * ``atlas.blue_team.manifest``                   — internal vulnerability
                                                     resolver + fix manifest
                                                     persistence (component 2).
  * ``atlas.blue_team.strategy_agent``             — proposal selection.
                                                     Three-way intersection of
                                                     ``request.allowed_fix_types``,
                                                     round-config
                                                     ``defensive_fix_types_allowed``,
                                                     and the Phase 6 card's
                                                     ``recommended_defensive_fix_types``.
  * ``atlas.blue_team.policy_fix_agent``           — propose/apply candidate
                                                     decision-threshold versions.
                                                     Writes
                                                     ``outputs/decision_thresholds/<v>.yaml``
                                                     — never mutates the
                                                     persisted baseline config.
  * ``atlas.blue_team.model_calibration_fix_agent`` — propose/apply candidate
                                                     model versions via the
                                                     existing Phase 4 trainer.
  * ``atlas.blue_team.feature_fix_agent``          — propose/apply candidate
                                                     model versions whose
                                                     training-time transform
                                                     is baked into the model
                                                     weights (public ``/score``
                                                     contract preserved).
  * ``atlas.blue_team.governance_agent``           — brief, deterministic,
                                                     public-safe rationale
                                                     formatter. NEVER overrides
                                                     the judge.
  * ``atlas.blue_team.fix_applier``                — orchestration:
                                                     load_manifest → dispatch →
                                                     evaluate via judge →
                                                     persist report → format
                                                     governance.

Phase 7 contracts:

  * **Synthetic + local-only.** Bible §6.1.
  * **Judge-owned metrics.** Bible §16.7 + §13.3 — blue-team text never
    invents or overrides metrics. ``apply_acceptance_rule`` is the
    single source of truth for ``accepted_by_judge``.
  * **No holdout fitting.** Calibration fits use only train + validation.
    Locked / drifted holdouts are read only by the judge.
  * **No in-place baseline mutation.** ``baseline_v1`` and the persisted
    ``config/decision_thresholds.yaml`` remain intact across all Phase 7
    operations. Candidates live under ``outputs/baseline_models/<v>/``
    and ``outputs/decision_thresholds/<v>.yaml``.
  * **No public scoring contract change.** ``/score`` ``FeatureVector``
    shape unchanged. Feature-fix family operates via training-time
    transforms baked into the model artifact.
  * **Deterministic.** Same inputs → byte-identical proposal/apply/judge
    JSON.
  * **Closed-enum text only.** ``description``, ``expected_benefit``,
    governance rationale, and persisted strings come from fixed
    templates / closed enums. No free-form text path.
  * **`applied` semantics**: ``applied=true`` ⇔ candidate was materialized
    AND judge-accepted. ``applied=false`` ⇔ candidate materialized but
    judge-rejected. Artifacts are persisted in BOTH cases.
"""

__all__: list[str] = []
